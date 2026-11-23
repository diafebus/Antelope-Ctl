"""Generic profile-driven AFX codec and frame builders (protocol.py).

The profiles below are small inline fragments, not shipped device data. Their
frames, offsets and ranges come from vendor-panel captures on a Zen Go Synergy
Core and a Discrete 4 (fork of this project, owner's units, 2026-11); field
lists are trimmed to what each test needs. The Orion test uses the shipped
Orion profile and its existing Memory Cat contract only.
"""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from antelope import afx, protocol
from antelope.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]
COMMAND = {'magic_offset': 0, 'magic': '0x70', 'opcode_offset': 4, 'param_id_offset': 16}
READBACK = {'magic_offset': 0, 'request_magic': '0x74', 'response_magic': '0x75',
            'response_discriminator_offset': 1, 'response_discriminator': '0x00',
            'subcmd': '0x10', 'subcmd_offset': 4, 'category_offset': 8, 'index_offset': 12, 'data_offset': 16}
WRITE = {'param_id': '0xd5', 'length_bias': '0x12'}
BYPASS = {'param_id': '0x98', 'opcode': '0x14'}
CLEARQ_DEFAULTS = ('1e 00 47 00 00 00 00 | c8 00 47 00 00 00 02 | e8 03 47 00 00 00 02 | '
                   '88 13 47 00 00 00 02 | 98 3a 47 00 00 00 01')
CLEARQ_BANDS = ['00 1e 00 47 00 00 00 00', '01 c8 00 47 00 00 00 02', '02 e8 03 47 00 00 00 02',
                '03 88 13 47 00 00 00 02', '04 98 3a 47 00 00 00 01']
AMP_DEFAULTS = '00 46 3e 3f 00 44 00 32 59 00 01 00 00 00 00 00'


def field(key, offset, kind, lo, hi, **extra):
    return dict(key=key, label=key, offset=offset, type=kind, min=lo, max=hi, **extra)


def effect(length, *fields, **extra):
    return dict(block_length=length, fields=list(fields), **extra)


CLEARQ = effect(35, field('b1_freq', 0, 'u16', 20, 800), field('b1_gain', 4, 'i16', -2400, 1200),
                field('b1_shape', 6, 'u8', 0, 4, values=[0, 4]), field('b2_freq', 7, 'u16', 20, 800),
                field('b2_q', 9, 'u16', 50, 1800), field('b2_gain', 11, 'i16', -2400, 1200),
                field('b3_freq', 14, 'u16', 125, 8000), field('b3_q', 16, 'u16', 50, 1800),
                field('b3_gain', 18, 'i16', -2400, 1200), field('b4_freq', 21, 'u16', 400, 20000),
                field('b4_q', 23, 'u16', 50, 1800), field('b4_gain', 25, 'i16', -2400, 1200),
                field('b5_freq', 28, 'u16', 400, 20000), field('b5_gain', 32, 'i16', -2400, 1200),
                field('b5_shape', 34, 'u8', 1, 3, values=[1, 3]),
                bands={'count': 5, 'length': 7, 'selector_offset': 0, 'selector_values': [0, 1, 2, 3, 4]})
AMP = effect(16, field('model', 0, 'u8', 0, 10), field('volume', 8, 'u8', 0, 100),
             field('output', 15, 'i8', -48, 12), defaults=AMP_DEFAULTS)
POWERGATE = effect(9, field('threshold', 0, 'u8', 0, 120), field('range', 1, 'u8', 0, 20),
                   field('attack', 2, 'u16', 1, 750), field('decay', 4, 'u16', 1, 1000),
                   field('hold', 6, 'u16', 0, 5000), field('gain', 8, 'i8', -24, 12))
POWERFFC = effect(18, field('attack', 0, 'u32', 100, 150000), field('release', 4, 'u32', 1000, 600000),
                  field('detector', 8, 'u16', 2000, 65535, values=[65535, 2000, 5000, 10000, 15000, 20000]),
                  field('ratio', 10, 'u16', 100, 2000), field('gain', 12, 'u16', 0, 2400),
                  field('threshold', 15, 'u8', 0, 80), field('knee', 16, 'u8', 0, 30))
