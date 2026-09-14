"""Offline checks for safety/evidence metadata carried by the Orion profile.

Run with: ``python3 -m unittest tools.test_orion_profile_audit``
"""
import json
from pathlib import Path
import unittest

from antelope import protocol


class OrionProfileAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'profiles/orion_studio_sc.json'
        cls.profile = json.loads(path.read_text())

    def test_power_is_declared_but_never_buildable(self):
        power = self.profile['params']['power']
        self.assertTrue(power['never_build'])
        self.assertEqual(power['status'], 'unconfirmed')
        builders = (
            lambda: protocol.build_command(self.profile, 'power', 0, 1),
            lambda: protocol.build_global_command(self.profile, 'power', 1),
            lambda: protocol.build_raw_command(self.profile, 0x01, 0, 1),
        )
        for builder in builders:
            with self.subTest(builder=builder):
                with self.assertRaises(protocol.ConstraintError):
                    builder()

    def test_observed_channels_have_a_derived_bound(self):
        channels = self.profile['channels']
        self.assertEqual(channels['confirmed_indices'], list(range(12)))
        self.assertEqual(channels['index_bound_status'], 'derived')
        self.assertIn('no out-of-range index', channels['index_bound_evidence'])
        self.assertIn('index_bound_is_untested', self.profile['hazards'])

    def test_shared_frames_have_one_wire_shape_each(self):
        mixer = self.profile['frame']['mix_command']
        self.assertEqual(mixer['param_id'], '0xd4')
        self.assertEqual(
            {mixer[key] for key in ('fader_offset', 'pan_flags_offset', 'send_offset')},
            {20, 21, 22},
        )
        self.assertTrue(self.profile['params']['mix_pan']['signed'])

        link = self.profile['frame']['link_command']
        self.assertEqual(link['param_id'], '0xa2')
        self.assertEqual(link['space_offset'], 17)
        self.assertEqual(link['pair_index_offset'], 18)
        self.assertEqual(link['enabled_offset'], 19)

    def test_model_specific_output_ids_are_not_sibling_ids(self):
        self.assertEqual(self.profile['params']['bus_dim']['id'], '0x68')
        self.assertEqual(self.profile['params']['bus_mono']['id'], '0x69')
        self.assertEqual(self.profile['params']['dc_coupling']['id'], '0x26')
        self.assertEqual(self.profile['params']['bus_dim']['status'], 'confirmed')
        self.assertEqual(self.profile['params']['bus_mono']['status'], 'confirmed')
        self.assertEqual(self.profile['params']['dc_coupling']['status'], 'confirmed')
        self.assertEqual(self.profile['params']['dc_coupling']['state_byte'], 93)
        self.assertEqual(self.profile['params']['dc_coupling']['state_bit'], 0)

    def test_preamp_gain_readback_is_signed(self):
        self.assertEqual(
            protocol.parse_preamp_gain_record(self.profile, bytes([0x00, 0x7f, 0x80, 0xfe])),
            [0, 127, -128, -2],
        )


if __name__ == '__main__':
    unittest.main()
