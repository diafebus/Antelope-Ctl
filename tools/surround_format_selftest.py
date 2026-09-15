#!/usr/bin/env python3
"""Read and experimentally round-trip the Surround global format.

Read the safe global state without changing it::

    python3 tools/surround_format_selftest.py -p profiles/orion_studio_sc.json

Test the two normal format writes and restore the original state at the end::

    python3 tools/surround_format_selftest.py --write \
        --format 2.0 --format 2.1 --confirm-format-write

Probe layouts that are intentionally disabled in the WebUI::

    python3 tools/surround_format_selftest.py --write --format 3.0 \
        --confirm-experimental-format-write

Exercise Bass Management fader persistence across the two enabled formats
and restore the original global state at the end::

    python3 tools/surround_format_selftest.py --write --test-bass-faders \
        --confirm-bass-fader-write

Exercise the candidate Bass Management filter/link/solo fields and the
speaker-monitor delay/level/phase/bypass controls::

    python3 tools/surround_format_selftest.py --write --test-bass-controls \
        --test-speaker-controls --confirm-surround-control-write

The higher-layout candidates come from the vendor panel's Surround model and
are sent directly to the device. A valid readback matching the requested
channel order means the wire path accepted the layout; it does not by itself
prove that every licensed software feature is active. The fader test uses
distinct values for stable channel IDs 1=L, 3=R, and 4=LFE, compares both
directions using fresh category-0x1b readbacks, and restores the original
complete body. Candidate control tests change one declared bit or head field
at a time and restore the saved category-0x1a speaker records as well. Stop
the WebUI and any other HID owner before running this tool. Never use it as a
blind index sweep.
"""
import argparse
import hashlib
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from antelope import protocol as proto
from antelope.transport import HidTransport, find_hidraw


SURROUND_GLOBAL_CAT = 0x1B


def _contract(profile):
    frame = profile.get('frame', {}).get('surround_global_command', {})
    contract = frame.get('contract', {}) if isinstance(frame, dict) else {}
    if not contract:
        raise ValueError('profile has no surround global contract')
    return contract


def _formats(profile):
    formats = _contract(profile).get('formats', []) or []
    if not formats:
        raise ValueError('profile has no surround format definitions')
    return formats


def _format_by_name(profile, name):
    wanted = str(name).strip()
    for item in _formats(profile):
        if str(item.get('name', '')).strip() == wanted:
            return item
    raise ValueError(f'unknown surround format {name!r}')


def _format_order(profile, body, item):
    contract = _contract(profile)
    offset = proto._as_int(contract.get('channel_order_offset', 13))
    size = proto._as_int(contract.get('channel_order_size', 10))
    expected = proto.pack_surround_channel_order(item['channel_order'], size)
    return bytes(body[offset:offset + size]), expected


def _format_name(profile, body):
    contract = _contract(profile)
    payload_offset = proto._as_int(contract.get('readback_payload_offset', 18))
    flags_a = body[proto._as_int(contract.get('flags_a_offset', payload_offset))
                    - payload_offset]
    flags_b = body[proto._as_int(contract.get('flags_b_offset', payload_offset + 1))
                    - payload_offset]
    mask_a = proto._as_int(contract.get('format_flags_a_write_mask', 0x3F))
    mask_b = proto._as_int(contract.get('format_flags_b_write_mask', 0x1F))
    for item in _formats(profile):
        try:
            item_a = proto._as_int(item['flags_a'])
            item_b = proto._as_int(item['flags_b'])
            actual_order, expected_order = _format_order(profile, body, item)
        except (KeyError, TypeError, ValueError):
            continue
        if ((flags_a & mask_a) != (item_a & mask_a)
                or (flags_b & mask_b) != (item_b & mask_b)):
            continue
        if actual_order == expected_order:
            return str(item['name'])
    return 'unknown'


