"""Load shared AFX knowledge from an ordered manifest or legacy inline catalog.

The storage layout does not change the logical catalog or enable device I/O.
Only Python's standard library is used; callers receive fresh objects each time.
"""
import json
import math
from pathlib import Path
import re
import struct


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


_FIELD_TYPES = {'u8': (1, False), 'i8': (1, True), 'u16': (2, False), 'i16': (2, True),
                'u32': (4, False), 'i32': (4, True), 'f32': (4, True)}


def _wire_field_value(kind, value):
    if kind == 'f32':
        if type(value) not in (int, float):
            return False
        try:
            return math.isfinite(struct.unpack('<f', struct.pack('<f', value))[0])
        except (OverflowError, struct.error):
            return False
    width, signed = _FIELD_TYPES[kind]
    upper = 1 << (width * 8 - int(signed))
    return type(value) is int and (-upper if signed else 0) <= value < upper


def _validate_parameter_fields(fields, length, where):
    if not isinstance(fields, list) or not fields:
        raise ValueError(f'{where}: fields must be a nonempty list')
    keys = set()
    occupied = set()
    for field in fields:
        if (not isinstance(field, dict) or not isinstance(field.get('key'), str) or not field['key']
                or field['key'] in keys or not isinstance(field.get('label'), str)
                or not isinstance(field.get('type'), str) or field['type'] not in _FIELD_TYPES
                or type(field.get('offset')) is not int or field['offset'] < 0):
            raise ValueError(f'{where}: bad field {field!r:.80}')
        key, kind, offset = field['key'], field['type'], field['offset']
        low, high = field.get('min'), field.get('max')
        if not (_wire_field_value(kind, low) and _wire_field_value(kind, high) and low <= high):
            raise ValueError(f'{where}: {key} has an invalid wire range')
        span = set(range(offset, offset + _FIELD_TYPES[kind][0]))
        if max(span) >= length or occupied.intersection(span):
            raise ValueError(f'{where}: {key} overlaps or is outside its block')
        occupied.update(span)
        keys.add(key)
        if 'values' in field:
            values = field['values']
            if (not isinstance(values, list) or not values
                    or any(not _wire_field_value(kind, value) or not low <= value <= high for value in values)
                    or len(set(values)) != len(values)):
                raise ValueError(f'{where}: {key} has invalid selector values')
        for name in ('options', 'orion_option_candidates'):
            if name not in field:
                continue
            options = field[name]
            if not isinstance(options, dict) or not options or any(
                    not isinstance(label, str) or not label or not isinstance(raw, str)
                    or not re.fullmatch(r'0|-?[1-9][0-9]{0,9}', raw)
                    or not low <= int(raw) <= high or ('values' in field and int(raw) not in field['values'])
                    for raw, label in options.items()):
                raise ValueError(f'{where}: {key} has invalid labels in {name}')


def _validate_parameter_bands(params, where):
    if 'bands' not in params:
        return
    bands = params['bands']
    if not isinstance(bands, dict):
        raise ValueError(f'{where}: bands must be an object')
    count, size, offset = (bands.get(key) for key in ('count', 'length', 'selector_offset'))
    selectors = bands.get('selector_values')
    if (type(count) is not int or type(size) is not int or count <= 0 or size <= 0
            or count * size != params['block_length'] or type(offset) is not int or not 0 <= offset <= size
            or not isinstance(selectors, list) or len(selectors) != count
            or any(not _wire_field_value('u8', selector) for selector in selectors)
            or len(set(selectors)) != count):
        raise ValueError(f'{where}: invalid band layout')



def _validate_parameter_commands(effect):
    """A populated ``commands.parameters`` is a runtime parameter-block contract."""
    implementations = effect.get('implementations') or []
    by_profile = {item.get('profile'): item for item in implementations if isinstance(item, dict)}
    for item in implementations:
        params = ((item.get('commands') or {}) if isinstance(item, dict) else {}).get('parameters')
        if params is None:
            continue
        where = f'AFX {effect["id"]} {item.get("profile")} commands.parameters'
        if (not isinstance(params, dict) or not _wire_field_value('u8', item.get('type_id'))
                or not isinstance(item.get('profile'), str) or not item['profile']
                or type(params.get('writable')) is not bool or not isinstance(params.get('frame'), str)
                or not params['frame'] or type(params.get('block_length')) is not int or params['block_length'] < 1
                or ('editable' in params and type(params['editable']) is not bool)):
            raise ValueError(f'{where}: invalid type, frame, flags or block length')
        if params.get('editable') is not False:
            stride, offset = params.get('read_stride'), params.get('read_offset')
            if (type(stride) is not int or type(offset) is not int or not 0 <= offset
                    or stride <= params['block_length'] or offset + params['block_length'] > stride):
                raise ValueError(f'{where}: invalid read stride or offset')
        _validate_parameter_bands(params, where)
        if params['writable'] != (params.get('editable') is not False):
            raise ValueError(f'{where}: writable must match editable')
        if ('fields' in params) == ('fields_from' in params):
            raise ValueError(f'{where}: needs exactly one of fields and fields_from')
        if 'fields_from' in params:
            if not isinstance(params['fields_from'], str):
                raise ValueError(f'{where}: fields_from must name another implementation')
            source = ((by_profile.get(params['fields_from']) or {}).get('commands') or {}).get('parameters')
            if (params['fields_from'] == item.get('profile') or not isinstance(source, dict)
                    or not isinstance(source.get('fields'), list) or source.get('block_length') != params['block_length']):
                raise ValueError(f'{where}: fields_from must name another implementation of this effect '
                                 'with its own fields and the same block_length')
            continue
        _validate_parameter_fields(params['fields'], params['block_length'], where)


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
