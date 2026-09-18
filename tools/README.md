# Development tools

These are intentionally standalone scripts: most are used while analysing a
capture or talking to a live device, so stable, short paths are safer than a
package-style reorganisation. This index is the entry point for choosing the
right tool.

## Choose a tool

| Need | Tool | Writes to hardware? |
| --- | --- | --- |
| Run the ordinary offline regression suite | `python3 -m unittest tools.test_profile_labels tools.test_readback_records tools.test_orion_startup tools.test_surround tools.test_meter_sources` | No |
| Check browser rendering and mixer-link interaction | `node tools/test_webui_meters.cjs` and `node tools/test_webui_mixer_links.cjs` | No |
| Verify the connected device through bounded readbacks | `python3 tools/selftest.py` | No by default |
| Run restore-safe hardware round trips | `python3 tools/selftest.py --write` | Yes; restores state |
| Check or experimentally probe Surround EQ | `python3 tools/surround_eq_selftest.py` | Read-only by default |
| Check or round-trip Surround format/control state | `python3 tools/surround_format_selftest.py` | Read-only by default |
| Check or round-trip Surround EQ PRE/POST | `python3 tools/surround_eq_position_selftest.py` | Read-only by default |
| Map live meter sources | `python3 tools/meter_selftest.py` | Yes; controlled, restores state |
| Compare two extracted command frames | `python3 tools/capture_diff.py before.hex after.hex` | No |
| Analyse a Windows TSV capture | `python3 tools/scan_capture.py all_reports.tsv` | No |
| Analyse a native-macOS capture | `python3 tools/scan_macos_capture.py CAP.pcapng` | No |
| Inspect decoded readback traffic in a capture | `python3 tools/scan_readback.py CAP.pcapng` | No |
| Inspect HID capabilities | `python3 tools/hid_probe.py --profile profiles/orion_studio_sc.json` | No |
| Enumerate profile-bounded device readbacks | `python3 tools/readback_enum.py --profile profiles/orion_studio_sc.json` | Yes; bounded queries |
| Investigate control-transfer/readback behavior | `python3 tools/ct_probe.py` or `python3 tools/readback_probe.py` | Potentially; read the script first |

## Safety classes

- `test_*` and `webui_sources.cjs` are offline regressions.
- `capture_diff.py` and `scan_*.py` analyse local captures only.
- `selftest.py` and the `surround_*_selftest.py` scripts are live-device tools.
  Their write paths are opt-in and must restore the state they modify.
- `hid_probe.py`, `readback_enum.py`, `readback_probe.py`, and `ct_probe.py`
  are protocol-discovery tools. Never use a force/unsafe option for an
  exploratory sweep: an out-of-range outer readback index can BusFault the
  device.

Local tool output is ignored because it can contain device-specific data.
Capture inputs are ignored too; keep only sanitized findings in the tracked
profile and protocol documentation.
