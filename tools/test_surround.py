import json
import unittest
from pathlib import Path

from antelope import protocol


ROOT = Path(__file__).resolve().parents[1]


class SurroundCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "profiles" / "orion_studio_sc.json").open() as handle:
            cls.profile = json.load(handle)

    def test_global_command_preserves_readback_state(self):
        body = bytearray(range(151))
        body[0] = 0x02
        body[1] = 0x9F
        body[13:23] = protocol.pack_surround_channel_order([1, 3])
        expected = bytearray(body)
        expected[2] = 12
        expected[4:6] = (650).to_bytes(2, "little")

        packet = protocol.build_surround_global_command(
            self.profile, body, global_delay=12, global_level=650)

        self.assertEqual(len(packet), 320)
        self.assertEqual(packet[0], 0x70)
        self.assertEqual(packet[4], 0xAB)
        self.assertEqual(packet[16:18], bytes((0xEB, 0x99)))
        self.assertEqual(packet[18:169], expected)
        self.assertEqual(packet[169:], bytes(151))

    def test_global_command_allows_21_format(self):
        body = bytearray(151)
        body[0] = 0x23
        body[1] = 0x82
        body[13:23] = protocol.pack_surround_channel_order([1, 3, 4])
        packet = protocol.build_surround_global_command(
            self.profile, body, global_delay=12)
        self.assertEqual(packet[18 + 2], 12)

    def test_eq_position_command_changes_only_flags_b_bit(self):
        body = bytearray((index * 5 + 3) & 0xFF for index in range(151))
        body[0] = 0x23
        body[1] = 0x82
        body[13:23] = protocol.pack_surround_channel_order([1, 3, 4])
        expected = bytearray(body)
        expected[1] |= 0x80

        packet = protocol.build_surround_global_eq_position_command(
            self.profile, body, "post", allow_experimental=True)

        self.assertEqual(packet[18:169], expected)
        self.assertEqual(packet[169:], bytes(151))
        self.assertEqual(packet[4], 0xAB)
        self.assertEqual(packet[16:18], bytes((0xEB, 0x99)))

    def test_eq_position_command_allows_confirmed_write(self):
        body = bytearray(151)
        body[0] = 0x02
        body[1] = 0x9F
        body[13:23] = protocol.pack_surround_channel_order([1, 3])
        packet = protocol.build_surround_global_eq_position_command(
            self.profile, body, "post")
        self.assertEqual(packet[19], 0x9F)

    def test_eq_position_command_rejects_unsupported_format(self):
        body = bytearray(151)
        body[0] = 0x03
        body[1] = 0x9F
        body[13:23] = protocol.pack_surround_channel_order([1, 3, 2])
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_surround_global_eq_position_command(
                self.profile, body, "post", allow_experimental=True)

    def test_channel_order_packing_matches_20_and_21_readbacks(self):
        self.assertEqual(
            protocol.pack_surround_channel_order([1, 3]),
            bytes.fromhex("00000000000000000023"))
        self.assertEqual(
            protocol.pack_surround_channel_order([1, 3, 4]),
            bytes.fromhex("00000000000000000464"))

    def test_format_command_changes_only_declared_format_fields(self):
        body = bytearray((index * 3) & 0xFF for index in range(151))
        body[0] = 0x23
        body[1] = 0x82
        body[13:23] = protocol.pack_surround_channel_order([1, 3, 4])
        expected = bytearray(body)
        expected[0] = 0x02
        expected[1] = 0x9F
        expected[13:23] = protocol.pack_surround_channel_order([1, 3])

        packet = protocol.build_surround_global_format_command(
            self.profile, body, "2.0")

        self.assertEqual(len(packet), 320)
        self.assertEqual(packet[0], 0x70)
        self.assertEqual(packet[4], 0xAB)
        self.assertEqual(packet[16:18], bytes((0xEB, 0x99)))
        self.assertEqual(packet[18:169], expected)
        self.assertEqual(packet[169:], bytes(151))

    def test_format_command_allows_normal_21_write(self):
        body = bytearray(151)
        body[0] = 0x02
        body[1] = 0x9F
        body[13:23] = protocol.pack_surround_channel_order([1, 3])

        packet = protocol.build_surround_global_format_command(
            self.profile, body, "2.1")

        self.assertEqual(packet[18], 0x23)
        self.assertEqual(packet[19], 0x82)
        self.assertEqual(
            packet[31:41], protocol.pack_surround_channel_order([1, 3, 4]))

    def test_format_command_preserves_eq_position_and_unknown_flag_bits(self):
        body = bytearray(151)
        body[0] = 0xC2  # 2.0 plus two preserved flags-A bits
        body[1] = 0xFF  # 2.0, EQ POST, plus preserved flags-B bits 5-6
        body[13:23] = protocol.pack_surround_channel_order([1, 3])

        packet = protocol.build_surround_global_format_command(
            self.profile, body, "2.1")

        self.assertEqual(packet[18], 0xE3)
        self.assertEqual(packet[19], 0xE2)

    def test_format_command_requires_explicit_higher_layout_opt_in(self):
        body = bytearray(151)
        body[0] = 0x23
        body[1] = 0x82
        body[13:23] = protocol.pack_surround_channel_order([1, 3, 4])
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_surround_global_format_command(
                self.profile, body, "3.0")

    def test_format_command_can_build_vendor_derived_higher_layout(self):
        body = bytearray(151)
        body[0] = 0x23
        body[1] = 0x82
        body[13:23] = protocol.pack_surround_channel_order([1, 3, 4])
        packet = protocol.build_surround_global_format_command(
            self.profile, body, "3.0", allow_experimental=True)
        self.assertEqual(packet[18], 0x03)
        self.assertEqual(packet[19], 0x9F)
        self.assertEqual(
            packet[31:41], protocol.pack_surround_channel_order([1, 3, 2]))

    def _bass_21_body(self):
        body = bytearray((index * 11 + 7) & 0xFF for index in range(151))
        body[0] = 0x23
        body[1] = 0x82
        body[13:23] = protocol.pack_surround_channel_order([1, 3, 4])
        return body

    def test_bass_command_changes_one_fader_and_preserves_other_state(self):
        body = self._bass_21_body()
        block = 25 + 8
        body[block + 4:block + 6] = (0xE345).to_bytes(2, "little")
        expected = bytearray(body)
        expected[block + 4:block + 6] = (0xE000 | 635).to_bytes(2, "little")

        packet = protocol.build_surround_global_bass_command(
            self.profile, body, channel=1, field="fader_db", value=3.5,
            allow_experimental=True)

        self.assertEqual(len(packet), 320)
        self.assertEqual(packet[18:169], expected)
        self.assertEqual(packet[169:], bytes(151))
        self.assertEqual(packet[4], 0xAB)
        self.assertEqual(packet[16:18], bytes((0xEB, 0x99)))

    def test_bass_cutoff_preserves_bypass_bit(self):
        body = self._bass_21_body()
        block = 25
        body[block:block + 2] = (0x8000 | 80).to_bytes(2, "little")

        packet = protocol.build_surround_global_bass_command(
            self.profile, body, channel=0, field="lp_cutoff_hz", value=120,
            allow_experimental=True)

        self.assertEqual(packet[18 + block:18 + block + 2],
                         (0x8000 | 120).to_bytes(2, "little"))

    def test_bass_order_and_boolean_fields_use_declared_encodings(self):
        body = self._bass_21_body()
        block = 25 + 2 * 8

        order_packet = protocol.build_surround_global_bass_command(
            self.profile, body, channel=2, field="hp_order", value=8,
            allow_experimental=True)
        self.assertEqual(order_packet[18 + block + 7], 2)

        mute_packet = protocol.build_surround_global_bass_command(
            self.profile, body, channel=2, field="fader_mute", value=True,
            allow_experimental=True)
        current = int.from_bytes(body[block + 4:block + 6], "little")
        expected = (current & 0x7FFF) | 0x8000
        self.assertEqual(mute_packet[18 + block + 4:18 + block + 6],
                         expected.to_bytes(2, "little"))

    def test_bass_command_allows_confirmed_layouts_and_rejects_unknown(self):
        body = self._bass_21_body()
        packet = protocol.build_surround_global_bass_command(
            self.profile, body, channel=0, field="lp_cutoff_hz", value=80)
        self.assertEqual(packet[18 + 25:18 + 27],
                         (80).to_bytes(2, "little"))

        body[0] = 0x03
        body[1] = 0x9F
        body[13:23] = protocol.pack_surround_channel_order([1, 3, 2])
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_surround_global_bass_command(
                self.profile, body, channel=0, field="lp_cutoff_hz", value=80,
                allow_experimental=True)

        body = self._bass_21_body()
        with self.assertRaises(ValueError):
            protocol.build_surround_global_bass_command(
                self.profile, body, channel=0, field="lp_cutoff_hz", value=500,
                allow_experimental=True)

    def test_bass_command_allows_confirmed_20_blocks(self):
        body = bytearray((index * 7 + 3) & 0xFF for index in range(151))
        body[0] = 0x02
        body[1] = 0x9F
        body[13:23] = protocol.pack_surround_channel_order([1, 3])
        block = 25 + 8
        expected = bytearray(body)
        current = int.from_bytes(body[block:block + 2], "little")
        expected[block:block + 2] = ((current & 0x8000) | 120).to_bytes(
            2, "little")

        packet = protocol.build_surround_global_bass_command(
            self.profile, body, channel=1, field="lp_cutoff_hz", value=120)

        self.assertEqual(packet[18:169], expected)

    def test_bass_filter_type_candidate_changes_only_declared_global_bit(self):
        body = self._bass_21_body()
        body[23] = 0xA4
        body[24] = 0x52
        expected = bytearray(body)
        expected[23] |= 0x01

        packet = protocol.build_surround_global_bass_command(
            self.profile, body, channel=0, field="hp_filter_type",
            value="Linkwitz-Riley", allow_experimental=True)

        self.assertEqual(packet[18:169], expected)
        self.assertEqual(packet[18 + 23], 0xA5)
        self.assertEqual(packet[18 + 24], 0x52)

    def test_bass_filter_type_parser_exposes_candidate_labels_and_slots(self):
        body = self._bass_21_body()
        body[23] = 0x01
        body[24] = 0x00
        body[25 + 4:25 + 6] = (635).to_bytes(2, "little")
        body[25 + 8 + 4:25 + 8 + 6] = (0x4000 | 585).to_bytes(2, "little")

        parsed = protocol.parse_surround_global_record(self.profile, body)

        self.assertEqual(parsed["bass_mgmt_filter_types"], {
            "hp": "Linkwitz-Riley", "lp": "Butterworth"})
        self.assertEqual(parsed["bass_mgmt_channels"][0]["slot"], 0)
        self.assertEqual(parsed["bass_mgmt_channels"][0]["channel_id"], 1)
        self.assertEqual(parsed["bass_mgmt_channels"][0]["fader_raw"], 635)
        self.assertEqual(parsed["bass_mgmt_channels"][1]["channel_id"], 3)
        self.assertEqual(parsed["bass_mgmt_channels"][2]["channel_id"], 4)
        self.assertTrue(parsed["bass_mgmt_channels"][1]["fader_solo"])
        self.assertEqual(parsed["bass_mgmt_channels"][1]["fader_solo_raw"], 1)

    def test_bass_speaker_bypass_changes_only_selected_global_mask_bit(self):
        body = self._bass_21_body()
        body[7:9] = (0xA5FF).to_bytes(2, "little")
        expected = bytearray(body)
        expected[7:9] = (0xA5FD).to_bytes(2, "little")

        packet = protocol.build_surround_global_speaker_mask_command(
            self.profile, body, speaker=1, field="bypass", value=True,
            allow_experimental=True)

        self.assertEqual(packet[18:169], expected)
        self.assertEqual(packet[4], 0xAB)
        self.assertEqual(packet[16:18], bytes((0xEB, 0x99)))

        clear_packet = protocol.build_surround_global_speaker_mask_command(
            self.profile, packet[18:169], speaker=1, field="bypass", value=False,
            allow_experimental=True)
        self.assertEqual(clear_packet[18 + 7:18 + 9],
                         (0xA5FF).to_bytes(2, "little"))


    def test_global_command_rejects_short_readback(self):
        with self.assertRaises(ValueError):
            protocol.build_surround_global_command(
                self.profile, bytes(150), global_level=600)

    def test_global_parser_uses_meaningful_template_size(self):
        body = bytearray(304)
        body[0] = 0x02
        body[1] = 0x9F
        body[4:6] = (600).to_bytes(2, "little")

        parsed = protocol.parse_surround_global_record(self.profile, body)

        self.assertEqual(len(parsed["bass_mgmt_channels"]), 15)

    def test_global_parser_uses_flags_b_for_lfe_and_eq_position(self):
        body = bytearray(151)
        body[0] = 0x24                 # 3.1: even count, so bit 0 is clear
        body[1] = 0x83                 # LFE at zero-based speaker index 3
        body[4:6] = (600).to_bytes(2, "little")

        parsed = protocol.parse_surround_global_record(self.profile, body)

        self.assertTrue(parsed["lfe_present"])
        self.assertEqual(parsed["lfe_index"], 3)
        self.assertTrue(parsed["eq_post"])

        body[1] = 0x1F                 # capture-defined no-LFE sentinel, PRE
        parsed = protocol.parse_surround_global_record(self.profile, body)
        self.assertFalse(parsed["lfe_present"])
        self.assertIsNone(parsed["lfe_index"])
        self.assertFalse(parsed["eq_post"])

    def test_speaker_eq_builder_allows_confirmed_contract(self):
        packet = protocol.build_surround_speaker_eq_command(
            self.profile, bytes(304), speaker=0, band=0,
            changes={"gain_raw": 100})
        self.assertEqual(len(packet), 320)

    def test_speaker_parser_decodes_candidate_head(self):
        body = bytearray(116)
        body[0:2] = (100).to_bytes(2, "little")
        body[2:4] = (0x8000 | 635).to_bytes(2, "little")

        parsed = protocol.parse_surround_speaker_eq_record(self.profile, body)

        self.assertEqual(parsed["head"]["delay_ms_raw"], 100)
        self.assertEqual(parsed["head"]["delay_ms"], 10.6)
        self.assertEqual(parsed["head"]["level_db_raw"], 635)
        self.assertEqual(parsed["head"]["level_db"], 3.5)
        self.assertTrue(parsed["head"]["phase_invert"])
        self.assertEqual(parsed["head"]["phase_invert_raw"], 1)

    def test_speaker_head_builder_changes_one_field_and_preserves_phase(self):
        body = bytearray((index * 3) & 0xFF for index in range(304))
        body[:4] = bytes((0x64, 0x00, 0x7B, 0x82))

        delay_packet = protocol.build_surround_speaker_head_command(
            self.profile, body, speaker=1, field="delay_ms", value=4.6,
            allow_experimental=True)
        self.assertEqual(delay_packet[16:19], bytes((0xEA, 0x75, 1)))
        self.assertEqual(delay_packet[19:21], (40).to_bytes(2, "little"))
        self.assertEqual(delay_packet[21:23], bytes((0x7B, 0x82)))
        self.assertEqual(delay_packet[23:135], bytes(body[4:116]))

        level_packet = protocol.build_surround_speaker_head_command(
            self.profile, body, speaker=1, field="level_db", value=-3.5,
            allow_experimental=True)
        self.assertEqual(
            level_packet[21:23], (0x8000 | 565).to_bytes(2, "little"))
        self.assertEqual(level_packet[19:21], bytes((0x64, 0x00)))

        phase_packet = protocol.build_surround_speaker_head_command(
            self.profile, body, speaker=1, field="phase_invert", value=False,
            allow_experimental=True)
        self.assertEqual(phase_packet[21:23], (635).to_bytes(2, "little"))
        phase_on_packet = protocol.build_surround_speaker_head_command(
            self.profile, phase_packet[19:135], speaker=1,
            field="phase_invert", value=True, allow_experimental=True)
        self.assertEqual(phase_on_packet[21:23],
                         (0x8000 | 635).to_bytes(2, "little"))

    def test_speaker_head_builder_allows_confirmed_contract(self):
        packet = protocol.build_surround_speaker_head_command(
            self.profile, bytes(304), speaker=0, field="delay_ms",
            value=0.6)
        self.assertEqual(len(packet), 320)

    def test_speaker_builder_changes_only_one_band_field(self):
        body = bytearray((index * 3) & 0xFF for index in range(304))
        original = bytearray(body[:116])
        band_offset = 4 + 2 * 7 + 4
        expected = bytearray(original)
        expected[band_offset:band_offset + 2] = (-100).to_bytes(
            2, "little", signed=True)

        packet = protocol.build_surround_speaker_eq_command(
            self.profile, body, speaker=1, band=2,
            changes={"gain_raw": -100}, allow_experimental=True)

        self.assertEqual(len(packet), 320)
        self.assertEqual(packet[0], 0x70)
        self.assertEqual(packet[4], 0x87)
        self.assertEqual(packet[16:19], bytes((0xEA, 0x75, 1)))
        self.assertEqual(packet[19:135], bytes(expected))
        self.assertEqual(packet[135:], bytes(185))

    def test_speaker_reset_changes_eq_fields_and_preserves_modes(self):
        body = bytearray((index * 3) & 0xFF for index in range(304))
        body[:4] = bytes((0xA1, 0xB2, 0xC3, 0xD4))
        frequencies = [30, 45, 90, 160, 350, 650, 1100, 1700,
                       2500, 3500, 4750, 6250, 8250, 10750, 13000, 15000]

        packet = protocol.build_surround_speaker_eq_reset_command(
            self.profile, body, speaker=2, frequencies=frequencies,
            q_raw=71, gain_raw=0, allow_experimental=True)

        self.assertEqual(len(packet), 320)
        self.assertEqual(packet[16:19], bytes((0xEA, 0x75, 2)))
        self.assertEqual(packet[19:23], bytes(body[:4]))
        for index, frequency in enumerate(frequencies):
            offset = 19 + 4 + index * 7
            self.assertEqual(
                packet[offset:offset + 2], frequency.to_bytes(2, "little"))
            self.assertEqual(packet[offset + 2:offset + 4],
                             (71).to_bytes(2, "little"))
            self.assertEqual(packet[offset + 4:offset + 6], bytes(2))
            self.assertEqual(packet[offset + 6], body[4 + index * 7 + 6])

    def test_speaker_reset_rejects_wrong_frequency_count(self):
        with self.assertRaisesRegex(ValueError, 'needs 16 frequencies'):
            protocol.build_surround_speaker_eq_reset_command(
                self.profile, bytes(304), speaker=0, frequencies=[30],
                q_raw=71, gain_raw=0, allow_experimental=True)


if __name__ == "__main__":
    unittest.main()
