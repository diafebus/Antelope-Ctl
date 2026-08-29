#!/usr/bin/env python3
"""
Auto-find the exact transition in a whole capture, instead of hand-picking
before/after frame numbers in the Wireshark GUI (easy to get wrong -- the
device polls constantly and resends the *same* report at rest, so two
frames picked by eye often land on the same steady state and diff to
nothing).

Usage:
  1. Capture your session as usual (see CAPTURING.md), doing ONE isolated
     action in the Launcher.
  2. Extract every report as tab-separated fields (NOT -x -- this uses
     tshark's field extractor, which sidesteps hex-dump text formatting
     entirely and always gives the full payload). HID interrupt transfers
     put their payload in usbhid.data, not usb.capdata (the latter is only
     used when no class-specific dissector -- like HID here -- claims the
     data, so it comes back empty for these reports):

       tshark -r session.pcapng -Y "usb.data_len==320" \
           -T fields -e frame.number -e frame.time_relative -e usbhid.data -e usb.capdata \
           > all_reports.tsv

     (Both fields are included so the same command works regardless of
     which one your Wireshark version populates -- scan_capture.py checks
     usbhid.data first and falls back to usb.capdata.)

     IMPORTANT: this filter is on usb.data_len, not on a specific magic byte
     -- keep it that way even if you only care about one report type right
     now. Filtering by magic here would silently throw away every OTHER
     report type in the capture, which is exactly the data you'd need if
     the thing you're investigating turns out to live somewhere unexpected
     (see --all-magics below, and the screen-brightness/surround-EQ case in
     the README's "What's still unconfirmed" section, which is exactly this
     situation -- a capture that was filtered too narrowly the first time).

  3. Run this tool on that file:

       python3 tools/scan_capture.py all_reports.tsv

     It walks every report in order and prints only the moments something
     actually changed -- the frame numbers, timestamps, and exact byte
     offsets/values -- so you don't have to guess which two frames to diff.

  4. Cross-check the printed timestamp against when you made your change.
     The offset(s) that flip right around that time are your candidate.

By default this only looks at state reports (magic 0x73) -- meter reports
(magic 0x75, same 320-byte size) change constantly on their own and would
otherwise drown out the signal. Use --magic to look at a different report
type if needed, or --all-magics to scan every report type found in the file
at once (each magic diffed against its own preceding report of that same
magic) -- use this when you don't already know which report type carries
the thing you're testing, e.g. investigating whether screen brightness or
routing shows up somewhere other than 0x73/0x75/0x70.
"""
import argparse
import sys
from collections import Counter, defaultdict


def parse_capdata(hexstr: str) -> bytes:
    """usb.capdata from `-T fields` is colon-separated hex ('70:00:00:...')."""
    hexstr = hexstr.strip()
    if not hexstr:
        return b''
    if ':' in hexstr:
        return bytes(int(b, 16) for b in hexstr.split(':') if b)
    # some tshark versions/fields come back as one contiguous hex string
    return bytes.fromhex(hexstr)


def read_all_records(path: str):
    """Yields (frame_number, time_relative, bytes) for EVERY report in the file,
    regardless of magic, in file order (which is capture order). Each input
    line is frame.number, frame.time_relative, usbhid.data, usb.capdata
    (tab-separated) -- HID interrupt transfers populate usbhid.data; usb.capdata
    is only used when no class-specific dissector (like HID) claims the
    payload, so it's typically empty here -- we take whichever of the two
    columns is non-empty."""
    with open(path) as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 3:
                continue  # malformed/short line, skip rather than crash the scan
            frame_no, t = parts[0], parts[1]
            hexstr = ''
            for col in parts[2:4]:
                if col.strip():
                    hexstr = col
                    break
            data = parse_capdata(hexstr)
            if not data:
                continue
            yield frame_no, t, data


def read_records(path: str, magic: int):
    """Same as read_all_records(), filtered to reports whose first byte matches
    `magic`."""
    for frame_no, t, data in read_all_records(path):
        if data[0] == magic:
            yield frame_no, t, data


def diff_bytes(before: bytes, after: bytes):
    n = min(len(before), len(after))
    return [(i, before[i], after[i]) for i in range(n) if before[i] != after[i]]


