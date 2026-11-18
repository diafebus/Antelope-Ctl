# Gazelle AFX capture handoff plan

Reviewed 2026-10-27. This is a proposed integration plan, not an enabled
cross-device capture runner. Hardware capture remains paused. The colleague's
device model, vendor GUI and host/VM arrangement still need to be identified.
The three-effect definition/panel refresh described below is now committed on
Gazelle proposal branches and published in the existing PRs.

The method is transferable: discover the vendor GUI, review bounded actions,
record USB traffic passively, correlate each action with observed reports,
checkpoint accepted phases and publish model-scoped findings. The current
scripts and JSON files need adaptation before a colleague can use this as a
Gazelle workflow.

## Revisions and existing collaboration

The comparison used fetched upstream refs, not only the older local clones:

| Repository / ref | Revision | Relevant state |
| --- | --- | --- |
| gazelle-device-profiles, main | `ab5a5315af8b82dc148430338d3d7bda0db3fc94` | Connector/device-profile schemas; no shared `effects/` tree |
| gazelle-docs, main | `d249bcbc06abff3616a9858b14a6efa5095b1e7c` | Project rules, hazards, protocol knowledge and product specification |
| gazelle, main | `11299c2` | Current published product snapshot; effect commands come from device profiles |
| gazelle, diafebus/linux-hidraw | `f84cffac2af119161419aff685622265a45a3e62` | Existing local working branch, updated by fast-forward |
| gazelle-device-profiles, diafebus/memory-cat-shared-definition | `995b6e9f10d2200a298e81626940f549f20343c7` | Proposed shared definitions/schema for Memory Cat, V12 and BBD |
| gazelle, diafebus/shared-modulation-panels | `a7b1708` | Proposed separate shared panel modules |

