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
            {'preamps': 0, 'adats': 1, 'spdifs': 2, 'mixer': 3, 'afx': 4},
        )

    def test_writable_families_have_matching_pair_counts(self):
        for family, expected_space in (('physical', 0), ('adat', 0), ('spdif', 1)):
            with self.subTest(family=family):
                spec, table = capture.validate_target(self.profile, family, 0)
                self.assertEqual(spec['space'], expected_space)
                self.assertEqual(spec['pairs'], table['record_count'])

    def test_pair_bounds_are_rejected_before_any_transport_is_opened(self):
        with self.assertRaises(ValueError):
            capture.validate_target(self.profile, 'spdif', 1)
        with self.assertRaises(ValueError):
            capture.validate_target(self.profile, 'physical', -1)

    def test_diffs_identify_only_changed_slots(self):
        before = {'preamps': [0, 0], 'adats': [0]}
        after = {'preamps': [0, 1], 'adats': [0]}
        self.assertEqual(capture.changed_tables(before, after), {
            'preamps': [{'pair': 1, 'before': 0, 'after': 1}],
        })


if __name__ == '__main__':
    unittest.main()
