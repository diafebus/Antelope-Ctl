Don't over use tokens, throwing agents and using all the resources at once, a good engineer saves resources

## TODO / next steps (keep this current)

**The raw `.pcapng` files are now local** at
`captures/raw pcapng captures/` (21 files, ~25 MB each), and `tshark`
4.6.8 is on this machine -- so anything needing full frames / both
directions / USB metadata can be done offline now, no VM round-trip.

### Analyze now -- offline
- [ ] `matrixtest-pre1-cmpplay1-2` -- routing. Opcode `0x53` / param `0xd3`.
      Only 4 command frames (`@17..21` = `41 01 00 00 02` on one). Decode
      what you can from the raw pcapng; probably still needs a fuller
      capture to finish.
- [x] ~~`settigs-thunderb-lat-dccp`~~ -- **DONE.** Zero outgoing frames on
      the HID endpoint. Host-side driver settings, or not exercised.
- [ ] Cross-check the `0x73` embedded meter block (offsets 157-232) against
      the `0x75` channel meters (offsets 32-43) frame-by-frame in a
      signal-carrying capture -- would collapse a chunk of
      `unresolved_state_offsets` to "redundant meter copy".
- [x] ~~Map the `0x74` enumeration groups~~ -- structure + counts in
      `PROTOCOL.md` §4. **Names are in NO capture on file** (checked all 21
      pcapng: not one string-descriptor fetch; UAC2 desc is a nameless
      stub). `0x19`=64 ≈ USB/TB channel stream. To name the rest: fresh
      string-descriptor capture, or read the Launcher routing-tab labels.
- [x] ~~Oscillator command~~ -- **DONE. Host-side only.** Zero outgoing
      frames in the whole osc pcapng. Not a device feature.
- [x] ~~ADAT vs physical `SET_LINK` byte compare~~ -- **DONE.** Byte-for-byte
      identical across all 320 bytes + USB metadata. Residual open question
      (does one command link both spaces?) moved to hardware-test list.

### Captures to record (need hardware)

**Strongly consider capturing on native macOS** (see CAPTURING.md) -- some
Launcher features do nothing under the VM (screen brightness confirmed).
A macOS capture would re-validate the "host-side" findings (oscillator,
brightness, thunderbolt) against a build where everything works. Settings-
window scorecard: PROTOCOL.md section 11.

- [ ] **Screen brightness on macOS** -- works there, sends nothing under
      the VM. Capture on macOS, no size filter, to see if it's a real
      device command (and what opcode).
- [ ] **Surround-EQ pre/post** -- new opcode `0xab` / param `0xeb` seen
      (only 2 frames). Toggle several times to decode the `0xab` layout.
- [ ] **Pan law** -- the trim capture never sent it. Move only the pan-law
      selector; watch `state_report` offset 25 bits 0-1 (spare 2-bit field).
- [ ] **S/PDIF** gain + link -- expected to mirror ADAT (gain via `0x13`,
      link via `0x14`/`0xa2`); confirm the param_id, don't assume `0x5b`.
- [ ] **DC-coupling** -- `thunderb-lat-dccp` sent nothing. Isolate the
      DC-coupling toggle (it should be hardware); maybe TB-gated.
- [ ] **String descriptors** -- fresh connect capture (remove device in
      Device Manager / re-plug on macOS), no size filter -> names for the
      `0x74` categories.
- [ ] **ADAT + physical link in ONE session, different per-channel gains**
      -- to see whether `SET_LINK(pair N)` links both spaces at once.
- [ ] **Routing matrix** -- systematic source x destination changes to
      decode the `0x53`/`0xd3` payload.
- [ ] **channel_link readback** (low priority) -- dedicated 6-pair on/off
      diff to confirm there's no readback bit.

### Code work (deferred on purpose -- protocol first)
- [x] ~~ADAT gain + link CLI~~ -- **DONE (2026-08).** `adat-status`,
      `set-adat-gain`, `set-adat-link`, `mark-adat-link`. Gain mirrors to
      the linked partner software-side, exactly like `set-gain`/`set-link`
      (user-confirmed ADAT link behaves like the preamp link). Separate
      link cache (`kind='adat'`). `set-adat-link` warns that pairs 0-5 may
      also toggle the physical link (identical frame).
- [ ] **Enforce `constraints` / `hazards`** (added to the profile 2026-08
      from the Discrete 8 Pro peer PR). `raw-set` sends arbitrary
      param_id + channel with no bounds check; `set-mode`/`set-gain`/etc.
      only *warn* past `confirmed_indices` and send anyway. The sibling
      device BusFaults on an out-of-range channel index and wedges on
      opcodes `0x01`/`0x02` -- Orion should refuse (not clamp) writes
      outside `constraints`, `--force` to override. Read the bounds from
      the profile, don't hardcode.
- [ ] `antelope/protocol.py`: add `build_global_command(profile, param_id, value)`
      (opcode `0x12`, value @17) -- the profile references it already.
- [ ] Decide which confirmed-but-unexposed params get CLI commands:
      talkback (`talkback_*`), line/reamp bus levels (already work via
      `set-bus-level` with bus 3/4), `output_trim`.
- [ ] `bus-status`: special-case `bus_level == 96` so a bus at max volume
      isn't reported as muted (the `0x04` bit is ambiguous).
