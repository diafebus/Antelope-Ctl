"""Offline Orion startup checks. Run: python3 -m unittest tools.test_orion_startup."""
import json
from pathlib import Path
import unittest

from antelope import protocol


class OrionStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'profiles/orion_studio_sc.json'
        cls.profile = json.loads(path.read_text())

    def test_windows_query_order_and_repeated_markers(self):
        # Sanitized category/index facts from AntelopeINIT.pcapng, frames 15688–20134.
        expected = [(0x11, 0), (0x11, 1), (0x0b, 1), (0x0b, 2), (0x1b, 0)]
        expected += [(0x1a, i) for i in range(16)]
        expected += [(0x03, i) for i in range(15)]
        for i in range(4):
            expected += [(0x04, i), (0x0b, 3)]
        expected += [(0x0a, 0), (0x15, 0), (0x0b, 0), (0x16, 0)]
        expected += [(0x19, i) for i in range(64)]
        expected += [(0x0b, 4)]
        queries = self.profile['frame']['readback']['startup_queries']
        actual = [(int(q['category'], 16), q['index']) for q in queries]
        self.assertEqual(actual, expected)
        for category, index in actual:
            frame = protocol.build_readback_query(self.profile, category, index)
            self.assertEqual(len(frame), 320)
            self.assertEqual(frame[0], 0x74)
            self.assertEqual(frame[4:8], bytes.fromhex('10 00 00 00'))
            self.assertEqual(frame[8:12], category.to_bytes(4, 'little'))
            self.assertEqual(frame[12:16], index.to_bytes(4, 'little'))
            self.assertEqual(frame[16:], bytes(304))

    def test_unobserved_link_table_indices_are_rejected(self):
        for index in (5, 6, 7):
            with self.subTest(index=index):
                with self.assertRaises(protocol.ConstraintError):
                    protocol.build_readback_query(self.profile, 0x0b, index)
        for index in range(5):
            protocol.build_readback_query(self.profile, 0x0b, index)


if __name__ == '__main__':
    unittest.main()
