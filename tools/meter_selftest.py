#!/usr/bin/env python3
"""Controlled live meter-mapping test for the Orion Studio Synergy Core.

The test uses a signal already present on physical Preamp 1.  It routes that
signal, one destination at a time, into the device's matrix and compares
state/meter reports with the destination muted.  It also walks the four
virtual mixers one strip at a time.  All routing and mixer writes are restored
on exit; no input gain, mode, phantom, or phase setting is changed.

Run from the repository root:

    python3 tools/meter_selftest.py

This is intentionally Orion-specific test tooling.  It does not query any
readback category without a profile-declared bound.
"""
import collections
import argparse
import json
import os
import select
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from antelope import protocol as proto
from antelope.transport import HidTransport, find_hidraw


PROFILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'profiles', 'orion_studio_sc.json')
STATE_MAGIC = 0x73
METER_MAGIC = 0x75
STATE_METER_RANGE = range(123, 233)
SHARED_METER_RANGE = range(123, 221)
ALL_REPORT_DATA = range(16, 320)
ROUTE_MUTE = (0x0b, 0)


def median(values):
    return int(statistics.median(values)) if values else None


def report_summary(before, after, offsets):
    """Return useful inverted-meter candidates, suppressing idle jitter."""
    hits = []
    for off in offsets:
        b = [x[off] for x in before if len(x) > off]
        a = [x[off] for x in after if len(x) > off]
        if not b or not a:
            continue
        bm, am = median(b), median(a)
        amin, amax = min(a), max(a)
        bmin, bmax = min(b), max(b)
        delta = bm - am
        # Meter values are inverted: idle is normally 96 and activity moves
        # downward. The second term catches a short peak missed by medians.
        # Use the median transition as the primary evidence. A single low
        # sample is common in the continuously-running report stream (and can
        # be caused by another active source), so it is not enough by itself
        # to claim a lane.
        active = delta >= 4
        if active:
            hits.append((off, bm, am, amin, amax, delta))
    hits.sort(key=lambda x: (-x[5], x[0]))
    return hits


class Device:
    def __init__(self, profile):
        self.profile = profile
        dev = profile['device']
        vid = int(dev['vid'], 16) if isinstance(dev['vid'], str) else dev['vid']
        pid = int(dev['pid'], 16) if isinstance(dev['pid'], str) else dev['pid']
        self.node = find_hidraw(vid, pid)
        self.size = profile['transport']['report_size']
        self.transport = HidTransport(self.node, self.size)

    def write(self, packet, pause=0.18):
        self.transport.write(packet)
        time.sleep(pause)

    def reports(self, seconds=0.35):
        """Collect both unsolicited report families without printing raw data."""
        groups = collections.defaultdict(list)
        fd = os.open(self.node, os.O_RDONLY)
        end = time.time() + seconds
        try:
            while time.time() < end:
                ready, _, _ = select.select([fd], [], [], 0.05)
                if not ready:
                    continue
                data = os.read(fd, self.size)
                if data and data[0] in (STATE_MAGIC, METER_MAGIC):
                    groups[data[0]].append(data)
        finally:
            os.close(fd)
        return groups

    def readback(self, category, index):
        # build_readback_query enforces category_counts. Never add force=True.
        req = proto.build_readback_query(self.profile, category, index)
        data = self.transport.query(
            req,
            lambda d: proto.is_readback_response(self.profile, d, category, index),
            timeout=3.0)
        if data is None:
            raise RuntimeError(f'no readback for category {category:#04x} index {index}')
        return proto.readback_body(self.profile, data)

    def route(self, dest, pairs):
        self.write(proto.build_route_command(self.profile, dest, pairs), pause=0.22)

    def select_meters(self, value):
        self.write(proto.build_command(self.profile, 'meters_window_selection', 0, value))

    def select_mixer(self, value):
        self.write(proto.build_command(self.profile, 'meters_window_selection', 1, value))

    def set_mix_strip(self, mix, channel, slot):
        self.write(proto.build_mix_command(
            self.profile, mix, channel, slot['fader'], slot['pan'], slot['send'],
            slot['mute'], slot['solo']), pause=0.22)


