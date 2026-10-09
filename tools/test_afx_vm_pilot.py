"""Hardware-free evidence and scope checks for the VM pilot."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.afx_vm_pilot import device_location, labelled_actions, planned_actions, validate_request, wait_file, verify_action_events
from tools.test_scan_afx_capture import frame


class VmPilotTests(unittest.TestCase):
    def test_range_plan_requires_only_two_endpoint_phases(self):
        request = {'version': 2, 'plan_id': 'instinct-speed-range', 'panel': 'Instinct',
                   'channel': 2, 'controls': ['SpeedPot'], 'actions': 2}
        plan = validate_request(request)
        self.assertEqual([phase for _, phase in planned_actions(plan)], ['minimum', 'maximum'])
        for changes in [{'actions': 3}, {'controls': ['VolumePot']}, {'channel': 1}]:
            with self.assertRaises(ValueError):
                validate_request({**request, **changes})

    def test_batch_requests_are_data_driven_and_cannot_substitute_controls(self):
        request = {'version': 2, 'plan_id': 'instinct-filters', 'panel': 'Instinct',
                   'channel': 2, 'controls': ['FilterEnableButton', 'PostFilterEnable'], 'actions': 4}
        self.assertEqual(len(validate_request(request)['controls']), 2)
        for changes in [{'controls': ['DelAll']}, {'actions': 6}, {'channel': 1},
                        {'panel': 'Other'}, {'plan_id': 'unreviewed'}, {'command': 'arbitrary'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_request({**request, **changes})

    def test_channel_and_gesture_scope_cannot_be_expanded_by_guest(self):
        request = {'version': 1, 'panel': 'Instinct', 'channel': 2,
                   'control': 'AltMorphButton', 'actions': 2}
        validate_request(request)
        for key, value in [('channel', 1), ('actions', 3), ('control', 'DelAll'),
                           ('panel', 'Memory Cat'), ('extra', 'command')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_request({**request, key: value})

    def test_frame_evidence_is_isolated_by_action_and_instance(self):
        reports = [(1, 1.5, 1, frame(0x7c, [0xd5, 0x6a, 75, 0, 1])),
                   (2, 1.6, 1, frame(0x7c, [0xd5, 0x6a, 75, 1, 9])),
                   (3, 3.5, 1, frame(0x7c, [0xd5, 0x6a, 75, 0, 0])),
                   (4, 5, 1, frame(0x7c, [0xd5, 0x6a, 75, 0, 255]))]
        result = labelled_actions(reports, [{'start_epoch': 1, 'end_epoch': 2},
                                            {'start_epoch': 3, 'end_epoch': 4}])
        self.assertIsNone(result[0]['events'][0]['changed_offsets_from_previous_action'])
        self.assertEqual(result[1]['events'][0]['changed_offsets_from_previous_action'], [20])
        self.assertEqual(result[1]['events'][0]['changed_bytes'], {'20': [1, 0]})
        self.assertNotIn('255', json.dumps(result))

    def test_overlap_or_invalid_clocks_do_not_assign_actions(self):
        for windows in [[{'start_epoch': 2, 'end_epoch': 1}],
                        [{'start_epoch': 1, 'end_epoch': float('nan')}],
                        [{'start_epoch': 1, 'end_epoch': 3}, {'start_epoch': 2, 'end_epoch': 4}]]:
            with self.assertRaises(ValueError):
                labelled_actions([], windows)

    def test_frame_boundaries_work_when_packet_and_host_clocks_differ(self):
        reports = [(10, 9.7, 1, frame(0x7c, [0xd5, 0x6a, 75, 1, 1])),
                   (20, 10.5, 1, frame(0x7c, [0xd5, 0x6a, 75, 1, 0]))]
        windows = [{'start_epoch': 10, 'end_epoch': 11,
                    'start_frame_exclusive': 9, 'end_frame_inclusive': 15},
                   {'start_epoch': 12, 'end_epoch': 13,
                    'start_frame_exclusive': 15, 'end_frame_inclusive': 25}]
        result = labelled_actions(reports, windows)
        self.assertEqual(result[0]['events'][0]['frame'], 10)
        self.assertEqual(result[1]['events'][0]['changed_bytes'], {'20': [1, 0]})

    def test_overlapping_recording_boundaries_are_rejected(self):
        windows = [{'start_epoch': 1, 'end_epoch': 2,
                    'start_frame_exclusive': 9, 'end_frame_inclusive': 15},
                   {'start_epoch': 3, 'end_epoch': 4,
                    'start_frame_exclusive': 14, 'end_frame_inclusive': 25}]
        with self.assertRaises(ValueError):
            labelled_actions([], windows)

    def test_other_out_is_reported_without_exporting_its_payload(self):
        data = bytearray(frame(0x12, [0x33]))
        data[50:57] = b'PRIVATE'
        result = labelled_actions([(1, 1.5, 1, bytes(data)), (2, 1.7, 130, bytes(data))],
                                  [{'start_epoch': 1, 'end_epoch': 2}])
        self.assertEqual(len(result[0]['events']), 1)
        self.assertEqual(result[0]['events'][0]['status'], 'other OUT command')
        self.assertNotIn('PRIVATE', str(result))

    def test_live_identity_requires_exactly_one_profile_match(self):
        profile = {'device': {'vid': '0x23e5', 'pid': '0xa221'}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(RuntimeError):
                device_location(profile, root)
            for name in ['one', 'two']:
                path = root/name
                path.mkdir()
                for field, value in {'idVendor': '23e5', 'idProduct': 'a221',
                                     'busnum': '5', 'devnum': '15'}.items():
                    (path/field).write_text(value)
                if name == 'one':
                    self.assertEqual(device_location(profile, root),
                                     {'sysfs': 'one', 'bus': 5, 'address': 15})
            with self.assertRaises(RuntimeError):
                device_location(profile, root)

    def test_guest_failure_stops_host_without_waiting_for_next_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'guest-error.json').write_text('{}')
            with patch('tools.afx_vm_pilot.time.sleep') as sleep:
                with self.assertRaises(RuntimeError):
                    wait_file(root/'missing.json', 1)
                sleep.assert_not_called()

    def test_out_verification_blocks_linked_instances_and_wrong_restoration_target(self):
        event = {'opcode': '0x7c', 'subcommand': '0x6a', 'type': 75, 'instance': 0}
        target = verify_action_events([event])
        for events, expected in [([], None), ([event, {**event, 'instance': 1}], None),
                                  ([{**event, 'type': 73}], None),
                                  ([event, {'status': 'other OUT command'}], None),
                                  ([{**event, 'instance': 1}], target)]:
            with self.subTest(events=events), self.assertRaises(RuntimeError):
                verify_action_events(events, expected)


if __name__ == '__main__':
    unittest.main()
