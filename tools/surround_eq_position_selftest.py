#!/usr/bin/env python3
"""Read and experimentally round-trip Surround EQ PRE/POST position.

Read the current global Surround state without changing it::

    python3 tools/surround_eq_position_selftest.py

Probe the opposite position, verify the category-0x1b readback, and restore
the complete original state::

    python3 tools/surround_eq_position_selftest.py --write \
        --confirm-experimental-write

Use ``--position pre`` or ``--position post`` to choose the probe target.
The position is one bit in the complete 0xab/0xeb global frame. Stop the
WebUI and any other HID owner before running this tool. It only queries the
profile-authorized category-0x1b index 0 and never probes a blind index.
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


SURROUND_GLOBAL_CAT = proto.SURROUND_GLOBAL_READBACK_CATEGORY


def _contract(profile):
    frame = profile.get('frame', {}).get('surround_global_command', {})
    contract = frame.get('contract', {}) if isinstance(frame, dict) else {}
    if not contract:
        raise ValueError('profile has no surround global contract')
    return contract


def _position_contract(profile):
    contract = _contract(profile)
    value = contract.get('eq_position_write', {}) or {}
    if not isinstance(value, dict) or not value:
        raise ValueError('profile has no Surround EQ-position write contract')
    return value


def _meaningful_body(profile, body):
    return bytes(body[:proto._as_int(_contract(profile).get(
        'template_size', 151))])


def _position(profile, body):
    return 'post' if proto.parse_surround_global_record(
        profile, body)['eq_post'] else 'pre'


def _position_field(profile):
    spec = _position_contract(profile)
    try:
        offset = proto._as_int(spec.get('readback_offset', 0))
        width = proto._as_int(spec.get('width', 1))
        mask = proto._as_int(spec['mask'])
        shift = proto._as_int(spec.get('shift', 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('invalid Surround EQ-position field contract') from exc
    return offset, width, mask, shift


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
    meaningful = _meaningful_body(profile, body)
    print(
        f'{label}: position={"POST" if state["eq_post"] else "PRE"} '
        f'format flags={body[0]:#04x}/{body[1]:#04x} '
        f'body_sha256={hashlib.sha256(meaningful).hexdigest()[:12]}')


def _probe(dev, profile, original, target):
    body, state = original
    current = 'post' if state['eq_post'] else 'pre'
    if target is None:
        target = 'pre' if current == 'post' else 'post'
    if target == current:
        print(f'[FAIL] requested position {target.upper()} is already active; '
              'choose the other position')
        return False

    try:
        offset, width, mask, shift = _position_field(profile)
        probe_packet = proto.build_surround_global_eq_position_command(
            profile, body, target, allow_experimental=True)
        restore_packet = proto.build_surround_global_eq_position_command(
            profile, body, current, allow_experimental=True)
    except (KeyError, TypeError, ValueError, proto.ConstraintError) as exc:
        print(f'[FAIL] cannot build EQ-position probe: {exc}')
        return False

    original_meaningful = _meaningful_body(profile, body)
    expected = bytearray(original_meaningful)
    raw = proto._as_int(_position_contract(profile)['values'][target])
    current_field = int.from_bytes(
        expected[offset:offset + width], 'little', signed=False)
    encoded = (current_field & ~mask) | ((raw << shift) & mask)
    expected[offset:offset + width] = encoded.to_bytes(
        width, byteorder='little', signed=False)
    probe_ok = False
    preserved_ok = False
    restore_ok = False
    print(f'probe EQ position: {current.upper()} -> {target.upper()}')
    try:
        dev.write(probe_packet)
        changed = dev.read_global()
        if changed is None:
            print('[FAIL] probe write: no category-0x1b readback')
        else:
            changed_body, changed_state = changed
            changed_meaningful = _meaningful_body(profile, changed_body)
            probe_ok = _position(profile, changed_body) == target
            preserved_ok = changed_meaningful == bytes(expected)
            print(f'[{"PASS" if probe_ok else "FAIL"}] probe readback: '
                  f'got {"POST" if changed_state["eq_post"] else "PRE"}, '
                  f'wanted {target.upper()}')
            print(f'[{"PASS" if preserved_ok else "FAIL"}] probe changed only '
                  f'the declared field'
                  + ('' if preserved_ok else
                     f' (other offsets changed: {_diff_offsets(bytes(expected), changed_meaningful)[:24]})'))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'[FAIL] probe write/read raised {exc}')
    finally:
        try:
            dev.write(restore_packet)
            restored = dev.read_global()
            if restored is not None:
                restored_body, restored_state = restored
                restore_ok = (
                    _meaningful_body(profile, restored_body) == original_meaningful
                    and _position(profile, restored_body) == current)
                print(f'[{"PASS" if restore_ok else "FAIL"}] restored original '
                      f'{current.upper()} global state')
            else:
                print('[FAIL] restore: no category-0x1b readback')
        except Exception as exc:
            print(f'[FAIL] restore raised {exc}')

    return probe_ok and preserved_ok and restore_ok


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-p', '--profile', default='orion',
                    help='profile path, filename, or short name (default: orion)')
    ap.add_argument('--write', action='store_true',
                    help='perform one position write and restore round trip')
    ap.add_argument('--position', choices=('pre', 'post'),
                    help='probe target; defaults to the opposite of the current position')
    ap.add_argument('--confirm-experimental-write', action='store_true',
                    help='acknowledge that the EQ-position transition needs live confirmation')
    ap.add_argument('--timeout', type=float, default=2.0)
    ap.add_argument('--settle', type=float, default=0.5,
                    help='seconds to wait after each write (default 0.5)')
    args = ap.parse_args()

    if not args.write and (args.position is not None
                           or args.confirm_experimental_write):
        ap.error('--position and --confirm-experimental-write require --write')
    if args.write and not args.confirm_experimental_write:
        ap.error('--write requires --confirm-experimental-write')

    from antelope.cli import _resolve_profile_path
    try:
        profile = proto.load_profile(_resolve_profile_path(args.profile))
        _position_contract(profile)
        dev = Device(profile, args.timeout, args.settle)
        original = dev.read_global()
        if original is None:
            print('ERROR: no category-0x1b index-0 readback', file=sys.stderr)
            return 2
        _print_state(profile, 'read', original)
        if not args.write:
            return 0
        return 0 if _probe(dev, profile, original, args.position) else 1
    except (OSError, ValueError, proto.ConstraintError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
