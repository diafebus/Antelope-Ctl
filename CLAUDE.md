Don't over use tokens, throwing agents and using all the resources at once, a good engineer saves resources

**Resuming a session?** Read `SUMMARY.md` first -- it is the cross-session
hand-off (project state, decoded protocol, code state, pending captures).
Update its "Right now" + "Session log" sections at the end of each session.

**Optional endgame:** `KERNEL.md` holds a plan for a possible mainline
`snd-usb-audio` mixer driver -- not committed to (Antelope is niche; a
good webUI may be enough). Not to be started before the protocol is
complete + hardware-verified.

## Session hygiene (keeps quota cost down)

Auto-compaction runs against the whole context window and is expensive
(one compact ~= 16% of a 5h quota). Avoid needing it:

- **One focused task per session.** `/clear` between unrelated tasks
  instead of letting context grow until auto-compact fires.
- **Resume by reading `SUMMARY.md` in a fresh session**, not by
  reloading a long transcript. `claude --resume` survives a reboot but
  reloading a big compacted session is the costly path.
- **End every session deliberately:** update `SUMMARY.md` ("Right now" +
  "Session log", keep the log to ~5 entries), commit, exit.
- **Commit findings immediately** after a capture is analyzed -- once
  it's in the docs a lost session costs nothing.
- **Never paste raw captures / hex / tsv dumps into chat** -- give the
  file path. Dumps sit in context permanently.
- **Targeted doc edits, not sweeps.** Name the capture; edit the
  relevant spots in the 4 docs, don't re-read all of them.
- **Big files** (`orion_studio_3.json`, `PROTOCOL.md`, `README.md`) --
  read only the needed sections.
- Routine work doesn't need `/fast` (Opus); Sonnet is fine.
- If a mid-session compact is unavoidable, run `/compact <focus>` early
  (smaller input + output) rather than waiting for the auto trigger.

## TODO / next steps (keep this current)

Raw `.pcapng` files are local under `captures/` (`raw pcapng captures/`,
`matrix-captures/`, and `macos-captures/` -- native-macOS Darwin XHC
captures, 40-byte pseudo-header + 320-byte payload, `frame.len==360`);
`tshark` 4.6.8 is on this machine. Anything needing full frames / both
directions / USB metadata is offline now.

**macOS matrix captures -- WATCH OUT:** most `macos-matrix-*` files
(`compplay*lineout*`, `afx*`, `surrnd*`, `mix1234*`, `ch1-12-mute-hp2LR`)
have **zero OUT frames** -- the user's Wireshark session only caught the
IN endpoint (`20.x.2`). Only `ch1-12-mute-hp1L` and `-hp1R` have the OUT
commands (endpoint `20.x.1`). Any recapture must confirm endpoint .1 is
being logged.

**macOS captures not yet triaged** (`captures/macos-captures/`):
`macos-mix1-send-pan-fader-mute-solo-link`, `macos-smplrt-*` (sample
rate), `macos-auraverb-on-off`, `macos-antelopeINIT-poweron` /
`-poweron1-itresettopreviousstate`
(2 more INIT variants). INIT poweroff-on2/on3 = CAPTURE E, done.

### ROUTING MATRIX -- the active thread