FET_A76 = effect(5, field('ratio', 4, 'u8', 0, 8, values=[0, 1, 2, 4, 8]))
INSTINCT = effect(104, field('punch', 0, 'f32', 0.0, 1.0), field('boost_freq', 16, 'f32', 0.0, 100.0),
                  field('centre_knob', 24, 'f32', 0.0, 100.0), field('filter_freq', 32, 'f32', 0.0, 100.0),
                  field('filter_q', 36, 'f32', 0.01, 1.0), field('volume', 100, 'f32', 0.0, 1.0))


def device(chain, query_targets, effects, write_effects, allowed, *, chain_instances,
           parameter_instances, bypass_instances):
    return {
        'transport': {'report_size': 320},
        'frame': {'command': COMMAND, 'readback': READBACK},
        'constraints': {'allowed_opcodes': allowed},
        'afx_inserts': {
            'type_labels': {kind: kind for kind in (*effects, '73')},
            'chain_write': dict(magic_offset=0, magic='0x70', opcode_offset=4, param_id_offset=16,
                                param_id='0xd7', subcmd_offset=17, strip_offset=18, slots_offset=19, **chain),
            'writes': {'enabled': True, 'strips': [0, 1, 2, 3], 'max_slots': 4, 'effects': write_effects,
                       'instances': chain_instances},
            'parameters': {'enabled': True, 'write': {**WRITE, 'instances': parameter_instances},
                           'state_query': {'targets': query_targets},
                           'bypass': {**BYPASS, 'instances': bypass_instances}, 'effects': effects},
        },
    }


def zen_go():
    return device({'opcode': '0x23', 'subcmd': '0x11'},
                  {'1': [0x07, 0x10, 0x80000001], '29': [0x07, 0x11, 0x8000001d]},
                  {'1': CLEARQ, '3': AMP, '9': FET_A76,
                   '27': effect(12), '29': effect(3, field('threshold', 0, 'u8', 0, 100),
                                                 field('ratio', 1, 'u8', 0, 60), field('output', 2, 'u8', 0, 100)),
                   '39': POWERGATE, '51': effect(1), '74': effect(11, field('output', 0, 'u8', 0, 100)),
                   '75': INSTINCT},
                  {'1': {'load_defaults': CLEARQ_BANDS}, '3': {'load_defaults': [AMP_DEFAULTS]}},
                  ['0x12', '0x13', '0x14', '0x16', '0x1d', '0x23', '0x53', '0x54'],
                  chain_instances={'1': [1], '3': [0], '27': [1], '39': [0], '51': [0]},
                  parameter_instances={'1': [0], '29': [0], '75': [0]}, bypass_instances={'74': [0]})


def discrete_4():
    return device({'opcode': '0x5b', 'subcmd': '0x49'},
                  {'1': [0x07, 0x10, 0]},
                  {'1': CLEARQ, '2': POWERFFC, '3': AMP,
                   '27': effect(12, field('threshold', 1, 'u8', 0, 80)), '39': POWERGATE, '51': effect(1)},
                  {'1': {'load_defaults': CLEARQ_BANDS}, '3': {'load_defaults': [AMP_DEFAULTS]}, '39': {}},
                  ['0x12', '0x13', '0x14', '0x16', '0x1d', '0x53', '0x54', '0x5b'],
                  chain_instances={'1': [0], '3': [0], '27': [0, 1], '39': [0], '51': [0]},
                  parameter_instances={'1': [0], '2': [0], '3': [0], '39': [0]},
                  bypass_instances={'27': [1], '39': [0, 1]})


def orion():
    return json.loads((ROOT / 'profiles' / 'orion_studio_sc.json').read_text())


def payload(packet):
    return packet[16:].rstrip(b'\0').hex(' ')


