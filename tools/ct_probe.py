#!/usr/bin/env python3
"""
Focused EP0 control-transfer probe (phase 2b): detach the kernel HID driver
from interface 3, then run control-IN transfers with FULL error reporting so
we can tell a device STALL (device has no such request) from an access /
busy error (host-side problem). Re-attaches the kernel driver on any exit
(normal, exception, or SIGTERM/SIGINT) so hidraw keeps working.

Needs write access to the usbfs node: run with sudo, or (transient)
  sudo chmod 666 /dev/bus/usb/<BUS>/<DEV>
The node reverts on replug / reboot; nothing to undo.

  python3 tools/ct_probe.py            full sweep
"""
import errno
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from antelope import protocol as proto

import usb.core
import usb.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = open(os.path.join(ROOT, "tools", "ct_probe_out.txt"), "w")


def out(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def hexdump(b, width=32):
    for i in range(0, len(b), width):
        out(f"      [{i:3d}] {b[i:i + width].hex()}")


profile = proto.load_profile(os.path.join(ROOT, "profiles/orion_studio_sc.json"))
dv = profile["device"]
VID = int(dv["vid"], 16) if isinstance(dv["vid"], str) else dv["vid"]
PID = int(dv["pid"], 16) if isinstance(dv["pid"], str) else dv["pid"]
RSIZE = profile["transport"]["report_size"]

dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    sys.exit("device not found")

detached = []


def cleanup(*_):
    try:
        usb.util.dispose_resources(dev)
    except Exception:
        pass
    for n in detached:
        try:
            dev.attach_kernel_driver(n)
            out(f"re-attached kernel driver to iface {n}")
        except Exception as e:
            out(f"!! could not re-attach iface {n}: {e} -- `usbreset` or replug the device")


signal.signal(signal.SIGTERM, lambda *_: (cleanup(), sys.exit(143)))
signal.signal(signal.SIGINT, lambda *_: (cleanup(), sys.exit(130)))


def ct(bmRT, bR, wV, wI, length, timeout=120):
    try:
        ret = dev.ctrl_transfer(bmRT, bR, wV, wI, length, timeout=timeout)
    except usb.core.USBError as e:
        return ({errno.EPIPE: "STALL", errno.EACCES: "EACCES", errno.EBUSY: "EBUSY",
                 errno.ETIMEDOUT: "timeout", errno.ENODEV: "ENODEV",
                 None: "err?"}.get(e.errno, f"errno{e.errno}"), None)
    return ("OK", bytes(ret))


try:
    for cfg in dev:
        for intf in cfg:
            n = intf.bInterfaceNumber
            try:
                if dev.is_kernel_driver_active(n):
                    dev.detach_kernel_driver(n)
                    detached.append(n)
            except Exception as e:
                out(f"  (detach iface {n}: {e})")
    out(f"detached kernel driver from: {detached}  (euid={os.geteuid()})")

    out("\n-- sanity: standard GET_DESCRIPTOR (proves control-IN works) --")
    for tag, (bmRT, bR, wV, wI) in {
        "device desc":         (0x80, 0x06, 0x0100, 0),
        "config desc(9)":      (0x80, 0x06, 0x0200, 0),
        "config desc(full)":   (0x80, 0x06, 0x0200, 0),
        "string langid(0)":    (0x80, 0x06, 0x0300, 0),
        "string 1 (mfr)":      (0x80, 0x06, 0x0301, 0x0409),
        "string 2 (product)":  (0x80, 0x06, 0x0302, 0x0409),
        "HID report desc if3": (0x81, 0x06, 0x2200, 3),
    }.items():
        kind, b = ct(bmRT, bR, wV, wI, 255, timeout=500)
        out(f"  {tag:<22} -> {kind}" + (f"  {len(b)}B" if b is not None else ""))
        if b:
            hexdump(b[:96])

    out("\n-- HID-class GET_REPORT on iface 3 (driver detached) --")
    for rtype, rn in ((1, "Input"), (3, "Feature")):
        for rid in range(4):
            kind, b = ct(0xA1, 0x01, (rtype << 8) | rid, 3, RSIZE, timeout=500)
            out(f"  {rn} id{rid} -> {kind}" +
                (f"  {len(b)}B nz={sum(1 for x in b if x)}" if b is not None else ""))
            if b and any(b):
                hexdump(b)

    out("\n-- vendor control-IN sweep bRequest 0x00..0xff --")
    non_stall = []
    for bmRT, tgt, wI in ((0xC0, "dev", 0), (0xC1, "iface3", 3),
                          (0xA1, "if3-class", 3), (0x80, "dev-std", 0),
                          (0x81, "iface3-std", 3)):
        summary = {}
        for bR in range(256):
            kind, b = ct(bmRT, bR, 0, wI, RSIZE, timeout=80)
            summary[kind] = summary.get(kind, 0) + 1
            if kind != "STALL" and kind != "timeout":
                non_stall.append((bmRT, tgt, wI, bR, kind, b))
        out(f"  [{tgt}] {summary}")

    out("\n-- every non-STALL / non-timeout response in detail --")
    for bmRT, tgt, wI, bR, kind, b in non_stall:
        n = len(b) if b is not None else -1
        nz = sum(1 for x in (b or b"") if x)
        out(f"  {tgt} bmRT={bmRT:#04x} bR={bR:#04x} -> {kind}  len={n} nz={nz}"
            + (f"  {b.hex()}" if b else ""))

    out("\n-- wValue/wLength sweep on each non-STALL vendor request --")
    for bmRT, tgt, wI, bR, kind, b in non_stall:
        if bmRT not in (0xC0, 0xC1):
            continue
        for wV in (0x0000, 0x0001, 0x0100, 0x00d3, 0xd300, 0x0053):
            for wL in (8, 64, RSIZE):
                k2, b2 = ct(bmRT, bR, wV, wI, wL, timeout=120)
                if k2 == "OK" and b2 and any(b2):
                    out(f"  *** {tgt} bR={bR:#04x} wV={wV:#06x} wL={wL} -> {len(b2)}B ***")
                    hexdump(b2)
finally:
    cleanup()
    out("\n[done] -> tools/ct_probe_out.txt")