def _expected_flags(profile, body, item):
    contract = _contract(profile)
    payload_offset = proto._as_int(contract.get('readback_payload_offset', 18))
    flags_a_offset = (proto._as_int(contract.get('flags_a_offset', payload_offset))
                      - payload_offset)
    flags_b_offset = (proto._as_int(contract.get('flags_b_offset', payload_offset + 1))
                      - payload_offset)
    mask_a = proto._as_int(contract.get('format_flags_a_write_mask', 0x3F))
    mask_b = proto._as_int(contract.get('format_flags_b_write_mask', 0x1F))
    target_a = proto._as_int(item['flags_a'])
    target_b = proto._as_int(item['flags_b'])
    return (
        (body[flags_a_offset] & ~mask_a) | (target_a & mask_a),
        (body[flags_b_offset] & ~mask_b) | (target_b & mask_b),
    )


def _meaningful_body(profile, body):
    return bytes(body[:proto._as_int(_contract(profile).get('template_size', 151))])


def _diff_offsets(before, after):
    return [index for index, (left, right) in enumerate(zip(before, after))
            if left != right]


class Device:
    def __init__(self, profile, timeout, settle):
        self.profile = profile
        self.timeout = timeout
        self.settle = settle
        device = profile['device']
        vid = proto._as_int(device['vid'])
        pid = proto._as_int(device['pid'])
        node = find_hidraw(vid, pid)
        self.transport = HidTransport(
            node, proto._as_int(profile['transport']['report_size']))

    def read_global(self):
        request = proto.build_readback_query(
            self.profile, SURROUND_GLOBAL_CAT, 0)
        report = self.transport.query(
            request,
            lambda data: proto.is_readback_response(
                self.profile, data, SURROUND_GLOBAL_CAT, 0),
            timeout=self.timeout)
        if report is None:
            return None
        body = proto.readback_body(self.profile, report)
        return body, proto.parse_surround_global_record(self.profile, body)

    def read_speaker(self, speaker):
        category = proto.SURROUND_SPEAKER_EQ_READBACK_CATEGORY
        speaker = int(speaker)
        request = proto.build_readback_query(self.profile, category, speaker)
        report = self.transport.query(
            request,
            lambda data: proto.is_readback_response(
                self.profile, data, category, speaker),
            timeout=self.timeout)
        if report is None:
            return None
        body = proto.readback_body(self.profile, report)
        return body, proto.parse_surround_speaker_eq_record(
            self.profile, body)

    def write(self, packet):
        self.transport.write(packet)
        time.sleep(self.settle)


def _print_state(profile, label, result):
    body, state = result
    contract = _contract(profile)
    payload_offset = proto._as_int(contract.get('readback_payload_offset', 18))
    flags_a_offset = (proto._as_int(contract.get('flags_a_offset', payload_offset))
                      - payload_offset)
    flags_b_offset = (proto._as_int(contract.get('flags_b_offset', payload_offset + 1))
                      - payload_offset)
    order_offset = proto._as_int(contract.get('channel_order_offset', 13))
    order_size = proto._as_int(contract.get('channel_order_size', 10))
    print(
        f'{label}: format={_format_name(profile, body)} '
        f'flags={body[flags_a_offset]:#04x}/{body[flags_b_offset]:#04x} '
        f'order={body[order_offset:order_offset + order_size].hex()} '
        f'delay={state["global_delay_ms"]:.1f} ms '
        f'level={state["level_db"]:+.1f} dB '
        f'body_sha256={hashlib.sha256(_meaningful_body(profile, body)).hexdigest()[:12]}')


