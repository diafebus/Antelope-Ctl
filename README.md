# antelope-ctl

Open-source Linux control for Antelope Audio USB interfaces, reverse-engineered
from USB traffic capture on hardware the contributors own (plus facts from
Antelope's own public manuals). No vendor software, firmware, or source is
used; the device firmware is not touched.

> **Looking for the wire format?** The protocol spec -- frame types, the
> bus-vs-channel address spaces, every bitmask, the `0x73` state-report
> byte-map, talkback, output trim, meter calibration, open questions --
> lives in **[`PROTOCOL.md`](PROTOCOL.md)**. This README is the guide to
> *using* the tool.

## Legal status & disclaimer

This is an independent interoperability project. It is **not affiliated
with, authorized by, or endorsed by Antelope Audio**. "Antelope",
"Orion", "Discrete", "Synergy Core" and related names are trademarks of
their respective owner and are used here only to identify the hardware
this software interoperates with.

- **No Antelope software, firmware, or source code is included or
  redistributed here.** The device is not modified and its firmware is
  not touched.
- The protocol description was produced by **observing USB traffic
  to/from hardware the contributors own**, on their own machines, for
  the sole purpose of making that hardware usable on operating systems
  the vendor does not support (Linux). Reverse engineering for
  interoperability is recognised in the US (e.g. *Sega v. Accolade*,
  *Sony v. Connectix*) and expressly permitted in the EU (Software
  Directive 2009/24/EC, Art. 6).
- **Antelope's own publicly published documentation** (user manuals, spec
  sheets, signal-flow diagrams from their download pages) is used only as
  a source of *facts* -- channel counts, feature names, signal flow. No
  manual text, tables, or diagrams are reproduced here; documents are
  cited in the profile's `evidence` fields.
- **Packet captures** committed under `captures/` are recordings of the
  contributor's own device on the contributor's own machine, kept
  minimal and included only as evidence for a documented finding. Device
  serial numbers are redacted where practical.
- **The licensed AFX plugin chain is out of scope.** Those plugins
  involve per-user licensing and online activation; this project does not
  touch, emulate, or circumvent any licensing or authentication
  mechanism. Device-*bundled* effects that carry no per-plugin activation
  (e.g. AuraVerb) are treated as ordinary device controls.
- Use at your own risk. Sending control frames to hardware can put it in
  unexpected states; see "hazards" in the profile JSON. No warranty.

If you are a rights holder with a concern, please open an issue.

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
tools/scan_capture.py          <- offline helper: auto-finds the transition across a whole capture (Windows TSV)
tools/scan_macos_capture.py    <- same, for native-macOS (Darwin XHC) pcapng -- see CAPTURING.md
CAPTURING.md                   <- how to capture USB traffic (Windows VM + USBPcap, or native macOS)
PROTOCOL.md                    <- the reverse-engineered wire format, in reference form
captures/                      <- analyzed .tsv exports + raw .pcapng captures/ (full-fidelity)
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

**Important (2026-08, confirmed on real hardware):** the device itself does
NOT propagate mode/gain/phantom/phase across a linked pair -- that's the
official Launcher software sending extra commands, which `set-link` now
replicates. See "Channel link is real, but the syncing you see isn't the
device doing it" below before assuming any other tool will behave the same
way against this hardware.

ADAT inputs -- a separate 16-channel space (ADAT ch 0-15), gain + link
only (no mode/phantom/phase):

```
python3 -m antelope.cli --profile profiles/orion_studio_3.json adat-status
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-adat-gain 0 6      # ADAT ch1, +6 dB
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-adat-link 0 on     # links ADAT ch1+ch2
```

ADAT link behaves exactly like the preamp link (user-confirmed on
hardware): linked channels move gain together, and -- as with the preamp
-- that's the *software* sending a second command, not the device, so
`set-adat-gain` mirrors to the linked partner itself. **Caveat:** the ADAT
and physical `SET_LINK` frames are byte-identical (both `space` byte
`0x00`), so `set-adat-link` on pairs 0-5 may also toggle the matching
*physical* link (ch1&2 ... ch11&12). Pairs 6-7 are ADAT-only. See
`params.adat_channel_link` in the profile.

