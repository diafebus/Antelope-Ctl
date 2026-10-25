"""Build bounded GUI discovery plans from live UI metadata, never wire guesses."""
import math
import re


def key(value):
    if not isinstance(value, str):
        raise ValueError('Inventory identity must be text')
    return re.sub(r'[^a-z0-9]', '', value.lower())


def rectangle(value):
    if not isinstance(value, dict) or any(type(value.get(k)) not in (int, float)
            or not math.isfinite(value[k]) for k in ('x', 'y', 'width', 'height')):
        raise ValueError('Invalid inventory rectangle')
    if value['width'] <= 0 or value['height'] <= 0:
        raise ValueError('Empty inventory rectangle')
    return value


def contains(outer, inner):
    return (inner['x'] >= outer['x'] and inner['y'] >= outer['y']
            and inner['x'] + inner['width'] <= outer['x'] + outer['width']
            and inner['y'] + inner['height'] <= outer['y'] + outer['height'])


def discovery_plan(inventory, catalog):
    """Only uniquely named Pot controls in an identified Orion effect panel."""
    if not isinstance(inventory, dict) or inventory.get('version') != 1 or inventory.get('process_name') != 'orionstudioiii':
        raise ValueError('Discovery requires Orion UI inventory')
    name = inventory['panel_name']
    effects = [e for e in catalog['effects'] if key(name) in
               {key(e['id']), key(e['name']), key(e.get('source_name', ''))}]
    if len(effects) != 1 or effects[0]['id'] == 'antares_autotune':
        raise ValueError('Plugin name must identify one catalog effect; Auto-Tune is unavailable')
    effect = effects[0]
    implementations = [i for i in effect['implementations'] if i['profile'] == 'orion_studio_sc.json']
    if len(implementations) != 1 or type(implementations[0].get('type_id')) is not int:
        raise ValueError('Orion effect type has not been captured; inventory retained')
    methods = implementations[0].get('parameter_observation', {}).get('gui_control_methods', {})
    panel_class = inventory['panel_class']
    # User-facing names can differ from Qt class names. Accept catalog identity
    # or the already reviewed workflow class, never an arbitrary common ancestor.
    identities = {key(effect['id']), key(effect['name']), key(effect.get('source_name', ''))}
    if key(panel_class) not in identities:
        raise ValueError('Detected panel class does not match the catalog effect; identity review needed')
    panel = rectangle(inventory['panel_bounds'])
    size = inventory['window_size']
    window = rectangle({'x': 0, 'y': 0, **size})
    if not contains(window, panel):
        raise ValueError('Plugin panel is outside the captured window')
    rows = inventory['controls']
    if not isinstance(rows, list) or len(rows) > 512:
        raise ValueError('Inventory exceeds the bounded panel tree')
    if any(not isinstance(row, dict) or not isinstance(row.get('class_name', ''), str)
           or not isinstance(row.get('values', {}), dict) for row in rows):
        raise ValueError('Malformed control inventory')
    controls, pending = [], []
    for row in rows:
        cls = row.get('class_name', '')
        editable = ('Pot' in cls or row.get('control_type') in
                    ('ControlType.ComboBox', 'ControlType.CheckBox', 'ControlType.Button')
                    or re.search(r'(Button|Switch|Select|Cabinet|Speaker)', cls))
        if not editable:
            continue
        reason = None
        if not re.fullmatch(r'[A-Za-z0-9_-]+', cls) or sum(r.get('class_name') == cls for r in rows) != 1:
            reason = 'ambiguous control identity'
        elif not contains(panel, rectangle(row['window_relative_bounds'])):
            reason = 'outside plugin panel'
        elif row.get('enabled') is not True or row.get('offscreen') is not False:
            reason = 'disabled or hidden; dependency unresolved'
        elif re.search(r'(preset|program|model|cabinet|speaker|select)', cls, re.I):
            reason = 'selection may change multiple parameters; inventory only'
        elif re.search(r'(bypass|power)', cls[len(panel_class):] if cls.startswith(panel_class) else cls, re.I):
            reason = 'processing switch requires a measured method; Pot class does not establish a knob'
        elif (row.get('control_type') == 'ControlType.CheckBox' and
              'TogglePatternIdentifiers.Pattern' in row.get('patterns', []) and
              row.get('values', {}).get('toggle') in ('On', 'Off') and
              key(cls).startswith(key(panel_class)) and 'bypass' not in cls.lower()):
            if methods.get(cls, {}).get('kind') == 'selector_cycle':
                pending.append({'control': cls, 'reason':
                    'capture-observed multi-state selector; TogglePattern does not establish a binary control'})
                continue
            controls.append({'id': cls, 'class_name': cls, 'label': row.get('name') or cls,
                             'kind': 'binary_button', 'feedback': 'gui_toggle'})
            continue
        elif 'Pot' not in cls:
            reason = 'selector/switch requires a measured method; presets inventory only'
        elif not key(cls).startswith(key(panel_class)):
            reason = 'knob class not scoped to this plugin'
        if reason:
            pending.append({'control': cls, 'reason': reason})
            continue
        controls.append({'id': cls, 'class_name': cls, 'label': row.get('name') or cls,
                         'kind': 'knob_range', 'feedback': 'captured_block'})
    if not 1 <= len(controls) <= (24 if any(c['kind'] == 'knob_range' for c in controls) else 3):
        raise ValueError('No bounded set of automatically supported knobs; inventory retained')
    return {'id': 'discover-' + effect['id'], 'panel': effect['id'],
            'panel_class': panel_class, 'effect_id': effect['id'],
            'process_name': 'orionstudioiii', 'channel': 2,
            'status': 'candidate knob endpoint discovery; no numeric range proof',
            'controls': controls, 'coverage': {'status': 'partial; endpoint candidates require review',
                                             'pending': pending, 'device_readback_verified': False}}


def block_feedback(reports, effect_type, instance, after_frame, previous=None, out_endpoint=1, opcodes=(0x16, 0x18, 0x1a, 0x1c, 0x1d, 0x20, 0x7c)):
    samples = [(n, data) for n, _, ep, data in reports if n > after_frame
               and ep == out_endpoint and len(data) >= 20 and data[0] == 0x70
               and data[16] == 0xd5 and data[18] == effect_type and data[19] == instance
               and data[4] in opcodes]
    payload = samples[-1][1][20:].hex() if samples else None
    stable = payload is not None and previous is not None and payload == previous
    return {'parameter_payload_hex': payload, 'continue': not stable,
            'plateau_observed': stable, 'endpoint_verified': False,
            'source': 'stable captured block candidate; physical endpoint and field offsets require review'}
