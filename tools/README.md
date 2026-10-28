# Development tools

These are intentionally standalone scripts: most are used while analysing a
capture or talking to a live device, so stable, short paths are safer than a
package-style reorganisation. This index is the entry point for choosing the
right tool.

## Choose a tool

| Need | Tool | Writes to hardware? |
| --- | --- | --- |
| Run the complete offline regression suite | `python3 tools/offline_checks.py` | No |
| Export the split AFX catalog as one JSON document | `python3 tools/export_afx_catalog.py --catalog profiles/afx_effects.json --output /tmp/afx-catalog.json` | No |
| Check browser rendering, links, and AFX popup lifecycle | `node tools/test_webui_meters.cjs`, `node tools/test_webui_mixer_links.cjs`, `node tools/test_webui_input_links.cjs`, and `node tools/test_webui_afx.cjs` | No |
| Verify the connected device through bounded readbacks | `python3 tools/selftest.py` | No by default |
| Run restore-safe hardware round trips | `python3 tools/selftest.py --write` | Yes; restores state |
| Check or experimentally probe Surround EQ | `python3 tools/surround_eq_selftest.py` | Read-only by default |
| Check or round-trip Surround format/control state | `python3 tools/surround_format_selftest.py` | Read-only by default |
| Check or round-trip Surround EQ PRE/POST | `python3 tools/surround_eq_position_selftest.py` | Read-only by default |
| Map live meter sources | `python3 tools/meter_selftest.py` | Yes; controlled, restores state |
| Capture and restore one link transition | `python3 tools/link_transition_capture.py --family spdif --pair 0 --from-state off --to-state on --write --confirm-transition` | Yes; explicit state restore |
| Compare two extracted command frames | `python3 tools/capture_diff.py before.hex after.hex` | No |
| Analyse a Windows TSV capture | `python3 tools/scan_capture.py all_reports.tsv` | No |
| Analyse a native-macOS capture | `python3 tools/scan_macos_capture.py CAP.pcapng` | No |
| Analyse Orion AFX chain/parameter traffic | `python3 tools/scan_afx_capture.py CAP.pcapng --output /tmp/afx-analysis.json` | No |
| Inspect decoded readback traffic in a capture | `python3 tools/scan_readback.py CAP.pcapng` | No |
| Inspect HID capabilities | `python3 tools/hid_probe.py --profile profiles/orion_studio_sc.json` | No |
| Enumerate profile-bounded device readbacks | `python3 tools/readback_enum.py --profile profiles/orion_studio_sc.json` | Yes; bounded queries |
| Investigate control-transfer/readback behavior | `python3 tools/ct_probe.py` or `python3 tools/readback_probe.py` | Potentially; read the script first |

## One overnight Codex continuation

`schedule_codex_continue.py` waits outside the agent and sends one message to
an exact session using the installed `codex queue` command. It does not launch
a second capture worker or access hardware itself. Choose the send time manually
from that night's `/status` reset estimate, with a small margin after reset;
there is no fixed reset schedule. Use the session UUID shown by Codex
(`CODEX_THREAD_ID` is also provided inside its shell tools).

Preview first, replacing the UUID and dates with your actual session and times:

```sh
python3 tools/schedule_codex_continue.py --thread SESSION_UUID \
  --at '2030-01-01T01:30:00+01:00' --stop-by '2030-01-01T07:00:00+01:00'
```

Run the same command with `--arm` in a separate ordinary terminal to wait and
send. To survive closing that terminal, use `nohup` and keep the printed PID:

```sh
nohup python3 tools/schedule_codex_continue.py --thread SESSION_UUID \
  --at '2030-01-01T01:30:00+01:00' --stop-by '2030-01-01T07:00:00+01:00' \
  --arm > /tmp/afx-overnight-continue.log 2>&1 &
echo $!
```

Cancel with Ctrl+C in the foreground or `kill PID` for the background process.
Arm only one copy. The waiting process must run outside an agent tool call so
it remains independent of the agent's usage allowance. Keep the computer awake,
Codex session and required VM/USB-redirection viewer running. Explicit UTC
offsets avoid ambiguity across daylight-saving changes.