def _probe(dev, profile, current, item):
    name = str(item['name'])
    body, _ = current
    try:
        packet = proto.build_surround_global_format_command(
            profile, body, name,
            allow_experimental=not item.get('format_writable', False))
        expected_a, expected_b = _expected_flags(profile, body, item)
        _, expected_order = _format_order(profile, body, item)
    except (KeyError, TypeError, ValueError, proto.ConstraintError) as exc:
        print(f'[FAIL] {name}: cannot build probe: {exc}')
        return False, False

    contract = _contract(profile)
    order_offset = proto._as_int(contract.get('channel_order_offset', 13))
    order_size = proto._as_int(contract.get('channel_order_size', 10))
    print(f'probe {name}: send flags={expected_a:#04x}/{expected_b:#04x} '
          f'order={expected_order.hex()}')
    try:
        dev.write(packet)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'[FAIL] {name}: write raised {exc}')
        return False, True

    changed = dev.read_global()
    if changed is None:
        print(f'[FAIL] {name}: no category-0x1b readback after write')
        return False, True
    changed_body, _ = changed
    payload_offset = proto._as_int(contract.get('readback_payload_offset', 18))
    flags_a_offset = (proto._as_int(contract.get('flags_a_offset', payload_offset))
                      - payload_offset)
    flags_b_offset = (proto._as_int(contract.get('flags_b_offset', payload_offset + 1))
                      - payload_offset)
    actual_order = changed_body[order_offset:order_offset + order_size]
    accepted = (
        changed_body[flags_a_offset] == expected_a
        and changed_body[flags_b_offset] == expected_b
        and actual_order == expected_order
    )
    if accepted:
        print(f'[PASS] {name}: readback accepted the requested format')
    else:
        changed_offsets = _diff_offsets(
            _meaningful_body(profile, body), _meaningful_body(profile, changed_body))
        print(f'[FAIL] {name}: readback did not match the requested format '
              f'(reported {_format_name(profile, changed_body)}; '
              f'changed offsets {changed_offsets[:24]})')
    return accepted, False


def _bass_fader_raw_spec(profile):
    contract = _contract(profile)
    bass = contract.get('bass_management_write', {}) or {}
    fields = bass.get('fields', {}) or {}
    spec = fields.get('fader_db')
    if not isinstance(spec, dict):
        raise ValueError('profile has no Bass Management fader field')
    try:
        lo, hi = (_as_int(value) for value in spec['raw_range'])
        zero = float(spec.get('zero', 0))
        step = float(spec.get('step', 1))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('invalid Bass Management fader field') from exc
    if lo > hi or step <= 0:
        raise ValueError('invalid Bass Management fader range')
    return spec, lo, hi, zero, step


def _as_int(value):
    return proto._as_int(value)


def _fader_test_values(profile, count):
    spec, lo, hi, zero, _step = _bass_fader_raw_spec(profile)
    candidates = [round(zero - 100), round(zero - 50), round(zero + 50),
                  round(zero + 100), lo, hi]
    values = []
    for value in candidates:
        value = max(lo, min(hi, int(value)))
        if value not in values:
            values.append(value)
        if len(values) == count:
            return values
    raise ValueError(
        f'Bass Management fader range does not contain {count} distinct values')


def _fader_display_value(spec, raw):
    return proto._surround_bass_display_value(spec, raw)


def _state_fader_map(profile, body, state):
    name = _format_name(profile, body)
    item = _format_by_name(profile, name)
    order = [_as_int(value) for value in item.get('channel_order', [])]
    result = {}
    for slot, block in enumerate(state.get('bass_mgmt_channels', [])):
        channel_id = block.get('channel_id')
        if channel_id is None and slot < len(order):
            channel_id = order[slot]
        if channel_id is None:
            continue
        raw = block.get('fader_raw')
        if raw is None:
            raw = round(float(block.get('fader_db', 0)) * 10 + 600)
        result[int(channel_id)] = int(raw) & 0x1FFF
    return result


def _read_format(dev, profile, current, name):
    body, _state = current
    if _format_name(profile, body) == name:
        return current
    try:
        packet = proto.build_surround_global_format_command(
            profile, body, name)
        dev.write(packet)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError,
            proto.ConstraintError) as exc:
        print(f'[FAIL] format {name}: {exc}')
        return None
    result = dev.read_global()
    if result is None:
        print(f'[FAIL] format {name}: no category-0x1b readback')
        return None
    actual = _format_name(profile, result[0])
    if actual != name:
        print(f'[FAIL] format {name}: readback reported {actual}')
        return None
    return result


def _write_fader(dev, profile, current, slot, raw):
    body, _state = current
    spec, _lo, _hi, _zero, _step = _bass_fader_raw_spec(profile)
    value = _fader_display_value(spec, raw)
    try:
        packet = proto.build_surround_global_bass_command(
            profile, body, channel=slot, field='fader_db', value=value,
            allow_experimental=True)
        dev.write(packet)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError,
            proto.ConstraintError) as exc:
        print(f'[FAIL] fader slot {slot}: {exc}')
        return None
    result = dev.read_global()
    if result is None:
        print(f'[FAIL] fader slot {slot}: no category-0x1b readback')
    return result