- [ ] Teach `tools/scan_capture.py` about `0x74` (its known-magic dict is
      hardcoded to `0x70`/`0x73`/`0x75`) so it stops printing UNKNOWN. The
      profile already has `frame.init_enumeration_report`.

## Capture notes

The reverse-engineered wire format is consolidated in **`PROTOCOL.md`**
(reference form); per-capture narrative is in `README.md`; the
machine-readable source of truth is `profiles/orion_studio_3.json`. Keep
all three in sync when a capture is analyzed. This section is just short
pointers to the raw captures.

### settings-osc1-2-fq-lvl (2026-08)

Settings-tab **test-tone generator**: two oscillators, each with a mute
button, a frequency selector (1kHz / 400Hz) and a level selector
(0 / -6 / -12 / -18 dBFS). User exercised the lot (osc1 mute on/pause/off,
osc1 freq, osc1 level, then osc2 the same).

- **No new magic byte.** The whole 27.7s file is `0x73` (state) + `0x75`
  (meter) only.
- **Nothing in either polled report reacts to any oscillator control** --
  every `0x73` transition is already-explained startup ramp (139-140),
  the ~3s init blip (17/19), or free-running meter jitter (157-232, only
  ever wobbling noise-floor values). `0x75` is jitter on the channel-meter
  bytes only.
- **The SET command is unrecoverable from this file** -- the capture is
  inbound-only, not one `0x70` command frame was logged.
- Next step: recapture with tshark logging **both directions + all
  magics**, one control at a time. See `params.oscillator`.

### Magic 0x74 -- device topology enumeration (seen only in all_reports_AntelopeINIT.tsv)

`AntelopeINIT.tsv` = the Launcher being **started with no user
interaction** (user-confirmed) -- pure init observation. So the `0x74`
burst, the lone `SET_PARAM(0x49)` at t=7.7s, and the `0x73` startup noise
(17/19 blip at t~3s, 139/140 ramp) are all the Launcher's automatic
handshake, nothing user-triggered.

113 records; each is `(category_id @8, index @12)` -- **no names** (names
are USB string descriptors = control transfers, not in the HID capture).
Full structure in `PROTOCOL.md` section 4 and `frame.init_enumeration_report`.

| category | count | meaning |
|---|---|---|
| `0x1a` | 16 | **ADAT** -- confirmed |
| `0x11` | 2  | **S/PDIF** (stereo L/R) -- confirmed by elimination; gain+link still need a dedicated capture |
| `0x19` | 64 | unmapped -- **probably the 64-ch USB/Thunderbolt stream** (device's headline I/O count; routing cmd's `0x41`=65 fits a 1-based index into it) |
| `0x03` | 15 | unmapped |
| `0x04` | 4  | unmapped (headphone outs? clock sources? each entry trailed by its own `0x0b` marker) |
| `0x1b`/`0x0a`/`0x15`/`0x16` | 1 each | unmapped single-instance subsystems |
| `0x0b` | 8 | **section/phase marker, not an I/O category** |

To name `0x19`/`0x03`/`0x04`/singletons: capture the USB control transfers
during connect, or match counts to the Launcher routing-tab labels.

**Not a live settings readback** -- indices only, no current values.
Documented in the profile as `frame.init_enumeration_report`.

### Untriaged captures with command frames (in logs and captures/wireshark captures/)

Still to fold into the profile -- all have outgoing `0x70` frames, so they
are analyzable offline right now:

- ~~`talkback-bttn` / `talkback-select` / `talkback-gain-int`~~ -- **DONE
  (2026-08).** Confirmed: new opcode `0x12` (`frame.global_command`),
  params `talkback_button` (`0x1f`), `talkback_source` (`0x27`, 0=internal
  mic / 1-12=input ch), `talkback_gain` (`0x20`, per-source, 0-96),
  `talkback_dest_assign` (opcode `0x13`, `0x5d`, dest 0-3). Readback in
  `state_report.talkback_block` (offsets 73 packed status, 74 gain). See
  README "Talkback" + profile. Not wired into cli.py (protocol-first).
- ~~`settings-linevol-mute-reampvol-toggle`~~ -- **DONE (2026-08).** It was
  `bus_level`/`bus_mute` (`0x47`/`0x48`) all along, on the two previously
  unknown bus ids: **3 = line out, 4 = reamp**. Also reproduced the
  "mute bit sets itself at max level" behavior on buses 3 & 4 (now resolved
  -- `0x04` = muted OR at level 96). All 6 bus slots now identified.
- ~~`settings-trim-mona-monb-line-panlaw`~~ -- **DONE (2026-08).** Output
  trim: `SET_PARAM(0x4b, target 0-2, value 0-6)`, packed readback at
  offsets 24-25 (`state_report.output_trim_block`). Targets 0/1/2 ≈ mona /
  monb / line trim. **Pan law was NOT in the capture** (no 4th target ever
  sent) -- still needs its own capture.
- `matrixtest-pre1-cmpplay1-2` -- routing: opcode `0x53`, param `0xd3`,
  multi-byte payload -- a genuinely different frame shape, confirms the
  profile's `routing` prediction. **Still open -- see TODO above.**
