# antelope-ctl

Open-source Linux control for Antelope Audio USB interfaces, reverse-engineered
from USB traffic capture (no official docs, no firmware modification).

## Requirements

- Linux, Python 3.9+ (no third-party packages -- stdlib only).
- Read/write access to the device's `hidraw` node. Either run with `sudo`,
  or add a udev rule granting your user access to the Antelope device's
  `vid`/`pid` (see `device` in the profile JSON) so you don't need root
  every time.
- Captures for adding new params are done from a Windows VM (Antelope
  Launcher + USBPcap + Wireshark/tshark) against the same passed-through
  hardware the Linux side controls -- see `CAPTURING.md`.

## Layout

```
profiles/orion_studio_3.json   <- single source of truth for this device's protocol
antelope/transport.py          <- generic HID open/read/write (no device-specific code)
antelope/protocol.py           <- generic frame build/parse, driven entirely by the profile
antelope/cli.py                <- generic CLI, driven entirely by the profile
tools/capture_diff.py          <- offline helper for finding new params from captures
tools/scan_capture.py          <- offline helper: auto-finds the transition across a whole capture
CAPTURING.md                   <- how to capture USB traffic (Windows VM + USBPcap + tshark)
captures/                      <- put your before/after hex dumps here (gitignore raw pcaps)
```

**Rule of thumb:** if you're about to hardcode a byte offset, param_id, or magic
number anywhere in `antelope/`, stop -- it belongs in the profile JSON instead.
That's what keeps this working across new params and new devices without
touching the Python. (When a new feature needs a genuinely different *frame
shape* -- see `channel_link` below -- it gets its own block under
`profile["frame"]`, rather than being forced into the existing one.)

## Using it (Orion Studio III)

Physical input channels (12 hybrid inputs, addressed 0-11):

```
python3 -m antelope.cli --profile profiles/orion_studio_3.json status
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-mode 0 mic
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-gain 0 12
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-phantom 0 on
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-invert 0 on
python3 -m antelope.cli --profile profiles/orion_studio_3.json meter          # see below re: dB calibration
```

Channel link -- pairs adjacent inputs (ch1+ch2, ch3+ch4, ... ch11+ch12) for
recording a stereo signal. Address either channel in the pair:

```
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-link 2 on   # links ch3+ch4
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-link 3 off  # same pair
```

Output buses -- monitor A/B and headphone 1/2. These are a *different*
address space from the input channels above (see "Buses vs. channels"
below); use either the numeric bus id or its name:

```
python3 -m antelope.cli --profile profiles/orion_studio_3.json bus-status
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-bus-level monitor_a 60
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-bus-dim mona on
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-bus-mute hp1 on
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-bus-mono hp2 off
```

### Buses vs. channels

The SET_PARAM command frame has one byte (`channel_offset`) that means
different things depending on which param you're setting:

- For `gain` / `input_mode` / `phantom` / `phase_invert`, it's a physical
  input index, 0-11.