S/PDIF input -- a 2-channel space (0 = L, 1 = R), gain + link only:

```
python3 -m antelope.cli --profile profiles/orion_studio_3.json spdif-status
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-spdif-gain 0 6   # S/PDIF L, +6 dB
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-spdif-link on    # links L+R
```

Same gain-mirroring behaviour as the other links. The S/PDIF `SET_LINK`
frame carries a distinct `space` byte (`0x01` vs `0x00` for physical/ADAT),
so it has **no** cross-space ambiguity -- `set-spdif-link` only touches
S/PDIF. Confirmed from `spdif-gain-link.pcapng` (gain param `0x5c`,
readback at state-report offsets 91/92).

Output buses -- monitor A/B, headphone 1/2, plus the settings-tab Line and
Reamp outputs. These are a *different* address space from the input
channels above (see "Buses vs. channels" below); use either the numeric
bus id or its name:

```
python3 -m antelope.cli --profile profiles/orion_studio_3.json bus-status
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-bus-level monitor_a 60
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-bus-dim mona on
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-bus-mute hp1 on
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-bus-mono hp2 off
```

### Device-global settings

```
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-brightness 75    # front-panel screen, 0-100
python3 -m antelope.cli --profile profiles/orion_studio_3.json sample-rate           # show current rate
python3 -m antelope.cli --profile profiles/orion_studio_3.json set-sample-rate 96k   # 32k/44.1k/48k/88.2k/96k/176.4k/192k
```

- **Screen brightness** only works when the device talks to a native
  host -- a VM Launcher no-ops the same slider (see the section further
  down).
- **`set-sample-rate` is disruptive**: the device drops audio and
  re-locks its clock (~1 s), and the readback lags the command by about
  that long. If a DAW or the OS audio engine is holding the stream open
  it may refuse or immediately revert -- change it with nothing
  streaming, then confirm with `sample-rate`.

### Routing matrix (EXPERIMENTAL)

The routing frame (opcode `0x53`) is decoded: after the destination byte
it's a plain array of `(source_bank, source_index)` pairs, **one per
output channel of that destination**, all sent every time. There is **no
device readback**, so `route` resends the channels it isn't changing from
a local cache. Wired destinations: **line out** (16 channels), **HP1,
HP2, Monitor A, Monitor B, Reamp** (2). All wired destinations are
hardware-verified (round-tripped against a real Orion Studio III --
including the 16-channel line out); still worth verifying in the Launcher.

```
python3 -m antelope.cli ... route hp1 all preamp3 preamp4    # set every channel (seeds the cache)
python3 -m antelope.cli ... route lineout all compplay1..16  # range shorthand for a 16-ch seed
python3 -m antelope.cli ... route hp1 R preamp7              # change one channel, keep the rest
python3 -m antelope.cli ... route lineout 3 afx5             # line-out channel 3 <- AFX 5
python3 -m antelope.cli ... route lineout 4 mix2R            # <- virtual mix 2, right
python3 -m antelope.cli ... route hp2 mute                   # mute every channel
python3 -m antelope.cli ... route lineout 6 mute             # mute one channel
python3 -m antelope.cli ... matrix-status                    # what THIS CLI has routed
```

- **Channel selector:** 1-based (`route lineout 3 ...`). `L`/`R` = 1/2 for
  the true stereo destinations (HP1/HP2/Mon A/Mon B) -- **not** Reamp,
  whose two outs are separate mono (`route reamp 1` / `route reamp 2`).
- **Source spec:** `preampN` (1-12), `emumicN` (mic-modeled preamp,
  numbered **5-12** by preamp like the Launcher), `compplayN` (Computer
  Playback; `playbackN` alias), `adatN` (1-16), `afxN` (1-32),
  `surroundN` (1-16), `spdifL/R`, `mix1L`…`mix4R`, `oscN` (1-2), `mute`,
  or `keep`.
