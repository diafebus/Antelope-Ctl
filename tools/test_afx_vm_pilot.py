"""Hardware-free evidence and scope checks for the VM pilot."""
from antelope.catalog import load_catalog
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from tools.afx_vm_pilot import device_location, labelled_actions, planned_actions, validate_request, wait_file, verify_action_events, wire_feedback, validate_wire_controls, verify_wire_changes
from tools.test_scan_afx_capture import frame


def recording_process(process, command, **kwargs):
    """Model dumpcap creating its output so final artifact hashing is exercised."""
    if '-w' in command:
        Path(command[command.index('-w') + 1]).write_bytes(b'offline-capture-fixture')
    return process


class VmPilotTests(unittest.TestCase):
    def test_reviewed_drag_axes_validate_before_capture(self):
        from tools.afx_vm_pilot import knob_drag_axis, load_plans
        self.assertEqual(knob_drag_axis({'kind': 'knob_range'}), 'vertical')
        policy = {'step_delta': 10, 'pause_ms': 1000, 'max_pulses': 4}
        plan = {'id': 'axis', 'panel': 'AudioBaton', 'channel': 2, 'controls': []}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'tools/windows/afx-scan-plans.json'
            path.parent.mkdir(parents=True)
            def load(axis, kind='knob_range', **metadata):
                plan['controls'] = [{'id': 'sg40', 'kind': kind, 'drag_axis': axis, **metadata}]
                path.write_text(json.dumps({'wheel_policy': policy, 'plans': [plan]}))
                with patch('tools.afx_vm_pilot.ROOT', root):
                    return load_plans()
            for axis in ('vertical', 'horizontal'):
                self.assertEqual(load(axis)['axis']['controls'][0]['drag_axis'], axis)
            for axis in (None, True, False, 0, 1, '', 'Horizontal', 'diagonal', [], {}):
                with self.subTest(axis=axis), self.assertRaisesRegex(ValueError, 'axis'):
                    load(axis)
            with self.assertRaisesRegex(ValueError, 'axis'):
                load('vertical', 'binary_button')
            for shift in (0, 1):
                self.assertEqual(load('horizontal', bounds_shift_x_px=shift)['axis']
                                 ['controls'][0]['bounds_shift_x_px'], shift)
            for shift in (-1, 2, True, False, None, 1.0, '1'):
                with self.subTest(shift=shift), self.assertRaisesRegex(ValueError, 'bounds shift'):
                    load('horizontal', bounds_shift_x_px=shift)
            with self.assertRaisesRegex(ValueError, 'bounds shift'):
                load('vertical', bounds_shift_x_px=1)

    def test_axis_targeting_requires_exact_guest_plan_and_keeps_legacy_vertical(self):
        import copy
        plan = {'id': 'axis', 'panel': 'AudioBaton', 'channel': 2,
                'controls': [{'id': 'sg40', 'kind': 'knob_range', 'drag_axis': 'horizontal'}]}
        request = {'version': 5, 'plan_id': 'axis', 'panel': 'AudioBaton',
                   'channel': 2, 'controls': ['sg40'], 'actions': 2,
                   'executed_plan': copy.deepcopy(plan)}
        with patch('tools.afx_vm_pilot.load_plans', return_value={'axis': plan}):
            self.assertEqual(validate_request(request), plan)
            stale = copy.deepcopy(request)
            stale['executed_plan']['controls'][0]['drag_axis'] = 'vertical'
            with self.assertRaises(ValueError):
                validate_request(stale)
            plan['controls'][0]['bounds_shift_x_px'] = 1
            current = copy.deepcopy(request)
            current['executed_plan'] = copy.deepcopy(plan)
            self.assertEqual(validate_request(current), plan)
            with self.assertRaises(ValueError):
                validate_request(request)  # Guest omitted the measured allowance.
            del plan['controls'][0]['bounds_shift_x_px']
            legacy = {k: v for k, v in request.items() if k != 'executed_plan'}
            legacy['version'] = 2
            with self.assertRaises(ValueError):
                validate_request(legacy)
            del plan['controls'][0]['drag_axis']
            self.assertEqual(validate_request(legacy), plan)

    def test_resume_rejects_changed_drag_axis(self):
        import copy
        from tools.afx_capture_progress import progress_snapshot, remaining_plan
        plan = {'id': 'axis', 'controls': [
            {'id': 'sg40', 'kind': 'knob_range', 'drag_axis': 'horizontal'}]}
        progress = progress_snapshot(plan, planned_actions(plan), [])
        changed = copy.deepcopy(plan)
        changed['controls'][0]['drag_axis'] = 'vertical'
        with self.assertRaisesRegex(ValueError, 'different original plan'):
            remaining_plan(changed, progress)

    def test_plan_loader_validates_reviewed_knob_overflow_before_capture(self):
        from tools.afx_vm_pilot import load_plans
        policy = {'step_delta': 10, 'pause_ms': 1000, 'max_pulses': 4}
        plan = {'id': 'overflow', 'panel': 'MeasuredPanel', 'channel': 2,
                'controls': [{'id': 'gain', 'kind': 'knob_range'}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'tools/windows/afx-scan-plans.json'
            path.parent.mkdir(parents=True)
            def load(control):
                plan['controls'] = [control]
                path.write_text(json.dumps({'wheel_policy': policy, 'plans': [plan]}))
                with patch('tools.afx_vm_pilot.ROOT', root):
                    return load_plans()
            self.assertIn('overflow', load({'id': 'gain', 'kind': 'knob_range'}))
            for margin in (1, 12, 14):
                with self.subTest(margin=margin):
                    loaded = load({'id': 'gain', 'kind': 'knob_range', 'panel_overflow_px': margin})
                    self.assertEqual(loaded['overflow']['controls'][0]['panel_overflow_px'], margin)
            for margin in (0, 15, True, False, 14.0, '14', None):
                with self.subTest(margin=margin), self.assertRaisesRegex(ValueError, 'overflow'):
                    load({'id': 'gain', 'kind': 'knob_range', 'panel_overflow_px': margin})
            with self.assertRaisesRegex(ValueError, 'overflow'):
                load({'id': 'switch', 'kind': 'binary_button', 'panel_overflow_px': 14})
            plan.update(panel_class='Ssl4kBus', effect_id='ssl4kbus')
            measured = {'id': 'threshold', 'kind': 'knob_range',
                        'class_name': 'Ssl4kBusPotThreshold', 'panel_overflow_px': 19}
            self.assertIn('overflow', load(measured))
            for field, value in (('class_name', 'UnmeasuredPot'), ('panel_overflow_px', 20),
                                 ('panel_overflow_px', 19.0), ('kind', 'binary_button')):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'overflow'):
                    load({**measured, field: value})
            plan['effect_id'] = 'another_effect'
            with self.assertRaisesRegex(ValueError, 'overflow'):
                load(measured)

    def test_knob_drag_points_require_finite_knob_only_coordinates(self):
        from tools.afx_vm_pilot import knob_drag_point
        self.assertEqual(knob_drag_point({'kind': 'knob_range'}), (0.5, 0.5))
        self.assertEqual(knob_drag_point({'kind': 'knob_range',
                         'drag_point': {'x': .86, 'y': .5}}), (.86, .5))
        for point in (None, [], True, {'x': .5}, {'x': .5, 'y': .5, 'z': 1},
                      {'x': True, 'y': .5}, {'x': 0, 'y': .5},
                      {'x': 1, 'y': .5}, {'x': .5, 'y': float('nan')},
                      {'x': float('inf'), 'y': .5}):
            with self.subTest(point=point), self.assertRaises(ValueError):
                knob_drag_point({'kind': 'knob_range', 'drag_point': point})
        with self.assertRaises(ValueError):
            knob_drag_point({'kind': 'binary_button', 'drag_point': {'x': .5, 'y': .5}})

    def test_point_targeting_requires_exact_executed_guest_plan(self):
        import copy
        plan = {'id': 'point-target', 'panel': 'Neve1023', 'channel': 2,
                'controls': [{'id': 'frequency', 'kind': 'knob_range',
                              'drag_point': {'x': .86, 'y': .5}}]}
        request = {'version': 5, 'plan_id': plan['id'], 'panel': plan['panel'],
                   'channel': 2, 'controls': ['frequency'], 'actions': 2,
                   'executed_plan': copy.deepcopy(plan)}
        with patch('tools.afx_vm_pilot.load_plans', return_value={plan['id']: plan}):
            self.assertEqual(validate_request(request), plan)
            stale = copy.deepcopy(request)
            stale['executed_plan']['controls'][0]['drag_point']['x'] = .5
            with self.assertRaises(ValueError):
                validate_request(stale)
            legacy = {k: v for k, v in request.items() if k != 'executed_plan'}
            legacy['version'] = 2
            with self.assertRaises(ValueError):
                validate_request(legacy)

    def test_recorder_lock_excludes_another_process_and_releases_after_error(self):
        import subprocess
        import sys
        from tools.afx_vm_pilot import recorder_lock
        child = '''
import sys
from pathlib import Path
from tools.afx_vm_pilot import recorder_lock
try:
    with recorder_lock(Path(sys.argv[1])): pass
except RuntimeError:
    sys.exit(7)
'''
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory)
            with self.assertRaisesRegex(ValueError, 'trial failure'):
                with recorder_lock(results):
                    before = (results/'.linux-recorder.lock').read_bytes()
                    other = subprocess.run([sys.executable, '-c', child, directory], capture_output=True, timeout=5)
                    self.assertEqual(other.returncode, 7, other.stderr)
                    self.assertEqual((results/'.linux-recorder.lock').read_bytes(), before)
                    raise ValueError('trial failure')
            other = subprocess.run([sys.executable, '-c', child, directory], capture_output=True, timeout=5)
            self.assertEqual(other.returncode, 0, other.stderr)

    def discovery_inventory(self):
        return {'version': 1, 'panel_name': 'Master De-Esser', 'panel_class': 'Deesser',
                'process_name': 'orionstudioiii', 'window_size': {'width': 1000, 'height': 400},
                'panel_bounds': {'x': 20, 'y': 20, 'width': 900, 'height': 200},
                'controls': [
                    {'class_name': 'DeesserThresholdPot', 'enabled': True, 'offscreen': False,
                     'window_relative_bounds': {'x': 40, 'y': 40, 'width': 30, 'height': 30}},
                    {'class_name': 'DeesserQPot', 'enabled': False, 'offscreen': False,
                     'window_relative_bounds': {'x': 80, 'y': 40, 'width': 30, 'height': 30}},
                    {'class_name': 'DeesserPresetsCombobox', 'enabled': True, 'offscreen': False,
                     'control_type': 'ControlType.ComboBox',
                     'window_relative_bounds': {'x': 120, 'y': 40, 'width': 30, 'height': 30}},
                    {'class_name': 'DeesserMonitorButton', 'enabled': True, 'offscreen': False,
                     'control_type': 'ControlType.CheckBox', 'patterns': ['TogglePatternIdentifiers.Pattern'],
                     'values': {'toggle': 'Off'},
                     'window_relative_bounds': {'x': 160, 'y': 40, 'width': 30, 'height': 30}}]}

    def test_discovery_prepares_knobs_and_binary_toggles_without_wire_guesses(self):
        from tools.afx_scan_discovery import discovery_plan
        from tools.afx_vm_pilot import ROOT
        catalog = load_catalog(ROOT/'profiles/afx_effects.json')
        plan = discovery_plan(self.discovery_inventory(), catalog)
        self.assertEqual([c['feedback'] for c in plan['controls']], ['captured_block', 'gui_toggle'])
        self.assertTrue(all('wire' not in c for c in plan['controls']))
        self.assertEqual(len(plan['coverage']['pending']), 2)
        request = {'version': 3, 'plan_id': plan['id'], 'panel': plan['panel'], 'channel': 2,
                   'controls': [c['id'] for c in plan['controls']], 'actions': 4, 'executed_plan': plan}
        self.assertEqual(validate_request(request, plan), plan)
        request['controls'].append('UnreviewedButton')
        with self.assertRaises(ValueError): validate_request(request, plan)

    def test_discovery_rejects_wrong_panel_and_never_moves_ambiguous_knobs(self):
        from tools.afx_scan_discovery import discovery_plan
        from tools.afx_vm_pilot import ROOT
        catalog = load_catalog(ROOT/'profiles/afx_effects.json')
        for field, value in [('process_name', 'other'), ('panel_class', 'Mixer'), ('panel_name', 'unknown')]:
            inventory = self.discovery_inventory(); inventory[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): discovery_plan(inventory, catalog)
        inventory = self.discovery_inventory()
        inventory['controls'].append(dict(inventory['controls'][0]))
        plan = discovery_plan(inventory, catalog)
        self.assertEqual([c['id'] for c in plan['controls']], ['DeesserMonitorButton'])
        inventory['panel_bounds']['x'] = float('nan')
        with self.assertRaises(ValueError): discovery_plan(inventory, catalog)
        for invalid in ([], None, {'version': 1, 'process_name': 'orionstudioiii', 'panel_name': 9}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): discovery_plan(invalid, catalog)
        for rows in ([None], [self.discovery_inventory()['controls'][0], None]):
            inventory = self.discovery_inventory(); inventory['controls'] = rows
            with self.assertRaises(ValueError): discovery_plan(inventory, catalog)

    def test_discovery_does_not_reclassify_measured_monitor_selector_as_binary(self):
        from tools.afx_scan_discovery import discovery_plan
        from tools.afx_vm_pilot import ROOT
        catalog = load_catalog(ROOT/'profiles/afx_effects.json')
        inventory = self.discovery_inventory()
        inventory['controls'][-1]['class_name'] = 'DeesserCtrlButtonNoInheritance'
        plan = discovery_plan(inventory, catalog)
        self.assertEqual([c['feedback'] for c in plan['controls']], ['captured_block'])
        self.assertTrue(any('multi-state selector' in p['reason'] for p in plan['coverage']['pending']))

    def test_discovery_never_sweeps_processing_switches_named_pot(self):
        from tools.afx_scan_discovery import discovery_plan
        from tools.afx_vm_pilot import ROOT
        catalog = load_catalog(ROOT/'profiles/afx_effects.json')
        for suffix in ('BypassPot', 'PowerPot'):
            inventory = self.discovery_inventory()
            switch = dict(inventory['controls'][0], class_name='Deesser' + suffix)
            inventory['controls'].append(switch)
            plan = discovery_plan(inventory, catalog)
            self.assertNotIn(switch['class_name'], [c['class_name'] for c in plan['controls']])
            self.assertTrue(any(p['control'] == switch['class_name'] and
                                'processing switch' in p['reason'] for p in plan['coverage']['pending']))
        # PowerGate's observed bypass uses a Pot suffix while its actual knobs
        # use Pan. The effect-name prefix must not misclassify real knobs, and
        # unsupported Pan controls must not leave a bypass-only sweep plan.
        inventory = self.discovery_inventory()
        inventory.update(panel_name='powergate', panel_class='PowerGate')
        knob = dict(inventory['controls'][0], class_name='PowerGateThresholdPot')
        switch = dict(knob, class_name='PowerGateBypassPot')
        inventory['controls'] = [knob, switch]
        plan = discovery_plan(inventory, catalog)
        self.assertEqual([c['class_name'] for c in plan['controls']], ['PowerGateThresholdPot'])
        inventory['controls'][0]['class_name'] = 'PowerGateThresholdPan'
        with self.assertRaisesRegex(ValueError, 'No bounded set'):
            discovery_plan(inventory, catalog)

    def test_uint16_endpoint_feedback_preserves_full_block_stability_requirement(self):
        control = {'wire': {'offset': 22, 'width': 2, 'range': [150, 20000]}}
        data = bytearray(frame(0x20, [0xd5, 0x0e, 27, 0]))
        data[22:24] = (20000).to_bytes(2, 'little')
        report = (1, 1, 1, bytes(data))
        first = wire_feedback([report], control, 27, 'maximum', instance=0)
        self.assertEqual(first['observed_raw'], 20000)
        self.assertFalse(first['endpoint_verified'])
        stable = wire_feedback([report], control, 27, 'maximum', instance=0,
                               previous_payload_hex=first['parameter_payload_hex'])
        self.assertTrue(stable['endpoint_verified'])
        data[24] = 1
        changed = wire_feedback([(2, 2, 1, bytes(data))], control, 27, 'maximum', instance=0,
                                previous_payload_hex=first['parameter_payload_hex'])
        self.assertFalse(changed['endpoint_verified'])

    def test_discovery_plateau_is_candidate_and_requires_a_matching_block(self):
        from tools.afx_scan_discovery import block_feedback
        def sample(n, value, instance=0, ep=1):
            data = bytearray(frame(0x20, [0xd5, 0x0e, 27, instance])); data[20] = value
            return n, 0, ep, bytes(data)
        first = block_feedback([sample(2, 10)], 27, 0, 1)
        self.assertTrue(first['continue'])
        stable = block_feedback([sample(2, 10)], 27, 0, 1, first['parameter_payload_hex'])
        self.assertTrue(stable['plateau_observed']); self.assertFalse(stable['endpoint_verified'])
        for reports in ([], [sample(1, 10)], [sample(2, 10, 1)], [sample(2, 10, ep=0x82)], [sample(2, 11)]):
            with self.subTest(reports=reports):
                self.assertTrue(block_feedback(reports, 27, 0, 1, first['parameter_payload_hex'])['continue'])

    def test_discovery_host_binds_complete_plan_before_readiness(self):
        import copy
        from tools.afx_scan_discovery import discovery_plan
        from tools.afx_vm_pilot import ROOT, run_job
        plan = discovery_plan(self.discovery_inventory(), load_catalog(ROOT/'profiles/afx_effects.json'))
        request = {'version': 3, 'plan_id': plan['id'], 'panel': plan['panel'], 'channel': 2,
                   'controls': [c['id'] for c in plan['controls']], 'actions': 4, 'executed_plan': plan}
        alterations = [('class_name', 'AnotherPot'), ('kind', 'binary_button'), ('feedback', 'numeric')]
        with tempfile.TemporaryDirectory() as directory:
            for field, value in alterations:
                changed = copy.deepcopy(request); changed['executed_plan']['controls'][0][field] = value
                job = Path(directory)/field; job.mkdir()
                (job/'request.json').write_text(json.dumps(changed))
                (job/'discovery-inventory.json').write_text(json.dumps(self.discovery_inventory()))
                with self.subTest(field=field), patch('tools.afx_vm_pilot.subprocess.Popen') as capture:
                    with self.assertRaises(ValueError): run_job(job, {})
                    capture.assert_not_called(); self.assertFalse((job/'ready.json').exists())

    def test_discovery_run_tracks_priming_and_silent_sweeps_without_promoting_range(self):
        from tools.afx_vm_pilot import ROOT, run_job
        from tools.afx_scan_discovery import discovery_plan
        inventory = self.discovery_inventory(); inventory['controls'] = inventory['controls'][:1]
        plan = discovery_plan(inventory, load_catalog(ROOT/'profiles/afx_effects.json'))
        current = []; mode = {'wrong': False}
        def add_parameter(value, instance=0):
            data = bytearray(frame(0x20, [0xd5, 0x0e, 27, instance])); data[20] = value
            current.append((len(current)+1, 0, 1, bytes(data)))
        def read(*args, **kwargs):
            current.append((len(current)+1, 0, 0x82, bytes([0x73]).ljust(320, b'\0')))
            return list(current)
        def wait(path, seconds, process=None):
            name = path.name
            if name == 'completed.json': return {'status': 'ok'}
            index = int(name.split('-')[1])
            if name.endswith('-request.json'): return {'action': index, 'control': 'DeesserThresholdPot'}
            if name.endswith('-primed.json'):
                if index == 1: add_parameter(50)
                return {'status': 'ok'}
            if '-sweep-' in name:
                sweep = int(name.split('-')[3])
                if sweep == 1: add_parameter(0 if index == 1 else 100, 1 if mode['wrong'] else 0)
                return {'status': 'ok'}
            if name.endswith('-done.json'): return {'status': 'ok'}
            raise AssertionError(name)
        location = {'bus': 5, 'address': 15, 'sysfs': 'fixture'}
        process = Mock(); process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            for wrong in (False, True):
                mode['wrong'] = wrong; current.clear()
                job = Path(directory)/str(wrong); job.mkdir()
                request = {'version': 3, 'plan_id': plan['id'], 'panel': plan['panel'], 'channel': 2,
                           'controls': [c['id'] for c in plan['controls']], 'actions': 2, 'executed_plan': plan}
                (job/'request.json').write_text(json.dumps(request))
                (job/'discovery-inventory.json').write_text(json.dumps(inventory))
                with patch('tools.afx_vm_pilot.device_location', return_value=location), \
                     patch('tools.afx_vm_pilot.Path.exists', side_effect=[True, False]), \
                     patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(process, command, **kw)), \
                     patch('tools.afx_vm_pilot.read_reports', side_effect=read), \
                     patch('tools.afx_vm_pilot.wait_file', side_effect=wait), patch('tools.afx_vm_pilot.time.sleep'):
                    if wrong:
                        with self.assertRaises(RuntimeError): run_job(job, {'transport': {'in_endpoint': '0x82', 'out_endpoint': '0x01'}})
                    else: run_job(job, {'transport': {'in_endpoint': '0x82', 'out_endpoint': '0x01'}})
                if wrong: self.assertFalse((job/'action-1-ack.json').is_file())
                else:
                    windows = json.loads((job/'action-windows.json').read_text())
                    self.assertFalse(windows[0]['candidate_block_feedback']['endpoint_verified'])
                    self.assertFalse(windows[0]['wire_feedback'][-1]['new_target_report'])
                    self.assertEqual(windows[0]['wire_feedback'][-1]['unchanged_sweeps'], 2)

    def test_single_launcher_workflows_reference_existing_reviewed_plans(self):
        from tools.afx_vm_pilot import load_plans
        workflows = json.loads((Path(__file__).resolve().parents[1] / 'tools/windows/afx-capture-workflows.json').read_text())
        self.assertEqual(workflows['channel'], 2)
        plans = load_plans()
        for workflow in workflows['plugins']:
            if workflow['next_step'] == 'ranges':
                self.assertIn(workflow['range_plan'], plans)
            elif workflow['next_step'] == 'complete':
                self.assertTrue(workflow['completion_evidence'])
                self.assertIn('unverified', workflow['completion_limits'])
            elif workflow['next_step'] == 'menus':
                self.assertEqual(workflow['effect_id'], 'deesser')
                self.assertEqual(workflow['panel_class'], 'Deesser')
                self.assertEqual(workflow['menu_classes'], ['DeesserPresetsCombobox', 'DeesserComboBoxFilterType'])
            elif workflow['next_step'] == 'review':
                self.assertTrue(workflow['review_reason'])
                self.assertTrue(workflow['partial_evidence'])
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
        catalog = load_catalog(Path(__file__).resolve().parents[1] / 'profiles/afx_effects.json')
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
        catalog = load_catalog(Path(__file__).resolve().parents[1] / 'profiles/afx_effects.json')
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
                 patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(process, command, **kw)), \
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
    def test_selector_cycle_and_power_handshake_reject_incomplete_or_other_target(self):
        from tools.afx_vm_pilot import run_job, load_plans
        base = load_plans()['bbd-controls']
        controls = [{**base['controls'][-2], 'kind':'selector_cycle'}, base['controls'][-1], next(c for c in base['controls'] if c['id']=='ChorusVibrato')]
        plan = {**base, 'controls': controls}
        profile = {'transport': {'in_endpoint':'0x82', 'out_endpoint':'0x01'}, 'device':{}}
        location = {'bus':5, 'address':15, 'sysfs':'fixture'}
        def report(number, value, power=False, instance=0):
            data = bytearray(frame(0x14 if power else 0x1c,
                                   [0x98,instance,78,value] if power else [0xd5,0x0a,78,instance]))
            if not power: data[25] = value
            return (number, float(number), 1, bytes(data))
        inbox = (1,0,0x82,bytes([0x73]).ljust(320,b'\0'))
        current = []
        mode = {'value':'ok'}
        def guest_wait(path, seconds, process=None):
            if path.name.endswith('-request.json'):
                index=int(path.name.split('-')[1])
                if mode['value']=='newer_edit' and index==2: current.append(report(19,3))
                return {'action':index, 'control':controls[0 if index<=4 else 1 if index<=6 else 2]['id']}
            if path.name.startswith('action-') and path.name.endswith('-done.json'):
                index=int(path.name.split('-')[1])
                if index<=4:
                    value = index % 4
                    if mode['value']=='repeat' and index==2: value=1
                    if mode['value']=='no_restore' and index==4: value=4
                    row=report(index*10,value)
                    if mode['value']=='other_field' and index==2:
                        data=bytearray(row[3]); data[26]=1; row=(*row[:3],bytes(data))
                    current.append(row)
                elif index<=6:
                    target=1 if mode['value']=='other_instance' else 0
                    current.extend([report(index*10,1,True,target),report(index*10+1,0,True,target)])
                else:
                    value=1 if index==7 else 0
                    if mode['value']=='toggle_no_change' and index==7: value=0
                    if mode['value']=='toggle_no_restore' and index==8: value=1
                    row=report(index*10,0); data=bytearray(row[3]); data[24]=value
                    current.append((*row[:3],bytes(data)))
                return {'status':'ok'}
            if path.name=='completed.json': return {'status':'ok'}
            raise AssertionError(path.name)
        process=Mock(); process.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory:
            for outcome in ('ok','repeat','no_restore','other_field','other_instance','newer_edit','toggle_no_change','toggle_no_restore'):
                with self.subTest(outcome=outcome):
                    mode['value']=outcome; current[:]=[inbox,report(2,0)]
                    job=Path(directory)/outcome; job.mkdir()
                    (job/'request.json').write_text(json.dumps({'version':2}))
                    with patch('tools.afx_vm_pilot.validate_request',return_value=plan), \
                         patch('tools.afx_vm_pilot.plan_effect_type',return_value=78), \
                         patch('tools.afx_vm_pilot.device_location',return_value=location), \
                         patch('tools.afx_vm_pilot.Path.exists',side_effect=[True,False]), \
                         patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(process, command, **kw)), \
                         patch('tools.afx_vm_pilot.read_reports',side_effect=lambda *a,**kw:list(current)), \
                         patch('tools.afx_vm_pilot.wait_file',side_effect=guest_wait), \
                         patch('tools.afx_vm_pilot.time.sleep'):
                        if outcome=='ok': run_job(job,profile)
                        else:
                            with self.assertRaises(RuntimeError): run_job(job,profile)
                    if outcome=='ok':
                        windows=json.loads((job/'action-windows.json').read_text())
                        self.assertEqual([w['observed_selector_raw'] for w in windows[:4]],[1,2,3,0])
                        self.assertEqual([e['state'] for e in windows[5]['bypass_events']],[1,0])
                        self.assertEqual([w['observed_toggle_raw'] for w in windows[6:]],[1,0])
                        self.assertTrue((job/'host-completed.json').is_file())
                    else:
                        failed_index={'repeat':2,'no_restore':4,'other_field':2,'other_instance':5,'newer_edit':2,'toggle_no_change':7,'toggle_no_restore':8}[outcome]
                        self.assertFalse((job/f'action-{failed_index}-ack.json').exists())

    def test_direct_selector_resume_learns_restore_without_a_prior_out_block(self):
        from tools.afx_vm_pilot import run_job, load_plans
        plan=load_plans()['bbd-remaining']
        self.assertEqual(len(planned_actions(plan)),7)
        profile={'transport':{'in_endpoint':'0x82','out_endpoint':'0x01'},'device':{}}
        location={'bus':5,'address':15,'sysfs':'fixture'}
        current=[]; outcome={'value':'ok'}
        def report(number,value,power=False,instance=0):
            data=bytearray(frame(0x14 if power else 0x1c,
                [0x98,instance,78,value] if power else [0xd5,0x0a,78,instance]))
            if not power: data[25]=value
            return (number,float(number),1,bytes(data))
        def guest_wait(path,seconds,process=None):
            index=int(path.name.split('-')[1]) if path.name.startswith('action-') else 0
            if path.name.endswith('-request.json'):
                if outcome['value']=='newer_edit' and index==2: current.append(report(19,9))
                return {'action':index,'control':'StereoType' if index<=5 else 'Power'}
            if path.name.startswith('action-') and path.name.endswith('-done.json'):
                if index<=5:
                    raw=[7,3,9,5,9][index-1]
                    if outcome['value']=='repeat' and index==2: raw=7
                    if outcome['value']=='wrong_restore' and index==5: raw=7
                    current.append(report(index*10,3 if raw!=3 else 9))
                    row=report(index*10+1,raw)
                    if outcome['value']=='other_field' and index==2:
                        data=bytearray(row[3]);data[26]=1;row=(*row[:3],bytes(data))
                    current.append(row)
                else:
                    current.extend([report(index*10,1,True),report(index*10+1,0,True)])
                return {'status':'ok','starting_position': None if outcome['value']=='ambiguous_start' else 2}
            if path.name=='completed.json':return {'status':'ok'}
            raise AssertionError(path.name)
        process=Mock();process.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory:
            for mode in ('ok','repeat','wrong_restore','other_field','newer_edit','ambiguous_start','disagreeing_start'):
                with self.subTest(mode=mode):
                    outcome['value']=mode
                    current[:]=[(1,0,0x82,bytes([0x73]).ljust(320,b'\0'))]
                    if mode=='disagreeing_start':current.append(report(2,7))
                    job=Path(directory)/mode;job.mkdir();(job/'request.json').write_text(json.dumps({'version':2}))
                    with patch('tools.afx_vm_pilot.validate_request',return_value=plan), \
                         patch('tools.afx_vm_pilot.plan_effect_type',return_value=78), \
                         patch('tools.afx_vm_pilot.device_location',return_value=location), \
                         patch('tools.afx_vm_pilot.Path.exists',side_effect=[True,False]), \
                         patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(process, command, **kw)), \
                         patch('tools.afx_vm_pilot.read_reports',side_effect=lambda *a,**kw:list(current)), \
                         patch('tools.afx_vm_pilot.wait_file',side_effect=guest_wait), \
                         patch('tools.afx_vm_pilot.time.sleep'):
                        if mode=='ok':run_job(job,profile)
                        else:
                            with self.assertRaises(RuntimeError):run_job(job,profile)
                    if mode=='ok':
                        ack=json.loads((job/'action-4-ack.json').read_text())
                        self.assertEqual(ack['restore_position'],2)
                        windows=json.loads((job/'action-windows.json').read_text())
                        self.assertEqual([w['observed_selector_raw'] for w in windows[:5]],[7,3,9,5,9])
                        self.assertTrue((job/'host-completed.json').is_file())
                    else:
                        failed={'repeat':2,'wrong_restore':5,'other_field':2,'newer_edit':2,'ambiguous_start':4,'disagreeing_start':4}[mode]
                        self.assertFalse((job/f'action-{failed}-ack.json').exists())

    def test_memorycat_processing_layout_distinguishes_linked_instances_from_states(self):
        # Literal tails from linked frames10215/10219 and isolated return837.
        from tools.scan_afx_capture import analyze_reports
        from tools.afx_vm_pilot import bypass_layout_for
        catalog=load_catalog(Path(__file__).resolve().parents[1]/'profiles/afx_effects.json')
        layout=bypass_layout_for({'effect_id':'memory_brigade'},catalog)
        reports=[]
        for number,tail in ((10215,'98014900'),(10219,'98004900'),(10220,'98004901')):
            data=bytes.fromhex('70000000140000000000000000000000'+tail).ljust(320,b'\0')
            reports.append((number,float(number),1,data))
        decoded=analyze_reports(reports)['operations']
        self.assertEqual([(o['instance'],o['state']) for o in decoded],[(1,0),(0,0),(0,1)])
        windows=[{'start_epoch':0,'end_epoch':10220,'start_frame_exclusive':0,'end_frame_inclusive':10220}]
        events=labelled_actions(reports,windows,bypass_layout=layout)[0]['events']
        self.assertEqual([(e['instance'],e['state']) for e in events],[(1,0),(0,0),(0,1)])
        profile=json.loads((Path(__file__).resolve().parents[1]/'profiles/orion_studio_sc.json').read_text())
        self.assertEqual(profile['frame']['afx_slot']['bypass']['state_offset'],19)
        self.assertEqual(profile['frame']['afx_slot']['bypass']['instance_index_offset'],17)
        self.assertFalse(profile['frame']['afx_slot']['bypass']['writable'])

    def test_bbd_power_layout_is_model_local_and_decodes_literal_capture_frames(self):
        from tools.afx_vm_pilot import bypass_layout_for, load_plans
        catalog=load_catalog(Path(__file__).resolve().parents[1]/'profiles/afx_effects.json')
        layout=bypass_layout_for(load_plans()['bbd-remaining'],catalog)
        reports=[]
        for number,tail in ((7063,'98004e00'),(7999,'98004e01')):
            data=bytes.fromhex('70000000140000000000000000000000'+tail).ljust(320,b'\0')
            reports.append((number,float(number),1,data))
        windows=[{'start_epoch':0,'end_epoch':1,'start_frame_exclusive':0,'end_frame_inclusive':7063},
                 {'start_epoch':2,'end_epoch':3,'start_frame_exclusive':7063,'end_frame_inclusive':7999}]
        decoded=labelled_actions(reports,windows,bypass_layout=layout)
        self.assertEqual([w['events'][0]['instance'] for w in decoded],[0,0])
        self.assertEqual([w['events'][0]['state'] for w in decoded],[0,1])
        from tools.scan_afx_capture import analyze_reports
        summary=analyze_reports(reports)
        self.assertEqual([(o['instance'],o['state']) for o in summary['operations']],[(0,0),(0,1)])
        self.assertIsNotNone(bypass_layout_for({'effect_id':'memory_brigade'},catalog))
        import copy
        changed=copy.deepcopy(catalog)
        implementation=next(i for e in changed['effects'] if e['id']=='bbdchorus'
                            for i in e['implementations'] if i['profile']=='orion_studio_sc.json')
        implementation['bypass_observation']['state_offset']=18
        with self.assertRaises(ValueError):bypass_layout_for(load_plans()['bbd-remaining'],changed)

    def test_filter_wheel_trial_verifies_labels_and_single_instance_before_ack(self):
        from tools.afx_vm_pilot import run_job, load_plans
        plan=load_plans()['deesser-filter-wheel']
        self.assertEqual([phase for _,phase in planned_actions(plan)],['wheel forward','wheel back'])
        profile={'transport':{'in_endpoint':'0x82','out_endpoint':'0x01'},'device':{}}
        location={'bus':5,'address':15,'sysfs':'fixture'}
        current=[]; mode={'value':'ok'}
        def guest_wait(path,seconds,process=None):
            index=int(path.name.split('-')[1]) if path.name.startswith('action-') else 0
            if path.name.endswith('-request.json'):return {'action':index,'control':'FilterTypeWheel'}
            if path.name.startswith('action-') and path.name.endswith('-done.json'):
                instance=1 if mode['value']=='other_instance' and index==2 else 0
                data=bytearray(frame(0x20,[0xd5,0x0e,27,instance]));data[20]=index
                current.append((index*10,float(index),1,bytes(data)))
                initial='HighPass 1'; selection='HighPass 2' if index==1 else initial
                if mode['value']=='unchanged' and index==1:selection=initial
                if mode['value']=='no_restore' and index==2:selection='HighPass 2'
                if mode['value']=='changed_initial' and index==2:initial='Different'
                if mode['value']=='bad_label':selection=None
                before = initial if index == 1 else 'HighPass 2'
                pulses = [{'delta': -15 if index == 1 else 15, 'pause_ms': 1500,
                           'starting_selection': before, 'selection': selection}]
                return {'status':'ok','starting_selection':initial,'selection':selection,'wheel_pulses':pulses}
            if path.name=='completed.json':return {'status':'ok'}
            raise AssertionError(path.name)
        process=Mock();process.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory:
            for outcome in ('ok','unchanged','no_restore','other_instance','changed_initial','bad_label'):
                with self.subTest(outcome=outcome):
                    mode['value']=outcome;current[:]=[(1,0,0x82,bytes([0x73]).ljust(320,b'\0'))]
                    job=Path(directory)/outcome;job.mkdir();(job/'request.json').write_text(json.dumps({'version':2}))
                    with patch('tools.afx_vm_pilot.validate_request',return_value=plan), \
                         patch('tools.afx_vm_pilot.plan_effect_type',return_value=27), \
                         patch('tools.afx_vm_pilot.device_location',return_value=location), \
                         patch('tools.afx_vm_pilot.Path.exists',side_effect=[True,False]), \
                         patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(process, command, **kw)), \
                         patch('tools.afx_vm_pilot.read_reports',side_effect=lambda *a,**kw:list(current)), \
                         patch('tools.afx_vm_pilot.wait_file',side_effect=guest_wait), \
                         patch('tools.afx_vm_pilot.time.sleep'):
                        if outcome=='ok':run_job(job,profile)
                        else:
                            with self.assertRaises(RuntimeError):run_job(job,profile)
                    if outcome=='ok':self.assertTrue((job/'host-completed.json').is_file())
                    else:
                        failed=1 if outcome in ('unchanged','bad_label') else 2
                        self.assertFalse((job/f'action-{failed}-ack.json').exists())

    def test_page_key_trial_checks_activation_adjacency_wire_and_restore_before_ack(self):
        from tools.afx_vm_pilot import run_job, load_plans
        plan = load_plans()['deesser-filter-keys']; control = plan['controls'][0]
        self.assertEqual([p for _, p in planned_actions(plan)], ['PageDown', 'PageUp'])
        names = ['HighPass 1', 'HighPass 2', 'HighPass 3', 'BandPass 1', 'BandPass 2']
        current = []; mode = {'value': 'ok'}
        def wait(path, seconds, process=None):
            if path.name == 'completed.json': return {'status': 'ok'}
            index = int(path.name.split('-')[1])
            if path.name.endswith('-request.json'):
                if index == 1:
                    data = bytes([0x73]).ljust(320, b'\0'); ep = 0x82
                    if mode['value'] == 'activation_out': data = frame(0x20, [0xd5, 0x0e, 27, 0]); ep = 1
                    current.append((2, 0, ep, data))
                if index == 2 and mode['value'] == 'newer_edit':
                    data = bytearray(frame(0x20, [0xd5, 0x0e, 27, 0])); data[26] = 2
                    current.append((15, 0, 1, bytes(data)))
                return {'action': index, 'control': control['id']}
            instance = 1 if mode['value'] == 'wrong_instance' and index == 2 else 0
            data = bytearray(frame(0x20, [0xd5, 0x0e, 27, instance])); data[26] = 1 if index == 1 else 0
            if mode['value'] == 'other_field' and index == 2: data[25] = 1
            if mode['value'] == 'same_raw' and index == 2: data[26] = 1
            if mode['value'] == 'unstable_block' and index == 1:
                other = bytearray(data); other[26] = 2
                current.append((9, 0, 1, bytes(other)))
            if mode['value'] != 'missing_out': current.append((index*10, 0, 1, bytes(data)))
            else: current.append((index*10, 0, 0x82, bytes([0x73]).ljust(320, b'\0')))
            result = {'status': 'ok', 'starting_selection': names[0],
                'selection': names[1] if index == 1 else names[0],
                'option_names': list(names), 'key': 'PageDown' if index == 1 else 'PageUp',
                'keypresses': 1, 'dwell_ms': 5000, 'keyboard_focus_verified': True,
                'activation_verified': True}
            if mode['value'] == 'skip' and index == 1: result['selection'] = names[3]
            if mode['value'] == 'wrong_restore' and index == 2: result['selection'] = names[1]
            if mode['value'] == 'no_activation': result['activation_verified'] = False
            if mode['value'] == 'no_focus': result['keyboard_focus_verified'] = False
            if mode['value'] == 'repeat_key': result['keypresses'] = 2
            if mode['value'] == 'wrong_key': result['key'] = 'End'
            if mode['value'] == 'too_fast': result['dwell_ms'] = 100
            if mode['value'] == 'changed_names' and index == 2: result['option_names'][-1] = 'changed'
            return result
        process = Mock(); process.poll.return_value = None
        outcomes = ('ok', 'activation_out', 'newer_edit', 'wrong_instance', 'other_field', 'same_raw',
                    'missing_out', 'skip', 'wrong_restore', 'no_activation', 'no_focus', 'repeat_key',
                    'wrong_key', 'too_fast', 'changed_names', 'unstable_block')
        with tempfile.TemporaryDirectory() as directory:
            for outcome in outcomes:
                with self.subTest(outcome=outcome):
                    mode['value'] = outcome; current[:] = [(1, 0, 0x82, bytes([0x73]).ljust(320, b'\0'))]
                    job = Path(directory)/outcome; job.mkdir(); (job/'request.json').write_text('{"version":2}')
                    with patch('tools.afx_vm_pilot.validate_request', return_value=plan), \
                         patch('tools.afx_vm_pilot.device_location', return_value={'bus':5,'address':15}), \
                         patch('tools.afx_vm_pilot.Path.exists', side_effect=[True,False]), \
                         patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(process, command, **kw)), \
                         patch('tools.afx_vm_pilot.read_reports', side_effect=lambda *a,**kw:list(current)), \
                         patch('tools.afx_vm_pilot.wait_file', side_effect=wait), patch('tools.afx_vm_pilot.time.sleep'):
                        if outcome == 'ok': run_job(job, {'transport': {'in_endpoint':'0x82','out_endpoint':'0x01'}})
                        else:
                            with self.assertRaises(RuntimeError): run_job(job, {'transport': {'in_endpoint':'0x82','out_endpoint':'0x01'}})
                    if outcome == 'ok': self.assertTrue((job/'host-completed.json').is_file())
                    else:
                        failed = 2 if outcome in ('newer_edit','wrong_instance','other_field','same_raw','wrong_restore','changed_names') else 1
                        self.assertFalse((job/f'action-{failed}-ack.json').exists())
                    if outcome == 'activation_out': self.assertFalse((job/'action-1-go.json').exists())
                    if outcome == 'newer_edit': self.assertFalse((job/'action-2-go.json').exists())

    def test_gui_toggle_requires_binary_change_restore_and_same_instance(self):
        from tools.afx_vm_pilot import run_job
        plan = {'id': 'test-toggle', 'panel': 'deesser', 'effect_id': 'deesser', 'channel': 2,
                'controls': [{'id': 'Monitor', 'label': 'Monitor', 'kind': 'binary_button', 'feedback': 'gui_toggle'}]}
        current = []; mode = {'value': 'ok'}
        def wait(path, seconds, process=None):
            if path.name == 'completed.json': return {'status': 'ok'}
            index = int(path.name.split('-')[1])
            if path.name.endswith('-request.json'): return {'action': index, 'control': 'Monitor'}
            selection = 'On' if index == 1 else 'Off'
            if mode['value'] == 'unchanged': selection = 'Off'
            if mode['value'] == 'no_restore' and index == 2: selection = 'On'
            if mode['value'] == 'indeterminate': selection = 'Indeterminate'
            instance = 1 if mode['value'] == 'other_instance' and index == 2 else 0
            current.append((index*10, 0, 1, frame(0x20, [0xd5, 0x0e, 27, instance, index])))
            return {'status': 'ok', 'starting_selection': 'Off', 'selection': selection}
        process = Mock(); process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            for outcome in ('ok', 'unchanged', 'no_restore', 'indeterminate', 'other_instance'):
                mode['value'] = outcome; current[:] = [(1, 0, 0x82, bytes([0x73]).ljust(320, b'\0'))]
                job = Path(directory)/outcome; job.mkdir(); (job/'request.json').write_text('{"version":2}')
                with patch('tools.afx_vm_pilot.validate_request', return_value=plan), \
                     patch('tools.afx_vm_pilot.device_location', return_value={'bus':5,'address':15}), \
                     patch('tools.afx_vm_pilot.Path.exists', side_effect=[True,False]), \
                     patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(process, command, **kw)), \
                     patch('tools.afx_vm_pilot.read_reports', side_effect=lambda *a,**kw:list(current)), \
                     patch('tools.afx_vm_pilot.wait_file', side_effect=wait), patch('tools.afx_vm_pilot.time.sleep'):
                    if outcome == 'ok': run_job(job, {'transport': {'in_endpoint':'0x82','out_endpoint':'0x01'}})
                    else:
                        with self.assertRaises(RuntimeError): run_job(job, {'transport': {'in_endpoint':'0x82','out_endpoint':'0x01'}})
                if outcome == 'ok': self.assertTrue((job/'host-completed.json').exists())
                else:
                    failed = 1 if outcome in ('unchanged', 'indeterminate') else 2
                    self.assertFalse((job/f'action-{failed}-ack.json').exists())

    def test_paced_wheel_stops_at_first_change_and_bounds_reverse_pulses(self):
        import copy
        from tools.afx_vm_pilot import verify_wheel_pulses, load_plans
        policy = load_plans()['deesser-filter-wheel']['wheel_policy']
        pulses = [{'delta': -15, 'pause_ms': 1500, 'starting_selection': 'A', 'selection': 'A'},
                  {'delta': -15, 'pause_ms': 1500, 'starting_selection': 'A', 'selection': 'B'}]
        result = {'selection': 'B', 'wheel_pulses': pulses}
        self.assertEqual(verify_wheel_pulses(result, policy, 'wheel forward', 'A'), 2)
        reverse = {'selection': 'A', 'wheel_pulses': [
            {'delta': 15, 'pause_ms': 1500, 'starting_selection': 'B', 'selection': 'A'}]}
        self.assertEqual(verify_wheel_pulses(reverse, policy, 'wheel back', 'B', 2), 1)
        for alteration in ('too_fast', 'full_notch', 'unknown_label', 'continued_after_change', 'missing'):
            bad = copy.deepcopy(result)
            if alteration == 'too_fast': bad['wheel_pulses'][0]['pause_ms'] = 10
            elif alteration == 'full_notch': bad['wheel_pulses'][0]['delta'] = -120
            elif alteration == 'unknown_label': bad['wheel_pulses'][0]['selection'] = None
            elif alteration == 'continued_after_change': bad['wheel_pulses'].append(dict(pulses[-1]))
            else: del bad['wheel_pulses']
            with self.subTest(alteration=alteration), self.assertRaises(RuntimeError):
                verify_wheel_pulses(bad, policy, 'wheel forward', 'A')
        with self.assertRaises(RuntimeError): verify_wheel_pulses(reverse, policy, 'wheel back', 'B', 0)

    def test_named_menu_requires_all_six_stable_labels_and_exact_selection(self):
        import copy
        from tools.afx_vm_pilot import verify_menu_labels, load_plans
        control = load_plans()['deesser-filter-menu']['controls'][0]
        names = ['one', 'two', 'three', 'four', 'five', 'six']
        completed = {'option_names': names, 'starting_selection': 'three', 'starting_position': 2,
                     'selection': 'one', 'popup_closed': True, 'dwell_ms': 5000}
        self.assertEqual(verify_menu_labels(completed, control, 'position-1'), names)
        for field, value in [('option_names', names[:5]), ('selection', 'six'), ('popup_closed', False),
                             ('dwell_ms', 0), ('starting_position', 0), ('option_names', ['one']*6)]:
            bad = copy.deepcopy(completed); bad[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                verify_menu_labels(bad, control, 'position-1')
        bad = copy.deepcopy(completed); bad['option_names'] = names[::-1]
        with self.assertRaises(RuntimeError): verify_menu_labels(bad, control, 'position-1', names)
        completed['selection'] = 'three'
        self.assertEqual(verify_menu_labels(completed, control, 'restore', names), names)

    def test_named_menu_records_six_independent_values_and_guards_restoration(self):
        from tools.afx_vm_pilot import load_plans, run_job
        plan = load_plans()['deesser-filter-menu']; control = plan['controls'][0]
        self.assertEqual(len(planned_actions(plan)), 7)
        current = []; mode = {'value': 'ok'}
        names = ['one', 'two', 'three', 'four', 'five', 'six']
        values = [0, 1, 2, 3, 4, 5, 2]
        def wait(path, seconds, process=None):
            if path.name == 'completed.json': return {'status': 'ok'}
            index = int(path.name.split('-')[1])
            if path.name.endswith('-request.json'): return {'action': index, 'control': control['id']}
            value = values[index-1]
            if mode['value'] == 'repeat' and index == 2: value = 0
            if mode['value'] == 'wrong_restore' and index == 7: value = 5
            instance = 1 if mode['value'] == 'wrong_instance' and index == 2 else 0
            data = bytearray(frame(0x20, [0xd5, 0x0e, 27, instance])); data[26] = value
            if mode['value'] == 'other_field' and index == 2: data[25] = 1
            current.append((index*10, 0, 1, bytes(data)))
            labels = list(names)
            if mode['value'] == 'changed_names' and index == 2: labels[-1] = 'changed'
            selection = names[index-1] if index <= 6 else names[2]
            if mode['value'] == 'skipped_choice' and index == 2: selection = names[5]
            return {'status': 'ok', 'option_names': labels, 'selection': selection,
                    'starting_selection': names[2], 'starting_position': 2, 'popup_closed': True, 'dwell_ms': 5000}
        process = Mock(); process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            for outcome in ('ok', 'repeat', 'wrong_restore', 'wrong_instance', 'other_field', 'changed_names', 'skipped_choice'):
                mode['value'] = outcome; current[:] = [(1, 0, 0x82, bytes([0x73]).ljust(320, b'\0'))]
                job = Path(directory)/outcome; job.mkdir(); (job/'request.json').write_text('{"version":2}')
                with patch('tools.afx_vm_pilot.validate_request', return_value=plan), \
                     patch('tools.afx_vm_pilot.device_location', return_value={'bus':5,'address':15}), \
                     patch('tools.afx_vm_pilot.Path.exists', side_effect=[True,False]), \
                     patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(process, command, **kw)), \
                     patch('tools.afx_vm_pilot.read_reports', side_effect=lambda *a,**kw:list(current)), \
                     patch('tools.afx_vm_pilot.wait_file', side_effect=wait), patch('tools.afx_vm_pilot.time.sleep'):
                    if outcome == 'ok': run_job(job, {'transport': {'in_endpoint':'0x82','out_endpoint':'0x01'}})
                    else:
                        with self.assertRaises(RuntimeError): run_job(job, {'transport': {'in_endpoint':'0x82','out_endpoint':'0x01'}})
                if outcome == 'ok':
                    self.assertEqual(json.loads((job/'action-6-ack.json').read_text())['restore_position'], 2)
                    self.assertTrue((job/'host-completed.json').is_file())
                else: self.assertFalse((job/f'action-{7 if outcome == "wrong_restore" else 2}-ack.json').exists())

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
