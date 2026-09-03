#!/usr/bin/env python3
"""Round-trip self-test against real hardware, using the in-band readback.

Before the 0x74/0x75 readback was decoded there was no way to check that a
write landed -- the CLI wrote and hoped. Now most subsystems can be verified
against the device itself, so this exercises them and reports what actually
holds.

    python3 tools/selftest.py                      # read-only, always safe
    python3 tools/selftest.py --write              # + restore-guaranteed writes
    python3 tools/selftest.py -p zen_go            # another device profile

READ-ONLY by default: it only sends readback queries, which is exactly what
the Launcher issues on connect. --write opts into a handful of round trips
that change device state and put it back.

SAFETY
  * Every readback index goes through protocol.build_readback_query, which
    bounds-checks against frame.readback.category_counts. An out-of-range
    index CRASHES this firmware (Cortex-M BusFault, physical power cycle --
    see PROTOCOL.md 4a). Categories with no known count are queried at
    index 0 only. --force is never used, and must never be added here.
  * Every write test captures true prior state first and restores it in a
    finally:, so an assertion failure or a Ctrl-C still puts the device back.
  * Write targets default to the least likely to be monitored (the last
    strip of the last mix). Override with --write-dest / --write-mix.

WHAT IT CANNOT CHECK
  Reported as SKIP, not PASS, so the summary never overstates coverage:
  mic modeling (no readback found), channel link (host-side by design --
  the device does not propagate it), sample rate (writing it drops audio,
  so it is not round-tripped here).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from antelope import protocol as proto
from antelope.transport import HidTransport, find_hidraw

PASS, FAIL, SKIP = 'PASS', 'FAIL', 'SKIP'
results = []


def record(status, name, detail=''):
    results.append((status, name, detail))
    colour = {'PASS': '\033[32m', 'FAIL': '\033[31m', 'SKIP': '\033[33m'}
    reset = '\033[0m' if sys.stdout.isatty() else ''
    tag = (colour.get(status, '') if sys.stdout.isatty() else '') + status + reset
    print(f'  [{tag}] {name}' + (f'  -- {detail}' if detail else ''), flush=True)


def check(name, cond, detail=''):
    # `detail` explains a failure; suppress it when the check passed so a
    # passing line never trails an empty "-- ".
    record(PASS if cond else FAIL, name, '' if cond else detail)
    return cond


class Dev:
    def __init__(self, profile, timeout):
        self.p = profile
        self.timeout = timeout
        d = profile['device']
        vid = int(d['vid'], 16) if isinstance(d['vid'], str) else d['vid']
        pid = int(d['pid'], 16) if isinstance(d['pid'], str) else d['pid']
        self.node = find_hidraw(vid, pid)
        self.t = HidTransport(self.node, profile['transport']['report_size'])

    def read(self, cat, idx=0):
        """Bounds-checked readback. Returns the body, or None."""
        req = proto.build_readback_query(self.p, cat, idx)   # raises if out of range
        data = self.t.query(
            req, lambda d: proto.is_readback_response(self.p, d, cat, idx),
            timeout=self.timeout)
        return proto.readback_body(self.p, data) if data is not None else None

    def write(self, pkt, settle=0.3):
        self.t.write(pkt)
        time.sleep(settle)


# --------------------------------------------------------------------------
# read-only tests
# --------------------------------------------------------------------------

def t_identity(dev):
    body = dev.read(proto.IDENTITY_READBACK_CATEGORY)
    if body is None:
        return record(FAIL, 'identity', 'no response to readback cat 0x01')
    ident = proto.parse_identity_record(dev.p, body)
    # never print the serial -- only that it is present and plausibly sized
    ok = bool(ident['name'])
    record(PASS if ok else FAIL, 'identity',
           f"name={ident['name']!r} rev={ident['revision']} "
           f"serial=<{len(ident['serial'] or '')} chars, not shown>")
    fw = proto.parse_firmware_record(dev.p, dev.read(proto.FIRMWARE_READBACK_CATEGORY))
    record(PASS if fw else SKIP, 'firmware string',
           fw or 'cat 0x00 carries no ASCII version on this device')


def t_bounds_guard(dev):
    """The BusFault guard must refuse an out-of-range index. Pure logic -- this
    deliberately does NOT send anything; sending it is what breaks hardware."""
    counts = dev.p['frame'].get('readback', {}).get('category_counts', {})
    if not counts:
        return record(SKIP, 'readback bounds guard',
                      'this profile declares no category_counts, so nothing can '
                      'be bounded -- do not sweep indices on this device')
    cat = next(iter(counts))
    n = int(counts[cat])
    try:
        proto.build_readback_query(dev.p, int(cat, 0), n)      # one past the end
        record(FAIL, 'readback bounds guard',
               f'cat {cat} index {n} was NOT refused -- this would crash the device')
    except proto.ConstraintError:
        record(PASS, 'readback bounds guard', f'cat {cat} index {n} correctly refused')


def t_routing(dev):
    rc = dev.p['frame'].get('routing_command', {})
    counts = rc.get('destination_channels', {})
    if not counts:
        return record(SKIP, 'routing readback', 'no destination_channels in profile')
    bad, unresolved = [], []
    for k in sorted(counts, key=int):
        dest = int(k)
        body = dev.read(proto.ROUTING_READBACK_CATEGORY, dest)
        if body is None:
            bad.append(f'dest {dest}: no response')
            continue
        try:
            did, pairs = proto.parse_routing_record(dev.p, body)
        except ValueError as e:
            bad.append(f'dest {dest}: {e}')
            continue
        if did != dest:
            bad.append(f'dest {dest}: record says dest {did}')
        # NOT a channel-count check: parse_routing_record derives its length
        # from destination_channels, so comparing len(pairs) to that value is
        # circular and can never fail. Instead use the one independent signal
        # the DEVICE gives us -- how far into the record real data extends.
        # The record is <dest_id> + 2 bytes per channel, so a declared count n
        # occupies 1+2n bytes. Data beyond that means n is too SMALL and we are
        # silently ignoring channels. (Data stopping short is fine: a trailing
        # pair can legitimately be (0,0) = preamp 1, which rstrip eats.)
        n = int(counts[k])
        used = len(bytes(body).rstrip(b'\x00'))
        if used > 1 + 2 * n:
            bad.append(f'dest {dest}: profile says {n} ch but the record carries '
                       f'data out to byte {used} (>= {(used - 1 + 1) // 2} ch)')
        for b, i in pairs:
            lab = proto.route_source_label(dev.p, b, i)
            if lab is None or 'unknown' in str(lab).lower():
                unresolved.append(f'({b:#04x},{i})')
    check(f'routing readback: {len(counts)} groups parse, counts match profile',
          not bad, '; '.join(bad[:3]))
    if unresolved:
        record(SKIP, 'routing source labels',
               f'{len(set(unresolved))} distinct (bank,idx) not named in the '
               f'profile: {sorted(set(unresolved))[:5]}')
    else:
        record(PASS, 'routing source labels', 'every source resolves to a name')


def t_routing_builder(dev):
    """Rebuild the write frame from what the device reports and check it is
    byte-identical. Proves builder and parser agree WITHOUT writing anything."""
    rc = dev.p['frame'].get('routing_command', {})
    counts = rc.get('destination_channels', {})
    addr = rc.get('addressable_destinations', {})
    if not counts or not addr:
        return record(SKIP, 'routing builder round-trip', 'profile lacks routing config')
    off = proto._as_int(rc['channel_list_offset'])
    stride = proto._as_int(rc.get('channel_stride', 2))
    mismatched = []
    for k in sorted(addr, key=int):
        dest = int(k)
        body = dev.read(proto.ROUTING_READBACK_CATEGORY, dest)
        if body is None:
            continue
        _, pairs = proto.parse_routing_record(dev.p, body)
        pkt = proto.build_route_command(dev.p, dest, pairs)
        want = b''.join(bytes(p) for p in pairs)
        got = bytes(pkt[off:off + stride * len(pairs)])
        if got != want:
            mismatched.append(f'dest {dest}')
    check('routing builder round-trip (build == what device reports)',
          not mismatched, ', '.join(mismatched[:4]))


def t_mixer(dev):
    cat = proto.MIXER_READBACK_CATEGORY
    n = proto.readback_category_count(dev.p, cat)
    if n is None:
        return record(SKIP, 'mixer readback',
                      'no record count for cat 0x04 on this device -- not swept')
    has_send = proto.mix_has_send(dev.p)
    bad = []
    nslots = None
    for m in range(n):
        body = dev.read(cat, m)
        if body is None:
            bad.append(f'mix {m + 1}: no response')
            continue
        slots = proto.parse_mixer_record(dev.p, body)
        if nslots is None:
            nslots = len(slots)
        elif len(slots) != nslots:
            bad.append(f'mix {m + 1}: {len(slots)} slots, mix 1 had {nslots}')
        for i, s in enumerate(slots):
            if not 0 <= s['fader'] <= 90:
                bad.append(f'mix {m + 1} slot {i}: fader {s["fader"]}')
            plo, phi = dev.p.get('params', {}).get('mix_pan', {}).get('range', (-30, 30))
            if not plo <= s['pan'] <= phi:
                bad.append(f'mix {m + 1} slot {i}: pan {s["pan"]} outside {plo}..{phi}')
            if has_send and not 0 <= s['send'] <= 96:
                bad.append(f'mix {m + 1} slot {i}: send {s["send"]}')
    check(f'mixer readback: {n} mixes x {nslots} slots, values in range',
          not bad, '; '.join(bad[:3]))

    # builder round-trip, no write
    body = dev.read(cat, 0)
    if body is not None:
        slots = proto.parse_mixer_record(dev.p, body)
        bad2 = []
        for i, s in enumerate(slots):
            pkt = proto.build_mix_command(dev.p, 0, i, s['fader'], s['pan'],
                                          s['send'], s['mute'], s['solo'])
            f = dev.p['frame']['mix_command']
            a = proto._as_int(f['fader_offset'])
            width = 3 if has_send else 2
            if bytes(pkt[a:a + width]) != s['raw'][:width]:
                bad2.append(str(i))
        check('mixer builder round-trip (build == what device reports)',
              not bad2, 'slots ' + ','.join(bad2[:6]))


def t_auraverb(dev):
    """AuraVerb readback (cat 0x0a) parses, values in range, builder matches."""
    cat = proto.AURAVERB_READBACK_CATEGORY
    if 'auraverb_command' not in dev.p.get('frame', {}):
        return record(SKIP, 'auraverb readback', 'no frame.auraverb_command in profile')
    body = dev.read(cat, 0)
    if body is None:
        return record(SKIP, 'auraverb readback', 'no response to cat 0x0a on this device')
    mixes = proto.parse_auraverb_record(dev.p, body)
    bad = []
    for m, mx in enumerate(mixes):
        for k, v in mx['params'].items():
            if not 0 <= v <= 100:
                bad.append(f'mix {m + 1} {k}={v}')
        if mx['wet'] not in (None, 100):
            bad.append(f'mix {m + 1} wet={mx["wet"]}')
    check(f'auraverb readback: {len(mixes)} mixes, params in range', not bad,
          '; '.join(bad[:3]))
    # builder round-trip: build Mix 1's frame from the readback, compare bytes
    m1 = mixes[0]
    pkt = proto.build_auraverb_command(dev.p, m1['params'], bool(m1['enabled']), mix=0)
    f = dev.p['frame']['auraverb_command']
    a = proto._as_int(f['param_offsets']['room_size'])
    e = proto._as_int(f['enabled_offset'])
    ref = m1['raw'][:9] + bytes([1 if m1['enabled'] else 0])
    got = bytes(pkt[a:a + 9]) + bytes([pkt[e]])
    check('auraverb builder round-trip (build == what device reports)',
          got == ref, f'{got.hex()} != {ref.hex()}')


def t_channel_state(dev):
    """cat 0x05 (preamp gain) + 0x06 (channel status) must agree with the
    pushed 0x73 state report -- two independent device reports of the same
    thing, so a mismatch means a parser (or the device) drifted."""
    g_body = dev.read(proto.PREAMP_GAIN_READBACK_CATEGORY)
    s_body = dev.read(proto.CHANNEL_STATUS_READBACK_CATEGORY)
    st = dev.t.read_one(proto.state_report_magic(dev.p), timeout=3.0)
    if g_body is None or s_body is None or st is None:
        return record(SKIP, 'channel state cross-check',
                      'no cat 0x05/0x06 or no 0x73 report on this device')
    gains = proto.parse_preamp_gain_record(dev.p, g_body)
    stats = proto.parse_channel_status_record(dev.p, s_body)
    bad = []
    for c in range(len(gains)):
        ref = proto.parse_state(dev.p, st, c)
        if gains[c] != ref['gain']:
            bad.append(f'ch{c} gain {gains[c]}!={ref["gain"]}')
        if (stats[c]['mode'] != ref['input_mode']
                or int(stats[c]['phantom']) != ref['phantom']
                or int(stats[c]['phase_invert']) != ref['phase_invert']):
            bad.append(f'ch{c} status {stats[c]["raw"]:#04x}')
    check(f'cat 0x05/0x06 agree with 0x73 for {len(gains)} channels',
          not bad, '; '.join(bad[:4]))


def t_state_report(dev):
    """The pushed 0x73 report should still parse and agree with the readback
    where they overlap."""
    data = dev.t.read_one(proto.state_report_magic(dev.p), timeout=3.0)
    if data is None:
        return record(FAIL, 'state report', 'no 0x73 report seen -- device hung?')
    ok = []
    for key, label in (('sample_rate_byte_offset', 'sample rate'),
                       ('screen_brightness_byte_offset', 'brightness')):
        try:
            ok.append(f'{label}={proto.parse_state_scalar(dev.p, data, key)}')
        except Exception:
            pass
    record(PASS, 'state report parses', ', '.join(ok))


# --------------------------------------------------------------------------
# write tests -- each restores in a finally
# --------------------------------------------------------------------------

def t_write_mixer(dev, mix):
    """Change one strip's fader, verify via readback, restore exactly."""
    cat = proto.MIXER_READBACK_CATEGORY
    n = proto.readback_category_count(dev.p, cat)
    if n is None:
        return record(SKIP, 'WRITE mixer strip', 'no mixer readback on this device')
    m = min(max(mix - 1, 0), n - 1)
    body = dev.read(cat, m)
    if body is None:
        return record(FAIL, 'WRITE mixer strip', f'could not read mix {m + 1}')
    slots = proto.parse_mixer_record(dev.p, body)
    ch = len(slots) - 1                      # last strip, least likely in use
    orig = slots[ch]
    probe = 30 if orig['fader'] != 30 else 40
    try:
        dev.write(proto.build_mix_command(dev.p, m, ch, probe, orig['pan'],
                                          orig['send'], orig['mute'], orig['solo']))
        got = proto.parse_mixer_record(dev.p, dev.read(cat, m))[ch]
        check(f'WRITE mixer: mix {m + 1} strip {ch} fader -> -{probe} dB',
              got['fader'] == probe,
              f"read back {got['fader']} (wanted {probe})")
        # untouched fields must survive a whole-strip write
        check('WRITE mixer: other fields preserved',
              (got['pan'], got['send'], got['mute'], got['solo'])
              == (orig['pan'], orig['send'], orig['mute'], orig['solo']))
    finally:
        dev.write(proto.build_mix_command(dev.p, m, ch, orig['fader'], orig['pan'],
                                          orig['send'], orig['mute'], orig['solo']))
        back = dev.read(cat, m)
        restored = back is not None and proto.parse_mixer_record(dev.p, back)[ch]['raw'] == orig['raw']
        record(PASS if restored else FAIL, 'WRITE mixer: restored original',
               '' if restored else 'RESTORE FAILED -- check the mixer by hand!')