- **No un-route** -- same as the Antelope Launcher: you replace a
  channel's source or set it to `mute`; there is no "empty" state.
- **Seed before per-channel edits.** A per-channel `route` needs every
  *other* channel already in this CLI's cache (there's no readback to look
  them up). `route <dest> all <s1> <s2> …` sets and caches the whole group
  in one shot -- seed it to match what the Launcher currently shows. In
  `all`, a range token like `compplay1..16` (or `compplay1-16`, and
  descending: `adat16..1`) expands to that many sequential sources, so a
  16-channel seed is one line.
- **`matrix-status` is a local cache**, not a device readback -- it only
  shows what `route` sent from this CLI, and goes stale if routing is
  changed anywhere else. This is a **device limitation, not a missing
  feature**: the HID interface has no readable report for routing (report
  descriptor declares only a streaming Input + Output report, no Feature
  report; the device rejects every control-pipe `GET_REPORT` -- see
  `tools/hid_probe.py`), routing is in none of the `0x73`/`0x74` reports,
  and loading a preset in the Launcher is a pure one-way push. The
  Antelope Launcher itself holds session state client-side the same way.
  (One check outstanding: a route changed from the device's front panel,
  read by a fresh offline Launcher -- see `PROTOCOL.md` §7.)
- ADAT out, com rec, AFX in, the mix channels and surround in use the
  **same** frame; their channel counts aren't captured yet, so they're not
  wired into the CLI.

See `PROTOCOL.md` §7 and `frame.routing_command` in the profile.

### Virtual mixer -- Mix 1-4 (decoded, not in the CLI yet)

The **Mix windows** are a separate UI from the routing matrix -- mixing
happens there, and each mix's L/R then shows up as a *source* in the
matrix (`mix1L` … `mix4R`). Decoded 2026-08 from
`macos-mix1-send-pan-fader-mute-solo-link` (opcode `0x17` / param `0xd4`):

- one frame per `(mix 0-3, channel 1-32)` strip, carrying **fader**
  (0 dB … −90 dB), **pan** (−30 … +30, centre `0x20`), **mute** (`[21]`
  bit 6), **solo** (`[21]` bit 7), and **send** (0 … 96, 96 = 0 dB).
- soloing a channel makes the Launcher re-send all 32 strips (that's how
  we know each mix has 32 inputs).
- **mix channel link** = `SET_LINK` with a new `space` byte `0x03`
  (0 = physical/ADAT, 1 = S/PDIF, 3 = mixer); software-mirrored.
- no `0x73` readback (like routing).

`protocol.build_mix_command(profile, mix, channel, fader, pan_deg, send,
mute, solo)` builds the frame. No CLI command yet. See `PROTOCOL.md` §12
and `frame.mix_command`.

### Mic modeling / emuMic (decoded, not in the CLI yet)

The front-panel **EMU** button on **preamps 7-12** runs Antelope's
mic-emulation DSP (for their Edge Solo / Edge Duo / Edge Note modelling
mics). Same opcode `0x17` as the mixer -- `[16]` is `0xe5` instead of
`0xd4`. Decoded 2026-08-31: per preamp, an **enable** bit, a **model id**
(`0` = EdgeDuo / raw, `1`…`18` = emulations), a **channel-order swap**
switch, and a **polar pattern** -- with model `0` a free 0-100 morph
(omni → cardioid → figure-8), with a selected model the model's
pattern-class (fixed / 3-way / variable). Enabling also auto-turns on
48 V phantom and links the preamp pair. No readback. The modeled signal
appears as routing source bank `0x01` (`emumicN`, N = preamp 5-12).

`protocol.build_micmodeling_command(profile, channel, enabled, pattern,
swap, model)` builds the frame. The model list is **account-bound** (Edge
mics + model packs activate against an Antelope account), so it lives in
`profiles/mic_models.json` as one account's snapshot -- a client should
let the user pick by name. Not in the CLI yet.

