"""Offline safety checks for tools.link_transition_capture."""
import json
from pathlib import Path
import unittest

from tools import link_transition_capture as capture


class LinkTransitionCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'profiles' / 'orion_studio_sc.json'
        cls.profile = json.loads(path.read_text())

    def test_only_profile_declared_link_tables_are_selected(self):
        tables = capture.link_tables(self.profile)
        self.assertEqual(
            {name: table['index'] for name, table in tables.items()},
            {'preamp': 0,
             'adat': 1,
             'spdif': 2, 'mixer': 3, 'afx': 4},
        )

    def test_writable_families_use_the_observed_table(self):
        for family, expected_index in (('physical', 0), ('adat', 1), ('spdif', 2), ('afx', 4)):
            with self.subTest(family=family):
                spec, table = capture.validate_target(self.profile, family, 0)
                self.assertEqual(spec['space'], expected_index)
                self.assertEqual(table['index'], expected_index)

    def test_pair_bounds_are_rejected_before_any_transport_is_opened(self):
        with self.assertRaises(ValueError):
            capture.validate_target(self.profile, 'spdif', 1)
        with self.assertRaises(ValueError):
            capture.validate_target(self.profile, 'physical', -1)
        with self.assertRaises(ValueError):
            capture.validate_target(self.profile, 'afx', 16)
        self.assertEqual(capture.validate_target(self.profile, 'afx', 15)[0]['pairs'], 16)
        spec, table = capture.validate_target(self.profile, 'adat', 6)
        self.assertEqual(table['index'], 1)
        self.assertEqual(table['record_count'], 8)

    def test_diffs_identify_only_changed_slots(self):
        before = {'preamps': [0, 0], 'adats': [0]}
        after = {'preamps': [0, 1], 'adats': [0]}
        self.assertEqual(capture.changed_tables(before, after), {
            'preamps': [{'pair': 1, 'before': 0, 'after': 1}],
        })


if __name__ == '__main__':
    unittest.main()
