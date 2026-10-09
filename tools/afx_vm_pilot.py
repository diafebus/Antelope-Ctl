#!/usr/bin/env python3
"""Coordinate Windows GUI scans and metadata discovery with passive Linux USB capture.

Never opens HID or sends device commands. Requests match reviewed plans or
bounded metadata-generated plans on channel2. Evidence remains local.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
import math
import os
import re
from pathlib import Path
import subprocess
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.scan_afx_capture import analyze_reports, PARAMETER_OPCODES
from tools.afx_scan_discovery import discovery_plan, block_feedback

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def recorder_lock(results):
    """One coordinator per shared folder; kernel releases locks after exit.

    Keep the inode after releasing: unlinking it could let another process
    lock a different inode while a listener still owns the old one.
    """
    with (results/'.linux-recorder.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A recorder is already waiting for this shared folder; use that recorder') from None
        try:
            lock.seek(0)
            lock.truncate()
            lock.write(json.dumps({'pid': os.getpid()}))
            lock.flush()
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def planned_actions(plan):
    actions = []
    for control in plan['controls']:
        if control['kind'] == 'knob_range':
            phases = ['minimum', 'maximum']
        elif control['kind'] == 'wheel_button':
            phases = ['wheel forward', 'wheel back']
        elif control['kind'] == 'key_button':
            phases = ['PageDown', 'PageUp']
        elif control['kind'] in ('selector_cycle', 'selector_positions', 'menu_positions'):
            phases = [f'position-{n}' for n in range(1, control['positions'] + 1)]
            if control['kind'] in ('selector_positions', 'menu_positions'):
                phases.append('restore')
        else:
            phases = ['click', 'click back']
        actions.extend((control, phase) for phase in phases)
    return actions


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def device_location(profile, sysfs=Path('/sys/bus/usb/devices')):
    identity = profile['device']
    matches = []
    for path in sysfs.iterdir():
        try:
            if (int((path/'idVendor').read_text().strip(), 16),
                int((path/'idProduct').read_text().strip(), 16)) != (
                    int(identity['vid'], 16), int(identity['pid'], 16)):
                continue
            matches.append({'sysfs': path.name, 'bus': int((path/'busnum').read_text()),
                            'address': int((path/'devnum').read_text())})
        except (OSError, ValueError):
            continue
    if len(matches) != 1:
        raise RuntimeError('Exactly one profile-matching Orion must be connected')
    return matches[0]


def load_plans():
    document = json.loads((ROOT/'tools/windows/afx-scan-plans.json').read_text())
    plans = document['plans']
    policy = document['wheel_policy']
    if (set(policy) != {'step_delta', 'pause_ms', 'max_pulses'}
            or any(type(v) is not int for v in policy.values())
            or not 1 <= policy['step_delta'] <= 30 or not 1000 <= policy['pause_ms'] <= 3000
            or not 1 <= policy['max_pulses'] <= 12
            or policy['step_delta'] * policy['max_pulses'] > 120
            or policy['pause_ms'] * policy['max_pulses'] > 20000):
        raise ValueError('Invalid bounded wheel pacing policy')
    for plan in plans:
        controls = plan['controls']
        if any(c['kind'] == 'wheel_button' for c in controls):
            plan['wheel_policy'] = policy
        limit = 24 if any(c['kind'] == 'knob_range' for c in controls) else 3
        if (plan['channel'] != 2 or not 1 <= len(controls) <= limit or
                not re.fullmatch(r'[A-Za-z0-9_-]+', plan['panel']) or
                len({c['id'] for c in controls}) != len(controls) or
                any(c['kind'] not in ('binary_button', 'knob_range', 'selector_cycle', 'selector_positions', 'wheel_button', 'menu_positions', 'key_button') or not re.fullmatch(r'[A-Za-z0-9_-]+', c['id']) for c in controls)):
            raise ValueError('Invalid reviewed GUI plan or scope')
        for control in controls:
            if control['kind'] == 'key_button' and (control.get('dwell_ms') != 5000
                    or type(control.get('positions')) is not int or not 2 <= control['positions'] <= 8
                    or control.get('activation') != 'click_open_escape_close'):
                raise ValueError('Key trial requires reviewed finite activation and five-second dwell')
            if control['kind'] == 'menu_positions' and (type(control.get('positions')) is not int
                    or not 2 <= control['positions'] <= 8 or type(control.get('dwell_ms')) is not int
                    or not 3000 <= control['dwell_ms'] <= 10000):
                raise ValueError('Menu requires a reviewed finite count and slow dwell')
            if control['kind'] in ('selector_cycle', 'selector_positions') and (type(control.get('positions')) is not int or not 2 <= control['positions'] <= 8 or not control.get('visual_region')):
                raise ValueError('Selector requires a reviewed finite count and visual region')
            if control['kind'] == 'selector_positions':
                points = control.get('position_points', [])
                if len(points) != control['positions'] or any(not all(type(p.get(k)) in (int, float) and math.isfinite(p[k]) and 0 < p[k] < 1 for k in ('x', 'y')) for p in points):
                    raise ValueError('Direct selector needs reviewed points inside its control')
    return {plan['id']: plan for plan in plans}


def wire_feedback(reports, control, effect_type, phase, out_endpoint=1, instance=None, previous_payload_hex=None, after_frame=0):
    """Read a captured write byte, never query the device or infer a UI scale."""
    wire = control['wire']
    samples = [(number, data) for number, _, ep, data in reports
               if number > after_frame and ep == out_endpoint and data[0] == 0x70 and data[4] in PARAMETER_OPCODES
               and data[16] == 0xd5 and data[18] == effect_type
               and (instance is None or data[19] == instance)]
    if not samples:
        return {'observed_raw': None, 'endpoint_verified': False, 'continue': True,
                'source': 'no captured parameter write; endpoint unverified'}
    number, data = samples[-1]
    offset = wire['offset']
    value = struct.unpack('<f', data[offset:offset + 4])[0] if wire.get('width', 1) == 4 else data[offset]
    expected = wire['range'][0 if phase == 'minimum' else 1]
    payload_hex = data[20:].hex()
    verified = value == expected and payload_hex == previous_payload_hex
    return {'observed_raw': value, 'frame': number, 'endpoint_verified': verified,
            'parameter_payload_hex': payload_hex, 'continue': not verified,
            'source': 'captured parameter write and stable full block; not device readback'}


def validate_wire_controls(plan, catalog):
    effect = next(e for e in catalog['effects'] if e['id'] == plan['effect_id'])
    implementation = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
    for control in plan['controls']:
        if control['kind'] in ('selector_cycle', 'selector_positions', 'menu_positions', 'key_button'):
            candidate = implementation['parameter_observation']['preserved_fields'][control['candidate_field']]
            if control['observed_field_offset'] != candidate['offset']:
                raise ValueError('Selector candidate must match its catalog preserved field')
        if control.get('feedback') not in ('captured_wire', 'captured_toggle'):
            continue
        wire = control['wire']
        if wire.get('source') == 'labelled_gui_observations':
            encoding = implementation['parameter_observation']['labelled_gui_observations'][wire['control_id']]
            expected_range = encoding['observed_wire_range']
            if encoding.get('encoding') != 'float32-le' or wire.get('width') != 4:
                raise ValueError('Observed float fields require measured float32-le encoding')
        else:
            encoding = implementation['control_encodings'][wire['control_id']]
            expected_range = encoding['range']
        if (wire['offset'] != encoding['offset'] or wire['range'] != expected_range
                or wire.get('width', 1) != encoding.get('width', 1)):
            raise ValueError('Wire endpoint feedback must match the captured catalog field')


def bypass_layout_for(plan, catalog):
    effect = next(e for e in catalog['effects'] if e['id'] == plan['effect_id'])
    implementation = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
    layout = implementation.get('bypass_observation')
    if layout is None:
        return None
    offsets = [layout[key] for key in ('instance_offset', 'type_offset', 'state_offset')]
    if (layout['status'] != 'capture-observed' or layout['opcode'] != '0x14'
            or layout['selector'] != '0x98' or sorted(offsets) != [17, 18, 19]):
        raise ValueError('Bypass capture layout must match model-local observed fields')
    return layout


def verify_wire_changes(reports, boundary, control, effect_type, instance, out_endpoint=1):
    samples = [(number, data) for number, _, ep, data in reports
               if ep == out_endpoint and data[0] == 0x70 and data[4] in PARAMETER_OPCODES
               and data[16] == 0xd5 and data[18] == effect_type and data[19] == instance]
    previous = None
    for number, data in samples:
        if number > boundary and previous is not None:
            changed = {offset for offset in range(20, len(data)) if previous[offset] != data[offset]}
            offset = control['wire']['offset']
            allowed = set(range(offset, offset + control['wire'].get('width', 1)))
            if changed - allowed:
                raise RuntimeError('GUI gesture changed bytes outside its reviewed wire field')
        previous = data


def validate_request(request, discovery=None):
    if not isinstance(request, dict):
        raise ValueError('Malformed guest request')
    plans = load_plans()
    legacy = {'version': 1, 'panel': 'Instinct', 'channel': 2,
              'control': 'AltMorphButton', 'actions': 2}
    if discovery is None and request == legacy:
        return plans['instinct-altmorph']
    plan = plans.get(request.get('plan_id'))
    if discovery is not None:
        plan = discovery
    expected = None if plan is None else {'version': 2, 'plan_id': plan['id'],
        'panel': plan['panel'], 'channel': plan['channel'],
        'controls': [c['id'] for c in plan['controls']], 'actions': len(planned_actions(plan))}
    if discovery is not None:
        expected.update(version=3, executed_plan=plan)
    if plan is None or request != expected:
        raise ValueError('Guest request must match a reviewed host GUI plan exactly')
    return plan


def plan_effect_type(plan):
    catalog = json.loads((ROOT/'profiles/afx_effects.json').read_text())
    effect = next(e for e in catalog['effects'] if e['id'] == plan['effect_id'])
    implementation = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
    return implementation['type_id']


def verify_menu_labels(completed, control, phase, previous=None):
    names = completed.get('option_names')
    if (not isinstance(names, list) or len(names) != control['positions']
            or any(not isinstance(n, str) or not n.strip() for n in names)
            or len(set(names)) != len(names) or (previous is not None and names != previous)):
        raise RuntimeError('Menu choices are missing, ambiguous or changed during capture')
    initial = completed.get('starting_selection')
    start = completed.get('starting_position')
    if type(start) is not int or not 0 <= start < len(names) or names[start] != initial:
        raise RuntimeError('Starting menu choice was not identified exactly')
    selected = initial if phase == 'restore' else names[int(phase.split('-')[1]) - 1]
    if completed.get('selection') != selected or completed.get('popup_closed') is not True:
        raise RuntimeError('Menu did not select its named choice and close')
    if completed.get('dwell_ms') != control['dwell_ms']:
        raise RuntimeError('Menu choice was not held for the reviewed dwell')
    return names


def verify_wheel_pulses(completed, policy, phase, expected_start, forward_count=None):
    pulses = completed.get('wheel_pulses')
    limit = policy['max_pulses'] if phase == 'wheel forward' else forward_count
    if type(limit) is not int or not isinstance(pulses, list) or not 1 <= len(pulses) <= limit:
        raise RuntimeError('Wheel pulse sequence exceeds its reviewed bound')
    delta = policy['step_delta'] * (-1 if phase == 'wheel forward' else 1)
    for index, pulse in enumerate(pulses):
        if (not isinstance(pulse, dict) or pulse.get('delta') != delta
                or pulse.get('pause_ms') != policy['pause_ms']
                or pulse.get('starting_selection') != expected_start
                or not isinstance(pulse.get('selection'), str) or not pulse['selection'].strip()):
            raise RuntimeError('Wheel pulse differs from reviewed pacing or GUI state')
        changed = pulse['selection'] != expected_start
        if changed != (index == len(pulses) - 1):
            raise RuntimeError('Wheel continued after a selection change or never changed')
    if pulses[-1]['selection'] != completed.get('selection'):
        raise RuntimeError('Wheel final selection differs from its pulse evidence')
    return len(pulses)


def verify_key_result(completed, control, phase, initial=None, changed=None, previous_names=None):
    start, selected = completed.get('starting_selection'), completed.get('selection')
    names = completed.get('option_names')
    if (completed.get('key') != phase or type(completed.get('keypresses')) is not int
            or completed['keypresses'] != 1 or completed.get('dwell_ms') != 5000
            or completed.get('keyboard_focus_verified') is not True
            or completed.get('activation_verified') is not True
            or not isinstance(start, str) or not start.strip()
            or not isinstance(selected, str) or not selected.strip()):
        raise RuntimeError('Key trial lacks exact key, focus, activation or paced GUI evidence')
    if (not isinstance(names, list) or len(names) != control['positions']
            or any(not isinstance(n, str) or not n.strip() for n in names)
            or len(set(names)) != len(names) or start not in names
            or (previous_names is not None and names != previous_names)):
        raise RuntimeError('Key activation choices are missing or changed')
    if phase == 'PageDown':
        position = names.index(start)
        if position + 1 >= len(names) or selected != names[position + 1]:
            raise RuntimeError('Page Down did not select the next observed choice')
    elif phase != 'PageUp' or start != initial or selected != initial or changed == selected:
        raise RuntimeError('Page Up did not restore the starting choice')
    return start, selected


def verify_action_events(events, expected=None, effect_type=75):
    targets = {(event['opcode'], event['subcommand'], event['type'], event['instance'])
               for event in events if 'type' in event}
    if len(targets) != 1 or next(iter(targets))[2] != effect_type:
        raise RuntimeError('Expected one target effect instance; missing, linked or other OUT requires review')
    if any('type' not in event for event in events):
        raise RuntimeError('Unexpected other OUT command during button trial; stop for review')
    target = next(iter(targets))
    if expected is not None and target != expected:
        raise RuntimeError('Target instance or command family changed; stop for review')
    return target


def read_reports(capture, location, transport, allow_incomplete=False):
    # Identity comes from a fresh profile-matching sysfs witness, checked again
    # at completion. No enumeration/reconnect or speculative device query.
    size = transport['report_size']
    out_ep, in_ep = (int(transport[key], 0) for key in ('out_endpoint', 'in_endpoint'))
    display = (f"usb.bus_id == {location['bus']} && usb.device_address == {location['address']}"
               f' && usb.data_len == {size} && (usb.endpoint_address == {out_ep} || usb.endpoint_address == {in_ep})')
    result = subprocess.run(['tshark', '-r', str(capture), '-Y', display, '-T', 'fields',
        '-e', 'frame.number', '-e', 'frame.time_epoch', '-e', 'usb.endpoint_address',
        '-e', 'usbhid.data', '-e', 'usb.capdata'], capture_output=True, text=True)
    if result.returncode and not (allow_incomplete and result.returncode == 2 and result.stdout):
        raise RuntimeError('tshark could not read the capture; inspect dumpcap.log')
    reports = []
    for line in result.stdout.splitlines():
        fields = line.split('\t')
        if len(fields) < 4:
            continue
        try:
            raw = next((value for value in fields[3:] if value), '')
            data = bytes.fromhex(raw.replace(':', ''))
            if len(data) == size:
                reports.append((int(fields[0]), float(fields[1]), int(fields[2], 0), data))
        except ValueError:
            continue
    return reports


def labelled_actions(reports, windows, out_endpoint=1, bypass_layout=None):
    """Report captured byte differences without promoting a writable map."""
    result = []
    previous = {}
    last_end = -math.inf
    last_frame = -1
    for window in windows:
        start, end = window['start_epoch'], window['end_epoch']
        frame_bound = 'start_frame_exclusive' in window or 'end_frame_inclusive' in window
        if frame_bound:
            first, final = window['start_frame_exclusive'], window['end_frame_inclusive']
            if (type(first) is not int or type(final) is not int or
                    not 0 <= first < final or first < last_frame):
                raise ValueError('Invalid or overlapping frame window')
            last_frame = final
        else:
            if not (math.isfinite(start) and math.isfinite(end) and last_end < start < end):
                raise ValueError('Invalid action timing')
            last_end = end
        events = []
        for number, epoch, endpoint, data in reports:
            in_window = first < number <= final if frame_bound else start <= epoch <= end
            if not in_window or endpoint != out_endpoint or data[0] != 0x70:
                continue
            if data[4] == 0x14 and data[16] == 0x98:
                events.append({'frame': number, 'opcode': '0x14', 'subcommand': '0x98',
                               'type': data[bypass_layout['type_offset']] if bypass_layout else data[18],
                               'instance': data[bypass_layout['instance_offset']] if bypass_layout else data[19],
                               'state': data[bypass_layout['state_offset']] if bypass_layout else data[17],
                               'layout_source': 'model-local captured catalog' if bypass_layout else 'legacy unverified layout',
                               'status': 'captured bypass gesture; polarity unverified'})
                continue
            if data[16] != 0xd5 or data[4] not in PARAMETER_OPCODES:
                events.append({'frame': number, 'opcode': hex(data[4]),
                               'selector': hex(data[16]), 'status': 'other OUT command'})
                continue
            key = (data[4], data[17], data[18], data[19])
            baseline = previous.get(key)
            offsets = ([i for i in range(20, len(data)) if data[i] != baseline[i]]
                       if baseline is not None else None)
            events.append({'frame': number, 'opcode': hex(key[0]), 'subcommand': hex(key[1]),
                'type': key[2], 'instance': key[3], 'changed_offsets_from_previous_action': offsets,
                'changed_bytes': ({str(i): [baseline[i], data[i]] for i in offsets}
                                  if offsets is not None else {}),
                'status': 'capture observation; wire semantics unverified'})
            previous[key] = data
        result.append({**window, 'events': events, 'missing_OUT_witness': not bool(events)})
    return result


def wait_file(path, seconds, process=None):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if (path.parent/'guest-error.json').is_file():
            raise RuntimeError('Guest stopped; inspect guest-error.json before any further action')
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8-sig'))
        if process is not None and process.poll() is not None:
            raise RuntimeError('Capture ended before the guest completed its action')
        time.sleep(.1)
    raise TimeoutError(f'Timed out waiting for {path.name}; no further actions permitted')


def run_job(job, profile):
    request = json.loads((job/'request.json').read_text(encoding='utf-8-sig'))
    generated = None
    if (job/'discovery-inventory.json').is_file():
        inventory = json.loads((job/'discovery-inventory.json').read_text(encoding='utf-8-sig'))
        generated = discovery_plan(inventory, json.loads((ROOT/'profiles/afx_effects.json').read_text()))
    plan = validate_request(request, generated)
    effect_type = plan_effect_type(plan)
    catalog = json.loads((ROOT/'profiles/afx_effects.json').read_text())
    validate_wire_controls(plan, catalog)
    bypass_layout = bypass_layout_for(plan, catalog)
    location = device_location(profile)
    transport = profile['transport']
    in_ep, out_ep = (int(transport[key], 0) for key in ('in_endpoint', 'out_endpoint'))
    interface = f"usbmon{location['bus']}"
    if not Path('/dev', interface).exists():
        raise RuntimeError('usbmon is not loaded; load it before starting the pilot')
    write_json(job/'host-device.json', {'profile': 'orion_studio_sc.json',
        'identity_source': 'profile VID/PID matched against live sysfs', **location})
    capture = job/f"{plan['panel']}-channel{plan['channel']}.pcapng"
    if capture.exists():
        raise RuntimeError('Refusing to overwrite an existing capture')
    windows = []
    expected_target = None
    selector_values = {}
    selector_baselines = {}
    toggle_baselines = {}
    wheel_baselines = {}
    wheel_counts = {}
    wheel_selections = {}
    menu_names = {}
    menu_starts = {}
    key_states = {}
    block_minima = {}
    actions = planned_actions(plan)
    has_knobs = any(c['kind'] == 'knob_range' for c in plan['controls'])
    has_wheel = any(c['kind'] in ('wheel_button', 'menu_positions', 'key_button') for c in plan['controls'])
    with (job/'dumpcap.log').open('x') as log:
        process = subprocess.Popen(['dumpcap', '-i', interface, '-s', '0',
            '-a', ('duration:600' if len(plan['controls']) > 3 else 'duration:240') if has_knobs else ('duration:180' if has_wheel else 'duration:60'),
            '-a', 'filesize:100000', '-w', str(capture)],
            stdout=log, stderr=log)
        try:
            # Prove that full matching IN reports reach the capture before
            # releasing the guest. Actual OUT is checked after each action.
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise RuntimeError('dumpcap failed; see dumpcap.log')
                try:
                    reports = read_reports(capture, location, transport, allow_incomplete=True)
                except RuntimeError:
                    reports = []
                if any(ep == in_ep and data[0] in (0x73, 0x75) for _, _, ep, data in reports):
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('No complete Orion IN reports; guest gestures remain blocked')
                time.sleep(.3)
            ready_frame = max(r[0] for r in reports)
            start_ready = time.time()
            write_json(job/'ready.json', {'version': 1, 'capture_ready': True})
            for index, (control, phase) in enumerate(actions, 1):
                action_request = wait_file(job/f'action-{index}-request.json',
                    45 if control['kind'] == 'key_button' and index == 1 else 15, process)
                expected_request = {'action': index, 'control': control['id']}
                if request['version'] == 1:
                    expected_request = {'action': index}
                if action_request != expected_request:
                    raise RuntimeError('Guest action does not match the reviewed plan; no click permitted')
                if device_location(profile) != location:
                    raise RuntimeError('Orion connection changed; no further gestures')
                before_reports = read_reports(capture, location, transport, allow_incomplete=True)
                if not before_reports:
                    raise RuntimeError('No current capture boundary; no click permitted')
                first_frame = max(row[0] for row in before_reports)
                if control['kind'] == 'key_button' and index == 1:
                    setup = {'start_frame_exclusive': ready_frame, 'end_frame_inclusive': first_frame,
                             'start_epoch': start_ready, 'end_epoch': time.time()}
                    setup_events = labelled_actions(before_reports, [setup], out_ep, bypass_layout)[0]['events']
                    write_json(job/'key-activation-window.json', {**setup, 'events': setup_events})
                    if setup_events:
                        raise RuntimeError('Dropdown activation sent OUT controls; no key permitted')
                if control['kind'] == 'key_button' and control['id'] in key_states:
                    previous_key = key_states[control['id']]
                    if any(number > previous_key['boundary'] and ep == out_ep and data[0] == 0x70
                           for number, _, ep, data in before_reports):
                        raise RuntimeError('New OUT since accepted key choice; no restoration key permitted')
                if control['kind'] in ('selector_cycle', 'selector_positions', 'menu_positions'):
                    prior = [data for _, _, ep, data in before_reports if ep == out_ep and data[0] == 0x70 and data[4] in PARAMETER_OPCODES and data[16] == 0xd5 and data[18] == effect_type and (expected_target is None or data[19] == expected_target[3])]
                    if not prior and control['kind'] == 'selector_cycle':
                        raise RuntimeError('Selector cycle requires a fresh preceding parameter block')
                    raw = prior[-1][control['observed_field_offset']] if prior else None
                    if control['id'] not in selector_baselines:
                        selector_baselines[control['id']] = raw
                    elif raw != selector_values[control['id']][-1]:
                        raise RuntimeError('Selector changed since accepted position; no further click')
                if control.get('feedback') == 'captured_toggle':
                    prior = [data for _, _, ep, data in before_reports if ep == out_ep and data[0] == 0x70 and data[4] in PARAMETER_OPCODES and data[16] == 0xd5 and data[18] == effect_type and (expected_target is None or data[19] == expected_target[3])]
                    if not prior:
                        raise RuntimeError('Measured toggle requires a preceding captured parameter block')
                    raw = prior[-1][control['wire']['offset']]
                    if raw not in control['wire']['range']:
                        raise RuntimeError('Toggle baseline is outside its measured binary range')
                    if control['id'] not in toggle_baselines:
                        toggle_baselines[control['id']] = raw
                    elif raw == toggle_baselines[control['id']]:
                        raise RuntimeError('Toggle changed since accepted trial; no restore click')
                start = time.time()
                write_json(job/f'action-{index}-go.json', {'action': index})
                feedback_history = []
                discovery_baseline = None
                unchanged_sweeps = 0
                last_sweep_frame = first_frame
                if control.get('feedback') == 'captured_block':
                    wait_file(job/f'action-{index}-primed.json', 10, process)
                    time.sleep(.3)
                    primed_reports = read_reports(capture, location, transport, allow_incomplete=True)
                    primed_events = labelled_actions(primed_reports, [{'start_frame_exclusive': first_frame,
                        'end_frame_inclusive': max(r[0] for r in primed_reports),
                        'start_epoch': start, 'end_epoch': time.time()}], out_ep, bypass_layout)[0]['events']
                    if primed_events:
                        expected_target = verify_action_events(primed_events, expected_target, effect_type)
                    if expected_target is None:
                        raise RuntimeError('Discovery priming did not establish a captured target')
                    prior = [data[20:].hex() for _, _, ep, data in primed_reports if ep == out_ep
                        and data[0] == 0x70 and data[4] in PARAMETER_OPCODES and data[16] == 0xd5
                        and data[18] == effect_type and data[19] == expected_target[3]]
                    if not prior:
                        raise RuntimeError('No primed parameter block; discovery remains unresolved')
                    discovery_baseline = prior[-1]
                    first_frame = last_sweep_frame = max(r[0] for r in primed_reports)
                    write_json(job/f'action-{index}-primed-ack.json', {'status': 'ok'})
                if control.get('feedback') in ('captured_wire', 'captured_block'):
                    for sweep in range(1, 13):
                        wait_file(job/f'action-{index}-sweep-{sweep}-done.json', 10, process)
                        time.sleep(.3)
                        current_reports = read_reports(capture, location, transport, allow_incomplete=True)
                        sweep_window = {'start_epoch': start, 'end_epoch': time.time(),
                                        'start_frame_exclusive': first_frame,
                                        'end_frame_inclusive': max(row[0] for row in current_reports)}
                        events = labelled_actions(current_reports, [sweep_window], out_ep, bypass_layout)[0]['events']
                        if events:
                            expected_target = verify_action_events(events, expected_target, effect_type)
                            if control.get('feedback') == 'captured_wire':
                                verify_wire_changes(current_reports, first_frame, control, effect_type,
                                                    expected_target[3], out_ep)
                        if control.get('feedback') == 'captured_block':
                            current_frame = max(r[0] for r in current_reports)
                            if current_frame <= last_sweep_frame:
                                raise RuntimeError('Capture stalled during discovery sweep')
                            feedback = block_feedback(current_reports, effect_type,
                                expected_target[3] if expected_target else None, first_frame,
                                feedback_history[-1].get('parameter_payload_hex') if feedback_history else None,
                                out_ep, PARAMETER_OPCODES)
                            unchanged_sweeps = unchanged_sweeps + 1 if feedback['plateau_observed'] else 0
                            payload = feedback['parameter_payload_hex']
                            candidate = unchanged_sweeps >= 2 and payload != discovery_baseline and payload is not None
                            fresh = any(n > last_sweep_frame and ep == out_ep and data[0] == 0x70
                                and data[4] in PARAMETER_OPCODES and data[16] == 0xd5
                                and data[18] == effect_type and data[19] == expected_target[3]
                                for n, _, ep, data in current_reports)
                            feedback['continue'] = not candidate
                            feedback['plateau_observed'] = candidate
                            feedback['new_target_report'] = fresh
                            feedback['basis'] = 'two completed sweeps without further target changes; capture advances'
                            feedback['unchanged_sweeps'] = unchanged_sweeps
                            last_sweep_frame = current_frame
                        else:
                            feedback = wire_feedback(current_reports, control, effect_type, phase, out_ep,
                                                 expected_target[3] if expected_target else None,
                                                 feedback_history[-1].get('parameter_payload_hex') if feedback_history else None,
                                                 first_frame)
                        feedback_history.append(feedback)
                        write_json(job/f'action-{index}-sweep-{sweep}-feedback.json', feedback)
                        if not feedback['continue']:
                            break
                    else:
                        raise RuntimeError('Captured endpoint was not reached in twelve continuous sweeps')
                action_timeout = 60 if has_knobs else 10
                if control['kind'] == 'wheel_button':
                    action_timeout = 10 + math.ceil(plan['wheel_policy']['pause_ms'] * plan['wheel_policy']['max_pulses'] / 1000)
                if control['kind'] == 'menu_positions':
                    action_timeout = 15 + math.ceil(control['dwell_ms'] / 1000)
                if control['kind'] == 'key_button':
                    action_timeout = 15
                completed = wait_file(job/f'action-{index}-done.json', action_timeout, process)
                window = {'action': index, 'control': control['id'], 'label': control['label'],
                          'gesture': phase,
                          'start_epoch': start, 'end_epoch': time.time(),
                          'start_frame_exclusive': first_frame,
                          'matching_method': 'recording frame boundaries; host times are metadata only',
                          'wire_feedback': feedback_history,
                          'guest_visual_result': completed}
                # dumpcap can buffer output briefly after the guest completes.
                deadline = time.monotonic() + 3
                while True:
                    reports = read_reports(capture, location, transport, allow_incomplete=True)
                    window['end_frame_inclusive'] = max((row[0] for row in reports), default=first_frame)
                    if window['end_frame_inclusive'] <= first_frame:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Capture did not advance after the action; stop for review')
                        time.sleep(.2)
                        continue
                    events = labelled_actions(reports, [window], out_ep, bypass_layout)[0]['events']
                    if events or time.monotonic() >= deadline:
                        break
                    time.sleep(.2)
                windows.append(window)
                write_json(job/'action-windows.json', windows)
                unchanged_endpoint = (control['kind'] == 'knob_range'
                                     and completed.get('starting_value') == completed.get('displayed_value')
                                     and 'displayed_value' in completed)
                if control.get('feedback') in ('captured_wire', 'captured_block') and feedback_history:
                    unchanged_endpoint = False
                if events or not unchanged_endpoint:
                    if control.get('command_family') == 'bypass':
                        if any(e['opcode'] != '0x14' or e['subcommand'] != '0x98' for e in events):
                            raise RuntimeError('Power gesture sent another command family')
                        target = verify_action_events(events, None, effect_type)
                        if expected_target is not None and target[2:] != expected_target[2:]:
                            raise RuntimeError('Power gesture changed effect instance')
                        if any(e['state'] not in (0, 1) for e in events):
                            raise RuntimeError('Power gesture contains an unknown captured value')
                        window['bypass_events'] = events
                        window['bypass_state_status'] = 'event sequence only; persistent state and polarity unverified'
                    else:
                        expected_target = verify_action_events(events, expected_target, effect_type)
                if control.get('feedback') == 'captured_toggle':
                    verify_wire_changes(reports, first_frame, control, effect_type, expected_target[3], out_ep)
                    samples = [data for number, _, ep, data in reports if number > first_frame and ep == out_ep and data[0] == 0x70 and data[4] in PARAMETER_OPCODES and data[16] == 0xd5 and data[18] == effect_type and data[19] == expected_target[3]]
                    values = {data[control['wire']['offset']] for data in samples}
                    expected = toggle_baselines[control['id']]
                    if phase == 'click':
                        expected = next(v for v in control['wire']['range'] if v != expected)
                    if values != {expected}:
                        raise RuntimeError('Measured toggle did not change/restore its captured value')
                    window['observed_toggle_raw'] = expected
                    window['toggle_restoration_source'] = 'captured parameter writes; not device readback'
                if control['kind'] == 'menu_positions':
                    menu_names[control['id']] = verify_menu_labels(completed, control, phase, menu_names.get(control['id']))
                    initial = completed['starting_selection']
                    if control['id'] in menu_starts and menu_starts[control['id']] != initial:
                        raise RuntimeError('Starting menu choice changed during capture')
                    menu_starts[control['id']] = initial
                if control['kind'] == 'key_button':
                    prior = key_states.get(control['id'])
                    initial, selection = verify_key_result(completed, control, phase,
                        prior['initial'] if prior else None, prior['changed'] if prior else None,
                        prior['names'] if prior else None)
                    offset = control['observed_field_offset']
                    verify_wire_changes(reports, first_frame, {'wire': {'offset': offset}},
                        effect_type, expected_target[3], out_ep)
                    samples = [data[20:] for number, _, ep, data in reports if number > first_frame
                        and ep == out_ep and data[0] == 0x70 and data[4] in PARAMETER_OPCODES
                        and data[16] == 0xd5 and data[18] == effect_type and data[19] == expected_target[3]]
                    if not samples or len(set(samples)) != 1:
                        raise RuntimeError('One Page key did not establish one stable captured parameter block')
                    payload = samples[-1]
                    if phase == 'PageDown':
                        key_states[control['id']] = {'initial': initial, 'changed': selection,
                            'payload': payload, 'names': completed['option_names'],
                            'boundary': window['end_frame_inclusive']}
                    else:
                        differences = {20 + n for n, (a, b) in enumerate(zip(prior['payload'], payload)) if a != b}
                        if differences != {offset}:
                            raise RuntimeError('Key round trip changed another field or no captured selector value')
                    window['observed_key_raw'] = payload[offset - 20]
                    window['key_state_source'] = 'labelled captured writes and GUI return; no independent initial readback'
                if control['kind'] in ('selector_cycle', 'selector_positions', 'menu_positions'):
                    offset = control['observed_field_offset']
                    verify_wire_changes(reports, first_frame, {'wire': {'offset': offset}}, effect_type, expected_target[3], out_ep)
                    samples = [data for number, _, ep, data in reports if number > first_frame and ep == out_ep and data[0] == 0x70 and data[16] == 0xd5 and data[18] == effect_type and data[19] == expected_target[3]]
                    values = {data[offset] for data in samples}
                    if control['kind'] == 'selector_cycle' and len(values) != 1:
                        raise RuntimeError('Selector click did not establish one captured position')
                    if not samples or len(values) > 2:
                        raise RuntimeError('Direct selector did not establish a bounded priming/target sequence')
                    value = samples[-1][offset]
                    seen = selector_values.setdefault(control['id'], [])
                    if phase != 'restore' and value in seen:
                        raise RuntimeError('Selector repeated a position before its full traversal')
                    if phase == 'restore' and value != selector_baselines[control['id']]:
                        raise RuntimeError('Direct selector did not restore starting raw value')
                    seen.append(value)
                    if control['kind'] in ('selector_positions', 'menu_positions') and len(seen) == control['positions']:
                        starting_position = completed.get('starting_position')
                        if type(starting_position) is not int or not 0 <= starting_position < control['positions']:
                            raise RuntimeError('Starting selector appearance did not match exactly one captured position')
                        visual_start = seen[starting_position]
                        if selector_baselines[control['id']] is not None and selector_baselines[control['id']] != visual_start:
                            raise RuntimeError('Starting visual position disagrees with preceding captured state')
                        selector_baselines[control['id']] = visual_start
                    if control['kind'] == 'selector_cycle' and len(seen) == control['positions'] and value != selector_baselines[control['id']]:
                        raise RuntimeError('Selector cycle did not restore its captured starting state')
                    window['observed_selector_raw'] = value
                    window['selector_mapping_status'] = 'position screenshot requires label review; no ordinal polarity inferred'
                if control.get('feedback') == 'captured_wire':
                    verify_wire_changes(reports, first_frame, control, effect_type, expected_target[3], out_ep)
                    final_feedback = wire_feedback(reports, control, effect_type, phase, out_ep,
                                                   expected_target[3], feedback_history[-1]['parameter_payload_hex'],
                                                   first_frame)
                    if not final_feedback['endpoint_verified']:
                        raise RuntimeError('Final captured block changed after endpoint feedback; no ACK')
                    window['final_wire_feedback'] = final_feedback
                if control.get('feedback') == 'captured_block':
                    final = block_feedback(reports, effect_type, expected_target[3], first_frame,
                        feedback_history[-1]['parameter_payload_hex'], out_ep, PARAMETER_OPCODES)
                    if not final['plateau_observed']:
                        raise RuntimeError('Captured block changed after plateau; no ACK')
                    payload = final['parameter_payload_hex']
                    if phase == 'minimum':
                        block_minima[control['id']] = payload
                    elif payload == block_minima[control['id']]:
                        raise RuntimeError('Knob sweeps yielded identical blocks; range is unresolved')
                    window['candidate_block_feedback'] = final
                window['wire_events_observed'] = bool(events)
                window['endpoint_range_verified'] = False
                write_json(job/'action-windows.json', windows)
                if control['kind'] == 'wheel_button' or control.get('feedback') == 'gui_toggle':
                    initial = completed.get('starting_selection')
                    selection = completed.get('selection')
                    if not isinstance(initial, str) or not initial.strip() or not isinstance(selection, str) or not selection.strip():
                        raise RuntimeError('Wheel trial requires known GUI selection labels')
                    if control.get('feedback') == 'gui_toggle' and {initial, selection} - {'On', 'Off'}:
                        raise RuntimeError('GUI toggle must report binary labels')
                    if control['kind'] == 'wheel_button':
                        start_selection = initial if phase == 'wheel forward' else wheel_selections[control['id']]
                        count = verify_wheel_pulses(completed, plan['wheel_policy'], phase, start_selection,
                            wheel_counts.get(control['id']))
                        if phase == 'wheel forward':
                            wheel_counts[control['id']] = count
                        wheel_selections[control['id']] = selection
                    if phase in ('wheel forward', 'click'):
                        if initial == selection:
                            raise RuntimeError('Wheel did not change the GUI selection')
                        wheel_baselines[control['id']] = initial
                    elif initial != wheel_baselines[control['id']] or selection != initial:
                        raise RuntimeError('Wheel did not restore the starting GUI selection')
                if completed.get('status') != 'ok':
                    raise RuntimeError('Guest visual verification failed; stop for review')
                ack = {'status': 'ok'}
                if control['kind'] in ('selector_positions', 'menu_positions') and phase == f"position-{control['positions']}":
                    baseline = selector_baselines[control['id']]
                    if baseline not in selector_values[control['id']]:
                        raise RuntimeError('Starting selector state absent from captured positions; no restore guess')
                    ack['restore_position'] = selector_values[control['id']].index(baseline)
                write_json(job/f'action-{index}-ack.json', ack)
            wait_file(job/'completed.json', 5, process)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    if device_location(profile) != location:
        raise RuntimeError('Device location changed; capture identity needs review')
    reports = read_reports(capture, location, transport)
    write_json(job/f"{plan['panel']}-analysis.json", {'status': 'candidate; review required', 'plan_id': plan['id'],
        'device_readback_verified': False, 'visual_restoration': 'see completed.json',
        'packet_loss': 'review dumpcap.log; not automatically certified',
        'labelled_actions': labelled_actions(reports, windows, out_ep, bypass_layout),
        'capture_summary': analyze_reports(reports)})
    write_json(job/'host-completed.json', {'status': 'ok', 'coverage': plan.get('coverage', {'status': 'partial; controls outside plan unknown'})})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared', type=Path, help='antelope-afx-tools directory')
    parser.add_argument('--preflight', type=Path, help='new local directory for a three-second passive capture')
    parser.add_argument('--wait-seconds', type=int, default=900, choices=range(1, 3601))
    parser.add_argument('--serve', action='store_true', help='remain available for successive plugin launches; stop on scan failure')
    args = parser.parse_args()
    profile = json.loads((ROOT/'profiles/orion_studio_sc.json').read_text())
    location = device_location(profile)
    if not Path('/dev', f"usbmon{location['bus']}").exists():
        parser.error('usbmon is not loaded; load it before starting the recorder')
    if args.preflight:
        args.preflight.mkdir(parents=True, exist_ok=False)
        capture = args.preflight/'Orion-preflight.pcapng'
        with (args.preflight/'dumpcap.log').open('x') as log:
            subprocess.run(['dumpcap', '-i', f"usbmon{location['bus']}", '-s', '0',
                '-a', 'duration:3', '-w', str(capture)], stdout=log, stderr=log, check=True)
        if device_location(profile) != location:
            raise RuntimeError('Connection changed during preflight')
        reports = read_reports(capture, location, profile['transport'])
        from collections import Counter
        counts = Counter((ep, data[0]) for _, _, ep, data in reports)
        summary = {'device': location, 'complete_reports': len(reports),
                   'endpoint_magic_counts': {f'{ep:#x}/{magic:#x}': n for (ep, magic), n in counts.items()},
                   'settings_written': False}
        write_json(args.preflight/'summary.json', summary)
        print(json.dumps(summary, indent=2), flush=True)
        return 0 if any(ep == int(profile['transport']['in_endpoint'], 0) and data[0] in (0x73, 0x75)
                        for _, _, ep, data in reports) else 1
    if args.shared is None:
        parser.error('--shared or --preflight is required')
    results = args.shared/'results'
    results.mkdir(exist_ok=True)
    try:
        with recorder_lock(results):
            return listen(args, profile, location, results)
    except RuntimeError as error:
        print(str(error), file=sys.stderr, flush=True)
        return 1


def listen(args, profile, location, results):
    # Hold the exclusive lock before observing or serving any jobs.
    print(f"Ready for GUI scan/discovery requests; Orion on usbmon{location['bus']}. No HID controller opened.", flush=True)
    def jobs():
        return set(results.glob('scan-*')) | set(results.glob('pilot-Instinct-*'))
    existing = jobs()
    discovered = set(results.glob('panel-*'))
    completed_jobs = 0
    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline:
        for folder in sorted(set(results.glob('panel-*')) - discovered):
            if folder.is_symlink() or not (folder/'discovery-request.json').is_file():
                continue
            discovered.add(folder)
            try:
                inventory = json.loads((folder/'inventory.json').read_text(encoding='utf-8-sig'))
                plan = discovery_plan(inventory, json.loads((ROOT/'profiles/afx_effects.json').read_text()))
                write_json(folder/'generated-plan.json', plan)
                deadline = time.monotonic() + args.wait_seconds
                print(f"Prepared {plan['panel']}: {len(plan['controls'])} knobs; other controls listed as pending.", flush=True)
            except (OSError, ValueError, KeyError, TypeError) as error:
                write_json(folder/'host-error.json', {'error': str(error), 'stop': True})
                print(f'Discovery retained for review: {error}', flush=True)
        for job in sorted(jobs() - existing):
            if job.is_symlink() or not (job/'request.json').is_file():
                continue
            try:
                run_job(job, profile)
                print(f'Pilot finished: {job}', flush=True)
                existing.add(job)
                completed_jobs += 1
                if not args.serve:
                    return 0
                deadline = time.monotonic() + args.wait_seconds
                print('Ready for the next plugin through the same launcher.', flush=True)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, TimeoutError) as error:
                write_json(job/'host-error.json', {'error': str(error), 'stop': True})
                print(f'Pilot stopped: {error}. Evidence retained at {job}', file=sys.stderr, flush=True)
                return 1
        time.sleep(.2)
    print(f'Recorder idle timeout; {completed_jobs} scan batch(es) completed.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
