"""Offline classification checks; no capture files or hardware required."""
import unittest

from tools.scan_afx_capture import analyze_reports


def frame(opcode, fields):
    payload = bytearray(320)
    payload[0], payload[4] = 0x70, opcode
    payload[16:16 + len(fields)] = bytes(fields)
    return bytes(payload)


class ScanAfxCaptureTests(unittest.TestCase):
    def test_stereo_mirroring_and_multibyte_parameter_changes_are_reported(self):
        first = frame(0x7c, [0xd5, 0x6a, 75, 1, 0, 0, 0, 63])
        second = frame(0x7c, [0xd5, 0x6a, 75, 0, 0, 0, 0, 63])
        third = frame(0x7c, [0xd5, 0x6a, 75, 1, 12, 34, 56, 63])
        result = analyze_reports([(1, 1, 1, first), (2, 1.004, 1, second), (3, 2, 1, third)])
        group = result['parameter_groups'][0]
        self.assertEqual(group['mirrored_writes'], [{'from_instance': 1, 'to_instance': 0, 'pairs': 1}])
        self.assertEqual(group['varying_offsets'], [20, 21, 22])
        self.assertEqual(group['targets'][1]['change_runs'][0]['offsets'], [20, 21, 22])

    def test_unlink_and_assignment_remain_separate_actions(self):
        result = analyze_reports([(1, 1, 1, frame(0x14, [0xa2, 4, 0, 0])),
                                  (2, 1.004, 1, frame(0x23, [0xd7, 0x11, 1, 73, 1]))])
        self.assertEqual([action['kind'] for action in result['operations']], ['link', 'chain'])
        self.assertEqual(result['operations'][1]['slots'][0], {'type': 73, 'instance': 1})

    def test_identity_and_inbound_reports_are_never_exported(self):
        payload = bytearray(320)
        payload[0], payload[8] = 0x75, 1
        payload[16:32] = b'PRIVATE-IDENTITY!'
        result = analyze_reports([(1, 1, 0x82, bytes(payload))])
        self.assertEqual(result['operations'], [])
        self.assertEqual(result['parameter_groups'], [])
        self.assertNotIn('PRIVATE', str(result))

    def test_tagged_instance_read_is_separate_from_category_queries(self):
        request = bytes.fromhex('7400000011000000070000004900008002000000').ljust(320,b'\x00')
        reply = bytes.fromhex('75000000400100000700000049000080013232310031303100').ljust(320,b'\x00')
        result = analyze_reports([(1,1,1,request),(2,1.05,0x82,reply)])
        self.assertEqual(result['readback_queries'], [])
        self.assertEqual(result['instance_state_queries'][0]['instance'], 2)
        self.assertEqual(result['memorycat_readbacks'][0]['instance_from_query'], 2)
        self.assertEqual(result['memorycat_readbacks'][0]['values']['level'], 50)
        self.assertFalse(result['memorycat_readbacks'][0]['bypassed'])


if __name__ == '__main__':
    unittest.main()