def current_buses(dev):
    groups = dev.reports(0.25)
    states = groups.get(STATE_MAGIC, [])
    if not states:
        raise RuntimeError('no 0x73 state report while snapshotting buses')
    data = states[-1]
    result = {}
    for key in dev.profile.get('buses', {}).get('known', {}):
        bus = int(key)
        result[bus] = proto.parse_bus_state(dev.profile, data, bus)
    return result

def current_routes(dev):
    result = {}
    counts = dev.profile['frame']['routing_command']['destination_channels']
    for key in sorted(counts, key=int):
        dest = int(key)
        body = dev.readback(proto.ROUTING_READBACK_CATEGORY, dest)
        _, pairs = proto.parse_routing_record(dev.profile, body)
        result[dest] = pairs
    return result


def current_mixes(dev):
    result = {}
    n = proto.readback_category_count(dev.profile, proto.MIXER_READBACK_CATEGORY)
    if n is None:
        n = 4
    for mix in range(n):
        body = dev.readback(proto.MIXER_READBACK_CATEGORY, mix)
        result[mix] = proto.parse_mixer_record(dev.profile, body)
    return result


def all_mute(n):
    return [ROUTE_MUTE] * n


def print_hits(label, before, after, offsets=SHARED_METER_RANGE):
    print(f'\n{label}')
    for magic, name in ((STATE_MAGIC, '0x73'), (METER_MAGIC, '0x75')):
        hits = report_summary(before.get(magic, []), after.get(magic, []), offsets)
        if not hits:
            print(f'  {name}: no activity candidate')
            continue
        rendered = ', '.join(
            f'@{off} {bm}->{am} (min {amin}, d{delta:+d})'
            for off, bm, am, amin, _amax, delta in hits[:16])
        extra = f' ... +{len(hits) - 16}' if len(hits) > 16 else ''
        print(f'  {name}: {rendered}{extra}')
    sys.stdout.flush()


def collect_selector_baseline(dev, value, route_pairs):
    dev.route(route_pairs[0], route_pairs[1])
    dev.select_meters(value)
    return dev.reports()


def test_physical_preamp(dev):
    """Physical Preamp 1 is already driven by the user's injected tone."""
    dev.select_meters(0)
    groups = dev.reports(0.65)
    print('\nphysical input: Preamp selector 0')
    states = groups.get(STATE_MAGIC, [])
    if not states:
        print('  0x73: no state reports')
        return
    values = [x[221:233] for x in states if len(x) >= 233]
    if not values:
        print('  0x73: report too short for physical meter bank')
        return
    med = [median([row[c] for row in values]) for c in range(12)]
    print('  0x73 @221..232 median raw:', ' '.join(f'ch{c + 1}={v}' for c, v in enumerate(med)))
    active = [c + 1 for c, v in enumerate(med) if v is not None and v < 90]
    if 1 in active:
        print('  RESULT: Preamp 1 responds')
    else:
        print('  RESULT: Preamp 1 tone was not visible below raw 90; verify injection/routing')
    print('  NOTE: physical preamps 2-12 require separate physical signals and remain untested')


