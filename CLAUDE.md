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

### STATE OF PLAY -- end of the 2026-08 native-macOS session

**Decoded + confirmed this session** (see PROTOCOL.md / profile for
detail): routing frame model (array of (bank,idx) pairs -- old "op bytes"
were a misread) + all source banks except `0x01` + line-out = 16-ch;
screen brightness (`0x12`/`0x0e`, readback @26, hardware-confirmed);
sample rate (`0x12`/`0x03`, index 0-6, readback @18); virtual mixer
(`0x17`/`0xd4` -- fader/pan/send/mute/solo, mix link = SET_LINK space 3);
AuraVerb on/off (`0x1d`/`0xda`, byte 28). CLI: `route` rewritten (numeric
channels), `set-brightness`, `sample-rate` / `set-sample-rate`.

**Half-baked / needs a follow-up capture:**
- **AuraVerb parameters** -- on/off known; frame bytes 17-27 (the DSP
  params) frozen in the only capture. *User's next task.*
- **Mixer CLI** -- `build_mix_command` exists; no `mix-set` command.
- **Multichannel routing dests** -- line-out=16 confirmed; adat out /
  com rec / afx in / mix chN / surround-in channel counts unknown, so
  only line-out + the 2-ch dests are wired.
- **Routing readback** -- exists (cross-machine persistence) but not at
  connect (CAPTURE E) and not decoded -> CAPTURE E' (routing-tab open).
- **Source bank `0x01`** -- last unseen matrix source (emumic?).
- **Clock state @21-23,27** -- moves at 88.2k/176.4k; undecoded.
- **`route` hardware round-trip** -- never tested against real hardware.
- **Surround-EQ `0xab`** -- 2 frames only, layout undecoded.

Full detail + the rest of the backlog is in the subsections below.

---

Raw `.pcapng` files are local under `captures/` (`raw pcapng captures/`,
`matrix-captures/`, and `macos-captures/` -- native-macOS Darwin XHC
captures, 40-byte pseudo-header + 320-byte payload, `frame.len==360`);
`tshark` 4.6.8 is on this machine. Anything needing full frames / both
directions / USB metadata is offline now.

**macOS matrix captures -- WATCH OUT:** `compplay1-12lineout1-12`,
`compplay17-32lineout1-12`, and `ch1-12-mute-hp2LR` have **zero OUT
frames** -- that Wireshark session only caught the IN endpoint (`20.x.2`).
The usable ones (OUT endpoint `20.x.1` present): `ch1-12-mute-hp1L`,
`-hp1R`, `afx1-19-to-line1-afx29to32-to-line1`, `surrnd1-16-to-lineo1`,
`mix1234-lineo1-invphch6`. Any recapture must confirm endpoint .1 is
being logged (`tools/scan_macos_capture.py` prints an `OUT magic 70` line
when a file is usable).

**macOS captures -- all triaged** except `macos-antelopeINIT-poweron` /
`-poweron1-itresettopreviousstate` (2 more INIT variants -- likely nothing
new; poweroff-on2/on3 = CAPTURE E, done).

### ROUTING MATRIX -- the active thread

