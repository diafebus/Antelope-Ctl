#!/usr/bin/env python3
"""
Hunt for a device-side readback path on an Antelope HID interface.

Companion to tools/hid_probe.py. hid_probe checks the HID report-descriptor
+ HID-class GET_REPORT (both dead ends on the Orion Studio III). This tool
covers the paths a HID-interrupt capture (USBPcap / Darwin XHC) physically
cannot show:

  phase 1  passive   -- catalogue every interrupt-IN report, full-dump one
                        of each magic, and mark which bytes ever move over
                        many frames. Confirms whether routing / mixer /
                        AuraVerb state is anywhere in 0x73. No root, no write.

  phase 2  --ct      -- every EP0 control-IN transfer: string descriptors,
                        HID-class GET_REPORT via the control pipe, and a
                        full vendor bRequest 0x00..0xff sweep (device- and
                        interface-targeted). READ-ONLY. Needs write access
                        to the usbfs node -> run with sudo, or install a
                        udev rule granting the device to your user.

  phase 3  --poke    -- write a few candidate "query" frames to EP-OUT and
                        watch EP-IN for a reply the device does not
                        volunteer. Safe subset only: the connect-handshake
                        frame SET_PARAM(0x49,ch1,0) and bare unknown
                        opcodes 0x73/0x74/0x75. Never touches a SET opcode
                        (0x12/0x13/0x14/0x17/0x1d/0x53). Still a write.

Usage:
  python3 tools/readback_probe.py --profile profiles/orion_studio_sc.json
  sudo python3 tools/readback_probe.py --profile profiles/orion_studio_sc.json --ct
  python3 tools/readback_probe.py --profile profiles/orion_studio_sc.json --poke

Every run also writes its full output next to this file as
readback_probe_out.txt so it can be inspected after the fact.
"""
import argparse
import collections
import os
import select
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from antelope import protocol as proto
from antelope.transport import find_hidraw

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "readback_probe_out.txt")
_LOG = open(OUT_PATH, "w")

# known free-running meter-jitter offsets in the 0x73 report (noise floor),
# so phase 3 can ignore them when diffing.
METER_JITTER = {157, 158, 159, 161, 162, 166, 169, 170, 171, 173, 174,
                221, 222, 223, 225, 226, 230, 235}


