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
type if needed.
"""
import argparse
import sys


def parse_capdata(hexstr: str) -> bytes:
    """usb.capdata from `-T fields` is colon-separated hex ('70:00:00:...')."""
    hexstr = hexstr.strip()
    if not hexstr:
        return b''
    if ':' in hexstr:
        return bytes(int(b, 16) for b in hexstr.split(':') if b)
    # some tshark versions/fields come back as one contiguous hex string
    return bytes.fromhex(hexstr)


def read_records(path: str, magic: int):
    """Yields (frame_number, time_relative, bytes) for reports whose first byte
    matches `magic`, in file order (which is capture order). Each input line is
    frame.number, frame.time_relative, usbhid.data, usb.capdata (tab-separated) --
    HID interrupt transfers populate usbhid.data; usb.capdata is only used when no
    class-specific dissector (like HID) claims the payload, so it's typically empty
    here -- we take whichever of the two columns is non-empty."""
    with open(path) as f:
        for line_no, line in enumerate(f, 1):
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
            if not data or data[0] != magic:
                continue
            yield frame_no, t, data


def diff_bytes(before: bytes, after: bytes):
    n = min(len(before), len(after))
    return [(i, before[i], after[i]) for i in range(n) if before[i] != after[i]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tsv', help='output of tshark -T fields -e frame.number -e frame.time_relative -e usb.capdata')
    ap.add_argument('--magic', type=lambda x: int(x, 0), default=0x73,
                     help='only diff reports whose first byte equals this (default 0x73, the state report)')
    ap.add_argument('--known-offset', type=int, action='append', default=[],
                     help='offset(s) already explained by other params, to suppress from output (repeatable)')
    args = ap.parse_args()

    known = set(args.known_offset)
    records = list(read_records(args.tsv, args.magic))
    if not records:
        sys.exit(f'No reports with first byte 0x{args.magic:02x} found in {args.tsv}.\n'
                  f'Most likely cause: neither usbhid.data nor usb.capdata had content on '
                  f'any line -- re-check the tshark command included BOTH '
                  f'"-e usbhid.data -e usb.capdata" (HID interrupt transfers populate '
                  f'usbhid.data, not usb.capdata). Otherwise, check --magic matches the '
                  f'report type you want (state=0x73, meter=0x75).')

    print(f'{len(records)} reports with magic 0x{args.magic:02x} loaded from {args.tsv}\n')

    transitions = 0
    prev_frame, prev_t, prev_data = records[0]
    for frame_no, t, data in records[1:]:
        changes = diff_bytes(prev_data, data)
        unexplained = [c for c in changes if c[0] not in known]
        if unexplained:
            transitions += 1
            print(f'frame {prev_frame} (t={prev_t}) -> frame {frame_no} (t={t}):')
            for off, old, new in unexplained:
                print(f'    offset {off:>3} (0x{off:02x}):  0x{old:02x} -> 0x{new:02x}  '
                      f'(signed: {old - 256 if old > 127 else old} -> {new - 256 if new > 127 else new})')
            print()
        prev_frame, prev_t, prev_data = frame_no, t, data

    if transitions == 0:
        print('No byte changes found across the whole file (outside --known-offset). '
              'Either the action never reached this report type, or nothing you did '
              'actually touched a byte in it -- double check --magic and the capture itself.')
    elif transitions > 1:
        print(f'note: {transitions} separate transitions found -- if you only made ONE change, '
              f'the others are likely something else moving in the background '
              f'(a UI ramp/animation, an unrelated control, meter bleed, etc). '
              f'Match the timestamp against when you actually acted.')


if __name__ == '__main__':
    main()
