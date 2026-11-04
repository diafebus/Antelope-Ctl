import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from tools.afx_capture_progress import _schedule, progress_snapshot
from tools.afx_capture_summary import main, summarize_job, summarize_jobs


class CaptureSummaryTests(unittest.TestCase):
    def fixture(self, root):
        job = root / 'scan-example'; job.mkdir()
        plan = {'id': 'example', 'panel': 'Example', 'effect_id': 'example', 'channel': 2,
                'controls': [{'id': 'gain', 'kind': 'knob_range'}],
                'coverage': {'pending': ['Physical units', 'Other controls']},
                'opaque_extension': {'keep': [9, 7]}}
        request = {'version': 2, 'plan_id': 'example', 'panel': 'Example',
                   'channel': 2, 'controls': ['gain'], 'actions': 2}
        windows, decoded = [], []
        for index, (phase, raw) in enumerate([('minimum', 0), ('maximum', 60)], 1):
            payload = bytes([raw]) + bytes(299)
            window = {'action': index, 'control': 'gain', 'gesture': phase,
                      'start_frame_exclusive': (index-1)*10, 'end_frame_inclusive': index*10,
                      'host_accepted': True,
                      'candidate_block_feedback': {'plateau_observed': True,
                                                   'parameter_payload_hex': payload.hex()}}
            windows.append(window)
            decoded.append({**copy.deepcopy(window), 'events': [
                {'frame': index*10-1, 'opcode': '0x19', 'subcommand': '0x7',
                 'type': 9, 'instance': 0, 'changed_bytes': {'20': [30, raw]}}]})
            self.write(job, f'action-{index}-ack.json', {'status': 'ok'})
        capture = job / 'Example-channel2.pcapng'; capture.write_bytes(b'local-evidence')
        artifacts = {'host-plan.json': plan, 'request.json': request,
                     'progress.json': progress_snapshot(plan, _schedule(plan), windows, completed=True),
                     'action-windows.json': windows,
                     'host-device.json': {'profile': 'orion_studio_sc.json', 'bus': 5, 'address': 14,
                                          'serial': 'PRIVATE-DO-NOT-PRINT'},
                     'Example-analysis.json': {'plan_id': 'example', 'labelled_actions': decoded,
                                              'capture_sha256': hashlib.sha256(capture.read_bytes()).hexdigest()},
                     'host-completed.json': {'status': 'ok'},
                     'completed.json': {'status': 'ok', 'device_readback_verified': True,
                                        'range_knobs_left_at': 'maximum'}}
        for name, data in artifacts.items(): self.write(job, name, data)
        (job / 'dumpcap.log').write_text("Packets received/dropped on interface 'usbmon5': 20/0 (100%)\n")
        return job

    def write(self, job, name, data):
        (job / name).write_text(json.dumps(data))

    def mutate(self, job, name, change):
        data = json.loads((job / name).read_text()); change(data); self.write(job, name, data)

    def test_complete_evidence_is_not_readback_runtime_or_semantic_authority(self):
        with tempfile.TemporaryDirectory() as folder:
            job = self.fixture(Path(folder)); before = {p.name: p.read_bytes() for p in job.iterdir()}
            with patch('tools.afx_vm_pilot.device_location', side_effect=AssertionError('no USB')):
                report = summarize_job(job)
            self.assertTrue(report['evidence_complete'], report['issues'])
            self.assertTrue(report['review_required'])
            self.assertEqual(report['completed_controls'], 1)
            self.assertEqual(report['pending_phases'], 0)
            self.assertEqual([(r['offset'], r['raw'], r['frame']) for r in report['endpoint_candidates']],
                             [(20, 0, 9), (20, 60, 19)])
            self.assertFalse(report['device_readback_verified'])
            self.assertFalse(report['runtime_authorized'])
            self.assertFalse(report['meters_verified'])
            self.assertNotIn('PRIVATE', json.dumps(report))
            self.assertEqual(before, {p.name: p.read_bytes() for p in job.iterdir()})

    def test_progress_alone_missing_ack_or_guest_cannot_claim_completion(self):
        for missing in ['host-completed.json', 'completed.json', 'action-2-ack.json',
                        'host-plan.json', 'action-windows.json', 'host-device.json']:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as folder:
                job = self.fixture(Path(folder)); (job / missing).unlink()
                report = summarize_job(job)
                self.assertFalse(report['evidence_complete']); self.assertTrue(report['review_required'])

    def test_tampering_or_unknown_frames_require_review(self):
        mutations = [
            ('host-plan.json', lambda d: d.update(opaque_extension={'keep': 'changed'})),
            ('request.json', lambda d: d.update(channel=3)),
            ('progress.json', lambda d: d.update(accepted_count=1)),
            ('progress.json', lambda d: d.update(runtime_authorized=True)),
            ('host-plan.json', lambda d: d.update(channel=True)),
            ('Example-analysis.json', lambda d: d['labelled_actions'][0]['events'][0].update(frame=1000)),
            ('Example-analysis.json', lambda d: d['labelled_actions'][0]['events'][0].update(opcode='0x99')),
            ('Example-analysis.json', lambda d: d['labelled_actions'][1]['events'][0].update(instance=1)),
            ('Example-analysis.json', lambda d: d['labelled_actions'][0]['events'][0].update(changed_bytes={'20': [30, 1]})),
            ('Example-analysis.json', lambda d: d.update(capture_sha256='0'*64)),
            ('host-device.json', lambda d: d.update(profile='../profiles/orion_studio_sc.json')),
        ]
        for artifact, mutation in mutations:
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as folder:
                job = self.fixture(Path(folder)); self.mutate(job, artifact, mutation)
                self.assertFalse(summarize_job(job)['evidence_complete'])

    def test_packet_loss_and_failure_markers_are_not_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            job = self.fixture(Path(folder))
            (job / 'dumpcap.log').write_text("Packets received/dropped on interface 'usbmon5': 20/1\n")
            self.assertFalse(summarize_job(job)['evidence_complete'])
            (job / 'dumpcap.log').write_text("Packets received/dropped on interface 'usbmon5': 20/0\n")
            self.write(job, 'host-error.json', {'error': 'old failure'})
            self.assertFalse(summarize_job(job)['evidence_complete'])

    def test_empty_capture_does_not_claim_saved_analysis_is_packet_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            job = self.fixture(Path(folder)); (job / 'Example-channel2.pcapng').write_bytes(b'')
            self.assertFalse(summarize_job(job)['evidence_complete'])

    def test_ambiguous_multi_byte_endpoint_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as folder:
            job = self.fixture(Path(folder))
            self.mutate(job, 'Example-analysis.json', lambda d:
                        d['labelled_actions'][0]['events'][0]['changed_bytes'].update({'21': [0, 1]}))
            report = summarize_job(job)
            self.assertFalse(report['evidence_complete'])
            self.assertFalse(report['endpoint_candidates'])

    def test_cli_is_compact_saves_json_and_refuses_to_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); job = self.fixture(root); output = root / 'summary.json'
            stream = io.StringIO()
            with redirect_stdout(stream): self.assertEqual(main([str(job), '--output', str(output)]), 0)
            self.assertLess(len(stream.getvalue()), 200)
            self.assertNotIn('PRIVATE', stream.getvalue())
            self.assertNotIn('parameter_payload_hex', output.read_text())
            self.assertTrue(json.loads(output.read_text())['evidence_complete'])
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main([str(job), '--output', str(job / 'progress.json')])
            self.assertFalse(summarize_jobs([job, root / 'missing'])['evidence_complete'])


if __name__ == '__main__': unittest.main()
