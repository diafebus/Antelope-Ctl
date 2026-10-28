"""Offline classification checks; no capture files or hardware required."""
import unittest

from tools.scan_afx_capture import analyze_reports


def frame(opcode, fields):
    payload = bytearray(320)
    payload[0], payload[4] = 0x70, opcode
    payload[16:16 + len(fields)] = bytes(fields)
    return bytes(payload)


class ScanAfxCaptureTests(unittest.TestCase):
    def test_vca160_captured_priming_classifies_only_passive_parameter_blocks(self):
        # Actual Output Gain priming frames2247/2295; no baseline before first.
        prefix = bytes.fromhex('70000000170000000000000000000000d505210032153a')
        first = prefix + bytes(320 - len(prefix))
        second = bytearray(first)
        second[22] = 59
        wrong_selector = bytearray(first)
        wrong_selector[16] = 0xd4
        result = analyze_reports([(2247, 0.0, 1, first), (2295, 0.1, 1, bytes(second)),
                                  (2296, 0.2, 0x82, first), (2297, 0.3, 1, bytes(wrong_selector))])
        self.assertEqual(len(result['parameter_groups']), 1)
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']), ('0x17', '0x5', 33))
        self.assertEqual(group['frames'], 2)
        self.assertEqual(group['varying_offsets'], [22])
        self.assertEqual(group['observed_byte_ranges']['22'], [58, 59])
        self.assertEqual(group['targets'][0]['instance'], 0)
        self.assertEqual(result['operations'], [])
        self.assertFalse(result['device_commands_sent'])

    def test_audiobaton_captured_seed_is_only_a_passive_parameter_observation(self):
        # Actual VOLUME priming frame2529; no preceding captured baseline.
        prefix = bytes.fromhex('700000001e0000000000000000000000d50c4500'
                               '32323232323232323233')
        captured = prefix + bytes(320 - len(prefix))
        wrong_selector = bytearray(captured)
        wrong_selector[16] = 0xd4
        result = analyze_reports([(2529, 0.0, 1, captured),
                                  (2530, 0.1, 0x82, captured),
                                  (2531, 0.2, 1, bytes(wrong_selector))])
        self.assertEqual(len(result['parameter_groups']), 1)
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']),
                         ('0x1e', '0xc', 69))
        self.assertEqual(group['frames'], 1)
        self.assertEqual(group['targets'], [{'instance': 0, 'frames': 1, 'change_runs': []}])
        self.assertEqual(group['varying_offsets'], [])
        self.assertEqual(result['operations'], [])
        self.assertFalse(result['device_commands_sent'])

    def test_stu089_captured_priming_is_only_a_passive_parameter_observation(self):
        # Actual priming frame2457: complete block, byte24 raw51.
        # A single report establishes no isolated field meaning or range.
        prefix = bytes.fromhex('700000001b0000000000000000000000d509150000000000330000')
        captured = prefix + bytes(320 - len(prefix))
        wrong_selector = bytearray(captured)
        wrong_selector[16] = 0xd4
        result = analyze_reports([(2457, 0.0, 1, captured),
                                  (2458, 0.1, 0x82, captured),
                                  (2459, 0.2, 1, bytes(wrong_selector))])
        self.assertEqual(len(result['parameter_groups']), 1)
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']),
                         ('0x1b', '0x9', 21))
        self.assertEqual(group['frames'], 1)
        self.assertEqual(group['targets'], [{'instance': 0, 'frames': 1, 'change_runs': []}])
        self.assertEqual(group['varying_offsets'], [])
        self.assertEqual(result['operations'], [])
        self.assertFalse(result['device_commands_sent'])

    def test_veq4k_pink_priming_family_remains_separate_from_chain_actions(self):
        frames = [2519, 2567, 2619, 2671, 2725, 2777, 2829, 2881, 2933]
        values = [8, 20, 34, 46, 58, 70, 82, 94, 100]
        reports = [(number, index / 10, 1, frame(0x23, [0xd5, 0x11, 16, 0, value]))
                   for index, (number, value) in enumerate(zip(frames, values))]
        reports.extend([(2934, 1, 0x82, frame(0x23, [0xd5, 0x11, 16, 0, 0])),
                        (2935, 1.1, 1, frame(0x23, [0xd4, 0x11, 16, 0, 0])),
                        (2936, 1.2, 1, frame(0x23, [0xd7, 0x11, 1, 16, 0]))])
        result = analyze_reports(reports)
        self.assertEqual(len(result['parameter_groups']), 1)
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']),
                         ('0x23', '0x11', 16))
        self.assertEqual(group['frames'], 9)
        self.assertEqual(group['targets'][0]['instance'], 0)
        self.assertEqual(group['varying_offsets'], [20])
        self.assertEqual(group['observed_byte_ranges']['20'], [8, 100])
        self.assertEqual([operation['kind'] for operation in result['operations']], ['chain'])
        self.assertEqual(result['operations'][0]['slots'][0], {'type': 16, 'instance': 0})
        self.assertFalse(result['device_commands_sent'])

    def test_neu_w492_priming_family_only_classifies_captured_parameter_writes(self):
        # Captured low-gain priming changed byte21, not the first body byte20.
        values = [(459, 42), (665, 0), (2905, 100)]
        reports = [(number, index / 10, 1,
                    frame(0x22, [0xd5, 0x10, 15, 0, 0, value]))
                   for index, (number, value) in enumerate(values)]
        reports.extend([(2906, 0.7, 0x82, frame(0x22, [0xd5, 0x10, 15, 0, 0, 255])),
                        (2907, 0.8, 1, frame(0x22, [0xd4, 0x10, 15, 0, 0, 255]))])
        result = analyze_reports(reports)
        self.assertEqual(len(result['parameter_groups']), 1)
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']),
                         ('0x22', '0x10', 15))
        self.assertEqual(group['frames'], 3)
        self.assertEqual(group['targets'][0]['instance'], 0)
        self.assertEqual(group['varying_offsets'], [21])
        self.assertEqual(group['observed_byte_ranges']['21'], [0, 100])
        self.assertFalse(result['device_commands_sent'])

    def test_neu_pev_priming_family_preserves_unsigned_wire_observations(self):
        # Observed family/type/instance and low-gain bytes from the stopped
        # priming job; these samples do not establish endpoints or signed units.
        reports = [(559, 0.0, 1, frame(0x19, [0xd5, 0x07, 13, 0, 0xff])),
                   (755, 0.1, 1, frame(0x19, [0xd5, 0x07, 13, 0, 0xfb])),
                   (2989, 0.2, 1, frame(0x19, [0xd5, 0x07, 13, 0, 3])),
                   (2990, 0.3, 0x82, frame(0x19, [0xd5, 0x07, 13, 0, 0])),
                   (2991, 0.4, 1, frame(0x19, [0xd4, 0x07, 13, 0, 0]))]
        result = analyze_reports(reports)
        self.assertEqual(len(result['parameter_groups']), 1)
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']),
                         ('0x19', '0x7', 13))
        self.assertEqual(group['frames'], 3)
        self.assertEqual(group['targets'][0]['instance'], 0)
        self.assertEqual(group['varying_offsets'], [20])
        self.assertEqual(group['observed_byte_ranges']['20'], [3, 255])
        self.assertFalse(result['device_commands_sent'])

    def test_gyratec_ix_parameter_family_is_passive_observation(self):
        first = frame(0x18, [0xd5, 0x06, 43, 0, 12, 59, 1, 0])
        second = frame(0x18, [0xd5, 0x06, 43, 0, 0, 59, 1, 0])
        result = analyze_reports([(1, 0.0, 1, first), (2, 0.1, 1, second)])
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']), ('0x18', '0x6', 43))
        self.assertEqual(group['varying_offsets'], [20])
        self.assertFalse(result['device_commands_sent'])

    def test_hlf_parameter_family_is_passive_observation(self):
        first = frame(0x16, [0xd5, 0x04, 11, 0, 2, 10])
        second = frame(0x16, [0xd5, 0x04, 11, 0, 10, 10])
        result = analyze_reports([(1, 1, 1, first), (2, 2, 1, second)])
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']), ('0x16', '0x4', 11))
        self.assertEqual(group['varying_offsets'], [20])

    def test_vmeq_parameter_family_is_passive_observation(self):
        first = frame(0x1a, [0xd5, 0x08, 5, 0, 0, 4, 0, 0, 0, 0])
        second = frame(0x1a, [0xd5, 0x08, 5, 0, 0, 100, 0, 0, 0, 0])
        result = analyze_reports([(1, 1, 1, first), (2, 2, 1, second)])
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']), ('0x1a', '0x8', 5))
        self.assertEqual(group['varying_offsets'], [21])

    def test_powergate_parameter_family_is_passive_observation(self):
        first = frame(0x1d, [0xd5, 0x0b, 39, 0, 90, 0, 100, 0, 50, 0])
        second = frame(0x1d, [0xd5, 0x0b, 39, 0, 31, 0, 100, 0, 50, 0])
        # Keep the negative fixture outside the captured parameter families.
        result = analyze_reports([(1, 1, 1, first), (2, 2, 1, second),
                                  (3, 3, 1, frame(0x1f, [0xd5, 0x0b, 39, 0]))])
        self.assertEqual(len(result['parameter_groups']), 1)
        group = result['parameter_groups'][0]
        self.assertEqual((group['opcode'], group['subcommand'], group['type']), ('0x1d', '0xb', 39))
        self.assertEqual(group['varying_offsets'], [20])

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

    def test_instinct_startup_decodes_only_observed_switch_baseline(self):
        request = bytes.fromhex('7400000011000000070000004b00008001000000').ljust(320, b'\x00')
        reply = bytearray(bytes.fromhex('7500000040010000070000004b000080').ljust(320, b'\x00'))
        reply[69], reply[73], reply[109] = 0, 1, 2
        result = analyze_reports([(1, 1, 1, request), (2, 1.05, 0x82, bytes(reply))])['observed_instance_readbacks']
        state = result['states'][0]
        self.assertEqual(state['instance_from_query'], 1)
        self.assertEqual(state['values']['alt_morph']['state'], 'disengaged')
        self.assertEqual(state['values']['filter_enable']['state'], 'engaged')
        self.assertEqual(state['values']['post_filter_enable']['state'], 'unknown')
        self.assertFalse(state['runtime_query_enabled'])
        self.assertEqual(bytes.fromhex(state['parameter_payload_hex']), bytes(reply[17:]))

    def test_overlapping_or_late_tagged_replies_do_not_guess_instance(self):
        request = bytes.fromhex('7400000011000000070000004b00008001000000').ljust(320, b'\x00')
        reply = bytes.fromhex('7500000040010000070000004b000080').ljust(320, b'\x00')
        for reports in ([(1,1,1,request),(2,1.01,1,request),(3,1.05,0x82,reply)],
                        [(1,1,1,request),(2,3,0x82,reply),(3,4,1,request),(4,4.05,0x82,reply)]):
            with self.subTest(reports=reports):
                result = analyze_reports(reports)['observed_instance_readbacks']
                self.assertEqual(result['states'], [])
                self.assertTrue(result['correlation_blocked'])


if __name__ == '__main__':
    unittest.main()
