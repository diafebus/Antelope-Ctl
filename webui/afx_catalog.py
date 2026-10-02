"""Presentation metadata for local AFX rack previews; no device commands."""
from antelope import afx

MENU_CATEGORIES = {
    'compressor': 'Dynamics', 'dynamics': 'Dynamics',
    'eq': 'EQ & Filters', 'chorus': 'Modulation', 'modulation': 'Modulation',
    'delay': 'Delay & Reverb', 'reverb': 'Delay & Reverb',
    'pitch': 'Pitch & Tuning', 'amp': 'Amps & Cabinets',
    'preamp': 'Preamps', 'saturation': 'Saturation & Distortion',
}


def panel_definition(effect, implementation):
    """Presentation only; declared display membership excludes opaque bytes.

    Partial captured maps still fail closed. Explicit display-only choices may
    appear in local previews without assigning a wire value or enabling writes.
    """
    panel = effect.get('panel', {})
    required = ([key for row in panel.get('rows', []) for key in row]
                + panel.get('switches', [])) or [c['id'] for c in effect.get('controls', [])]
    declarations = {c['id']: c for c in effect.get('controls', [])}
    encodings = implementation.get('control_encodings', {})
    controls = []
    for key in required:
        declaration = declarations.get(key, {})
        field = encodings.get(key, {})
        display_only = panel.get('display_only_controls', {}).get(key)
        if display_only:
            controls.append({'id': key, 'label': display_only['label'],
                             'kind': 'enum', 'options': display_only['options'],
                             'device_available': False})
            continue
        if field.get('status') != 'capture-observed':
            return None
        control = {'id': key, 'label': field.get('label', declaration.get('label', key)),
                   'kind': field.get('kind')}
        if control['kind'] == 'continuous' and field.get('display_range'):
            control['range'] = field['display_range']
            if 'display_center' in field:
                control['display_center'] = field['display_center']
        elif control['kind'] == 'enum' and field.get('options'):
            control['options'] = field['options']
        else:
            return None
        controls.append(control)
    if not controls:
        return None
    return {'id': effect['id'], 'name': effect['name'],
            'description': effect.get('description'), 'controls': controls,
            **({'panel': {key: panel[key] for key in ('rows', 'switches', 'dependencies') if key in panel}} if panel else {})}


def effect_choices(catalog, profile_name, profile):
    try:
        allowed = afx.load_effects(profile)
    except (ValueError, KeyError):
        allowed = {}
    choices = []
    for effect in catalog.get('effects', []):
        implementation = next((item for item in effect.get('implementations', [])
                               if item.get('profile') == profile_name), {})
        spec = allowed.get(effect['id'])
        type_id = implementation.get('type_id')
        panel = panel_definition(effect, implementation)
        choices.append({'id': effect['id'], 'name': effect['name'],
                        'category': MENU_CATEGORIES.get(effect.get('category'), 'Other'),
                        'type_id': type_id,
                        'loadable': bool(spec and spec['type_id'] == type_id),
                        **({'panel': panel} if panel else {})})
    return sorted(choices, key=lambda item: item['name'].casefold())


def preview_catalog(catalog, profile_name):
    effects = []
    for effect in catalog.get("effects", []):
        implementation = next((item for item in effect.get("implementations", [])
                               if item.get("profile") == profile_name), None)
        if not implementation:
            continue
        panel = panel_definition(effect, implementation)
        if panel:
            effects.append(panel)
    return {"mode": "preview", "device_writes": False, "effects": effects}