class ChainWriteTests(unittest.TestCase):
    def test_zen_go_frames_match_capture(self):
        cases = [([(27, 1)], 'd7 11 01 1b 01'),
                 ([(27, 1), (39, 0)], 'd7 11 01 1b 01 27'),
                 ([(27, 1), (39, 0), (51, 0)], 'd7 11 01 1b 01 27 00 33'),
                 ([(51, 0)], 'd7 11 01 33'),
                 ([], 'd7 11 01')]
        for slots, expected in cases:
            packet = protocol.build_afx_insert_chain(zen_go(), 1, slots)
            self.assertEqual(len(packet), 320)
            self.assertEqual(packet[:5].hex(' '), '70 00 00 00 23')
            self.assertEqual(payload(packet), expected)

    def test_discrete_4_frames_match_capture(self):
        cases = [(0, [(27, 0)], 'd7 49 00 1b'),
                 (0, [(27, 1)], 'd7 49 00 1b 01'),
                 (1, [(27, 0), (39, 0), (51, 0)], 'd7 49 01 1b 00 27 00 33'),
                 (1, [], 'd7 49 01'),
                 (0, [], 'd7 49')]
        for strip, slots, expected in cases:
            packet = protocol.build_afx_insert_chain(discrete_4(), strip, slots)
            self.assertEqual(packet[:5].hex(' '), '70 00 00 00 5b')
            self.assertEqual(payload(packet), expected)

    def test_contract_is_enforced(self):
        refused = [(4, [(27, 0)]),                          # strip outside writes.strips
                   (0, [(73, 0)]),                          # label exists, but no write contract
                   (0, [(27, 0), (27, 0)]),                 # repeated instance
                   (0, [(27, 0), (27, 1.5)]),               # instance is an integer
                   (0, [(27, 0), (27, 255)]),               # byte-sized but unmeasured
                   (0, [(27, 0), (27, 256)]),               # instance is one byte
                   (0, [(27, i) for i in range(5)])]        # more than max_slots
        for strip, slots in refused:
            with self.assertRaises(protocol.ConstraintError, msg=(strip, slots)):
                protocol.build_afx_insert_chain(discrete_4(), strip, slots)
        disabled = discrete_4()
        disabled['afx_inserts']['writes']['enabled'] = False
        self.assertIsNone(protocol.afx_insert_writes(disabled))
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_insert_chain(disabled, 0, [])


