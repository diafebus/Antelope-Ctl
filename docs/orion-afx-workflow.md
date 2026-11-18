# Orion AFX capture and implementation workflow

The aim is to support every effect available to this Orion, using reusable JSON
knowledge. The catalog's 80 reference entries are a starting checklist, not an
Orion availability list. Current executable support is the five-effect captured
pilot in [SCOPE.md](../SCOPE.md#orion-captured-effect-pilot).

This document describes the capture method and completion criteria. The local,
ignored `AUDIT.md` holds the current work order.

The Windows kit now supports inventory-to-scan discovery through the same
`Run-AfxCapture.cmd` launch. The Linux passive coordinator's `--serve` mode
remains available for successive plugins. For effects with an observed Orion
type and an identified panel, the host generates bounded plans for uniquely
identified enabled Pot knobs and binary UI Automation checkboxes. The complete
plan Windows executes is checked before any host readiness/gesture gate.
Generic knob discovery records stable-block endpoint candidates without guessing
field offsets or parsing plugin-specific numeric labels. It distinguishes fresh
unchanged writes from suppressed writes after further completed sweeps; neither
establishes a physical endpoint, interpolation law or device readback. Controls
with unresolved identity, selectors, presets and disabled dependencies remain
listed as pending. Known measured plans retain their existing behavior. See
[the Windows instructions](../tools/windows/README.md) for operation and limits.

## Selector labels and completion

Capture each selector value together with its displayed label and what it means.
A complete numeric cycle with unknown mode names remains partial semantic
coverage, even when its visible-control capture pass is recorded. Match labels
against captured GUI indicators and available vendor documentation; audible
interpretations need separate confirmation. Do not invent user-facing names.
Master De-Esser's four Monitor/Out values remain semantically unidentified; the
panel marks that selector unverified and disables it pending this work.

## Editing captured plugin knowledge

The [catalog manifest](../profiles/afx_effects.json) owns shared provenance and
ordered file references. Record an effect's controls, model-local encodings,
source frames and confirmation limits in `profiles/afx/<effect_id>.json`.
For example, unfinished Audio / Baton findings belong in
[afx/audiobaton.json](../profiles/afx/audiobaton.json). Read only the relevant
plugin file when preparing a capture; use `antelope.catalog.load_catalog(path)`
when a consumer needs the resolved catalog. A new plugin needs a stable-ID
file and a manifest reference. The [schema guide](profile-schema.md#afx-and-the-shared-effect-catalog)
records loading and flat-export usage.

Private helpers archived from earlier capture sessions may search or splice
inline effect objects in `profiles/afx_effects.json`. Those helpers predate the
manifest and must be adapted before reuse: update the plugin file directly and
use the shared loader for catalog reads. Never serialize the assembled catalog
back over the manifest. Keep historical helper archives intact as evidence;
their archived runtime IDs, deadlines and bridge paths also require fresh
session checks. This refactor does not resume hardware work or authorize writes.

## Evidence already available

Initialization status readback is established. The owner reconfirmed the
Antelope Launcher initialization trigger on 2026-10-27, and startup captures
already exist. Reuse those captures for remaining AFX field decoding and reply
correlation. Per-effect readback flags below identify that remaining mapping
work; no new initialization capture is required.

| Effect | Orion type | Existing evidence |
| --- | --- | --- |
| Memory Cat Brigade | 73 | Eight fields, fresh parameter/processing reads for instances0–2, Launcher-restart retention, owner-confirmed switch labels |
| Instinct | 75 | All21knob endpoint candidates, three parameter switches, model/power round trips and60entry factory menu inventory captured; interpolation, preset encodings and runtime readback remain unverified |
| Master De-Esser | 27 | Load/chain and older linked writes; native capture now covers eight knob endpoint candidates, five filter choices, four monitoring states, processing-button round trip and preset inventory; runtime readback/scaling remain unverified |
| V12 Chorus | 70 | Ten knob endpoint candidates, Humanize, all12Voices counts and isolated power return captured; runtime/readback/scaling remain unverified |
| BBD Chorus | 78 | Four knob endpoint candidates, modulation/stereo choices and processing return captured; runtime/readback/scaling remain unverified |
| PowerGate | 39 | Six knob endpoint candidates and processing-lever GUI round trip captured; runtime/readback/scaling unverified |
| PowerEx | 51 | Six knob endpoint candidates and processing-switch GUI round trip captured; runtime/readback/scaling unverified |
| VEQ-1A | 6 | Five continuous knob endpoint candidates, all three rotary maps and processing-switch GUI round trip captured; runtime/readback/scaling unverified |
| VMEQ-5 | 5 | Three gain knob endpoint candidates, all 5/11/5 rotary maps and processing-switch GUI round trip captured; runtime/readback/scaling unverified |
| VEQ-HLF | 11 | Both eleven-position cut-off selectors and processing-switch GUI round trip captured; runtime/readback/units unverified |
| BA-31 | 48 | Both knob endpoint candidates and processing-switch GUI round trip captured; runtime/readback/scaling unverified |
| Gyratec IX | 43 | Both continuous endpoint candidates, all Phase/Low-Cut detents and processing round trip captured; runtime/readback/scaling unverified |
| VPA 76 | 44 | Warmth/Trim endpoint candidates, both filter detent maps and processing round trip captured; runtime/readback/scaling unverified |
| ATuner | 72 | Power captured; essential frequency/note/cents/needle screen reading explicitly deferred by owner |
| BAE-1023 | 24 | Eight rotary controls, all four frequency-selector maps, Phase and processing captured; scaling and per-field readback contracts unverified |
| NEU-PEV | 13 | Five rotary endpoint pairs, four complete stepped maps and processing captured; Output scaling and per-field readback contracts unverified |
| NEU-W492 | 15 | Nine rotary endpoint pairs, four band-switch returns, all three Low Cut positions and processing captured; scaling and per-field readback contracts unverified |
| NEU-W495 | 20 | Seven rotary endpoint pairs, six complete stepped maps, three Bell Quality positions and processing captured; scaling and per-field readback contracts unverified |
| VEQ-4K PINK | 16 | Thirteen rotary endpoint pairs, LMF ÷3/HMF ×3 mode/LED returns and processing captured; scaling and per-field readback contracts unverified |
| VEQ-4K ORANGE | 17 | Thirteen rotary endpoint pairs, LF/HF BELL mode/LED returns and processing captured; scaling and per-field readback contracts unverified |
| VEQ-4K BROWN | 19 | Thirteen rotary endpoint pairs, LF/HF BELL mode/LED returns and processing captured; scaling and per-field readback contracts unverified |
| VEQ-STU 900 | 23 | Eleven rotary endpoint pairs, four positional switch returns and processing captured; Low Cut raw0 OFF/High Cut raw100 OFF observed; scaling and per-field readback contracts unverified |
| VEQ-STU 169 | 22 | Five distinct rotary endpoint pairs, positional Filter return and processing captured; concentric MF controls preserve their partner fields; scales/detents and per-field readback contracts unverified |
| VEQ-STU 089 | 21 | Two rotary endpoint pairs, all five stepped slider maps (5/5/9/9/7 positions) and processing captured; physical scaling, per-field readback and signal telemetry unverified |
| MG4+ | 68 | Seven gain/output endpoint pairs, full eleven-position Sky Band map and processing captured; gain scales/interpolation, per-field readback and meter telemetry unverified |
| Audio / Baton | 69 | All ten raw0/100 endpoint pairs and rack BP processing return captured; OUT/IN indicator GUI states correlated. Direct front click/drag methods were negative. [EQ findings](orion-afx-eq.md#audio--baton--visible-control-pass-2026-10-28) preserve limits; runtime/readback/scaling unverified |
| VCA160 | 33 | Three raw endpoint pairs with printed endpoint associations, plus labelled POWER/rack BP GUI processing return. [Dynamics findings](orion-afx-power-dynamics.md#vca160--visible-control-pass-2026-10-28) retain limits; readback/interpolation/runtime unverified |
| ALT-436C | 35 | Four raw endpoint pairs with printed label associations, plus rack BP/front POWER indicator GUI return. [Dynamics findings](orion-afx-power-dynamics.md#alt-436c--visible-control-pass-2026-10-28) preserve signed Output candidates and unidentified byte24; runtime/readback/scaling unverified |
| Liverpool | 31 | Two continuous endpoint pairs, complete11/11/6 Attack/Recovery/Output selector maps with printed meanings, and Mains Power/BP/lamp GUI return. [Dynamics findings](orion-afx-power-dynamics.md#liverpool--visible-control-pass-2026-10-29) preserve limits; runtime/readback/timing unverified |
| Stay-Levin | 34 | Three endpoint pairs, five Recovery contacts and labelled Mode/Power GUI returns. Intermediate Recovery timing meanings remain unknown; [dynamics findings](orion-afx-power-dynamics.md#stay-levin--visible-control-pass-2026-11-03) preserve limits; runtime/readback unverified |
| SMT-100A | 36 | Two endpoint pairs, three-contact Attack/Release maps and Power GUI return. Centered timing meanings remain unknown; [dynamics findings](orion-afx-power-dynamics.md#smt-100a--visible-control-pass-2026-11-03) preserve limits; runtime/readback unverified |
| X903 | 29 | Three endpoint pairs with literal ratio endpoint −1:1 and IN-button/lamp GUI return. [Dynamics findings](orion-afx-power-dynamics.md#x903--visible-control-pass-2026-11-03) preserve limits; runtime/readback/scales unverified |
| FET-A78 | 37 | Four endpoint pairs, four individually labelled Ratio button states and Power GUI return. [Dynamics findings](orion-afx-power-dynamics.md#fet-a78--visible-control-pass-2026-11-03) preserve limits; combinations/runtime/readback/timing unverified |
| FET-A76 | 9 | Four endpoint pairs, four individually labelled Ratio button states and illuminated ON-button return. [Dynamics findings](orion-afx-power-dynamics.md#fet-a76--visible-control-pass-2026-11-03) preserve limits; combinations/runtime/readback/timing unverified |
| Impresser (partial) | 42 | Six endpoint pairs and eight literal Ratio labels captured. Detector intermediate labels, Harmonics, Stereo Link, UK Mode and processing remain pending. Full Ratio parameter body returns, but OPTO lamp differs; [partial findings](orion-afx-power-dynamics.md#impresser--partial-control-capture-2026-11-04) preserve the failed static check. This is not a completed plugin pass; runtime/readback/telemetry remain unverified |
| Comp-4K-Bus | 63 | Six continuous endpoint pairs including HR, complete Attack/Release/Ratio label maps, Auto Fade and IN-button/rack BP GUI returns captured. Own trial removed and empty AFX2 verified; [dynamics findings](orion-afx-power-dynamics.md#comp-4k-bus--visible-control-pass-2026-11-04) preserve scope and physical/runtime limits |
| NEU-473A (partial) | 80 | Directed AFX 2 assignment, native panel inventory and four paired endpoints. See the [Orion findings](orion-afx-power-dynamics.md#neu-473a--partial-control-capture-2026-11-18). |

PowerGate's labelled load is frame2959 in the local
`unattended-20261025-load-powergate/Orion.pcapng`; the catalog retains its hash
and chain fields. Its six visible knob containers use `Pan` classes, while
`PowerGateBypassPot` is a processing lever. Generic discovery excludes processing
switches even when their class contains `Pot`. Its reviewed six-knob plan and
separate lever trial are now captured; the launcher skips a redundant full
rescan. See [the power dynamics findings](orion-afx-power-dynamics.md) for exact
coverage and limitations. These observations add no runtime support.

The [EQ findings](orion-afx-eq.md) record the completed VEQ-1A/VMEQ-5/VEQ-HLF visible
passes, including every rotary detent. Their launcher workflows skip redundant
full captures; original range plans remain available for explicitly reviewed work.

Earlier unlabelled Instinct/De-Esser captures remain historical; labelled native
batches establish control names independently of catalog declaration order.
Instinct model/processing and factory menu captures are complete; see [its findings](orion-afx-instinct.md). Memory Cat/V12/BBD visible controls are now
captured, including all twelve discrete V12 Voices counts and separate power
round trips; see [the modulation findings](orion-afx-modulation.md). Fresh state
readback, physical scaling and audible/stereo behavior remain unverified.
Exact frames, wire maps
and confirmation limits belong in
[PROTOCOL.md §12a](../PROTOCOL.md#12a-afx-real-time-chain-and-parameter-controls)
and the [Orion profile](../profiles/orion_studio_sc.json).

Memory Cat's mono parameters/readbacks are usable now. Its linked writer is a
bounded candidate awaiting a specific vendor stereo witness and owner audible
confirmation. Isolated bypass-enable writes and instance reads3–7 are incomplete.
Preserve those limits while expanding the catalog.

## Automation available now

The [Windows panel inspector](../tools/windows/README.md) reads the focused
plugin's UI Automation controls and saves a window screenshot directly beside
the script in a shared folder. Use it on Instinct to determine whether named
selectors are available before building the gesture runner. It changes no
settings and requires no individual packet exports or manual file transfers.
An Instinct run now exposes 21 knob classes and five switch-like entries with
positions but blank accessibility values. The inspector is not a gesture
runner or USB batch recorder.

The same [Windows tooling guide](../tools/windows/README.md#capture-stages)
documents the bounded ALT Morph two-click pilot on unlinked AFX channel 2 and
its Linux listener, `tools/afx_vm_pilot.py`. It coordinates passive capture,
visual before/change/restore evidence and labelled frame analysis through a
shared folder. The ALT Morph pilot now has both OUT witnesses and exact visual
restoration, associating the button with byte72. Device parameter readback and
a runtime writer remain unverified. The reusable `Run-AfxScan.ps1` executes
reviewed JSON plans; `instinct-filters` now also completed both switches' visual
round trips in one recording, associating filter/post-filter enable with bytes
76/112. A new plugin uses reviewed data or a bounded plan generated from its
inventory. Knob endpoint candidates and finite selectors use separate evidence
checks; unsupported controls remain explicitly pending.

The standard entry point is now `Run-AfxCapture.cmd`: name the plugin and
its reviewed workflow selects inventory or a prepared batch. V12's reviewed
batch now covers ten knobs (Space first) and Humanize on unlinked AFX2.
Captured byte feedback uses its existing raw ranges; full-panel screenshots
record physical values. The same feedback supports Instinct float32 endpoints,
requires phase-local writes and stable full blocks, and rechecks before ACK.
The launcher preflights PowerShell syntax/native helpers in the Windows VM.
Capture budgets now scale with the planned controls and bounded sweep count.
The host saves accepted per-control progress and the current action before each
gesture. An interrupted job can produce a reviewed remaining-control plan;
partial controls need current-state reconciliation before a fresh full trial.
See the [recovery instructions](../tools/windows/README.md#interrupted-batches-and-reviewed-resume).
Independent review and mocked host/guest tests cover interruptions, stale plans,
late writes and ambiguous labels. A Windows preflight on 2026-10-21 loaded the
reviewed plans and compiled the native helpers without operating plugin controls.
The revised dropdown activation and five visible De-Esser choices passed native
GUI/USB verification on 2026-10-25. Its four-state Monitor/Out selector also
passed after correcting the binary-looking checkbox classification. See
[De-Esser findings](orion-afx-deesser.md). Consecutive-plugin and interrupted/
resumed live acceptance remain separate milestones. Selector metadata covers
cabinet/speaker/model candidates; complete option enumeration remains pending.
Legacy pilot launchers are removed. Instinct's catalog now records all21 knob
endpoint associations and three switches; Volume displays−infinity..+1dB,
with observed float32-le0..1 at offset120. Unknown interpolation laws and
declaration-ID correspondence keep runtime parameter writes disabled.

Fresh startup capture on 2026-10-09 matches Instinct instance1 reply body@17
to the last restored filter-scan write body@20 over write offsets20–123.
The shared offline analyzer now correlates serialized tagged replies, retains
the opaque parameter body, and decodes the three observed switch baselines at
reply offsets69/73/109. Overlapping requests or late replies stop correlation
for that capture. This establishes a restored baseline association; changed
switch readbacks, knob labels/scales and a runtime reader remain unverified.
It sends no queries or writes. Knob automation still requires an exact restore
method; inverse mouse movement alone does not establish restoration.

Run the WebUI as the sole HID controller. The recorder polls its bounded read
API and saves changed chains, link flags and Memory Cat parameter/processing
state. It does not discover unknown commands or effect licenses.

```sh
python3 tools/afx_state_capture.py --channel 1 --seconds 60 --interval 1 \
  --output captures/memorycat-linked-readbacks.jsonl
```

Channels are 1-based in this command; recorded channel/instance indices are
zero-based. Use a new output filename. Reconnection stops the recording rather
than combining sessions. Parameter support is currently Memory Cat instances0–2.
It records actual replies during WebUI edits, without opening another HID
controller or sending parameters.

The offline scanner can reuse existing vendor captures:

```sh
python3 tools/scan_afx_capture.py captures/new/effect-session.pcapng \
  --output captures/effect-analysis.json
```

It groups the three observed parameter opcode families (`0x1c`, `0x20`, `0x7c`),
instances, changing offsets, observed byte ranges, change runs and mirrored
writes. It lists tagged query selectors and decodes Memory Cat replies. It does
**not** yet discover other families, decode other effects' state, identify float
fields or generate labelled JSON maps. Use a new analysis filename to preserve
previous results.

## Proposed batch capture system

The time saving comes from scripting ordinary Launcher gestures and saving an
action log alongside USB traffic. One recording can contain many effects, with
one control changing at a time. Each distinct control encoding still needs
observations; Memory Cat cannot establish another effect's map.

These components are proposed work beyond the existing tools above:

| Component | Job | Owner input |
| --- | --- | --- |
| Local manifest | List Launcher-enabled effects, demos and controls actually present on Orion | Confirm names/availability and review hidden controls |
| Launcher gesture runner | Load, exercise controls, restore trial settings and log actions | Verify selectors or initially mark control locations |
| Passive USB recorder | Record complete HID OUT/IN for bounded batches | Confirm a working capture path |
| Offline batch analyzer | Join actions to frames, draft field maps and report gaps | Resolve uncertain labels, units and scaling |
| Linux verification runner | Test captured write/read/restore contracts through the existing actor | Listen to mono/linked behavior |

Keep optional GUI dependencies in capture tooling, outside the stdlib-only core.
Logs, images and raw captures stay local; reviewed facts go into JSON profiles.

### Reuse Gazelle's existing work

For the current format comparison, open shared-definition proposals, later
capture corrections and colleague onboarding sequence, see the
[Gazelle AFX handoff plan](gazelle-afx-handoff.md). The references below retain
the revisions used for the original Orion pilot.

The reference effect names/control checklist are already imported into
[the shared catalog](../profiles/afx_effects.json), with pinned provenance.
Gazelle offers additional examples for the implementation and verification
passes:

- Its [Discrete 4 fixture](https://github.com/Gazelle-ctl/gazelle/blob/1292df62eff6d97d17b996c227469eb53633c3bf/captures/fixtures/profile_four_preamp_2026-09-14.json)
  records nine confirmed effect configurations with readback contracts. These
  are Discrete 4 observations, with display units/scales still unresolved in
  [the effects review](https://github.com/Gazelle-ctl/gazelle/blob/1292df62eff6d97d17b996c227469eb53633c3bf/docs/EFFECTS-RECON.md).
- [Readback schema](https://github.com/Gazelle-ctl/gazelle/blob/1292df62eff6d97d17b996c227469eb53633c3bf/engine/gazelle-profile/src/read_back.rs)
  and [probe method](https://github.com/Gazelle-ctl/gazelle/blob/1292df62eff6d97d17b996c227469eb53633c3bf/engine/gazelle-probe/src/write_cycle.rs)
  show measured addressing and verification, including distinguishing volatile
  state from the values actually changed. Orion's tagged instance replies need
  their own correlation and bounds.
- The [Konsola rack](https://github.com/Gazelle-ctl/gazelle/blob/1292df62eff6d97d17b996c227469eb53633c3bf/engine/gazelle-panel/assets/skins/konsola/skin.js)
  creates controls from command fields and locates instances in chains. Its
  [browser checks](https://github.com/Gazelle-ctl/gazelle/blob/1292df62eff6d97d17b996c227469eb53633c3bf/tools/browser/konsola_effects.mjs)
  compare rendered slots with device state; their write mode targets a simulated
  daemon. They test Gazelle's WebUI, not Antelope's Launcher.

The inspected [Gazelle Orion profile](https://github.com/Gazelle-ctl/gazelle-device-profiles/blob/a9c87be8b427c23ef5eb5d89c38170a4c65892f8/profiles/antelope/orion_studio_synergy_core.json)
has no AFX mappings. No Launcher gesture-capture runner was found in the checked
Gazelle tooling. Use these examples to design our own consumers and tests;
derive Orion encodings from its captures. Unverified vendor declaration layouts
are not a substitute for that evidence or a source for new wire maps.

### Establish a GUI pilot

The [capture guide](../CAPTURING.md) documents a Windows Launcher VM on Fedora.
Use that route if still available; otherwise use native macOS with the same
labelled procedure. The gesture runner belongs where the Launcher runs. Linux
can record/analyze traffic, but cannot generate an unknown vendor command alone.

On Windows, inspect whether knobs expose names, values and automation patterns;
prefer semantic selectors when available. Microsoft's
[accessibility inspection guidance](https://learn.microsoft.com/en-us/windows/win32/winauto/inspect-objects)
recommends Accessibility Insights. Exposed patterns determine available actions;
Launcher accessibility has not yet been checked.

For custom-drawn panels, use window-relative mouse gestures, fixed display
scaling and a verified panel anchor. A one-time label/location pass per panel may
still be needed. [PyAutoGUI](https://pyautogui.readthedocs.io/en/latest/mouse.html)
can replay clicks/drags but does not identify control semantics. Reuse a layout
only after checking that effect's actual controls and modes.

Pilot Memory Cat against its known fields, then Instinct/De-Esser's two other
captured command families. Measure setup and per-control time before estimating
full coverage. Require correct labels, an OUT witness, useful state evidence and
restoration before enlarging batches.

### Build the local availability manifest

Record what this device's Launcher permits loading, without account/entitlement
traffic. Keep enabled, greyed-out and unknown entries distinct; record owned/demo
status only from owner confirmation. The reference catalog may include meters
or controls absent from the Orion panel; classify them rather than turning them.

An automated load pass can associate visible names with chain types and allocated
instances. Use one effect at a time in a known empty mono slot; log channel,
slot and actual instance instead of assuming instance0. Record initialization
frames and any queries the Launcher issues. Loading blocks do not prove ranges.

### Record labelled control batches

Start with small batches, for example five effects, on an owner-selected empty
test channel outside the active audio path. Preserve existing racks and links.
For each effect:

1. Confirm the intended panel and capture a baseline. Identify the loaded
   chain/instance from traffic.
2. Change one editable control at a time: minimum→middle→maximum→original;
   visit every switch/enum state. Log the label, mode and observed value/unit when
   available. A mouse position is not a numeric parameter value.
3. Add quarter/three-quarter positions only where scaling/quantization remains
   ambiguous. Endpoints plus a middle position do not prove a nonlinear curve.
   Cover mode-dependent controls in relevant modes.
4. Obtain query/reply evidence while loaded. Reopen/refresh a panel only if it
   demonstrably queries state; otherwise capture a controlled Launcher restart.
   Do not invent queries to fill gaps.
5. Restore only trial changes, verify where readback is known, and remove the
   temporary insert. Sent restoration alone remains unverified; preserve newer
   owner edits if interrupted.

Log action start/end times, effect/control, channel/slot, gesture, observed value,
mode and success/failure. Include wall-clock and monotonic times plus a known
isolated gesture to align guest logs with host packets; their clocks may differ.
Crop local evidence images to the panel. Unexpected panels, absent command
witnesses or ambiguous replies stop that job for review. Save completed jobs for
resuming without repetition.

Use one capture and action log per bounded batch, then split by action windows
offline. This removes manual recording start/stop for every plugin or knob.
If semantic automation fails, mark control positions once and let the runner
perform repeated gestures. Fully manual work remains for unsupported panels.

### Produce candidate JSON knowledge

Extend the scanner rather than building another USB decoder. Join labelled
windows to frames and report unrecognized OUT families. Compare full blocks for
byte/bit/integer/finite-float candidates, distinguishing parameters from headers
and meters. Float-like bytes alone do not establish widths, units or scaling.

Match state only when query/reply order identifies the instance unambiguously.
Some replies omit instance identity; overlapping same-type queries must be
flagged rather than assigned to the latest request. Emit draft maps with source
frames and uncertainty, plus missing controls, enum states, ranges, readbacks
and stereo/bypass evidence.

A GUI preset changing several controls can reveal block shape, but cannot name
fields. Final mapping needs isolated gestures. Vendor installation/preset files
are not data sources for this workflow.

### Verify contracts and expose controls

Review candidates into the catalog's Orion implementation and device profile,
following [the schema](profile-schema.md#afx-and-the-shared-effect-catalog).
Captured fields remain observations until bounded write/read/restore trials
verify them. Linux can then automate known round trips through the existing
actor, using fresh state and captured query tuples/ranges. It cannot discover
unknown effects through ID/index sweeps.

Reuse builders for verified matching families while retaining per-effect maps;
a shared opcode does not imply a shared layout. Render ordinary controls from
JSON with a reusable panel module, keeping custom presentations in separate
modules. Check live edits, fresh state and reconnect without settings replay.

Add stereo/bypass trials per effect or demonstrably shared contract, confirming
both distinct linked instances and their settings. Owner listening complements
readback, especially for modes and linked operation. Channel addressing can
reuse the proven rack contract; every control need not repeat on all 32 channels.

## Dedicated native meter session

The owner reserved a separate session for **actual card meter readings**, using
`antelope-ctl` oscillator/routing controls with the existing capture process.
This session runs on Linux without the official Launcher or Windows GUI bridge.
Reuse passive usbmon recording, labelled action windows, full-report decoding,
checkpoints and evidence review from the control campaign; replace vendor GUI
gestures with serialized native device operations. The
[meter inventory and telemetry criteria](orion-afx-displays.md#dedicated-card-telemetry-session)
remain the source of completion requirements. This is a future-session procedure,
not a record of an executed test or a scheduled automation.

### Native controls and evidence already available

- [Matrix operations](../README.md#routing-matrix) provide `matrix-status` and
  `route`, including oscillator sources, AFX inputs/returns and recording/output
  destinations. `protocol.resolve_route_dest`, `resolve_route_source` and
  `build_route_command` obtain addressing and group sizes from the active profile.
  The native WebUI's `/api/routing` and `/api/route` use the existing device actor.
- [Oscillator settings](../PROTOCOL.md#oscillator----two-access-points-settings-panel-decoded-2026-09-01)
  are separate from routing: the captured generator command is a packed
  `SET_GLOBAL` parameter described by `params.oscillator`, built with
  `protocol.build_global_command`. There is no dedicated oscillator-settings
  CLI/UI command today. Frequency-bit label polarity and the apparent shared
  level field still have unresolved semantics, and ordinary state reports do
  not provide a confirmed settings readback. Do not invent CLI syntax or treat
  an old captured byte as the current oscillator state.
- The [prior native meter investigation](../README.md#current-meter-status-2026-09-12)
  already used direct oscillator routing, silence comparisons and restoration
  to map card-returned Surround lanes. Reuse its method and archived evidence;
  its offsets/scales do not establish a plugin's meter contract.

### Oscillator, matrix and capture procedure

1. Give the existing Linux device actor sole HID ownership; release VM USB
   passthrough and leave the Launcher stopped. Run all routing, generator,
   effect and readback operations through that owner. A standalone CLI session
   must not open a second transport alongside an active WebUI actor. Passive
   usbmon recording and audio recording are separate from HID control ownership.
2. Snapshot fresh device routing for every destination group the trial may touch,
   plus the test rack, relevant selectors, effect settings and available generator
   state. `matrix-status` can fall back to cached routes: only confirmed live
   category-`0x03` records are a restoration baseline. Do not rely on CLI/worker
   routing caches for fresh read-modify-write; explicitly refresh each group
   through the actor before changing it and compare device readback afterward.
3. Choose an unused test channel and recording/output destination. The intended
   path is `OSCILLATOR -> AFX In N -> loaded effect -> AFX Out N -> chosen
   destination`. For a test plan using unused AFX2/Computer Record2 channels,
   the existing route operations are `route afx_in 2 osc1` and
   `route com_rec 2 afx2`; substitute the session's actual unused channels.
   Additional recording/physical output taps use the same matrix API and must
   each have a saved baseline. AFX In is a matrix destination; AFX Out is a
   source. Inserting an oscillator means selecting `osc1`/`osc2` as that
   destination channel's source. Removing it means restoring the saved source,
   or temporarily selecting `mute`; there is no empty/unroute operation.
4. Start the bounded full-length, bidirectional HID capture before setup writes
   and retain it through restoration. Log oscillator identity, measured frequency
   and level, destination/channel, effect type/actual instance, action start/end
   frames and verification outcome. Matrix frames resend the whole destination
   group: preserve all other channel pairs, and on cleanup restore only slots
   still attributable to this trial, preserving newer owner changes. Keep audio
   ISO traffic distinct from HID reports and check truncation/drops as in the
   existing capture process.
5. Establish silence by routing the test AFX input to `mute`, then route the
   oscillator back for repeated tone-on/off and level trials. This can gate the
   test path without changing the shared oscillator settings or anyone else's
   oscillator routes. Measure the routed tone's frequency/amplitude through the
   selected recording path when available; do not assume the oscillator's
   last-sent label is a measured signal level.
6. Where generator frequency/level/mute changes are required, use the captured
   packed-byte fields through a bounded native operation on the same actor.
   Preserve the other oscillator's fields and unknown bits, and record the
   baseline's provenance and restoration limits. If a current complete baseline
   cannot be established, keep the generator settings unchanged and gate/measure
   the existing tone through the matrix; establish the missing native state/
   restore contract before relying on generator-setting sweeps. Unknown shared-
   level semantics must not be presented as independent oscillator levels.
7. Exercise one variable at a time: stimulus level, measured effect input/output
   gain, dynamics action, or a captured meter gain/sensitivity control if one
   exists. Use only native effect operations with verified contracts. For other
   captured effects, first add and validate the bounded profile-driven native
   operation through the actor; capture-only mappings do not silently become
   runtime writers. The meter session must not require a Launcher gesture to
   load an effect, alter a gain or operate a special meter.
8. Correlate the card's inbound reports with tone, routing and gain changes.
   Distinguish input/output level from gain reduction or other meter quantities;
   change actual instances/channels independently to establish ownership. Record
   native readouts, measured audio and existing captured panel labels as
   references. The official GUI is not required as a live reference. Preserve
   raw bytes, source frames, layout, timing and uncertainty; retain existing
   distinctions between free-running meter reports and query replies.
9. Finish with silence, then restore and read back the trial's routes, effect/
   selector changes and any generator settings whose restoration contract was
   established. Remove only temporary effects owned by this trial. Stop on
   verification failure and record the exact residual state rather than issuing
   blind repair writes. Publish only correlated card telemetry and measured
   display conversions; absent/stale data stays unknown, with no simulated
   activity derived from oscillator or knob settings.

## Capture transport

For the native meter session, keep the single Linux actor and use usbmon as a
passive recorder; no Launcher, guest GUI bridge or competing HID controller is
needed. For vendor-GUI control discovery, stop the WebUI before the Launcher
owns HID. Capture passively with full report
lengths and both directions. Verify a known 320-byte OUT before a long batch.
Audio ISO may dominate file size; bound recordings and check drops/truncation.

For QEMU **USB-device** passthrough, Linux-host usbmon is a candidate route,
supported by earlier repository captures. General applicability is an inference
from QEMU forwarding and usbmon host-controller observation; validate the current
setup. A whole controller assigned to the guest does not use that host USB path.
Sources: [QEMU USB passthrough](https://www.qemu.org/docs/master/system/devices/usb.html),
[Linux usbmon](https://docs.kernel.org/usb/usbmon.html).
Windows USBPcap and the documented native macOS method are alternatives.

## Completion criteria

For every effect available on this Orion, reviewed JSON knowledge should cover:

- Verified load/remove/reorder addressing, measured instance/resource limits,
  with availability separate from capabilities.
- Editable controls' width/endian/mask, measured raw ranges, enum polarity and
  display units/scaling when established; explicit unknowns elsewhere.
- Fresh parameter/processing readbacks, unambiguous correlation, untouched-field
  preservation and verified write/read/restore results.
- Bypass, linked behavior, live UI controls and reconnect without replay.
- Capture/owner provenance and separate observed, verified and audible status.

The full reference catalog and unsupported devices are separate coverage targets.

V12 batch `scan-V12-Chorus-20261009T184118945Z` completed ten knob endpoint
pairs and Humanize (byte20,0→1→0),138835 packets with zero drops. Captured
write feedback confirms existing raw bounds; power/bypass and device readback
remain unverified. BBD inventories `panel-BBD-Chorus-20261009T184528924Z`
and `panel-BBD-Chorus-20261009T184609823Z` only hovered controls. Reviewed
`bbd-controls` now covers four knob ranges and Chorus/Vibrato via the same
launcher. The next plan now adds a bounded four-position Stereo Type cycle and Power
round trip in the same launch; actual gesture execution and mode labels remain
pending the first complete Windows batch.

Generic selector cycles require a reviewed finite count, bounded visual region
and catalog-preserved candidate field. Before GO the host checks the last
accepted selector value; after each click it checks isolated candidate-byte
changes and distinct positions. The last click must restore starting raw and
visual state. Separate screenshots retain each position. BBD Power accepts
only captured0x14/0x98 events for the same type/instance, preserving event
sequences without persistent-state or polarity claims. Unknown-plugin inventory
explicitly reports partial coverage; existing V12/Instinct plans remain partial.

BBD Chorus/Vibrato now uses measured byte24 change/restoration feedback;
its adjacent animated GainReduction LED caused a false visual guard failure
in `scan-BBD-Chorus-20261009T191323291Z`. Keep phase screenshots, but do
not claim mode image equality or device readback from that feedback.

`scan-BBD-Chorus-20261009T192357505Z` completed eight knob phases and the
mode round trip,57828 packets with zero drops. Selector centre click changed
Basic (raw25=0) to Split (raw25=2,frame53691); repeating the same centre click
produced no OUT and the same picture. Power was not reached. The next same-name
launcher run selects `bbd-remaining`, seven phases for selector and Power only.
`selector_positions` supports four direct row targets plus learned restoration;
initial appearance must uniquely match one captured position, and any preceding
raw baseline must agree. Each target is primed through another row for fresh
OUT. Retain completed knob/mode evidence rather than repeating those gestures.
The complete plan remains available with17phases; row-hit execution is pending.

Master De-Esser inventory `panel-Master-De-esser-20261009T194702842Z`
establishes actual classDeesser, seven enabled knobs and disabled Q under
HighPass1, Monitor/Out, Bypass, and two dropdowns:DeesserPresetsCombobox
andDeesserComboBoxFilterType. Existing type27 writes have unlabelled fields;
no knob encodings are inferred. The next same-launcher `menus` stage invokes
those reviewed ComboBoxes to record popup controls/images, closes with Escape
and verifies unchanged selected values. First Windows execution remains pending.
Review filter choices/Q dependencies before enabling a complete parameter plan.

Master De-Esser menu attempt `panel-Master-De-esser-20261009T203954906Z`
stopped before menu evidence because a whole-UI descendant count exceeded512.
Menu inspection now queries only ListItem/MenuItem roles, bounding visible
options. Owner proposes hover+wheel; next same-name launcher runs the reviewed
`deesser-filter-wheel` two-action trial, one notch forward/back on Filter Type
with GUI selection and captured single-instance checks. No popup/Escape or
preset selection is used. Full option enumeration, Q dependency and parameter
field maps remain pending. No raw offsets/scales were assigned from declarations.

The full-notch trial `scan-Master-De-Esser-20261009T211457387Z` completed
HighPass3 → BandPass1 → HighPass3 with type27/instance0 OUT frames447/1209,
byte26 values3/2 and no other changed parameter bytes. Both guest and host
completed;1754packets/zero drops. This establishes two labelled filter values,
not the entire menu or physical range. At the owner's request, the shared wheel
policy now uses15-unit partial notches, a1500ms pause and at most8increments,
stopping at the first GUI selection change. The reverse is bounded by the
forward count and must restore the initial label. Each increment retains a PNG
and metadata; the slower Windows gesture is pending verification.

The partial-notch run `scan-Master-De-Esser-20261009T212819731Z` also completed
the same two GUI selections, with a single15-unit pulse per phase and1500ms
pauses. The owner reports that wheel input still skips among six choices; the
wheel trials therefore do not establish complete menu coverage. The next
`deesser-filter-menu` plan uses the generic `menu_positions` method: live
visible names and row bounds identify six direct selections, each held5000ms,
followed by restoration of the initial named choice. No labels or raw enum
order are guessed. The host verifies six distinct raw byte26 values, stable
names, selected labels, popup closure and restoration. Input accepts only the
original panel or this opening's verified popup handles. The first attempt,
`scan-Master-De-Esser-20261009T213945408Z`, stopped at the64-row discovery cap;
its514packets contained257complete IN reports, zero OUT reports and zero drops.
The corrected discovery scopes candidates to the active effect panel and nearby
separate popup windows, applying dropdown geometry before counting. It compares
visible rows across opening even when Qt reuses a popup container. Baseline and
open-menu screenshots/metadata are saved before validation, without pointer or
focus changes. Parameter screenshots follow verified selection and closure.
Other plugin controls and presets are excluded from this selector batch.

The corrected discovery run `scan-Master-De-Esser-20261009T214921898Z`
opened Filter Type and stopped before selection because only five named rows
were exposed: HighPass1/2/3 and BandPass1/2. The screenshot shows the same five
choices; the selected HighPass1 header is separate. This does not resolve the
earlier owner-confirmed total of six. The1570packets contained785complete IN
reports, no OUT reports and zero drops.

The owner now reports Page Up/Down move one value after clicking the dropdown
open and closed; hovering alone applies to the wheel. Next is the bounded
`deesser-filter-keys` trial: click open, verify the owned native popup, click
the same dropdown to close unchanged, verify exact ComboBox keyboard focus, Page Down
to the next observed name,5000ms dwell/screenshot/host verification, then one
Page Up back to the initial name. The passive host rejects activation OUT,
wrong/skipped labels, other fields or instances, unstable blocks and newer edits
before the restore key. It observes byte26 writes without an independent
initial state readback. Activation uses the five capture-backed ordered labels;
it does not traverse or screenshot popup rows. First Windows key execution and full inventory remain
pending; no menu count, raw ordering or runtime control contract is promoted.

The [preamp findings](orion-afx-preamps.md) record the completed BA-31/Gyratec IX visible
control pass, with endpoint candidates and an isolated processing-switch round trip.
Runtime parameter writes, physical scaling and independent readback remain open.

## Reviewed queue runner

The [batch runner guide](orion-afx-batch-runner.md) describes fingerprinted
offline queue preparation, a fresh leased GUI bridge, the reusable capture-plan
adapter and compact saved-artifact reports. Completion still requires reviewed
setup/cleanup recipes and semantic evidence review. Validate the Windows changes
and run a supervised bounded trial before unattended use.

## Display observations during capture

Record each plugin's visible VU/peak/gain-reduction meters, LEDs and other live
readouts separately from its editable controls. The [display inventory](orion-afx-displays.md)
and model-local catalog preserve native classes and source evidence, with unknown
signal semantics, scales and device telemetry left explicit. Parameter readouts
are distinguished from signal meters. ATuner's screen reading is deferred by
owner request; its power-control pass does not implement tuning. A control pass
marked complete does not claim decoded metering or screens. No speculative query
is authorized by observing a widget.