This sends once without retries. If the machine wakes more than ten minutes
after the selected time, or after the device deadline, it skips delivery. A
successful queue exit is not proof the agent resumed; live delivery after a
usage reset remains to be tested. The stop time is an instruction to the agent,
**not an enforced hardware cutoff**. A suspended/blocked agent cannot guarantee
device release at that time. The continuation requests fresh state checks,
bounded batches that finish before the deadline, a saved handoff and a pause;
it does not override a newer owner pause. No job is armed by installing this
script. See the [official queue documentation](https://learn.chatgpt.com/docs/developer-commands#codex-queue).

## Safety classes

- `offline_checks.py` is the documented all-in-one offline suite. It runs the
  Python profile/protocol tests plus the WebUI meter, mixer-link, input-link,
  AFX lifecycle/selection/reordering/live-write checks, and static source checks. Use `--python-only` only where Node.js is unavailable.
- `test_*` and `webui_sources.cjs` are offline regressions.
- `capture_diff.py` and `scan_*.py` analyse local captures only.
- `selftest.py` and the `surround_*_selftest.py` scripts are live-device tools.
  Their write paths are opt-in and must restore the state they modify.
- `link_transition_capture.py` compares all five safe Orion link tables
  around one explicit transition and restores the declared starting flag.
  Input spaces/readback selectors are 0=Preamp (six pairs), 1=ADAT (eight
  pairs), and 2=S/PDIF (one pair), verified on 2026-09-30. Orion also supports
  `--family afx`: space 4, pair indices 0–15, matching `0x0b:4` bytes 0–15,
  independently verified on 2026-10-01. Bytes 16–31 remain unmapped. The
  tool uses the explicit Orion rack contract and does not assign any effects.
  Stop the WebUI/Launcher before using it so only one controller owns HID.
  All writes require
  explicit transition confirmation. Legacy profiles with shared Preamp/ADAT
  selectors additionally require `--confirm-shared-space`.

- `hid_probe.py`, `readback_enum.py`, `readback_probe.py`, and `ct_probe.py`
  are protocol-discovery tools. Never use a force/unsafe option for an
  exploratory sweep: an out-of-range outer readback index can BusFault the
  device.

Local tool output is ignored because it can contain device-specific data.
Capture inputs are ignored too; keep only sanitized findings in the tracked
profile and protocol documentation.

## Orion AFX evidence and regression checks

AFX plugin definitions live in `profiles/afx/<effect_id>.json`, listed by the
ordered `profiles/afx_effects.json` manifest. Python tools read them through
`antelope.catalog.load_catalog(path)`. The exporter above writes resolved
inline JSON for external tools; omit `--output` for stdout or `--catalog` to
select the repository catalog. Generated exports
are not authored catalog sources. Archived capture helpers that parsed or
text-spliced the old inline catalog require migration before reuse; see the
[editing workflow](../docs/orion-afx-workflow.md#editing-captured-plugin-knowledge).

The 2026-10-01 device trials verified all 16 AFX link transitions against the
five bounded link tables, then verified Memory Cat load/remove on the 30
unlinked channels AFX 3–32. Each original chain was restored exactly;
reordering additionally verified on AFX 3 and 32. AFX 1–2 and their existing
link/effects were preserved. Earlier owner testing covers AFX 1; AFX 2 mono
writes were not exercised while linked. A separate parameter test sent
Level 100→99 and resent the original complete block, without identifying a
parameter readback or independently verifying the restored parameter value.
The results do not authorize queries beyond current profile bounds.

The raw local evidence remains ignored:

- `captures/afx-link-readback-transitions-20261001.json`
- `captures/afx-channel-slot-roundtrips-20261001.json`
- `captures/afx-parameter-readback-selftest-20261001.json`

The committed findings are in [PROTOCOL.md §12a](../PROTOCOL.md#12a-afx-real-time-chain-and-parameter-controls).
The temporary channel/parameter trial scripts are not installed public tools;
do not confuse the offline `test_*` suite with an automatic hardware trial.
`tools/test_afx_test.py` covers selected-channel bounds, instance allocation,
fresh read/verify behavior, link readbacks and verification failures;
`tools/test_afx_catalog.py` covers supported types and presentation groups;
`tools/test_webui_afx.cjs` covers left selectors, both drag surfaces, channel
payloads, linked-pair guards, reconnect and live-write coalescing. These tests
never open a HID node.

`scan_afx_capture.py` also reports tagged effect-state queries separately from
classic category queries, and decodes captured Memory Cat replies with the
Orion JSON layout. `memorycat_readbacks` includes parameters, processing state
and the most recent matching request's instance/frame; the reply itself does
not echo an instance. This is offline capture correlation, not permission to
query an unobserved instance. The two later owner captures establish retained
parameters after Launcher restart and a newly loaded active effect after
Bypass All, superseding the earlier self-test's missing-readback result.

AFX regressions also cover linked left/right chain loads, replacement, removal
and reorder, distinct allocation, preflight conflicts/resource exhaustion,
and partner verification failure without automatic repair. No live paired-chain
mutation was performed in this implementation pass.

## Linux AFX state recordings

`afx_state_capture.py` records changed state through the running WebUI actor
with read-only GETs. It logs selected/linked-partner chains, flags and captured
Memory Cat parameter/bypass readbacks, without identity, account data, settings
writes or a second HID controller. Use a new local output path:

```sh
python3 tools/afx_state_capture.py --channel 1 --seconds 60 --interval 1 \
  --output captures/memorycat-linked-readbacks.jsonl
```

Channels are1-based; current parameter coverage is Memory Cat instances0–2.
Recording stops if the device connection changes. See the
[Orion AFX workflow](../docs/orion-afx-workflow.md) for the effect rollout plan,
existing-capture analysis, optional Linux-host usbmon capture and vendor-side
endpoint-gesture fallback. This records our readback/control tests; an unknown
vendor control still needs independent command/label evidence.