def _compare_faders(profile, label, body, state, expected):
    actual = _state_fader_map(profile, body, state)
    failures = []
    for channel_id, raw in expected.items():
        if actual.get(channel_id) != (int(raw) & 0x1FFF):
            failures.append(
                f'{channel_id}: expected {int(raw) & 0x1FFF}, '
                f'got {actual.get(channel_id)!r}')
    if failures:
        print(f'[FAIL] {label}: fader readback mismatch ({"; ".join(failures)})')
        return False
    print(f'[PASS] {label}: fader readback by channel ID '
          + ', '.join(f'{channel_id}={raw}'
                      for channel_id, raw in sorted(expected.items())))
    return True


def _test_bass_faders(dev, profile, original):
    """Round-trip distinct faders through 2.0 -> 2.1 -> 2.0 -> 2.1."""
    if _format_name(profile, original[0]) not in {'2.0', '2.1'}:
        print('[FAIL] Bass fader test requires an original 2.0 or 2.1 state')
        return False
    values20 = _fader_test_values(profile, 2)
    values21 = _fader_test_values(profile, 3)
    print('Bass fader test values: '
          f'2.0 L/R={values20[0]}/{values20[1]}, '
          f'2.1 L/R/LFE={values21[0]}/{values21[1]}/{values21[2]} raw')

    current = _read_format(dev, profile, original, '2.0')
    if current is None:
        return False
    for slot, raw in enumerate(values20):
        current = _write_fader(dev, profile, current, slot, raw)
        if current is None:
            return False
    body20, state20 = current
    if not _compare_faders(profile, '2.0 baseline', body20, state20,
                           {1: values20[0], 3: values20[1]}):
        return False

    current = _read_format(dev, profile, current, '2.1')
    if current is None:
        return False
    body21, state21 = current
    if not _compare_faders(profile, '2.0 -> 2.1', body21, state21,
                           {1: values20[0], 3: values20[1]}):
        return False

    for slot, raw in enumerate(values21):
        current = _write_fader(dev, profile, current, slot, raw)
        if current is None:
            return False
    body21, state21 = current
    if not _compare_faders(profile, '2.1 baseline', body21, state21,
                           {1: values21[0], 3: values21[1], 4: values21[2]}):
        return False

    current = _read_format(dev, profile, current, '2.0')
    if current is None:
        return False
    body20, state20 = current
    if not _compare_faders(profile, '2.1 -> 2.0', body20, state20,
                           {1: values21[0], 3: values21[1]}):
        return False

    current = _read_format(dev, profile, current, '2.1')
    if current is None:
        return False
    body21, state21 = current
    return _compare_faders(profile, '2.0 -> 2.1 final', body21, state21,
                           {1: values21[0], 3: values21[1], 4: values21[2]})


def _bass_candidate_fields(profile):
    fields = (_contract(profile).get('bass_management_write', {}) or {}).get(
        'fields', {}) or {}
    return [
        (str(name), spec) for name, spec in fields.items()
        if isinstance(spec, dict) and spec.get('writable', True)
        and str(spec.get('kind', '')).strip().lower() in {
            'filter_type', 'link'}
    ]


def _bass_candidate_value(spec, raw):
    if spec.get('boolean'):
        return not bool(raw)
    display_values = spec.get('display_values') or []
    raw_values = spec.get('raw_values') or []
    for index, candidate in enumerate(raw_values):
        if _as_int(candidate) == int(raw) and index < len(display_values):
            if len(display_values) < 2:
                break
            return display_values[(index + 1) % len(display_values)]
    if display_values:
        return display_values[0]
    raise ValueError('candidate Bass Management field has no alternate value')


def _bass_candidate_raw(profile, body, field, state):
    fields = (_contract(profile).get('bass_management_write', {}) or {}).get(
        'fields', {}) or {}
    spec = fields[field]
    kind = str(spec.get('kind', '')).strip().lower()
    if kind == 'filter_type':
        side = str(spec.get('side', field)).strip().lower()
        return _as_int((state.get('bass_mgmt_filter_type_raw', {}) or {}).get(
            side, 0))
    if kind == 'link':
        return _as_int((state.get('bass_mgmt_link_raw', {}) or {}).get(
            field, 0))
    raise ValueError(f'unsupported Bass Management candidate {field}')


