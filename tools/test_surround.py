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
        body[0] = 0x03
        body[1] = 0x82
        with self.assertRaises(protocol.ConstraintError):
            protocol.build_surround_global_command(
                self.profile, body, global_delay=12)

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


if __name__ == "__main__":
    unittest.main()
