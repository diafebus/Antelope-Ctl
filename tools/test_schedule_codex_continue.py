"""Offline scheduling checks: no real session receives a message."""
import argparse
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from tools.schedule_codex_continue import dispatch, timestamp


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.stop = self.at + timedelta(hours=3)

    def test_explicit_timezone_required(self):
        self.assertEqual(timestamp("2030-01-01T01:00+01:00"), self.at)
        with self.assertRaises(argparse.ArgumentTypeError):
            timestamp("2030-01-01T00:00")

    def test_wait_then_single_failed_send_without_retry(self):
        times = iter([self.at - timedelta(seconds=45), self.at])
        waits, sends = [], []

        def run(command, **kwargs):
            sends.append((command, kwargs))
            return SimpleNamespace(returncode=7)

        result = dispatch(self.at, self.stop, ["fake", "queue"],
                          now=lambda: next(times), sleep=waits.append, run=run)
        self.assertEqual(waits, [30])
        self.assertEqual(result, 7)
        self.assertEqual(sends, [(["fake", "queue"],
                                 {"check": False, "timeout": 60})])

    def test_suspend_past_delivery_window_does_not_send(self):
        def unexpected(*args, **kwargs):
            self.fail("must not send")

        for late in (self.at + timedelta(minutes=11), self.stop):
            with self.subTest(late=late), self.assertRaises(RuntimeError):
                dispatch(self.at, self.stop, ["fake"], now=lambda: late,
                         run=unexpected)

    def test_deadline_before_ten_minute_grace_still_blocks(self):
        with self.assertRaises(RuntimeError):
            dispatch(self.at, self.at + timedelta(minutes=2), ["fake"],
                     now=lambda: self.at + timedelta(minutes=3),
                     run=lambda *args, **kwargs: self.fail("must not send"))


if __name__ == "__main__":
    unittest.main()
