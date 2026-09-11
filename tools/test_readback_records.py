"""Offline tests for profile-declared nested readback records."""
import json
from pathlib import Path
import unittest

from antelope import protocol


class ReadbackRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.profile = json.loads((root / 'profiles/orion_studio_sc.json').read_text())
        cls.zen = json.loads((root / 'profiles/zen_go_sc.json').read_text())

    def test_link_table_layouts_are_indexed_by_link_space(self):
        expected = {0: ('preamps', 6), 1: ('adats', 8), 2: ('spdifs', 1),
                    3: ('mixer', 64), 4: ('afx', 32)}
        for index, (name, count) in expected.items():
            with self.subTest(index=index):
                layout = protocol.readback_record_layout(self.profile, 0x0b, index)
                self.assertEqual(layout['name'], name)
                self.assertEqual(layout['record_count'], count)
                body = bytes((i & 1 for i in range(count))) + bytes(304 - count)
                records = protocol.parse_link_table(self.profile, body, 0x0b, index)
                self.assertEqual(len(records), count)
                self.assertEqual([r['linked'] for r in records],
                                 [i & 1 for i in range(count)])

    def test_mic_emulation_records(self):
        body = b''.join(bytes((i, i + 1, i & 1, i + 2)) for i in range(8))
        records = protocol.parse_mic_emulations(self.profile, body + bytes(304 - len(body)),
                                                0x16, 0)
        self.assertEqual(len(records), 8)
        self.assertEqual(records[0]['target'], 0)
        self.assertEqual(records[3]['emu_model'], 4)
        self.assertEqual(records[7]['ch_swap'], 1)
        self.assertEqual(records[7]['pattern'], 9)

    def test_afx_strip_order_records(self):
        body = b''.join(bytes((0, 0)) if i == 0 else bytes((i, i + 0x40))
                         for i in range(8))
        records = protocol.parse_afx_strip_order(self.profile,
                                                 body + bytes(304 - len(body)),
                                                 0x19, 63)
        self.assertEqual(len(records), 8)
        self.assertEqual(records[0]['raw'], b'\x00\x00')
        self.assertEqual((records[4]['type'], records[4]['inst']), (4, 0x44))
        self.assertIsNone(protocol.readback_record_layout(self.profile, 0x19, 64))

    def test_afx_instance_count_tables(self):
        body = b''.join(bytes((i & 0xff, (i * 2) & 0xff)) for i in range(91))
        records = protocol.parse_afx_instance_table(self.profile,
                                                     body + bytes(304 - len(body)),
                                                     0x15, 0)
        self.assertEqual(len(records), 91)
        self.assertEqual(records[12]['type_id'], 12)
        self.assertEqual(records[12]['inst_count'], 24)

        available = protocol.parse_afx_instance_table(
            self.profile, bytes(180) + bytes(124), 0x0c, 0)
        self.assertEqual(len(available), 90)

    def test_short_nested_record_is_rejected(self):
        with self.assertRaises(ValueError):
            protocol.parse_mic_emulations(self.profile, bytes(31), 0x16, 0)

    def test_schema_only_outer_indices_are_not_queryable(self):
        self.assertEqual(protocol.readback_record_layout_indices(
            self.profile, 0x19), list(range(64)))
        self.assertEqual(protocol.readback_record_layout_indices(
            self.profile, 0x0c), [])
        self.assertEqual(protocol.readback_record_layout_indices(
            self.profile, 0x0c, safe_only=False), [0, 1])
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_readback_query(self.profile, 0x0c, 0)
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_readback_query(self.profile, 0x0b, -1)

    def test_sibling_profiles_do_not_inherit_orion_layouts(self):
        self.assertIsNone(protocol.readback_record_layout(self.zen, 0x0b, 0))


if __name__ == '__main__':
    unittest.main()