**AuraVerb** (the bundled reverb on the Mix 1 window) has its own frame
-- opcode `0x1d` / param `0xda`. Fully decoded (2026-08-31): byte 28 =
on/off, plus 8 DSP controls, each a plain 0-100 byte -- Room Size (@19),
Color (@20), Pre-Delay (@21, 0-100 → 0-32 ms), Early Reflection Gain
(@23), Late Reflection Delay (@24), Richness (@25), Reverb Time (@26),
Reverb Level (@27). AuraVerb is bundled with the device (no per-plugin
activation), so it's in scope. No device readback, so the CLI caches
what it sent:

```
antelope-ctl ... auraverb                          # show CLI-cached state
antelope-ctl ... auraverb --on                      # enable
antelope-ctl ... auraverb --reverb-time 55 --color 40 --room-size 70
antelope-ctl ... auraverb --off --defaults          # reset params, disable
```

`protocol.build_auraverb_command(profile, params, enabled)`. See
`PROTOCOL.md` §12 and `frame.auraverb_command`. Not hardware round-trip
tested yet.

### Buses vs. channels

The SET_PARAM command frame has one byte (`channel_offset`) that means
different things depending on which param you're setting:

- For `gain` / `input_mode` / `phantom` / `phase_invert`, it's a physical
  input index, 0-11.
- For `bus_level` / `bus_dim` / `bus_mute` / `bus_mono`, it's an output
  **bus id** instead. All 6 are now identified (2026-08): `0`=monitor A,
  `1`=headphone 1, `2`=headphone 2, `3`=line out, `4`=reamp, `5`=monitor B.
  Ids 3/4 turned out to be the settings-tab Line and Reamp output levels
  (not the headphone-3/4 that was previously guessed). `bus_dim`/`bus_mono`
  weren't exercised on 3/4 and may not apply to a line/reamp out;
  `bus_mute` is confirmed on 3 only. The Orion III has **two** physical
  reamp outputs (Reamp 1 / Reamp 2 -- separate mono outs for two guitar
  amps); bus 4 is one shared "Reamp" level slider, whether Reamp 1/2 have
  independent levels is untested.

Don't mix the two up -- `set-gain 5 10` and `set-bus-level 5 60` both use
"5" but mean completely different things (physical channel 6 vs. Monitor B).

**Reading `bus_mute` back:** the bus status byte's `0x04` bit is set both
by an explicit mute *and* whenever that bus sits at `bus_level == 96` (max)
-- reproduced on buses 0, 3 and 4. A bus-status reader must check the
level: at 96, `0x04` means "at max", not necessarily muted.

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
   revealed that shift, only the outgoing command bytes did. Talkback
   (2026-08) turned up a *third* opcode, `0x12` (`frame.global_command`):
   same header as SET_PARAM but for device-global params with no target,
   so the value byte sits at offset **17** (where SET_PARAM keeps its
   channel byte) and offset 18 is unused. `talkback_button` / `_source` /
   `_gain` all use it; `talkback_dest_assign` uses the ordinary `0x13`
   because it *does* take a target. Moral: check the opcode first, then
   figure out where the payload bytes actually are for that opcode.
5. Add an entry to `profiles/orion_studio_3.json` under `"params"` with
   `"status": "unconfirmed"` and your candidate offset/id in `"notes"`.
6. If it looks like the existing SET_PARAM(param_id, channel, value) shape,
   test it deliberately with the CLI's escape hatch:
   ```
   python3 -m antelope.cli --profile profiles/orion_studio_3.json raw-set 0 0x53 10
   ```
   and confirm via another capture that *only* the expected offset moved,
   across a few different values, before calling it confirmed. `raw-set`
   enforces `profile["constraints"]` (target must be a valid index in some
   address space) and prints a hazard note for an unmapped `param_id` --
   `--force` bypasses the bound. Never sweep opcodes or feed it values from
   an untrusted source: on the sibling Discrete 8 Pro, opcodes `0x01`/`0x02`
   and out-of-range indices wedged/BusFaulted the unit (see
   `profile["hazards"]` and `PROTOCOL.md` §14).
