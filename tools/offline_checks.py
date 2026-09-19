#!/usr/bin/env python3
"""Run the complete hardware-free project regression suite.

This is the one command documented for a pre-commit or audit pass.  It never
opens a HID node, reads a capture, or uses a local device profile selected from
the environment.  Keep device-facing self-tests separate: their safety and
restore contracts need an explicit human decision.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTHON_MODULES = (
    "tools.test_profile_labels",
    "tools.test_readback_records",
    "tools.test_orion_startup",
    "tools.test_orion_profile_audit",
    "tools.test_surround",
    "tools.test_meter_sources",
    "tools.test_offline_checks",
)
NODE_CHECKS = (
    "tools/test_webui_meters.cjs",
    "tools/test_webui_mixer_links.cjs",
    "tools/webui_sources.cjs",
)


def checks(include_node=True):
    """Return labelled commands without running them.

    Kept as data so the test can ensure new safety checks join this runner
    rather than becoming another command somebody has to remember.
    """
    checks_to_run = [("Python profile and protocol checks", [
        sys.executable, "-m", "unittest", *PYTHON_MODULES,
    ])]
    if include_node:
        checks_to_run.extend((Path(path).name, ["node", path]) for path in NODE_CHECKS)
    return checks_to_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-only", action="store_true",
                        help="skip browser-source checks that need Node.js")
    parser.add_argument("--list", action="store_true",
                        help="print the checks without running them")
    args = parser.parse_args(argv)

    selected = checks(include_node=not args.python_only)
    if args.list:
        for label, command in selected:
            print(f"{label}: {' '.join(command)}")
        return 0
    if not args.python_only and shutil.which("node") is None:
        print("node is required for the WebUI checks; use --python-only to skip them",
              file=sys.stderr)
        return 2

    for label, command in selected:
        print(f"\n== {label} ==", flush=True)
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode:
            print(f"{label} failed with exit status {completed.returncode}", file=sys.stderr)
            return completed.returncode
    print("\nAll offline checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
