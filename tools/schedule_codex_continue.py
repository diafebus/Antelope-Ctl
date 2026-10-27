#!/usr/bin/env python3
"""Send one scheduled continuation to an exact Codex session; preview by default.

Run this from an ordinary local terminal, outside an agent tool invocation.
No model runs while this process waits. No hardware is accessed by this script.
"""
import argparse
from datetime import datetime, timedelta, timezone
import shutil
import subprocess
import time
from uuid import UUID


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ValueError("include a timezone offset, e.g. +01:00")
        return result.astimezone(timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def session_id(value):
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use the exact session UUID") from exc


def message(stop_by):
    return (
        "Continue task: resume the authorized Orion AFX captures. "
        f"Device availability ends at {stop_by.isoformat()}. "
        "Before any device action, check the current time, owner instructions, "
        "device/window/rack state and whether a previous capture is still running. "
        "Do not start a batch that cannot finish, verify and release the device "
        "before that deadline. Stop device work by the deadline, save the handoff "
        "and pause for the owner. Preserve existing capture safety guards; "
        "do not override a newer owner pause. This is the single overnight restart."
    )


def dispatch(at, stop_by, command, now=None, sleep=None, run=None):
    """Wait using wall time, then attempt delivery once; never retry a send."""
    now = now or (lambda: datetime.now(timezone.utc))
    sleep = sleep or time.sleep
    run = run or subprocess.run
    while True:
        current = now()
        if current >= stop_by or current > at + timedelta(minutes=10):
            raise RuntimeError("delivery window expired; nothing sent")
        remaining = (at - current).total_seconds()
        if remaining <= 0:
            break
        sleep(min(remaining, 30))
    return run(command, check=False, timeout=60).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread", required=True, type=session_id)
    parser.add_argument("--at", required=True, type=timestamp,
                        help="send time, ISO date/time with explicit UTC offset")
    parser.add_argument("--stop-by", required=True, type=timestamp,
                        help="device deadline included in the agent instruction")
    parser.add_argument("--arm", action="store_true",
                        help="wait and actually send; otherwise preview only")
    args = parser.parse_args(argv)
    current = datetime.now(timezone.utc)
    if not current < args.at < args.stop_by:
        parser.error("require now < send time < stop-by time")
    codex = shutil.which("codex")
    if not codex:
        parser.error("codex must be installed and on PATH")
    command = [codex, "queue", "--thread", args.thread,
               "--message", message(args.stop_by)]
    print(f"Session: {args.thread}\nSend: {args.at.isoformat()}\n"
          f"Device deadline (agent instruction): {args.stop_by.isoformat()}\n"
          f"Message: {command[-1]}", flush=True)
    if not args.arm:
        print("Preview only; no timer or message created. Add --arm to run.")
        return 0
    print("Armed in this process; Ctrl+C or terminate this PID to cancel.", flush=True)
    try:
        result = dispatch(args.at, args.stop_by, command)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Stopped: {exc}. No retry; inspect the session before resending.")
        return 1
    print(f"Queue command exited {result}; delivery does not prove task resumed.")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
