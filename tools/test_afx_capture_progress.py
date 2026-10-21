"""Checkpoints retain accepted work without claiming replay/restoration safety."""
import copy
import json
import unittest

from tools.afx_capture_progress import progress_snapshot, remaining_plan
from tools.afx_vm_pilot import planned_actions


class CaptureProgressTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            'id': 'test-controls', 'channel': 2, 'panel': 'Test', 'effect_id': 'test',
            'coverage': {'pending': ['Q disabled', 'dropdown full count unresolved']},
            'controls': [{'id': 'Level', 'kind': 'knob_range', 'label': 'Level'},
                         {'id': 'Mode', 'kind': 'binary_button', 'label': 'Mode'},
                         {'id': 'Filter', 'kind': 'key_button', 'label': 'Filter'}]
        }
        self.actions = planned_actions(self.plan)

    def windows(self, count):
        return [{'action': index, 'control': control['id'], 'gesture': phase,
                 'guest_visual_result': {'status': 'ok'}}
                for index, (control, phase) in enumerate(self.actions[:count], 1)]

    def test_only_accepted_phases_count_and_current_phase_remains_partial(self):
        progress = progress_snapshot(self.plan, self.actions, self.windows(3), current_action=4,
                                     error='Guest stopped during restore')
        self.assertEqual(progress['accepted_count'], 3)
        self.assertEqual([row['status'] for row in progress['controls']], ['completed', 'partial', 'pending'])
        self.assertEqual(progress['controls'][1]['accepted_phases'], ['click'])
        self.assertIn('unknown', progress['controls'][1]['restoration_status'])
        self.assertEqual(progress['current_action'], {'action': 4, 'control': 'Mode', 'gesture': 'click back'})
        self.assertEqual(progress['status'], 'failed')
        self.assertIn('maximum candidate', progress['controls'][0]['restoration_status'])
        self.assertIs(progress['runtime_authorized'], False)

    def test_interrupted_first_phase_is_partial_without_any_accepted_evidence(self):
        progress = progress_snapshot(self.plan, self.actions, [], current_action=1, error='timeout')
        self.assertEqual(progress['controls'][0]['status'], 'partial')
        self.assertEqual(progress['controls'][0]['accepted_count'], 0)
        self.assertIn('unknown', progress['controls'][0]['restoration_status'])

    def test_remaining_preview_omits_only_completed_controls_and_preserves_scope(self):
        original = copy.deepcopy(self.plan)
        progress = progress_snapshot(self.plan, self.actions, self.windows(3), current_action=4, error='timeout')
        preview = remaining_plan(self.plan, json.loads(json.dumps(progress)))
        self.assertEqual([control['id'] for control in preview['controls']], ['Mode', 'Filter'])
        self.assertEqual(preview['coverage'], self.plan['coverage'])
        self.assertEqual(preview['channel'], 2)
        self.assertEqual(preview['original_plan_id'], self.plan['id'])
        self.assertEqual(preview['id'], 'resume-' + self.plan['id'])
        self.assertIs(preview['preview_only'], True)
        self.assertIs(preview['resume_requires_review'], True)
        self.assertIs(preview['runtime_authorized'], False)
        self.assertEqual(preview['resume_review']['partial_controls_requiring_reconciliation'], ['Mode'])
        self.assertEqual(planned_actions(preview)[0][1], 'click')
        preview['coverage']['pending'].append('new note')
        self.assertEqual(self.plan, original)

    def test_fingerprint_covers_full_plan_and_ignores_dictionary_key_order(self):
        progress = progress_snapshot(self.plan, self.actions, self.windows(2))
        reordered = {key: self.plan[key] for key in reversed(self.plan)}
        other = progress_snapshot(reordered, planned_actions(reordered), self.windows(2))
        self.assertEqual(progress['plan_fingerprint'], other['plan_fingerprint'])
        for field, value in [('channel', 3), ('coverage', {'pending': []}), ('panel', 'Other')]:
            foreign = copy.deepcopy(self.plan); foreign[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'different original plan'):
                remaining_plan(foreign, progress)

    def test_accepted_windows_cannot_skip_duplicate_or_change_action_identity(self):
        for field, value in [('action', True), ('action', 2), ('control', 'Other'), ('gesture', 'maximum')]:
            windows = self.windows(1); windows[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                progress_snapshot(self.plan, self.actions, windows)
        for windows in (None, [None], self.windows(2)[::-1], self.windows(1) * 2,
                        self.windows(6) + self.windows(1)):
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                progress_snapshot(self.plan, self.actions, windows)
        wrong_actions = copy.deepcopy(self.actions); wrong_actions[0] = (wrong_actions[0][0], 'maximum')
        with self.assertRaises(ValueError):
            progress_snapshot(self.plan, wrong_actions, [])

    def test_invalid_current_action_and_inconsistent_completion_fail(self):
        for current in (True, 0, 2, {}, {'action': 1, 'control': 'Level', 'gesture': 'maximum'}):
            with self.subTest(current=current), self.assertRaises(ValueError):
                progress_snapshot(self.plan, self.actions, [], current_action=current)
        for kwargs in ({'completed': True}, {'completed': 1}, {'error': {}},
                       {'completed': True, 'error': 'failure'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                progress_snapshot(self.plan, self.actions, [], **kwargs)
        with self.assertRaises(ValueError):
            progress_snapshot(self.plan, self.actions, self.windows(6), current_action=7)

    def test_tampered_derived_checkpoint_fields_are_rejected(self):
        original = progress_snapshot(self.plan, self.actions, self.windows(2))
        cases = []
        for field, value in [('version', True), ('accepted_count', True), ('plan_id', 'other'),
                             ('status', 'completed'), ('completed', True), ('runtime_authorized', True),
                             ('resume_requires_review', False), ('accepted_actions', []),
                             ('controls', []), ('plan_fingerprint', '0' * 64)]:
            progress = copy.deepcopy(original); progress[field] = value; cases.append(progress)
        progress = copy.deepcopy(original); del progress['error']; cases.append(progress)
        progress = copy.deepcopy(original); progress['controls'][1]['status'] = 'completed'; cases.append(progress)
        progress = copy.deepcopy(original); progress['controls'][0]['accepted_count'] = True; cases.append(progress)
        for progress in (None, [], {}, *cases):
            with self.subTest(progress=progress), self.assertRaises(ValueError):
                remaining_plan(self.plan, progress)

    def test_all_accepted_controls_have_no_resume_even_before_final_completion(self):
        for completed in (False, True):
            progress = progress_snapshot(self.plan, self.actions, self.windows(6), completed=completed)
            self.assertEqual([row['status'] for row in progress['controls']], ['completed'] * 3)
            with self.subTest(completed=completed), self.assertRaisesRegex(ValueError, 'already have accepted'):
                remaining_plan(self.plan, progress)

    def test_phase_schedules_cover_every_supported_gesture_and_minimal_mocks(self):
        plan = {'id': 'all-kinds', 'controls': [
            {'id': 'Mock'}, {'id': 'Wheel', 'kind': 'wheel_button'},
            {'id': 'Cycle', 'kind': 'selector_cycle', 'positions': 3},
            {'id': 'Selector', 'kind': 'selector_positions', 'positions': 2},
            {'id': 'Menu', 'kind': 'menu_positions', 'positions': 2}]}
        # Older callers/tests may omit kind for a generic two-click mock.
        actions = [(plan['controls'][0], 'click'), (plan['controls'][0], 'click back')]
        actions += planned_actions({'controls': plan['controls'][1:]})
        progress = progress_snapshot(plan, actions, [])
        self.assertEqual(progress['total_actions'], 13)
        self.assertEqual(progress['controls'][2]['phases'], ['position-1', 'position-2', 'position-3'])
        self.assertEqual(progress['controls'][3]['phases'][-1], 'restore')
        self.assertEqual(progress['controls'][4]['phases'][-1], 'restore')
        self.assertEqual(len(remaining_plan(plan, progress)['controls']), 5)

    def test_malformed_plan_scope_and_nonfinite_metadata_fail(self):
        for plan in (None, {}, {'id': 'x', 'controls': []}, {'id': 'x', 'controls': [None]},
                     {'id': 'x', 'controls': [{'id': 'a'}, {'id': 'a'}]},
                     {'id': 'x', 'controls': [{'id': 'a', 'kind': 'unknown'}]},
                     {'id': 'x', 'controls': [{'id': 'a', 'kind': 'selector_positions', 'positions': True}]}):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                progress_snapshot(plan, [], [])
        plan = copy.deepcopy(self.plan); plan['bad_metadata'] = float('nan')
        with self.assertRaises(ValueError):
            progress_snapshot(plan, self.actions, [])


if __name__ == '__main__':
    unittest.main()
