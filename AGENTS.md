# Project instructions

## Purpose and scope

`antelope-ctl` documents Antelope USB-HID controls and provides a profile-driven
Python CLI and WebUI for Linux. JSON profiles are the primary reusable device
knowledge; keep the CLI/protocol core stdlib-only.

Current hardware work is **Orion Studio Synergy Core only**. Other devices need
their own evidence and an explicit scope change. Work in this repository first;
follow Gazelle's guidelines when work there is requested. [SCOPE.md](SCOPE.md)
defines the research sources, contribution boundaries and captured AFX pilot.
Kernel work remains a later option after protocol/hardware validation.

## Start and resume

1. Check `git status --short` and the branch; preserve existing user work.
2. If available, read `SUMMARY.md` for the latest handoff and `AUDIT.md` for open
   Orion tasks. Both are ignored local files, optional on a fresh clone.
3. Read only relevant sections of [README.md](README.md),
   [PROTOCOL.md](PROTOCOL.md), [the Orion profile](profiles/orion_studio_sc.json)
   and [the schema](docs/profile-schema.md). For AFX use
   [the workflow](docs/orion-afx-workflow.md) and [the catalog](profiles/afx_effects.json).
   Use local `captures/CAPTURE_INDEX.md` before rescanning raw captures.

User instructions and existing session authorization take precedence. Finish
already-authorized work without asking for the same permission again. Give
concise progress updates; spawn subagents only when requested.

## Evidence and implementation

- Resolve disagreements using observable device behavior, then directed/action-
  labelled captures, capture-backed profiles, and finally code/tests/prose.
  Distinguish captured facts, owner confirmations, candidates and unknowns;
  record source frames/offsets and confirmation status.
- Get report sizes, endpoints, addressing, ranges and query limits from the
  active profile. Separate HID controls from audio ISO traffic; an inbound-only
  capture does not establish a write command.
- Store capacity and wire/runtime contracts in device profiles; store shared
  effect definitions with model-specific encodings in the AFX catalog. Resource
  counts do not establish license ownership. Consumers use these mappings;
  preserve unknown fields/bits and compatibility identifiers.
- UI/software naming is **Gazelle Reverb**; **AuraVerb** is the original
  hardware/protocol name. Keep identifiers such as `auraverb` compatible.

## Device transactions

- Enforce classic query bounds with `protocol.check_readback_index`. Out-of-range
  queries can BusFault the MCU and require a physical power cycle. Nested payload
  counts do not expand outer bounds; avoid `--force` and speculative index sweeps.
- Tagged AFX queries have separate profile-declared tuples and correlation rules.
  Use the existing single device actor. Stop uncorrelated instance reads after a
  timeout/invalid reply until reconnect; do not open a competing HID controller.
- Hardware writes require authorization and measured frames/ranges. Existing
  authorization for bounded reversible trials persists. Read current state,
  verify writes and restore only the trial's changes; stop on verification failure.
  Preserve newer owner changes and avoid blind reset/repair writes.
- Opening, refreshing and reconnecting read device state without replaying presets,
  parameters or bypass. Scope caches to the transport/session and report absent
  state as unknown. Retention claims specify the restart/power-cycle actually tested.

## WebUI

Keep effect panels in separate modules and shared rack/state logic generic.
Use an original design with static knob bodies/lighting, moving pointers and
no extra sliders; send coalesced live edits. Preserve the single-channel rack,
categorized left slot selectors, drag/drop from both views, compact chain link button, link markers
and readback-based loaded-effect counts. Linked edits use actual channel/instance
state and preserve missing/different partner effects. Distinguish verified device
readback from last-sent state and audible confirmation.

## Verify and finish

- Use meaningful existing checks for executable changes:
  `python3 tools/offline_checks.py` runs the hardware-free Python + Node suite.
  Device self-tests require an authorized bounded write/verify/restore plan.
  Documentation-only changes need reference checks and `git diff --check`.
- Update each fact in its owning document/profile, then affected consumers.
  Keep instructions here, latest session state in `SUMMARY.md`, open tasks in
  `AUDIT.md`, and research history in the ignored capture archive.
- Stage files explicitly. Keep captures, serials, account data, tokens and local
  handoffs out of Git. Preserve repository-local identity and unrelated changes;
  name the actual assistant/model in commit coauthor trailers.
- Commit meaningful completed work. Push/create PRs when requested, including
  existing session authorization. Report changes, verification, material remaining
  uncertainty and publication status.