def _write_bass_candidate(dev, profile, current, slot, field, value):
    body, _state = current
    try:
        packet = proto.build_surround_global_bass_command(
            profile, body, channel=slot, field=field, value=value,
            allow_experimental=True)
        dev.write(packet)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError,
            proto.ConstraintError) as exc:
        print(f'[FAIL] Bass Management {field}: {exc}')
        return None
    result = dev.read_global()
    if result is None:
        print(f'[FAIL] Bass Management {field}: no category-0x1b readback')
    return result


def _test_bass_controls_for_format(dev, profile, current):
    body, state = current
    format_name = _format_name(profile, body)
    passed = True
    for field, spec in _bass_candidate_fields(profile):
        try:
            raw = _bass_candidate_raw(profile, body, field, state)
            value = _bass_candidate_value(spec, raw)
        except (KeyError, TypeError, ValueError) as exc:
            print(f'[FAIL] {format_name} {field}: cannot select candidate: {exc}')
            passed = False
            continue
        print(f'probe {format_name} {field}: raw {raw} -> {value!r}')
        changed = _write_bass_candidate(dev, profile, current, 0, field, value)
        if changed is None:
            return None, False
        changed_body, changed_state = changed
        field_spec = ((_contract(profile).get('bass_management_write', {})
                       or {}).get('fields', {}) or {})[field]
        try:
            actual = _bass_candidate_raw(
                profile, changed_body, field, changed_state)
            expected = proto._surround_bass_raw_value(field_spec, value)
        except (KeyError, TypeError, ValueError):
            actual = None
            expected = None
        if expected is None or actual != expected:
            print(f'[FAIL] {format_name} {field}: readback raw {actual!r}, '
                  f'expected {expected!r}')
            passed = False
        else:
            print(f'[PASS] {format_name} {field}: readback raw {actual}')
        current = changed
        body, state = current

    active_slots = len(_format_by_name(profile, format_name).get(
        'channel_order', []))
    fields = ((_contract(profile).get('bass_management_write', {}) or {}).get(
        'fields', {}) or {})
    solo_spec = fields.get('fader_solo')
    if isinstance(solo_spec, dict) and solo_spec.get('writable', True):
        for slot in range(active_slots):
            blocks = state.get('bass_mgmt_channels', [])
            block = blocks[slot] if slot < len(blocks) else {}
            raw = _as_int(block.get('fader_solo_raw',
                                      1 if block.get('fader_solo') else 0))
            value = _bass_candidate_value(solo_spec, raw)
            print(f'probe {format_name} fader_solo slot {slot}: '
                  f'raw {raw} -> {value!r}')
            changed = _write_bass_candidate(
                dev, profile, current, slot, 'fader_solo', value)
            if changed is None:
                return None, False
            changed_body, changed_state = changed
            changed_blocks = changed_state.get('bass_mgmt_channels', [])
            changed_block = (changed_blocks[slot]
                             if slot < len(changed_blocks) else {})
            actual = _as_int(changed_block.get(
                'fader_solo_raw',
                1 if changed_block.get('fader_solo') else 0))
            expected = 1 if bool(value) else 0
            if actual != expected:
                print(f'[FAIL] {format_name} fader_solo slot {slot}: '
                      f'readback raw {actual}, expected {expected}')
                passed = False
            else:
                print(f'[PASS] {format_name} fader_solo slot {slot}: '
                      f'readback raw {actual}')
            current = changed
            body, state = current
    return current, passed


def _test_bass_controls(dev, profile, original):
    """Probe filter/link/solo candidates in both writable stereo layouts."""
    if _format_name(profile, original[0]) not in {'2.0', '2.1'}:
        print('[FAIL] Bass Management control test requires an original '
              '2.0 or 2.1 state')
        return False
    current = _read_format(dev, profile, original, '2.0')
    if current is None:
        return False
    current, passed20 = _test_bass_controls_for_format(
        dev, profile, current)
    if current is None:
        return False
    current = _read_format(dev, profile, current, '2.1')
    if current is None:
        return False
    current, passed21 = _test_bass_controls_for_format(
        dev, profile, current)
    return current is not None and passed20 and passed21