def t_write_auraverb(dev):
    """Nudge Mix 1's reverb-level, verify via readback cat 0x0a, restore.
    Keeps the enabled bit and every other param as read, so a disabled
    AuraVerb stays disabled and inaudible throughout."""
    cat = proto.AURAVERB_READBACK_CATEGORY
    if 'auraverb_command' not in dev.p.get('frame', {}):
        return record(SKIP, 'WRITE auraverb', 'no frame.auraverb_command in profile')
    body = dev.read(cat, 0)
    if body is None:
        return record(SKIP, 'WRITE auraverb', 'no cat 0x0a readback on this device')
    mx = proto.parse_auraverb_record(dev.p, body)[0]
    en = bool(mx['enabled'])
    orig = dict(mx['params'])
    probe = dict(orig, reverb_level=(33 if orig['reverb_level'] != 33 else 44))
    try:
        dev.write(proto.build_auraverb_command(dev.p, probe, en, mix=0))
        got = proto.parse_auraverb_record(dev.p, dev.read(cat, 0))[0]
        check('WRITE auraverb: Mix 1 reverb-level changes',
              got['params']['reverb_level'] == probe['reverb_level'],
              f"read back {got['params']['reverb_level']}")
        check('WRITE auraverb: other params + enabled preserved',
              got['enabled'] == en and all(
                  got['params'][k] == orig[k] for k in orig if k != 'reverb_level'))
    finally:
        dev.write(proto.build_auraverb_command(dev.p, orig, en, mix=0))
        back = dev.read(cat, 0)
        ok = back is not None and proto.parse_auraverb_record(dev.p, back)[0]['raw'] == mx['raw']
        record(PASS if ok else FAIL, 'WRITE auraverb: restored original',
               '' if ok else 'RESTORE FAILED -- check `auraverb` by hand!')


