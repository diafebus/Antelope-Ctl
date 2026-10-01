# Orion AFX capture and implementation plan

The JSON profiles are the reusable protocol record. Runtime writers are enabled
only for captured Orion commands and measured instance ranges; other devices
need their own evidence. UI labels, layouts and validation consume these facts.

## Current state

| Effect | Orion type | Existing evidence | Next step |
| --- | --- | --- | --- |
| Memory Cat Brigade | 73 | Eight parameters, readbacks for instances0–2, processing flag, retained settings, owner-confirmed switch labels | Confirm audible linked editing; complete isolated bypass-enable evidence and read evidence for instances3–7 |
| Instinct | 75 | Load/chain, opcode`0x7c` parameter blocks, paired instance writes, state query75/1 | Analyze existing float-like field changes; associate each with its labelled control |
| Master De-Esser | 27 | Load/chain, opcode`0x20` parameter blocks, paired writes, state query27/1 | Analyze existing multibyte changes and obtain only missing control labels |
| V12 Chorus | 70 | Load/reorder and a parameter-frame witness | Establish controls and current-state query before a complete UI |
| BBD Chorus | 78 | Demo load/reorder, parameter-frame witnesses, state query78/0 | Decode controls without treating demo availability as ownership |

Memory Cat modes are raw0=550ms/Chorus and raw1=1100ms/Tremolo. `chrs_vibr`
remains the wire/API compatibility identifier. The owner's confirmation supplies
label polarity; captures supply offsets and ranges.

Linked Memory Cat knob changes were previously discarded by both frontend and
backend guards. The fix uses fresh link/chain reads, writes the existing selected
instance and a same-slot Memory Cat partner when present, and verifies only the
captured read indices0–2. A different or absent partner is left unchanged, without
loading an effect as a side effect of a knob turn. Captured other-effect parameter
families motivate right-then-left mirroring; a Memory Cat-specific vendor stereo
parameter capture is still pending. This is a bounded operator candidate, not a
claim that every stereo effect has the same internal behavior.

A linked pair can retain different racks. Refresh reads both. If the selected rack
is empty and its partner has inserts, the popup selects that actual populated
channel so its controls remain available. Link/unlink itself preserves both racks.

## Linux automation available now

Run the WebUI as the sole HID controller. The new recorder polls its existing
bounded read API and writes only changed state snapshots, including chains, link
state, Memory Cat settings and bypass. It does not access raw HID separately,
send parameters, sweep type IDs, or record identity/account information.

```sh
python3 tools/afx_state_capture.py --channel 1 --seconds 60 --interval 1 \
  --output captures/memorycat-linked-readbacks.jsonl
```

Channels are1-based. Use a new output filename for each recording. A device
connection change stops the recording rather than combining two sessions. Current
parameter support is Memory Cat instances0–2; this tool cannot discover unknown
parameter commands or effect licenses. Move the WebUI controls while recording to
obtain an automatic timeline of actual replies. Once another effect has a verified
state reader, the same workflow can be extended to that effect.
Recorded channel and instance indices use the zero-based protocol/API convention.

Analyze existing vendor captures offline with the existing scanner:

```sh
python3 tools/scan_afx_capture.py captures/new/effect-session.pcapng \
  --output captures/effect-analysis.json
```

It groups parameter opcodes/types/instances, changed bytes, change runs, ranges,
mirrored writes and tagged state queries. Analysis can automate byte/float
candidate detection, write/read correlation and creation of draft field maps.
Names, units and endpoint semantics still require independent evidence.

## Ordered implementation passes

1. Finish Memory Cat's mono/linked read-write and audible validation. Keep bypass
   as a separate confirmed-state reader until isolated enable/disable writes are
   proven. Do not repeat the already confirmed input/AFX link-map trials.
2. Decode the existing Instinct and Master De-Esser captures first. Match their
   change runs to the declared control list; request only missing labels or an
   ambiguous endpoint, rather than another full sweep.
3. Put each confirmed field into the Orion implementation: opcode/subcommand,
   type/instance addressing, width/endian/range, enum/scaling, write and read
   offsets, source capture and confirmation status. Keep reusable effect names
   and descriptions in the shared catalog, with model-specific encodings.
4. Generate the control surface from that complete field map in a separate panel
   module. Require fresh whole-state reads, preserve untouched fields, and test
   write/read/restore round trips before expanding effect controls.
5. Move to V12 and BBD, then the remaining available effects. One effect per
   evidence/implementation pass; loading IDs and resource counts alone do not
   authorize parameter writes or identify account ownership.

## When new vendor evidence is required

Linux can observe device traffic, but it cannot reproduce an unknown vendor
parameter gesture without the Launcher generating it somewhere. For each new
FX, make one continuous vendor session: load into a known empty slot, visit each
control in a written order, move minimum→maximum→middle (or cycle a switch),
then reconnect the Launcher to record retained state. Endpoint changes are more
useful than a slow sweep through every intermediate knob position. Keep mono
control identification separate from one short linked-mirroring test. No need to
repeat the same control on all32 channels.

If the Launcher runs in a Windows guest with QEMU USB-device passthrough, the
Linux host may be able to capture the USB requests with binary usbmon even though
it cannot run the Launcher itself. This is an inference from QEMU's `usb-host`
forwarding and usbmon's host-controller request monitoring; verify an actual
320-byte OUT witness first. It does not apply to a whole USB controller assigned
to the guest. Sources: [QEMU USB-device passthrough](https://www.qemu.org/docs/master/system/devices/usb.html),
[Linux usbmon](https://docs.kernel.org/usb/usbmon.html).

Use binary capture with sufficient packet length: usbmon text traces may truncate
payloads. Filter the Orion HID interface and control endpoints; audio ISO traffic
is separate. Stop the Linux WebUI before handing the device to the vendor
controller. No VM, controller assignment or capture permissions are changed by
this plan.

Vendor GUI automation must run where the Launcher runs. A repeatable per-panel
control script could perform labelled endpoint gestures and annotate captures;
its selectors/layout and licensed/demo availability must be checked first. Linux
can automate recording and analysis around it, but cannot infer missing controls
from readbacks alone. If GUI automation is impractical, the one-session-per-effect
manual sequence above is the fallback.
