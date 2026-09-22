#!/usr/bin/env python3
"""Capture one bounded Orion link transition and restore the declared state.

This is intentionally a *capture assistant*, not another general link
controller.  Category 0x0b has five safe, profile-declared link tables, but
their correlation with SET_LINK still needs live evidence.  The script reads
all five tables before and after one requested transition, writes a local JSON
record, and restores the state the operator explicitly declared.

Read-only inventory:
    python3 tools/link_transition_capture.py

One S/PDIF transition (the Launcher must show it currently off):
    python3 tools/link_transition_capture.py --family spdif --pair 0 \
        --from-state off --to-state on --write --confirm-transition

Physical and ADAT links share SET_LINK space 0 on Orion.  Their write path
therefore needs the extra --confirm-shared-space acknowledgement and records
both tables; use it only when the corresponding pair is known to have the
declared starting state in both domains.

Only one process may own the HID node.  Stop the WebUI, CLI, and Launcher
before running this tool.  The default output path is ignored by Git because
it can contain device-specific observations.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from antelope import protocol as proto
from antelope.transport import HidTransport, find_hidraw


LINK_CATEGORY = 0x0B
DEFAULT_OUTPUT = Path(__file__).with_name('link_transition_out.json')


def _as_int(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def link_tables(profile):
    """Return the profile-declared category-0x0b tables keyed by their name."""
    tables = {}
    layouts = profile.get('frame', {}).get('readback', {}).get('record_layouts', [])
    for layout in layouts:
        if (layout.get('kind') == 'link_table'
                and _as_int(layout.get('category', -1)) == LINK_CATEGORY
                and 'index' in layout and layout.get('name')):
            tables[layout['name']] = {
                'index': _as_int(layout['index']),
                'record_count': _as_int(layout['record_count']),
            }
    return tables


def family_spec(profile, family):
    """Resolve a logical family through profile declarations, never defaults."""
    tables = link_tables(profile)
    if family == 'physical':
        return {'table': 'preamps', 'space': 0,
                'pairs': _as_int(profile['channels']['link_pairs']['count']),
                'shared_space': True}
    if family == 'adat':
        return {'table': 'adats', 'space': 0,
                'pairs': _as_int(profile['adat']['link_pairs']['count']),
                'shared_space': True}
    if family == 'spdif':
        return {'table': 'spdifs', 'space': 1,
                'pairs': _as_int(profile['spdif']['link_pairs']['count']),
                'shared_space': False}
    raise ValueError(f'unsupported link family {family!r}')


def validate_target(profile, family, pair):
    """Return a verified target or reject absent/profile-inconsistent metadata."""
    spec = family_spec(profile, family)
    table = link_tables(profile).get(spec['table'])
    if table is None:
        raise ValueError(f'profile has no 0x0b table for {family} links')
    if table['record_count'] != spec['pairs']:
        raise ValueError(
            f'{family} pair count ({spec["pairs"]}) disagrees with its '
            f'0x0b table ({table["record_count"]}); refusing to write')
    if not 0 <= pair < spec['pairs']:
        raise ValueError(
            f'{family} pair {pair} is outside the profile-confirmed '
            f'0..{spec["pairs"] - 1} range')
    return spec, table


class Device:
    def __init__(self, profile, timeout):
        device = profile['device']
        vid = _as_int(device['vid'])
        pid = _as_int(device['pid'])
        self.profile = profile
        self.timeout = timeout
        self.node = find_hidraw(vid, pid)
        self.transport = HidTransport(self.node, _as_int(profile['transport']['report_size']))

    def read_table(self, index):
        request = proto.build_readback_query(self.profile, LINK_CATEGORY, index)
        data = self.transport.query(
            request,
            lambda report: proto.is_readback_response(
                self.profile, report, LINK_CATEGORY, index),
            timeout=self.timeout,
        )
        if data is None:
            raise RuntimeError(f'no response for safe link table 0x0b/{index}')
        body = proto.readback_body(self.profile, data)
        return proto.parse_link_table(self.profile, body, LINK_CATEGORY, index)

    def snapshot(self):
        """Read only the five safe, profile-declared 0x0b table indices."""
        out = {}
        for name, table in sorted(link_tables(self.profile).items(),
                                  key=lambda item: item[1]['index']):
            records = self.read_table(table['index'])
            out[name] = [record['linked'] for record in records]
        return out

    def set_link(self, pair, enabled, space, settle):
        self.transport.write(proto.build_link_command(
            self.profile, pair, enabled, space=space))
        time.sleep(settle)


def changed_tables(before, after):
    """A compact, JSON-friendly table/slot diff for a capture record."""
    result = {}
    for name in sorted(set(before) | set(after)):
        left, right = before.get(name), after.get(name)
        if left != right:
            slots = []
            for index, (old, new) in enumerate(zip(left or [], right or [])):
                if old != new:
                    slots.append({'pair': index, 'before': old, 'after': new})
            result[name] = slots or {'before': left, 'after': right}
    return result


def output_record(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    print(f'capture record: {path}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-p', '--profile', default='profiles/orion_studio_sc.json',
                        help='profile JSON path (default: Orion Studio SC)')
    parser.add_argument('--family', choices=('physical', 'adat', 'spdif'),
                        help='link family for a controlled transition')
    parser.add_argument('--pair', type=int, help='zero-based pair index')
    parser.add_argument('--from-state', choices=('on', 'off'),
                        help='state visibly present before the test; used for restoration')
    parser.add_argument('--to-state', choices=('on', 'off'),
                        help='one state to write before restoring --from-state')
    parser.add_argument('--write', action='store_true',
                        help='perform the one requested SET_LINK transition')
    parser.add_argument('--confirm-transition', action='store_true',
                        help='acknowledge that this changes then restores the named link')
    parser.add_argument('--confirm-shared-space', action='store_true',
                        help='acknowledge physical/ADAT share wire space 0 on Orion')
    parser.add_argument('--timeout', type=float, default=1.0,
                        help='readback response timeout in seconds (default: 1.0)')
    parser.add_argument('--settle', type=float, default=0.35,
                        help='wait after a SET_LINK frame in seconds (default: 0.35)')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT),
                        help='local JSON capture record (default: tools/link_transition_out.json)')
    args = parser.parse_args(argv)

    if args.timeout <= 0 or args.settle < 0:
        parser.error('--timeout must be positive and --settle must not be negative')
    if args.write:
        missing = [name for name in ('family', 'pair', 'from_state', 'to_state')
                   if getattr(args, name) is None]
        if missing:
            parser.error('--write requires --family, --pair, --from-state, and --to-state')
        if not args.confirm_transition:
            parser.error('--write requires --confirm-transition')
        if args.from_state == args.to_state:
            parser.error('--from-state and --to-state must differ')
    elif any(value is not None for value in
             (args.family, args.pair, args.from_state, args.to_state)):
        parser.error('transition options require --write; read-only mode inventories all safe tables')

    profile = proto.load_profile(args.profile)
    if args.write:
        spec, table = validate_target(profile, args.family, args.pair)
        if spec['shared_space'] and not args.confirm_shared_space:
            parser.error(
                'physical and ADAT share SET_LINK space 0; --write for either needs '
                '--confirm-shared-space after checking both domains have --from-state')

    device = Device(profile, args.timeout)
    print(f'Using {device.node}; reading only safe, profile-declared 0x0b link tables.')
    before = device.snapshot()
    if not args.write:
        print(json.dumps(before, indent=2, sort_keys=True))
        return 0

    prior = args.from_state == 'on'
    requested = args.to_state == 'on'
    target_before = before[spec['table']][args.pair]
    print(f'operator-declared {args.family} pair {args.pair}: {args.from_state}; '
          f'0x0b/{table["index"]} reports raw value {target_before}.')
    record = {
        'format': 'antelope-ctl link transition capture v1',
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'profile': profile.get('device', {}).get('name'),
        'family': args.family,
        'pair': args.pair,
        'wire_space': spec['space'],
        'operator_declared_before': args.from_state,
        'requested_state': args.to_state,
        'before': before,
    }
    wrote = False
    exit_code = 0
    try:
        device.set_link(args.pair, requested, spec['space'], args.settle)
        wrote = True
        after = device.snapshot()
        record['after_transition'] = after
        record['transition_diff'] = changed_tables(before, after)
        print('transition diff:')
        print(json.dumps(record['transition_diff'], indent=2, sort_keys=True))
    finally:
        if wrote:
            print(f'restoring declared {args.from_state} state...')
            device.set_link(args.pair, prior, spec['space'], args.settle)
            restored = device.snapshot()
            record['after_restore'] = restored
            record['restore_diff'] = changed_tables(before, restored)
            output_record(args.output, record)
            if record['restore_diff']:
                print('WARNING: tables differ from the initial snapshot after restoration; '
                      'inspect the JSON record and the official UI before further writes.',
                      file=sys.stderr)
                exit_code = 2
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