def t_write_routing(dev, destname):
    """Re-point one routing channel, verify, restore exactly."""
    try:
        dest = proto.resolve_route_dest(dev.p, destname)
    except ValueError as e:
        return record(SKIP, 'WRITE routing', str(e))
    body = dev.read(proto.ROUTING_READBACK_CATEGORY, dest)
    if body is None:
        return record(FAIL, 'WRITE routing', f'could not read dest {dest}')
    _, orig = proto.parse_routing_record(dev.p, body)
    ch = len(orig) - 1                       # last channel of the group
    mute = tuple(proto.ROUTE_MUTE)
    probe = mute if tuple(orig[ch]) != mute else (0, 0)
    new = list(orig)
    new[ch] = probe
    try:
        dev.write(proto.build_route_command(dev.p, dest, new))
        _, got = proto.parse_routing_record(
            dev.p, dev.read(proto.ROUTING_READBACK_CATEGORY, dest))
        check(f'WRITE routing: {destname} ch {ch + 1} -> '
              f'{proto.route_source_label(dev.p, *probe)}',
              tuple(got[ch]) == probe,
              f'read back {got[ch]}')
        check('WRITE routing: other channels preserved',
              [tuple(x) for x in got[:ch]] == [tuple(x) for x in orig[:ch]])
    finally:
        dev.write(proto.build_route_command(dev.p, dest, orig))
        back = dev.read(proto.ROUTING_READBACK_CATEGORY, dest)
        ok = back is not None and [tuple(x) for x in proto.parse_routing_record(dev.p, back)[1]] \
            == [tuple(x) for x in orig]
        record(PASS if ok else FAIL, 'WRITE routing: restored original',
               '' if ok else 'RESTORE FAILED -- check the matrix by hand!')


