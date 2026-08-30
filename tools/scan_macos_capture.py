#!/usr/bin/env python3
"""
Scan a native-macOS (Darwin "XHC") pcapng of the Antelope vendor HID
interface. The macOS capture format is NOT the USBPcap TSV that
scan_capture.py expects -- tshark leaves usbhid.data / usb.capdata empty,
so this reads the raw frames instead.

Layout: each vendor HID report = 40-byte Darwin pseudo-header + 320-byte
payload (frame.len == 360). payload[0] = magic (0x70 out / 0x73 0x74 0x75
in). Header byte 30 = endpoint (0x01 OUT host->dev, 0x82 IN dev->host);
VID/PID at header bytes 36-39. tshark's usb.src/usb.dst direction labels
are unreliable here -- outgoing frames are identified by magic 0x70.

Usage:
  tools/scan_macos_capture.py CAP.pcapng                 # outgoing cmds + 0x73 transitions
  tools/scan_macos_capture.py CAP.pcapng --magic 74      # dump one magic
  tools/scan_macos_capture.py CAP.pcapng --diff OTHER.pcapng   # final-state diff (per magic)

Needs tshark on PATH.
"""
import argparse, json, subprocess, sys
from collections import Counter


def load(path):
    out = subprocess.run(
        ["tshark", "-r", path, "-Y", "frame.len==360", "-T", "json", "-x"],
        capture_output=True, text=True, check=True).stdout
    rows = []
    for p in json.loads(out):
        L = p["_source"]["layers"]
        b = bytes.fromhex(L["frame_raw"][0])
        hdr, payload = b[:40], b[40:]
        magic = payload[0]
        # magic is the reliable discriminator: 0x70 = host->device command,
        # 0x73/0x74/0x75 = device->host report. Header byte 30 (endpoint) is
        # not consistent enough on Darwin captures (0x74 rides endpoint 1).
        direction = "OUT" if magic == 0x70 else "IN"
        rows.append({
            "n": int(L["frame"]["frame.number"]),
            "t": float(L["frame"]["frame.time_relative"]),
            "dir": direction,
            "magic": magic,
            "payload": payload,
        })
    return rows


def summary(rows, path):
    c = Counter((r["dir"], f"{r['magic']:02x}") for r in rows)
    print(f"# {path}  ({len(rows)} payloads)")
    for (d, m), v in sorted(c.items()):
        print(f"#   {d:4} magic {m}  x{v}")
    print()


def show_outgoing(rows):
    print("=== OUTGOING (magic 0x70) ===")
    for r in rows:
        if r["magic"] != 0x70:
            continue
        p = r["payload"]
        print(f"{r['n']:>6} t={r['t']:8.3f}  op={p[4]:02x}  "
              f"p16={p[16]:02x} p17={p[17]:02x} p18={p[18]:02x} "
              f"p19={p[19]:02x} p20={p[20]:02x}  | {p[:32].hex()}")


def show_transitions(rows, magic):
    print(f"\n=== magic {magic:02x} distinct-state transitions ===")
    prev = None
    for r in rows:
        if r["magic"] != magic:
            continue
        p = r["payload"]
        if prev is None:
            print(f"{r['n']:>6} t={r['t']:8.3f}  (initial)")
        else:
            d = [(i, prev[i], p[i]) for i in range(len(p)) if prev[i] != p[i]]
            if d:
                s = " ".join(f"{i}:{a:02x}->{b:02x}" for i, a, b in d[:40])
                print(f"{r['n']:>6} t={r['t']:8.3f}  {len(d)}B: {s}")
        prev = p


def last_distinct(rows, magic):
    out = None
    for r in rows:
        if r["magic"] == magic:
            out = r["payload"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--magic", type=lambda x: int(x, 16), default=None)
    ap.add_argument("--diff", metavar="OTHER.pcapng", default=None)
    args = ap.parse_args()

    rows = load(args.capture)
    summary(rows, args.capture)

    if args.diff:
        other = load(args.diff)
        for m in sorted({r["magic"] for r in rows} | {r["magic"] for r in other}):
            a, b = last_distinct(rows, m), last_distinct(other, m)
            if a is None or b is None:
                print(f"magic {m:02x}: only in one capture")
                continue
            d = [(i, a[i], b[i]) for i in range(min(len(a), len(b))) if a[i] != b[i]]
            print(f"magic {m:02x}: final-state diff {len(d)} bytes")
            for i, x, y in d:
                print(f"  off {i:3} ({i:#04x}): {x:02x} vs {y:02x}")
        return

    if args.magic is not None:
        show_transitions(rows, args.magic)
        return

    show_outgoing(rows)
    show_transitions(rows, 0x73)


if __name__ == "__main__":
    main()
