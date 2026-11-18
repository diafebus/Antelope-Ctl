"""Validate captured GUI choices; these are not wire enums or license evidence.

Unknown plugins are deliberately an error here. The launcher may still offer
inventory-only discovery for them, without claiming any known dropdown choices.
"""
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'tools/windows/afx-dropdown-options.json'


def normalized_name(value):
    if not isinstance(value, str):
        raise ValueError('Dropdown names must be strings')
    return re.sub(r'[^a-z0-9]', '', value.lower())


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f'Dropdown {field} must be a nonempty trimmed string')
    return value


def _strings(value, field):
    if not isinstance(value, list):
        raise ValueError(f'Dropdown {field} must be a list')
    for item in value:
        _text(item, field)
    if len(set(value)) != len(value):
        raise ValueError(f'Dropdown {field} must be distinct')
    return value


def _validate_document(document):
    if (not isinstance(document, dict) or type(document.get('version')) is not int
            or document.get('version') != 1 or document.get('profile') != 'orion_studio_sc.json'):
        raise ValueError('Dropdown registry must declare the Orion GUI metadata version')
    sources = document.get('sources')
    if not isinstance(sources, dict) or not sources:
        raise ValueError('Dropdown sources must be a nonempty mapping')
    for source_id, source in sources.items():
        _text(source_id, 'source identity')
        if not isinstance(source, dict):
            raise ValueError('Dropdown source must describe its evidence')
        if source.get('kind') not in ('capture-review', 'owner-confirmation', 'documentation'):
            raise ValueError('Dropdown source kind is unknown')
        _text(source.get('reference'), 'source reference')
        _text(source.get('notes'), 'source notes')

    def references(value):
        refs = _strings(value, 'source references')
        if not refs or any(ref not in sources for ref in refs):
            raise ValueError('Dropdown source reference is missing')

    plugins = document.get('plugins')
    if not isinstance(plugins, list):
        raise ValueError('Dropdown plugin registry is missing')
    ids, names = set(), {}
    for plugin in plugins:
        if not isinstance(plugin, dict):
            raise ValueError('Dropdown plugin must be an object')
        effect_id = _text(plugin.get('effect_id'), 'effect identity')
        if effect_id in ids:
            raise ValueError('Duplicate dropdown effect identity')
        ids.add(effect_id)
        aliases = _strings(plugin.get('aliases', []), 'aliases')
        for name in [effect_id, _text(plugin.get('name'), 'plugin name'), *aliases]:
            key = normalized_name(name)
            if not key or key in names and names[key] != effect_id:
                raise ValueError('Ambiguous dropdown plugin name')
            names[key] = effect_id
        if plugin.get('hardware_testing') not in ('allowed', 'excluded'):
            raise ValueError('Dropdown hardware testing policy is missing')
        references(plugin.get('source_ids'))
        _strings(plugin.get('unresolved', []), 'unresolved evidence')
        dropdowns = plugin.get('dropdowns')
        if not isinstance(dropdowns, list):
            raise ValueError('Dropdown controls must be a list')
        controls = set()
        for dropdown in dropdowns:
            if not isinstance(dropdown, dict):
                raise ValueError('Dropdown control must be an object')
            control_id = _text(dropdown.get('id'), 'control identity')
            if control_id in controls:
                raise ValueError('Duplicate dropdown control identity')
            controls.add(control_id)
            for field in ('label', 'class_name', 'status', 'full_count_status'):
                _text(dropdown.get(field), field)
            options = dropdown.get('options')
            if not isinstance(options, list) or any(not isinstance(option, dict)
                    or set(option) != {'label'} for option in options):
                raise ValueError('Dropdown options must contain GUI labels only')
            labels = _strings([option['label'] for option in options], 'labels')
            if dropdown.get('ordering') not in ('unknown', 'capture-observed', 'manual-listed'):
                raise ValueError('Dropdown ordering is unknown')
            if dropdown.get('selection_policy', 'inventory-only') not in ('inventory-only', 'reviewed-parameter-trial'):
                raise ValueError('Dropdown selection policy is unknown')
            if labels and dropdown['ordering'] == 'unknown':
                raise ValueError('Known dropdown labels need evidenced ordering')
            count = dropdown.get('full_count')
            if count is not None and (type(count) is not int or count < max(1, len(labels))):
                raise ValueError('Dropdown full count conflicts with observed choices')
            references(dropdown.get('source_ids'))
    return document


def load_dropdown_options(path=REGISTRY):
    return _validate_document(json.loads(Path(path).read_text(encoding='utf-8')))


def find_plugin(name, document=None):
    document = _validate_document(document) if document is not None else load_dropdown_options()
    key = normalized_name(name)
    matches = [plugin for plugin in document['plugins'] if key in {
        normalized_name(value) for value in [plugin['effect_id'], plugin['name'], *plugin.get('aliases', [])]}]
    if len(matches) != 1:
        raise ValueError('Plugin name is missing or ambiguous in the dropdown registry')
    return matches[0]


def key_control_options(effect_id, control, document=None):
    plugin = find_plugin(effect_id, document)
    if plugin.get('hardware_testing') == 'excluded':
        raise ValueError('Plugin is excluded from hardware capture')
    if not isinstance(control, dict):
        raise ValueError('Key target must be a control object')
    matches = [d for d in plugin['dropdowns'] if d['id'] == control.get('dropdown_id')]
    if len(matches) != 1:
        raise ValueError('Key target is missing from the dropdown registry')
    dropdown = matches[0]
    if dropdown.get('selection_policy', 'inventory-only') != 'reviewed-parameter-trial':
        raise ValueError('Inventory-only dropdown cannot be used for a key trial')
    labels = [option['label'] for option in dropdown.get('options', [])]
    if (dropdown.get('class_name') != control.get('class_name') or
            dropdown.get('ordering') not in ('capture-observed', 'manual-listed') or not 2 <= len(labels) <= 8):
        raise ValueError('Key trial needs a measured GUI class and ordered known choices')
    return labels