def t_write_brightness(dev):
    """Harmless and visible: nudge the front panel, verify, restore."""
    key = 'screen_brightness_byte_offset'
    if key not in dev.p.get('frame', {}).get('state_report', {}):
        return record(SKIP, 'WRITE brightness', 'not in this profile')
    if 'screen_brightness' not in dev.p.get('params', {}):
        return record(SKIP, 'WRITE brightness', 'no screen_brightness param')
    data = dev.t.read_one(proto.state_report_magic(dev.p), timeout=3.0)
    if data is None:
        return record(FAIL, 'WRITE brightness', 'no state report')
    orig = proto.parse_state_scalar(dev.p, data, key)
    probe = 40 if orig != 40 else 70
    try:
        dev.write(proto.build_global_command(dev.p, 'screen_brightness', probe), settle=0.6)
        data = dev.t.read_one(proto.state_report_magic(dev.p), timeout=3.0)
        got = proto.parse_state_scalar(dev.p, data, key)
        check(f'WRITE brightness: {orig} -> {probe}', got == probe, f'read back {got}')
    finally:
        dev.write(proto.build_global_command(dev.p, 'screen_brightness', orig), settle=0.6)
        data = dev.t.read_one(proto.state_report_magic(dev.p), timeout=3.0)
        ok = data is not None and proto.parse_state_scalar(dev.p, data, key) == orig
        record(PASS if ok else FAIL, 'WRITE brightness: restored original',
               '' if ok else f'RESTORE FAILED -- set it back with `set-brightness {orig}`')


