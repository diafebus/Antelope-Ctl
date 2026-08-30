# SUMMARY.md -- session resume doc

**Purpose:** read this first when resuming work. It is the human/AI
hand-off between sessions. Update the "Session log" and "Right now"
sections at the end of every working session.

Deeper detail lives in: `CLAUDE.md` (live TODO + capture notes),
`PROTOCOL.md` (wire format reference), `README.md` (user-facing),
`profiles/orion_studio_3.json` (machine-readable source of truth).
Keep those four in sync whenever a capture is analyzed.

---

## What this project is

Reverse-engineering the USB-HID vendor protocol of an **Antelope Orion
Studio III** audio interface (VID `0x23e5`, PID `0xa221`) from
Wireshark/USBPcap captures, and building a **stdlib-only Python CLI**
(`antelope-ctl`) to control it on Linux.

**Direction (priority order):**
1. **Now** -- reverse-engineer *all* controls / as much of the device as
   possible.
2. **Next** -- a forming group of collaborators will build a **webUI**
   control panel on top of the decoded protocol. The Python CLI is the
   reference implementation + test harness, not the final product; the
   webUI backend will consume the same `profiles/*.json`. Keep
   `antelope/` generic and profile-driven.
3. **Optional endgame** -- a mainline `snd-usb-audio` kernel driver
   (`KERNEL.md`). Not committed to; Antelope is niche and a good webUI
   may be enough. Revisit only if headless/studio demand appears, and
   never before the protocol is complete + hardware-verified.

- HID vendor interface 3, EP `0x01` OUT / `0x82` IN, 320-byte reports,
  4 ms poll. Audio is separate iso endpoints (`0x05` / `0x84`), not
  touched.
- A peer got a sibling **Discrete 8 Pro** working with the same protocol
  (`profiles/discrete_8_pro_synergy_core.json`). **Do not modify or
  discuss that file** unless explicitly asked -- we standardize later.
- Raw `.pcapng` captures are local under `captures/` (git-ignored).
  `tshark` 4.6.8 is on the Linux box. Offline analysis of any existing
  capture is possible now.

## Standing constraints

- **Conserve resources** -- don't spawn subagents or fan out tools for
  work that can be done inline (CLAUDE.md line 1).
- Commit after each meaningful step. Git trailer:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
- When committing, `git add` files explicitly so
  `profiles/discrete_8_pro_synergy_core.json` is never staged.
- `git config` user is repo-local: `diafebus` / `diaf3bus@gmail.com`.

---

## Protocol state -- what is DECODED

### Command opcodes (byte @4)
| opcode | name | layout |
|---|---|---|
| `0x13` | SET_PARAM | param@16, channel@17, value@18 |
| `0x12` | SET_GLOBAL | param@16, value@17 (no channel) -- talkback_*, screen_brightness (`0x0e`, 0-100, readback @26) |
| `0x14` | SET_LINK | `0xa2`@16, space@17, pair@18, enabled@19 |
| `0x53` | SET_ROUTE | `0xd3`@16, `0x41`@17, dest group@18, then (bank,idx) pair per output channel from @19 stride 2 |
| `0xab` | surround-EQ | `0xeb`@16 -- barely decoded, needs a capture |

Outgoing frames use magic `0x70` @0 (cosmetic -- device ignores byte 0
on outgoing).

### Incoming reports (byte 0 magic)
- `0x73` state report -- byte-map below
- `0x75` meter report
- `0x74` init topology enumeration -- one-shot at connect, 113 records
  `(category@8, index@12)`, **no names** (names are USB string
  descriptors = control transfers, absent from HID capture). `0x1a`x16 =
  ADAT, `0x11`x2 = S/PDIF; `0x19`x64 / `0x03`x15 / `0x04`x4 + singletons
  unmapped.

### `0x73` state-report byte-map (confirmed)
| offset | meaning |
|---|---|
| 24-25 | output_trim, packed (targets 0/1/2 = mona/monb/line) |
| 26 | screen brightness (0-100, plain byte) -- confirmed 2026-08 |
| 28-45 | bus block, 6 buses x 3 bytes at `28+3N` |
| 49-60 | channel gain array (12 input ch) |
| 61-72 | channel status array (bits: mode `0x03`, phantom `0x10`, phase `0x40`) |
| 73 | talkback status (src `&3` bits0-1, dest_assign bits2-5, button bit6) |
| 74 | talkback gain |
| 75-90 | ADAT gain array (16) |
| 91-92 | S/PDIF gain L/R |
| 17/19 | ~3 s Launcher-handshake blip -- NOT user state |
| 139-140 | startup ramp -- NOT user state |
| 157-232 | embedded meter jitter -- noise floor only |

