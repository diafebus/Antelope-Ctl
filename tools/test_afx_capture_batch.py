"""Fault-injection checks for reviewed queue execution; no VM or device access."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

from tools import afx_capture_batch as batch
from tools import test_afx_capture_summary as summary_fixtures
from tools.afx_capture_progress import progress_snapshot, _schedule


class BatchTests(unittest.TestCase):
    def fixture(self, root, count=2):
        session = root / 'session'
        session.mkdir()
        batch.write_json(session / 'bridge-identity.json', dict(
            version=1, generation='a'*32, expires_epoch=time.time()+3600))
        plugins = []
        for n in range(count):
            steps = []
            for phase in batch.PHASES:
                script = session / (phase+'.ps1')
                script.write_text('# Reviewed test fixture; never executed\n')
                params = session / (phase+'.json')
                params.write_text('{}')
                steps.append(dict(phase=phase, script=script.name, input=params.name,
                                  script_sha256=batch.digest(script), input_sha256=batch.digest(params)))
            plugins.append(dict(effect_id=f'effect_{n}', steps=steps))
        return session, dict(version=1, plugins=plugins)

    def bridge(self, session, calls, mutate=None):
        def reply(_session, command, timeout, stop_file=None):
            request = batch.read_json(session / ('command-'+command+'.json'))
            calls.append(request)
            if request['action'] == 'script':
                evidence = session / ('evidence-'+command+'.json')
                evidence.write_text('{"bounded_trial":"verified by test adapter"}')
                receipt = dict(status='verified', continuation_safe=True, command_id=command,
                               generation='a'*32, effect_id=request['effect_id'], phase=request['phase'],
                               trial_removed=request['phase']=='cleanup', evidence=[dict(
                                   file=evidence.name, sha256=batch.digest(evidence))])
                if request['phase']=='capture':
                    fixture_root = session.parent / ('fixture-'+command)
                    fixture_root.mkdir()
                    job = summary_fixtures.CaptureSummaryTests().fixture(fixture_root)
                    job = job.rename(session.parent / ('scan-'+request['effect_id']))
                    plan = batch.read_json(job/'host-plan.json')
                    plan['effect_id'] = request['effect_id']
                    batch.write_json(job/'host-plan.json', plan)
                    windows = batch.read_json(job/'action-windows.json')
                    batch.write_json(job/'progress.json', progress_snapshot(
                        plan, _schedule(plan), windows, completed=True))
                    receipt['capture_jobs'] = [job.name]
                if mutate:
                    mutate(request, receipt)
                batch.write_json(session / request['receipt'], receipt)
            result = dict(status='ok', generation='a'*32, command_id=command)
            batch.write_json(session / ('result-'+command+'.json'), result)
            return result
        return reply

    def test_queue_completes_only_after_each_verified_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root, count=7)
            calls = []
            with patch.object(batch, 'wait_reply', side_effect=self.bridge(session, calls)):
                result = batch.run(plan, session, root/'output')
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['completed_plugins'], 7)  # No five-plugin limit.
            self.assertEqual(len(calls), 22)
            self.assertTrue(result['review_required'])
            self.assertEqual(result['pending_review_jobs'], 7)

    def test_uncertain_cleanup_halts_queue_without_repair_or_next_plugin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root)
            calls = []
            def invalidate(request, receipt):
                if request['phase']=='cleanup':
                    receipt['trial_removed'] = False
            with patch.object(batch, 'wait_reply', side_effect=self.bridge(session, calls, invalidate)):
                result = batch.run(plan, session, root/'output')
            self.assertEqual(result['status'], 'review_required')
            self.assertEqual(result['completed_plugins'], 0)
            self.assertEqual(len(calls), 4)
            self.assertIsNotNone(result['pending_command'])

    def test_missing_evidence_or_wrong_receipt_identity_never_advances(self):
        for field, value in [('evidence', []), ('effect_id', 'wrong'),
                             ('command_id', 'stale'), ('continuation_safe', False)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                session, plan = self.fixture(root)
                calls = []
                with patch.object(batch, 'wait_reply', side_effect=self.bridge(
                        session, calls, lambda request, receipt: receipt.update({field:value}))):
                    result = batch.run(plan, session, root/'output')
                self.assertTrue(result['review_required'])
                self.assertEqual(len(calls), 2)

    def test_timeout_records_intent_and_run_directory_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root)
            def timeout(*args, **kwargs):
                state = batch.read_json(root/'output/state.json')
                self.assertIsNotNone(state['pending_command'])
                raise TimeoutError('pending; do not replay')
            with patch.object(batch, 'wait_reply', side_effect=timeout):
                result = batch.run(plan, session, root/'output')
            before = list(session.glob('command-*.json'))
            self.assertEqual(len(before), 1)
            self.assertTrue(result['review_required'])
            with self.assertRaises(FileExistsError):
                batch.run(plan, session, root/'output')
            self.assertEqual(list(session.glob('command-*.json')), before)
            with self.assertRaisesRegex(RuntimeError, 'Pending bridge command'):
                batch.check_pending(session)

    def test_changed_inputs_between_stages_are_rejected_before_more_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root)
            calls = []
            original = self.bridge(session, calls)
            def change(*args, **kwargs):
                result = original(*args, **kwargs)
                (session/'capture.ps1').write_text('# Changed after review')
                return result
            with patch.object(batch, 'wait_reply', side_effect=change):
                result = batch.run(plan, session, root/'output')
            self.assertTrue(result['review_required'])
            self.assertEqual(len(calls), 1)

    def test_rejects_expired_closed_bridge_and_pending_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root)
            identity = batch.read_json(session/'bridge-identity.json')
            for expiry in [0, float('inf')]:
                identity['expires_epoch'] = expiry
                # Deliberate invalid fixture; the normal writer rejects non-finite JSON.
                (session/'bridge-identity.json').write_text(json.dumps(identity))
                with self.assertRaises(RuntimeError):
                    batch.bridge_identity(session)
            (session/'bridge-closed.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                batch.bridge_identity(session)

    def test_manifest_rejects_missing_cleanup_traversal_symlinks_and_changed_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root)
            for field, value in [('script','../escape.ps1'),('input_sha256','wrong')]:
                damaged = copy.deepcopy(plan)
                damaged['plugins'][0]['steps'][0][field] = value
                with self.assertRaises(ValueError):
                    batch.validate_plan(damaged, session)
            damaged = copy.deepcopy(plan)
            damaged['plugins'][0]['steps'].pop()
            with self.assertRaisesRegex(ValueError, 'Stage order|setup, capture'):
                batch.validate_plan(damaged, session)
            (session/'setup.ps1').unlink()
            (session/'setup.ps1').symlink_to(session/'capture.ps1')
            with self.assertRaisesRegex(ValueError, 'redirected'):
                batch.validate_plan(plan, session)

    def test_offline_preparation_never_dispatches_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root)
            draft = root/'draft.json'
            batch.write_json(draft, plan)
            reviewed = root/'reviewed.json'
            batch.prepare(draft, session, reviewed)
            self.assertEqual(list(session.glob('command-*.json')), [])
            with self.assertRaisesRegex(ValueError, 'replace'):
                batch.prepare(draft, session, reviewed)

    def test_lease_must_cover_cleanup_before_any_plugin_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root)
            identity = batch.read_json(session/'bridge-identity.json')
            identity['expires_epoch'] = time.time()+100
            batch.write_json(session/'bridge-identity.json', identity)
            calls = []
            with patch.object(batch, 'wait_reply', side_effect=self.bridge(session, calls)):
                result = batch.run(plan, session, root/'output')
            self.assertTrue(result['review_required'])
            self.assertIn('including cleanup', result['reason'])
            self.assertEqual([q['action'] for q in calls], ['hello'])

    def test_prepare_skips_completed_effects_and_execution_rejects_stale_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root)
            draft = root/'draft.json'
            batch.write_json(draft, plan)
            with patch.object(batch, 'completed_effects', return_value={'effect_0'}):
                remaining = batch.prepare(draft, session, root/'reviewed.json')
                self.assertEqual(remaining['skipped_completed'], ['effect_0'])
                self.assertEqual([p['effect_id'] for p in remaining['plugins']], ['effect_1'])
                with self.assertRaisesRegex(ValueError, 'already complete'):
                    batch.validate_plan(plan, session)

    def test_timeout_and_stop_publish_cancellation_without_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder)
            with self.assertRaises(TimeoutError):
                batch.wait_reply(session, 'a'*32, 0)
            self.assertTrue((session/('cancel-'+'a'*32)).exists())
            self.assertEqual(list(session.glob('command-*.json')), [])

    def test_owned_recorder_shutdown_covers_its_process_group(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            process = Mock(pid=123456)
            process.poll.return_value = None
            def launch(command, **kwargs):
                self.assertTrue(kwargs['start_new_session'])
                kwargs['stdout'].write('Ready for GUI scan/discovery requests;\n')
                kwargs['stdout'].flush()
                return process
            with patch.object(batch.subprocess, 'Popen', side_effect=launch), \
                 patch.object(batch.os, 'killpg') as kill_group:
                with self.assertRaisesRegex(RuntimeError, 'stage failed'):
                    with batch.managed_recorder(root/'kit', root/'output'):
                        raise RuntimeError('stage failed')
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=10)
            kill_group.assert_called_once_with(process.pid, batch.signal.SIGTERM)

    def test_windows_bridge_and_scanner_keep_cancellation_and_single_owner_guards(self):
        windows = Path(__file__).parent/'windows'
        bridge = (windows/'Run-AfxSessionBridge.ps1').read_text()
        scan = (windows/'Run-AfxScan.ps1').read_text()
        adapter = (windows/'Invoke-AfxCaptureStage.ps1').read_text()
        self.assertIn('AntelopeAfxCaptureBridge', bridge)
        self.assertIn('Existing GUI capture worker found', bridge)
        self.assertIn('child_running=$true', bridge)
        self.assertNotIn('Stop-Process', bridge)
        self.assertIn('CheckCancellation();', scan)
        self.assertIn('finally { Held(false); }', scan)
        self.assertIn('$executed.effect_id -cne $EffectId', adapter)
        self.assertIn('-CancellationPath $CancellationPath -DeadlineEpoch $DeadlineEpoch', adapter)

    def test_stop_request_does_not_dispatch_a_stage_or_automatically_clean_up(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            session, plan = self.fixture(root)
            stop = root/'stop'
            stop.touch()
            calls = []
            with patch.object(batch, 'wait_reply', side_effect=self.bridge(session, calls)):
                result = batch.run(plan, session, root/'output', stop)
            self.assertTrue(result['review_required'])
            self.assertEqual([c['action'] for c in calls], ['hello'])


if __name__=='__main__':
    unittest.main()