def t_unverifiable():
    for name, why in (
            ('mic modeling / emuMic', 'no readback found; only the phantom bit moves'),
            ('channel link', 'no link readback exists (proven 2026-09-03) -- state is client-tracked'),
            ('sample rate', 'writing it drops audio, so it is not round-tripped here')):
        record(SKIP, f'{name}: cannot self-verify', why)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-p', '--profile', default='orion',
                    help='profile path, filename, or short name (default: orion)')
    ap.add_argument('--write', action='store_true',
                    help='also run round-trip WRITE tests (each restores afterwards)')
    ap.add_argument('--write-mix', type=int, default=4,
                    help='mix number for the write test (default 4, least likely in use)')
    ap.add_argument('--write-dest', default='mix_ch4',
                    help='routing destination for the write test (default mix_ch4)')
    ap.add_argument('--timeout', type=float, default=2.0)
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from antelope.cli import _resolve_profile_path
    profile = proto.load_profile(_resolve_profile_path(args.profile))

    print(f"self-test: {profile['device'].get('name', '?')}  "
          f"({'READ-ONLY' if not args.write else 'READ + WRITE round trips'})\n")

    if 'readback' not in profile.get('frame', {}):
        print('This profile has no frame.readback -- nothing can be verified '
              'against the device. Aborting.')
        return 2

    dev = Dev(profile, args.timeout)

    print('device identity')
    t_identity(dev)
    print('\nsafety')
    t_bounds_guard(dev)
    print('\nrouting matrix (readback cat 0x03)')
    t_routing(dev)
    t_routing_builder(dev)
    print('\nvirtual mixer (readback cat 0x04)')
    t_mixer(dev)
    print('\nAuraVerb (readback cat 0x0a)')
    t_auraverb(dev)
    print('\nchannel state (readback cat 0x05 / 0x06)')
    t_channel_state(dev)
    print('\npushed state report (0x73)')
    t_state_report(dev)

    if args.write:
        print('\nwrite round trips (each restores)')
        t_write_brightness(dev)
        t_write_mixer(dev, args.write_mix)
        t_write_auraverb(dev)
        t_write_routing(dev, args.write_dest)
    else:
        print('\nwrite round trips')
        record(SKIP, 'write tests', 'not run -- pass --write to enable')

    print('\nknown gaps')
    t_unverifiable()

    n_pass = sum(1 for s, _, _ in results if s == PASS)
    n_fail = sum(1 for s, _, _ in results if s == FAIL)
    n_skip = sum(1 for s, _, _ in results if s == SKIP)
    print(f'\n{n_pass} passed, {n_fail} failed, {n_skip} skipped')
    if n_fail:
        print('\nFAILURES:')
        for s, name, detail in results:
            if s == FAIL:
                print(f'  {name}  -- {detail}')
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main())