class ParameterCodecTests(unittest.TestCase):
    def test_powergate_frames_match_capture(self):
        profile = discrete_4()
        gate = protocol.afx_parameter_effect(profile, 39)
        defaults = bytes.fromhex('5a0064003200000000')
        self.assertEqual(protocol.afx_block_get(gate, defaults),
                         {'threshold': 90, 'range': 0, 'attack': 100, 'decay': 50, 'hold': 0, 'gain': 0})
        cases = [('threshold', 91, '27 00 5b 00 64 00 32 00 00 00 00'),
                 ('attack', 110, '27 00 5a 00 6e 00 32 00 00 00 00'),
                 ('hold', 40, '27 00 5a 00 64 00 32 00 28 00 00'),
                 ('range', 1, '27 00 5a 01 64 00 32 00 00 00 00'),
                 ('decay', 60, '27 00 5a 00 64 00 3c 00 00 00 00'),
                 ('gain', 1, '27 00 5a 00 64 00 32 00 00 00 01')]
        for key, value, expected in cases:
            packet = protocol.build_afx_parameter_write(
                profile, 39, 0, protocol.afx_block_set(gate, defaults, key, value))
            self.assertEqual(packet[:5].hex(' '), '70 00 00 00 1d')
            self.assertEqual(packet[16:18].hex(' '), 'd5 0b')
            self.assertEqual(packet[18:29].hex(' '), expected)
            self.assertFalse(any(packet[29:]))
        self.assertEqual(protocol.afx_block_get(
            gate, protocol.afx_block_set(gate, defaults, 'gain', -24))['gain'], -24)
        for key, value in (('gain', 13), ('attack', 0), ('hold', 5001), ('unknown', 1), ('threshold', 91.0)):
            with self.assertRaises(protocol.ConstraintError, msg=(key, value)):
                protocol.afx_block_set(gate, defaults, key, value)
        with self.assertRaises(protocol.ConstraintError):   # wrong block length
            protocol.afx_block_set(gate, defaults[:8], 'gain', 0)
        with self.assertRaises(protocol.ConstraintError):
            protocol.afx_block_get(gate, defaults[:-1])
        with self.assertRaises(protocol.ConstraintError):
            protocol.afx_block_get(dict(gate, fields=[*gate['fields'], field('alias', 1, 'u8', 0, 1)]),
                                   defaults)
        with self.assertRaises(protocol.ConstraintError):
            protocol.afx_block_get(dict(gate, fields=[field('overrun', 8, 'u16', 0, 1)]), defaults)
        with self.assertRaises(protocol.ConstraintError):   # a block holding an out-of-range value is not sent
            protocol.build_afx_parameter_write(profile, 39, 0, bytes.fromhex('790064003200000000'))
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_parameter_write(profile, 39, 255, defaults)
        profile['transport']['report_size'] = 28
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_parameter_write(profile, 39, 0, defaults)
        self.assertIsNone(protocol.afx_parameter_effect(profile, 4))   # unmapped type
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_parameter_write(profile, 4, 0, defaults)

    def test_u32_fields_and_selector_values(self):
        profile = discrete_4()
        ffc = protocol.afx_parameter_effect(profile, 2)
        block = bytes.fromhex('1027000010270000ffff640000000018' '0000')
        self.assertEqual(protocol.afx_block_get(ffc, block)['release'], 10000)
        changed = protocol.afx_block_set(ffc, block, 'release', 600000)
        self.assertEqual(changed[4:8].hex(' '), 'c0 27 09 00')
        packet = protocol.build_afx_parameter_write(profile, 2, 0, changed)
        self.assertEqual(packet[4], 0x14 + 0x12)
        self.assertEqual(packet[16:20].hex(' '), 'd5 14 02 00')
        ratio = protocol.afx_parameter_effect(zen_go(), 9)['fields'][0]
        self.assertEqual([value for value in range(-1, 10) if protocol.afx_field_in_range(ratio, value)],
                         [0, 1, 2, 4, 8])
        with self.assertRaises(protocol.ConstraintError):
            protocol.afx_block_set(ffc, block, 'detector', 3000)

    def test_float_fields_round_trip_and_refuse_bad_values(self):
        zen = zen_go()
        instinct = protocol.afx_parameter_effect(zen, 75)
        half, zero = '0000003f', '00000000'
        # The Instinct block the Zen Go held before the first control was moved.
        block = bytes.fromhex(half * 4 + '0000c842' + half + zero + half + '0000c442' + half * 2 + '0000803f'
                              + zero * 3 + half * 4 + '0000c442' + half * 3 + zero + half * 2)
        values = protocol.afx_block_get(instinct, block)
        self.assertEqual((values['punch'], values['boost_freq'], values['filter_freq'], values['centre_knob']),
                         (0.5, 100.0, 98.0, 0.0))
        changed = protocol.afx_block_set(instinct, block, 'punch', 0.51)
        self.assertEqual((changed[:4].hex(), changed[4:]), ('5c8f023f', block[4:]))   # the frame the panel sent
        # The read-back float (0.50999999...) encodes to the same bytes; an int is taken as a float.
        self.assertEqual(protocol.afx_block_set(
            instinct, block, 'punch', protocol.afx_block_get(instinct, changed)['punch']), changed)
        self.assertEqual(protocol.afx_block_set(instinct, block, 'volume', 1)[100:].hex(), '0000803f')
        packet = protocol.build_afx_parameter_write(zen, 75, 0, changed)
        self.assertEqual((packet[4], packet[16:24].hex(' ')), (0x7c, 'd5 6a 4b 00 5c 8f 02 3f'))
        # float32(0.01) is below the double 0.01: the lower limit itself must still be in range.
        protocol.build_afx_parameter_write(zen, 75, 0, protocol.afx_block_set(instinct, block, 'filter_q', 0.01))
        for key, value in (('punch', 1.01), ('punch', -0.01), ('filter_q', 0.009), ('punch', float('nan')),
                           ('punch', float('inf')), ('punch', 1e40), ('punch', '0.5'), ('punch', True)):
            with self.assertRaises(protocol.ConstraintError, msg=(key, value)):
                protocol.afx_block_set(instinct, block, key, value)
        with self.assertRaises(protocol.ConstraintError):   # a stored NaN is not sent
            protocol.build_afx_parameter_write(zen, 75, 0, bytes.fromhex('0000c07f') + block[4:])

    def test_zen_go_write_frame_and_tagged_query(self):
        zen = zen_go()
        packet = protocol.build_afx_parameter_write(zen, 29, 0, bytes.fromhex('523232'))
        self.assertEqual((packet[4], packet[16:23].hex(' ')), (0x17, 'd5 05 1d 00 52 32 32'))
        self.assertEqual(protocol.build_afx_state_query(zen, 29, loaded_types={29})[:16].hex(' '),
                         '74 00 00 00 11 00 00 00 07 00 00 00 1d 00 00 80')
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_state_query(zen, 4, loaded_types={4})
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_state_query(zen, 29, loaded_types=set())
        zen['afx_inserts']['parameters']['effects']['29']['editable'] = False
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_state_query(zen, 29, loaded_types={29})

    def test_clearq_band_frames_match_capture(self):
        d4, zen = discrete_4(), zen_go()
        clearq = protocol.afx_parameter_effect(d4, 1)
        defaults = bytes.fromhex(CLEARQ_DEFAULTS.replace('|', ''))
        want = {'b1_freq': 30, 'b2_q': 71, 'b2_gain': 0, 'b3_freq': 1000, 'b3_q': 71, 'b3_gain': 0}
        got = protocol.afx_block_get(clearq, defaults)
        self.assertEqual({key: got[key] for key in want}, want)
        # The Zen Go owner's ClearQ: band 1 at 125 Hz, shape 4.
        owner = bytes.fromhex('7d004700000004') + defaults[7:]
        self.assertEqual(protocol.afx_block_get(clearq, owner)['b1_freq'], 125)
        # One knob, one band, one frame.
        swept = protocol.afx_block_set(clearq, protocol.afx_block_set(clearq, defaults, 'b3_freq', 125), 'b3_q', 50)
        cases = [(defaults, 'b3_freq', 3000, '01 00 02 b8 0b 47 00 00 00 02'),
                 (defaults, 'b1_freq', 50, '01 00 00 32 00 47 00 00 00 00'),
                 (defaults, 'b2_q', 221, '01 00 01 c8 00 dd 00 00 00 02'),
                 (swept, 'b3_gain', -2400, '01 00 02 7d 00 32 00 a0 f6 02'),
                 (swept, 'b3_gain', 1200, '01 00 02 7d 00 32 00 b0 04 02')]
        for before, key, value, expected in cases:
            frames = protocol.build_afx_parameter_writes(
                d4, 1, 0, protocol.afx_block_set(clearq, before, key, value), before)
            self.assertEqual(len(frames), 1, key)
            self.assertEqual(frames[0][:5].hex(' '), '70 00 00 00 1c')
            self.assertEqual(frames[0][16:28].hex(' '), 'd5 0a ' + expected)
        # Without a previous block every band is sent, in band order.
        frames = protocol.build_afx_parameter_writes(zen, 1, 0, owner)
        self.assertEqual([frame[16:28].hex(' ') for frame in frames][:2],
                         ['d5 0a 01 00 00 7d 00 47 00 00 00 04', 'd5 0a 01 00 01 c8 00 47 00 00 00 02'])
        self.assertEqual(len(frames), 5)
        self.assertEqual(protocol.build_afx_parameter_writes(d4, 1, 0, defaults, defaults), [])
        for key, value in (('b1_freq', 801), ('b2_gain', 1201), ('b3_q', 49), ('b4_freq', 399), ('b1_shape', 2)):
            with self.assertRaises(protocol.ConstraintError, msg=key):
                protocol.afx_block_set(clearq, defaults, key, value)
        with self.assertRaises(protocol.ConstraintError):   # five frames, not one
            protocol.build_afx_parameter_write(d4, 1, 0, defaults)
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_parameter_writes(d4, 1, 0, defaults[:8])
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_parameter_writes(d4, 1, 0, defaults, defaults[:8])
        # The two profiles declare different captured targets for ClearQ.
        self.assertEqual(protocol.build_afx_state_query(d4, 1, loaded_types={1})[:16].hex(' '),
                         '74 00 00 00 10 00 00 00 07 00 00 00 00 00 00 00')
        d4['frame']['readback'] = {**READBACK, 'category_counts': {'0x07': 0}}
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_state_query(d4, 1, loaded_types={1})
        self.assertEqual(protocol.build_afx_state_query(zen, 1, loaded_types={1})[:16].hex(' '),
                         '74 00 00 00 10 00 00 00 07 00 00 00 01 00 00 80')
        reply = (bytes.fromhex('75 00 00 00 40 01 00 00 07 00 00 00 01 00 00 80') + owner + b'\x01').ljust(320, b'\0')
        self.assertTrue(protocol.is_afx_state_response(zen, reply, 1))
        self.assertFalse(protocol.is_afx_state_response(zen, reply, 27))
        self.assertFalse(protocol.is_afx_state_response(zen, reply[:16], 1))
        self.assertFalse(protocol.is_afx_state_response(zen, None, 1))

    def test_load_defaults_match_capture(self):
        for profile, instance in ((discrete_4(), 0), (zen_go(), 1)):
            frames, block = protocol.afx_load_defaults(profile, 1, instance)
            self.assertEqual([frame[16:28].hex(' ') for frame in frames],
                             [f'd5 0a 01 {instance:02x} {band}' for band in CLEARQ_BANDS])
            self.assertTrue(all(frame[4] == 0x1c and not any(frame[28:]) for frame in frames))
            self.assertEqual(block.hex(' '), CLEARQ_DEFAULTS.replace(' | ', ' '))
            frames, block = protocol.afx_load_defaults(profile, 3, 0)
            self.assertEqual([payload(frame) for frame in frames],
                             ['d5 12 03 00 00 46 3e 3f 00 44 00 32 59 00 01'])
            self.assertEqual(frames[0][:5].hex(' '), '70 00 00 00 24')
            self.assertEqual(block, bytes.fromhex(AMP_DEFAULTS))
        self.assertEqual(protocol.afx_load_defaults(discrete_4(), 39, 0), ([], None))   # chain write only
        broken = discrete_4()
        broken['afx_inserts']['writes']['effects']['1']['load_defaults'] = CLEARQ_BANDS[1:] + CLEARQ_BANDS[:1]
        with self.assertRaises(protocol.ConstraintError):   # band selectors out of order
            protocol.afx_load_defaults(broken, 1, 0)
        broken['afx_inserts']['writes']['effects']['3']['load_defaults'] = [AMP_DEFAULTS, AMP_DEFAULTS]
        with self.assertRaises(protocol.ConstraintError):
            protocol.afx_load_defaults(broken, 3, 0)

    def test_guitar_amp_block(self):
        profile = discrete_4()
        amp = protocol.afx_parameter_effect(profile, 3)
        block = bytes.fromhex(amp['defaults'])
        changed = protocol.afx_block_set(amp, protocol.afx_block_set(amp, block, 'model', 10), 'output', -48)
        self.assertEqual(changed.hex(' '), '0a 46 3e 3f 00 44 00 32 59 00 01 00 00 00 00 d0')
        self.assertEqual([payload(frame) for frame in protocol.build_afx_parameter_writes(profile, 3, 0, changed)],
                         ['d5 12 03 00 0a 46 3e 3f 00 44 00 32 59 00 01 00 00 00 00 d0'])
        for key, value in (('model', 11), ('output', 13), ('volume', 101)):
            with self.assertRaises(protocol.ConstraintError):
                protocol.afx_block_set(amp, block, key, value)


