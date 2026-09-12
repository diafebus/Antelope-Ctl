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

    def test_global_command_rejects_read_only_21_format(self):
        body = bytearray(151)
        body[0] = 0x23
        body[1] = 0x82
        body[13:23] = protocol.pack_surround_channel_order([1, 3, 4])
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_surround_global_command(
                self.profile, body, global_delay=12)

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

    def test_speaker_builder_requires_explicit_experimental_opt_in(self):
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_surround_speaker_eq_command(
                self.profile, bytes(304), speaker=0, band=0,
                changes={"gain_raw": 100})

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
