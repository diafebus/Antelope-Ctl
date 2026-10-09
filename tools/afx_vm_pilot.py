#!/usr/bin/env python3
"""Coordinate one reviewed Windows GUI scan with passive Linux USB capture.

Never opens HID or sends device commands. Shared-folder requests must match reviewed JSON plans on channel2. Evidence remains local.
"""
import argparse
import json
import math
import re
from pathlib import Path
import subprocess
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.scan_afx_capture import analyze_reports, PARAMETER_OPCODES

ROOT = Path(__file__).resolve().parents[1]


def planned_actions(plan):
    return [(control, phase) for control in plan['controls']
            for phase in (('minimum', 'maximum') if control['kind'] == 'knob_range'
                          else tuple(f'position-{n}' for n in range(1, control['positions'] + 1))
                          if control['kind'] == 'selector_cycle' else ('click', 'click back'))]


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
    plans = json.loads((ROOT/'tools/windows/afx-scan-plans.json').read_text())['plans']
    for plan in plans:
        controls = plan['controls']
        limit = 24 if any(c['kind'] == 'knob_range' for c in controls) else 3
        if (plan['channel'] != 2 or not 1 <= len(controls) <= limit or
                not re.fullmatch(r'[A-Za-z0-9_-]+', plan['panel']) or
                len({c['id'] for c in controls}) != len(controls) or
                any(c['kind'] not in ('binary_button', 'knob_range', 'selector_cycle') or not re.fullmatch(r'[A-Za-z0-9_-]+', c['id']) for c in controls)):
            raise ValueError('Invalid reviewed GUI plan or scope')
        for control in controls:
            if control['kind'] == 'selector_cycle' and (type(control.get('positions')) is not int or not 2 <= control['positions'] <= 8 or not control.get('visual_region')):
                raise ValueError('Selector cycle requires a reviewed finite count and visual region')
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
        if control['kind'] == 'selector_cycle':
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


def validate_request(request):
    plans = load_plans()
    legacy = {'version': 1, 'panel': 'Instinct', 'channel': 2,
              'control': 'AltMorphButton', 'actions': 2}
    if request == legacy:
        return plans['instinct-altmorph']
    plan = plans.get(request.get('plan_id'))
    if plan is None or request != {'version': 2, 'plan_id': plan['id'],
        'panel': plan['panel'], 'channel': plan['channel'],
        'controls': [c['id'] for c in plan['controls']], 'actions': len(planned_actions(plan))}:
        raise ValueError('Guest request must match a reviewed host GUI plan exactly')
    return plan


def plan_effect_type(plan):
    catalog = json.loads((ROOT/'profiles/afx_effects.json').read_text())
    effect = next(e for e in catalog['effects'] if e['id'] == plan['effect_id'])
    implementation = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
    return implementation['type_id']


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


