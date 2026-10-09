"""Hardware-free evidence and scope checks for the VM pilot."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from tools.afx_vm_pilot import device_location, labelled_actions, planned_actions, validate_request, wait_file, verify_action_events, wire_feedback, validate_wire_controls, verify_wire_changes
from tools.test_scan_afx_capture import frame


class VmPilotTests(unittest.TestCase):
    def test_single_launcher_workflows_reference_existing_reviewed_plans(self):
        from tools.afx_vm_pilot import load_plans
        workflows = json.loads((Path(__file__).resolve().parents[1] / 'tools/windows/afx-capture-workflows.json').read_text())
        self.assertEqual(workflows['channel'], 2)
        plans = load_plans()
        for workflow in workflows['plugins']:
            if workflow['next_step'] == 'ranges':
                self.assertIn(workflow['range_plan'], plans)
            else:
                self.assertEqual(workflow['next_step'], 'inventory')
        v12 = next(w for w in workflows['plugins'] if w['name'] == 'V12 Chorus')
        self.assertEqual(v12['effect_id'], 'turboensembler')
        self.assertEqual(v12['range_plan'], 'v12-controls')

    def test_v12_plan_reuses_measured_fields_and_enables_space_before_color(self):
        from tools.afx_vm_pilot import load_plans
        plans = load_plans()
        plan = plans['v12-controls']
        catalog = json.loads((Path(__file__).resolve().parents[1] / 'profiles/afx_effects.json').read_text())
        validate_wire_controls(plan, catalog)
        self.assertEqual(plan['controls'][0]['wire']['control_id'], 'space')
        self.assertEqual(len(planned_actions(plan)), 22)
        import copy
        altered = copy.deepcopy(plan)
        altered['controls'][0]['wire']['offset'] = 28
        with self.assertRaises(ValueError): validate_wire_controls(altered, catalog)

    def test_wire_feedback_requires_endpoint_and_stable_complete_payload(self):
        control = {'wire': {'offset': 26, 'range': [0, 100]}}
        def report(value, opaque=0, instance=1):
            data = bytearray(frame(0x20, [0xd5, 0x0e, 70, instance]))
            data[26], data[28] = value, opaque
            return (1, 1, 1, bytes(data))
        missing = wire_feedback([], control, 70, 'minimum')
        self.assertTrue(missing['continue'])
        first = wire_feedback([report(100)], control, 70, 'maximum', instance=1)
        self.assertTrue(first['continue'])
        stable = wire_feedback([report(100)], control, 70, 'maximum', instance=1,
                               previous_payload_hex=first['parameter_payload_hex'])
        self.assertTrue(stable['endpoint_verified'])
        changed = wire_feedback([report(100, opaque=1)], control, 70, 'maximum', instance=1,
                                previous_payload_hex=first['parameter_payload_hex'])
        self.assertTrue(changed['continue'])
        self.assertTrue(wire_feedback([report(100, instance=0)], control, 70, 'maximum', instance=1)['continue'])
        self.assertTrue(wire_feedback([report(100)], control, 70, 'maximum', after_frame=1)['continue'])
        with self.assertRaises(RuntimeError):
            verify_wire_changes([report(100), (2, 2, 1, report(100, opaque=1)[3])], 0, control, 70, 1)

    def test_float_feedback_uses_measured_wire_range_not_rounded_label(self):
        import struct
        from tools.afx_vm_pilot import load_plans
        plan = load_plans()['instinct-speed-range']
        catalog = json.loads((Path(__file__).resolve().parents[1] / 'profiles/afx_effects.json').read_text())
        validate_wire_controls(plan, catalog)
        control = plan['controls'][0]
        data = bytearray(frame(0x7c, [0xd5, 0x6a, 75, 1]))
        data[28:32] = struct.pack('<f', 0.999)
        first = wire_feedback([(1,1,1,bytes(data))], control, 75, 'maximum')
        self.assertTrue(first['continue'])
        data[28:32] = struct.pack('<f', 1)
        endpoint = wire_feedback([(2,2,1,bytes(data))], control, 75, 'maximum')
        verified = wire_feedback([(2,2,1,bytes(data))], control, 75, 'maximum',
                                 previous_payload_hex=endpoint['parameter_payload_hex'])
        self.assertTrue(verified['endpoint_verified'])

    def test_host_guest_wire_handshake_completes_without_a_numeric_ui_label(self):
        from tools.afx_vm_pilot import run_job
        control = {'id':'Space', 'label':'Space', 'kind':'knob_range', 'feedback':'captured_wire',
                   'wire':{'control_id':'space', 'offset':26, 'range':[0,100]}}
        plan = {'id':'fixture-wire', 'panel':'V12', 'channel':2, 'effect_id':'turboensembler', 'controls':[control]}
        profile = {'transport':{'in_endpoint':'0x82','out_endpoint':'0x01'}, 'device':{}}
        location = {'bus':5,'address':15,'sysfs':'test'}
        def report(number, value):
            data = bytearray(frame(0x20, [0xd5,0x0e,70,1]))
            data[26] = value
            return (number, float(number), 1, bytes(data))
        inbox = (1, 0, 0x82, bytes([0x73]).ljust(320,b'\0'))
        current = [inbox]
        late_write = {'mode': None}
        def guest_wait(path, seconds, process=None):
            name = path.name
            if name.endswith('-request.json'):
                index = int(name.split('-')[1]); return {'action':index,'control':'Space'}
            if '-sweep-' in name:
                index = int(name.split('-')[1]); value = 0 if index==1 else 100
                if not any(row[3][26]==value for row in current if row[2]==1):
                    current.append(report(10*index,value))
                return {'status':'ok'}
            if name.startswith('action-') and name.endswith('-done.json'):
                if name == 'action-2-done.json' and late_write['mode'] is not None:
                    changed = bytearray(report(21,100)[3])
                    if late_write['mode'] == 'field': changed[28] = 1
                    else: changed[26] = 99
                    current.append((21,21,1,bytes(changed)))
                return {'status':'ok'}
            if name=='completed.json': return {'status':'ok'}
            raise AssertionError(name)
        process = Mock()
        process.poll.side_effect = lambda: None
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory)
            (job/'request.json').write_text(json.dumps({'version':2}))
            with patch('tools.afx_vm_pilot.validate_request',return_value=plan), \
                 patch('tools.afx_vm_pilot.plan_effect_type',return_value=70), \
                 patch('tools.afx_vm_pilot.device_location',return_value=location), \
                 patch('tools.afx_vm_pilot.Path.exists',return_value=True) as exists, \
                 patch('tools.afx_vm_pilot.subprocess.Popen',return_value=process), \
                 patch('tools.afx_vm_pilot.read_reports',side_effect=lambda *a,**kw:list(current)), \
                 patch('tools.afx_vm_pilot.wait_file',side_effect=guest_wait), \
                 patch('tools.afx_vm_pilot.time.sleep'):
                # Path.exists has one call for interface and one for refusing
                # an existing capture. The fixture has no capture file.
                exists.side_effect=[True,False]
                run_job(job,profile)
                for mode in ['field', 'endpoint']:
                    with self.subTest(late_write=mode):
                        late_write['mode'] = mode
                        current[:] = [inbox]
                        trial = job/mode
                        trial.mkdir()
                        (trial/'request.json').write_text(json.dumps({'version':2}))
                        exists.side_effect=[True,False]
                        with self.assertRaises(RuntimeError): run_job(trial,profile)
                        self.assertFalse((trial/'action-2-ack.json').is_file())
            windows=json.loads((job/'action-windows.json').read_text())
            self.assertEqual(len(windows),2)
            self.assertTrue(all(w['wire_feedback'][-1]['endpoint_verified'] for w in windows))
            self.assertTrue((job/'host-completed.json').is_file())
    def test_range_plan_requires_only_two_endpoint_phases(self):
        request = {'version': 2, 'plan_id': 'instinct-speed-range', 'panel': 'Instinct',
                   'channel': 2, 'controls': ['SpeedPot'], 'actions': 2}
        plan = validate_request(request)
        self.assertEqual([phase for _, phase in planned_actions(plan)], ['minimum', 'maximum'])
        for changes in [{'actions': 3}, {'controls': ['VolumePot']}, {'channel': 1}]:
            with self.assertRaises(ValueError):
                validate_request({**request, **changes})

    def test_full_knob_batch_preserves_reviewed_inventory_and_order(self):
        from tools.afx_vm_pilot import load_plans
        plan = load_plans()['instinct-knob-ranges']
        controls = [c['id'] for c in plan['controls']]
        self.assertEqual(len(controls), 21)
        request = {'version': 2, 'plan_id': plan['id'], 'panel': 'Instinct',
                   'channel': 2, 'controls': controls, 'actions': 42}
        self.assertEqual(len(planned_actions(validate_request(request))), 42)
        for changes in [{'controls': controls[::-1]}, {'actions': 63}, {'controls': controls[:-1]}]:
            with self.assertRaises(ValueError):
                validate_request({**request, **changes})

    def test_resume_plan_excludes_completed_controls(self):
        from tools.afx_vm_pilot import load_plans
        plans = load_plans()
        remaining = plans['instinct-knob-ranges-remaining']
        self.assertEqual(remaining['controls'], plans['instinct-knob-ranges']['controls'][5:])
        request = {'version': 2, 'plan_id': remaining['id'], 'panel': 'Instinct', 'channel': 2,
                   'controls': [c['id'] for c in remaining['controls']], 'actions': 32}
        self.assertEqual(len(planned_actions(validate_request(request))), 32)

    def test_volume_only_plan_accepts_finite_and_infinite_labels(self):
        import re
        from tools.afx_vm_pilot import load_plans
        plan = load_plans()['instinct-volume-range']
        pattern = plan['controls'][0]['status_pattern']
        for label in ['VOLUME: -12 DB', 'VOLUME: -inf DB', 'VOLUME: -Infinity DB']:
            self.assertIsNotNone(re.fullmatch(pattern, label, re.IGNORECASE))
        self.assertIsNone(re.fullmatch(pattern, 'GAIN: -12 DB'))
        request = {'version':2, 'plan_id':plan['id'], 'panel':'Instinct', 'channel':2,
                   'controls':['VolumePot'], 'actions':2}
        self.assertEqual(len(planned_actions(validate_request(request))), 2)

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
