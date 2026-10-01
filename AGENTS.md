# Project instructions

## Purpose and scope

`antelope-ctl` documents the Antelope USB-HID control protocol and provides a
profile-driven Python CLI and WebUI for Linux. The JSON profiles are the primary
reusable result: another client should be able to implement device controls from
their documented mappings and evidence. Keep the CLI/protocol core stdlib-only.

- Current hardware work is **Orion Studio Synergy Core only**. Other devices are
  unavailable to this owner. Do not modify their profiles or transfer Orion
  findings to them without an explicit scope change and device-specific evidence.
- Work in this repository first. Work in Gazelle or `gazelle-device-profiles`
  only when requested, following that repository's own contribution guidelines.
- Follow [SCOPE.md](SCOPE.md). Use owned-device USB observations and facts from
  public vendor documentation. Do not derive protocol data from vendor binaries,
  firmware, disassembly, login-gated material, or licensing/activation traffic.
  Device-side AFX controls are distinct from Native/Cosmos plugins. Keep loading
  within the owner-requested, captured Orion pilot; do not implement plugin DSP.
- A possible kernel driver is a later option, after protocol and hardware
  validation. Do not start kernel work as part of ordinary profile/UI tasks.

## Start and resume

1. Check `git status --short` and the current branch; preserve existing work.
2. If present, read the ignored local `SUMMARY.md`, then `CLAUDE.md` and
   `AUDIT.md`. `AUDIT.md` is the sole live completion queue. These files are
   local handoffs, not requirements for a fresh clone. Consult archives only
   when historical evidence is needed.
3. Read the relevant sections of [README.md](README.md),
   [PROTOCOL.md](PROTOCOL.md), [the Orion profile](profiles/orion_studio_sc.json)
   and [the profile schema](docs/profile-schema.md). For AFX, also use
   [the workflow](docs/orion-afx-workflow.md) and the shared catalog
   [profiles/afx_effects.json](profiles/afx_effects.json).
4. Use the local `captures/CAPTURE_INDEX.md` when available before rescanning
   captures. Keep reads targeted; do not load every archive or capture by default.

User instructions and existing session authorization take precedence over local
guidance. Complete authorized work without asking for the same permission again.
Use concise progress updates and state unresolved evidence plainly. Do not spawn
subagents unless requested.

## Evidence and profile design

- When sources conflict, prefer observable device behavior, then captures with
  direction/action order, then capture-backed profiles, then code/tests/prose.
  Separate captured facts, owner confirmations, bounded candidates and unknowns.
  Record source filenames, frame references, offsets and confirmation status.
- Filter Orion captures to VID `0x23e5`, PID `0xa221`, the HID interface and
  control endpoints `0x01` OUT / `0x82` IN. Reports are 320 bytes. Audio ISO
  traffic is separate. An inbound-only capture does not establish a write frame.
- Put device capacity, addressing, query bounds, write/read fields, ranges,
  encodings and runtime contracts in the device profile. AFX channels/slots
  belong there; effect definitions and descriptions belong in the shared catalog
  with model-specific implementations. Resource counters do not prove licenses.
- Make consumers use profile facts instead of duplicating mappings in UI code.
  Preserve unknown fields/bits and wire/API compatibility identifiers. Unknown
  controls remain unavailable; do not invent defaults, labels or scaling.
- Application-facing naming is **Gazelle Reverb**. Keep **AuraVerb** for original
  hardware/protocol evidence and preserve identifiers such as `auraverb`.

## Hardware access and state

- Never query a classic readback outer index beyond the enumerated category
  count. The firmware can BusFault and require a physical power cycle. Nested
  record counts are payload layouts, not permission to query more outer indices.
  Use profile bounds and `protocol.check_readback_index`; do not use `--force`
  or exploratory index/type sweeps.
- Tagged AFX instance queries use a distinct opcode/selector namespace. A
  captured tuple does not extend classic category bounds. Current Memory Cat
  state reads are limited to loaded instances0–2; consult the profile for the
  complete contract. Replies do not echo the instance: serialize transactions
  through the existing device actor, and stop these reads after a timeout or
  invalid reply until reconnect. Do not open a competing HID controller.
- Device writes need owner authorization and a measured frame/range. Existing
  authorization for bounded, reversible trials persists within that scope.
  Read the current state before a trial, verify the result, and restore only
  that trial's changes. Stop on failed verification; avoid blind repair/reset
  writes. Never restore an old snapshot over newer owner changes.
- Opening, refreshing and reconnecting the UI must read device state without
  applying presets or replaying parameter/bypass values. Scope caches to the
  current transport/session; stale or absent state is unknown.
- Preserve device-reported active/bypass state. New effects were observed active
  even after Bypass All; do not hardwire that result into the writer. Confirmed
  Launcher-restart retention does not prove power-cycle persistence.
- ADAT and S/PDIF link addressing/readbacks are confirmed and work across
  controller restarts with corrected writes. Do not revive superseded uncertainty
  from the original Launcher's incorrect selectors. Linking alone preserves
  existing racks; do not reproduce its unlink cleanup bug.

## WebUI and AFX

- Keep effect panels in separate modules; shared rack/state logic stays generic.
  Use an original design with static knob bodies/lighting and moving pointers,
  without redundant sliders. Knob edits send coalesced live changes using fresh
  settings and the existing failure/retry guards.
- Show one selected channel, its categorized slot selectors on the left and its
  rack on the right. Preserve drag/drop from both views, the compact chain link
  button, link markers and readback-based loaded-effect counts in channel menus.
- Use actual channel/instance readbacks for linked racks. Preserve different or
  missing partner effects; never load an effect as a side effect of turning a
  knob. Keep captured behavior distinct from candidate stereo mirroring.

## Verification and completion

- Run meaningful existing checks appropriate to the change. The hardware-free
  suite is `python3 tools/offline_checks.py` (Python + Node); use `--python-only`
  only when reporting that the WebUI checks were skipped. Device self-tests are
  separate and require an authorized, bounded write/verify/restore plan.
- Keep profiles, `PROTOCOL.md`, schema/startup/AFX docs and affected CLI/WebUI
  documentation synchronized. Update local handoffs and capture provenance when
  present. Keep current task lists out of this file and public references.
- Run `git diff --check` and inspect the final diff. Keep captures, serials,
  account data, tokens and generated diagnostic dumps out of tracked files.
  Do not force-add ignored local handoffs or captures.
- Stage files explicitly and preserve repository-local Git identity. Commit
  meaningful completed work; push or create PRs when requested, including when
  that authorization already exists in the session. Never force-push or discard
  unrelated user work. Name the actual assistant/model in the commit coauthor
  trailer rather than copying another session's identity.
- Report what changed, checks performed, remaining hardware uncertainty, and
  commit/push or PR status. Do not claim audible verification from readback alone.
