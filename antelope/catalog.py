"""Load shared AFX knowledge from an ordered manifest or legacy inline catalog.

The storage layout does not change the logical catalog or enable device I/O.
Only Python's standard library is used; callers receive fresh objects each time.
"""
import json
from pathlib import Path
import re


DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / 'profiles' / 'afx_effects.json'
_EFFECT_FILE = re.compile(r'afx/([a-z][a-z0-9_]*)[.]json\Z')


def _read_object(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'AFX JSON must be an object: {path}')
    return value


def _validate_effects(effects):
    if not isinstance(effects, list):
        raise ValueError('AFX effects must be a list')
    seen = set()
    for effect in effects:
        if not isinstance(effect, dict) or not isinstance(effect.get('id'), str) or not effect['id']:
            raise ValueError('Each AFX effect must have a nonempty string ID')
        if effect['id'] in seen:
            raise ValueError(f'Duplicate AFX effect ID: {effect["id"]}')
        seen.add(effect['id'])
        _validate_parameter_commands(effect)
    types = {}
    for effect in effects:
        for item in effect.get('implementations') or []:
            if isinstance(item, dict) and ((item.get('commands') or {}).get('parameters')) is not None:
                key = (item.get('profile'), item.get('type_id'))
                if key in types:
                    raise ValueError(f'AFX type {key[1]} of {key[0]} has parameters in {types[key]} and {effect["id"]}')
                types[key] = effect['id']


_FIELD_TYPES = {'u8', 'i8', 'u16', 'i16', 'u32', 'i32', 'f32'}


def _validate_parameter_commands(effect):
    """A populated ``commands.parameters`` is a runtime parameter-block contract."""
    implementations = effect.get('implementations') or []
    by_profile = {item.get('profile'): item for item in implementations if isinstance(item, dict)}
    for item in implementations:
        params = ((item.get('commands') or {}) if isinstance(item, dict) else {}).get('parameters')
        if params is None:
            continue
        where = f'AFX {effect["id"]} {item.get("profile")} commands.parameters'
        if (not isinstance(params, dict) or type(item.get('type_id')) is not int
                or type(params.get('writable')) is not bool or not isinstance(params.get('frame'), str)
                or type(params.get('block_length')) is not int or params['block_length'] < 1
                or any(type(params.get(key)) is not int for key in ('read_stride', 'read_offset')
                       if params.get('editable') is not False)):  # an unconfirmed read claims no layout
            raise ValueError(f'{where}: needs an integer type_id, frame, writable, block_length, read_stride, read_offset')
        if params['writable'] != (params.get('editable') is not False):
            raise ValueError(f'{where}: writable must match editable')
        if ('fields' in params) == ('fields_from' in params):
            raise ValueError(f'{where}: needs exactly one of fields and fields_from')
        if 'fields_from' in params:
            source = ((by_profile.get(params['fields_from']) or {}).get('commands') or {}).get('parameters')
            if (params['fields_from'] == item.get('profile') or not isinstance(source, dict)
                    or not isinstance(source.get('fields'), list) or source.get('block_length') != params['block_length']):
                raise ValueError(f'{where}: fields_from must name another implementation of this effect '
                                 'with its own fields and the same block_length')
            continue
        fields = params['fields']
        if not isinstance(fields, list) or not fields:
            raise ValueError(f'{where}: fields must be a nonempty list')
        keys = set()
        for field in fields:
            if (not isinstance(field, dict) or not isinstance(field.get('key'), str) or field['key'] in keys
                    or not isinstance(field.get('label'), str) or field.get('type') not in _FIELD_TYPES
                    or type(field.get('offset')) is not int or field['offset'] < 0
                    or any(type(field.get(key)) not in (int, float) for key in ('min', 'max'))):
                raise ValueError(f'{where}: bad field {field!r:.80}')
            keys.add(field['key'])
            options = field.get('options')
            if options is not None and (not isinstance(options, dict) or not options or any(
                    not isinstance(label, str) or not isinstance(raw, str) or not raw.lstrip('-').isdigit()
                    for raw, label in options.items())):
                raise ValueError(f'{where}: {field["key"]} options must map raw integers to labels')


def load_catalog(path=None):
    """Return the inline logical catalog, retaining order and unknown metadata.

    Version 1 manifests list ``afx/<stable_id>.json`` files relative to the
    manifest. Mixed layouts, duplicate references/IDs, mismatched filenames,
    unsupported storage versions and paths escaping the catalog fail closed.
    Legacy inline catalogs remain readable. No partial result is returned.
    """
    path = Path(path) if path is not None else DEFAULT_CATALOG
    catalog = _read_object(path)
    if 'storage_schema' not in catalog:
        if 'effect_files' in catalog:
            raise ValueError('AFX effect_files requires storage_schema')
        _validate_effects(catalog.get('effects'))
        return catalog
    schema = catalog['storage_schema']
    if (not isinstance(schema, dict) or set(schema) != {'id', 'version'}
            or schema.get('id') != 'antelope-afx-catalog-manifest'
            or type(schema.get('version')) is not int or schema['version'] != 1):
        raise ValueError('Unsupported AFX storage_schema')
    if 'effects' in catalog:
        raise ValueError('AFX manifest cannot mix effects and effect_files')
    references = catalog.get('effect_files')
    if not isinstance(references, list):
        raise ValueError('AFX effect_files must be a list')
    base = path.resolve().parent
    effects, seen = [], set()
    for reference in references:
        match = _EFFECT_FILE.fullmatch(reference) if isinstance(reference, str) else None
        if match is None:
            raise ValueError(f'Invalid AFX effect file: {reference!r}')
        if reference in seen:
            raise ValueError(f'Duplicate AFX effect file: {reference}')
        seen.add(reference)
        source = (base / reference).resolve()
        if not source.is_relative_to(base / 'afx'):
            raise ValueError(f'AFX effect file escapes catalog folder: {reference}')
        effect = _read_object(source)
        if effect.get('id') != match.group(1):
            raise ValueError(f'AFX effect ID does not match its file: {reference}')
        effects.append(effect)
    _validate_effects(effects)
    result = {key: value for key, value in catalog.items()
              if key not in ('storage_schema', 'effect_files')}
    result['effects'] = effects
    return result