### Connect handshake (cross-platform confirmed, 2026-08)
Entire host->device init = ONE frame `SET_PARAM(param 0x49, ch 1, val 0)`
(Windows AntelopeINIT + all 4 macOS INIT captures). Device replies with
`0x74` enum burst + `0x73`/`0x75` polling. Any extra `SET_PARAM(gain
0x50)` frames = the user wiggling sliders to force the buggy Launcher to
flush, not device behaviour.
**No routing readback at connect** -- but one exists (see routing section).

### Screen brightness -- CONFIRMED (2026-08, native macOS)
`global_command` opcode `0x12`, param `0x0e`, value 0-100 (0x00-0x64) @17.
Readback = `0x73` offset 26, plain byte = value (25/25 in
`macos-scrbrght-0-100-50-multvalue`). VM Launcher no-ops the slider ->
"zero frames under the VM" != host-side; recheck VM negatives on macOS.
CLI: `set-brightness <0-100>` (2026-08) -- HARDWARE-CONFIRMED (user: the
CLI command changes the device's physical screen).

### macOS capture format (`captures/macos-captures/`)
Darwin XHC pcapng: 40-byte pseudo-header + 320-byte payload =
`frame.len==360`; payload[0] = magic; header byte 30 = endpoint
(0x01 OUT / 0x82 IN). `0x74` on IN-ep1, `0x73`/`0x75` on IN-ep2.
`tools/scan_capture.py` only knows the Windows TSV layout; use
`tools/scan_macos_capture.py` for these (`--magic`, `--diff` modes).

### Address spaces
- input channels 0-11; ADAT 0-15 (8 link pairs); S/PDIF 0-1
- bus ids: 0=mona, 1=hp1, 2=hp2, 3=line_out, 4=reamp, 5=monb
- talkback source: 0=INT mic, 1-12=preamps 1-12 (user-confirmed)
- talkback dest_assign: 0-3 = Mon A / Mon B / HP1 / HP2, **combinable**
  bitmask (multi-destination confirmed)
- output_trim targets 0-2; step 0-6
- bus `0x04` bit = muted **OR** at level 96 (ambiguous -- see TODO)

### SET_LINK `space` byte (@17)
`0` = physical preamp + ADAT (still ambiguous between the two, both
`0x00`), `1` = S/PDIF.

### Channel link is SOFTWARE-controlled
Device firmware does **not** propagate mode/gain/phantom/phase between
linked channels. The Launcher sends two SET_PARAM frames.
**Strongest proof:** turning the physical front-panel gain wheel on a
linked channel moves only that channel. The CLI mirrors to the partner
host-side, exactly like the Launcher.

### Routing matrix (opcode `0x53`) -- FRAME MODEL + BANKS DECODED, active thread
- `d3 41 <dest> | <bank0> <idx0> | <bank1> <idx1> | ...` -- after byte 18,
  an **array of (source_bank, source_index) pairs**, one per output
  channel of the destination group, from byte 19, **stride 2**
  (channel c at bytes 19+2c, 20+2c). NO op bytes -- the old `02 01`/
  `00 02` was a misread of the OTHER channel's untouched (bank,idx),
  which caused the L/R swap the user saw. Whole group always sent.
- byte 18 = **destination group**: `0`=line out, `1`=hp1, `2`=hp2,
  `3`=mona, `4`=monb, `5`=reamp, `6`=com rec, `7`=adat out, `8`=spdif
  out, `9`=afx in, `10`-`13`=mix ch1-4, `14`=surround in.
- **line out = 16-channel group** (byte 18 = 0) -- CONFIRMED. Other
  multichannel dests' channel counts still open.
- **source banks (all confirmed 2026-08 except `0x01`):** `0x00` preamp
  (0-11), `0x01` UNKNOWN (emumic?), `0x02` compplay (0-23 VM / 0-31
  macOS), `0x03` ADAT (0-15), `0x04` S/PDIF (0-1), `0x05` **AFX out**
  (0-31), `0x06`-`0x09` **mix 1-4** (L/R), `0x0a` **surround out** (0-15),
  `0x0b` MUTE (idx 0), `0x0c` oscillator (0/1).
- mute a channel = put `(0x0b, 0)` in its slot. No "no source" / no
  un-route. Exclusive per channel; idempotent.
- EVIDENCE: `macos-matrix-ch1-12-mute-hp1L`/`-hp1R` (2-ch model + mute),
  `-afx1-19-to-line1*` (bank 0x05, line-out 16-ch), `-mix1234-lineo1-*`
  (banks 0x06-0x09), `-surrnd1-16-to-lineo1` (bank 0x0a). talkback NOT a
  matrix source. oscillator-insert goes through this frame.
- **Routing readback EXISTS but is undecoded, and is NOT at connect.**
  User proof it exists: changed routing on Windows VM -> switched to
  macOS -> macOS Launcher showed the NEW routing (host cache can't
  cross machines; device stores in NVRAM + reports to whoever asks).
  CAPTURE E (2026-08, `macos-antelopeINIT-poweroff-on2/on3`: cold boot,
  swapped LineOut routing) ruled out the CONNECT sequence -- `0x74`
  identical, descriptors identical, `0x73` only a preamp-gain byte +
  meter noise, no `0x53`. So it fires later; prime suspect = opening
  the routing tab (CAPTURE E'). Also not in the `0x73` report at all.

---

## Code state

### `antelope/protocol.py` (generic, no hardcoded device values)
- frame build/parse for all opcodes + reports
- `build_command`, `build_link_command(profile, pair, enabled, space=0)`,
  `build_global_command(profile, param, value)` (opcode 0x12, value @17),
  `build_route_command(profile, dest, channels)` -- `channels` = ordered
  list of (bank, idx) tuples, whole destination group
- `resolve_route_source` / `resolve_route_dest` / `route_source_label`
  (reverse lookup); `ROUTE_MUTE` = (0x0b, 0)
- constraints layer: `ConstraintError`, `check_opcode`, `check_target`,
  `check_enum`, `channel_space_bounds` -- profile-driven, `--force`
  overrides
- parse helpers: ADAT/SPDIF gain; `parse_state_scalar(profile, data, key)`
  (a plain byte at state_report.<key>, e.g. screen_brightness_byte_offset)

### `antelope/cli.py` (generic CLI)
- input channel: `set-gain` / `set-mode` / `set-phantom` / `set-invert`
- link: `set-link` / `mark-link`; ADAT: `adat-status` /
  `set-adat-gain` / `set-adat-link` / `mark-adat-link`; S/PDIF:
  `spdif-status` / `set-spdif-gain` / `set-spdif-link` / `mark-spdif-link`
- bus: `bus-status` / `set-bus-level` / `set-bus-dim|mute|mono`
- `set-brightness <0-100>` (screen brightness; global_command; readback @26)
- `raw-set` (constraint-guarded, `--force`)
- **EXPERIMENTAL, not hardware-tested:** `route <dest> <chan> <source>`
  (1-based channel; `L`/`R`=1/2 for stereo dests; keeps other channels
  from cache), `route <dest> all <s1>..<sN>`, `route <dest> mute` /
  `route <dest> <chan> mute`, `matrix-status`. No `unroute`. Dests:
  line_out (16 ch) + hp1/hp2/mona/monb/reamp (2). Sources: preamp,
  compplay (alias playback), adat, afx, surround, osc (numbered); spdif,
  mix1-4 (L/R); mute; keep. Rewritten twice 2026-08.
  protocol helpers: `route_dest_channels`, `resolve_route_channel`.
- constraints enforced on all channel/bus/adat/spdif/raw commands
- caches under `~/.cache/antelope-ctl/`: link state (kinds `''` /
  `adat` / `spdif`) and routing (`matrix`) -- all **CLI-tracked, not
  device readback**

### Pending code work (protocol-first, deferred on purpose)
- decide CLI exposure for talkback + output_trim params (talkback can now
  use `build_global_command` for `0x1f`/`0x20`/`0x27`, + `0x13` for
  `talkback_dest_assign`)
- `bus-status`: special-case `bus_level == 96` vs the mute bit
- teach `tools/scan_capture.py` about magic `0x74`

---

## Captures still needed (hardware -- user records these)

| id | what | maps |
|---|---|---|
| ~~**C**~~ | ~~source-bank enumeration~~ | **DONE 2026-08** for `0x05`-`0x0a` (afx/mix1-4/surround, from `-afx1-19*`/`-mix1234-*`/`-surrnd1-16*`). Only bank `0x01` (emumic?) left -- small. |
| ~~**D**~~ | ~~line-out channel count~~ | **DONE 2026-08** -- line out = 16 ch. Still open: adat out / com rec / afx in / mix chN / surround-in destination channel counts. |
| ~~**E**~~ | ~~routing readback at connect~~ | **DONE 2026-08** -- no readback at connect (macOS on2/on3). |
| **E'** | with Launcher already connected, capture clicking into the routing *tab*, x2 with different routes, diff | whether tab-open triggers a routing query (last possible readback path) |

Lower priority: surround-EQ pre/post (`0xab`), pan law (state offset 25
bits 0-1), DC-coupling, string descriptors (fresh connect no size filter
-> `0x74` names), ADAT + physical link in one session, channel_link
readback diff.

**Also pending:** user to hardware round-trip test
`antelope-ctl route hp1 preamp3 preamp4` -> Launcher should show HP1
L=preamp3, R=preamp4 (old code swapped them).

---

## Right now (update me each session)

- Working tree: run `git log` -- several routing commits this session.
- Routing matrix: **frame model + all source banks (bar `0x01`) + line-out
  channel count (16) decoded.** CLI `route <dest> <chan> <source>` (per
  channel) / `all` / `mute`, dests line_out + hp1/hp2/mona/monb/reamp.
  **Not hardware-tested** -- user to run `route hp1 all preamp3 preamp4`
  and check the Launcher shows L=preamp3 R=preamp4 (old code swapped them).
- **CAPTURE E answered:** no routing readback in the connect sequence --
  BUT one must exist (user: routing survived a Windows->macOS switch).
  Next = CAPTURE E' (routing-tab open).
- **Screen brightness DONE + hardware-confirmed:** CLI `set-brightness
  <0-100>` (via new `build_global_command`).
- Still open on routing: channel counts of the other multichannel dests
  (adat out / com rec / afx in / mix chN / surround in); bank `0x01`
  (emumic?); the readback. `compplay*lineout*` captures = no OUT frames.
- Pending: hardware round-trip `route`; CAPTURE E'.

## Session log

- **2026-08-30 (macOS-captures session)** -- Worked the native-macOS
  capture batch. Commits `213e42f`, `3e0ef09`, `6176e95`, `7d0226b`.
  1. **CAPTURE E**: no routing readback in the *connect* sequence
     (`macos-antelopeINIT-poweroff-on2/on3`, swapped LineOut routing ->
     connect diffs to nothing routing-related). BUT the user reports
     routing survived a Windows-VM -> macOS host switch, so a device
     readback DOES exist -- undecoded, next try = CAPTURE E' (routing-tab
     open). Connect handshake = one `SET_PARAM(0x49,ch1,0)`, cross-platform.
  2. **Screen brightness decoded + wired** (`macos-scrbrght-0-100-50-multvalue`):
     `global_command 0x12` / param `0x0e` / value 0-100, readback `0x73`
     offset 26. VM had shown nothing only because the VM Launcher no-ops
     the slider -- so "zero frames under the VM" != host-side. Added
     `protocol.build_global_command` + `parse_state_scalar` and the CLI
     `set-brightness <0-100>` -- user then confirmed on hardware it
     changes the device's physical screen.
  3. **Routing frame model CORRECTED** (`macos-matrix-ch1-12-mute-hp1L`/
     `-hp1R`): after byte 18 it's an array of (source_bank, source_index)
     pairs, one per output channel, stride 2 -- NO "op bytes" (`00 02` was
     literally preamp 3 = the untouched other channel). That was the
     L/R-swap bug the user hit on the Windows Launcher. Dropped `unroute`
     (Launcher has none). Renamed source `playback` -> `compplay` (alias).
  4. **Source banks `0x05`-`0x0a` + line-out channel count decoded**
     (`macos-matrix-afx1-19-to-line1*` = AFX out bank `0x05` idx 0-31 +
     line out = 16-channel group; `-mix1234-lineo1-*` = mix 1-4 =
     `0x06`-`0x09` L/R; `-surrnd1-16-to-lineo1` = surround out `0x0a`
     idx 0-15). Only bank `0x01` (emumic?) unseen now.
  5. **CLI rebuilt for numeric channels** (user-noted -- L/R doesn't
     generalize): `route <dest> <chan> <source>` (1-based; L/R = 1/2 for
     the stereo dests only), `route <dest> all <s1>..<sN>`, `route <dest>
     mute`. Added protocol `route_dest_channels` / `resolve_route_channel`.
     line_out (16 ch) now wired alongside hp1/hp2/mona/monb/reamp. Frames
     verified byte-exact vs all five usable macOS matrix captures.
  7. Added `tools/scan_macos_capture.py`; documented the Darwin XHC
     format. NOTE: `macos-matrix-compplay*lineout*` + `ch1-12-mute-hp2LR`
     are missing the OUT endpoint -> unusable for command decoding.
     Commits `6176e95` (frame fix) .. later (banks + CLI rebuild + brightness).
- **2026-08-30 (routing-decode session)** -- Decoded routing matrix
  destinations 0-14 + source banks from Windows `matrix-*` captures;
  shipped the first experimental `route` / `matrix-status`. (Its "op
  bytes" model was wrong -- fixed in the session above.) Confirmed channel
  link is software-only via the hardware-wheel test. Created this file.
- **earlier (2026-08)** -- Talkback fully decoded (`0x12` / `0x13`).
  Bus ids 3/4 = line out / reamp. Output trim (`0x4b`). S/PDIF gain +
  link, discovered SET_LINK `space` byte. `0x74` = init topology enum.
  Folded Discrete 8 Pro peer-PR lessons into constraints/hazards.
  Built + wired the constraints enforcement layer. ADAT gain + link CLI.
