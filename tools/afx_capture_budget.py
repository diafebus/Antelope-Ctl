"""Finite wall-clock budgets shared by passive capture and the Windows runner.

These are failure deadlines, not requested delays. Native sweeps request at
most 800 pixels in four-pixel steps (12 ms per step plus 200 ms held), followed
by 500 ms hover settling. Budget eight seconds for that operation and UIA
guards. Host parsing is bounded to twenty seconds and peer responses have
forty-five seconds of tolerance. Processing and response deadlines overlap;
they are not two consecutive sleeps.
The recorder must cover every allowed sweep, rather than expire at an
unrelated fixed duration halfway through a large panel.
"""
import math


MAX_CONTROLS = 24
MAX_SWEEPS = 12
MAX_CAPTURE_SECONDS = 12 * 60 * 60
GESTURE_SECONDS = 8
FEEDBACK_SECONDS = 45
PARSE_SECONDS = 20
REQUEST_SECONDS = 45
FINALIZATION_SECONDS = 60
KINDS = frozenset(('knob_range', 'binary_button', 'selector_cycle',
                   'selector_positions', 'wheel_button', 'menu_positions',
                   'key_button'))


def bounded_integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{label} must be an integer from {minimum} to {maximum}')
    return value


def phase_count(control):
    kind = control.get('kind')
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError('Unsupported capture gesture')
    if kind in ('selector_cycle', 'selector_positions', 'menu_positions'):
        count = bounded_integer(control.get('positions'), 2, 8, 'Selector positions')
        return count + (kind != 'selector_cycle')
    return 2


def phase_seconds(control, plan=None):
    """Maximum allowed work in one action, including its host responses."""
    phase_count(control)
    kind = control['kind']
    if kind == 'knob_range':
        # Two-direction priming is permitted even if the knob begins clamped.
        priming = 2 * GESTURE_SECONDS + FEEDBACK_SECONDS
        sweeps = MAX_SWEEPS * (GESTURE_SECONDS + FEEDBACK_SECONDS)
        return priming + sweeps + GESTURE_SECONDS + FEEDBACK_SECONDS
    dwell = 1
    if kind == 'key_button':
        dwell = math.ceil(bounded_integer(control.get('dwell_ms'), 5000, 5000,
                                          'Key dwell') / 1000)
    elif kind == 'menu_positions':
        dwell = math.ceil(bounded_integer(control.get('dwell_ms'), 3000, 10000,
                                          'Menu dwell') / 1000)
    elif kind == 'wheel_button':
        policy = (plan or {}).get('wheel_policy', {})
        if not isinstance(policy, dict):
            raise ValueError('Wheel policy must be an object')
        pulses = bounded_integer(policy.get('max_pulses'), 1, 12, 'Wheel pulses')
        pause = bounded_integer(policy.get('pause_ms'), 1000, 3000, 'Wheel pause')
        delta = bounded_integer(policy.get('step_delta'), 1, 30, 'Wheel delta')
        if delta * pulses > 120 or pause * pulses > 20000:
            raise ValueError('Wheel policy exceeds bounded movement or dwell')
        # A screenshot and UIA guards may follow each individual pulse.
        return pulses * (math.ceil(pause / 1000) + GESTURE_SECONDS) + FEEDBACK_SECONDS
    # Named menus may need discovery, a priming selection, target selection,
    # screenshots and closure checks, rather than a single click.
    operations = 4 if kind in ('menu_positions', 'selector_positions') else 2
    return operations * GESTURE_SECONDS + dwell + FEEDBACK_SECONDS


def capture_budget(plan, reviewed_resume=False):
    """Return JSON-compatible deadlines for a reviewed or generated plan.

    Deadline values are integers in seconds, apart from max_sweeps. Invalid plans
    fail instead of silently clipping a required duration to a smaller cap.
    Consumers may use action_seconds when a single common action wait is
    needed, or phase_seconds(control, plan) for individual action waits.
    ``reviewed_resume`` permits a validated mixed plan's non-knob remainder
    to retain its original control bound after its knobs are omitted. The
    caller must validate that ancestry; a flag in guest plan data is not proof.
    """
    if not isinstance(plan, dict) or not isinstance(plan.get('controls'), list):
        raise ValueError('Capture plan needs a controls list')
    controls = plan['controls']
    if type(reviewed_resume) is not bool:
        raise ValueError('Reviewed resume must be an explicit boolean')
    if not 1 <= len(controls) <= MAX_CONTROLS or any(not isinstance(c, dict) for c in controls):
        raise ValueError('Capture plan requires one to twenty-four controls')
    if not reviewed_resume and not any(c.get('kind') == 'knob_range' for c in controls) and len(controls) > 3:
        raise ValueError('A plan without knobs permits at most three controls')
    phases = [(phase_count(c), phase_seconds(c, plan)) for c in controls]
    # Include preflight/readiness, setup before every request, final analysis
    # and host/guest completion; none of those consume a sweep's time budget.
    duration = 30 + sum(n * (REQUEST_SECONDS + seconds) for n, seconds in phases)
    duration += 2 * FINALIZATION_SECONDS
    bounded_integer(duration, 1, MAX_CAPTURE_SECONDS, 'Capture duration')
    return {
        'capture_seconds': duration,
        'ready_seconds': 30,
        'request_seconds': REQUEST_SECONDS,
        'priming_seconds': 2 * GESTURE_SECONDS + FEEDBACK_SECONDS,
        'sweep_seconds': GESTURE_SECONDS + 7,
        'feedback_seconds': FEEDBACK_SECONDS,
        'parse_seconds': PARSE_SECONDS,
        'action_seconds': max(seconds for _, seconds in phases),
        'completed_seconds': FINALIZATION_SECONDS,
        'finalization_seconds': FINALIZATION_SECONDS,
        'max_sweeps': MAX_SWEEPS,
        'limit_kib': max(100000, min(1000000, math.ceil(duration / 600) * 100000)),
        'metadata': {
            'source': 'sum of all allowed gesture and peer-response waits; parsing fits inside peer response',
            'capture_policy_seconds': MAX_CAPTURE_SECONDS,
            'capture_policy_kib': 1000000,
            'capture_limit_clamped': False,
            'reviewed_resume': reviewed_resume,
            'deadlines_are_delays': False,
            'on_limit': 'stop, retain confirmed progress and report recorder duration/size limit; never restart gestures',
        },
    }
