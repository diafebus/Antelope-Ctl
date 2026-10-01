"""Bounded Orion AFX candidates for explicit operator testing.

These typed builders are the sole exceptions to the generic AFX opcode
guards. Only independently captured effects and measured indices are accepted.
"""
from antelope import protocol


def test_contract(profile):
    contract = profile.get('runtime_contracts', {}).get('afx_memorycat_test', {})
    device = profile.get('device', {})
    if (not contract.get('enabled') or not contract.get('experimental')
            or protocol._as_int(device.get('vid', 0)) != 0x23e5
            or protocol._as_int(device.get('pid', 0)) != 0xa221
            or profile.get('transport', {}).get('report_size') != 320
            or contract.get('type_id') != 73 or contract.get('channels') != list(range(32))
            or contract.get('slot_count') != 8
            or contract.get('instance_indices') != list(range(8))):
        raise protocol.ConstraintError('Memory Cat testing is unavailable for this profile')
    protocol.check_readback_index(profile, 0x19, 0)
    return contract


def test_channel(profile, channel):
    contract = test_contract(profile)
    _integer(channel, 0, 31, 'AFX channel')
    if channel not in contract['channels']:
        raise protocol.ConstraintError('AFX channel is outside the operator test contract')
    protocol.check_readback_index(profile, 0x19, channel)
    return channel


def _integer(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{label} must be an integer in {lo}..{hi}')
    return value


def load_effects(profile):
    base = test_contract(profile)
    fallback = {'memory_brigade': {'type_id': 73, 'name': 'Memory Cat Brigade',
                                  'instance_indices': base['instance_indices']}}
    rack = profile.get('runtime_contracts', {}).get('afx_rack_test', {})
    if not rack.get('enabled'):
        return fallback
    if (not rack.get('experimental') or rack.get('channels') != list(range(32))
            or rack.get('slot_count') != 8):
        raise protocol.ConstraintError('AFX rack testing is unavailable for this profile')
    observed = {'memory_brigade': (73, list(range(8))), 'instinct': (75, [0, 1]),
                'deesser': (27, [0, 1]), 'turboensembler': (70, [0, 1]),
                'bbdchorus': (78, [0, 1])}
    effects = rack.get('effects', {})
    for name, spec in effects.items():
        if name not in observed or (spec.get('type_id'), spec.get('instance_indices')) != observed[name]:
            raise protocol.ConstraintError('Effect is outside the independently captured Orion set')
    return effects


def validate_slots(slots):
    if len(slots) != 8:
        raise ValueError('An AFX chain must contain exactly eight slots')
    result = []
    for effect_type, instance in slots:
        result.append((_integer(effect_type, 0, 255, 'type'),
                       _integer(instance, 0, 255, 'instance')))
        if not effect_type and instance:
            raise ValueError('An empty slot must be {0,0}')
    active = [slot for slot in result if slot[0]]
    if len(set(active)) != len(active):
        raise ValueError('The same instance cannot occupy two slots')
    return result


def change_chain(profile, slots, operation, slot, *, source=None, instance=None,
                 effect_id='memory_brigade'):
    effects = load_effects(profile)
    known_types = {spec['type_id'] for spec in effects.values()}
    result = validate_slots(slots)
    _integer(slot, 0, 7, 'slot')
    if operation in ('load', 'replace'):
        if operation == 'load' and result[slot] != (0, 0):
            raise ValueError('Load requires an empty slot; existing effects are preserved')
        if operation == 'replace' and result[slot][0] not in known_types:
            raise ValueError('Only captured effect types can be replaced')
        if effect_id not in effects:
            raise ValueError('Effect loading is not mapped for this Orion profile')
        spec = effects[effect_id]
        if instance not in spec['instance_indices'] or type(instance) is not int:
            raise ValueError('Instance is outside the captured test range')
        result[slot] = (spec['type_id'], instance)
    elif operation == 'remove':
        if result[slot][0] not in known_types:
            raise ValueError('Only captured effect types can be removed by this test')
        result.pop(slot)
        result.append((0, 0))
    elif operation == 'move':
        _integer(source, 0, 7, 'source slot')
        if result[source][0] not in known_types:
            raise ValueError('Only captured effect types can be moved by this test')
        result.insert(slot, result.pop(source))
    else:
        raise ValueError('Operation must be load, replace, remove, or move')
    return validate_slots(result)


def build_chain_test(profile, slots, *, original_slots=None, channel=0):
    contract = test_contract(profile)
    test_channel(profile, channel)
    if (contract.get('chain_opcode'), contract.get('chain_param_id'),
            contract.get('chain_subcmd')) != ('0x23', '0xd7', '0x11'):
        raise protocol.ConstraintError('Chain frame does not match the captured candidate')
    slots = validate_slots(slots)
    types = {spec['type_id']: spec for spec in load_effects(profile).values()}
    if any(effect_type in types and instance not in types[effect_type]['instance_indices']
           for effect_type, instance in slots):
        raise protocol.ConstraintError('Effect instance is outside the captured test range')
    original = validate_slots(original_slots if original_slots is not None else [(0, 0)] * 8)
    # A caller may preserve foreign effects from readback, never introduce,
    # remove, or duplicate one through the captured-effect test builder.
    if sorted(slot for slot in slots if slot[0] and slot[0] not in types) != sorted(
            slot for slot in original if slot[0] and slot[0] not in types):
        raise protocol.ConstraintError('The AFX candidate must preserve all unknown effects')
    packet = bytearray(320)
    packet[0], packet[4] = 0x70, 0x23
    packet[16:19] = bytes([0xd7, 0x11, channel])
    packet[19:35] = bytes(value for slot in slots for value in slot)
    return bytes(packet)


def validate_parameters(profile, values):
    contract = test_contract(profile)
    expected = dict(blend=20, level=21, feedback=22, chrs_vibr=23,
                    depth=24, delay=25, lpf_fc=26, size=27)
    if contract['parameter_offsets'] != expected:
        raise protocol.ConstraintError('Parameter fields do not match the captured Memory Cat block')
    for name in expected:
        if contract['parameter_ranges'].get(name) != [0, 1 if name in ('chrs_vibr', 'size') else 100]:
            raise protocol.ConstraintError('Parameter range does not match the Memory Cat candidate')
    if set(values) != set(contract['parameter_offsets']):
        raise ValueError('All eight Memory Cat settings must be supplied explicitly')
    return {name: _integer(values[name], *contract['parameter_ranges'][name], name)
            for name in contract['parameter_offsets']}


def build_parameter_test(profile, instance, values):
    contract = test_contract(profile)
    if instance not in contract['instance_indices'] or type(instance) is not int:
        raise ValueError('Instance is outside the captured test range')
    if (contract.get('parameter_opcode'), contract.get('parameter_param_id'),
            contract.get('parameter_subcmd')) != ('0x1c', '0xd5', '0x0a'):
        raise protocol.ConstraintError('Parameter frame does not match the captured candidate')
    values = validate_parameters(profile, values)
    packet = bytearray(320)
    packet[0], packet[4] = 0x70, 0x1c
    packet[16:20] = bytes([0xd5, 0x0a, 73, instance])
    for name, offset in contract['parameter_offsets'].items():
        packet[offset] = values[name]
    return bytes(packet)
