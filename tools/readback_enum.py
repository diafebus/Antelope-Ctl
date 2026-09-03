#!/usr/bin/env python3
"""
Drive the Antelope in-band readback protocol and enumerate its categories.

Discovered from a usbmon capture of the Windows Launcher connecting
(CAPTURE E', 2026-08-31): the device answers a request/response protocol on
the SAME HID interrupt endpoints -- not a Feature report, not a control
transfer, which is why every earlier probe missed it.

  REQUEST  host->device, EP 0x01 OUT, 320 B:
    74 00 00 00 | 10 00 00 00 | <cat> 00 00 00 | <idx> 00 00 00 | 00...
  RESPONSE device->host, EP 0x82 IN, 320 B:
    75 00 00 00 | 40 01 00 00 | <cat> 00 00 00 | <idx> 00 00 00 | <data...>

Response magic is 0x75 but byte 1 = 0x00 (meter report is 0x75 / byte1 0x1f;
0x73 state report is the same family with magic 0x73). The device free-runs
0x73 + 0x75/1f on the same endpoint, so we filter on (magic, byte1, cat, idx).

!!! DANGER -- READ THIS BEFORE SWEEPING INDICES !!!

The firmware does NOT bounds-check the readback index. Query one index past a
category's record count and it hands back adjacent memory (wrong layout); go a
bit further and it faults. On 2026-08-31 `--cat 0x04 --max-idx 5` hard-crashed
the Orion Studio III -- front panel "CRITICAL ERROR! / Failure.c / L: 204 E: 0
/ BusFault_Handler" (a Cortex-M BusFault) -- and the unit needed a physical
power cycle. The tell-tale sequence is: in-range indices answer with a
consistent layout; the first over-range one answers with a DIFFERENT layout;
the next answers with NOTHING and the OUT endpoint goes dead.

NOTE: this supersedes the earlier note here blaming "hammering"/query rate for
the halted endpoint. That crash took ~10 slow queries. Rate was never the
trigger -- the out-of-range index was. Pacing is still polite, but it is not
the safety mechanism; the index bound is.

So by default this tool now sweeps ONLY indices the device itself declared, via
frame.readback.category_counts (derived from the 0x74 connect enumeration).
`--unsafe` lifts that, and is how you break the hardware.

Notes learned from the first run:
  * the device answers every IN-RANGE (cat, idx) -- one it has no record for
    just comes back empty. "has data" is the liveness signal, not "answered".
  * scalar categories (0x00 id, 0x01 name/serial, 0x02 ...) return the same
    record for every idx.
  * pace queries and reopen the node on write error.

Read-only: every frame sent is a read request, exactly what the Launcher
issues on connect.

  python3 tools/readback_enum.py --profile profiles/orion_studio_sc.json
  python3 tools/readback_enum.py --profile ... --cat 0x03
"""
import argparse
import os
import select
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from antelope import protocol as proto
from antelope.transport import find_hidraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "readback_enum_out.txt")
_LOG = open(OUT, "w")

# categories whose payload embeds the device serial -> redact in the log
_SERIAL_CATS = {0x01}


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    _LOG.write(s + "\n")
    _LOG.flush()


def q_frame(rsize, cat, idx):
    f = bytearray(rsize)
    f[0], f[4], f[8], f[12] = 0x74, 0x10, cat, idx
    return bytes(f)


class Link:
    def __init__(self, node, rsize):
        self.node, self.rsize = node, rsize
        self.fd = os.open(node, os.O_RDWR)

    def _reopen(self):
        try:
            os.close(self.fd)
        except OSError:
            pass
        time.sleep(0.3)
        self.fd = os.open(self.node, os.O_RDWR)

    def query(self, cat, idx, window=0.15):
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, self.rsize)
        for attempt in range(3):
            try:
                os.write(self.fd, q_frame(self.rsize, cat, idx))
                break
            except (TimeoutError, OSError):
                self._reopen()
        else:
            return None
        end = time.time() + window
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.02)
            if not r:
                continue
            p = os.read(self.fd, self.rsize)
            if len(p) >= 16 and p[0] == 0x75 and p[1] == 0x00 and p[8] == cat and p[12] == idx:
                return p[16:]
        return None


def redact(cat, body):
    if cat in _SERIAL_CATS:
        # keep the ascii name, blank the rest
        return body[:16] + b"\x00" * (len(body) - 16)
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--cat", type=lambda x: int(x, 0), default=None)
    ap.add_argument("--max-cat", type=lambda x: int(x, 0), default=0x2a)
    ap.add_argument("--max-idx", type=int, default=24,
                    help="upper index bound; still clamped to the category's "
                         "declared record count unless --unsafe")
    ap.add_argument("--unsafe", action="store_true",
                    help="sweep past a category's declared record count. THIS CAN "
                         "CRASH THE DEVICE (BusFault -> power cycle). See the "
                         "module docstring.")
    ap.add_argument("--miss-break", type=int, default=3)
    ap.add_argument("--pace", type=float, default=0.03)
    ap.add_argument("--rest-every", type=int, default=25)
    ap.add_argument("--rest", type=float, default=0.5)
    args = ap.parse_args()

    profile = proto.load_profile(args.profile)
    dev = profile["device"]
    vid = int(dev["vid"], 16) if isinstance(dev["vid"], str) else dev["vid"]
    pid = int(dev["pid"], 16) if isinstance(dev["pid"], str) else dev["pid"]
    rsize = profile["transport"]["report_size"]
    node = find_hidraw(vid, pid)
    log(f"node {node}  report_size {rsize}")
    link = Link(node, rsize)

    cats = [args.cat] if args.cat is not None else list(range(0, args.max_cat + 1))

    nq = [0]

    def paced_query(c, i):
        nq[0] += 1
        if nq[0] % args.rest_every == 0:
            time.sleep(args.rest)
        r = link.query(c, i)
        time.sleep(args.pace)
        return r

    if args.unsafe:
        log("!!! --unsafe: sweeping past declared record counts. An out-of-range "
            "index can BusFault the device and force a power cycle. !!!")

    for cat in cats:
        # HARD SAFETY BOUND: never query past what the device declared in its own
        # 0x74 connect enumeration. cat 0x04 idx 5 crashed the unit (see docstring).
        declared = proto.readback_category_count(profile, cat)
        hi = args.max_idx
        if declared is not None and not args.unsafe:
            hi = min(hi, declared - 1)
        if hi < 0:
            continue
        idx0 = paced_query(cat, 0)
        entries = []
        if idx0 is not None and idx0.rstrip(b"\x00"):
            entries.append((0, idx0.rstrip(b"\x00")))
            misses = 0
            prev = idx0
            for idx in range(1, hi + 1):
                body = paced_query(cat, idx)
                if body is None or not body.rstrip(b"\x00"):
                    misses += 1
                    if misses >= args.miss_break:
                        break
                    continue
                misses = 0
                if body == prev:            # scalar / single-record category
                    log(f"  cat {cat:#04x}: single-record (idx echoes) -- stopping")
                    break
                prev = body
                entries.append((idx, body.rstrip(b"\x00")))
        if not entries:
            continue
        log(f"\n=== category {cat:#04x} : {len(entries)} record(s) ===")
        for idx, nz in entries:
            nz = redact(cat, nz)
            log(f"  [{idx:2d}] {len(nz):3d}B  {nz.hex()}")

    log(f"\n[done] -> {OUT}")


if __name__ == "__main__":
    main()
