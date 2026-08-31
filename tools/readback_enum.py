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

Notes learned from the first run:
  * the device answers EVERY (cat, idx) -- an unknown one just comes back
    empty. "has data" is the liveness signal, not "answered".
  * scalar categories (0x00 id, 0x01 name/serial, 0x02 ...) return the same
    record for every idx.
  * hammering the OUT endpoint too fast eventually halts it (ETIMEDOUT on
    write) -- we pace and reopen on halt.

Read-only: every frame sent is a read request, exactly what the Launcher
issues on connect.

  python3 tools/readback_enum.py --profile profiles/orion_studio_3.json
  python3 tools/readback_enum.py --profile ... --cat 0x03 --max-idx 20
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
    ap.add_argument("--max-idx", type=int, default=24)
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

    for cat in cats:
        idx0 = paced_query(cat, 0)
        entries = []
        if idx0 is not None and idx0.rstrip(b"\x00"):
            entries.append((0, idx0.rstrip(b"\x00")))
            misses = 0
            prev = idx0
            for idx in range(1, args.max_idx + 1):
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
