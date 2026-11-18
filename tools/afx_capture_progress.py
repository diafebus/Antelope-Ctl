"""Pure-data capture checkpoints and REVIEW-ONLY remaining-plan previews.

An accepted phase means the caller verified its evidence and issued its ACK.
This module does not infer acceptance from guest files, replay gestures, restore
controls, or authorize a capture. After interruption the reviewer must reconcile
the live GUI/device state. Even completed phases are not a fresh device readback.
Knob batches intentionally finish at the maximum candidate, without restoration.
"""
import copy
import hashlib
import json


def _fingerprint(plan):
    try:
        payload = json.dumps(plan, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('Capture plan must contain finite JSON data') from exc
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _schedule(plan):
    if (not isinstance(plan, dict) or not isinstance(plan.get('id'), str)
            or not plan['id'].strip() or not isinstance(plan.get('controls'), list)
            or not plan['controls']):
        raise ValueError('Capture progress needs a named plan with controls')
    result, ids = [], set()
    for control in plan['controls']:
        if (not isinstance(control, dict) or not isinstance(control.get('id'), str)
                or not control['id'].strip() or control['id'] in ids):
            raise ValueError('Capture control identities must be distinct strings')
        ids.add(control['id'])
        kind = control.get('kind', 'binary_button')
        if kind == 'knob_range':
            phases = ['minimum', 'maximum']
        elif kind == 'wheel_button':
            phases = ['wheel forward', 'wheel back']
        elif kind == 'key_button':
            phases = ['PageDown', 'PageUp']
        elif kind in ('selector_cycle', 'selector_positions', 'menu_positions'):
            count = control.get('positions')
            if type(count) is not int or not 2 <= count <= 8:
                raise ValueError('Capture selector phase count is invalid')
            phases = [f'position-{n}' for n in range(1, count + 1)]
            if kind != 'selector_cycle':
                phases.append('restore')
        elif kind == 'binary_button':
            phases = ['click', 'click back']
        else:
            raise ValueError('Unknown capture control kind')
        result.extend((control, phase) for phase in phases)
    _fingerprint(plan)
    return result


def _identity(index, control, phase):
    return {'action': index, 'control': control['id'], 'gesture': phase}


def progress_snapshot(plan, actions, accepted_windows, current_action=None, error=None, completed=False):
    """Build deterministic JSON data, counting only a matching accepted prefix.

    ``actions`` is the coordinator's list of ``(control, phase)`` pairs. Windows
    must match one-based action/control/gesture identities, in order. A current
    action is the next unaccepted index or its identity dictionary; it may have
    moved hardware already, so its restoration state is explicitly unknown.
    """
    expected = _schedule(plan)
    if not isinstance(actions, (list, tuple)) or _fingerprint(actions) != _fingerprint(expected):
        raise ValueError('Capture actions do not match the original plan')
    if not isinstance(accepted_windows, list) or len(accepted_windows) > len(expected):
        raise ValueError('Accepted capture windows must be a bounded list')
    accepted = []
    for index, window in enumerate(accepted_windows, 1):
        control, phase = expected[index - 1]
        identity = _identity(index, control, phase)
        if (not isinstance(window, dict) or type(window.get('action')) is not int
                or any(window.get(key) != value for key, value in identity.items())):
            raise ValueError('Accepted window does not match its action/control/gesture')
        accepted.append(identity)
    if type(completed) is not bool or (error is not None and not isinstance(error, str)):
        raise ValueError('Capture completion/error metadata is invalid')
    if current_action is not None:
        next_index = len(accepted) + 1
        if next_index > len(expected):
            raise ValueError('Current action exceeds the remaining capture schedule')
        identity = _identity(next_index, *expected[next_index - 1])
        if type(current_action) is int:
            if current_action != next_index:
                raise ValueError('Current action must be the next unaccepted phase')
        elif (not isinstance(current_action, dict) or set(current_action) != set(identity)
              or type(current_action.get('action')) is not int or current_action != identity):
            raise ValueError('Current action identity differs from the next phase')
        current_action = identity
    if completed and (len(accepted) != len(expected) or current_action is not None or error is not None):
        raise ValueError('Completed capture requires all accepted phases and no error/current action')
    controls = []
    for control in plan['controls']:
        phases = [phase for candidate, phase in expected if candidate['id'] == control['id']]
        accepted_phases = [row['gesture'] for row in accepted if row['control'] == control['id']]
        interrupted = current_action is not None and current_action['control'] == control['id']
        status = ('completed' if len(accepted_phases) == len(phases)
                  else 'partial' if accepted_phases or interrupted else 'pending')
        if status == 'partial':
            restoration = 'unknown; reconcile live state before any further gesture'
        elif status == 'pending':
            restoration = 'not attempted by this capture; live state unverified'
        elif control.get('kind') == 'knob_range':
            restoration = 'intentionally not restored; ends at maximum candidate'
        else:
            restoration = 'accepted phases only; current restoration state unverified'
        controls.append({'id': control['id'], 'status': status, 'phases': phases,
                         'total_phases': len(phases), 'accepted_phases': accepted_phases,
                         'accepted_count': len(accepted_phases), 'restoration_status': restoration})
    return {
        'version': 1, 'plan_id': plan['id'], 'plan_fingerprint': _fingerprint(plan),
        'status': 'completed' if completed else 'failed' if error is not None else 'in-progress',
        'completed': completed, 'error': error, 'current_action': current_action,
        'total_actions': len(expected), 'accepted_count': len(accepted),
        'accepted_actions': accepted, 'controls': controls,
        'resume_requires_review': True, 'runtime_authorized': False,
        'state_warning': 'Checkpoint acceptance is capture evidence, not fresh GUI/device state. Reconcile interrupted controls; never blindly restore or replay.'
    }


def remaining_plan(plan, progress):
    """Preview whole unfinished controls, preserving original scope and unknowns.

    Partial controls remain complete units in the preview. No current-state
    baseline or restoration permission is inferred from the saved checkpoint.
    """
    actions = _schedule(plan)
    if (not isinstance(progress, dict) or progress.get('plan_fingerprint') != _fingerprint(plan)
            or progress.get('plan_id') != plan['id']):
        raise ValueError('Capture checkpoint belongs to a different original plan')
    expected = progress_snapshot(plan, actions, progress.get('accepted_actions'),
        current_action=progress.get('current_action'), error=progress.get('error'),
        completed=progress.get('completed'))
    if _fingerprint(progress) != _fingerprint(expected):
        raise ValueError('Capture checkpoint schema or derived progress is inconsistent')
    done = {control['id'] for control in expected['controls'] if control['status'] == 'completed'}
    if len(done) == len(plan['controls']):
        raise ValueError('All capture controls already have accepted phases; no remaining plan')
    result = copy.deepcopy(plan)
    result['id'] = 'resume-' + plan['id']
    result['controls'] = [control for control in result['controls'] if control['id'] not in done]
    result['original_plan_id'] = plan['id']
    result['original_plan_fingerprint'] = _fingerprint(plan)
    result['resume_requires_review'] = True
    result['runtime_authorized'] = False
    result['preview_only'] = True
    result['resume_review'] = {
        'completed_controls_omitted': [control['id'] for control in expected['controls']
                                       if control['status'] == 'completed'],
        'partial_controls_requiring_reconciliation': [control['id'] for control in expected['controls']
                                                       if control['status'] == 'partial'],
        'requirements': [
            'Review the original capture evidence and current GUI/device identity and state.',
            'Reconcile every interrupted control before preparing a separately reviewed runtime plan.',
            'Do not replay partial phases or blindly restore values from this preview.',
            'Knob batches intentionally end at maximum candidates, without restoration.'
        ]
    }
    return result
