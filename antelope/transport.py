"""
Generic HID transport for Antelope devices.

Nothing device-specific lives here -- VID/PID/report size all come from
the profile dict loaded by antelope.protocol.load_profile(). This is what
lets a second device (a different Antelope interface) reuse this file
unchanged; only its JSON profile differs.
"""
import glob
import os
import select
import sys
import time


def find_hidraw(vid: int, pid: int) -> str:
    for path in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        uevent_paths = [
            os.path.join(path, 'device', 'uevent'),
            os.path.join(path, 'uevent'),
        ]
        for upath in uevent_paths:
            if not os.path.exists(upath):
                continue
            try:
                content = open(upath).read()
            except Exception:
                continue
            for line in content.splitlines():
                if line.startswith('HID_ID='):
                    parts = line.split('=')[1].split(':')
                    if len(parts) == 3:
                        found_vid = int(parts[1], 16)
                        found_pid = int(parts[2], 16)
                        if found_vid == vid and found_pid == pid:
                            return f'/dev/{os.path.basename(path)}'
                elif line.startswith('MODALIAS='):
                    val = line.upper()
                    if f'V{vid:08X}' in val and f'P{pid:08X}' in val:
                        return f'/dev/{os.path.basename(path)}'

    sys.exit(
        f'HID node not found for VID={hex(vid)} PID={hex(pid)}.\n'
        'Check USB connection or list nodes with: ls /dev/hidraw*'
    )


class HidTransport:
    """Thin wrapper around a hidraw node: blocking-ish read with timeout, plain write."""

    def __init__(self, path: str, report_size: int):
        self.path = path
        self.report_size = report_size

    def read_reports(self, magic: int, timeout: float = 3.0):
        """Generator yielding raw reports whose first byte matches `magic`."""
        try:
            fd = os.open(self.path, os.O_RDONLY)
        except PermissionError:
            sys.exit(f'Permission denied reading {self.path}. Try running with sudo.')

        end = time.time() + timeout
        try:
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.2)
                if r:
                    data = os.read(fd, self.report_size)
                    if data and data[0] == magic:
                        yield data
        finally:
            os.close(fd)

    def read_one(self, magic: int, timeout: float = 3.0):
        for data in self.read_reports(magic, timeout):
            return data
        return None

    def query(self, request: bytes, match, timeout: float = 1.0, retries: int = 2):
        """Write a readback request, then read reports until `match(report)`
        is truthy or `timeout` elapses; return that report or None.

        The device free-runs state/meter reports on the same IN endpoint, so
        `match` must identify the specific response (see
        protocol.is_readback_response). A write can fail with ETIMEDOUT /
        EPIPE -- we reopen and retry.

        NOTE: if every retry fails AND the free-running 0x73 stream has also
        stopped, the device is not busy, it has CRASHED -- almost certainly a
        readback query with an out-of-range index (see
        protocol.check_readback_index and frame.readback.hazard). Only a
        physical power cycle recovers it; do NOT call dev.reset() on a hung
        unit, that knocks it off USB entirely.
        """
        if len(request) != self.report_size:
            raise ValueError(f'request must be exactly {self.report_size} bytes')
        for attempt in range(retries + 1):
            try:
                fd = os.open(self.path, os.O_RDWR)
            except PermissionError:
                sys.exit(f'Permission denied on {self.path}. Try sudo or a udev rule.')
            try:
                # drain anything already queued so we don't match a stale frame
                while select.select([fd], [], [], 0)[0]:
                    os.read(fd, self.report_size)
                try:
                    os.write(fd, request)
                except OSError:
                    if attempt < retries:
                        continue
                    raise
                end = time.time() + timeout
                while time.time() < end:
                    r, _, _ = select.select([fd], [], [], 0.05)
                    if not r:
                        continue
                    data = os.read(fd, self.report_size)
                    if data and match(data):
                        return data
                return None
            finally:
                os.close(fd)
        return None

    def write(self, payload: bytes):
        if len(payload) != self.report_size:
            raise ValueError(f'payload must be exactly {self.report_size} bytes, got {len(payload)}')
        try:
            fd = os.open(self.path, os.O_WRONLY)
        except PermissionError:
            sys.exit(f'Permission denied writing {self.path}. Try running with sudo.')
        try:
            n = 0
            while n < len(payload):
                w = os.write(fd, payload[n:])
                if w <= 0:
                    sys.exit('short/failed write to HID device')
                n += w
        finally:
            os.close(fd)
