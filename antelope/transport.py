"""
Generic HID transport for Antelope devices.

Nothing device-specific lives here -- VID/PID/report size all come from
the profile dict loaded by antelope.protocol.load_profile(). This is what
lets a second device (a different Antelope interface) reuse this file
unchanged; only its JSON profile differs.
"""
import ctypes
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


def list_connected_hid() -> set:
    """{(vid, pid), ...} for every HID node this host exposes right now.

    Read-only and best-effort: no device is opened, and an empty set means
    "could not enumerate" (unsupported platform, no sysfs, no permission),
    not "nothing is plugged in". Callers use it to pick a profile from what
    is actually connected -- see webui/server.py.
    """
    if sys.platform == 'win32':
        try:
            return _list_windows_hid()
        except Exception:
            return set()

    found = set()
    for path in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        for upath in (os.path.join(path, 'device', 'uevent'),
                      os.path.join(path, 'uevent')):
            try:
                content = open(upath).read()
            except OSError:
                continue
            for line in content.splitlines():
                if line.startswith('HID_ID='):
                    parts = line.split('=', 1)[1].split(':')
                    if len(parts) == 3:
                        try:
                            found.add((int(parts[1], 16), int(parts[2], 16)))
                        except ValueError:
                            pass
            break   # the first uevent that exists describes this node
    return found


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


# ---------------------------------------------------------------------------
# Windows
#
# The vendor-defined collection sits on Microsoft's in-box HidUsb driver, so
# nothing needs replacing with WinUSB and nothing needs test signing. What gets
# in the way is an ordinary exclusive handle: while Antelope's service runs,
# CreateFileW on the collection fails with ERROR_SHARING_VIOLATION. Stop the
# service and the same call returns a read/write handle.
#
# Reports here carry a leading report-number byte that hidraw hides, so this
# class strips it on read and prepends it on write. Callers see exactly what
# they see on Linux: report_size bytes starting with the frame magic.

ERROR_SHARING_VIOLATION = 32