`frame.routing_command`: opcode `0x53` / param `0xd3`. **FRAME MODEL
DECODED (2026-08, `macos-matrix-ch1-12-mute-hp1L`/`-hp1R`):**
`d3 41 <dest> | <bank0> <idx0> | <bank1> <idx1> | ...` -- after byte 18 it's
a plain array of (source_bank, source_index) pairs, one per output channel
of the destination group, from byte 19, stride 2. NO op bytes (the old
`02 01`/`00 02` model was a misread of the other channel's untouched
routing -- caused the L/R swap the user saw). Whole group always sent.
mute = (bank `0x0b`, idx 0); no "no source". EXCLUSIVE per channel. No
`0x73` readback / none at connect (CAPTURE E), but a readback **exists**
(cross-machine persistence) -- undecoded, likely on routing-tab open
(CAPTURE E'). Oscillator-insert goes through this frame. Talkback is NOT
a matrix source.
CLI: `route <dest> <chan> <source>` (1-based; `L`/`R`=1/2 for the stereo
dests; resends other channels from cache), `route <dest> all <s1>..<sN>`,
`route <dest> mute`, `matrix-status`. No `unroute` (Launcher has none).
Fixed + extended 2026-08.

**Matrix source banks** (byte 19) -- ALL confirmed 2026-08 except `0x01`:
| bank | source | idx |
|---|---|---|
| `0x00` | preamp | 0-11 |
| `0x01` | **UNKNOWN** (emumic?) -- CAPTURE C | ? |
| `0x02` | compplay (Computer Playback) | 0-23 VM / 0-31 macOS |
| `0x03` | adat in | 0-15 |
| `0x04` | spdif in | 0-1 |
| `0x05` | afx out | 0-31 |
| `0x06`-`0x09` | mix 1-4 | 0/1 = L/R |
| `0x0a` | surround out | 0-15 |
| `0x0b` | mute (pseudo) | 0 |
| `0x0c` | oscillator | 0-1 |
(`0x05`-`0x0a` from `macos-matrix-afx1-19*` / `-mix1234-*` / `-surrnd1-16*`.)

**Matrix destinations** (byte 18) -- **DONE** (`matrix-compplay-allouts-1`):
`0`=line out, `1`=hp1, `2`=hp2, `3`=mona, `4`=monb, `5`=reamp, `6`=com rec,
`7`=adat out, `8`=spdif out, `9`=afx in, `10`=mix ch1, `11`=mix ch2,
`12`=mix ch3, `13`=mix ch4, `14`=surround in.

The routing frame is an array of (bank,idx) pairs, one per output channel
of the destination group; the whole group is always sent (see the block
above + `frame.routing_command`). Routing an already-present source is
idempotent (no frame).

### VIRTUAL MIXER -- Mix 1-4 (`0x17` / `0xd4`) -- decoded 2026-08

A 6th opcode. **Separate UI from the matrix** -- mixing happens in the Mix
windows, then Mix N L/R shows up as a matrix source (banks `0x06`-`0x09`).
`macos-mix1-send-pan-fader-mute-solo-link`: `d4 05 <mix> <ch> <fader>
<pan|flags> <send>` -- [18]=mix 0-3 (only 0 seen), [19]=channel 1-32,
[20]=fader (0=0dB .. 90=-90dB), [21]=pan (low 6 bits, `0x20`=centre,
`0x02`/`0x3e`=L30/R30) + mute bit `0x40` + solo bit `0x80`, [22]=send
(0-96, 96=0dB). One frame per strip, whole state each time. **Solo
re-sends all 32 strips** (channel-count probe). **Mix link = SET_LINK
space `0x03`** (new 4th link domain). No `0x73` readback (like routing).
`protocol.build_mix_command`; `0x17` in `allowed_opcodes`. NOT in the CLI
yet. `frame.mix_command` + `params.mix_*`.

- [x] ~~CAPTURE B -- destination enumeration~~ -- DONE (map above).
- [x] ~~CAPTURE A -- L/R sub-channel + frame model~~ -- **DONE, REVISED
      2026-08** (`macos-matrix-ch1-12-mute-hp1L`/`-hp1R`). Array of
      (bank,idx) pairs, from byte 19 stride 2. Old `02 01`/`00 02`
      reading was the OTHER channel's untouched routing. CLI fixed.
- [x] ~~CAPTURE C -- source-bank enumeration~~ -- **DONE 2026-08 for
      `0x05`-`0x0a`** (`macos-matrix-afx1-19-to-line1*` = AFX out bank
      `0x05` idx 0-31; `-mix1234-lineo1-*` = mix 1-4 banks `0x06`-`0x09`
      idx L/R; `-surrnd1-16-to-lineo1` = surround out bank `0x0a` idx
      0-15 -- these 3 files DO have the OUT endpoint). Only bank `0x01`
      (emumic?) still unseen -- a small follow-up.
- [x] ~~CAPTURE D -- line-out channel count~~ -- **DONE 2026-08**: line
      out (byte 18 = 0) is a **16-channel** group; the same 3 captures
      show all 16 (bank,idx) pairs (bytes 19-50). Still open: channel
      counts of adat out / com rec / afx in / mix chN / surround-in
      destinations. NOTE `macos-matrix-compplay*lineout*` = zero OUT
      frames, unusable.
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
- [x] ~~**wire `route` / `matrix-status`**~~ -- **DONE, REWRITTEN twice
      2026-08.** `build_route_command(profile, dest, channels)` takes an
      ordered (bank,idx) list for the whole group. `route_dest_channels` /
      `resolve_route_channel` map a 1-based channel selector (`L`/`R` =
      1/2 for `stereo_destinations`). CLI: `route <dest> <chan> <source>`
      (per-channel, keeps the rest from cache), `route <dest> all
      <s1>..<sN>`, `route <dest> mute` / `route <dest> <chan> mute`,
      `matrix-status`. NO `unroute` (user-noted: Launcher has none).
      Dests: line_out (16 ch) + hp1/hp2/mona/monb/reamp (2 ch). Sources:
      preamp/compplay/adat/afx/surround/osc (numbered), spdif/mix1-4
      (L/R), mute, keep. Frame builds verified byte-exact vs the hp1L/
      hp1R AND afx/mix/surround captures.
      **STILL NOT round-trip tested against hardware** -- user to test:
      `antelope-ctl route hp1 all preamp3 preamp4` then check the Launcher
      (should show HP1 L=preamp3, R=preamp4 -- the old code swapped them).

### Out of scope (deliberate)

**Licensed AFX plugins** -- the per-user-licensed, online-activated
plugin chain (Auto-Tune, the modelled-EQ/comp collections, etc.).
Skipped: touching that path drags in authentication/licensing.

**AuraVerb -- IN SCOPE (user decision, 2026-08).** AuraVerb is a
device-bundled reverb, always present, no per-plugin activation. Its own
frame: opcode `0x1d` / param `0xda`, byte 28 = enabled, bytes 17-27 = DSP
params (`macos-auraverb-on-off` only toggled on/off, so those are frozen
in that capture). **Next: full AuraVerb controls** -- needs a capture
that sweeps each control (decay / size / mod / hi+lo damp / mix / gain --
check the public manual for the real control list) one at a time. Then
map bytes 17-27, add `0x1d` to `allowed_opcodes`, `build_auraverb_command`
+ a CLI command. Still off-limits: anything that reads/writes license
state, and the licensed-plugin chain layout.

### Reverse-engineering sources -- what's allowed

- **Observed USB traffic** to/from hardware we own (the whole project).
- **Publicly published Antelope documentation** -- user manuals, spec
  sheets, block/signal-flow diagrams from antelope's own download pages.
  FINE to use: DMCA 1201 is about circumventing protection measures, not
  reading a PDF; and facts (channel counts, feature names, signal flow,
  parameter ranges) are not copyrightable. RULES: extract facts only,
  never paste manual text/tables/diagrams into the repo, cite the
  document + version + page in the `evidence` field. Don't use leaked
  service manuals or SDK docs -- public downloads only.
- **NOT allowed:** Antelope software / firmware / source, disassembly of
  their binaries, anything behind their login.

### Other captures to record (hardware)

Consider **native macOS** (CAPTURING.md). **LESSON (2026-08): the VM
Launcher silently no-ops some controls -- "zero frames under the VM" does
NOT mean host-side.** Screen brightness proved this: nothing under the VM,
full command on native macOS. Re-check oscillator / thunderbolt / DC-coup
on native macOS before trusting the "host-side" verdicts.

- [x] ~~**Screen brightness on macOS**~~ -- **DONE (2026-08), in the CLI,
      hardware-confirmed.** `macos-scrbrght-0-100-50-multvalue`: opcode
      `0x12` / param `0x0e` / value 0-100 at offset 17; readback `0x73`
      offset 26 (1:1, 25/25). `params.screen_brightness` +
      `state_report.screen_brightness_byte_offset`; CLI `set-brightness
      <0-100>` -- user confirmed it changes the physical screen.
- [ ] **AuraVerb parameter sweep** (user wants full controls next) --
      opcode `0x1d` / param `0xda` is known; `macos-auraverb-on-off` only
      toggled on/off so bytes 17-27 (the DSP params) are frozen. Capture
      on native macOS, sweeping ONE AuraVerb control at a time (decay /
      size / mod depth+rate / hi+lo damp / mix / gain -- confirm the real
      control list from the public manual). Then map bytes 17-27, add
      `0x1d` to `allowed_opcodes`, write `build_auraverb_command` + a CLI
      command. See `frame.auraverb_command`.
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
- [x] ~~`build_global_command` + `set-brightness`~~ -- **DONE (2026-08),
      HARDWARE-CONFIRMED.** `protocol.build_global_command(profile, param,
      value)` (opcode `0x12`, value @17) + `protocol.parse_state_scalar`
      (plain byte at a named state_report offset). CLI `set-brightness
      <0-100>` -- user confirmed it changes the device's physical screen.
      `build_global_command` also unblocks talkback params.
- [x] ~~sample rate CLI~~ -- **DONE (2026-08).** CLI `sample-rate` /
      `set-sample-rate <hz>` (accepts `48000`/`48k`/`44.1k`/...), via
      `build_global_command(profile, 'sample_rate', index)` +
      `parse_state_scalar(..., 'sample_rate_byte_offset')`. Not hardware
      round-trip tested.
- [x] ~~`build_mix_command` (opcode `0x17`)~~ -- **DONE 2026-08.**
      `protocol.build_mix_command(profile, mix, channel, fader, pan_deg,
      send, mute, solo)`; `frame.mix_command` + `params.mix_*`. NOT in a
      CLI command yet -- big surface (fader/pan/send/mute/solo/link ×
      32ch × 4 mixes, no readback so each command sends the whole strip).
      A `mix-set <mix> <ch> [--fader] [--pan] ...` with a local cache
      (like `route`) is the shape.
- [ ] Hardware round-trip test the rewritten `route`:
      `route hp1 all preamp3 preamp4` (Launcher should show HP1 L=preamp3
      R=preamp4; old code swapped them), then `route hp1 mute`. Also
      round-trip `set-sample-rate` (with nothing streaming).
- [ ] `mix-set <mix> <ch> [--fader/--pan/--send/--mute/--solo]` CLI for
      `0x17` -- local cache like `route` (no readback).
- [ ] AuraVerb param CLI once the sweep capture is analyzed (map frame
      bytes 17-27, add `build_auraverb_command`, `0x1d` -> allowed_opcodes).
- [ ] Decide which confirmed-but-unexposed params get CLI commands:
      talkback (`talkback_*`), line/reamp bus levels (already work via
      `set-bus-level` with bus 3/4), `output_trim`, the mixer (`mix_*`).
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
  nothing because the VM Launcher no-ops the slider.
  `params.screen_brightness`; CLI `set-brightness`.
- **Routing** (`matrix-*` captures) -- **frame model + all source banks
  (bar `0x01`) + line-out channel count (16) decoded** 2026-08. Opcode
  `0x53`/`0xd3`; byte 18 = destination group (0-14 map confirmed); from
  byte 19, an array of (bank,idx) pairs, stride 2, one per output channel.
  Whole group always sent. mute=(0x0b,0). Exclusive per channel. CLI:
  `route <dest> <chan> <source>` / `all` / `mute`. Still open: channel
  counts of the other multichannel dests; bank `0x01`; the readback
  (exists per cross-machine persistence -> E').
  See `frame.routing_command` + `params.routing`.
- ~~`macos-mix1-send-pan-fader-mute-solo-link`~~ -- **DONE (2026-08).**
  Virtual mixer, new opcode `0x17` / param `0xd4`. `d4 05 <mix> <ch>
  <fader> <pan|flags> <send>`; mute/solo = bits `0x40`/`0x80` of the pan
  byte; mix link = SET_LINK space `0x03`; 32 channels/mix; no `0x73`
  readback. `frame.mix_command` + `params.mix_*` + `protocol.build_mix_command`.
  Not in CLI.
- ~~`macos-auraverb-on-off`~~ -- **PARTIAL (2026-08).** AuraVerb (Mix 1
  reverb) on/off: new opcode `0x1d` / param `0xda`, byte 28 = enabled
  (2 frames, identical bar byte 28). Bytes 17-27 = DSP params, frozen in
  this capture. `frame.auraverb_command` + `params.auraverb`. **User wants
  full controls next** -> needs a param-sweep capture (see the captures
  TODO above). AuraVerb is IN SCOPE (bundled, no per-plugin activation).
- ~~`macos-smplrt-32k-44k1-48-88k2-96k-176k4-192k`~~ -- **DONE (2026-08).**
  Sample rate: `SET_GLOBAL` (opcode `0x12`) / param `0x03` / index 0-6 at
  offset 17 (0=32k 1=44.1k 2=48k 3=88.2k 4=96k 5=176.4k 6=192k). Readback
  `0x73` offset 18, ~1 s lag (clock re-lock). `params.sample_rate` +
  `state_report.sample_rate_byte_offset`; CLI `sample-rate` /
  `set-sample-rate <hz>`. Not hardware round-trip tested. Offsets
  21-23,27 also move at 88.2k/176.4k -- undecoded clock state.
