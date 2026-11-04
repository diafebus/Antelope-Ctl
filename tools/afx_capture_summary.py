#!/usr/bin/env python3
"""Compact offline capture evidence reports; never opens HID or changes profiles.

Saved decoder output is checked against the host plan, accepted action windows,
ACKs and both completion markers. Raw packets are not rescanned and no current
USB location is consulted. Completion means the planned job, not the plugin's
semantics, readback, restoration or runtime support, has been established.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.afx_capture_progress import _schedule, progress_snapshot
from tools.scan_afx_capture import PARAMETER_OPCODES


class EvidenceError(ValueError):
    pass


def _require(value, message):
    if not value:
        raise EvidenceError(message)


def _load(job, name):
    path = job / name
    _require(path.is_file() and not path.is_symlink(), 'missing or linked ' + name)
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError) as error:
        raise EvidenceError('invalid JSON in ' + name) from error


def _digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _identity(row):
    return {k: row[k] for k in ('action', 'control', 'gesture')}


def _integer(value, lower=0, upper=None):
    return type(value) is int and value >= lower and (upper is None or value <= upper)


def _opcode(value):
    try:
        return int(value, 0) if isinstance(value, str) else value
    except ValueError:
        return None


def _candidate(window, report_size, capture):
    """Return only an isolated one-byte endpoint candidate, never a wire writer."""
    events = window.get('events')
    _require(isinstance(events, list) and events and window.get('missing_OUT_witness') is not True,
             'missing outbound witness')
    offsets, last_values, target = set(), {}, None
    previous_frame = window['start_frame_exclusive']
    for event in events:
        _require(isinstance(event, dict), 'malformed decoded event')
        frame = event.get('frame')
        _require(_integer(frame) and previous_frame < frame <= window['end_frame_inclusive'],
                 'decoded event outside its action window')
        previous_frame = frame
        opcode, subcommand = _opcode(event.get('opcode')), _opcode(event.get('subcommand'))
        _require(_integer(event.get('type'), upper=255) and
                 _integer(event.get('instance'), upper=255), 'uncorrelated decoded target')
        current = (opcode, subcommand, event['type'], event['instance'])
        _require(target is None or current == target, 'multiple decoded targets in one action')
        target = current
        if opcode == 0x14 and subcommand == 0x98:
            _require(event.get('layout_source') == 'model-local captured catalog',
                     'unverified processing layout')
            _require(_integer(event.get('state'), upper=1), 'invalid processing state')
            continue
        _require(opcode in PARAMETER_OPCODES and _integer(subcommand, upper=255),
                 'unrecognized outbound family')
        changed = event.get('changed_bytes')
        _require(isinstance(changed, dict), 'missing decoded byte changes')
        for text_offset, values in changed.items():
            _require(isinstance(text_offset, str) and text_offset.isdecimal(), 'invalid byte offset')
            offset = int(text_offset)
            _require(20 <= offset < report_size and isinstance(values, list) and len(values) == 2 and
                     all(_integer(value, upper=255) for value in values), 'invalid byte change')
            offsets.add(offset)
            last_values[offset] = (values[1], frame)
    if window['gesture'] not in ('minimum', 'maximum'):
        return None, target
    _require(len(offsets) == 1, 'endpoint does not isolate one byte')
    offset = next(iter(offsets))
    raw, frame = last_values[offset]
    feedback = window.get('candidate_block_feedback')
    if feedback is not None:
        _require(isinstance(feedback, dict) and feedback.get('plateau_observed') is True,
                 'endpoint plateau not established')
        try:
            payload = bytes.fromhex(feedback['parameter_payload_hex'])
        except (KeyError, TypeError, ValueError) as error:
            raise EvidenceError('invalid endpoint block') from error
        _require(len(payload) == report_size - 20 and payload[offset - 20] == raw,
                 'endpoint block disagrees with decoded events')
    return {'control': window['control'], 'gesture': window['gesture'],
            'offset': offset, 'raw': raw, 'frame': frame, 'capture': capture,
            'writable': False, 'device_readback_verified': False}, target


def summarize_job(job):
    """Read saved evidence and return a compact, fail-closed report.

    ``evidence_complete`` is separate from ``review_required``: intact jobs can
    still have planned coverage gaps and all candidates require semantic review.
    No artifacts are mutated. Opaque source fields remain in their original files.
    """
    job = Path(job)
    result = {'version': 1, 'job': job.name, 'status': 'review_required',
              'evidence_complete': False, 'review_required': True,
              'accepted_phases': 0, 'pending_phases': None,
              'completed_controls': 0, 'pending_controls': None,
              'endpoint_candidates': [], 'coverage_pending': [], 'issues': [],
              'device_readback_verified': False, 'runtime_authorized': False,
              'meters_verified': False,
              'evidence_source': 'saved coordinator artifacts; no raw packet re-decode'}
    try:
        _require(job.is_dir() and not job.is_symlink(), 'job must be a real directory')
        plan = _load(job, 'host-plan.json')
        request = _load(job, 'request.json')
        progress = _load(job, 'progress.json')
        windows = _load(job, 'action-windows.json')
        _require(all(isinstance(v, dict) for v in (plan, request, progress)), 'invalid job metadata')
        _require(_integer(plan.get('channel'), 1), 'invalid planned channel')
        actions = _schedule(plan)
        _require(request.get('version') == 2 and request.get('plan_id') == plan['id'] and
                 request.get('panel') == plan['panel'] and request.get('channel') == plan['channel'] and
                 request.get('controls') == [c['id'] for c in plan['controls']] and
                 type(request.get('actions')) is int and request['actions'] == len(actions),
                 'request does not match host plan')
        _require(isinstance(windows, list), 'invalid action windows')
        accepted = []
        for position, window in enumerate(windows):
            _require(isinstance(window, dict), 'invalid action window')
            if window.get('host_accepted') is True:
                _require(len(accepted) == position, 'accepted windows are not a prefix')
                accepted.append(window)
        expected = progress_snapshot(plan, actions, accepted,
                                    current_action=progress.get('current_action'),
                                    error=progress.get('error'), completed=progress.get('completed'))
        for key in ('plan_id', 'plan_fingerprint', 'status', 'completed', 'total_actions',
                    'accepted_count', 'accepted_actions', 'controls'):
            _require(progress.get(key) == expected[key], 'progress disagrees with accepted evidence')
        _require(progress.get('runtime_authorized') is False, 'capture progress claims runtime authority')
        result.update(plan_id=plan['id'], effect_id=plan.get('effect_id'), channel=plan['channel'],
                      accepted_phases=len(accepted), pending_phases=len(actions)-len(accepted),
                      completed_controls=sum(c['status'] == 'completed' for c in expected['controls']),
                      pending_controls=sum(c['status'] != 'completed' for c in expected['controls']))
        coverage = plan.get('coverage', {})
        _require(isinstance(coverage, dict) and isinstance(coverage.get('pending', []), list),
                 'invalid planned coverage')
        result['coverage_pending'] = list(coverage.get('pending', []))
        for index, window in enumerate(accepted, 1):
            _require(_load(job, f'action-{index}-ack.json').get('status') == 'ok',
                     'accepted action is missing its host ACK')
        device = _load(job, 'host-device.json')
        _require(isinstance(device, dict) and isinstance(device.get('profile'), str) and
                 Path(device['profile']).name == device['profile'] and
                 _integer(device.get('bus'), 1) and _integer(device.get('address'), 1),
                 'missing recorded capture identity')
        profile = json.loads((ROOT / 'profiles' / device['profile']).read_text())
        size = profile['transport']['report_size']
        _require(_integer(size, 20), 'invalid profile report size')
        panel = plan['panel']
        _require(isinstance(panel, str) and re.fullmatch(r'[A-Za-z0-9_-]+', panel), 'invalid panel identifier')
        capture_name = f"{panel}-channel{plan['channel']}.pcapng"
        capture = job / capture_name
        _require(capture.is_file() and not capture.is_symlink() and capture.stat().st_size > 0,
                 'missing or empty capture file')
        analysis = _load(job, panel + '-analysis.json')
        _require(isinstance(analysis, dict) and analysis.get('plan_id') == plan['id'] and
                 isinstance(analysis.get('labelled_actions'), list) and
                 len(analysis['labelled_actions']) == len(windows), 'analysis does not match job')
        targets, last_frame = set(), -1
        for window, decoded in zip(accepted, analysis['labelled_actions']):
            _require(isinstance(decoded, dict) and _identity(decoded) == _identity(window),
                     'decoded action identity mismatch')
            first, final = window.get('start_frame_exclusive'), window.get('end_frame_inclusive')
            _require(_integer(first) and _integer(final) and last_frame <= first < final,
                     'invalid or overlapping frame windows')
            last_frame = final
            _require(decoded.get('start_frame_exclusive') == first and
                     decoded.get('end_frame_inclusive') == final, 'decoded frame window mismatch')
            for key in ('candidate_block_feedback', 'guest_visual_result', 'host_accepted'):
                _require(decoded.get(key) == window.get(key), 'decoded evidence differs from accepted window')
            candidate, target = _candidate(decoded, size, capture_name)
            targets.add(target)
            if candidate:
                result['endpoint_candidates'].append(candidate)
        _require(len({(t[2], t[3]) for t in targets}) <= 1, 'effect target changed across actions')
        if targets:
            _, _, effect_type, instance = next(iter(targets))
            result['target'] = {'type': effect_type, 'instance': instance,
                                'families': [{'opcode': hex(t[0]), 'subcommand': hex(t[1])}
                                             for t in sorted(targets)]}
        log = job / 'dumpcap.log'
        _require(log.is_file(), 'missing packet-loss record')
        losses = re.findall(r'Packets received/dropped[^\n]*?:\s*(\d+)/(\d+)',
                            log.read_text(errors='replace'))
        _require(losses and all(int(received) > 0 and int(dropped) == 0
                               for received, dropped in losses),
                 'packet loss absent or nonzero')
        host, guest = _load(job, 'host-completed.json'), _load(job, 'completed.json')
        _require(isinstance(host, dict) and isinstance(guest, dict) and
                 host.get('status') == 'ok' and guest.get('status') == 'ok',
                 'both host and guest completion are required')
        _require(not (job / 'host-error.json').exists() and progress['completed'] is True and
                 not progress.get('error') and len(accepted) == len(actions), 'job is incomplete or failed')
        digest = _digest(capture)
        if 'capture_sha256' in analysis:
            _require(analysis['capture_sha256'] == digest, 'capture hash differs from saved analysis')
        result.update(status='complete', evidence_complete=True, packet_loss=0,
                      review_required=bool(result['coverage_pending'] or result['endpoint_candidates']),
                      capture={'file': capture_name, 'sha256': digest,
                               'analysis_hash_binding_verified': 'capture_sha256' in analysis},
                      restoration=guest.get('range_knobs_left_at', 'see recorded guest restoration evidence'))
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        # Artifact contents/exception text may include payloads or private data;
        # only our bounded validation messages are returned to the console.
        issue = str(error) if isinstance(error, EvidenceError) else 'malformed or inaccessible job evidence'
        result['issues'].append(issue)
    return result


def summarize_jobs(jobs):
    reports = [summarize_job(job) for job in jobs]
    return {'version': 1, 'jobs': reports, 'jobs_complete': sum(j['evidence_complete'] for j in reports),
            'jobs_total': len(reports), 'review_required': any(j['review_required'] for j in reports),
            'evidence_complete': bool(reports) and all(j['evidence_complete'] for j in reports),
            'device_readback_verified': False, 'runtime_authorized': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jobs', nargs='+', type=Path, help='saved capture job directories')
    parser.add_argument('--output', type=Path, help='save detailed compact JSON without dumping payloads')
    args = parser.parse_args(argv)
    report = summarize_jobs(args.jobs)
    if args.output:
        if any(args.output.resolve().is_relative_to(job.resolve()) for job in args.jobs):
            parser.error('output must be outside capture job directories')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', prefix=args.output.name + '.', suffix='.tmp',
                                             dir=args.output.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(report, indent=2) + '\n')
            temporary.replace(args.output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    phases = sum(j['accepted_phases'] for j in report['jobs'])
    review = sum(j['review_required'] for j in report['jobs'])
    print(f"Capture evidence: {report['jobs_complete']}/{report['jobs_total']} jobs complete; "
          f"{phases} accepted phases; {review} jobs need review.")
    for job in report['jobs']:
        if job['issues']:
            print(f"  {job['job']}: {job['issues'][0]}")
    return 0 if report['evidence_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
