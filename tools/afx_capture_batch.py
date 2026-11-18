#!/usr/bin/env python3
"""Run reviewed capture stages through one existing GUI bridge, without HID access.

Preparation and reporting are offline. Execution is opt-in and requires a fresh,
leased bridge. Scripts and inputs are fingerprinted; uncertain actions are never
retried or automatically repaired. Detailed output stays in local artifacts.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
import signal
import subprocess
from pathlib import Path
import re
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCHEMA = 1
PHASES = ('setup', 'capture', 'cleanup')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def local_file(root, name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
        raise ValueError('Stage files must be session-local basenames')
    path = root / name
    if path.is_symlink() or not path.is_file() or path.resolve().parent != root.resolve():
        raise ValueError('Missing or redirected session file: ' + name)
    return path


def completed_effects():
    workflows = read_json(Path(__file__).parent / 'windows/afx-capture-workflows.json')
    return {entry['effect_id'] for entry in workflows['plugins']
            if entry.get('next_step') == 'complete'}


def validate_plan(plan, session):
    if not isinstance(plan, dict) or type(plan.get('version')) is not int or plan['version'] != SCHEMA:
        raise ValueError('Unsupported batch version')
    plugins = plan.get('plugins')
    if not isinstance(plugins, list) or not 1 <= len(plugins) <= 100:
        raise ValueError('Batch needs one to one hundred reviewed plugins')
    ids = set()
    done = completed_effects()
    for plugin in plugins:
        effect = plugin.get('effect_id') if isinstance(plugin, dict) else None
        if not isinstance(effect, str) or not re.fullmatch(r'[a-z0-9_]+', effect) or effect in ids:
            raise ValueError('Distinct stable effect IDs required')
        if 'autotune' in effect.replace('_', ''):
            raise ValueError('Auto-Tune capture remains excluded')
        if effect in done:
            raise ValueError('Effect already complete; prepare a queue of remaining work: ' + effect)
        ids.add(effect)
        steps = plugin.get('steps')
        if not isinstance(steps, list) or not 3 <= len(steps) <= 32:
            raise ValueError('Each plugin needs reviewed setup, capture and cleanup steps')
        phases = [step.get('phase') for step in steps if isinstance(step, dict)]
        if (len(phases) != len(steps) or phases[0] != 'setup' or phases[-1] != 'cleanup'
                or 'capture' not in phases or any(p not in PHASES for p in phases)
                or [PHASES.index(p) for p in phases] != sorted(PHASES.index(p) for p in phases)):
            raise ValueError('Stage order must be setup, capture, cleanup')
        for step in steps:
            script = local_file(session, step.get('script'))
            inputs = local_file(session, step.get('input'))
            if script.suffix.lower() != '.ps1' or inputs.suffix.lower() != '.json':
                raise ValueError('Stages need a PowerShell script and JSON input')
            if digest(script) != step.get('script_sha256') or digest(inputs) != step.get('input_sha256'):
                raise ValueError('Stage content changed; prepare and review a new manifest')
            read_json(inputs)
            seconds = step.get('timeout_seconds', 900)
            if type(seconds) is not int or not 1 <= seconds <= 7200:
                raise ValueError('Stage timeout must be 1..7200 seconds')
    return plan


def prepare(source, session, output):
    plan = read_json(source)
    done = completed_effects()
    if not isinstance(plan, dict) or not isinstance(plan.get('plugins'), list):
        raise ValueError('Draft needs a plugin queue')
    plan['skipped_completed'] = [p['effect_id'] for p in plan['plugins']
                                 if isinstance(p, dict) and p.get('effect_id') in done]
    plan['plugins'] = [p for p in plan['plugins']
                       if not isinstance(p, dict) or p.get('effect_id') not in done]
    if not plan['plugins']:
        raise ValueError('No remaining plugins; all requested effects already complete')
    for plugin in plan.get('plugins', []):
        for step in plugin.get('steps', []):
            step['script_sha256'] = digest(local_file(session, step.get('script')))
            step['input_sha256'] = digest(local_file(session, step.get('input')))
    validate_plan(plan, session)
    if output.exists():
        raise ValueError('Refusing to replace a reviewed manifest')
    write_json(output, plan)
    return plan


@contextmanager
def batch_lock(session):
    with (session / '.capture-batch.lock').open('a+') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another batch owns this session') from None
        yield


def check_pending(session):
    pending = [p.name for p in session.glob('command-*.json')
               if not (session / ('result-' + p.stem[8:] + '.json')).exists()]
    if pending:
        raise RuntimeError('Pending bridge command; reconcile without replay: ' + ', '.join(pending[:3]))


def wait_reply(session, command, timeout, stop_file=None):
    result = session / ('result-' + command + '.json')
    deadline = time.monotonic() + timeout
    while not result.exists():
        if stop_file is not None and stop_file.exists():
            (session / ('cancel-' + command)).touch()
            raise RuntimeError('Stop requested; cancellation sent; child may still be running; do not replay')
        if time.monotonic() >= deadline:
            (session / ('cancel-' + command)).touch()
            raise TimeoutError('Cancellation sent; bridge command may still be running; do not replay: ' + command)
        time.sleep(.2)
    reply = read_json(result)
    if reply.get('status') != 'ok':
        raise RuntimeError('Bridge rejected stage; inspect local result-' + command + '.json')
    return reply


def bridge_identity(session):
    if (session / 'bridge-closed.json').exists():
        raise RuntimeError('Bridge is closed; start a fresh isolated session')
    identity = read_json(session / 'bridge-identity.json')
    if (type(identity.get('version')) is not int or identity['version'] != 1 or not isinstance(identity.get('generation'), str)
            or not re.fullmatch(r'[a-f0-9]{32}', identity['generation'])
            or type(identity.get('expires_epoch')) not in (int, float)
            or not math.isfinite(identity['expires_epoch'])
            or identity['expires_epoch'] <= time.time()):
        raise RuntimeError('Bridge identity absent or expired; start a fresh isolated session')
    return identity


def checked_reply(reply, identity, command):
    if reply.get('generation') != identity['generation'] or reply.get('command_id') != command:
        raise RuntimeError('Stale or uncorrelated bridge reply')


def verify_receipt(session, receipt_name, command, effect, phase, generation):
    receipt = read_json(local_file(session, receipt_name))
    if (receipt.get('status') != 'verified' or receipt.get('continuation_safe') is not True
            or receipt.get('command_id') != command or receipt.get('effect_id') != effect
            or receipt.get('phase') != phase or receipt.get('generation') != generation):
        raise RuntimeError('Missing verified, correlated stage receipt; review required')
    evidence = receipt.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        raise RuntimeError('Stage receipt has no evidence')
    for item in evidence:
        if not isinstance(item, dict) or digest(local_file(session, item.get('file'))) != item.get('sha256'):
            raise RuntimeError('Stage evidence missing or changed')
    jobs = receipt.get('capture_jobs', [])
    if not isinstance(jobs, list):
        raise RuntimeError('Malformed capture job references')
    if phase == 'capture' and not jobs:
        raise RuntimeError('Capture stage must reference host-verified jobs')
    summaries = []
    if jobs:
        from tools.afx_capture_summary import summarize_job
        for name in jobs:
            if not isinstance(name, str) or not re.fullmatch(r'scan-[A-Za-z0-9_-]+', name):
                raise RuntimeError('Invalid capture job name')
            job = session.parent / name
            if job.is_symlink() or job.resolve().parent != session.parent.resolve():
                raise RuntimeError('Capture job redirected outside results')
            summary = summarize_job(job)
            if (summary.get('evidence_complete') is not True or summary.get('effect_id') != effect
                    or summary.get('capture', {}).get('analysis_hash_binding_verified') is not True):
                raise RuntimeError('Capture evidence incomplete, unbound or wrong effect; inspect job summary')
            summaries.append(summary)
    if phase == 'cleanup' and receipt.get('trial_removed') is not True:
        raise RuntimeError('Cleanup did not verify removal of the trial')
    return {**receipt, 'capture_summaries': summaries}


def compact(state):
    result = {key: state[key] for key in ('status', 'total_plugins',
              'current_effect', 'current_phase', 'pending_command', 'review_required', 'reason')}
    result['completed_plugins'] = len(state['completed_plugins'])
    result['pending_review_jobs'] = len(state['pending_review_jobs'])
    return result


def run(plan, session, output, stop_file=None):
    """One execution only. A failed or interrupted directory cannot be resumed."""
    validate_plan(plan, session)
    output.mkdir(exist_ok=False)
    state = dict(version=1, status='starting', plan_sha256=fingerprint(plan),
                 completed_plugins=[], pending_review_jobs=[], total_plugins=len(plan['plugins']), current_effect=None,
                 current_phase=None, pending_command=None, review_required=False, reason=None)
    write_json(output / 'plan.json', plan)
    def save():
        write_json(output / 'state.json', state)
        write_json(output / 'summary.json', compact(state))
    save()
    try:
        with batch_lock(session):
            check_pending(session)
            identity = bridge_identity(session)
            command = uuid.uuid4().hex
            state.update(status='checking_bridge', pending_command=command)
            save()  # Intent is durable BEFORE dispatch; crash recovery never resends it.
            write_json(session / ('command-' + command + '.json'),
                       dict(action='hello', generation=identity['generation']))
            reply = wait_reply(session, command, 15, stop_file)
            checked_reply(reply, identity, command)
            state['pending_command'] = None
            save()
            for plugin in plan['plugins']:
                state['current_effect'] = plugin['effect_id']
                state['current_phase'] = None
                remaining_budget = sum(step.get('timeout_seconds', 900) for step in plugin['steps']) + 30
                if identity['expires_epoch'] - time.time() < remaining_budget:
                    raise RuntimeError('Bridge lease cannot cover this plugin including cleanup; renew in a fresh session')
                for index, step in enumerate(plugin['steps']):
                    if stop_file is not None and stop_file.exists():
                        raise RuntimeError('Stop requested; reconcile any remaining trial before continuing')
                    validate_plan(plan, session)  # Recheck immutable scripts/inputs before each stage.
                    if bridge_identity(session) != identity:
                        raise RuntimeError('Bridge session changed')
                    check_pending(session)
                    command = uuid.uuid4().hex
                    receipt = 'receipt-' + command + '.json'
                    state.update(status='running', current_phase=step['phase'], pending_command=command)
                    save()
                    request = dict(action='script', generation=identity['generation'],
                                   file=step['script'], script_sha256=step['script_sha256'],
                                   input=step['input'], input_sha256=step['input_sha256'],
                                   receipt=receipt, effect_id=plugin['effect_id'], phase=step['phase'],
                                   timeout_seconds=step.get('timeout_seconds', 900))
                    write_json(session / ('command-' + command + '.json'), request)
                    reply = wait_reply(session, command, step.get('timeout_seconds', 900), stop_file)
                    checked_reply(reply, identity, command)
                    verified = verify_receipt(session, receipt, command, plugin['effect_id'],
                                              step['phase'], identity['generation'])
                    write_json(output / (f"{plugin['effect_id']}-{index:02d}.json"), verified)
                    for summary in verified['capture_summaries']:
                        if summary.get('review_required'):
                            state['pending_review_jobs'].append(summary['job'])
                    state['pending_command'] = None
                    save()
                state['completed_plugins'].append(plugin['effect_id'])
                save()
            state.update(status='completed', current_effect=None, current_phase=None,
                         review_required=bool(state['pending_review_jobs']))
            save()
    except BaseException as error:
        if state['pending_command'] is not None:
            (session / ('cancel-' + state['pending_command'])).touch()
        state.update(status='review_required', review_required=True,
                     reason=str(error) if isinstance(error, Exception) else 'Interrupted; reconcile saved command')
        save()
        if not isinstance(error, Exception):
            raise
    return compact(state)


@contextmanager
def managed_recorder(shared, output):
    """Own one passive coordinator; never attach to or kill somebody else's."""
    log_path = output.with_name(output.name + '-recorder.log')
    with log_path.open('x') as log:
        process = subprocess.Popen([sys.executable, '-u',
            str(Path(__file__).with_name('afx_vm_pilot.py')), '--shared', str(shared),
            '--serve', '--wait-seconds', '3600'], stdout=log, stderr=log, start_new_session=True)
        try:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Recorder unavailable; inspect ' + str(log_path))
                if 'Ready for GUI scan/discovery requests;' in log_path.read_text():
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Recorder readiness timeout; no bridge actions dispatched')
                time.sleep(.2)
            yield
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            # Also stop any leftover descendants in this coordinator's owned process group.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def main(argv=None):
    # Cooperatively cancel the pending stage when the host runner is terminated.
    signal.signal(signal.SIGTERM, interrupt_runner)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--prepare', type=Path, metavar='DRAFT_JSON')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-reviewed', action='store_true')
    parser.add_argument('--stop-file', type=Path)
    parser.add_argument('--shared', type=Path, help='kit root; execution starts one owned passive recorder')
    args = parser.parse_args(argv)
    try:
        if args.prepare and args.plan:
            raise ValueError('Preparation and execution/validation are separate modes')
        if args.prepare and not args.plan and not args.execute_reviewed and args.session:
            plan = prepare(args.prepare, args.session.resolve(), args.output)
            print(json.dumps({'status': 'prepared_offline', 'plugins': len(plan['plugins']),
                              'manifest': str(args.output)}, separators=(',', ':')))
            return 0
        if args.plan and args.session:
            plan = validate_plan(read_json(args.plan), args.session.resolve())
            if not args.execute_reviewed:
                print(json.dumps({'status': 'validated_offline', 'plugins': len(plan['plugins'])}))
                return 0
            if args.prepare:
                raise ValueError('Preparation cannot combine with execution')
            if args.shared is None or args.session.resolve().parent != (args.shared / 'results').resolve():
                raise ValueError('Execution requires --shared with this session directly under kit/results')
            if args.output.exists():
                raise ValueError('Batch output already exists; uncertain runs are never replayed')
            with managed_recorder(args.shared.resolve(), args.output):
                result = run(plan, args.session.resolve(), args.output, args.stop_file)
            print(json.dumps(result, separators=(',', ':')))
            return 0 if result['status'] == 'completed' else 2
        parser.error('Choose --prepare DRAFT --session DIR, or --plan MANIFEST --session DIR')
    except KeyboardInterrupt:
        print(json.dumps({'status': 'review_required', 'reason': 'Interrupted; inspect saved state, do not replay'}))
        return 130
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({'status': 'review_required', 'reason': str(error)}, separators=(',', ':')))
        return 2


def interrupt_runner(signum, frame):
    raise KeyboardInterrupt


if __name__ == '__main__':
    raise SystemExit(main())
