# Remote Discrete-profile completion playbook

This is a field guide for an AI agent or engineer working over SSH on a
machine that has an Antelope Discrete device attached, but without physical
access to the official Antelope Launcher. It is deliberately conservative:
the Orion and Zen Go profiles are sources of hypotheses and tooling patterns,
not byte-level templates for another device.

The goal is to improve one device profile at a time, using the tools already
in this repository, while preserving enough evidence for another agent to
reproduce or reject each conclusion.

## What can and cannot be done without the Launcher

Remote access is enough to do useful work:

- identify the USB/HID node, report descriptor, report length, report IDs, and
  endpoint metadata;
- observe passive state, meter, and unsolicited reports;
- test an already-confirmed command from the device's profile while capturing
  both directions;
- inspect in-band readback only where that device's own bounds or a
  capture-confirmed index make the query safe;
- compare the device's reports with the public Antelope report schema and
  extract candidate field layouts;
- add profile metadata, parsers, fixtures, tests, and documentation without
  touching the device.

Remote access is not enough to prove a new write command from an inbound-only
capture. A state byte changing does not reveal the opcode, parameter ID,
payload layout, or whether the change came from the host or the device. For a
new write mapping, some controlled outbound action must exist: an already
working project command, a vendor client available on the remote host, or a
remote operator who can make the device/client perform the action. If none is
available, record the limitation and stop at passive/schema work; do not
invent a command by copying Orion bytes.

Wireshark is not mandatory. A full raw capture from Linux `usbmon`, Windows
USBPcap, native-macOS XHC, or an equivalent tool is sufficient. What matters
is seeing the complete device-specific traffic, especially the OUT command
and the matching IN report.

## Current starting point

| profile | current evidence | first useful remote objective |
|---|---|---|
| `discrete_8_pro_sc.json` (`0xa2b5`) | HID identity/transport, the ordinary command shape, and six basic parameters are confirmed by the peer profile. The device does not stream state and has no confirmed readback. Bus dim/mono and channel link remain unconfirmed. | Verify the Linux HID report-ID/write-length behavior, then capture one already-known control and map the actual state/readback behavior without assuming Orion's passive model. |
| `discrete_4_sc.json` (`0xa2be`) | Identity, report size, and channel/state-layout hints exist. The command frame and state offsets are unconfirmed; `params` is empty. | Obtain the first device-specific outbound frame and confirm transport before adding any writable parameter. |
| `discrete_4_pro_sc.json` (`0xa2bf`) | Identity, report size, and a schema-derived report layout exist. The command geometry is only derived: offset 4 may be a payload length, not an opcode, and the selector byte is unresolved. `params` is empty. | Capture one real preamp or bus action. Do not use the Orion `0x13` command builder until the captured frame proves that shape. |

The exact current fields are in the profiles. The profile status is evidence
for that device only; a shared VID, PID family, parameter number, or report
size does not establish shared semantics.

## Evidence and status rules

Use this evidence order:

1. a full, device-specific OUT+IN capture with an isolated action;
2. a device-specific passive capture or direct device observation;
3. the device's own report schema or manual;
4. a sibling profile, used only to form a candidate;
5. intuition or a numerical resemblance, which is not evidence.

Use profile statuses consistently:

- `confirmed`: repeatable on this exact device, with the command and the
  resulting state/readback correlated;
- `observed`: seen, but the meaning or field ownership is not isolated;
- `derived`: inferred from the device's own schema or fixed layout, not yet
  validated against a real transition;
- `unconfirmed`: a candidate that must not drive a normal command;
- `capture-confirmed`: a specific readback layout or outer index was proven
  safe by this device's capture, even if the whole category is not bounded.

Do not turn `observed`, `derived`, or `unconfirmed` into runtime capability
merely because a frame was accepted or the device stayed silent. On the
Discrete 8 Pro, a recognised opcode can be silent and still have no effect.

## Non-negotiable safety rules

The Orion hard-faulted after an out-of-range in-band readback index, and the
Discrete 8 Pro hard-faulted on dangerous opcodes and invalid channel indices.
Treat that as a family hazard until disproven on a particular model.