On the review date, [profiles PR21](https://github.com/Gazelle-ctl/gazelle-device-profiles/pull/21)
and [panel PR6](https://github.com/Gazelle-ctl/gazelle/pull/6) are open. Their
definitions are a useful starting point, not a merged Gazelle standard.
The local Gazelle application checkout stays on its existing Linux branch;
`origin/main` was inspected separately. Untracked Rust build output was retained.

The owner then requested the three definitions be brought up to current
knowledge. Isolated worktrees on the existing proposal branches merged current
main and produced these published commits:

| Branch | Published commit | Result |
| --- | --- | --- |
| profiles: diafebus/memory-cat-shared-definition | `fd4eecf` | Corrected processing observations, BBD stereo map, all twelve Voices values, display inventories and captured fixtures |
| app: diafebus/shared-modulation-panels | `c04c03c` | Updated discrete controls, complete-map editing gates, current footer/keyboard integration and browser regressions |

The original checkouts remain on their prior branches. PR21 and PR6 now contain
these commits and updated descriptions. Both are open and mergeable. Profiles
CI passed for `fd4eecf`; the app engine/panel CI was running for `c04c03c` at
publication verification. Neither PR was merged.

## Format compatibility

Our [AFX catalog](../profiles/afx_effects.json) has a documented project format,
`catalog_schema.id = antelope-afx-effect-catalog`, version 1. Its current storage
is an ordered manifest plus per-plugin files; `antelope.catalog.load_catalog`
resolves the same logical `effects` array, and `tools/export_afx_catalog.py` can
export it as flat JSON. Its contract is
described in [the profile schema guide](profile-schema.md#afx-and-the-shared-effect-catalog)
and checked by the existing catalog tests. It is not Gazelle's JSON schema.
"Shared catalog" here means shared between this project's device profiles.

| Topic | antelope-ctl | Gazelle main / proposed PR21 | Required handoff |
| --- | --- | --- | --- |
| Packaging | Ordered manifest plus per-plugin files; resolved/exported catalog has an `effects` array | Main has device `params` and `plugins`; PR21 adds one file per effect | Explicit conversion, not copying the catalog into Gazelle |
| Effect IDs | `memory_brigade`, `turboensembler`, `bbdchorus` | PR21 uses `antelope/`-qualified versions of these IDs | Preserve compatibility IDs with an explicit namespace map |
| Shared controls | Array keyed by each entry's `id` | PR21 object keyed by control ID | Convert structure; retain labels and sources |
| Device knowledge | `implementations[]`, selected by profile filename | PR21 named `encodings` plus profile `effects` bindings | Separate shared descriptions, encoding candidates and model-local verification |
| Raw observations | `control_encodings`, `parameter_observation`, `bypass_observation` | PR21 encoding `controls`, `parameters`, `bypass`, `state_readback` | Map semantics explicitly; preserve unknowns and evidence |
| Confirmation | `capture-observed`, `capture-confirmed`, runtime contracts and read-only flags | Gazelle writable `confirmed` requires model-local change/readback/restore | Never translate a capture observation directly into a confirmed writer |
| Control kinds | Continuous, integer, boolean, enum, or unknown; model overrides | PR21 shared-control kind accepts continuous or enum | Extend the contract or define an explicit lossless representation |
| Detailed fields | Width/signedness, discrete maps, dependencies, endpoint candidates, display inventories | PR21 encoded control fields are limited to offset, readback offset, range, values, label and evidence | Agree schema extensions before moving the wider captured set |

The proposed shared family encoding records `observed_on`. Referencing it from
another model does not verify that model's transport, IDs, fields, safe query
tuples, ranges or writes. Resource counts and menu presence do not establish
license ownership.

## Three-effect reconciliation

The fetched proposal predates later captures. Its three-effect differences
are corrected in the published refresh; no original scan was repeated:

| Finding | Current Orion evidence | Gazelle published refresh | Remaining work |
| --- | --- | --- | --- |
| Processing addressing | Catalog model-local observations for Memory Cat, V12 and BBD use instance byte17, type byte18, state byte19 | Corrected all three definitions and prose; fixtures include nonzero instances | Review candidate observations; runtime bypass stays unconfirmed |
| BBD stereo selector | Byte25: 0 Basic, 1 Wide, 2 Split, 3 Cross; captured selector returns to Basic | Mapped byte25; bytes26/27 stay opaque; panel requires caller's model map | Parameter readback and runtime write verification |
| V12 Voices | Byte21: twelve individually witnessed integer positions, with matching readout images | Enum definition, twelve captured samples and rotary panel; incomplete maps cannot enable editing | Model-local reader/write contract |
| Other completed effects | Current [workflow coverage](orion-afx-workflow.md) records 22 visible editable-control passes | PR21 defines three effects | Add effects incrementally after agreeing the extended schema |
| Meters and tuner | [Display inventory](orion-afx-displays.md) records widgets; tuner screen decoding is owner-deferred | Three-effect native display inventories added with readers disabled | Signal telemetry contracts and deferred tuner work |

Processing witnesses include Memory Cat first/return frames3637/837 in the
2026-10-25 processing trial, V12 frames3461/713, and BBD resume
frames7063/7067 and7999/8007. The catalog records the source captures and
linked-instance witnesses that distinguish instance from state. Static GUI
restoration is recorded separately from device readback. Full details are in
[modulation findings](orion-afx-modulation.md) and [PROTOCOL.md](../PROTOCOL.md).

Antelope Launcher initialization readback is already established. Reuse the
existing startup traces to map remaining fields; no redundant initialization
capture or speculative getter sweep is part of this handoff.

## Delivery sequence

1. **Agree the target station and scope.** Record the colleague's exact model,
   firmware, host, vendor GUI process/panels and capture backend. Create a
   station configuration for VM/share locations and device selection. Keep
   station paths, serials and credentials outside public profiles. If the
   target is not Orion, its hardware work is a separate explicit scope.
2. **Reconcile shared protocol facts.** Update the owning Gazelle protocol
   documents and proposed effect definitions from the later evidence above.
   Keep confirmation model-local. Validate PR21 against current main before
   extending it; do not overwrite newer Discrete measurements from its older
   base. Coordinate review through the existing PRs rather than duplicating
   definitions in another location.
   The three-effect definitions and panel descriptions are now refreshed
   and published in the existing PRs; other effects and the broader protocol
   handoff remain pending.
3. **Agree the data contract.** Extend the proposed effect schema for finite
   rotary values, width/signedness, physical-scale unknowns, dependencies,
   processing observations and display-only widgets. Separate capture evidence
   and preview values from runtime contracts. Specify how each existing field
   is preserved or deliberately omitted. Unknown or unsupported input must be
   reported rather than silently dropped. Confirm that Gazelle's engine
   actually consumes the agreed definitions; schema acceptance alone does not
   make a panel loadable.
4. **Make the capture method reproducible.** Define a documented job/handshake
   contract for GUI inventory, reviewed plan, device identity, action windows,
   accepted phases, failure state and reviewed remaining work. Supply sample
   sanitized evidence and expected outcomes. Configure process/panel identity,
   transport/framing and per-model selectors separately. Reacquire runtime GUI
   IDs and USB addresses after restart. Replace session-local helpers and
   hardcoded paths before calling the kit portable.
5. **Run offline acceptance, then one supervised pilot.** Test interrupted
   knob/toggle trials, discrete-position maps, stale GUI IDs, reconnects,
   malformed handshakes, preserved bytes, no fresh OUT, device mismatch and
   late/missing ACKs. On the colleague's authorized station, use one available
   effect on an agreed channel with bounded actions and an explicit cleanup
   plan. Require action-labelled OUT evidence, no unexpected edits and exact
   ownership of the trial before enabling a longer run. A visual control pass
   remains distinct from a confirmed runtime write contract.
6. **Enable an unattended campaign only after acceptance.** Give it a finite
   allow-list and device-availability deadline, single coordinator lock,
   persistent checkpoints, explicit pending coverage and a resumable handoff.
   Reconcile state after a timeout; never replay an uncertain GUI command.
   Stop device actions on a verification failure and preserve the evidence.
   The external one-shot continuation is optional and separate from capture
   recovery. Its current morning deadline is only an agent instruction; an
   independently enforced runner deadline/cleanup contract is still needed
   before claiming guaranteed morning device release.

## Reuse boundaries and missing packaging

Gazelle's [project instructions](https://github.com/Gazelle-ctl/gazelle-docs/blob/d249bcbc06abff3616a9858b14a6efa5095b1e7c/AGENTS.md)
state: "do not copy code out of `diafebus/Antelope-Ctl` into
`Gazelle-ctl/gazelle`." This plan follows that contribution rule: share
observable protocol facts and a behavioral specification, then author Gazelle
consumers independently. Our GPL scripts can remain separately maintained in
this repository; that is not a claim that Gazelle has accepted them as a
dependency or that another device is supported by them.

The committed starting kit is [tools/windows](../tools/windows/README.md),
[afx_vm_pilot.py](../tools/afx_vm_pilot.py), discovery, budgets, progress and
offline analysis. It currently selects Orion-specific profile/catalog entries,
vendor process names and report layouts. It is not yet a generic Gazelle runner.

The larger unattended campaign also used local session helpers for the guest
bridge, keep-awake lifecycle, exact-menu loading/removal, reviewed switch and
detent trials, display inventories and finalization. Those are not all part of
the committed kit. They need an inventory, configuration interface, provenance
review and tests before another person can reproduce the whole campaign.
Publishing only the one-shot continuation script would not transfer that work.

The capture controller remains the vendor GUI while the host records USB
passively. A Gazelle daemon or probe must not open a competing HID handle on
the same device. Native Gazelle write/read/restore testing is a later,
separately authorized mode after releasing the vendor controller, using that
model's confirmed allow-list and existing device actor.

## Completion criteria

- The colleague can install and validate the documented kit on a fresh station
  without copying private session files or guessing paths/GUI coordinates.
- Shared definitions and model bindings pass Gazelle's schema, semantic and
  publication gates; sanitized fixtures retain source hashes/frame references.
- Discrete controls retain every witnessed position; endpoint candidates are
  not presented as measured physical scales or defaults.
- Candidate encodings remain unable to enable writes or widen query bounds.
- Interrupted work resumes only after fresh state/identity review and cannot
  create duplicate workers or silently claim a control was restored.
- A supervised target-station pilot passes before any unattended run; the
  device deadline and release behavior are tested independently of agent quota.

The refresh passed 87 focused profile tests, 14 compatibility tests,
schema/structural/publication checks, 1,010 Rust workspace tests, live-profile
loading with the updated files, public panel-asset tests, the shared-panel
browser probe, 30 simulated panel interactions and four carrier tests. The
reviewed partial-map regression keeps Voices disabled until all twelve model
values are supplied, and rejects unmapped destination values separately.

Six static Node gates passed. The separate meter-names gate cannot run from
this public checkout because its private `captures/d8p` input is absent.
Rustfmt, Clippy and the Windows target are absent from this host, so the full
engine gate is not claimed. No raw device/controller was opened. Hardware
capture remains paused and no scheduler was armed. The owner requested
publication; both PR branches were pushed after the tracked-file publication
gates passed (31 profile-repository files and 208 application-repository files).