class BypassTests(unittest.TestCase):
    def test_bypass_frames_match_capture(self):
        frame = protocol.build_afx_bypass(zen_go(), 74, 0, False)
        self.assertEqual((frame[:5].hex(' '), frame[16:20].hex(' '), any(frame[20:])),
                         ('70 00 00 00 14', '98 00 4a 00', False))
        self.assertEqual(protocol.build_afx_bypass(zen_go(), 74, 0, True)[16:20].hex(' '), '98 00 4a 01')
        d4 = discrete_4()
        self.assertEqual([protocol.build_afx_bypass(d4, 39, inst, False)[16:20].hex(' ') for inst in (0, 1)],
                         ['98 00 27 00', '98 01 27 00'])
        self.assertEqual(protocol.build_afx_bypass(d4, 0x1b, 1, False)[16:20].hex(' '), '98 01 1b 00')
        with self.assertRaises(protocol.ConstraintError):   # type not mapped on this device
            protocol.build_afx_bypass(d4, 74, 0, False)
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_bypass(d4, 39, 255, False)
        del d4['afx_inserts']['parameters']['bypass']
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_bypass(d4, 39, 0, False)


class OrionTests(unittest.TestCase):
    def test_orion_profile_has_no_generic_contract(self):
        profile = orion()
        self.assertIsNone(protocol.afx_insert_writes(profile))
        self.assertIsNone(protocol.afx_parameter_effect(profile, 73))
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_afx_parameter_writes(profile, 73, 0, bytes(8))

    def test_generic_builder_reproduces_captured_memory_cat_frame(self):
        # Test-only fragment: the Memory Cat block as the generic codec would describe
        # it, derived from the Orion profile's existing afx_memorycat_test contract.
        profile = orion()
        contract = profile['runtime_contracts']['afx_memorycat_test']
        fields = [field(name, offset - 20, 'u8', *contract['parameter_ranges'][name])
                  for name, offset in contract['parameter_offsets'].items()]
        profile['afx_inserts'] = {'parameters': {
            'enabled': True, 'write': {**WRITE, 'instances': {'73': [4]}},
            'state_query': {'targets': {'73': [0x07, 0x11, 0x80000049]}},
            'effects': {'73': effect(8, *fields)}}}
        values = dict(blend=50, level=0, feedback=0, chrs_vibr=0, depth=0, delay=0, lpf_fc=100, size=0)
        block = bytes(8)
        for name, value in values.items():
            block = protocol.afx_block_set(profile['afx_inserts']['parameters']['effects']['73'], block, name, value)
        packet = protocol.build_afx_parameter_write(profile, 73, 4, block)
        # The level-zero capture on instance 4 (tools/test_afx_test.py).
        expected = bytes.fromhex('700000001c0000000000000000000000d50a49043200000000006400').ljust(320, b'\0')
        self.assertEqual(packet, expected)
        self.assertEqual(packet, afx.build_parameter_test(profile, 4, values))
        # The tagged query header for instance 0 is the same request upstream builds.
        self.assertEqual(protocol.build_afx_state_query(profile, 73, loaded_types={73}), afx.build_parameter_query(profile, 0))


