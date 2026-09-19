"""Contract tests for the documented hardware-free regression runner."""
from pathlib import Path
import unittest

from tools import offline_checks


class OfflineChecksTests(unittest.TestCase):
    def test_the_orion_audit_is_part_of_the_standard_python_suite(self):
        self.assertIn("tools.test_orion_profile_audit", offline_checks.PYTHON_MODULES)

    def test_every_declared_node_check_exists(self):
        root = Path(__file__).resolve().parents[1]
        for check in offline_checks.NODE_CHECKS:
            with self.subTest(check=check):
                self.assertTrue((root / check).is_file())

    def test_python_only_never_spawns_a_browser_check(self):
        selected = offline_checks.checks(include_node=False)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][1][:3], [offline_checks.sys.executable, "-m", "unittest"])


if __name__ == "__main__":
    unittest.main()