7. **Don't assume a new feature fits the SET_PARAM shape.** Seven opcodes
   are known now (`0x12`/`0x13`/`0x14`/`0x17`/`0x1d`/`0x53`/`0xab`), each with its own
   frame block under `"frame"` and its own `build_*_command()` in
   `protocol.py`. Routing (`0x53` / `frame.routing_command`) is the worked
   example: a distinct opcode whose payload is an array of `(bank, index)`
   pairs (one per output channel of the destination), not a fixed field --
   and the first read of it (op bytes `02 01` / `00 02`) was *wrong* until
   a single-variable capture (`macos-matrix-ch1-12-mute-hp1L`/`-hp1R`)
   showed `00 02` was just the other channel's untouched routing. Confirm
   the shape from a capture that changes ONE thing; add a new `"frame"`
   block and builder rather than bending an existing one.
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
  `bus_block` in the state report (see `bus-status`). **Update (2026-08):**
  bus ids `3` and `4` are the settings-tab **Line** and **Reamp** output
  levels -- confirmed in `settings-linevol-mute-reampvol-toggle` via full
  `bus_level` sweeps (readback offsets 37 and 40) plus a `bus_mute` toggle
  on bus 3. All 6 bus slots are now identified; see "Buses vs. channels".
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

  **Re-verified independently (2026-08) against the raw
  `all_reports_ch-link-gain-ph-inv-test.tsv`**: every report in that capture
  has first byte `0x70`, `0x73`, or `0x75` -- no other magic byte shows up
  anywhere in the session, so there's no hidden fourth report type carrying
  a link flag either. The capture toggled pair 0 (ch1&ch2) on/off/on/off
  (4 `0x70`/`0x14`/`0xa2` frames, pair_index always `0x00`); diffing the
  `0x73` state report from immediately before to immediately after each of
  those 4 commands shows **zero changed bytes** every time -- consistent
  with (not just "not yet found", but actively re-confirmed for this
  session's pair-0 toggles) there being no readback bit. Separately, the
  live gain-mirroring behavior itself is real and fast: sweeping ch0's gain
  while linked produces a matching ch1 state-report update about 8ms later,
  in lockstep, for the whole sweep -- this is what `set-link`'s new
  before/after check (below) leans on.

  **`set-link` now does an indirect confirmation.** Since there's no direct
  readback, `set-link ... on` snapshots gain/phantom/phase_invert for both
  channels in the pair before and after sending the command. If they
  disagreed before and agree after, that's real (if indirect) evidence the
  link engaged, grounded in the confirmed mirroring behavior above -- not a
  guess. If they already agreed before (nothing to observe changing), or
  still disagree after, the CLI says so plainly instead of claiming
  confirmation it doesn't have. `set-link ... off` still can't be confirmed
  this way (disengaging has no known observable effect on its own).

  **`status` now shows a link indicator**, e.g.:
  ```
   0  mic     0dB   on   off -.
   1  mic     0dB   on   off -'   (linked, pair 0 -- CLI-tracked, not device-confirmed)
  ```
  This is **not a device readback** -- there isn't one. It's a small local
  cache (`~/.cache/antelope-ctl/link_state_<vid>_<pid>.json`) of the last
  `set-link` command *this CLI* has sent for each pair. It will go stale if
  link state changes some other way (the official Launcher, another
  instance of this tool, or the device losing/regaining power) -- `status`
  prints a note to that effect whenever it has anything cached. Treat the
  markers as "what I last told the device", not "what the device currently
  is".

  **Channel link is real, but the syncing you see isn't the device doing
  it (confirmed 2026-08, real hardware).** Using an earlier version of this
  CLI to send only the raw SET_LINK frame did engage a real link flag --
  visible on the Orion's own front-panel control, so the hardware itself
  really is tracking "linked" -- but each channel kept whatever mode/gain it
  already had. Linking ch1 (mic, 20dB) and ch2 (line, 10dB) through the
  Launcher app snaps ch2 to mic/20dB immediately; doing the exact same
  SET_LINK frame from the CLI alone did not. Re-examining the outgoing
  frames in `all_reports_ch-link-gain-ph-inv-test.tsv` explains why: every
  gain change made while linked in that capture shows **two separate**
  outgoing `SET_PARAM(gain=0x50, channel, value)` frames (channel 0, then
  channel 1, ~2ms apart, identical value) -- not one command with an
  observed two-channel effect. The "live sync" documented above is the
  Launcher software choosing to send two commands every time, not the
  device firmware fanning one write out to both channels. **Cleanest
  proof (user, 2026-08):** turning the *physical gain wheel* on a linked
  channel moves only that channel -- the wheel bypasses all host software,
  so the device plainly has no link-propagation logic, and the Launcher
  only mirrors changes it makes in its own UI. `profiles/orion_studio_3.json`'s
  `params.channel_link.side_effects` and `.live_sync_while_linked` notes
  have been updated to say this plainly, so nobody re-discovers it as a
  "CLI bug" later.

  **`cli.py` now replicates the Launcher's behavior itself:**
  - `set-link ... on` immediately pushes the higher-numbered channel's
    mode/gain/phantom/phase_invert to match the lower one's (only sending a
    command for fields that actually differ, mode-before-gain-before-phantom
    to respect real constraints -- see `_push_full_sync`).
  - From then on, for as long as this CLI's local cache says the pair is
    linked, `set-gain`/`set-phantom`/`set-invert` on either channel also
    sends the same command to its partner (mirroring what the Launcher's
    two-frames-per-change behavior does). `set-mode` on a linked channel is
    refused (`--force` to override) -- mode genuinely can't be changed on a
    linked pair on real hardware; the confirmed workflow is still unlink ->
    set mode independently -> re-link.
  - This mirroring is driven entirely by the **local cache**, not a device
    fact. If you link a pair through the official Launcher instead of this
    CLI, this CLI won't know and won't mirror -- use the new
    `mark-link <channel> on/off` command to tell it (updates only the
    cache, sends nothing to the device) so `set-gain`/etc. mirror correctly
    afterward.