- Never sweep opcodes, parameter IDs, channel indices, or readback indices.
- Never use `--unsafe` or `--force` for exploratory work.
- Never query a readback category unless the profile has a device-derived
  `frame.readback.category_counts` entry or an explicitly capture-confirmed
  safe layout/index. If the count is unknown, index 0 is the maximum
  exploratory query allowed by this playbook, and only when the profile has a
  readback block for that device.
- A nested `record_count` is the number of records inside one response. It is
  not a safe outer query bound.
- Do not use `tools/readback_probe.py --poke` on a stub or on a device whose
  command frame is not confirmed. Do not use its `--ct` vendor-request sweep
  as a first-line test.
- Do not write to a device when the report ID, hidraw write length, or command
  shape is unresolved. A write failure is not proof that the command was
  harmless.
- If the free-running report stops, an OUT write times out, or the device
  emits an error frame, stop. Do not retry a suspected crash, reset the USB
  device, or continue probing without the device owner's explicit recovery
  plan.
- Keep audio streaming and disruptive clock/sample-rate experiments out of
  the first pass.

## Remote session setup

Run these checks on the machine physically connected to the target device.
Keep raw captures and logs in a private temporary directory; `captures/` is
gitignored, but a raw USB capture can still contain the device serial.

```bash
cd /path/to/antelope-ctl
git status --short --branch
python3 -m json.tool profiles/discrete_4_sc.json >/dev/null
python3 -m json.tool profiles/discrete_4_pro_sc.json >/dev/null
python3 -m json.tool profiles/discrete_8_pro_sc.json >/dev/null
lsusb -d 23e5:
```

Use the exact profile matching the attached PID. Do not silently substitute
Orion or Zen Go just because the device is in the same USB family.

### Descriptor and passive observation

These two commands do not require the Launcher and do not send a feature
write. They are the correct first probes for all three Discrete profiles:

```bash
python3 tools/hid_probe.py \
  --profile profiles/discrete_4_sc.json \
  > /tmp/discrete4-hid-probe.txt

python3 tools/readback_probe.py \
  --profile profiles/discrete_4_sc.json \
  --seconds 8 \
  > /tmp/discrete4-passive.txt
```

Substitute the matching profile for a Discrete 4 Pro or Discrete 8 Pro.
`hid_probe.py` records the HID descriptor, Feature/Input attempts, report IDs,
and lengths. `readback_probe.py` phase 1 records passive report magics and
moving offsets. It writes a local `tools/readback_probe_out.txt`; treat that
as private too.

Expected outcomes are informative, not failures:

- no passive control report on the Discrete 8 Pro is consistent with its
  current profile and means only that it does not volunteer state;
- a `0x73`, `0x75`, `0x83`, or other report magic must be identified from the
  target capture, not renamed to Orion's magic by analogy;
- a HID descriptor with no Report ID is a transport concern. On Linux,
  hidraw may require a leading report-number byte, making the OS write 321
  bytes for a 320-byte payload. Confirm this before changing transport code
  or sending writes.

Do not paste descriptor output or category `0x01` bodies into a public issue
or commit if they contain identity data. Keep only a redacted summary and a
hash of the private artifact.

## Capturing remotely without the Launcher

### Linux host / `usbmon`

If the remote host is Linux, capture at the USB bus while another safe client
or remote operator performs one isolated action. `usbmon` sees traffic even
when a VM owns the USB device.

```bash
sudo modprobe usbmon
lsusb -d 23e5:
dumpcap -D
dumpcap -i usbmonN -a duration:30 -w /tmp/discrete-one-action.pcapng
```

Run the capture and the action from separate SSH sessions. On a host where
`dumpcap` needs elevated access, use the site's approved `wireshark` group or
privilege mechanism; do not weaken permissions broadly.

For a Discrete 8 Pro, an already-confirmed basic command may be a useful
round-trip subject after the owner has confirmed the hidraw report-ID issue:

```bash
python3 -m antelope.cli -p profiles/discrete_8_pro_sc.json \
  set-gain 0 30
```

