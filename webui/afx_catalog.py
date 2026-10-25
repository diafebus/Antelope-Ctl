"""Presentation metadata for local AFX rack previews; no device commands."""
from antelope import afx
import math

MENU_CATEGORIES = {
    'compressor': 'Dynamics', 'dynamics': 'Dynamics',
    'eq': 'EQ & Filters', 'chorus': 'Modulation', 'modulation': 'Modulation',
    'delay': 'Delay & Reverb', 'reverb': 'Delay & Reverb',
    'pitch': 'Pitch & Tuning', 'amp': 'Amps & Cabinets',
    'preamp': 'Preamps', 'saturation': 'Saturation & Distortion',
}


def presentation_definition(effect, implementation):
    """Sanitize explicitly local UI choices; never derive runtime encodings."""
    presentation = implementation.get('presentation', {})
    if not isinstance(presentation, dict) or presentation.get('status') != 'local-preview':
        return None
    observations = implementation.get('parameter_observation', {}).get('labelled_gui_observations', {})
    encodings = implementation.get('control_encodings', {})
    fields = presentation.get('controls')
    if (not isinstance(observations, dict) or not isinstance(encodings, dict) or
            not isinstance(fields, list) or not 1 <= len(fields) <= 64 or
            any(not isinstance(presentation.get(key), str) or not presentation[key]
                for key in ('name', 'category'))):
        return None
    controls = []
    for field in fields:
        if not isinstance(field, dict):
            return None
        if field.get('source') == 'processing':
            if (field.get('id') != 'processing' or field.get('kind') != 'enum' or
                    implementation.get('bypass_observation', {}).get('status') != 'capture-observed'):
                return None
        else:
            source = field.get('source_control')
            if not isinstance(source, str) or source != field.get('id'):
                return None
            observation = encodings.get(source) or observations.get(source) or {}
            if (not isinstance(observation, dict) or
                    not isinstance(observation.get('status'), str) or
                    not observation['status'].startswith('capture-observed')):
                return None
        control = {key: field[key] for key in ('id', 'label', 'kind', 'range', 'step', 'decimals',
                                               'default', 'options', 'rotary') if key in field}
        if (not isinstance(control.get('id'), str) or not isinstance(control.get('label'), str) or
                not control['id'] or type(control.get('rotary', False)) is not bool):
            return None
        if control.get('kind') == 'continuous':
            bounds = control.get('range', [])
            step, default = control.get('step'), control.get('default')
            if (not isinstance(bounds, list) or len(bounds) != 2 or any(type(v) not in (int, float) or not math.isfinite(v)
                                       for v in [*bounds, step, default]) or
                    not bounds[0] < bounds[1] or step <= 0 or not bounds[0] <= default <= bounds[1]):
                return None
            if type(control.get('decimals', 0)) is not int or not 0 <= control.get('decimals', 0) <= 6:
                return None
        elif control.get('kind') == 'enum':
            options = control.get('options')
            if (not isinstance(options, dict) or len(options) < 2 or
                    any(not isinstance(k, str) or not isinstance(v, str) for k, v in options.items()) or
                    control.get('default') not in options):
                return None
        else:
            return None
        controls.append(control)
    ids = [c['id'] for c in controls]
    rows, switches = presentation.get('rows', []), presentation.get('switches', [])
    if (not isinstance(rows, list) or not rows or
            any(not isinstance(row, list) or not row or any(not isinstance(key, str) for key in row)
                for row in rows) or not isinstance(switches, list) or
            any(not isinstance(key, str) for key in switches)):
        return None
    members = [key for row in rows for key in row] + switches
    if not ids or len(set(ids)) != len(ids) or sorted(members) != sorted(ids):
        return None
    dependencies = presentation.get('dependencies', {})
    if not isinstance(dependencies, dict):
        return None
    by_id = {c['id']: c for c in controls}
    for target, condition in dependencies.items():
        if (target not in ids or by_id[target]['kind'] != 'continuous' or not isinstance(condition, dict) or
                not isinstance(condition.get('control'), str) or condition['control'] not in ids or
                by_id[condition['control']]['kind'] != 'enum' or
                not isinstance(condition.get('values'), list) or not condition['values'] or
                any(not isinstance(value, str) or value not in by_id[condition['control']]['options']
                    for value in condition['values'])):
            return None
    return {'id': effect['id'], 'name': presentation['name'], 'category': presentation['category'],
            'description': effect.get('description'), 'controls': controls,
            'panel': {'rows': rows, 'switches': switches, 'dependencies': dependencies,
                      'family': presentation.get('family', 'SYNERGY CORE')},
            'local_presentation': True}


def panel_definition(effect, implementation):
    """Presentation only; declared display membership excludes opaque bytes.

    Partial captured maps still fail closed. Explicit display-only choices may
    appear in local previews without assigning a wire value or enabling writes.
    """
    if 'presentation' in implementation:
        return presentation_definition(effect, implementation)
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
            if field.get('rotary') is True:
                control['rotary'] = True
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
        choices.append({'id': effect['id'], 'name': panel['name'] if panel else effect['name'],
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