def test_mixes(dev, routes, mixes, full_strip_sweep=True):
    """Map every virtual-mixer strip under selectors 21..24."""
    results = []
    for mix in range(4):
        dest = 10 + mix
        original_route = routes[dest]
        working = all_mute(len(original_route))
        # Keep all strips silent except the strip under test. Make the mix
        # master unity and unmuted while testing, then restore in finally.
        master = dict(mixes[mix][0])
        master.update(fader=0, pan=0, send=96, mute=False, solo=False)
        dev.set_mix_strip(mix, 0, master)
        dev.route(dest, working)
        dev.select_mixer(mix)
        print(f'\nvirtual Mix {mix + 1}: selectors 5..8 and 21..24')

        # First verify the L/R selector family with strip 1 active.
        working[0] = (0x00, 0)
        strip = dict(mixes[mix][1])
        strip.update(fader=0, pan=0, send=96, mute=False, solo=False)
        dev.set_mix_strip(mix, 1, strip)
        dev.route(dest, working)
        for value in (5 + mix, 21 + mix):
            dev.select_meters(value)
            dev.select_mixer(mix)
            before = dev.reports(0.25)
            working[0] = ROUTE_MUTE
            dev.route(dest, working)
            muted = dev.reports(0.25)
            working[0] = (0x00, 0)
            dev.route(dest, working)
            after = dev.reports(0.35)
            # Print using the muted comparison; the first sample above is
            # retained only to settle the selector after the write.
            print_hits(f'  active-vs-muted selector {value}', muted, after,
                       ALL_REPORT_DATA)
            results.append((mix, value, 1, after, muted))

        if not full_strip_sweep:
            continue
        # Walk each strip. A mute baseline and active sample isolates its lane.
        for channel in range(1, 33):
            working = all_mute(len(original_route))
            working[channel - 1] = (0x00, 0)
            slot = dict(mixes[mix][channel])
            slot.update(fader=0, pan=0, send=96, mute=False, solo=False)
            dev.set_mix_strip(mix, channel, slot)
            dev.route(dest, working)
            dev.select_meters(21 + mix)
            dev.select_mixer(mix)
            active = dev.reports(0.32)
            working[channel - 1] = ROUTE_MUTE
            dev.route(dest, working)
            muted = dev.reports(0.24)
            details = []
            for magic, name in ((STATE_MAGIC, '0x73'), (METER_MAGIC, '0x75')):
                offsets = SHARED_METER_RANGE if magic == STATE_MAGIC else ALL_REPORT_DATA
                hits = report_summary(muted.get(magic, []), active.get(magic, []), offsets)
                if hits:
                    details.append(f'{name} {[h[0] for h in hits[:12]]}')
            print(f'  strip {channel:2d}: ' +
                  ('; '.join(details) if details else 'no lane candidate'))
            results.append((mix, 21 + mix, channel, active, muted))
        # Leave this mix silent until the next one; final restoration handles it.
    return results


def test_mixer_selector_matrix(dev, routes, mixes):
    """Cross-check target-0 and target-1 selectors independently.

    The per-strip sweep above intentionally selects the matching values on
    both controls. This pass holds one mix active and varies the mixer-window
    selector, so a lane is attributed to the selector that actually gates it.
    """
    print('\nmixer-window selector cross-check (target 1)')
    for mix in range(4):
        dest = 10 + mix
        original = routes[dest]
        active_route = all_mute(len(original))
        active_route[0] = (0x00, 0)
        slot = dict(mixes[mix][1])
        slot.update(fader=0, pan=0, send=96, mute=False, solo=False)
        master = dict(mixes[mix][0])
        master.update(fader=0, pan=0, send=96, mute=False, solo=False)
        dev.set_mix_strip(mix, 0, master)
        dev.set_mix_strip(mix, 1, slot)
        for target in range(4):
            dev.route(dest, active_route)
            dev.select_meters(21 + mix)
            dev.select_mixer(target)
            active = dev.reports(0.3)
            dev.route(dest, all_mute(len(original)))
            muted = dev.reports(0.22)
            hits = report_summary(muted.get(STATE_MAGIC, []),
                                  active.get(STATE_MAGIC, []),
                                  SHARED_METER_RANGE)
            lanes = [h[0] for h in hits]
            print(f'  active Mix {mix + 1}, target-1={target}: '
                  + (f'lanes {lanes}' if lanes else 'no lane'))


