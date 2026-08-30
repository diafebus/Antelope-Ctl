Don't over use tokens, throwing agents and using all the resources at once, a good engineer saves resources

## TODO / next steps (keep this current)

Raw `.pcapng` files are local under `captures/` (`raw pcapng captures/`
and `matrix-captures/`); `tshark` 4.6.8 is on this machine. Anything
needing full frames / both directions / USB metadata is offline now.

### ROUTING MATRIX -- the active thread

`frame.routing_command`: opcode `0x53` / param `0xd3`. Confirmed bytes:
17=`0x41`, **18 = destination**, **19 = source bank**, **20 = source
index in bank**, **21 = op** (`0x02` add / `0x00` remove). Routing is
EXCLUSIVE per output (virtual mixes = the summing path). NO `0x73`
readback. Output mute (bank `0x0b`) and oscillator-insert (bank `0x0c`)
go through this same frame via right-click. Talkback is NOT a matrix
source.

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

**Matrix destinations** (byte 18) -- user's full output list:
| dest | byte 18 | status |
|---|---|---|
| hp1 | `1` | confirmed |
| hp2 | `2` | confirmed |
| mona | `3` | confirmed |
| monb | `4` | confirmed |
| reamp | `5` | confirmed |
| lineout, com rec, adat out, spdif out, afx in, mix ch1-4, surround in | ? | **TBD** |

- [ ] **CAPTURE A -- L/R sub-channel** (the blocker for CLI wiring):
      route comp-play 1 -> HP1 **Left**, wait, -> HP1 **Right**, wait (no
      un-route between). Then comp-play 1 -> Monitor A Left, wait, -> Right.
      Diff the frame pairs -> the byte that changes is the L/R selector,
      and whether it's the same value per destination.
- [ ] **CAPTURE B -- destination enumeration**: route comp-play 1 to one
      output of EACH type in the list above (lineout, com rec, adat out 1,
      spdif out L, afx in, mix ch1, surround in, ...), un-routing between,
      3 s pauses. Maps byte 18's full range.
- [ ] **CAPTURE C -- source-bank enumeration**: route each of emumic /
      afx out / mix1 L / mix1 R / surround out -> HP1 L, one at a time.
      Maps the remaining byte-19 banks.
- [ ] **CAPTURE D -- virtual mix (additive path)**: route 2-3 sources INTO
      mix ch1 (a mix channel destination), keeping all -- shows how summing
      is encoded (different frame? a "mix" flag? add without replace?).
- [ ] then: decode + fold into `frame.routing_command` / `params.routing`,
      and wire `route` / `unroute` / `matrix-status`(client-cache) into the
      CLI.

### Other captures to record (hardware)

Consider **native macOS** (CAPTURING.md) -- screen brightness works there,
does nothing under the VM.

- [ ] **Screen brightness on macOS** -- real command or not? (no size filter)
- [ ] **Surround-EQ pre/post** -- opcode `0xab` / param `0xeb`, only 2
      frames so far. Toggle several times to decode.
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
- ~~`matrixtest-pre1-cmpplay1-2` / `matrix-ch3tohpmonreamp`~~ -- routing,
  **partly decoded** (see TODO + `frame.routing_command` + `params.routing`).
  Opcode `0x53` / param `0xd3`; dest byte 18 (1=hp1..5=reamp), source byte
  20 (0-idx input). No `0x73` readback. Bytes 19/21/22 + L/R + un-route
  still need 3 targeted captures.