def _iter_windows_hid():
    """Yield (vid, pid) for each HID collection Windows can open. A collection
    held by another process (vendor service) can't be queried and is skipped --
    fine for enumeration; find_windows_hid() has the busy-vs-absent logic for
    the single-device open path."""
    W, GUID, IfaceData, Attributes = _win_structs()
    setup, hid, k32 = ctypes.windll.setupapi, ctypes.windll.hid, ctypes.windll.kernel32
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    devinfo = setup.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)
    index = 0
    try:
        while True:
            iface = IfaceData()
            iface.cbSize = ctypes.sizeof(iface)
            if not setup.SetupDiEnumDeviceInterfaces(
                    devinfo, None, ctypes.byref(guid), index, ctypes.byref(iface)):
                break
            index += 1
            need = W.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(
                devinfo, ctypes.byref(iface), None, 0, ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            ctypes.cast(buf, ctypes.POINTER(W.DWORD))[0] = (
                8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6)
            if not setup.SetupDiGetDeviceInterfaceDetailW(
                    devinfo, ctypes.byref(iface), buf, need, None, None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + ctypes.sizeof(W.DWORD))
            handle = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
            if handle == -1:
                continue
            attrs = Attributes()
            attrs.Size = ctypes.sizeof(attrs)
            ok = hid.HidD_GetAttributes(handle, ctypes.byref(attrs))
            k32.CloseHandle(handle)
            if ok:
                yield attrs.VendorID, attrs.ProductID
    finally:
        setup.SetupDiDestroyDeviceInfoList(devinfo)


def _list_windows_hid() -> set:
    return set(_iter_windows_hid())


def _win_structs():
    from ctypes import wintypes as W

    class GUID(ctypes.Structure):
        _fields_ = [('Data1', W.DWORD), ('Data2', W.WORD),
                    ('Data3', W.WORD), ('Data4', ctypes.c_ubyte * 8)]

    class IfaceData(ctypes.Structure):
        _fields_ = [('cbSize', W.DWORD), ('InterfaceClassGuid', GUID),
                    ('Flags', W.DWORD), ('Reserved', ctypes.POINTER(W.ULONG))]

    class Attributes(ctypes.Structure):
        _fields_ = [('Size', W.ULONG), ('VendorID', ctypes.c_ushort),
                    ('ProductID', ctypes.c_ushort), ('VersionNumber', ctypes.c_ushort)]

    return W, GUID, IfaceData, Attributes


def find_windows_hid(vid: int, pid: int) -> str:
    r"""Return the \\?\hid#... path for this device, or exit with why not.

    Attributes can only be read from an open handle, so a device held by the
    vendor software would otherwise look absent rather than busy: the open
    fails and its vendor id is never seen. Sharing violations are counted so
    the message can tell the two apart.
    """
    W, GUID, IfaceData, Attributes = _win_structs()
    setup, hid, k32 = ctypes.windll.setupapi, ctypes.windll.hid, ctypes.windll.kernel32

    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    devinfo = setup.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)

    held = 0
    index = 0
    try:
        while True:
            iface = IfaceData()
            iface.cbSize = ctypes.sizeof(iface)
            if not setup.SetupDiEnumDeviceInterfaces(
                    devinfo, None, ctypes.byref(guid), index, ctypes.byref(iface)):
                break
            index += 1

            need = W.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(
                devinfo, ctypes.byref(iface), None, 0, ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            # cbSize of the detail struct, not of the buffer we allocated.
            ctypes.cast(buf, ctypes.POINTER(W.DWORD))[0] = (
                8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6)
            if not setup.SetupDiGetDeviceInterfaceDetailW(
                    devinfo, ctypes.byref(iface), buf, need, None, None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + ctypes.sizeof(W.DWORD))

            handle = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
            if handle == -1:
                if k32.GetLastError() == ERROR_SHARING_VIOLATION:
                    held += 1
                continue
            attrs = Attributes()
            attrs.Size = ctypes.sizeof(attrs)
            ok = hid.HidD_GetAttributes(handle, ctypes.byref(attrs))
            k32.CloseHandle(handle)
            if ok and attrs.VendorID == vid and attrs.ProductID == pid:
                return path
    finally:
        setup.SetupDiDestroyDeviceInfoList(devinfo)

    if held:
        sys.exit(
            f'The HID collection for VID={hex(vid)} PID={hex(pid)} is held by '
            f'another process ({held} sharing violation(s)).\n'
            'Antelope\'s service holds it while it runs. Stop it and close the '
            'Launcher:\n'
            '  Stop-Service Antelope-Manager-Service -Force\n'
            '  Get-Process "Antelope Launcher","AntelopeAudioServer" | Stop-Process -Force\n'
            'Start-Service Antelope-Manager-Service puts it back.'
        )
    sys.exit(
        f'HID collection not found for VID={hex(vid)} PID={hex(pid)}.\n'
        'Check the USB connection.'
    )


class WindowsHidTransport:
    """Same surface as HidTransport, over the Windows HID API.

    One handle is kept open for the life of the object. Reopening per call the
    way the hidraw path does would race the vendor software for the exclusive
    handle every time.
    """

    def __init__(self, path: str, report_size: int):
        from ctypes import wintypes as W
        self.path = path
        self.report_size = report_size
        self._W = W
        self._k32 = ctypes.windll.kernel32
        self.handle = self._k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
        if self.handle == -1:
            sys.exit(f'Could not open {path}, error {self._k32.GetLastError()}')

    def _read_raw(self, timeout: float):
        buf = ctypes.create_string_buffer(self.report_size + 1)
        got = self._W.DWORD()
        end = time.time() + timeout
        while time.time() < end:
            if not self._k32.ReadFile(self.handle, buf, self.report_size + 1,
                                      ctypes.byref(got), None):
                return None
            if got.value:
                # drop the report-number byte so callers see what hidraw gives
                return buf.raw[1:got.value]
        return None

    def read_reports(self, magic: int, timeout: float = 3.0):
        end = time.time() + timeout
        while time.time() < end:
            data = self._read_raw(max(0.0, end - time.time()))
            if data and data[0] == magic:
                yield data

    def read_one(self, magic: int, timeout: float = 3.0):
        for data in self.read_reports(magic, timeout):
            return data
        return None

    def query(self, request: bytes, match, timeout: float = 1.0, retries: int = 2):
        if len(request) != self.report_size:
            raise ValueError(f'request must be exactly {self.report_size} bytes')
        for attempt in range(retries + 1):
            try:
                self.write(request)
            except OSError:
                if attempt < retries:
                    continue
                raise
            end = time.time() + timeout
            while time.time() < end:
                data = self._read_raw(max(0.0, end - time.time()))
                if data and match(data):
                    return data
        return None

    def write(self, payload: bytes):
        if len(payload) != self.report_size:
            raise ValueError(
                f'payload must be exactly {self.report_size} bytes, got {len(payload)}')
        report = b'\x00' + payload
        written = self._W.DWORD()
        if not self._k32.WriteFile(self.handle, report, len(report),
                                   ctypes.byref(written), None):
            raise OSError(f'WriteFile failed, error {self._k32.GetLastError()}')

    def close(self):
        if getattr(self, 'handle', None) not in (None, -1):
            self._k32.CloseHandle(self.handle)
            self.handle = None


def open_transport(vid: int, pid: int, report_size: int):
    """Pick the transport this platform can use."""
    if sys.platform == 'win32':
        return WindowsHidTransport(find_windows_hid(vid, pid), report_size)
    return HidTransport(find_hidraw(vid, pid), report_size)
