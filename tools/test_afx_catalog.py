"""Hardware-free checks for the preview's model and write boundaries."""
from antelope.catalog import load_catalog
import copy
import json
from pathlib import Path
import unittest

from webui.afx_catalog import preview_catalog, effect_choices


class AfxCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(Path(__file__).resolve().parents[1] / "profiles/afx_effects.json")

    def test_orion_preview_has_labels_without_wire_commands_or_handles(self):
        result = preview_catalog(self.catalog, "orion_studio_sc.json")
        self.assertEqual(result["mode"], "preview")
        self.assertFalse(result["device_writes"])
        self.assertEqual({e['id'] for e in result['effects']},
                         {'memory_brigade', 'turboensembler', 'bbdchorus', 'deesser',
                          'powergate', 'powerex', 'pultec_eqp', 'pultec_meq'})
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

    def test_instinct_endpoint_inventory_is_complete_without_enabling_runtime_writes(self):
        effect = next(e for e in self.catalog['effects'] if e['id'] == 'instinct')
        implementation = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
        observation = implementation['parameter_observation']
        knobs = [f for f in observation['labelled_gui_observations'].values() if f.get('encoding') == 'float32-le']
        self.assertEqual(len(knobs), 21)
        occupied = [byte for f in knobs for byte in range(f['offset'], f['offset'] + f['width'])]
        self.assertEqual(len(occupied), len(set(occupied)))
        self.assertTrue(all(f['writable'] is False and f['readback_verified'] is False for f in knobs))
        self.assertEqual(observation['labelled_gui_observations']['knob_volume']['observed_display_range'], ['-Infinity', 1])
        self.assertFalse(observation['writable'])
        self.assertFalse(observation['range_capture_summary']['interpolation_laws_verified'])
        self.assertNotIn('instinct', {e['id'] for e in preview_catalog(self.catalog, 'orion_studio_sc.json')['effects']})

    def test_captured_presentations_are_local_and_match_browser_fixture(self):
        preview = preview_catalog(self.catalog, 'orion_studio_sc.json')
        preview['effects'] = [e for e in preview['effects'] if e.get('local_presentation')]
        fixture = json.loads((Path(__file__).resolve().parents[1] /
                              'tools/fixtures/afx_captured_presentations.json').read_text())
        self.assertEqual(preview, fixture)
        self.assertEqual(len(preview['effects']), 5)
        serialized = json.dumps(preview)
        for key in ('offset', 'opcode', 'wire_enum', 'commands', 'instance_handle', 'source_control'):
            self.assertNotIn('"' + key + '"', serialized)
        controls = {e['id']: {c['id']: c for c in e['controls']} for e in preview['effects']}
        self.assertEqual(controls['powergate']['attack']['range'], [0.1, 75])
        self.assertEqual(controls['powerex']['attack']['range'], [1, 750])
        self.assertEqual(controls['powergate']['gain']['range'], [-24, 12])
        self.assertEqual(len(controls['pultec_meq']['mid_freq']['options']), 11)

    def test_eq_frequency_labels_include_units_without_changing_wire_choices(self):
        preview = {e['id']: e for e in preview_catalog(self.catalog, 'orion_studio_sc.json')['effects']}
        eqp = {c['id']: c for c in preview['pultec_eqp']['controls']}
        meq = {c['id']: c for c in preview['pultec_meq']['controls']}
        self.assertEqual(eqp['high_freq']['options']['5'], '12 kHz')
        self.assertEqual(eqp['atten_sel']['options']['0'], '5 kHz')
        self.assertEqual(meq['mid_freq']['options']['0'], '200 Hz')
        self.assertEqual(meq['mid_freq']['options']['6'], '2 kHz')
        self.assertEqual(meq['hi_freq']['options']['0'], '1.5 kHz')
        for effect_id, control_id in [('pultec_eqp', 'high_freq'), ('pultec_meq', 'mid_freq')]:
            effect = next(e for e in self.catalog['effects'] if e['id'] == effect_id)
            impl = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
            display = next(c for c in preview[effect_id]['controls'] if c['id'] == control_id)
            self.assertEqual(list(display['options']), list(impl['control_encodings'][control_id]['wire_enum']))
            self.assertFalse(impl['control_encodings'][control_id]['writable'])

    def test_liverpool_selector_contacts_stay_distinct_and_read_only(self):
        effect = next(e for e in self.catalog['effects'] if e['id'] == 'liverpool')
        impl = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
        for control_id, letter in [('attack', 'C'), ('recovery', 'H')]:
            control = impl['control_encodings'][control_id]
            self.assertEqual(control['kind'], 'enum')
            self.assertEqual(list(control['wire_enum']), [str(n) for n in range(11)])
            contacts = [str(n) for n in (1, 3, 5, 7, 9)]
            self.assertTrue(all(control['printed_labels'][key] == letter for key in contacts))
            self.assertEqual(len({control['options'][key] for key in contacts}), 5,
                             'Repeated Off/Hold legends must not collapse different wire contacts')
            self.assertFalse(control['writable'])
        output = impl['control_encodings']['output']
        self.assertEqual(output['kind'], 'enum', 'Output is a stepped attenuator, not continuous gain')
        self.assertEqual(list(output['options'].values()), ['30 dB', '20 dB', '15 dB', '10 dB', '5 dB', '0 dB'])
        self.assertFalse(output['writable'])
        self.assertTrue(all(command is None for command in impl['commands'].values()))
        self.assertNotIn('liverpool', {e['id'] for e in preview_catalog(self.catalog, 'orion_studio_sc.json')['effects']},
                         'Capture metadata alone must not enable a runtime or guessed local panel')

    def test_local_presentation_requires_its_own_model_capture_sources(self):
        catalog = copy.deepcopy(self.catalog)
        effect = next(e for e in catalog['effects'] if e['id'] == 'powergate')
        orion = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
        del orion['parameter_observation']['labelled_gui_observations']['threshold']
        self.assertNotIn('powergate', {e['id'] for e in preview_catalog(catalog, 'orion_studio_sc.json')['effects']})
        sibling = next(i for i in effect['implementations'] if i['profile'] == 'discrete_4_sc.json')
        sibling['presentation'] = copy.deepcopy(orion['presentation'])
        self.assertNotIn('powergate', {e['id'] for e in preview_catalog(catalog, 'discrete_4_sc.json')['effects']})
        catalog = copy.deepcopy(self.catalog)
        effect = next(e for e in catalog['effects'] if e['id'] == 'powergate')
        orion = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
        del orion['bypass_observation']
        self.assertNotIn('powergate', {e['id'] for e in preview_catalog(catalog, 'orion_studio_sc.json')['effects']})

    def test_invalid_local_presentations_fail_closed(self):
        from webui.afx_catalog import panel_definition
        effect = next(e for e in self.catalog['effects'] if e['id'] == 'deesser')
        implementation = next(i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json')
        mutations = [
            lambda p: p.update(controls=[None]),
            lambda p: p['controls'][0].update(range=None),
            lambda p: p['controls'][0].update(range=[80, 0]),
            lambda p: p['controls'][0].update(step=0),
            lambda p: p['controls'][0].update(default=float('nan')),
            lambda p: p['controls'][0].update(decimals=100),
            lambda p: p['controls'][0].update(source_control=['threshold']),
            lambda p: p['controls'].append(copy.deepcopy(p['controls'][0])),
            lambda p: p.update(rows=[None]),
            lambda p: p.update(dependencies={'q_factor': 'filter_type'}),
            lambda p: p.update(dependencies={'q_factor': {'control': 'filter_type', 'values': ['99']}}),
            lambda p: p['controls'][-1].update(rotary='yes'),
        ]
        for index, mutate in enumerate(mutations):
            invalid = copy.deepcopy(implementation)
            mutate(invalid['presentation'])
            with self.subTest(index=index):
                self.assertIsNone(panel_definition(effect, invalid))

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
        self.assertTrue(controls['voices']['rotary'])
        self.assertEqual(controls['voices']['kind'], 'enum')
        self.assertEqual(list(controls['voices']['options']), [str(i) for i in range(1, 13)])
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