This does not discover a new command and does not establish readback. Capture
the action and restore the prior setting. For the two Discrete 4 stubs, do
not run `raw-set` or synthesize an Orion frame; there is no confirmed command
shape for them yet.

### Extracting a full USBPcap/usbmon capture

Do not use Wireshark's truncated “copy as text” output. Extract full payloads
with both HID fields so the command works across tshark versions:

```bash
tshark -r /tmp/discrete-one-action.pcapng \
  -Y 'usb.data_len==320' \
  -T fields \
  -e frame.number \
  -e frame.time_relative \
  -e usbhid.data \
  -e usb.capdata \
  > /tmp/discrete-one-action.tsv

python3 tools/scan_capture.py \
  /tmp/discrete-one-action.tsv \
  --all-magics
```

The outgoing magic `0x70` row is the command candidate. Inspect its actual
bytes first; the opcode, selector, target, and payload positions may all
differ. The incoming transition may be `0x73`, `0x83`, or another device
report. `scan_capture.py` is a transition finder, not a semantic decoder.

For a native macOS capture, use the repository's Darwin parser instead:

```bash
python3 tools/scan_macos_capture.py \
  /tmp/discrete-one-action.pcapng
```

Confirm that the capture contains an outgoing `0x70` line. An IN-only file
can locate a changing state byte but cannot identify the command that caused
it.

### State transition analysis

When a complete before/after state report is available:

```bash
python3 tools/capture_diff.py before.hex after.hex
```

Use `--known-offset` only for offsets already proven on this exact device.
The diff produces candidate offsets; it does not prove the parameter ID or
the command layout. Confirm a candidate with multiple values, multiple legal
targets, and a restore action, while watching the exact command timestamp.

## Device-specific work order

### Discrete 4 Synergy Core

1. Run `hid_probe.py` and record the actual descriptor, Report ID behavior,
   report lengths, and any endpoint metadata visible in the capture.
2. Run the passive probe long enough to distinguish a free-running state
   stream from a meter stream. Keep the raw report private.
3. Obtain one real outbound action from any available client. A PnP record or
   Antelope report schema cannot fill `frame.command` by itself.
4. Decode the command header and payload from that frame. Only after the
   frame is understood should the profile receive a `params` entry such as
   gain, mode, phantom, phase, or link.
5. Capture one control at a time and map state offsets independently. The
   existing four-channel layout is a starting hypothesis, not permission to
   write four channels or copy Orion's values.
6. Add bus IDs, digital I/O, routing, mixer, mic-model, and readback only
   after their own device evidence exists.

If no client can produce an outbound action, the correct deliverable is a
better transport/state/schema note and a blocked command bring-up, not a
guessed `0x13` builder.

### Discrete 4 Pro Synergy Core

Start with the same descriptor/passive workflow, but treat the report schema
as especially non-portable. The current schema-derived notes suggest that
offset 4 may be a payload length and that the payload identifier is not
necessarily the parameter selector at offset 16. Therefore:

- do not call offset 4 an opcode until an OUT capture proves it;
- do not populate `params.<name>.id` from the schema's payload ID;
- capture a real gain or phantom action before adding a command builder;
- verify the unusual preamp-gain stride and six-entry bus block against a
  real report before making them runtime state offsets;
- leave unknown bus names and selectors empty rather than inheriting Orion.

### Discrete 8 Pro Synergy Core

The peer profile has the strongest starting point, but it is not an Orion
profile:

- `0x13` and six basic parameters are confirmed, while bus dim/mono and
  channel link are not;
- the device does not stream state and has no confirmed in-band readback;
- the profile records a HID descriptor with no Report ID, so Linux hidraw
  write framing must be checked before using the generic 320-byte path;
- Orion's bus scale, input-mode values, link frame, passive-read behavior,
  and mixer/routing assumptions must not be copied.

Priority order is: transport write framing, one known preamp command capture,
state/error behavior, bus controls, channel link, digital I/O, routing/mixer,
then meters and advanced features. An accepted but silent `0x14` does not
count as a working link command.

## How to use Orion and Zen Go findings safely

These are candidate families to compare against a real Discrete OUT frame,
not commands to send blindly:

