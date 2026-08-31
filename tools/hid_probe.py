#!/usr/bin/env python3
"""
Probe the Antelope HID interface for a device-side readback path.

Every USB capture we have (connect, preset-load, per-control) shows the
device sending only 0x73 / 0x74 / 0x75 interrupt reports on EP 0x82 --
none of which carry routing / mixer / AuraVerb state. The write opcodes
(0x53 / 0x17 / 0x1d) have no matching interrupt readback.

The one USB path a Wireshark/USBPcap capture can miss is a HID **Feature
report** (or a GET_REPORT on the Input report), which the OS/Launcher
would pull over the control pipe (EP0). This tool asks the hidraw node
directly:

  1. dump + parse the HID report descriptor  -> does it declare a Feature
     report (or multiple report IDs) at all?
  2. HIDIOCGRDESCSIZE / HIDIOCGRDESC             (report descriptor)
  3. for every report ID it finds (and id 0), try HIDIOCGFEATURE and a
     blocking read, and dump whatever comes back.

Run it on the machine the device is plugged into:

  python3 tools/hid_probe.py --profile profiles/orion_studio_3.json
  # add --set-route-first  to change a route via the CLI first, so you can
  # tell whether a feature report actually reflects current routing.

Read-only except with --set-route-first. Needs read access to the hidraw
node (sudo, or the udev rule from the README).
"""
import argparse
import array
import fcntl
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from antelope import protocol as proto
from antelope.transport import find_hidraw


def _ioc(direction, type_, nr, size):
    return (direction << 30) | (size << 16) | (ord(type_) << 8) | nr


IOC_READ, IOC_WRITE = 2, 1
HIDIOCGRDESCSIZE = _ioc(IOC_READ, 'H', 0x01, 4)
HIDIOCGRDESC = _ioc(IOC_READ, 'H', 0x02, 4 + 4096)


def hidiocgfeature(size):
    return _ioc(IOC_READ | IOC_WRITE, 'H', 0x07, size)


def hidiocginput(size):
    return _ioc(IOC_READ | IOC_WRITE, 'H', 0x0A, size)


def get_report_descriptor(fd):
    buf = array.array('B', b'\x00' * 4)
    fcntl.ioctl(fd, HIDIOCGRDESCSIZE, buf, True)
    size = int.from_bytes(buf.tobytes(), 'little')
    desc = array.array('B', size.to_bytes(4, 'little') + b'\x00' * 4096)
    fcntl.ioctl(fd, HIDIOCGRDESC, desc, True)
    return bytes(desc[4:4 + size])


ITEM_TAGS = {
    0x80: 'Input', 0x90: 'Output', 0xB0: 'Feature',
    0xA0: 'Collection', 0xC0: 'End Collection',
    0x84: 'Report ID', 0x74: 'Report Size', 0x94: 'Report Count',
    0x04: 'Usage Page', 0x08: 'Usage',
}


def parse_desc(desc):
    """Minimal walk: list every Main item, the current Report ID, and the
    running Report Size/Count, so we can see Input vs Output vs Feature."""
    i = 0
    report_id = 0
    size = count = None
    items = []
    ids = set()
    while i < len(desc):
        b = desc[i]
        if b == 0xFE:  # long item
            n = desc[i + 1]
            i += 3 + n
            continue
        tag = b & 0xFC
        blen = {0: 0, 1: 1, 2: 2, 3: 4}[b & 0x03]
        data = int.from_bytes(desc[i + 1:i + 1 + blen], 'little') if blen else None
        name = ITEM_TAGS.get(tag, f'item {b:#04x}')
        if tag == 0x84:
            report_id = data or 0
            ids.add(report_id)
        elif tag == 0x74:
            size = data
        elif tag == 0x94:
            count = data
        elif tag in (0x80, 0x90, 0xB0):
            total_bits = (size or 0) * (count or 0)
            items.append((name, report_id, size, count, total_bits, data))
        i += 1 + blen
    return items, (ids or {0})


def try_read(fd, ioctl_fn, label, report_id, length):
    buf = array.array('B', bytes([report_id]) + b'\x00' * (length - 1))
    try:
        n = fcntl.ioctl(fd, ioctl_fn(length), buf, True)
    except OSError as e:
        print(f"  {label} id={report_id:<3} len={length:<4} -> errno {e.errno} ({e.strerror})")
        return
    out = bytes(buf[:n if n > 0 else length])
    nz = sum(1 for x in out if x)
    print(f"  {label} id={report_id:<3} len={length:<4} -> {n} bytes, {nz} nonzero")
    print(f"    {out.hex()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', required=True)
    ap.add_argument('--set-route-first', metavar='"DEST CH SRC"',
                    help='run `route ...` via cli.py before probing, to see if a '
                         'feature report tracks routing')
    args = ap.parse_args()

    profile = proto.load_profile(args.profile)
    dev = profile['device']
    vid = int(dev['vid'], 16) if isinstance(dev['vid'], str) else dev['vid']
    pid = int(dev['pid'], 16) if isinstance(dev['pid'], str) else dev['pid']
    node = find_hidraw(vid, pid)
    rsize = profile['transport']['report_size']
    print(f"hidraw node: {node}   report_size: {rsize}")

    if args.set_route_first:
        import subprocess
        cmd = [sys.executable, '-m', 'antelope.cli', '--profile', args.profile,
               'route'] + args.set_route_first.split()
        print(f"\n$ {' '.join(cmd)}")
        subprocess.run(cmd, check=False)

    fd = os.open(node, os.O_RDWR)
    try:
        desc = get_report_descriptor(fd)
        print(f"\n=== HID report descriptor ({len(desc)} bytes) ===")
        print(desc.hex())
        items, ids = parse_desc(desc)
        print("\nMain items (name, reportID, size, count, total_bits):")
        for name, rid, size, count, bits, _ in items:
            print(f"  {name:<8} id={rid:<3} size={size} count={count} -> {bits} bits "
                  f"({bits // 8} bytes)")
        has_feature = any(n == 'Feature' for n, *_ in items)
        print(f"\nFeature report declared: {'YES' if has_feature else 'no'}")
        print(f"report IDs seen: {sorted(ids)}")

        print("\n=== GET_FEATURE attempts ===")
        for rid in sorted(ids):
            for length in (rsize, 64, 256, 512):
                try_read(fd, hidiocgfeature, 'FEATURE', rid, length)

        print("\n=== GET_REPORT(Input) attempts ===")
        for rid in sorted(ids):
            try_read(fd, hidiocginput, 'INPUT  ', rid, rsize)
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
