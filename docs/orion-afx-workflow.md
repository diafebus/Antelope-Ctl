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

## Evidence already available

| Effect | Orion type | Existing evidence |
| --- | --- | --- |
| Memory Cat Brigade | 73 | Eight fields, fresh parameter/processing reads for instances0–2, Launcher-restart retention, owner-confirmed switch labels |
| Instinct | 75 | Load/chain,93older linked parameter writes, opcode`0x7c`, observed query75/1; automated GUI trials map three switches and all21 knob endpoints; model selection, power, interpolation laws and runtime readback remain unresolved |
| Master De-Esser | 27 | Load/chain and older linked writes; native capture now covers eight knob endpoint candidates, five filter choices, four monitoring states, processing-button round trip and preset inventory; runtime readback/scaling remain unverified |
| V12 Chorus | 70 | Labelled modulation capture: eleven changed fields and245 mirrored pairs; reader/restoration still unverified |
| BBD Chorus | 78 | Demo modulation capture: five changed fields and85 mirrored pairs; stereo-mode mapping and reader/restoration still unverified |
| PowerGate | 39 | Six knob endpoint candidates and processing-lever GUI round trip captured; runtime/readback/scaling unverified |
| PowerEx | 51 | Six knob endpoint candidates and processing-switch GUI round trip captured; runtime/readback/scaling unverified |
| VEQ-1A | 6 | Five continuous knob endpoint candidates, all three rotary maps and processing-switch GUI round trip captured; runtime/readback/scaling unverified |
| VMEQ-5 | 5 | Three gain knob endpoint candidates, all 5/11/5 rotary maps and processing-switch GUI round trip captured; runtime/readback/scaling unverified |
| VEQ-HLF | 11 | Both eleven-position cut-off selectors and processing-switch GUI round trip captured; runtime/readback/units unverified |
| BA-31 | 48 | Both knob endpoint candidates and processing-switch GUI round trip captured; runtime/readback/scaling unverified |
| Gyratec IX | 43 | Both continuous endpoint candidates, all Phase/Low-Cut detents and processing round trip captured; runtime/readback/scaling unverified |
| VPA 76 | 44 | Warmth/Trim endpoint candidates, both filter detent maps and processing round trip captured; runtime/readback/scaling unverified |

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
Instinct model/processing work remains open. V12/BBD visible controls are now
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

## Capture transport

Stop the WebUI before the Launcher owns HID. Capture passively with full report
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
