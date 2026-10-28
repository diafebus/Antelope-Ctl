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