def out(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    _LOG.write(s + "\n")
    _LOG.flush()


def hexdump(b, width=32):
    for i in range(0, len(b), width):
        out(f"    [{i:3d}] {b[i:i + width].hex()}")


def _median_frame(frames):
    frames = [f for f in frames if f]
    if not frames:
        return None
    n = min(map(len, frames))
    return bytes(sorted(f[i] for f in frames)[len(frames) // 2] for i in range(n))


def _listen(fd, rsize, seconds, note):
    got = collections.defaultdict(list)
    end = time.time() + seconds
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            data = os.read(fd, rsize)
            if data:
                got[data[0]].append(data if len(got[data[0]]) < 40 else None)
    out(f"  [{note}] { {hex(m): len(v) for m, v in got.items()} }")
    return got


def phase1(node, rsize, seconds=6.0):
    out(f"\n=== phase 1: passive interrupt-IN ({seconds}s) {node} ===")
    fd = os.open(node, os.O_RDONLY)
    samples = collections.defaultdict(list)
    counts = collections.Counter()
    end = time.time() + seconds
    try:
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.2)
            if not r:
                continue
            data = os.read(fd, rsize)
            if not data:
                continue
            counts[data[0]] += 1
            if len(samples[data[0]]) < 80:
                samples[data[0]].append(data)
    finally:
        os.close(fd)
    out(f"magics: {dict(counts)}")
    for m, frames in sorted(samples.items()):
        out(f"\n--- magic {m:#04x} x{counts[m]} ---")
        hexdump(frames[0])
        n = min(map(len, frames))
        moving = [i for i in range(n)
                  if any(f[i] != frames[0][i] for f in frames)]
        last_nz = max((i for i in range(n) if frames[0][i]), default=-1)
        out(f"  moving offsets ({len(moving)}): {moving}")
        out(f"  last nonzero byte: {last_nz}")
    return samples


def phase2(vid, pid, rsize):
    out("\n=== phase 2: EP0 control-IN transfers ===")
    import usb.core
    import usb.util
    dev = usb.core.find(idVendor=vid, idProduct=pid)
    if dev is None:
        out("  device not found via libusb")
        return []
    hits = []

    out("\n -- string descriptors --")
    for idx in range(1, 6):
        try:
            out(f"  string[{idx}] = {usb.util.get_string(dev, idx)!r}")
        except Exception as e:
            out(f"  string[{idx}] -> {e}")

    out("\n -- HID-class GET_REPORT via EP0 (bmRequestType 0xA1) --")
    for rtype, rn in ((1, "Input"), (3, "Feature")):
        for rid in range(0, 4):
            try:
                ret = dev.ctrl_transfer(0xA1, 0x01, (rtype << 8) | rid, 3,
                                        rsize, timeout=400)
                b = bytes(ret)
                out(f"  {rn} id{rid} -> {len(b)}B nz={sum(1 for x in b if x)}")
                if any(b):
                    hits.append((f"GET_REPORT {rn} id{rid}", b))
                    hexdump(b)
            except Exception as e:
                out(f"  {rn} id{rid} -> {e}")

    out("\n -- vendor bRequest sweep 0x00..0xff --")
    for bmRT, tgt in ((0xC0, "dev"), (0xC1, "if3"), (0xC2, "ep")):
        wI = 3 if bmRT == 0xC1 else (0x82 if bmRT == 0xC2 else 0)
        n_ok = 0
        for bR in range(256):
            try:
                ret = dev.ctrl_transfer(bmRT, bR, 0, wI, rsize, timeout=150)
            except Exception:
                continue
            n_ok += 1
            b = bytes(ret)
            out(f"  {tgt} bR={bR:#04x} -> {len(b)}B nz={sum(1 for x in b if x)}")
            if any(b):
                hits.append((f"{tgt} bR={bR:#04x}", b))
                hexdump(b)
        out(f"  [{tgt}] {n_ok}/256 returned without stall")

    out(f"\n=== phase 2 result: {len(hits)} non-empty response(s) ===")
    for tag, b in hits:
        out(f"  {tag}")
        hexdump(b)
    return hits


def _frame(rsize, opcode, param=None, ch=None, val=None):
    f = bytearray(rsize)
    f[0] = 0x70
    f[4] = opcode
    if param is not None:
        f[16] = param
    if ch is not None:
        f[17] = ch
    if val is not None:
        f[18] = val
    return bytes(f)


def phase3(node, rsize):
    out("\n=== phase 3: EP-OUT poke + EP-IN listen (writes to device) ===")
    fd = os.open(node, os.O_RDWR)
    try:
        base = _listen(fd, rsize, 2.0, "baseline")
        base_magics = set(base)
        base73 = _median_frame(base.get(0x73, []))
        pokes = [
            ("SET_PARAM(0x49,ch1,0)  [connect-handshake frame]",
             _frame(rsize, 0x13, 0x49, 1, 0)),
            ("bare opcode 0x74", _frame(rsize, 0x74)),
            ("bare opcode 0x73", _frame(rsize, 0x73)),
            ("bare opcode 0x75", _frame(rsize, 0x75)),
        ]
        for name, fr in pokes:
            out(f"\n--> POKE: {name}")
            os.write(fd, fr)
            got = _listen(fd, rsize, 2.5, "reply")
            new = set(got) - base_magics
            if new:
                out(f"  *** NEW MAGIC(S): {[hex(m) for m in new]} ***")
                for m in new:
                    for i, f in enumerate(got[m][:3]):
                        if f:
                            out(f"  magic {hex(m)} frame {i}:")
                            hexdump(f)
            now73 = _median_frame(got.get(0x73, []))
            if base73 and now73:
                diff = [(i, base73[i], now73[i])
                        for i in range(min(len(base73), len(now73)))
                        if base73[i] != now73[i] and i not in METER_JITTER]
                out(f"  0x73 non-meter deltas vs baseline: {diff or 'none'}")
    finally:
        os.close(fd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--ct", action="store_true", help="phase 2 (needs sudo)")
    ap.add_argument("--poke", action="store_true", help="phase 3 (writes)")
    ap.add_argument("--seconds", type=float, default=6.0)
    args = ap.parse_args()

    profile = proto.load_profile(args.profile)
    dev = profile["device"]
    vid = int(dev["vid"], 16) if isinstance(dev["vid"], str) else dev["vid"]
    pid = int(dev["pid"], 16) if isinstance(dev["pid"], str) else dev["pid"]
    rsize = profile["transport"]["report_size"]
    node = find_hidraw(vid, pid)

    out(f"python   = {sys.executable}")
    out(f"euid     = {os.geteuid()}")
    out(f"device   = {vid:#06x}:{pid:#06x}   hidraw = {node}   report_size = {rsize}")
    out(f"full log -> {OUT_PATH}")

    for name, fn, run in (
        ("phase1", lambda: phase1(node, rsize, args.seconds), True),
        ("phase2", lambda: phase2(vid, pid, rsize), args.ct),
        ("phase3", lambda: phase3(node, rsize), args.poke),
    ):
        if not run:
            continue
        try:
            fn()
        except Exception:
            out(f"\n!! {name} raised:\n{traceback.format_exc()}")

    out("\n[done]")


if __name__ == "__main__":
    main()
