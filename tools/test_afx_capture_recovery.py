"""Offline recovery regressions: accepted controls, stale plans and failed jobs."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.test_afx_vm_pilot import recording_process
from tools.afx_capture_progress import progress_snapshot
from tools.afx_vm_pilot import (checked_job_plan, load_plans, planned_actions,
                               listen, read_reports, resume_plan, resume_request, run_job, write_json)
from tools.test_scan_afx_capture import frame


class CaptureRecoveryTests(unittest.TestCase):
    def source(self, root, count=2):
        job = root/'scan-previous'
        job.mkdir()
        plan = load_plans()['instinct-filters']
        actions = planned_actions(plan)
        windows = [dict(action=i, control=c['id'], gesture=phase, host_accepted=True)
                   for i, (c, phase) in enumerate(actions[:count], 1)]
        write_json(job/'host-plan.json', plan)
        write_json(job/'request.json', dict(version=2, plan_id=plan['id'], panel=plan['panel'],
            channel=2, controls=[c['id'] for c in plan['controls']], actions=len(actions)))
        write_json(job/'action-windows.json', windows)
        write_json(job/'progress.json', progress_snapshot(plan, actions, windows,
            current_action=count+1, error='recorded interruption'))
        write_json(job/'host-device.json', dict(profile='orion_studio_sc.json', bus=5, address=15))
        for window in windows:
            write_json(job/f"action-{window['action']}-ack.json", {'status': 'ok'})
        return job, plan

    def test_resume_omits_only_a_fully_accepted_control(self):
        with tempfile.TemporaryDirectory() as folder:
            job, plan = self.source(Path(folder))
            remaining = resume_plan(job)
            self.assertEqual(remaining['controls'], plan['controls'][1:])
            self.assertTrue(remaining['resume_requires_review'])
            self.assertFalse(remaining['runtime_authorized'])

    def test_first_phase_interruption_keeps_all_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            job, plan = self.source(Path(folder), count=0)
            self.assertEqual(resume_plan(job)['controls'], plan['controls'])

    def test_partial_switch_is_reconciled_as_a_whole_new_trial(self):
        with tempfile.TemporaryDirectory() as folder:
            job, plan = self.source(Path(folder), count=1)
            remaining = resume_plan(job)
            self.assertEqual(remaining['controls'], plan['controls'])
            self.assertEqual(remaining['resume_review']['partial_controls_requiring_reconciliation'],
                             [plan['controls'][0]['id']])

    def test_missing_ack_or_changed_canonical_plan_blocks_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            job, plan = self.source(Path(folder))
            changed = copy.deepcopy(plan)
            changed['controls'][0]['class_name'] = 'CorrectedControlClass'
            with patch('tools.afx_vm_pilot.validate_request', return_value=changed):
                with self.assertRaisesRegex(ValueError, 'Source plan changed'):
                    resume_plan(job)
            (job/'action-2-ack.json').unlink()
            with self.assertRaisesRegex(ValueError, 'host-accepted evidence'):
                resume_plan(job)

    def test_fresh_resume_request_rejects_tampering_and_changed_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, _ = self.source(root)
            remaining = resume_plan(source)
            job = root/'scan-new'; job.mkdir()
            write_json(job/'resume-source.json', {'job': source.name})
            request = resume_request(remaining)
            write_json(job/'request.json', request)
            self.assertEqual(checked_job_plan(job), remaining)
            request['resume_reviewed'] = False
            write_json(job/'request.json', request)
            with patch('tools.afx_vm_pilot.subprocess.Popen') as recorder:
                with self.assertRaisesRegex(ValueError, 'Reviewed resume'):
                    run_job(job, {})
                recorder.assert_not_called()
            write_json(job/'request.json', resume_request(remaining))
            with patch('tools.afx_vm_pilot.device_location', return_value={'bus': 5, 'address': 16}), \
                 patch('tools.afx_vm_pilot.subprocess.Popen') as recorder:
                with self.assertRaisesRegex(RuntimeError, 'Device connection changed'):
                    run_job(job, {'transport': {}})
                recorder.assert_not_called()

    def test_resumed_capture_executes_only_remaining_control_and_records_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, _ = self.source(root)
            plan = resume_plan(source)
            job = root/'scan-new'; job.mkdir()
            write_json(job/'resume-source.json', {'job': source.name})
            write_json(job/'request.json', resume_request(plan))
            current = [(1, 0, 0x82, bytes([0x73]).ljust(320, b'\0'))]
            requested = []
            def wait(path, seconds, process=None):
                if path.name == 'completed.json':
                    return {'status': 'ok'}
                index = int(path.name.split('-')[1])
                if path.name.endswith('-request.json'):
                    requested.append(plan['controls'][0]['id'])
                    return {'action': index, 'control': plan['controls'][0]['id']}
                data = bytearray(frame(0x7c, [0xd5, 0x6a, 75, 0]))
                data[20] = int(index == 1)
                current.append((index+1, 0, 1, bytes(data)))
                return {'status': 'ok'}
            recorder = Mock(); recorder.poll.return_value = None
            with patch('tools.afx_vm_pilot.device_location', return_value={'bus': 5, 'address': 15}), \
                 patch('tools.afx_vm_pilot.Path.exists', side_effect=[True, False]), \
                 patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(recorder, command, **kw)), \
                 patch('tools.afx_vm_pilot.read_reports', side_effect=lambda *a, **k: list(current)), \
                 patch('tools.afx_vm_pilot.wait_file', side_effect=wait), \
                 patch('tools.afx_vm_pilot.time.sleep'):
                run_job(job, {'transport': {'in_endpoint': '0x82', 'out_endpoint': '0x01'}})
            self.assertEqual(requested, ['PostFilterEnable', 'PostFilterEnable'])
            progress = json.loads((job/'progress.json').read_text())
            self.assertTrue(progress['completed'])
            self.assertEqual(progress['accepted_count'], 2)

    def test_first_action_failure_saves_actionable_progress_without_reusing_old_job(self):
        with tempfile.TemporaryDirectory() as folder:
            source, plan = self.source(Path(folder), count=0)
            # Use a fresh job rather than overwriting source capture evidence.
            job = Path(folder)/'scan-failed'; job.mkdir()
            write_json(job/'request.json', json.loads((source/'request.json').read_text()))
            recorder = Mock(); recorder.poll.return_value = None
            initial = [(1, 0, 0x82, bytes([0x73]).ljust(320, b'\0'))]
            def wait(path, *args):
                if path.name.endswith('-request.json'):
                    return {'action': 1, 'control': plan['controls'][0]['id']}
                raise RuntimeError('guest focus changed')
            with patch('tools.afx_vm_pilot.device_location', return_value={'bus': 5, 'address': 15}), \
                 patch('tools.afx_vm_pilot.Path.exists', side_effect=[True, False]), \
                 patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(recorder, command, **kw)), \
                 patch('tools.afx_vm_pilot.read_reports', return_value=initial), \
                 patch('tools.afx_vm_pilot.wait_file', side_effect=wait):
                with self.assertRaisesRegex(RuntimeError, 'guest focus changed'):
                    run_job(job, {'transport': {'in_endpoint': '0x82', 'out_endpoint': '0x01'}})
            progress = json.loads((job/'progress.json').read_text())
            self.assertEqual(progress['status'], 'failed')
            self.assertEqual(progress['current_action']['action'], 1)
            self.assertEqual(resume_plan(job)['controls'], plan['controls'])
            before = (job/'progress.json').read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'already has progress'):
                run_job(job, {})
            self.assertEqual((job/'progress.json').read_bytes(), before)

    def test_slow_decoder_stops_with_an_explanation(self):
        with patch('tools.afx_vm_pilot.subprocess.run', side_effect=subprocess.TimeoutExpired('tshark', 20)):
            with self.assertRaisesRegex(RuntimeError, 'decoding exceeded twenty seconds'):
                read_reports(Path('capture.pcapng'), {'bus': 5, 'address': 15},
                             {'report_size': 320, 'in_endpoint': '0x82', 'out_endpoint': '0x01'})

    def test_termination_unwinds_active_capture_and_records_failed_progress(self):
        from tools.afx_vm_pilot import stop_recorder
        with tempfile.TemporaryDirectory() as folder:
            source, _ = self.source(Path(folder), count=0)
            job = Path(folder)/'scan-interrupted'; job.mkdir()
            write_json(job/'request.json', json.loads((source/'request.json').read_text()))
            recorder = Mock(); recorder.poll.return_value = None
            initial = [(1, 0, 0x82, bytes([0x73]).ljust(320, b'\0'))]
            with patch('tools.afx_vm_pilot.device_location', return_value={'bus': 5, 'address': 15}), \
                 patch('tools.afx_vm_pilot.Path.exists', side_effect=[True, False]), \
                 patch('tools.afx_vm_pilot.subprocess.Popen', side_effect=lambda command, **kw: recording_process(recorder, command, **kw)), \
                 patch('tools.afx_vm_pilot.read_reports', return_value=initial), \
                 patch('tools.afx_vm_pilot.wait_file', side_effect=lambda *a: stop_recorder(None, None)):
                with self.assertRaises(KeyboardInterrupt):
                    run_job(job, {'transport': {'in_endpoint': '0x82', 'out_endpoint': '0x01'}})
            recorder.terminate.assert_called_once()
            recorder.wait.assert_called_once()
            progress = json.loads((job/'progress.json').read_text())
            self.assertEqual(progress['status'], 'failed')
            self.assertEqual(progress['accepted_count'], 0)

    def test_serving_success_failure_then_fresh_success_never_replays_failed_job(self):
        with tempfile.TemporaryDirectory() as folder:
            results = Path(folder)
            clock = {'now': 0, 'launch': 0}
            attempts = []
            failed_progress = {'accepted_count': 1, 'current_action': 2,
                               'restoration': 'unknown; review required'}
            names = ['scan-first', 'scan-failed', 'scan-reviewed-next']

            def launch_on_sleep(_seconds):
                clock['now'] += 1
                if clock['launch'] < len(names):
                    job = results/names[clock['launch']]
                    job.mkdir()
                    write_json(job/'request.json', {'new_launch': True})
                    clock['launch'] += 1

            def run(job, _profile):
                attempts.append(job.name)
                if job.name == 'scan-failed':
                    write_json(job/'progress.json', failed_progress)
                    # A failed batch may have outlasted the previous idle
                    # deadline. The listener must grant a new idle period.
                    clock['now'] += 8
                    raise RuntimeError('capture lost focus')
                write_json(job/'host-completed.json', {'status': 'ok'})

            output, errors = io.StringIO(), io.StringIO()
            with patch('tools.afx_vm_pilot.time.monotonic', side_effect=lambda: clock['now']), \
                 patch('tools.afx_vm_pilot.time.sleep', side_effect=launch_on_sleep), \
                 patch('tools.afx_vm_pilot.run_job', side_effect=run), \
                 redirect_stdout(output), redirect_stderr(errors):
                status = listen(SimpleNamespace(serve=True, wait_seconds=3), {}, {'bus': 5}, results)
            self.assertEqual(status, 0)
            self.assertEqual(attempts, names)
            self.assertEqual(json.loads((results/'scan-failed'/'progress.json').read_text()), failed_progress)
            failure = json.loads((results/'scan-failed'/'host-error.json').read_text())
            self.assertEqual(failure, {'error': 'capture lost focus', 'stop': True})
            self.assertTrue((results/'scan-reviewed-next'/'host-completed.json').is_file())
            self.assertIn('2 scan batch(es) completed', output.getvalue())

    def test_one_shot_failure_stops_before_another_queued_job(self):
        with tempfile.TemporaryDirectory() as folder:
            results = Path(folder)
            clock = {'now': 0}

            def launch_on_sleep(_seconds):
                clock['now'] += 1
                for name in ('scan-0-failed', 'scan-1-next'):
                    job = results/name
                    job.mkdir()
                    write_json(job/'request.json', {'new_launch': True})

            with patch('tools.afx_vm_pilot.time.monotonic', side_effect=lambda: clock['now']), \
                 patch('tools.afx_vm_pilot.time.sleep', side_effect=launch_on_sleep), \
                 patch('tools.afx_vm_pilot.run_job', side_effect=RuntimeError('capture stopped')) as run, \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status = listen(SimpleNamespace(serve=False, wait_seconds=3), {}, {'bus': 5}, results)
            self.assertEqual(status, 1)
            self.assertEqual([call.args[0].name for call in run.call_args_list], ['scan-0-failed'])
            self.assertTrue((results/'scan-0-failed'/'host-error.json').is_file())
            self.assertFalse((results/'scan-1-next'/'host-error.json').exists())


if __name__ == '__main__':
    unittest.main()
