#!/usr/bin/env python3
"""Hardware-free checks for the Linux sysfs scan in antelope.transport."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from antelope import transport

NODES = {
    'hidraw0': 'HID_ID=0003:000023E5:0000A270\nHID_NAME=Antelope\n',
    'hidraw1': 'DRIVER=hid-generic\nMODALIAS=hid:b0003g0001v000023E5p0000A015\n',
    'hidraw2': 'HID_ID=0003:0000046D:0000C52B\n',
    'hidraw3': 'HID_ID=garbage\nMODALIAS=usb:v23E5pFFFFd0100\n',
}


class SysfsScanTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, uevent in NODES.items():
            os.makedirs(os.path.join(tmp.name, name, 'device'))
            with open(os.path.join(tmp.name, name, 'device', 'uevent'), 'w') as f:
                f.write(uevent)
        patch = mock.patch.object(transport, '_SYSFS_HIDRAW', tmp.name)
        patch.start()
        self.addCleanup(patch.stop)

    def test_find_and_list_agree(self):
        listed = transport.list_connected_hid()
        self.assertEqual(listed, {(0x23E5, 0xA270), (0x23E5, 0xA015), (0x046D, 0xC52B)})
        nodes = {transport.find_hidraw(vid, pid) for vid, pid in listed}
        self.assertEqual(nodes, {'/dev/hidraw0', '/dev/hidraw1', '/dev/hidraw2'})

    def test_not_found_raises_oserror_not_systemexit(self):
        with self.assertRaises(OSError) as raised:
            transport.find_hidraw(0x23E5, 0xFFFF)
        self.assertIn('HID node not found', str(raised.exception))

    def test_unreadable_sysfs_lists_empty(self):
        with mock.patch.object(transport, '_SYSFS_HIDRAW', '/nonexistent'):
            self.assertEqual(transport.list_connected_hid(), set())

    def test_permission_error_is_oserror_with_message(self):
        hid = transport.HidTransport('/dev/hidraw-fake', 4)
        with mock.patch.object(transport.os, 'open', side_effect=PermissionError(13, 'denied')):
            for call in (lambda: hid.write(b'\0' * 4),
                         lambda: hid.query(b'\0' * 4, bool),
                         lambda: hid.read_one(0x73, 0.01)):
                with self.assertRaises(PermissionError) as raised:
                    call()
                self.assertIn('/dev/hidraw-fake', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