def catalog_device(name):
    """Test-only configuration for resolving sibling device evidence."""
    return {
        'transport': {'report_size': 320},
        'frame': {'command': COMMAND, 'readback': READBACK},
        'constraints': {'allowed_opcodes': ['0x14']},
        'afx_inserts': {'parameters': {
            'enabled': True, 'catalog': 'afx_effects.json', 'catalog_profile': name,
            'write': {**WRITE, 'instances': {'70': [0]}},
            'state_query': {'targets': {'1': [0x07, 0x10, 0x80000001]}},
            'bypass': {**BYPASS, 'instances': {'74': [0]}},
        }},
    }


class CatalogContractTests(unittest.TestCase):
    """The Zen Go / Discrete 4 parameter blocks stored in profiles/afx/<effect_id>.json."""

    def test_contracts_resolve_and_are_sound(self):
        zen, d4 = catalog_device('zen_go_sc.json'), catalog_device('discrete_4_a270.json')
        for profile, count in ((zen, 69), (d4, 47)):
            effects = protocol.afx_parameter_effects(profile)
            self.assertEqual(len(effects), count)
            for kind, effect in effects.items():
                self.assertIs(protocol.afx_parameter_effect(profile, int(kind)), effect)
                length, taken = effect['block_length'], set()
                if effect.get('editable') is False:   # read not captured: no read layout is claimed
                    self.assertNotIn('read_stride', effect, kind)
                else:
                    self.assertGreater(effect['read_stride'], length, kind)
                for item in effect['fields']:
                    width, signed = protocol._AFX_FIELD_TYPES[item['type']]
                    span = set(range(item['offset'], item['offset'] + width))
                    self.assertFalse(span & taken, f'{kind} {item["key"]} overlaps')
                    self.assertLessEqual(max(span), length - 1, kind)
                    taken |= span
                    if item['type'] != 'f32':
                        low = -(1 << (8 * width - 1)) if signed else 0
                        self.assertTrue(low <= item['min'] < item['max'] < 1 << (8 * width - signed), kind)
        # The 47 shared effects take the Discrete 4's field list (fields_from).
        shared = protocol.afx_parameter_effects(d4)
        for kind in shared:
            self.assertEqual(protocol.afx_parameter_effect(zen, int(kind))['fields'], shared[kind]['fields'], kind)

    def test_inline_fixtures_agree_with_the_catalogue(self):
        # The trimmed fragments above came from these devices; every field they name is in the catalogue.
        for inline, name in ((zen_go(), 'zen_go_sc.json'), (discrete_4(), 'discrete_4_a270.json')):
            shipped = catalog_device(name)
            for kind, effect in protocol.afx_parameter_effects(inline).items():
                mapped = protocol.afx_parameter_effect(shipped, int(kind))
                by_offset = {item['offset']: item for item in mapped['fields']}
                for item in effect['fields']:
                    have = by_offset[item['offset']]
                    self.assertEqual({key: have.get(key) for key in ('type', 'min', 'max', 'values')},
                                     {key: item.get(key) for key in ('type', 'min', 'max', 'values')},
                                     (name, kind, item['key']))

    def test_catalog_and_inline_effects_are_exclusive(self):
        profile = catalog_device('discrete_4_a270.json')
        profile['afx_inserts']['parameters']['effects'] = {}
        with self.assertRaises(protocol.ConstraintError):
            protocol.afx_parameter_effect(profile, 9)
        self.assertIsNone(protocol.afx_effect_id(zen_go(), 9))   # inline effects have no catalogue id

    def test_orion_labels_remain_unconfirmed_for_sibling_devices(self):
        catalog = {entry['id']: entry for entry in load_catalog()['effects']}
        count = 0
        for name in ('discrete_4_a270.json', 'zen_go_sc.json'):
            profile = catalog_device(name)
            for kind, effect in protocol.afx_parameter_effects(profile).items():
                entry = catalog[protocol.afx_effect_id(profile, int(kind))]
                implementations = {item['profile']: item for item in entry['implementations']}
                params = implementations[name]['commands']['parameters']
                source = implementations[params['fields_from']]['commands']['parameters'] if 'fields_from' in params else params
                source_fields = {item['key']: item for item in source['fields']}
                for item in effect['fields']:
                    self.assertNotIn('orion_option_candidates', item)
                    candidates = source_fields[item['key']].get('orion_option_candidates')
                    if candidates:
                        count += 1
                        self.assertNotIn('options', item)
                        self.assertTrue(all(protocol.afx_field_in_range(item, int(value)) for value in candidates))
        self.assertEqual(count, 87)

    def test_model_local_options_are_not_inherited(self):
        mapped_field = field('selector', 0, 'u8', 0, 1, options={'0': 'Model-specific label'})
        catalog = {'effects': [{'id': 'selector', 'implementations': [
            {'profile': 'source.json', 'type_id': 1,
             'commands': {'parameters': effect(1, mapped_field)}},
            {'profile': 'target.json', 'type_id': 1,
             'commands': {'parameters': {'block_length': 1, 'fields_from': 'source.json'}}},
        ]}]}
        with patch.object(protocol, 'load_catalog', return_value=catalog):
            source = protocol._catalog_parameter_contracts('model-local-options.json', 'source.json')
            target = protocol._catalog_parameter_contracts('model-local-options.json', 'target.json')
        self.assertEqual(source['1'][1]['fields'][0]['options'], {'0': 'Model-specific label'})
        self.assertNotIn('options', target['1'][1]['fields'][0])

    def test_v12_orion_candidates_are_not_written(self):
        zen = catalog_device('zen_go_sc.json')
        effect = protocol.afx_parameter_effect(zen, 70)
        self.assertEqual(protocol.afx_effect_id(zen, 70), 'turboensembler')
        self.assertFalse({4, 5} & {item['offset'] for item in effect['fields']})
        v12 = next(e for e in load_catalog()['effects'] if e['id'] == 'turboensembler')
        candidates = next(i for i in v12['implementations'] if i['profile'] == 'zen_go_sc.json')['control_encodings']
        self.assertEqual({key: (enc['offset'], enc['writable']) for key, enc in candidates.items()},
                         {'color': (24, False), 'colorShifter': (25, False)})
        self.assertTrue(all(enc['status'].startswith('candidate') for enc in candidates.values()))
        block = bytes([0, 1, 1, 0, 0xaa, 0xbb, 0, 0, 0xcc, 90, 0, 0])
        frame = protocol.build_afx_parameter_write(zen, 70, 0, protocol.afx_block_set(effect, block, 'space', 7))
        self.assertEqual(frame[24:29].hex(' '), 'aa bb 07 00 cc')   # bytes 4, 5 and 8 written back unchanged

    def test_zen_go_capture_fixtures(self):
        zen = catalog_device('zen_go_sc.json')
        self.assertEqual(protocol.build_afx_state_query(zen, 1, loaded_types={1})[:16].hex(' '),   # ClearQ's captured tuple
                         '74 00 00 00 10 00 00 00 07 00 00 00 01 00 00 80')
        self.assertEqual(protocol.build_afx_bypass(zen, 74, 0, False)[16:20].hex(' '), '98 00 4a 00')
        self.assertIsNone(protocol.afx_insert_writes(zen))
        shipped = json.loads((ROOT / 'profiles' / 'zen_go_sc.json').read_text())
        self.assertIsNone(protocol.afx_parameter_effect(shipped, 70))
        self.assertIsNone(protocol.afx_parameter_effect(zen, 4))   # cabinet: identified, not mapped


if __name__ == '__main__':
    unittest.main()