def _speaker_head_test_value(spec, raw):
    if spec.get('boolean'):
        return not bool(raw)
    lo, hi = (_as_int(value) for value in spec['raw_range'])
    current = _as_int(raw)
    for delta in (50, -50, 10, -10, 1, -1):
        candidate = current + delta
        if lo <= candidate <= hi and candidate != current:
            return proto._surround_speaker_head_display(spec, candidate)
    raise ValueError('speaker head range has no distinct test value')


def _write_speaker_head_candidate(dev, profile, current, speaker, field,
                                  value):
    body, _state = current
    try:
        packet = proto.build_surround_speaker_head_command(
            profile, body, speaker, field, value, allow_experimental=True)
        dev.write(packet)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError,
            proto.ConstraintError) as exc:
        print(f'[FAIL] speaker {speaker} {field}: {exc}')
        return None
    result = dev.read_speaker(speaker)
    if result is None:
        print(f'[FAIL] speaker {speaker} {field}: no category-0x1a readback')
    return result


def _test_speaker_controls(dev, profile, original):
    """Probe L/R speaker head controls and the global per-speaker bypass bit."""
    original_name = _format_name(profile, original[0])
    if original_name not in {'2.0', '2.1'}:
        print('[FAIL] speaker control test requires an original 2.0 or 2.1 state')
        return False
    speaker_contract = profile.get('runtime_contracts', {}).get(
        'surround_speaker_eq', {}) or {}
    head_specs = speaker_contract.get('head_fields', {}) or {}
    head_write = speaker_contract.get('write_contract', {}) or {}
    declared_head_fields = set(head_write.get('head_fields', []) or [])
    writable = [name for name in ('delay_ms', 'level_db', 'phase_invert')
                if isinstance(head_specs.get(name), dict)
                and head_specs[name].get('writable')
                and name in declared_head_fields]
    passed = True
    for speaker in (0, 1):
        current = dev.read_speaker(speaker)
        if current is None:
            print(f'[FAIL] speaker {speaker}: no category-0x1a baseline readback')
            return False
        for field in writable:
            state = current[1]
            raw = state.get('head', {}).get(f'{field}_raw')
            if raw is None:
                print(f'[FAIL] speaker {speaker} {field}: no decoded baseline')
                passed = False
                continue
            try:
                value = _speaker_head_test_value(head_specs[field], raw)
                expected = proto._surround_speaker_head_raw_value(
                    head_specs[field], value)
            except (KeyError, TypeError, ValueError) as exc:
                print(f'[FAIL] speaker {speaker} {field}: {exc}')
                passed = False
                continue
            print(f'probe speaker {speaker} {field}: raw {raw} -> {value!r}')
            changed = _write_speaker_head_candidate(
                dev, profile, current, speaker, field, value)
            if changed is None:
                return False
            actual = changed[1].get('head', {}).get(f'{field}_raw')
            if actual != expected:
                print(f'[FAIL] speaker {speaker} {field}: readback raw '
                      f'{actual!r}, expected {expected!r}')
                passed = False
            else:
                print(f'[PASS] speaker {speaker} {field}: readback raw {actual}')
            current = changed

    global_current = dev.read_global()
    if global_current is None:
        print('[FAIL] speaker bypass: no category-0x1b baseline readback')
        return False
    mask_contract = _contract(profile).get('speaker_mask_write', {}) or {}
    fields = mask_contract.get('fields', {}) or {}
    spec = fields.get('bypass')
    if not isinstance(spec, dict) or not spec.get('writable', True):
        print('[FAIL] speaker bypass: no writable profile field')
        return False
    for speaker in (0, 1):
        state = global_current[1]
        mask = state.get('bypass_mask')
        if mask is None:
            print(f'[FAIL] speaker {speaker} bypass: no mask readback')
            passed = False
            continue
        current_value = not bool(int(mask) & (1 << speaker))
        value = not current_value
        print(f'probe speaker {speaker} bypass: {current_value!r} -> {value!r}')
        try:
            packet = proto.build_surround_global_speaker_mask_command(
                profile, global_current[0], speaker, 'bypass', value,
                allow_experimental=True)
            dev.write(packet)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError,
                proto.ConstraintError) as exc:
            print(f'[FAIL] speaker {speaker} bypass: {exc}')
            return False
        changed = dev.read_global()
        if changed is None:
            print(f'[FAIL] speaker {speaker} bypass: no readback')
            return False
        actual = not bool(int(changed[1].get('bypass_mask', 0))
                          & (1 << speaker))
        if actual != value:
            print(f'[FAIL] speaker {speaker} bypass: readback {actual!r}, '
                  f'expected {value!r}')
            passed = False
        else:
            print(f'[PASS] speaker {speaker} bypass: readback {actual!r}')
        global_current = changed
    return passed


