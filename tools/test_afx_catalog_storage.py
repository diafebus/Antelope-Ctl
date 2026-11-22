"""Hardware-free catalog layout, resolution and compatibility checks."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from antelope.catalog import DEFAULT_CATALOG, load_catalog
from tools.export_afx_catalog import main as export_catalog


class CatalogStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'afx').mkdir()
        self.path = self.root / 'catalog.json'
        self.manifest = {
            'catalog_schema': {'id': 'antelope-afx-effect-catalog', 'version': 1},
            'unknown_future_metadata': {'keep': [None, 0, True, 'µ']},
            'storage_schema': {'id': 'antelope-afx-catalog-manifest', 'version': 1},
            'effect_files': ['afx/second.json', 'afx/first.json'],
        }
        self.effects = [
            {'id': 'second', 'unknown': {'opaque': [255, 17]}, 'implementations': []},
            {'id': 'first', 'controls': [], 'commands': None},
        ]
        for effect in self.effects:
            self.write(self.root / 'afx' / (effect['id'] + '.json'), effect)
        self.write(self.path, self.manifest)

    def write(self, path, obj):
        path.write_text(json.dumps(obj), encoding='utf-8')

    def test_resolution_preserves_all_logical_fields_and_explicit_order(self):
        expected = {k: v for k, v in self.manifest.items()
                    if k not in ('storage_schema', 'effect_files')}
        expected['effects'] = self.effects
        self.assertEqual(load_catalog(self.path), expected)
        self.assertEqual(list(load_catalog(self.path)), list(expected))
        self.assertEqual([e['id'] for e in load_catalog(self.path)['effects']], ['second', 'first'])

    def test_legacy_inline_catalog_remains_exact(self):
        legacy = {'custom': {'keep': [1, None]}, 'effects': self.effects}
        self.write(self.path, legacy)
        self.assertEqual(load_catalog(self.path), legacy)

    def test_default_catalog_files_are_complete_unique_and_ordered(self):
        manifest = json.loads(DEFAULT_CATALOG.read_text())
        catalog = load_catalog()
        self.assertEqual(len(catalog['effects']), len(manifest['effect_files']))
        self.assertEqual(len({e['id'] for e in catalog['effects']}), len(catalog['effects']))
        self.assertEqual(set(manifest['effect_files']),
                         {'afx/' + p.name for p in (DEFAULT_CATALOG.parent / 'afx').glob('*.json')})
        for effect, ref in zip(catalog['effects'], manifest['effect_files']):
            self.assertEqual(effect, json.loads((DEFAULT_CATALOG.parent / ref).read_text()))
        self.assertEqual({k: v for k, v in catalog.items() if k != 'effects'},
                         {k: v for k, v in manifest.items()
                          if k not in ('storage_schema', 'effect_files')})

    def test_reads_fresh_files_and_returns_independent_objects(self):
        first = load_catalog(self.path)
        first['effects'][0]['unknown']['opaque'].append(9)
        self.effects[0]['new_evidence'] = ['measured']
        self.write(self.root / 'afx/second.json', self.effects[0])
        self.assertEqual(load_catalog(self.path)['effects'], self.effects)

    def test_storage_version_and_shape_fail_closed(self):
        variants = [None, [], {}, {'id': 'other', 'version': 1}]
        variants += [{'id': 'antelope-afx-catalog-manifest', 'version': n}
                     for n in (True, False, 1.0, 0, 2, '1', None)]
        variants += [{**self.manifest['storage_schema'], 'unexpected': 1}]
        for schema in variants:
            with self.subTest(schema=schema):
                self.write(self.path, {**self.manifest, 'storage_schema': schema})
                with self.assertRaisesRegex(ValueError, 'storage_schema'):
                    load_catalog(self.path)

    def test_mixed_or_missing_storage_metadata_fails_closed(self):
        for manifest in ({**self.manifest, 'effects': []},
                         {k: v for k, v in self.manifest.items() if k != 'storage_schema'}):
            self.write(self.path, manifest)
            with self.assertRaises(ValueError):
                load_catalog(self.path)

    def test_invalid_reference_lists_and_paths_fail_closed(self):
        variants = [None, {}, 'afx/first.json', [None], [1], [{}],
                    ['../first.json'], ['/tmp/first.json'], ['afx/../first.json'],
                    ['afx\\first.json'], ['afx/first.json/extra'], ['https://example.com/first.json']]
        for refs in variants:
            with self.subTest(refs=refs):
                self.write(self.path, {**self.manifest, 'effect_files': refs})
                with self.assertRaises(ValueError):
                    load_catalog(self.path)

    def test_duplicate_references_and_legacy_ids_fail_closed(self):
        self.write(self.path, {**self.manifest, 'effect_files': ['afx/first.json'] * 2})
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            load_catalog(self.path)
        self.write(self.path, {'effects': [self.effects[0]] * 2})
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            load_catalog(self.path)

    def test_missing_malformed_or_mismatched_effect_fails_without_partial_result(self):
        source = self.root / 'afx/first.json'
        for content in ('[]', 'null', '{', '{"id":"wrong"}', '{"name":"missing id"}'):
            source.write_text(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                load_catalog(self.path)
        source.unlink()
        with self.assertRaises(OSError):
            load_catalog(self.path)

    def test_invalid_catalog_or_legacy_effect_list_fails_closed(self):
        for obj in ([], None, {}, {'effects': None}, {'effects': {}},
                    {'effects': [None]}, {'effects': [{'id': ''}]}, {'effects': [{'id': []}]}):
            self.write(self.path, obj)
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                load_catalog(self.path)

    def test_parameter_commands_fail_closed(self):
        field = {'key': 'level', 'label': 'Level', 'offset': 0, 'type': 'u8', 'min': 0, 'max': 100}
        params = {'frame': 'afx_inserts.parameters.write', 'writable': True, 'block_length': 2,
                  'read_stride': 3, 'read_offset': 1, 'fields': [field]}

        def implementation(profile, **changes):
            return {'profile': profile, 'type_id': 7,
                    'commands': {'load': None, 'recall': None, 'parameters': {**params, **changes}}}
        good = [implementation('a.json'), implementation('b.json', fields_from='a.json', fields=None)]
        del good[1]['commands']['parameters']['fields']
        self.write(self.root / 'afx/second.json', {'id': 'second', 'implementations': good})
        resolved = load_catalog(self.path)['effects'][0]['implementations']
        self.assertEqual(resolved, good)
        bad = [[implementation('a.json', writable='yes')],
               [implementation('a.json', block_length=0)],
               [implementation('a.json', editable=False)],                 # writable must say false too
               [implementation('a.json', fields=[])],
               [implementation('a.json', fields=[field, field])],          # repeated key
               [implementation('a.json', fields=[{**field, 'type': 'u24'}])],
               [implementation('a.json', fields=[{**field, 'options': {'one': 'One'}}])],
               [implementation('a.json', fields_from='a.json')],           # both fields and fields_from
               [implementation('b.json', fields_from='a.json', fields=None)]]  # no such implementation
        del bad[-1][0]['commands']['parameters']['fields']
        for implementations in bad:
            self.write(self.root / 'afx/second.json', {'id': 'second', 'implementations': implementations})
            with self.subTest(implementations=implementations), self.assertRaises(ValueError):
                load_catalog(self.path)
        # One device type id cannot carry parameters in two effects.
        self.write(self.root / 'afx/second.json', {'id': 'second', 'implementations': [implementation('a.json')]})
        self.write(self.root / 'afx/first.json', {'id': 'first', 'implementations': [implementation('a.json')]})
        with self.assertRaisesRegex(ValueError, 'type 7'):
            load_catalog(self.path)

    def test_symlink_escape_fails_closed(self):
        external = self.root / 'external.json'
        self.write(external, {'id': 'first'})
        source = self.root / 'afx/first.json'
        source.unlink()
        source.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            load_catalog(self.path)

    def test_export_stdout_and_file_are_the_logical_catalog(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(export_catalog(['--catalog', str(self.path)]), 0)
        self.assertEqual(json.loads(stdout.getvalue()), load_catalog(self.path))
        output = self.root / 'export.json'
        export_catalog(['--catalog', str(self.path), '--output', str(output)])
        self.assertEqual(load_catalog(output), load_catalog(self.path))
        self.assertNotIn('storage_schema', json.loads(output.read_text()))

    def test_export_refuses_to_overwrite_either_source_kind(self):
        for output in (self.path, self.root / 'afx/first.json'):
            before = output.read_bytes()
            with self.subTest(output=output), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                export_catalog(['--catalog', str(self.path), '--output', str(output)])
            self.assertEqual(output.read_bytes(), before)

    def test_export_cli_works_from_another_working_directory(self):
        script = Path(__file__).resolve().parent / 'export_afx_catalog.py'
        result = subprocess.run([sys.executable, str(script)], cwd=self.root,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), load_catalog())


if __name__ == '__main__':
    unittest.main()