def test_outputs(dev, routes, buses):
    """Test matrix-fed output destinations using Preamp 1 as the source."""
    # Meters selector -> routing destination. Inputs and unresolved positions
    # are intentionally excluded and reported below.
    tests = [
        (9, 14, 'Surround Out', True),
        (10, 0, 'Line Out', False),
        (11, 1, 'HP1', False),
        (12, 2, 'HP2', False),
        (13, 3, 'Monitor A', False),
        (14, 4, 'Monitor B', False),
        (15, 5, 'Reamp', False),
        (16, 7, 'ADAT Out', False),
        (17, 8, 'S/PDIF Out', False),
        (18, 9, 'AFX In', False),
        (25, 14, 'Surround In', False),
    ]
    results = []
    for selector, dest, label, surround in tests:
        original = routes[dest]
        working = all_mute(len(original))
        working[0] = (0x00, 0)  # Preamp 1
        bus_id = {0: 3, 1: 1, 2: 2, 3: 0, 4: 5, 5: 4}.get(dest)
        if bus_id is not None:
            # The output meter may be post-level. Preserve the user's level,
            # but make a zero-level bus testable for this controlled pass.
            dev.write(proto.build_command(dev.profile, 'bus_level', bus_id, 96))
            if buses[bus_id].get('mute'):
                dev.write(proto.build_command(dev.profile, 'bus_mute', bus_id, 0))
        dev.route(dest, working)
        dev.select_meters(selector)
        active = dev.reports(0.35)
        working[0] = ROUTE_MUTE
        dev.route(dest, working)
        muted = dev.reports(0.25)
        print_hits(f'output {label}: selector {selector}, destination {dest}',
                   muted, active, ALL_REPORT_DATA)
        results.append((selector, dest, label, active, muted))
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--quick', action='store_true',
                    help='skip the 128-case per-strip sweep; keep selector/output tests')
    args = ap.parse_args()
    with open(PROFILE_PATH) as fh:
        profile = json.load(fh)
    dev = Device(profile)
    print(f'meter self-test: {profile["device"]["name"]} ({dev.node})')
    routes = current_routes(dev)
    mixes = current_mixes(dev)
    buses = current_buses(dev)
    start = dev.reports(0.25).get(STATE_MAGIC, [])
    start_state = start[-1] if start else None
    if start_state:
        print(f'initial selectors: meters={start_state[121]} mixer={start_state[122]}')

    try:
        test_physical_preamp(dev)
        # Mix tests are the broadest pass. They use only internal routing and
        # do not require the user's tone to be present after Preamp 1 is seen.
        test_mixes(dev, routes, mixes, full_strip_sweep=not args.quick)
        test_mixer_selector_matrix(dev, routes, mixes)
        test_outputs(dev, routes, buses)
        print('\nselector-only pass: values 0..25 and mixer target values 0..3')
        for value in range(26):
            dev.select_meters(value)
            groups = dev.reports(0.08)
            states = groups.get(STATE_MAGIC, [])
            echoed = states[-1][121] if states and len(states[-1]) > 121 else None
            print(f'  meters {value:2d}: echoed {echoed}')
        for value in range(4):
            dev.select_mixer(value)
            groups = dev.reports(0.08)
            states = groups.get(STATE_MAGIC, [])
            echoed = states[-1][122] if states and len(states[-1]) > 122 else None
            print(f'  mixer target {value}: echoed {echoed}')
    finally:
        print('\nrestoring routing, mixer state, and selectors...')
        for dest in sorted(routes):
            dev.route(dest, routes[dest])
        for mix in sorted(mixes):
            for channel, slot in enumerate(mixes[mix]):
                dev.set_mix_strip(mix, channel, slot)
        for bus, state in sorted(buses.items()):
            dev.write(proto.build_command(profile, 'bus_level', bus, state['level']))
            for param, key in (('bus_dim', 'dim'), ('bus_mute', 'mute'),
                               ('bus_mono', 'mono')):
                if key in state:
                    dev.write(proto.build_command(profile, param, bus, int(bool(state[key]))))
        if start_state:
            dev.select_meters(start_state[121])
            dev.select_mixer(start_state[122])
        print('restore complete')


if __name__ == '__main__':
    main()
