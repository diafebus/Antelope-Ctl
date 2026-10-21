"""Hardware-free registry validation and capture-policy regressions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.afx_dropdown_options import find_plugin, key_control_options, load_dropdown_options


class DropdownOptionsTests(unittest.TestCase):
    def setUp(self):
        self.document = load_dropdown_options()
        self.control = {'dropdown_id': 'filter_type', 'class_name': 'DeesserComboBoxFilterType'}

    def load_document(self, document):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'registry.json'
            path.write_text(json.dumps(document), encoding='utf-8')
            return load_dropdown_options(path)

    def test_captured_filter_labels_preserve_order_without_claiming_full_count(self):
        labels = key_control_options('Master-De-Esser', self.control)
        self.assertEqual(labels, ['HighPass 1', 'HighPass 2', 'HighPass 3', 'BandPass 1', 'BandPass 2'])
        dropdown = find_plugin('deesser')['dropdowns'][0]
        self.assertIsNone(dropdown['full_count'])
        self.assertIn('unresolved', dropdown['full_count_status'])
        self.assertTrue(all(set(option) == {'label'} for option in dropdown['options']))
        self.assertIn('deesser-menu-20261009', dropdown['source_ids'])

    def test_aliases_resolve_but_unknown_inventory_is_not_a_known_plan(self):
        for alias in ('Master De-Esser', 'Master-De-Esser', 'Deesser', 'DEESSER'):
            self.assertEqual(find_plugin(alias)['effect_id'], 'deesser')
        for alias in ('unknown', '', None, 12):
            with self.subTest(alias=alias), self.assertRaises(ValueError):
                find_plugin(alias)

    def test_unpurchased_autotune_is_excluded_for_every_known_alias(self):
        for alias in ('Auto-Tune', 'AutoTune', 'Antares Auto-Tune', 'antares_autotune'):
            self.assertEqual(find_plugin(alias)['hardware_testing'], 'excluded')
            with self.subTest(alias=alias), self.assertRaisesRegex(ValueError, 'excluded'):
                key_control_options(alias, self.control)

    def test_key_trial_requires_known_order_and_exact_control_class(self):
        for control in (None, {}, {'dropdown_id': 'filter_type', 'class_name': 'AnotherComboBox'},
                        {'dropdown_id': 'presets', 'class_name': 'DeesserPresetsCombobox'}):
            with self.subTest(control=control), self.assertRaises(ValueError):
                key_control_options('deesser', control)
        # The trial bound is independent of any eventual complete inventory.
        for count in (1, 9):
            document = copy.deepcopy(self.document)
            document['plugins'][0]['dropdowns'][0]['options'] = [{'label': f'choice {n}'} for n in range(count)]
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'ordered known choices'):
                key_control_options('deesser', self.control, document)

    def test_malformed_document_and_plugin_shapes_are_value_errors(self):
        cases = [None, [], {}, {'version': True, 'profile': 'orion_studio_sc.json'}]
        for field, value in [('version', True), ('profile', 'other.json'), ('sources', []),
                             ('sources', {}), ('plugins', None), ('plugins', [None]),
                             ('plugins', [{}])]:
            document = copy.deepcopy(self.document)
            document[field] = value
            cases.append(document)
        for document in cases:
            with self.subTest(document=document), self.assertRaises(ValueError):
                self.load_document(document)
        for field, value in [('aliases', 'other'), ('aliases', [None]), ('effect_id', []),
                             ('name', ' '), ('hardware_testing', 'yes'), ('source_ids', []),
                             ('unresolved', 'pending'), ('dropdowns', None), ('dropdowns', [None])]:
            document = copy.deepcopy(self.document)
            document['plugins'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.load_document(document)

    def test_ambiguous_identities_and_labels_are_rejected(self):
        document = copy.deepcopy(self.document)
        document['plugins'].append(copy.deepcopy(document['plugins'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate dropdown effect'):
            self.load_document(document)
        document = copy.deepcopy(self.document)
        document['plugins'][1]['aliases'].append('Master De Esser')
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            self.load_document(document)
        document = copy.deepcopy(self.document)
        document['plugins'][0]['dropdowns'].append(copy.deepcopy(document['plugins'][0]['dropdowns'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate dropdown control'):
            self.load_document(document)
        document = copy.deepcopy(self.document)
        dropdown = document['plugins'][0]['dropdowns'][0]
        dropdown['options'].append(copy.deepcopy(dropdown['options'][0]))
        with self.assertRaises(ValueError):
            self.load_document(document)

    def test_controls_require_labels_and_resolvable_evidence(self):
        for field, value in [('id', None), ('class_name', ''), ('status', None),
                             ('options', None), ('options', [None]), ('options', [{'label': 3}]),
                             ('options', [{'label': '   '}]),
                             ('options', [{'label': 'HighPass 1', 'raw': 0}]),
                             ('ordering', 'guessed'), ('ordering', 'unknown'),
                             ('full_count', True), ('full_count', 4), ('full_count_status', ''),
                             ('source_ids', []), ('source_ids', ['missing']),
                             ('source_ids', 'deesser-menu-20261009')]:
            document = copy.deepcopy(self.document)
            document['plugins'][0]['dropdowns'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.load_document(document)
        for value in (None, {}, {'kind': 'guess', 'reference': 'x', 'notes': 'x'}):
            document = copy.deepcopy(self.document)
            document['sources']['deesser-menu-20261009'] = value
            with self.subTest(source=value), self.assertRaises(ValueError):
                self.load_document(document)

    def test_supplied_document_cannot_bypass_validation(self):
        document = copy.deepcopy(self.document)
        document['plugins'][0]['dropdowns'][0]['source_ids'] = ['missing']
        with self.assertRaises(ValueError):
            find_plugin('deesser', document)
        with self.assertRaises(ValueError):
            key_control_options('deesser', self.control, document)


if __name__ == '__main__':
    unittest.main()
