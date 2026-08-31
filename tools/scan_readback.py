#!/usr/bin/env python3
"""
Scan any capture (USBPcap / Darwin-XHC / usbmon pcapng) for the
`0x74` request / `0x75` response readback protocol -- see PROTOCOL.md §4a.

Pulls every HID payload, classifies by (magic, byte1, category, index),
and prints the distinct non-empty readback responses. Handy for re-reading
old INIT captures now that we know what the frames are.

  python3 tools/scan_readback.py "captures/raw pcapng captures/AntelopeINIT.pcapng"
  python3 tools/scan_readback.py captures/macos-captures/macos-antelopeINIT-poweron.pcapng
"""
import collections
import re
import subprocess
import sys

if len(sys.argv) != 2:
    sys.exit(__doc__)
F = sys.argv[1]

# category 0x01 embeds the device serial -- blank everything after the name
SERIAL_CATS = {0x01}


def payloads():
    for field in ("usbhid.data", "usb.capdata"):
        r = subprocess.run(["tshark", "-r", F, "-Y", field, "-T", "fields",
                            "-e", field], capture_output=True, text=True)
        got = [bytes.fromhex(l.strip().replace(":", ""))
               for l in r.stdout.splitlines()
               if len(l.strip().replace(":", "")) >= 32]
        if got:
            return got, field
    # Darwin XHC: raw frames, strip the 40-byte pseudo-header
    r = subprocess.run(["tshark", "-r", F, "-x"], capture_output=True, text=True)
    frames, cur = [], []
    for line in r.stdout.splitlines():
        m = re.match(r'^([0-9a-f]{4})  ((?:[0-9a-f]{2} )+)', line)
        if not m:
            continue
        if int(m.group(1), 16) == 0:
            if cur:
                frames.append(b"".join(cur))
            cur = [bytes.fromhex(m.group(2).replace(" ", ""))]
        else:
            cur.append(bytes.fromhex(m.group(2).replace(" ", "")))
    if cur:
        frames.append(b"".join(cur))
    got = [fr[40:360] for fr in frames if len(fr) >= 360]
    return got, "raw -x (Darwin XHC header stripped)"


pl, src = payloads()
print(f"{F}\n  {len(pl)} payloads via {src}")

magics = collections.Counter()
reqs = collections.Counter()
resp = collections.OrderedDict()
for p in pl:
    if len(p) < 16:
        continue
    magics[p[0]] += 1
    if p[0] == 0x74 and p[4] == 0x10:
        reqs[p[8]] += 1
    if p[0] == 0x75 and p[1] == 0x00:
        body = p[16:].rstrip(b"\x00")
        if body and (p[8], p[12]) not in resp:
            resp[(p[8], p[12])] = body

print("  payload magics:", {hex(k): v for k, v in magics.most_common()})
print("  0x74 requests by category:", {hex(k): v for k, v in sorted(reqs.items())})
print(f"  distinct non-empty 0x75/@1=0x00 responses: {len(resp)}")
for (cat, idx), body in resp.items():
    if cat in SERIAL_CATS:
        body = body[:16] + b"\x00" * (len(body) - 16)
    print(f"    cat={cat:#04x} idx={idx:<3} {len(body):3d}B  {body[:72].hex()}")