def _restore_speakers(dev, profile, originals):
    passed = True
    for speaker, original in sorted(originals.items()):
        body, _state = original
        try:
            packet = proto.build_surround_speaker_eq_command(
                profile, body, speaker=speaker, band=0, changes={},
                allow_experimental=True)
            dev.write(packet)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError,
                proto.ConstraintError) as exc:
            print(f'[FAIL] restore speaker {speaker}: {exc}')
            passed = False
            continue
        result = dev.read_speaker(speaker)
        if result is None:
            print(f'[FAIL] restore speaker {speaker}: no category-0x1a readback')
            passed = False
            continue
        restored_body, _ = result
        exact = bytes(restored_body[:len(body)]) == bytes(body)
        if exact:
            print(f'[PASS] restored original speaker {speaker} record')
        else:
            print(f'[FAIL] restore speaker {speaker}: readback differs at '
                  f'offsets {_diff_offsets(body, restored_body)[:24]}')
            passed = False
    return passed


def _restore(dev, profile, original):
    body, _ = original
    original_name = _format_name(profile, body)
    if original_name == 'unknown':
        print('[FAIL] restore: original format is not recognized')
        return False
    try:
        packet = proto.build_surround_global_format_command(
            profile, body, original_name, allow_experimental=True)
        dev.write(packet)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError,
            proto.ConstraintError) as exc:
        print(f'[FAIL] restore {original_name}: {exc}')
        return False
    result = dev.read_global()
    if result is None:
        print(f'[FAIL] restore {original_name}: no category-0x1b readback')
        return False
    restored_body, _ = result
    exact = _meaningful_body(profile, restored_body) == _meaningful_body(profile, body)
    if exact:
        print(f'[PASS] restored original {original_name} global state')
    else:
        print(f'[FAIL] restore {original_name}: readback differs at offsets '
              f'{_diff_offsets(_meaningful_body(profile, body), _meaningful_body(profile, restored_body))[:24]}')
    return exact


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-p', '--profile', default='orion',
                    help='profile path, filename, or short name (default: orion)')
    ap.add_argument('--format', dest='formats', action='append',
                    help='format to probe; repeat for a sequence')
    ap.add_argument('--all-formats', action='store_true',
                    help='probe every format in the profile in sequence')
    ap.add_argument('--write', action='store_true',
                    help='perform format writes and restore the original state')
    ap.add_argument('--confirm-format-write', action='store_true',
                    help='acknowledge the normal 2.0/2.1 format write test')
    ap.add_argument('--confirm-experimental-format-write', action='store_true',
                    help='acknowledge direct writes for layouts disabled in the WebUI')
    ap.add_argument('--test-bass-faders', action='store_true',
                    help='round-trip Bass Management faders through 2.0 and 2.1')
    ap.add_argument('--test-bass-controls', action='store_true',
                    help='probe Bass Management filter/link/solo candidates')
    ap.add_argument('--test-speaker-controls', action='store_true',
                    help='probe speaker delay/level/phase/bypass controls')
    ap.add_argument('--confirm-bass-fader-write', action='store_true',
                    help='acknowledge the Bass Management fader write test')
    ap.add_argument('--confirm-bass-control-write', action='store_true',
                    help='acknowledge experimental Bass Management control probes')
    ap.add_argument('--confirm-speaker-control-write', action='store_true',
                    help='acknowledge experimental speaker-monitor control probes')
    ap.add_argument('--confirm-surround-control-write', action='store_true',
                    help='acknowledge all experimental Bass Management and speaker-control probes')
    ap.add_argument('--timeout', type=float, default=2.0)
    ap.add_argument('--settle', type=float, default=0.5,
                    help='seconds to wait after each write (default 0.5)')
    args = ap.parse_args()

    control_tests = (args.test_bass_faders or args.test_bass_controls
                     or args.test_speaker_controls)
    if args.all_formats and args.formats:
        ap.error('--all-formats cannot be combined with --format')
    if control_tests and (args.all_formats or args.formats):
        ap.error('control tests cannot be combined with --format or --all-formats')
    if not args.write and (args.all_formats or args.formats or control_tests):
        ap.error('--format, --all-formats, and control tests require --write')
    if args.write and not (args.all_formats or args.formats or control_tests):
        ap.error('--write requires --format, --all-formats, or a control test')
    if args.write and args.all_formats and not args.confirm_experimental_format_write:
        ap.error('--all-formats requires --confirm-experimental-format-write')
    if args.test_bass_faders and not (
            args.confirm_bass_fader_write or args.confirm_surround_control_write):
        ap.error('--test-bass-faders requires --confirm-bass-fader-write')
    if args.test_bass_controls and not (
            args.confirm_bass_control_write or args.confirm_surround_control_write):
        ap.error('--test-bass-controls requires --confirm-bass-control-write')
    if args.test_speaker_controls and not (
            args.confirm_speaker_control_write or args.confirm_surround_control_write):
        ap.error('--test-speaker-controls requires --confirm-speaker-control-write')

    from antelope.cli import _resolve_profile_path
    try:
        profile = proto.load_profile(_resolve_profile_path(args.profile))
        selected = ([] if control_tests else
                    (_formats(profile) if args.all_formats else
                     [_format_by_name(profile, name) for name in args.formats or []]))
        needs_experimental = any(
            not item.get('format_writable', False) for item in selected)
        if args.write and needs_experimental and not args.confirm_experimental_format_write:
            ap.error('a selected layout is experimental; add '
                     '--confirm-experimental-format-write')
        if args.write and not needs_experimental and not (
                args.confirm_format_write or args.confirm_experimental_format_write):
            ap.error('normal format writes require --confirm-format-write')

        dev = Device(profile, args.timeout, args.settle)
        original = dev.read_global()
        if original is None:
            print('ERROR: no category-0x1b index-0 readback', file=sys.stderr)
            return 2
        _print_state(profile, 'read', original)
        speaker_originals = {}
        if args.test_speaker_controls:
            for speaker in (0, 1):
                result = dev.read_speaker(speaker)
                if result is None:
                    print(f'ERROR: no category-0x1a speaker {speaker} readback',
                          file=sys.stderr)
                    return 2
                speaker_originals[speaker] = result
        if not args.write:
            return 0

        passed = True
        fatal = False
        if control_tests:
            try:
                if args.test_bass_faders or args.test_bass_controls:
                    passed = _test_bass_faders(dev, profile, original) and passed
                if args.test_bass_controls:
                    passed = _test_bass_controls(dev, profile, original) and passed
                if args.test_speaker_controls:
                    passed = _test_speaker_controls(dev, profile, original) and passed
            finally:
                if speaker_originals and not _restore_speakers(
                        dev, profile, speaker_originals):
                    passed = False
                if not _restore(dev, profile, original):
                    passed = False
        else:
            try:
                for item in selected:
                    current = dev.read_global()
                    if current is None:
                        print(f'[FAIL] {item["name"]}: no baseline readback before probe')
                        passed = False
                        fatal = True
                        break
                    ok, no_response = _probe(dev, profile, current, item)
                    passed = passed and ok
                    if no_response:
                        fatal = True
                        break
            finally:
                if not _restore(dev, profile, original):
                    passed = False
        if fatal:
            print('Stopped after a transport/readback failure; no later formats were sent.')
        return 0 if passed else 1
    except (OSError, ValueError, proto.ConstraintError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
