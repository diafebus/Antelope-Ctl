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
| `0x12` | SET_GLOBAL | param@16, value@17 (no channel) |
| `0x14` | SET_LINK | `0xa2`@16, space@17, pair@18, enabled@19 |
| `0x53` | SET_ROUTE | `0xd3`@16, `0x41`@17, dest@18, src_bank@19, src_idx@20, op bytes @21/@22 or a list |
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

### Routing matrix (opcode `0x53`) -- PARTLY decoded, active thread
- byte 18 = **destination**, full map: `0`=line out, `1`=hp1, `2`=hp2,
  `3`=mona, `4`=monb, `5`=reamp, `6`=com rec, `7`=adat out,
  `8`=spdif out, `9`=afx in, `10`=mix ch1, `11`=mix ch2, `12`=mix ch3,
  `13`=mix ch4, `14`=surround in
- byte 19 = **source bank**, byte 20 = **source index in bank**
- source banks: `0x00` preamp (0-11), `0x02` DAW playback (0-23 -- caps
  at 24, no ch32), `0x03` ADAT (0-15), `0x04` S/PDIF (0-1), `0x0b` MUTE
  pseudo-source, `0x0c` oscillator (0/1 = osc 1/2)
- **unseen banks:** `0x01`, `0x05`-`0x0a`, `0x0d`+ -- need emumic
  (starts at ch5; ch1-4 have no mic emulation), afx out, mix1-4 L/R,
  surround out
- **matrix is all-mono** -- each output treated as mono; L/R sources go
  to separate outputs individually, they do not fill both
- routing is **exclusive** (one source per output; replacing sends no
  remove frame) and **idempotent** (no frame if source already routed)
- op bytes for simple 2-output destinations (hp1/hp2/mona/monb/reamp):
  output 1 = `[21]=0x02 [22]=0x01`; output 2 = `[21]=0x00 [22]=0x02`;
  un-route = `[21]=0x00 [22]=0x00`; mute = bank `0x0b` idx 0 + op pair
- multichannel destinations (line out, adat out, mix ch) carry an
  **undecoded variable-length per-channel list** at bytes 21+
- talkback is **NOT** a matrix source (its dest toggles live in the
  Monitors/Headphones menu)
- oscillator insert + output mute both go through this frame via
  right-click
- **NO `0x73` readback** for routing. Checked `AntelopeINIT.pcapng` --
  no routing data anywhere. Untested hypothesis: readback may only
  appear in the Launcher INIT handshake (see CAPTURE E).

---

## Code state

### `antelope/protocol.py` (generic, no hardcoded device values)
- frame build/parse for all opcodes + reports
- `build_command`, `build_link_command(profile, pair, enabled, space=0)`,
  `build_route_command(profile, dest, src_bank, src_idx, output)`
- `resolve_route_source` / `resolve_route_dest`
- constraints layer: `ConstraintError`, `check_opcode`, `check_target`,
  `check_enum`, `channel_space_bounds` -- profile-driven, `--force`
  overrides
- ADAT/SPDIF gain parse helpers

### `antelope/cli.py` (generic CLI)
- input channel: `set-gain` / `set-mode` / `set-phantom` / `set-invert`
- link: `set-link` / `mark-link`; ADAT: `adat-status` /
  `set-adat-gain` / `set-adat-link` / `mark-adat-link`; S/PDIF:
  `spdif-status` / `set-spdif-gain` / `set-spdif-link` / `mark-spdif-link`
- bus: `bus-status` / `set-bus-level` / `set-bus-dim|mute|mono`
- `raw-set` (constraint-guarded, `--force`)
- **EXPERIMENTAL, not hardware-tested:** `route <dest> <output>
  <source>`, `unroute <dest> <output> <source>`, `matrix-status`
- constraints enforced on all channel/bus/adat/spdif/raw commands
- caches under `~/.cache/antelope-ctl/`: link state (kinds `''` /
  `adat` / `spdif`) and routing (`matrix`) -- all **CLI-tracked, not
  device readback**

### Pending code work (protocol-first, deferred on purpose)
- `build_global_command(profile, param_id, value)` in protocol.py
  (opcode `0x12`, value @17 -- profile references it already)
- decide CLI exposure for talkback + output_trim params
- `bus-status`: special-case `bus_level == 96` vs the mute bit
- teach `tools/scan_capture.py` about magic `0x74`

---

## Captures still needed (hardware -- user records these)

| id | what | maps |
|---|---|---|
| **C** | route emumic / afx out / mix1 L / mix1 R / surround out -> HP1 output 1, one at a time | source banks `0x01`, `0x05`-`0x0a`, `0x0d`+ |
| **D** | change ONE channel of line out (or adat out) at a time; also 2-3 sources into mix ch1 keeping all | the variable-length per-channel list; the virtual-mix additive path |
| **E** | change routes, fully quit Launcher, restart, capture connect (no size filter), x2 with different routes, diff | whether routing readback lives in the INIT handshake |

Lower priority: screen brightness on macOS, surround-EQ pre/post
(`0xab`), pan law (state offset 25 bits 0-1), DC-coupling, string
descriptors (fresh connect no size filter -> `0x74` names), ADAT +
physical link in one session, channel_link readback diff.

**Also pending:** user to hardware round-trip test
`antelope-ctl route hp1 L preamp3` then check the Launcher.

---

## Right now (update me each session)

- Working tree clean. Last commit `2056f0c`.
- Routing matrix is the active thread. Simple destinations
  (hp1/hp2/mona/monb/reamp) are fully decoded and wired into an
  experimental CLI; nothing has been tested against real hardware yet.
- Next input needed from user: any of CAPTURE C / D / E, or the
  `route` round-trip test result.

## Session log

- **2026-08-30** -- Decoded routing matrix (destinations 0-14, source
  banks, op bytes for simple destinations) from `matrix-*` captures.
  Shipped experimental `route` / `unroute` / `matrix-status`. Confirmed
  channel link is software-only via the hardware-wheel test. Checked
  `AntelopeINIT.pcapng` for routing readback -- none. Created this file.
- **earlier (2026-08)** -- Talkback fully decoded (`0x12` / `0x13`).
  Bus ids 3/4 = line out / reamp. Output trim (`0x4b`). S/PDIF gain +
  link, discovered SET_LINK `space` byte. `0x74` = init topology enum.
  Folded Discrete 8 Pro peer-PR lessons into constraints/hazards.
  Built + wired the constraints enforcement layer. ADAT gain + link CLI.
