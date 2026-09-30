"""Hardware-free checks for the preview's model and write boundaries."""
import copy
import json
from pathlib import Path
import unittest

from webui.afx_catalog import preview_catalog


class AfxCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((Path(__file__).resolve().parents[1]
                                  / "profiles/afx_effects.json").read_text())

    def test_orion_preview_has_labels_without_wire_commands_or_handles(self):
        result = preview_catalog(self.catalog, "orion_studio_sc.json")
        self.assertEqual(result["mode"], "preview")
        self.assertFalse(result["device_writes"])
        self.assertEqual(len(result["effects"]), 1)
        effect = result["effects"][0]
        self.assertEqual(effect["id"], "memory_brigade")
        self.assertEqual(len(effect["controls"]), 8)
        self.assertEqual(sum(c["kind"] == "continuous" for c in effect["controls"]), 6)
        for field in effect["controls"]:
            self.assertNotIn("offset", field)
            self.assertNotIn("wire_enum", field)
        self.assertNotIn("commands", effect)
        self.assertNotIn("instance_handle", effect)

    def test_other_profiles_do_not_inherit_orion_observations(self):
        for profile in ("discrete_4_sc.json", "zen_go_sc.json", "missing.json"):
            with self.subTest(profile=profile):
                self.assertEqual(preview_catalog(self.catalog, profile)["effects"], [])

    def test_partial_observations_are_not_presented_as_a_complete_panel(self):
        catalog = copy.deepcopy(self.catalog)
        effect = next(e for e in catalog["effects"] if e["id"] == "memory_brigade")
        implementation = next(i for i in effect["implementations"]
                              if i["profile"] == "orion_studio_sc.json")
        del implementation["control_encodings"]["size"]
        self.assertEqual(preview_catalog(catalog, "orion_studio_sc.json")["effects"], [])


if __name__ == "__main__":
    unittest.main()