def labelled_actions(reports, windows, out_endpoint=1):
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
                               'type': data[18], 'instance': data[19], 'state': data[17],
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
    plan = validate_request(request)
    effect_type = plan_effect_type(plan)
    validate_wire_controls(plan, json.loads((ROOT/'profiles/afx_effects.json').read_text()))
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
    actions = planned_actions(plan)
    has_knobs = any(c['kind'] == 'knob_range' for c in plan['controls'])
    with (job/'dumpcap.log').open('x') as log:
        process = subprocess.Popen(['dumpcap', '-i', interface, '-s', '0',
            '-a', ('duration:600' if len(plan['controls']) > 3 else 'duration:240') if has_knobs else 'duration:60',
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
            write_json(job/'ready.json', {'version': 1, 'capture_ready': True})
            for index, (control, phase) in enumerate(actions, 1):
                action_request = wait_file(job/f'action-{index}-request.json', 15, process)
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
                if control['kind'] == 'selector_cycle':
                    prior = [data for _, _, ep, data in before_reports if ep == out_ep and data[0] == 0x70 and data[4] in PARAMETER_OPCODES and data[16] == 0xd5 and data[18] == effect_type and (expected_target is None or data[19] == expected_target[3])]
                    if not prior:
                        raise RuntimeError('Selector cycle requires a fresh preceding parameter block')
                    raw = prior[-1][control['observed_field_offset']]
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
                if control.get('feedback') == 'captured_wire':
                    for sweep in range(1, 13):
                        wait_file(job/f'action-{index}-sweep-{sweep}-done.json', 10, process)
                        time.sleep(.3)
                        current_reports = read_reports(capture, location, transport, allow_incomplete=True)
                        sweep_window = {'start_epoch': start, 'end_epoch': time.time(),
                                        'start_frame_exclusive': first_frame,
                                        'end_frame_inclusive': max(row[0] for row in current_reports)}
                        events = labelled_actions(current_reports, [sweep_window], out_ep)[0]['events']
                        if events:
                            expected_target = verify_action_events(events, expected_target, effect_type)
                            verify_wire_changes(current_reports, first_frame, control, effect_type,
                                                expected_target[3], out_ep)
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
                completed = wait_file(job/f'action-{index}-done.json', 60 if has_knobs else 10, process)
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
                    events = labelled_actions(reports, [window], out_ep)[0]['events']
                    if events or time.monotonic() >= deadline:
                        break
                    time.sleep(.2)
                windows.append(window)
                write_json(job/'action-windows.json', windows)
                unchanged_endpoint = (control['kind'] == 'knob_range'
                                     and completed.get('starting_value') == completed.get('displayed_value')
                                     and 'displayed_value' in completed)
                if control.get('feedback') == 'captured_wire' and feedback_history:
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
                if control['kind'] == 'selector_cycle':
                    offset = control['observed_field_offset']
                    verify_wire_changes(reports, first_frame, {'wire': {'offset': offset}}, effect_type, expected_target[3], out_ep)
                    samples = [data for number, _, ep, data in reports if number > first_frame and ep == out_ep and data[0] == 0x70 and data[16] == 0xd5 and data[18] == effect_type and data[19] == expected_target[3]]
                    values = {data[offset] for data in samples}
                    if len(values) != 1:
                        raise RuntimeError('Selector click did not establish one captured position')
                    value = next(iter(values))
                    seen = selector_values.setdefault(control['id'], [])
                    if value in seen:
                        raise RuntimeError('Selector repeated a position before its full cycle')
                    seen.append(value)
                    if len(seen) == control['positions'] and value != selector_baselines[control['id']]:
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
                window['wire_events_observed'] = bool(events)
                window['endpoint_range_verified'] = False
                write_json(job/'action-windows.json', windows)
                if completed.get('status') != 'ok':
                    raise RuntimeError('Guest visual verification failed; stop for review')
                write_json(job/f'action-{index}-ack.json', {'status': 'ok'})
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
        'labelled_actions': labelled_actions(reports, windows, out_ep),
        'capture_summary': analyze_reports(reports)})
    write_json(job/'host-completed.json', {'status': 'ok', 'coverage': plan.get('coverage', {'status': 'partial; controls outside plan unknown'})})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared', type=Path, help='antelope-afx-tools directory')
    parser.add_argument('--preflight', type=Path, help='new local directory for a three-second passive capture')
    parser.add_argument('--wait-seconds', type=int, default=900, choices=range(1, 3601))
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
    print(f"Ready for one reviewed scan request; Orion on usbmon{location['bus']}. No HID controller opened.", flush=True)
    results = args.shared/'results'
    results.mkdir(exist_ok=True)
    def jobs():
        return set(results.glob('scan-*')) | set(results.glob('pilot-Instinct-*'))
    existing = jobs()
    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline:
        for job in sorted(jobs() - existing):
            if job.is_symlink() or not (job/'request.json').is_file():
                continue
            try:
                run_job(job, profile)
                print(f'Pilot finished: {job}', flush=True)
                return 0
            except (OSError, ValueError, RuntimeError, TimeoutError) as error:
                write_json(job/'host-error.json', {'error': str(error), 'stop': True})
                print(f'Pilot stopped: {error}. Evidence retained at {job}', file=sys.stderr, flush=True)
                return 1
        time.sleep(.2)
    print('No guest request arrived; nothing captured or changed.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