def scan_one_magic(records, magic, known, label=''):
    """Runs the transition scan over one magic's already-filtered record list.
    Returns the transition count. `label` is prefixed to output when scanning
    multiple magics at once, so you can tell them apart."""
    if not records:
        return 0
    transitions = 0
    prev_frame, prev_t, prev_data = records[0]
    for frame_no, t, data in records[1:]:
        changes = diff_bytes(prev_data, data)
        unexplained = [c for c in changes if c[0] not in known]
        if unexplained:
            transitions += 1
            print(f'{label}frame {prev_frame} (t={prev_t}) -> frame {frame_no} (t={t}):')
            for off, old, new in unexplained:
                print(f'    offset {off:>3} (0x{off:02x}):  0x{old:02x} -> 0x{new:02x}  '
                      f'(signed: {old - 256 if old > 127 else old} -> {new - 256 if new > 127 else new})')
            print()
        prev_frame, prev_t, prev_data = frame_no, t, data
    return transitions


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tsv', help='output of tshark -T fields -e frame.number -e frame.time_relative -e usb.capdata')
    ap.add_argument('--magic', type=lambda x: int(x, 0), default=0x73,
                     help='only diff reports whose first byte equals this (default 0x73, the state report). '
                          'Ignored if --all-magics is given.')
    ap.add_argument('--all-magics', action='store_true',
                     help='scan every distinct magic byte found in the file, not just one. Each magic is '
                          'diffed against its own preceding report of that same magic, independently. Use '
                          'this when you do not already know which report type carries what you are '
                          'testing (e.g. is screen brightness in 0x73, or somewhere else entirely?).')
    ap.add_argument('--known-offset', type=int, action='append', default=[],
                     help='offset(s) already explained by other params, to suppress from output (repeatable). '
                          'In --all-magics mode this is applied to every magic\'s stream, which only makes '
                          'sense for offsets you know are coincidentally-shared noise (e.g. none, normally) -- '
                          'prefer running single-magic mode with the right --known-offset list per report type '
                          'once you know which magic you care about.')
    args = ap.parse_args()

    known = set(args.known_offset)

    if args.all_magics:
        all_records = list(read_all_records(args.tsv))
        if not all_records:
            sys.exit(f'No reports found in {args.tsv} at all -- check the tshark command included BOTH '
                      f'"-e usbhid.data -e usb.capdata" and that the capture/filter actually has data.')
        by_magic = defaultdict(list)
        for rec in all_records:
            by_magic[rec[2][0]].append(rec)
        counts = Counter({m: len(recs) for m, recs in by_magic.items()})
        print(f'{len(all_records)} total reports, {len(by_magic)} distinct magic byte(s) found in {args.tsv}:')
        for m, c in sorted(counts.items()):
            known_name = {0x70: 'outgoing command', 0x73: 'state report', 0x75: 'meter report'}.get(m, 'UNKNOWN -- not in profile yet!')
            print(f'  0x{m:02x}: {c:>6} reports  ({known_name})')
        print()

        total_transitions = 0
        for m in sorted(by_magic):
            label = f'[0x{m:02x}] '
            total_transitions += scan_one_magic(by_magic[m], m, known, label=label)

        if total_transitions == 0:
            print('No byte changes found in ANY magic across the whole file (outside --known-offset). '
                  'Either the action you were testing never actually got sent to the device during this '
                  'capture window, or it truly has no effect on any polled report (could be host-side-only, '
                  'e.g. a setting the Launcher keeps for itself and never syncs down).')
        else:
            print(f'note: {total_transitions} total transition(s) found across all magics -- if you only '
                  f'made ONE change, match the timestamp against when you actually acted, and note which '
                  f'magic it showed up under (that tells you which report type to add to the profile).')
        return

    records = list(read_records(args.tsv, args.magic))
    if not records:
        sys.exit(f'No reports with first byte 0x{args.magic:02x} found in {args.tsv}.\n'
                  f'Most likely cause: neither usbhid.data nor usb.capdata had content on '
                  f'any line -- re-check the tshark command included BOTH '
                  f'"-e usbhid.data -e usb.capdata" (HID interrupt transfers populate '
                  f'usbhid.data, not usb.capdata). Otherwise, check --magic matches the '
                  f'report type you want (state=0x73, meter=0x75) -- or try --all-magics '
                  f'if you are not sure which report type to look at.')

    print(f'{len(records)} reports with magic 0x{args.magic:02x} loaded from {args.tsv}\n')

    transitions = scan_one_magic(records, args.magic, known)

    if transitions == 0:
        print('No byte changes found across the whole file (outside --known-offset). '
              'Either the action never reached this report type, or nothing you did '
              'actually touched a byte in it -- double check --magic and the capture itself, '
              'or try --all-magics to check every report type at once.')
    elif transitions > 1:
        print(f'note: {transitions} separate transitions found -- if you only made ONE change, '
              f'the others are likely something else moving in the background '
              f'(a UI ramp/animation, an unrelated control, meter bleed, etc). '
              f'Match the timestamp against when you actually acted.')


if __name__ == '__main__':
    main()
