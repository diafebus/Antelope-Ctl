"""Bounded Orion Memory Cat candidates for explicit operator testing.

These typed builders are the sole exceptions to the generic AFX opcode
guards. They cannot select another effect, device, or unmeasured channel.
"""
from antelope import protocol


def test_contract(profile):
    contract = profile.get('runtime_contracts', {}).get('afx_memorycat_test', {})
    device = profile.get('device', {})
    if (not contract.get('enabled') or not contract.get('experimental')
            or protocol._as_int(device.get('vid', 0)) != 0x23e5
            or protocol._as_int(device.get('pid', 0)) != 0xa221
            or profile.get('transport', {}).get('report_size') != 320
            or contract.get('type_id') != 73 or contract.get('channels') != [0]
            or contract.get('slot_count') != 8
            or contract.get('instance_indices') != list(range(8))):
        raise protocol.ConstraintError('Memory Cat testing is unavailable for this profile')
    protocol.check_readback_index(profile, 0x19, 0)
    return contract


def _integer(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{label} must be an integer in {lo}..{hi}')
    return value


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


def change_chain(profile, slots, operation, slot, *, source=None, instance=None):
    contract = test_contract(profile)
    result = validate_slots(slots)
    _integer(slot, 0, 7, 'slot')
    if operation == 'load':
        if result[slot] != (0, 0):
            raise ValueError('Load requires an empty slot; existing effects are preserved')
        if instance not in contract['instance_indices'] or type(instance) is not int:
            raise ValueError('Instance is outside the captured test range')
        result[slot] = (contract['type_id'], instance)
    elif operation == 'remove':
        if result[slot][0] != contract['type_id']:
            raise ValueError('Only Memory Cat instances can be removed by this test')
        result.pop(slot)
        result.append((0, 0))
    elif operation == 'move':
        _integer(source, 0, 7, 'source slot')
        if result[source][0] != contract['type_id']:
            raise ValueError('Only Memory Cat instances can be moved by this test')
        result.insert(slot, result.pop(source))
    else:
        raise ValueError('Operation must be load, remove, or move')
    return validate_slots(result)


def build_chain_test(profile, slots, *, original_slots=None):
    contract = test_contract(profile)
    if (contract.get('chain_opcode'), contract.get('chain_param_id'),
            contract.get('chain_subcmd')) != ('0x23', '0xd7', '0x11'):
        raise protocol.ConstraintError('Chain frame does not match the captured candidate')
    slots = validate_slots(slots)
    if any(effect_type == 73 and instance not in contract['instance_indices']
           for effect_type, instance in slots):
        raise protocol.ConstraintError('Memory Cat instance is outside the captured test range')
    original = validate_slots(original_slots if original_slots is not None else [(0, 0)] * 8)
    # A caller may preserve foreign effects from readback, never introduce,
    # remove, or duplicate one through the Memory Cat test builder.
    if sorted(slot for slot in slots if slot[0] not in (0, 73)) != sorted(
            slot for slot in original if slot[0] not in (0, 73)):
        raise protocol.ConstraintError('The Memory Cat candidate must preserve all other effects')
    packet = bytearray(320)
    packet[0], packet[4] = 0x70, 0x23
    packet[16:19] = bytes([0xd7, 0x11, 0])
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
