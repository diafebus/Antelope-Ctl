"""Presentation metadata for local AFX rack previews; no device commands."""
from antelope import afx

MENU_CATEGORIES = {
    'compressor': 'Dynamics', 'dynamics': 'Dynamics',
    'eq': 'EQ & Filters', 'chorus': 'Modulation', 'modulation': 'Modulation',
    'delay': 'Delay & Reverb', 'reverb': 'Delay & Reverb',
    'pitch': 'Pitch & Tuning', 'amp': 'Amps & Cabinets',
    'preamp': 'Preamps', 'saturation': 'Saturation & Distortion',
}


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
        choices.append({'id': effect['id'], 'name': effect['name'],
                        'category': MENU_CATEGORIES.get(effect.get('category'), 'Other'),
                        'type_id': type_id,
                        'loadable': bool(spec and spec['type_id'] == type_id)})
    return sorted(choices, key=lambda item: item['name'].casefold())


def preview_catalog(catalog, profile_name):
    effects = []
    for effect in catalog.get("effects", []):
        implementation = next((item for item in effect.get("implementations", [])
                               if item.get("profile") == profile_name), None)
        if not implementation:
            continue
        encodings = implementation.get("control_encodings", {})
        controls = []
        for declaration in effect.get("controls", []):
            control_id = declaration["id"]
            field = encodings.get(control_id, {})
            if field.get("status") != "capture-observed":
                continue
            control = {"id": control_id,
                       "label": field.get("label", declaration["label"]),
                       "kind": field.get("kind")}
            if control["kind"] == "continuous" and field.get("display_range"):
                control["range"] = field["display_range"]
            elif control["kind"] == "enum" and field.get("options"):
                control["options"] = field["options"]
            else:
                continue
            controls.append(control)
        # A partial field map must not silently produce a partial effect panel.
        if controls and len(controls) == len(effect.get("controls", [])):
            effects.append({"id": effect["id"], "name": effect["name"],
                            "description": effect.get("description"),
                            "controls": controls})
    return {"mode": "preview", "device_writes": False, "effects": effects}