- **Resolved (2026-08):** the "unexplained" `mute` status bit that flipped
  on by itself when `bus_level` hit 96 in the monitor-A capture is real and
  reproducible -- `settings-linevol-mute-reampvol-toggle` sweeps buses 3
  and 4 to max repeatedly and the `0x04` bit tracks `level == 96` exactly,
  every pass. So the bit means "muted **or** at max level"; a bus-status
  reader must special-case `level == 96`. See `params.bus_mute` and
  `unresolved_state_offsets` in the profile.
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
- **Open question, partly answered (2026-08, raw pcapng).** The
  physical-pair-0-ON frame (`ch-link-on-off.pcapng`) and the
  ADAT-pair-0-ON frame (`ADAT-link1-2-7-8.pcapng`) were compared
  byte-for-byte across **all 320 bytes plus the USB metadata** (endpoint
  `0x01`, device address 2, interface, direction): **zero differences.**
  So `SET_LINK(pair_index, enabled)` is genuinely ambiguous at the wire
  level -- there is no disambiguating byte or USB field, confirmed. What's
  still unknown: whether one command links pair N in **both** the physical
  and ADAT spaces at once (the Launcher just sending gain/mode sync for
  whichever you're looking at). The two captures couldn't show this
  because both channels of each pair already had equal gain. To settle it:
  link a physical pair and an ADAT pair in one session with *different*
  gains per channel, or test on hardware. Until then, if the CLI ever
  sends `SET_LINK` it should assume it may affect both spaces.

### Talkback (confirmed, 2026-08 -- not yet in the CLI)

Three captures (`talkback-bttn`, `talkback-select`, `talkback-gain-int-ch1-2-12`)
pinned down the whole talkback feature. It is **protocol-confirmed but
deliberately not wired into `cli.py` yet** (protocol-first; add commands
later if wanted). Full details in `profiles/orion_studio_3.json` --
`frame.global_command`, `state_report.talkback_block`, and the four
`talkback_*` params. Summary:

| Control | opcode / param | payload | readback (0x73 report) |
|---|---|---|---|
| Talkback button (hold-to-talk) | `0x12` / `0x1f` | value@17: 1=press, 0=release | offset 73, bit 6 (`0x40`) |
| Talkback source | `0x12` / `0x27` | index@17: **0 = INT** (built-in talkback mic, the one behind the unit's physical TB button), **1-12 = preamps 1-12** | offset 73, **bits 0-1 only** (`source & 3`) |
| Talkback gain (per source) | `0x12` / `0x20` | value@17: 0-96 (same scale as `bus_level`) | offset 74 (selected source's gain) |
| Talkback destination assign | `0x13` / `0x5d` | dest 0-3 @17, on/off @18 | offset 73, bits 2-5 (dest N = bit N+2) |

Key takeaways:

- **New opcode `0x12` (`global_command`)** -- for global params with no
  target; value goes at offset 17, not 18. See "Adding a new param" above.
- **Talkback gain is per-source.** Select a source, then set its gain;
  offset 74 always shows the *currently selected* source's value.
- **Source readback is incomplete** -- only the low 2 bits of the source
  index appear (offset 73 bits 0-1). Track the full 0-12 value client-side.
- **Untested overlap:** offset-73 bits 2-3 are shared between the source
  index (values 4-12) and the dest-assign bitmask (dest0/dest1). The three
  captures never set a high source index and a destination at the same
  time, so how the packed byte behaves with talkback fully configured is
  still unverified -- one combined capture would close this.
- **Destinations = Monitor A / Monitor B / HP1 / HP2** (user-confirmed),
  four toggle buttons in the Monitors/Headphones menu -- **not** routing-
  matrix sources. They **combine**: talkback can go to all four at once
  (the bitmask holds multiple bits). Exact index→name order (0-3) isn't
  pinned down; likely 0=Mon A, 1=Mon B, 2=HP1, 3=HP2.

### Output trim (confirmed, 2026-08 -- not yet in the CLI)

`settings-trim-mona-monb-line-panlaw` pinned down the settings-tab output
**trim** selectors: `SET_PARAM(0x4b, target, value)`, `target` 0/1/2,
`value` a 7-position selector (0-6). Readback is packed into two bytes just
before `bus_block`: target 0 at offset 24 (`value << 4`), target 1 at
offset 25 bits 2-4 (`value << 2`), target 2 at offset 25 bits 5-7
(`value << 5`). Targets 0/1/2 are almost certainly Monitor A / Monitor B /
Line output trim (capture-order inference). See `params.output_trim` and
`state_report.output_trim_block`.

- What the 7 steps *mean* physically (dB? reference level?) isn't in the
  capture -- only the raw index.
- **Pan law was not actually captured** despite the filename -- no 4th
  target or other param_id was ever sent. The readback block has spare
  bits (offset 25 bits 0-1 = a 2-bit / 4-option field) that could hold it.
  Needs its own capture.

### Screen brightness -- CONFIRMED, real device command (2026-08, native macOS)

The VM capture showed nothing for the brightness slider, which had it
filed as host-side. **Wrong -- the VM Launcher just no-ops the slider.**
Recaptured on native macOS (`macos-scrbrght-0-100-50-multvalue`) with the
device's physical screen visibly changing:

- **Command:** opcode `0x12` (global), param `0x0e`, value **0-100**
  (`0x00`-`0x64`) at payload offset 17.
- **Readback:** `0x73` state report **offset 26** = the value, exactly,
  on all 25 commands.
- **CLI:** `set-brightness <0-100>` (via `protocol.build_global_command`,
  the first SET_GLOBAL builder -- talkback params can use it next).
  Hardware-confirmed: the CLI command changes the device's physical
  screen. See `params.screen_brightness`.

**Lesson:** "zero frames under the VM" ≠ host-side. The VM Launcher
silently drops some controls. Re-check on native macOS before concluding.

### Sample rate -- CONFIRMED (2026-08, native macOS)

`macos-smplrt-32k-44k1-48-88k2-96k-176k4-192k`: stepping every rate sent
opcode `0x12` (global), param `0x03`, an **index 0-6** at offset 17
(0 = 32000, 1 = 44100, 2 = 48000, 3 = 88200, 4 = 96000, 5 = 176400,
6 = 192000). Readback is `0x73` **offset 18**, tracking ~1 s behind each
command (clock re-lock). CLI: `sample-rate` / `set-sample-rate <hz>`
(`params.sample_rate`). Not hardware round-trip tested. Offsets 21-23 & 27
also move but only at the 88.2k / 176.4k steps -- undecoded clock/PLL
state.

### Oscillator, thunderbolt -- resolved as host-side (2026-08)

- **Oscillator / test-tone generator** -- the *settings-tab panel*
  (freq / level / mute) sends **zero** outgoing frames. But there are two
  oscillators and the way you actually use them is a right-click in the
  routing matrix ("insert oscillator into this output") -- and *that*
  **is** a real device command: the `0x53` routing frame with source bank
  `0x0c` (see `params.routing` / `params.oscillator`). So only the
  per-signal parameters are host-side; the insert isn't. (Worth a
  native-macOS recheck too, given the brightness lesson above.)
- **Thunderbolt / latency / DC-coupling** -- also zero outgoing frames.
  Host driver settings, or not exercised in the capture.
- **Surround-EQ pre/post** -- the one thing here that *does* talk to the
  device: 2 frames of a **new opcode `0xab` / param `0xeb`**, differing
  only in bit 7 of payload byte @19. No `0x73` effect. Too few frames to
  decode the frame layout -- needs a dedicated capture. See
  `params.surround_eq`.

### Connect handshake & routing readback -- resolved (2026-08, native macOS)

Four native-macOS captures of the Launcher connecting to the device
(`captures/macos-captures/macos-antelopeINIT-*`): device powered fully
off, Launcher quit, start recording, launch Launcher, power device on.
Two of them (`...poweroff-on2-itsavedstate`, `...poweroff-on3-itsavedstate`)
were recorded with **deliberately different LineOut routing** -- preamp
1-12 vs computer-playback, swapped between the two.

- **The whole host->device connect handshake is one frame:**
  `SET_PARAM(param 0x49, channel 1, value 0)`. Present in all four macOS
  captures *and* in the older Windows `AntelopeINIT.tsv` -- cross-platform
  confirmed. The device replies with the `0x74` topology enumeration
  burst and normal `0x73`/`0x75` polling. In `on2` the Launcher also sent
  a short `SET_PARAM(gain 0x50)` sequence -- the user nudging gain sliders
  to force the buggy Launcher to flush state, not handshake or device
  behaviour.
- **The routing readback is not at connect** (but it exists -- see the
  cross-machine evidence under "Routing matrix" above). Diffing the on2
  vs on3 connect sequences byte-for-byte: the `0x74` enumeration is
  identical, the USB descriptors are identical, the final `0x73` state
  report differs only in one preamp-gain byte and meter noise, and there
  is no `0x53` frame in either direction. So the readback fires later --
  prime suspect: opening the routing-matrix *tab* (these captures only
  watched the connect).
- **macOS capture format:** Darwin "XHC" pcapng wraps each 320-byte
  vendor HID report in a 40-byte pseudo-header (`frame.len == 360`);
  payload byte 0 is the usual magic. `tools/scan_capture.py` only reads
  the Windows TSV layout -- use **`tools/scan_macos_capture.py`** for
  these (see `CAPTURING.md`).

### Still unconfirmed

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