- For `bus_level` / `bus_dim` / `bus_mute` / `bus_mono`, it's an output
  **bus id** instead: `0`=monitor A, `1`=headphone 1, `2`=headphone 2,
  `5`=monitor B. Ids `3` and `4` are unassigned/unconfirmed on this unit
  (see the profile's `"buses"` section for the reasoning).

Don't mix the two up -- `set-gain 5 10` and `set-bus-level 5 60` both use
"5" but mean completely different things (physical channel 6 vs. Monitor B).

## Adding a new param (e.g. routing)

Same discipline as Phase 1/2 -- capture, correlate against a real user action,
confirm, only then trust it. Nothing is inferred from byte patterns alone.

1. **Capture** a full, untruncated report -- see `CAPTURING.md` for the
   step-by-step (tshark, not Wireshark's plain-text export, which truncates
   past ~110 bytes and hides anything past the first ~90 bytes of a
   320-byte report).
2. In the official Launcher, change **only** the one thing you're
   investigating (e.g. routing), and note the state report just
   before and just after.
3. Save those two 320-byte reports as hex dumps and run:
   ```
   python3 tools/capture_diff.py before.hex after.hex \
       --known-offset 49 --known-offset 61   # suppress already-explained bytes
   ```
   This prints exactly which offsets changed and how -- your candidate
   field for the new param. If you dumped a whole session instead (see
   `CAPTURING.md`), use `tools/scan_capture.py` on the `.tsv` instead --
   it walks every report in order and finds the transition(s) for you, so
   you don't have to hand-pick before/after frame numbers.
4. **Also check what the Launcher actually SENT, not just what changed in
   the readback.** The state-report diff only tells you which bytes moved;
   it doesn't tell you the *opcode*, *param_id*, or exact frame layout the
   Launcher used to cause that. Filter the same capture for outgoing
   `URB_INTERRUPT out` frames (magic `0x70`) and look at the opcode byte
   (offset 4) and the bytes after `param_id_offset` (offset 16) directly --
   don't assume they land at the usual `channel_offset`/`value_offset`
   (17/18). `channel_link` turned out to use a different opcode (`0x14`,
   not the usual `0x13`) with its pair-index and enabled bytes shifted one
   position later (18/19) -- the state-report diff alone would never have
   revealed that shift, only the outgoing command bytes did.
5. Add an entry to `profiles/orion_studio_3.json` under `"params"` with
   `"status": "unconfirmed"` and your candidate offset/id in `"notes"`.
6. If it looks like the existing SET_PARAM(param_id, channel, value) shape,
   test it deliberately with the CLI's escape hatch:
   ```
   python3 -m antelope.cli --profile profiles/orion_studio_3.json raw-set 0 0x53 10
   ```
   and confirm via another capture that *only* the expected offset moved,
   across a few different values, before calling it confirmed.
7. **Don't assume routing (or anything else new) fits the same frame shape.**
   A source x destination matrix likely needs a different opcode or a
   multi-byte payload -- confirm the actual shape from a capture first. If
   it turns out to need a new frame type, add a new block under `"frame"` in
   the profile (e.g. `"frame.routing_command"`, following the same pattern
   as `"frame.link_command"`) rather than overloading the existing
   `SET_PARAM` shape to fit. Add a matching `build_*_command()` function to
   `antelope/protocol.py` alongside `build_link_command()`.
8. Once confirmed, flip `"status"` to `"confirmed"`, add real ranges/enums,
   and add a proper subcommand to `antelope/cli.py` if it deserves one
   (or leave it on `raw-set` if it's rarely used).

## Adding a new Antelope device

Copy `profiles/orion_studio_3.json` to `profiles/<device>.json`, reverse
its VID/PID and protocol from a fresh capture (don't assume it matches --
different product lines may use a different frame format entirely), and
point `--profile` at the new file. `antelope/transport.py`,
`antelope/protocol.py`, and `antelope/cli.py` should need zero changes if
the new device follows the same general "vendor HID, N-byte reports,
SET_PARAM(id, channel, value)" shape. If it doesn't, that's a sign the
frame format itself needs to become part of the profile too (it already
mostly is -- see `"frame"` in the JSON).

## What's still unconfirmed

See `"status": "unconfirmed"` entries in the profile, and
`"unresolved_state_offsets"`. Nothing there is used by the CLI's normal
commands -- it's flagged so nobody mistakes "solved the MVP" for "solved
the whole protocol."

As of the 2026-08 vumeter session: all 12 physical inputs are confirmed
working through the CLI (`set-mode`/`set-gain`/`set-phantom`/`set-invert`),
and Hi-Z is hardware-limited to channels 1-4 (`channels.hiz_channels` in the
profile; `set-mode <ch> hiz` on ch 5-12 now refuses unless you pass `--force`).

As of the follow-up 2026-08 mona/monb/hp1/hp2/chlink captures:

- **Output buses are confirmed.** Monitor A, Monitor B, Headphone 1, and
  Headphone 2 each have a `bus_level` (0-96, 0=-inf, 96/0x60=0dB) plus
  `bus_dim`/`bus_mute`/`bus_mono` booleans, all readable back from a new
  `bus_block` in the state report (see `bus-status`). Bus ids `3` and `4`
  exist in the addressing scheme but were never exercised in a capture --
  don't assume they work.
- **Channel link syncs gain, phantom, AND phase_invert live -- but not mode.**
  `set-link <channel> on/off` sends a real, verified command (a distinct
  opcode/frame from everything else -- see `frame.link_command` in the
  profile), and all 6 pairs were individually confirmed in the capture.
  A follow-up capture (ch-link-gain-ph-inv-test, 2026-08) showed that once
  a pair is linked, changing gain, phantom, or phase_invert on either
  channel mirrors to the other channel immediately -- but `input_mode`
  does not, and the Launcher grays out the mode control while linked. The
  confirmed workflow to change mode on a linked pair is: unlink -> set
  mode independently per channel (gain resets to fit the new mode's
  range) -> re-link. This matches user reports and is expected device
  behavior, not a CLI bug.
  Still **no dedicated link-enabled bit found in the state report** --
  everything observed changing on link is explained as a side effect of
  the gain/status sync above, not a standalone flag. `bus-status` and
  `status` both print a note about this rather than silently omitting it.
  If you find the actual readback bit, that's a great follow-up capture.
- One **unexplained coincidence**: in the monitor-A capture, the `mute`
  status bit flipped on by itself the instant `bus_level` hit its max
  value (96), with no `bus_mute` command anywhere nearby in the log. Only
  seen once, not deliberately reproduced -- see `unresolved_state_offsets`
  in the profile before assuming "max volume implies mute."
- A single-byte state-report change at **offsets 17 and 19** (seen once
  in the original vumeter-test-ch1 session) turned up again in two later,
  otherwise-unrelated captures, always ~3.0-3.06s from the start of the
  capture and with no link/unlink action anywhere nearby -- this rules
  out "link-state readback" as the explanation and points instead to a
  periodic or connection-startup event. Still not deliberately isolated,
  so it stays in `unresolved_state_offsets`.

As of the 2026-08 ADAT test (adat-ch1-2-3-12-link12 capture):

- **ADAT gain is confirmed**, including the outgoing param_id: `param_id
  0x5b`, `channel_offset = adat_channel_index` (0-indexed, ADAT ch1=0 ...
  ch16=15), range -6..+12 dB matching the UI. Readback lives at
  `adat_gain_base_offset = 75`, one byte per channel (confirmed for
  channels 1, 2, 3, and 12 in this capture). `params.adat_gain.id` is now
  `0x5b` -- distinct from physical-channel gain's `0x50`, as suspected.
- **ADAT channel link is confirmed**, including the outgoing pair_index
  encoding: `pair_index = adat_channel_index // 2`, same formula as
  physical channels but over the 16-channel ADAT space, giving 8 pairs
  (pair_index 0-7) instead of physical's 6. Linked ADAT channels' gain
  bytes track together the same way physical-channel pairs do. The
  outgoing frame reuses the *exact same* opcode/param_id as physical
  channel_link (`0x70`/`0x14`/`0xa2`) -- see the important open caveat
  about this below.

As of the follow-up 2026-08 ADAT-link1-2-7-8 capture (activate link1,
link2, link7, link8 in order; sweep gain on ch1/ch3/ch13/ch15; deactivate
link8, link7, link2, link1):

- **Confirms the pair_index formula across the full range, not just
  pair_index 0.** link1/2/7/8 sent pair_index `0x00`/`0x01`/`0x06`/`0x07`
  respectively, each immediately followed by gain-sync behavior on the
  matching pair (ch1&2, ch3&4, ch13&14, ch15&16) -- including pair_index
  6 and 7, which have no physical-channel equivalent (physical only goes
  up to pair_index 5). Full round-trip (link then unlink, in the stated
  order) confirmed for all four pairs.
- **A momentary missed-sync frame was observed and is noted but not
  investigated further** (per instruction): while sweeping ch1's gain
  down, one step (ch1 -> -6dB) has no matching mirrored command for ch2,
  which stayed at -4dB. Looked like a one-off dropped command on the
  wire rather than a parsing artifact. Worth another look if it recurs
  during real use.
- **Open question, still unresolved:** since ADAT link and physical link
  share the identical frame shape (opcode/param_id/pair_index/enabled,
  no other differentiating byte found in any capture so far), and their
  pair_index ranges overlap (physical 0-5, ADAT 0-7), there's no
  confirmed way yet to tell from the frame alone whether `pair_index=0,
  enabled=1` links physical ch1&2 or ADAT ch1&2. No capture so far has
  toggled a *physical* link in the same session as an ADAT one, so there's
  nothing to diff against directly. **Needed before wiring ADAT link into
  the CLI**: a capture that toggles a physical pair, dumped in full and
  compared byte-for-byte (all bytes, not just offsets 16-19) against the
  ADAT link frames already on file -- and if genuinely identical, it may
  be worth checking USB-level fields (endpoint/interface) in case the
  disambiguation happens below the HID report itself, rather than
  assuming it's a firmware quirk with no real distinction.

A settings-tab capture (scr-brght-surroundEQ, 2026-08) covering the
screen-brightness slider and the surround-EQ pre/post toggle produced
**zero** state-report changes beyond normal startup/meter noise -- either
that data isn't in the 0x73 report, or the controls weren't actually
exercised in that capture window. Needs a `tshark -x` recapture logging
every magic (not just 0x73) before drawing a conclusion either way.

The meter report (magic `0x75`) originally had one *candidate* offset:
`frame.meter_report.channel_meter_base_offset = 32`, one byte per channel
(same ordering as gain/status), scale inverted -- resting near `0x60` (96)
and falling toward `0x00` as the input gets louder. That came from a single
correlated capture (scream into ch1 while it was hot, watch byte 32 dive to
0 and climb back), not the capture-correlate-confirm-repeat discipline the
rest of the profile follows.

As of the 2026-08 vumeter-sinewave session, channel 0's offset and scale are
**confirmed**, with a real raw-byte -> dBFS calibration
(`frame.meter_report.db_curve`) to go with it. Method: feed a steady 1kHz
sine into ch0 (a tone sweeps more predictably than white noise) and sweep
`gain` down from its max instead of touching the source level, watching the
Launcher's own on-screen meter. The useful trick: click `phase_invert`
on/off as a marker after each reference point -- it's a real SET_PARAM
command, so it shows up as an unambiguous, precisely-timestamped
`status_base_offset` bit flip in the very same state-report capture, with no
need for a second outgoing-frame capture just to bookmark timestamps. Two
swipes were done this way: one by color (clip, then where orange stops
appearing, then where yellow stops appearing = -12dB) and one by absolute dB
steps read off the Launcher meter (clip, -10, -20, -30, -40, -60). The
reconstructed raw meter byte at each marker tracks the target dB exactly
1:1, raw == -dB, across the whole sweep from 0 to -60 -- see `db_curve` and
its notes for the full point list and one leftover oddity (a stray marker
click at raw=72 that doesn't fit either swipe's sequence or the line at
all, presumably an incidental click made while resetting gain between
swipes).

The same session also pinned down the meter LED color thresholds in
`frame.meter_report.led_scale`: yellow/green at exactly -12dB (both stated
directly and matching the measured raw=12 point), and orange/yellow at
-4dB (matching two independent estimates -- the captured marker's raw=4, and
the user's own LED-segment count). There's no separate solid-red band below
clip -- orange runs straight through to 0dB, and red only appears at clip
itself.

All 12 channels' meter offsets are now confirmed working (2026-08 -- each
channel's meter tracks its own signal correctly). `db_curve` is still from
the channel-0-only sweep above and is applied to every channel for lack of
a per-channel one -- reasonable estimate, not independently verified past
channel 0. Don't build anything on the deep-silence tail past -60dB either
-- it isn't swept yet, and the stray raw=72 point above hints it may not
stay linear that far down. Try `python3 -m antelope.cli --profile
profiles/orion_studio_3.json meter` while making noise into a channel to see
it live.

**Capture format matters.** Wireshark's plain-text/"Copy as Text" export
only exposes ~111 of each 320-byte report's bytes, which is why the meter
report above is still unconfirmed. Always use `tshark -x`, or better, the
whole-session `-T fields` dump described in `CAPTURING.md` (that's what all
of the mona/monb/hp1/hp2/chlink captures used, and it's also what let
`tools/scan_capture.py` find every transition automatically instead of
hand-picking frame numbers).
