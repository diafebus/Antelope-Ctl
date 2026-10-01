# Orion AFX capture and implementation workflow

The aim is to support every effect available to this Orion, using reusable JSON
knowledge. The catalog's 80 reference entries are a starting checklist, not an
Orion availability list. Current executable support is the five-effect captured
pilot in [SCOPE.md](../SCOPE.md#orion-captured-effect-pilot).

This document describes the capture method and completion criteria. The local,
ignored `AUDIT.md` holds the current work order.

## Evidence already available

| Effect | Orion type | Existing evidence |
| --- | --- | --- |
| Memory Cat Brigade | 73 | Eight fields, fresh parameter/processing reads for instances0–2, Launcher-restart retention, owner-confirmed switch labels |
| Instinct | 75 | Load/chain, 93 parameter writes in the linked-control capture, opcode`0x7c`, paired writes, observed query75/1; control labels/scales unresolved |
| Master De-Esser | 27 | Load/chain, 126 parameter writes in the linked-control capture, opcode`0x20`, paired writes, observed query27/1; control labels/scales unresolved |
| V12 Chorus | 70 | Load/reorder and a parameter block, without changing control bytes in that capture |
| BBD Chorus | 78 | Demo load/reorder and parameter blocks, without changing control bytes in that capture; query78/0 observed separately |

Instinct and De-Esser changes can reduce new capture work, but their individual
control order was not labelled. Do not assign names from catalog declaration
order. V12 and BBD still need isolated labelled changes. Exact frames, wire maps
and confirmation limits belong in
[PROTOCOL.md §12a](../PROTOCOL.md#12a-afx-real-time-chain-and-parameter-controls)
and the [Orion profile](../profiles/orion_studio_sc.json).

Memory Cat's mono parameters/readbacks are usable now. Its linked writer is a
bounded candidate awaiting a specific vendor stereo witness and owner audible
confirmation. Isolated bypass-enable writes and instance reads3–7 are incomplete.
Preserve those limits while expanding the catalog.

## Automation available now

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
