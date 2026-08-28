#!/usr/bin/env python3
"""
Byte-diff helper for finding new params (master volume, routing, etc.)
from tshark captures, following the same capture -> correlate -> confirm
discipline used for the confirmed params.

Workflow for a new param, e.g. master volume:
  1. Start a capture (tshark -r ... -x, per the Phase 1 doc's method --
     the plain-text Wireshark export truncates past ~110 bytes, don't use it).
  2. In the official Launcher, change ONLY master volume (nothing else),
     note roughly when.
  3. Save the state report just before your action as before.hex, and the
     state report just after as after.hex (one hex-per-line or a raw dump --
     see --format below).
  4. Run: python3 capture_diff.py before.hex after.hex
     -> it prints every byte offset that changed and old/new values.
  5. Cross-check the changed offset(s) against action log timing. If only
     one or two offsets moved and it lines up with your action, that's
     your candidate offset/param_id -- add it to the profile JSON as
     "status": "unconfirmed" first, re-test deliberately with raw-set to
     confirm it moves ONLY on that param, then flip status to "confirmed".

This tool does no capturing itself -- it only diffs two byte sequences
you already captured from your own device traffic.
"""
import argparse
import sys


def parse_hex_dump(path: str) -> bytes:
    """Accepts either a single line of hex bytes ('70 00 00 ...' or '7000...')
    or a tshark -x style dump (offset + hex columns + ascii gutter)."""
    text = open(path).read().strip()
    lines = text.splitlines()

    # Single-line hex (space separated or contiguous)
    if len(lines) == 1:
        line = lines[0].replace('0x', '').strip()
        tokens = line.split()
        if all(len(t) == 2 for t in tokens):
            return bytes(int(t, 16) for t in tokens)
        # contiguous hex string
        hexonly = ''.join(ch for ch in line if ch in '0123456789abcdefABCDEF')
        return bytes.fromhex(hexonly)

    # tshark -x style: "0000  70 00 00 00 13 00 ...   p......."
    out = bytearray()
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        # drop leading offset column if present (hex or decimal-ish token followed by hex bytes)
        idx = 1 if len(parts[0]) <= 8 and all(c in '0123456789abcdefABCDEFx' for c in parts[0]) else 0
        for tok in parts[idx:]:
            if len(tok) == 2 and all(c in '0123456789abcdefABCDEF' for c in tok):
                out.append(int(tok, 16))
            else:
                break  # hit the ascii gutter, stop this line
    return bytes(out)


def diff(before: bytes, after: bytes):
    n = min(len(before), len(after))
    changes = []
    for i in range(n):
        if before[i] != after[i]:
            changes.append((i, before[i], after[i]))
    if len(before) != len(after):
        print(f'warning: length mismatch ({len(before)} vs {len(after)} bytes) -- '
              f'only comparing first {n}', file=sys.stderr)
    return changes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('before', help='hex dump captured just before the action')
    ap.add_argument('after', help='hex dump captured just after the action')
    ap.add_argument('--known-offset', type=int, action='append', default=[],
                     help='offset(s) already explained by other params, to suppress from output (repeatable)')
    args = ap.parse_args()

    before = parse_hex_dump(args.before)
    after = parse_hex_dump(args.after)
    changes = diff(before, after)

    known = set(args.known_offset)
    unexplained = [c for c in changes if c[0] not in known]

    print(f'{len(changes)} byte(s) changed total, {len(unexplained)} not in --known-offset list\n')
    for off, old, new in unexplained:
        marker = ''
        print(f'  offset {off:>3} (0x{off:02x}):  0x{old:02x} -> 0x{new:02x}  '
              f'(signed: {old - 256 if old > 127 else old} -> {new - 256 if new > 127 else new}){marker}')

    if not unexplained:
        print('  (nothing unexplained -- either no real change, or it is fully covered by --known-offset)')


if __name__ == '__main__':
    main()