| Orion/Zen concept | Candidate only | What must be re-proven |
|---|---|---|
| ordinary per-target parameter | Orion `0x13`, often ID at `@16`, target/value nearby | opcode, selector, target space, value encoding, bounds |
| stereo link | Orion `0x14` shape | opcode, space selector, pair index, enabled byte, actual effect |
| device-global setting | Orion `0x12` | whether the device has the opcode and where its value lives |
| mixer | Orion/Zen mixer frames differ already | opcode, subcommand, mix/channel numbering, strip count, flags |
| mic modeling | Orion uses a different frame from Zen's candidate | device presence, opcode, channel bias, model/pattern encoding |
| routing | Orion `0x53` is an array payload | destination groups, source banks, channel count, whole-state semantics |
| in-band readback | Orion/Zen use the same family shape, but counts/layouts differ | response header, category bounds, per-category body, safe indices |

The AntelopeAudio schema and manager logs are useful for discovering names,
field types, and likely nested arrays. They do not prove that a Discrete
device exposes the same category, outer count, selector, or transition.

## Readback procedure after a profile has evidence

First add the target's own `frame.readback` header. Then populate
`category_counts` only from that device's connect enumeration. If the device's
connect walk is sparse, add an exact or ranged `record_layouts` entry with
`status: "capture-confirmed"` only for outer indices proven by that device's
capture.

Use the guarded CLI for one known safe query:

```bash
python3 -m antelope.cli \
  --profile profiles/<device>.json \
  readback 0x01 0
```

Category `0x01` commonly contains the serial. Keep its output private. For
bounded profiles, `tools/readback_enum.py` may enumerate only the declared
category range. For an unbounded category, the script now defaults to index 0
only; never add `--unsafe` to make progress. A non-empty response can reveal
a body layout, but it does not establish the next safe index.

When a response contains nested records, declare the inner `record_count` and
field widths in `frame.readback.record_layouts`. Use the generic parser and
offline fixtures first. The parser may decode a body with a schema-only
layout, but the query path must remain blocked until the outer index is
capture-confirmed.

## Profile update contract

For every new finding:

1. preserve the raw capture privately and record a SHA-256 hash;
2. write a short action log: device model/PID, exact control, order, values,
   timestamps, and whether audio or another client was active;
3. add the candidate to the matching device profile as `unconfirmed` or
   `derived`, with the capture filename and observation in `evidence`;
4. add a new `frame` block when the payload shape differs—do not bend
   `frame.command` to fit it;
5. add device-specific ranges, enum values, address spaces, and hazards only
   after they have been tested on that device;
6. flip to `confirmed` only after the outbound bytes, resulting report, and
   repeat/restore behavior agree;
7. add an offline fixture/test before wiring a normal CLI or WebUI command;
8. update `PROTOCOL.md`, `README.md`, `docs/profile-schema.md`, the relevant
   startup notes, and WebUI documentation together.

Never copy a whole Orion profile and delete the fields that look wrong. Start
from the target profile, retain unknowns explicitly, and keep `family_notes`
clear about which sibling supplied a hypothesis.

## Validation and handoff

After offline profile edits, run:

```bash
python3 -m json.tool profiles/<device>.json >/dev/null
python3 -m py_compile antelope/protocol.py antelope/cli.py
python3 -m unittest discover -s tools -p 'test_*.py'
git diff --check
```

Do not run `tools/selftest.py --write` on a profile that has no confirmed
readback contract and restore-safe write targets. A profile without a
readback path should be reported as write-only, not made to look verified by
the absence of an error.

Use this compact handoff record in the agent's final note:

```text
device/model + PID:
profile:
remote host / OS:
transport: report size, report ID, endpoint evidence:
passive magics and report rates:
outbound action source (if any):
command bytes proven:
state/readback body proven:
safe outer readback indices:
new profile fields and status:
tests run:
raw artifacts kept privately at / hash:
remaining blocker:
```

The most valuable honest result may be “transport and passive reports
confirmed; no outbound client action available.” That narrows the next
remote session without putting a Discrete unit at risk.
