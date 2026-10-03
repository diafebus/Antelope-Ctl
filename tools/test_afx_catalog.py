"""Hardware-free checks for the preview's model and write boundaries."""
import copy
import json
from pathlib import Path
import unittest

from webui.afx_catalog import preview_catalog, effect_choices


class AfxCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((Path(__file__).resolve().parents[1]
                                  / "profiles/afx_effects.json").read_text())

    def test_orion_preview_has_labels_without_wire_commands_or_handles(self):
        result = preview_catalog(self.catalog, "orion_studio_sc.json")
        self.assertEqual(result["mode"], "preview")
        self.assertFalse(result["device_writes"])
        self.assertEqual(len(result["effects"]), 3)
        effect = next(e for e in result["effects"] if e['id'] == 'memory_brigade')
        self.assertEqual(effect["id"], "memory_brigade")
        self.assertEqual(len(effect["controls"]), 8)
        self.assertEqual(sum(c["kind"] == "continuous" for c in effect["controls"]), 6)
        for field in effect["controls"]:
            self.assertNotIn("offset", field)
            self.assertNotIn("wire_enum", field)
        encodings = next(i for e in self.catalog['effects'] if e['id'] == 'memory_brigade'
                         for i in e['implementations'] if i['profile'] == 'orion_studio_sc.json')['control_encodings']
        self.assertEqual(encodings['chrs_vibr']['wire_enum'], {'0':'chorus','1':'tremolo'})
        self.assertEqual(encodings['size']['wire_enum'], {'0':'550ms','1':'1100ms'})
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
        self.assertNotIn('memory_brigade', {e['id'] for e in preview_catalog(catalog, "orion_studio_sc.json")["effects"]})

    def test_modulation_panels_exclude_opaque_bytes_and_keep_unknown_modes_display_only(self):
        result = preview_catalog(self.catalog, 'orion_studio_sc.json')
        panels = {e['id']: e for e in result['effects']}
        v12 = panels['turboensembler']
        self.assertEqual(v12['panel']['rows'][0], ['voices', 'delay', 'depth', 'feedback', 'gain'])
        self.assertNotIn('presetIndex', {c['id'] for c in v12['controls']})
        controls = {c['id']: c for c in v12['controls']}
        self.assertEqual(controls['gain']['range'], [0, 255])
        self.assertEqual(controls['colorShifter']['range'], [0, 255])
        bbd = {c['id']: c for c in panels['bbdchorus']['controls']}
        self.assertEqual(bbd['chvibrato']['options'], {'0': 'Vibrato', '1': 'Chorus'})
        self.assertFalse(bbd['type']['device_available'])
        self.assertEqual(set(bbd), {'level', 'intensity', 'depth', 'rate', 'type', 'chvibrato'})
        for effect in (v12, panels['bbdchorus']):
            self.assertNotIn('commands', effect)
            for field in effect['controls']:
                self.assertNotIn('offset', field)
                self.assertNotIn('wire_enum', field)

    def test_missing_modulation_knob_does_not_make_a_partial_panel(self):
        catalog = copy.deepcopy(self.catalog)
        v12 = next(e for e in catalog['effects'] if e['id'] == 'turboensembler')
        implementation = next(i for i in v12['implementations'] if i['profile'] == 'orion_studio_sc.json')
        implementation['control_encodings'].pop('gain')
        self.assertNotIn('turboensembler', {e['id'] for e in preview_catalog(catalog, 'orion_studio_sc.json')['effects']})

    def test_modulation_browser_fixture_matches_the_catalog(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] / 'tools/fixtures/afx_modulation_presentations.json').read_text())
        actual = preview_catalog(self.catalog, 'orion_studio_sc.json')
        actual['effects'] = [e for e in actual['effects'] if e['id'] in ('bbdchorus', 'turboensembler')]
        self.assertEqual(fixture, actual)


    def test_picker_enables_only_independently_captured_orion_types(self):
        profile = json.loads((Path(__file__).resolve().parents[1]
                              / 'profiles/orion_studio_sc.json').read_text())
        choices = effect_choices(self.catalog, 'orion_studio_sc.json', profile)
        self.assertEqual(len(choices), 80)
        groups = {row['id']:row['category'] for row in choices}
        self.assertEqual(groups['memory_brigade'], 'Delay & Reverb')
        self.assertEqual(groups['instinct'], 'Dynamics')
        self.assertEqual(groups['bbdchorus'], 'Modulation')
        self.assertEqual(groups['api_550'], 'EQ & Filters')
        self.assertTrue(all(row['category'] for row in choices))
        self.assertEqual({row['id'] for row in choices if row['loadable']},
                         {'memory_brigade', 'instinct', 'deesser', 'turboensembler', 'bbdchorus'})
        self.assertFalse(any(row['loadable'] for row in effect_choices(self.catalog, 'missing.json', profile)))
        modified = copy.deepcopy(self.catalog)
        next(row for row in modified['effects'] if row['id'] == 'instinct')['implementations'] = []
        self.assertFalse(next(row for row in effect_choices(modified, 'orion_studio_sc.json', profile)
                              if row['id'] == 'instinct')['loadable'])


if __name__ == "__main__":
    unittest.main()