`frame.routing_command`: opcode `0x53` / param `0xd3`. **FRAME MODEL
DECODED (2026-08, `macos-matrix-ch1-12-mute-hp1L`/`-hp1R`):**
`d3 41 <dest> | <bank0> <idx0> | <bank1> <idx1> | ...` -- after byte 18 it's
a plain array of (source_bank, source_index) pairs, one per output channel
of the destination group, from byte 19, stride 2. ch0 = L/out1/Reamp1,
ch1 = R/out2/Reamp2. Multichannel groups just have more pairs. NO op bytes
(the old `02 01`/`00 02` model was a misread of the other channel's
untouched routing -- it caused the L/R swap the user saw). Whole group is
always sent. mute = (bank `0x0b`, idx 0); no "no source". Routing is
EXCLUSIVE per channel. No `0x73` readback / none at connect (CAPTURE E),
but a readback **exists** (cross-machine persistence) -- undecoded, likely
on routing-tab open (CAPTURE E'). Oscillator-insert (bank `0x0c`) goes
through this same frame. Talkback is NOT a matrix source.
CLI: `route <dest> <Lsrc> [<Rsrc>]` (omit R = keep; `route <dest> mute` =
mute all), `matrix-status`. No `unroute` -- the Launcher has no such
concept (replace or mute). Fixed 2026-08.

**Matrix source banks** (byte 19) -- user's full source list:
| source | bank | status |
|---|---|---|
| preamp 1-12 | `0x00` (idx 0-11) | confirmed |
| comp play 1-24 | `0x02` (idx 0-23) | confirmed |
| adat in 1-16 | `0x03` (idx 0-15) | confirmed |
| spdif in L/R | `0x04` (idx 0-1) | confirmed |
| mute (pseudo) | `0x0b` | confirmed |
| oscillator 1/2 | `0x0c` (idx 0-1) | confirmed |
| emumic | ? | **TBD** |
| afx out | ? | **TBD** |
| mix1/2/3/4 L/R | ? | **TBD** (also destinations -- the virtual mixes) |
| surround out | ? | **TBD** |

**Matrix destinations** (byte 18) -- **DONE** (`matrix-compplay-allouts-1`):
`0`=line out, `1`=hp1, `2`=hp2, `3`=mona, `4`=monb, `5`=reamp, `6`=com rec,
`7`=adat out, `8`=spdif out, `9`=afx in, `10`=mix ch1, `11`=mix ch2,
`12`=mix ch3, `13`=mix ch4, `14`=surround in.

**Big complication found:** the routing frame is NOT a simple crosspoint.
Bytes 21+ are a variable-length list dumping the whole destination group's
per-channel routing state (1 entry for hp1/reamp, 15-30 for adat out / mix
channels). Routing an already-present source is idempotent (no frame).

- [x] ~~CAPTURE B -- destination enumeration~~ -- DONE (map above).
- [x] ~~CAPTURE A -- L/R sub-channel + frame model~~ -- **DONE, REVISED
      2026-08** (`macos-matrix-ch1-12-mute-hp1L`/`-hp1R`). NO op bytes:
      after byte 18 the frame is an array of (bank,idx) pairs, one per
      output channel, from byte 19 stride 2. ch0=(19,20), ch1=(21,22).
      The old `02 01`/`00 02` reading was the OTHER channel's untouched
      routing. mute=(0x0b,0). Whole group always sent. CLI fixed.
- [ ] **CAPTURE C -- source-bank enumeration**: route each of emumic /
      afx out / mix1 L / mix1 R / surround out -> a channel, one at a
      time. Maps banks `0x01`, `0x05`-`0x0a`, `0x0d`+. (macOS
      `macos-matrix-afx*` / `-surrnd*` are missing the OUT endpoint --
      need a fresh capture that catches endpoint .1.)
- [ ] **CAPTURE D -- multichannel channel counts**: how many (bank,idx)
      pairs does line out / adat out / mix chN / com rec / afx in carry?
      Change ONE channel of one such group. NOTE: the macOS
      `macos-matrix-compplay*lineout*` / `-mix1234-lineo1-*` /
      `-surrnd*` files ALL have zero OUT frames (only endpoint .2 was
      captured) -- unusable. Need a recapture on the endpoint the OUT
      commands actually use (see `macos-matrix-ch1-12-mute-hp1L` for the
      working setup).
- [ ] **CAPTURE E' -- routing readback on TAB open**: with the Launcher
      already connected, capture (both dirs, no size filter) while
      clicking into the routing-matrix tab. Do it with two different
      routings and diff. This is the last place a device-side routing
      readback could live -- connect-time is ruled out (CAPTURE E).
- [x] ~~**CAPTURE E -- routing readback via fresh Launcher INIT**~~ --
      **DONE (2026-08, native macOS).** `macos-antelopeINIT-poweroff-on2/on3-itsavedstate.pcapng`:
      cold boot, Launcher quit, record, launch Launcher, power device on;
      on2 vs on3 had swapped LineOut routing (preamp1-12 vs compplay).
      RESULT: **no routing readback in the connect sequence.** 0x74
      identical (all 209 frames, bytes 0-15 only), USB descriptors
      identical, 0x73 differs only in a preamp-gain byte + meter noise,
      no 0x53 either direction. Entire connect handshake = one frame
      `SET_PARAM(param 0x49, ch 1, val 0)` (matches Windows AntelopeINIT).
      BUT a routing readback **must exist** -- user changed routing on
      Windows VM, moved to macOS, macOS Launcher showed the NEW routing
      (host cache can't cross machines). So it fires LATER, undecoded.
      -> CAPTURE E'. See `params.routing.readback`, PROTOCOL.md §4/§7.
- [x] ~~**wire `route` / `matrix-status`**~~ -- **DONE, then REWRITTEN
      2026-08** after the model revision. `build_route_command(profile,
      dest, channels)` takes an ordered (bank,idx) list for the whole
      group. CLI: `route <dest> <Lsrc> [<Rsrc>]` (omit/`keep` R = keep;
      `route <dest> mute` = mute all), `matrix-status` (per-channel
      cache). NO `unroute` (Launcher has no un-route -- replace or mute;
      user-noted). Only hp1/hp2/mona/monb/reamp. Frame builds verified
      byte-exact against the hp1L/hp1R captures.
      **STILL NOT round-trip tested against hardware** -- user to test:
      `antelope-ctl route hp1 preamp3 preamp4` then check the Launcher
      (should show HP1 L=preamp3, R=preamp4 -- the old code swapped them).

### Out of scope (deliberate)

**AFX / Synergy Core effects** -- the on-DSP plugin chain. Skipped on
purpose: plugins are per-user licensed with online activation, so
touching that path drags in authentication/licensing concerns we want
nothing to do with. Focus is the mixer/routing/preamp feature set needed
for professional tracking + monitoring. Revisit only if a clean,
license-free "is effect slot N bypassed" style control shows up.

### Other captures to record (hardware)

Consider **native macOS** (CAPTURING.md). **LESSON (2026-08): the VM
Launcher silently no-ops some controls -- "zero frames under the VM" does
NOT mean host-side.** Screen brightness proved this: nothing under the VM,
full command on native macOS. Re-check oscillator / thunderbolt / DC-coup
on native macOS before trusting the "host-side" verdicts.

- [x] ~~**Screen brightness on macOS**~~ -- **DONE (2026-08).**
      `macos-scrbrght-0-100-50-multvalue`: opcode `0x12` / param `0x0e` /
      value 0-100 at offset 17; readback `0x73` offset 26 (1:1, 25/25).
      `params.screen_brightness` + `state_report.screen_brightness_byte_offset`.
      TODO: wire into CLI once `build_global_command` exists.
- [ ] **Surround-EQ pre/post** -- opcode `0xab` / param `0xeb`, only 2
      frames so far. Toggle several times to decode. (macOS)
- [ ] **Pan law** -- trim capture never sent it. Move only pan-law; watch
      `state_report` offset 25 bits 0-1.
- [ ] **DC-coupling** -- `thunderb-lat-dccp` sent nothing; isolate it.
- [ ] **String descriptors** -- fresh connect, no size filter -> `0x74` names.
- [ ] **ADAT + physical link in ONE session, different per-channel gains**
      -- does `SET_LINK(space=0, pair N)` link both spaces?
- [ ] **channel_link readback** (low priority) -- 6-pair on/off diff.

### Analyze offline (lower priority)
- [ ] Cross-check the `0x73` embedded meter block (157-232) against `0x75`
      channel meters (32-43) frame-by-frame -- would collapse part of
      `unresolved_state_offsets` to "redundant meter copy".

### Code work (deferred on purpose -- protocol first)
- [x] ~~ADAT gain + link CLI~~ -- **DONE (2026-08).** `adat-status`,
      `set-adat-gain`, `set-adat-link`, `mark-adat-link`. Gain mirrors to
      the linked partner software-side, exactly like `set-gain`/`set-link`
      (user-confirmed ADAT link behaves like the preamp link). Separate
      link cache (`kind='adat'`). `set-adat-link` warns that pairs 0-5 may
      also toggle the physical link (identical frame).
- [x] ~~**Enforce `constraints` / `hazards`**~~ -- **DONE (2026-08).**
      `protocol.py` has `check_target` / `check_enum` / `check_opcode`
      (profile-driven, raise `ConstraintError`). Wired into `set-mode`
      (channel + input_mode enum), `set-gain` / `set-phantom` / `set-invert`
      (channel), `set-adat-gain` (adat), `set-bus-level` / `set-bus-*`
      (bus id), and `raw-set` (target must be valid in some space + hazard
      note for unmapped param_id). `build_command` / `build_link_command`
      assert the opcode isn't forbidden. `--force` overrides every bound.
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
| `0x11` | 2  | **S/PDIF** (stereo L/R) -- confirmed; gain param `0x5c`, link space byte `0x01` (`spdif-gain-link`, 2026-08) |
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
  params `talkback_button` (`0x1f`), `talkback_source` (`0x27`, 0=INT
  built-in mic / 1-12=preamps 1-12, user-confirmed), `talkback_gain`
  (`0x20`, per-source, 0-96),
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
- ~~`macos-scrbrght-0-100-50-multvalue`~~ -- **DONE (2026-08, native macOS).**
  Screen brightness: opcode `0x12` / param `0x0e` / value 0-100 at
  offset 17; `0x73` readback offset 26 (1:1, 25/25 commands). VM showed
  nothing because the VM Launcher no-ops the slider. `params.screen_brightness`.
- **Routing** (`matrix-*` captures) -- **frame model decoded** for
  2-channel destinations, active thread. Opcode `0x53`/`0xd3`; byte 18 =
  destination group (full 0-14 map confirmed); from byte 19, an array of
  (bank,idx) pairs, stride 2, one per output channel of the group. Whole
  group always sent. mute=(0x0b,0). Exclusive per channel. CLI rewritten
  (`route <dest> <L> <R>`). Multichannel channel counts + true readback
  still open (readback exists per cross-machine persistence -> E'). See
  `frame.routing_command` + `params.routing`.
