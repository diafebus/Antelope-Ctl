"""Offline deadline regressions for large, interrupted and slow GUI scans."""
import unittest

from tools.afx_capture_budget import (
    MAX_CAPTURE_SECONDS, MAX_SWEEPS, capture_budget, phase_count, phase_seconds,
)


class CaptureBudgetTests(unittest.TestCase):
    def test_twenty_four_knobs_fit_every_permitted_sweep_and_handshake(self):
        control = {'kind': 'knob_range', 'feedback': 'captured_block'}
        small = capture_budget({'controls': [control]})
        large = capture_budget({'controls': [control] * 24})
        self.assertGreater(large['capture_seconds'], 600)
        self.assertLessEqual(large['capture_seconds'], MAX_CAPTURE_SECONDS)
        minimum_phase = 2 * 8 + 45 + MAX_SWEEPS * (8 + 45) + 8 + 45
        self.assertGreaterEqual(large['action_seconds'], minimum_phase)
        self.assertGreaterEqual(large['capture_seconds'], 48 * minimum_phase)
        self.assertGreater(large['capture_seconds'], small['capture_seconds'])
        self.assertEqual(small['max_sweeps'], MAX_SWEEPS)

    def test_known_and_discovered_knobs_share_gesture_deadlines(self):
        for feedback in ('captured_wire', 'captured_block', 'numeric'):
            self.assertEqual(phase_seconds({'kind': 'knob_range', 'feedback': feedback}),
                             phase_seconds({'kind': 'knob_range'}))

    def test_restoring_selector_and_menu_phases_are_included(self):
        cycle = {'kind': 'selector_cycle', 'positions': 8}
        direct = {'kind': 'selector_positions', 'positions': 8}
        menu = {'kind': 'menu_positions', 'positions': 8, 'dwell_ms': 10000}
        self.assertEqual(phase_count(cycle), 8)
        self.assertEqual(phase_count(direct), 9)
        self.assertEqual(phase_count(menu), 9)
        budget = capture_budget({'controls': [menu]})
        self.assertGreaterEqual(budget['capture_seconds'], 9 * phase_seconds(menu))

    def test_slow_wheel_accounts_for_each_pulse_and_screenshot(self):
        plan = {'controls': [{'kind': 'wheel_button'}], 'wheel_policy': {
            'step_delta': 10, 'pause_ms': 1500, 'max_pulses': 12}}
        budget = capture_budget(plan)
        self.assertGreaterEqual(budget['action_seconds'], 12 * (2 + 8) + 45)
        self.assertGreaterEqual(budget['capture_seconds'], 2 * budget['action_seconds'])

    def test_key_and_binary_plans_have_bounded_finite_waits(self):
        for control in ({'kind': 'key_button', 'dwell_ms': 5000},
                        {'kind': 'binary_button', 'feedback': 'gui_toggle'}):
            budget = capture_budget({'controls': [control]})
            self.assertTrue(all(type(n) is int and n > 0 for key, n in budget.items()
                                if key != 'metadata'))
            self.assertGreater(budget['request_seconds'], 15)
            self.assertGreater(budget['feedback_seconds'], 10)
            self.assertEqual(budget['parse_seconds'], 20)

    def test_size_ceiling_and_timing_policy_are_explicit(self):
        budget = capture_budget({'controls': [{'kind': 'knob_range'}] * 24})
        self.assertLessEqual(budget['limit_kib'], 1000000)
        self.assertGreaterEqual(budget['limit_kib'], 100000)
        self.assertEqual(budget['metadata']['capture_policy_seconds'], MAX_CAPTURE_SECONDS)
        self.assertFalse(budget['metadata']['capture_limit_clamped'])
        self.assertFalse(budget['metadata']['deadlines_are_delays'])

    def test_non_knob_remainder_keeps_validated_mixed_plan_bound_only_after_review(self):
        toggles = [{'kind': 'binary_button', 'feedback': 'gui_toggle'}] * 4
        original = capture_budget({'controls': [{'kind': 'knob_range'}, *toggles]})
        remainder = {'controls': toggles, 'resume_reviewed': True}
        with self.assertRaises(ValueError):
            capture_budget(remainder)
        resumed = capture_budget(remainder, reviewed_resume=True)
        self.assertLess(resumed['capture_seconds'], original['capture_seconds'])
        self.assertTrue(resumed['metadata']['reviewed_resume'])
        self.assertLessEqual(resumed['capture_seconds'], MAX_CAPTURE_SECONDS)
        with self.assertRaises(ValueError):
            capture_budget({'controls': toggles * 7}, reviewed_resume=True)
        with self.assertRaises(ValueError):
            capture_budget(remainder, reviewed_resume=1)

    def test_bad_or_oversized_plans_never_produce_unbounded_timeouts(self):
        invalid = [None, {}, {'controls': []}, {'controls': [None]},
                   {'controls': [{'kind': 'unknown'}]},
                   {'controls': [{'kind': []}]},
                   {'controls': [{'kind': 'knob_range'}] * 25},
                   {'controls': [{'kind': 'binary_button'}] * 4},
                   {'controls': [{'kind': 'selector_cycle', 'positions': True}]},
                   {'controls': [{'kind': 'menu_positions', 'positions': 2, 'dwell_ms': float('inf')}]},
                   {'controls': [{'kind': 'key_button', 'dwell_ms': 60000}]},
                   {'controls': [{'kind': 'wheel_button'}], 'wheel_policy': None},
                   {'controls': [{'kind': 'wheel_button'}], 'wheel_policy': {
                       'step_delta': 30, 'pause_ms': 3000, 'max_pulses': 12}}]
        for plan in invalid:
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                capture_budget(plan)


if __name__ == '__main__':
    unittest.main()
