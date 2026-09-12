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

The higher-layout candidates come from the vendor panel's Surround model and
are sent directly to the device. A valid readback matching the requested
channel order means the wire path accepted the layout; it does not by itself
prove that every licensed software feature is active. Stop the WebUI and any
other HID owner before running this tool. Never use it as a blind index sweep.
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
    ap.add_argument('--timeout', type=float, default=2.0)
    ap.add_argument('--settle', type=float, default=0.5,
                    help='seconds to wait after each write (default 0.5)')
    args = ap.parse_args()

    if args.all_formats and args.formats:
        ap.error('--all-formats cannot be combined with --format')
    if not args.write and (args.all_formats or args.formats):
        ap.error('--format and --all-formats require --write')
    if args.write and not (args.all_formats or args.formats):
        ap.error('--write requires --format or --all-formats')
    if args.write and args.all_formats and not args.confirm_experimental_format_write:
        ap.error('--all-formats requires --confirm-experimental-format-write')

    from antelope.cli import _resolve_profile_path
    try:
        profile = proto.load_profile(_resolve_profile_path(args.profile))
        selected = (_formats(profile) if args.all_formats else
                    [_format_by_name(profile, name) for name in args.formats or []])
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
        if not args.write:
            return 0

        passed = True
        fatal = False
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
