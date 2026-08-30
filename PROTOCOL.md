# Antelope Orion Studio III -- protocol & hardware reference

Everything reverse-engineered so far about how the device talks, in one
place. `README.md` is the user-facing guide; this file is the spec you
reach for once you've read it. `profiles/orion_studio_3.json` is the
machine-readable source of truth -- if the two ever disagree, the profile
wins and this file is stale.

All offsets are **byte offsets into the 320-byte HID report**, 0-indexed.
"2026-08" on a claim means it was confirmed by capture in that session;
see `README.md` and the profile's `evidence` fields for which capture.

---

## 1. Device & transport

| | |
|---|---|
| Device | Antelope Orion Studio III |
| USB VID:PID | `0x23e5:0xa221` |
| bcdDevice | 7.00 |
| Control interface | vendor **HID, interface 3** (the UAC2 audio-control interface is a stub -- 1 clock, 4 terminals `nrChannels=1`, no Feature Units -- all control is HID) |
| Report size | **320 bytes**, fixed, both directions (but see §13 -- Linux hidraw writes may need a leading `0x00`, making them 321; unverified on Orion) |
| Control OUT endpoint | `0x01` (host -> device commands), interrupt |
| Control IN endpoint | `0x82` (device -> host reports), interrupt |
| Audio stream endpoints | `0x05` OUT / `0x84` IN, isochronous, 24-ch / 24-bit in the class-compliant descriptor -- **unrelated to control** |
| Device address | 2 (`usb.dst 1.2.x` in the captures) |
| Poll interval | 4 ms |
| GET / query opcode | **none known** -- state is only ever read passively from the IN reports the device streams |
| String descriptors | **never fetched in any capture on file** -- so no channel/bus/category names are recoverable from the USB traffic |

Byte 0 of every **incoming** report is a **magic** that identifies the
frame type. On **outgoing** commands byte 0 (`0x70`) is cosmetic -- the
sibling Discrete 8 Pro ignores it entirely; the opcode at offset 4 is the
real discriminator (§13).

---

## 2. Outgoing command frames (magic `0x70`)

Four opcodes are known. The opcode is at **offset 4**. The param_id is at
**offset 16** for all of them. What comes after offset 16 depends on the
opcode -- this is the single most important thing to get right:

| Opcode @4 | Name | param_id @16 | Payload | Used by |
|---|---|---|---|---|
| `0x13` | SET_PARAM | param | `channel` @17, `value` @18 | gain, input_mode, phantom, phase_invert, adat_gain, bus_level/dim/mute/mono, output_trim, talkback_dest_assign |
| `0x12` | SET_GLOBAL | param | `value` @17 (no channel byte; @18 unused) | talkback_button, talkback_source, talkback_gain |
| `0x14` | SET_LINK | `0xa2` (fixed) | `space` @17 (0 = physical+ADAT, 1 = S/PDIF), `pair_index` @18, `enabled` @19 | channel_link, adat_channel_link, spdif_channel_link |
| `0x53` | SET_ROUTE | `0xd3` | `0x41` @17 (const), `destination` @18, `source` @20; `@19`/`@21`/`@22` undecoded | routing matrix (§7) |
| `0xab` | (surround-EQ?) | `0xeb` | `99 b0 <flags@19> 06 00 58 02` (@17..23), **barely decoded** -- 2 frames, bit 7 of @19 is the toggle | surround-EQ pre/post (probably) |

Notes:
- `0x12` puts its value where `0x13` puts its channel. A builder that
  assumes `0x13` layout will write the value to the wrong byte.
- `0x14` shifts everything one byte later than `0x13` and adds an explicit
  `enabled` byte that `0x13` has no equivalent of.
- The official Launcher frequently **double-sends** the same command
  (two identical frames tens of ms apart). One is enough.
- For a linked pair, the Launcher sends **two** `SET_PARAM` frames per
  change (one per channel) -- the firmware does not fan a single write out
  to both channels. See section 8.

---

## 3. Incoming report frames

| Magic @0 | Name | Rate | Purpose |
|---|---|---|---|
| `0x73` | state report | continuous (~every 4-8 ms) | the readback for nearly everything -- see section 5 |
| `0x75` | meter report | continuous | per-channel input meters, offset 32 + channel index |
| `0x74` | init enumeration | **once**, ~t=7.5-16 s of the connect sequence, then never | device topology dump; see section 4 |

`0x75` meter bytes: one byte per channel from offset **32**, same channel
order as gain/status. Scale is **inverted** -- `0x60` (96) at
rest/silence, falls toward `0x00` as the signal gets louder. Calibration
in section 9.

### 2026-08 caveat: only `0x70` / `0x73` / `0x75` exist in normal use

Every multi-thousand-report capture to date contains only those three
magics (plus `0x74` in the one INIT capture). There is no hidden fourth
report type carrying link state, oscillator state, etc.

---

## 4. Magic `0x74` -- init enumeration (unconfirmed)

One-shot at device connect (t=7.5-16 s of `all_reports_AntelopeINIT.tsv`,
113 records total, never seen in any other capture). That capture is the
Launcher being **started with no user interaction** -- so the whole burst,
plus the single outgoing `SET_PARAM(param 0x49)` at t=7.7 s, is the
Launcher's automatic startup handshake. Record layout:

```
@0   0x74
@4   u32  0x10        (constant on every record)
@8   u32  category_id
@12  u32  index       (0-based, runs 0..count-1 within a category)
@16+ zero
```

The device walks each internal category and emits one record per member.
**The records carry only `(category_id, index)` -- no names.** Names would
be in USB string descriptors -- and **none of the 21 raw pcapng files on
file contains a single string-descriptor fetch** (checked 2026-08), plus
the UAC2 descriptor is a nameless stub. So the counts and emission order
below are everything the captures give; the labels are inference. To get
real names: a fresh connect capture where Windows re-fetches strings, or
read the counts off against the Launcher's routing-tab labels.

### Full emission order

| # | category | indices | count | notes |
|---|---|---|---|---|
| 1 | `0x11` | 0-1 | 2 | **S/PDIF** (stereo L/R) -- matches the `0x11`x2 = S/PDIF read of the ADAT/`0x1a` pairing |
| 2 | `0x0b` | 1, 2 | (2) | **section marker, not I/O** -- see below |
| 3 | `0x1b` | 0 | 1 | singleton, grouped with the digital inputs |
| 4 | `0x1a` | 0-15 | 16 | **ADAT** -- confirmed (matches the 16-ch / 8-pair ADAT link+gain space) |
| 5 | `0x03` | 0-14 | 15 | unmapped -- see candidates below |
| 6 | `0x04` | 0-3 | 4 | unmapped -- each entry is followed by its own `0x0b` index-3 marker (no other category does this) |
| 7 | `0x0a` | 0 | 1 | singleton |
| 8 | `0x15` | 0 | 1 | singleton |
| 9 | `0x16` | 0 | 1 | singleton (emitted just before the 64-list, after a ~3.5 s gap) |
| 10 | `0x19` | 0-63 | 64 | unmapped -- almost certainly the 64-channel USB/Thunderbolt stream (this is the interface's headline I/O count); the routing command's first payload byte is `0x41`=65, consistent with a 1-based index into a 64-entry space |
| - | `0x0b` | 0, then 4 | (2) | closing section markers |

### `0x0b` is a phase/section marker, not an I/O category

Its 8 records carry index values `1, 2, 3, 3, 3, 3, 0, 4` and land only at
section boundaries (after S/PDIF; after ADAT starts; after each `0x04`
entry; before and after the `0x19` list). Treat it as structural.

### What's still unmapped

- **`0x19` = 64** -- best guess: the 64 USB/TB streaming channels. Fairly
  well-founded (matches the device spec and the routing index hint).
- **`0x03` = 15** and **`0x04` = 4** -- physical-I/O or routing-node
  groups; exact identity unknown. `0x04`=4 plausibly the headphone outs,
  monitor outs, or clock sources (Internal / ADAT / S/PDIF / Word Clock);
  `0x03`=15 has no obvious match. Don't guess in code.
- **Singletons `0x1b` / `0x0a` / `0x15` / `0x16`** -- single-instance
  subsystems (word clock? internal talkback mic? oscillator? monitor
  controller?). Not distinguishable from this capture.

To actually name these: capture the USB **control transfers** during
connect (string descriptors), or match the counts against the labels in
the Launcher's routing tab.

It carries **indices, not values** -- useless for reading current
settings. Mainly documented so tools stop flagging `0x74` as unknown and
so a future string-descriptor capture has something to line up against.

---

## 5. State report (`0x73`) byte-map

Only the bytes that are understood are listed. "Formula" columns give the
offset for target *N*.

| Offset(s) | Field | Formula / encoding | Status |
|---|---|---|---|
| 0 | magic `0x73` | | confirmed |
| 4-7 | header `0x40 0x01 0x00 0x00` | (meaning unknown, constant) | - |
| 17, 19 | *Launcher-handshake blip* | one byte each, `0x08->0x00` / `0x06->0x00`, ~3.0 s after the Launcher starts (incl. the no-user INIT capture) | startup noise, ignore |
| 24 | output_trim target 0 | `value << 4` (bits 4-6) | confirmed |
| 25 | output_trim targets 1 & 2 | t1 = `value << 2` (bits 2-4); t2 = `value << 5` (bits 5-7) | confirmed |
| 28-45 | **bus_block** -- 6 buses x 3 bytes | bus *N*: level @ `28+3N`, status @ `29+3N`, reserved @ `30+3N` | confirmed |
| 37 / 38 | bus 3 (line_out) level / status | (= the `28+3N` formula, N=3) | confirmed |
| 40 / 41 | bus 4 (reamp) level / status | (N=4) | confirmed |
| 49-60 | **channel gain array** -- 12 physical inputs | channel *N* gain @ `49+N`, int8 two's-complement dB | confirmed |
| 61-72 | **channel status array** -- 12 physical inputs | channel *N* status @ `61+N` (bitfield, section 6) | confirmed |
| 73 | **talkback status** | packed bitfield (section 6 / section 7) | confirmed |
| 74 | **talkback gain** | 0-96, gain of the currently-selected talkback source | confirmed |
| 75-90 | **ADAT gain array** -- 16 ADAT channels | ADAT channel *N* (0-indexed) gain @ `75+N`, int8 dB, range -6..+12 | confirmed |
| 91-92 | **S/PDIF gain** -- L / R | ch 0 (L) @ `91`, ch 1 (R) @ `92`, int8 dB, range -6..+12 | confirmed |
| 139-140 | *startup ramp* | both bytes ramp to `0x60` in the first ~0.12 s of every capture (a nearby block, 129-136, does the same in INIT) | startup settling, ignore |
| 157-176, 221-232 | *embedded meter jitter* | free-runs `0x5a`<->`0x60` at rest; drops toward 0 on loud signal | unresolved (looks like a second meter copy) |

Layout is tight and sequential: gain array (49-60), status array (61-72),
talkback status+gain (73-74), ADAT gain array (75-90), S/PDIF gain (91-92)
-- no gaps.

---

## 6. Bitmask logic

### Channel status byte (offsets 61-72, one per physical input)

```
status_byte = (phase_invert << 6) | (phantom << 4) | (input_mode & 0x03)
```

| Field | Mask | Shift | Values |
|---|---|---|---|
| input_mode | `0x03` | 0 | 0=mic, 1=line, 2=hiz, 3=direct |
| phantom | `0x10` | 4 | 0/1 |
| phase_invert | `0x40` | 6 | 0/1 |

### Bus status byte (offset `29 + 3*bus_id`)

| Field | Mask | Shift |
|---|---|---|
| mute | `0x04` | 2 |
| dim | `0x08` | 3 |
| mono | `0x10` | 4 |

**`mute` bit is ambiguous.** `0x04` reads 1 both when the bus is
explicitly muted **and** whenever `bus_level == 96` (max), with no mute
command -- reproduced on buses 0, 3, 4 (2026-08). A reader must
special-case `level == 96`: at max level, treat `0x04` as "at unity", not
"muted", unless a mute was explicitly sent.

### Talkback status byte (offset 73)

Three sub-fields packed into one byte:

| Field | Mask | Shift | Meaning |
|---|---|---|---|
| source (low bits) | `0x03` | 0 | `talkback_source & 0x03` **only** -- high bits of the 0-12 index are not exposed |
| dest_assign | `0x3c` | 2 | bitmask, destination *N* assigned = bit `N+2` (dest0=`0x04`, dest1=`0x08`, dest2=`0x10`, dest3=`0x20`) |
| button | `0x40` | 6 | hold-to-talk active |

**Untested overlap:** the source low-bits (`0x03`) and dest0/dest1 assign
bits (`0x04`/`0x08`) are adjacent, and source index 4-12 sets bits 2-3
too. The talkback-select and talkback-bttn captures were separate sessions
(source was 0 during dest toggles; no dest during the source sweep), so
how this byte reads with talkback *fully* configured is unverified.

### Output trim packing (offsets 24-25)

| Target | Byte | Mask | Shift | Confirmed sweep |
|---|---|---|---|---|
| 0 (~ Monitor A trim) | 24 | `0x70` | 4 | `0x00,0x10,0x20,0x30,0x40,0x50,0x60` |
| 1 (~ Monitor B trim) | 25 | `0x1c` | 2 | `0x00,0x04,0x08,0x0c,0x10,0x14,0x18` |
| 2 (~ Line trim) | 25 | `0xe0` | 5 | `0x00,0x20,0x40,0x60,0x80,0xa0,0xc0` |

Readback value = `raw_bits >> shift` = the commanded value (0-6).
Spare bits: offset 24 bits 0-3 and 7; offset 25 bits 0-1. Offset 25 bits
0-1 (a 2-bit / 4-option field) is the likely home of **pan law**, which
was never actually captured.

---

## 7. Address spaces

The `channel` byte (offset 17) in a `SET_PARAM` frame is **not one
namespace**. Its meaning depends entirely on the param_id:

| When setting... | offset-17 byte is... | Range |
|---|---|---|
| gain / input_mode / phantom / phase_invert | physical input index | 0-11 |
| adat_gain | ADAT channel index | 0-15 |
| bus_level / bus_dim / bus_mute / bus_mono | **bus id** (see below) | 0-5 |
| output_trim | trim target | 0-2 |
| talkback_dest_assign | talkback destination | 0-3 |
| (talkback_button / _source / _gain use `0x12`, no target byte) | - | - |

For `SET_LINK` (`0x14`), offset **18** is a `pair_index`, not offset 17.

### Bus ids (all 6 identified, 2026-08)

Bus ids are **not** in UI order and **not** contiguous with channel
indices.

| Bus id | Name | Aliases | bus_block level offset |
|---|---|---|---|
| 0 | monitor_a | mona, mon_a | 28 |
| 1 | headphone_1 | hp1 | 31 |
| 2 | headphone_2 | hp2 | 34 |
| 3 | line_out | line, lineout | 37 |
| 4 | reamp | reamp_out, re-amp | 40 |
| 5 | monitor_b | monb, mon_b | 43 |

`master_volume` is not a distinct param -- it is bus 0's `bus_level`.

`bus_dim` / `bus_mono` were only exercised on 0/1/2/5 and may not apply to
line_out / reamp. `bus_mute` confirmed on 0/1/2/3.

The Orion III has **two** physical reamp outputs (Reamp 1 / Reamp 2 --
separate mono outs for two guitar amps, not a stereo pair). The settings
tab exposes one "Reamp" level slider (bus 4); whether Reamp 1 and 2 share
that level or have independent controls is untested.

### Physical channel link pairs

`pair_index = channel_index // 2` (0-indexed channels): pair 0 = ch1&ch2,
pair 1 = ch3&ch4, ... pair 5 = ch11&ch12. 6 pairs (index 0-5).

### SET_LINK `space` byte (offset 17)

`SET_LINK` frames carry a domain selector at **offset 17**:

| space @17 | domain | pair_index range |
|---|---|---|
| `0x00` | physical inputs **and** ADAT (shared) | physical 0-5, ADAT 0-7 |
| `0x01` | S/PDIF | 0 only (the L/R pair) |

Discovered from `spdif-gain-link` (2026-08). Previously this byte was
thought to be unused/always-0.

### ADAT link pairs

`pair_index = channel_index // 2` over the 16-channel ADAT space: 8 pairs
(0-7). Pairs 6 and 7 have no physical-channel equivalent.

**Behaviour is identical to the preamp link** (user-confirmed on hardware):
linked channels' gains move together, and -- as with the preamp -- the
*device* doesn't do that, the software sends a second `SET_PARAM(adat_gain)`
for the partner. `set-adat-gain` / `set-adat-link` replicate this.

**Still ambiguous with physical link.** Physical link and ADAT link *both*
use space `0x00`, and the physical-pair-0-ON and ADAT-pair-0-ON frames are
byte-for-byte identical across all 320 bytes + USB metadata. S/PDIF (space
`0x01`) is now unambiguous, but physical-vs-ADAT is not. Unknown: whether
one `SET_LINK(space=0, pair_index=N)` links pair N in *both* spaces. To
settle it: link a physical and an ADAT pair in one session with different
per-channel gains, or test on hardware.

### S/PDIF link pair

One L/R pair, `SET_LINK` with `space=0x01` / `pair_index=0x00`. Same
gain-mirroring behaviour as the preamp link; the CLI's `set-spdif-gain` /
`set-spdif-link` handle it. No cross-space ambiguity (distinct `space`).

### Routing matrix (partly decoded)

A 5th command shape: opcode `0x53`, param `0xd3` (`frame.routing_command`).

| byte | meaning |
|---|---|
| 16 | `0xd3` param |
| 17 | `0x41` constant |
| 18 | **destination** (see full map below) |
| 19 | **source bank** -- `0x00`=preamps, `0x02`=DAW/USB playback (24 ch), `0x03`=ADAT, `0x04`=S/PDIF, `0x0b`=**mute**, `0x0c`=oscillator. `0x01`, `0x05`-`0x0a` unseen. |
| 20 | **source index** within the bank, 0-based (preamp 1/6/12 → `0x00`/`0x05`/`0x0b`; ADAT 1/16 → `0x00`/`0x0f`; osc 1/2 → `0x00`/`0x01`) |
| 21+ | **a variable-length list**, not a fixed field -- see below |

**Destination map** (byte 18) -- confirmed from `matrix-compplay-allouts-1`:

| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| line out | HP1 | HP2 | Mon A | Mon B | Reamp | com rec | ADAT out | S/PDIF out | AFX in | mix ch1 | mix ch2 | mix ch3 | mix ch4 | surround in |

**The frame is a group dump, not a single crosspoint.** After byte 20 comes
a variable-length list of 2-byte entries describing the *whole destination
group's* per-channel state. Simple destinations → 1 entry (HP1 → `02 00`,
Reamp → `00 02`, S/PDIF out → `04 01`); big groups → 15-30 entries (ADAT
out → 15× `03 NN` for NN=1..15). The entries look like
`(source_bank, channel)` pairs but aren't decoded. Bytes 19-20 are the
source the user picked; the list is the resulting state. Decoding it needs
captures that change **one channel of a small destination** at a time.

**Routing is exclusive** (one source per output; replacing sends no remove
frame) and **idempotent** (routing an already-present source sends nothing
at all -- that's why HP1/HP2/Mon A/Mon B/mix ch4 produced no frame in the
enumeration capture). Summing is via separate "virtual mixes".

**The matrix is all-mono** -- HP1 L and HP1 R are separate targets. The
mono-output selector is somewhere in the list, still not isolated.

Also open: source banks `0x01`, `0x05`-`0x0a`; the list structure.

**Output mute and oscillator-insert both go through this frame** (bank
`0x0b` and `0x0c`, right-click in the matrix). Un-mute = re-assign a real
source. The settings-tab oscillator panel is separate and sends nothing
(§11). **Talkback is NOT a matrix source** -- its 4 destination toggles
(Mon A / Mon B / HP1 / HP2, which combine) use `talkback_dest_assign`
(`0x13` / `0x5d`).

**No `0x73` readback** -- routing state is invisible in the state report,
same as channel link.

---

## 8. Channel link -- behaviour

`SET_LINK` (`0x14` / `0xa2`, `space` @17, `pair_index` @18, `enabled` @19)
engages a real link flag **on the device** -- visible on the Orion's own front
panel. But:

- **The firmware does NOT propagate mode/gain/phantom/phase across a
  linked pair.** Every bit of "syncing" you see is the official Launcher
  sending extra `SET_PARAM` commands.
  - On link engage: the Launcher pushes the higher-numbered channel's
    mode + gain to match the lower one.
  - While linked: every gain / phantom / phase_invert change is sent
    **twice** by the Launcher, once per channel (~2 ms apart, same value).
  - `input_mode` cannot be changed while linked (Launcher greys it out).
    Workflow: unlink -> set mode per channel (gain resets to the new
    mode's range) -> re-link.
- **No link-enabled bit has been found in the `0x73` report.** Diffing
  the state report immediately before/after link toggles shows zero
  changed bytes. Link readback may not exist; track it client-side.

Any non-Launcher controller must replicate the two-commands-per-change
behaviour itself if it wants Launcher-equivalent results.

---

## 9. Meter calibration (`0x75` report)

Raw meter byte at offset `32 + channel_index`. Inverted scale.

### dB curve (channel 0 only, applied to all 12)

`raw_byte == -dBFS`, essentially exactly, across 0 to -60 dB:

| raw | dBFS |
|---|---|
| 0 | 0 |
| 10 | -10 |
| 12 | -12 |
| 20 | -20 |
| 30 | -30 |
| 40 | -40 |
| 60 | -60 |

Not swept below -60 dB (one stray raw=72 point at deep silence doesn't fit
the line). Not independently verified past channel 0, but the offset
formula holds for all 12 so the curve probably does too.

### LED colour thresholds

| Band | Range | Colour |
|---|---|---|
| clip | >= 0 dB | red (only at clip) |
| | -4 .. 0 dB | orange |
| | -12 .. -4 dB | yellow |
| | < -12 dB | green |

No separate solid-red band below clip -- orange runs straight to 0 dB.

---

## 10. Parameter reference

| Param | id | Opcode | Target (@17) | Value (@18, or @17 for `0x12`) | Readback |
|---|---|---|---|---|---|
| input_mode | `0x4f` | `0x13` | channel 0-11 | 0=mic,1=line,2=hiz,3=direct | status byte bits 0-1 |
| gain | `0x50` | `0x13` | channel 0-11 | int8 dB (range per mode: mic 0..75, line -6..20, hiz 0..65, direct 0..20) | gain array `49+ch` |
| phantom | `0x51` | `0x13` | channel 0-11 | 0/1 (mic mode only) | status byte bit 4 |
| phase_invert | `0x52` | `0x13` | channel 0-11 | 0/1 | status byte bit 6 |
| adat_gain | `0x5b` | `0x13` | ADAT ch 0-15 | int8 dB, -6..+12 | ADAT gain array `75+ch` |
| bus_level | `0x47` | `0x13` | bus id 0-5 | 0-96 (0=-inf, 96=0dB) | bus_block level `28+3N` |
| bus_dim | `0x68` | `0x13` | bus id | 0/1 | bus status bit 3 |
| bus_mute | `0x48` | `0x13` | bus id | 0/1 | bus status bit 2 (ambiguous, section 6) |
| bus_mono | `0x69` | `0x13` | bus id | 0/1 | bus status bit 4 |
| output_trim | `0x4b` | `0x13` | target 0-2 | 0-6 | offsets 24-25 (section 6) |
| spdif_gain | `0x5c` | `0x13` | S/PDIF ch (0=L, 1=R) | int8 dB, -6..+12 | offset `91` (L) / `92` (R) |
| channel_link | `0xa2` | `0x14` | space=0 @17, pair_index @18 (0-5) | enabled @19 | none found |
| adat_channel_link | `0xa2` | `0x14` | space=0 @17, pair_index @18 (0-7) | enabled @19 | none found (gain bytes track together; preamp-link behaviour, CLI mirrors gain) |
| spdif_channel_link | `0xa2` | `0x14` | **space=1** @17, pair_index @18 (0) | enabled @19 | none found (L/R gain bytes track together; CLI mirrors gain) |
| talkback_button | `0x1f` | `0x12` | - | 1=press, 0=release @17 | offset 73 bit 6 |
| talkback_source | `0x27` | `0x12` | - | 0-12 @17 -- `0` = INT (built-in talkback mic behind the physical TB button), `1-12` = preamps 1-12 (user-confirmed) | offset 73 bits 0-1 (low bits only) |
| talkback_gain | `0x20` | `0x12` | - | 0-96 @17 (per selected source) | offset 74 |
| talkback_dest_assign | `0x5d` | `0x13` | dest 0-3 = Mon A / Mon B / HP1 / HP2 (menu toggles, not the matrix) | 0/1 @18 | offset 73 bits 2-5 |
| routing | `0xd3` | `0x53` | ? | multi-byte, undecoded | ? |
| surround_eq (pre/post?) | `0xeb` | `0xab` | - | bit 7 of payload byte @19, rest undecoded | none in `0x73` |
| oscillator (matrix insert) | `0xd3` | `0x53` | routing frame, source bank `0x0c` idx 0/1 = osc 1/2 (§7) | none |
| oscillator (settings panel: freq/level/mute) | - | - | host-side, sends nothing (§11) | none |

---

## 11. Settings window -- device-side vs host-side

What the Settings/Device window controls actually do, from the captures
(all Windows-VM Launcher + USBPcap, 2026-08):

| Feature | Capture | Device traffic | Verdict |
|---|---|---|---|
| **Line-out level + mute** | `settings-linevol-...` | `bus_level` `0x47` / `bus_mute` `0x48` on **bus 3** | **real, confirmed** -- in CLI (`set-bus-level line` / `set-bus-mute line`) |
| **Reamp-out level** | `settings-linevol-...` | `bus_level` `0x47` on **bus 4** | **real, confirmed** -- in CLI (`set-bus-level reamp`) |
| **Output trim** (Mon A / Mon B / Line) | `settings-trim-...` | param `0x4b`, 20 frames | **real, confirmed** -- readback @24-25 (section 6); not yet in CLI |
| **Surround-EQ pre/post** | `settings-scrbrght-surroundEQ` | opcode `0xab` / param `0xeb`, **2 frames** | **real command exists** -- layout undecoded, no `0x73` readback |
| Pan law | `settings-trim-...` | none (not sent in that capture) | unknown -- recapture |
| **Oscillator** -- matrix insert | `matrix-source-enum` | `0x53` routing frame, source bank `0x0c` | **real device command** (§7) |
| **Oscillator** -- settings panel (freq/level/mute) | `settings-osc1-2-fq-lvl` | **zero frames** | host-side or uncaptured |
| **Screen brightness** | `settings-scrbrght-surroundEQ` | **zero frames** | host-side *in the VM* -- but see below, it works on native macOS |
| **Thunderbolt / latency / DC-coupling** | `settigs-thunderb-lat-dccp` | **zero frames** | host driver settings; TB is inactive while connected over USB, so this tab does nothing in this setup |

So the Settings window is a genuine mix: output levels/mute, the three
trims, and surround-EQ pre/post are real device commands; the oscillator
and (at least under the VM) screen brightness and latency are host-side.

### Oscillator -- two access points

**In the routing matrix:** right-click an output → insert oscillator. It
becomes a matrix source, bank `0x0c` (idx 0/1 = oscillator 1/2), sent as
the normal `0x53` routing frame (confirmed, §7). So *inserting* an
oscillator into an output IS a real device command.

**The settings-tab oscillator panel** (freq 1kHz/400Hz, level 0..−18 dBFS,
mute): `settings-osc1-2-fq-lvl.pcapng` had **zero** outgoing frames over
27.7 s. So the per-signal parameters are configured host-side or via an
uncaptured path -- only the matrix "insert into output" half is confirmed.

### Screen brightness -- VM shows nothing, macOS works

`settings-scrbrght-surroundEQ.pcapng` sent nothing for the brightness
slider. **But the user reports brightness *does* work from the native
macOS Launcher** (and doesn't change at all under the VM). USBPcap on the
same capture did catch the 2 surround-EQ frames, so it's not a
lost-OUT-transfer problem -- more likely the VM's Launcher build no-ops
brightness when it can't fully talk to the hardware, or that build just
doesn't implement it. **A native macOS USB capture is the way to settle
this** (and would also re-check the oscillator / thunderbolt findings
against a Launcher build where everything works). Capture with **no size
filter** so nothing like the `0xab` frames gets dropped.

### Surround-EQ

The one Settings-window control here that does talk to the device:
opcode `0xab` / param `0xeb` (a 5th command shape), 2 frames, bit 7 of
payload byte @19 toggles. No `0x73` effect. Needs a dedicated capture to
decode the `0xab` layout.

### Thunderbolt / latency / DC-coupling

`settigs-thunderb-lat-dccp.pcapng` -- zero outgoing frames. Latency/buffer
is a host driver setting. Thunderbolt is inactive over USB. DC-coupling
*should* be hardware but wasn't exercised (or is TB-gated) -- worth an
isolated recapture, ideally on macOS.

---

## 12. Open questions

| Item | Status |
|---|---|
| Routing frame (`0x53` / `0xd3`) | **partly decoded** (§7): destination `@18`, source bank `@19` + index `@20`, op `@21` all confirmed; routing is exclusive. Open: the destination sub-channel (L/R) byte, bank `0x0b` (mute?), remaining source banks. No state readback. |
| ADAT vs physical `SET_LINK` | both use `space` byte `0x00` -- byte-identical frames (§7). S/PDIF (space `0x01`) is now distinguishable. Open: does one space-0 command link pair N in *both* physical and ADAT? Needs different per-channel gains or a hardware test |
| Pan law | never captured; likely offset 25 bits 0-1 |
| S/PDIF gain + link | **confirmed** (`spdif-gain-link`, 2026-08): gain param `0x5c`, readback `91`/`92`, link via `space=1`. In the CLI. |
| Oscillator | matrix insert is a real command (routing bank `0x0c`, §7); the settings-panel freq/level/mute sends nothing |
| Screen brightness | resolved -- sends nothing (host-side or not persisted) |
| Surround-EQ pre/post | new opcode `0xab` / param `0xeb` seen (2 frames); layout undecoded, no `0x73` effect |
| Thunderbolt / latency / DC-coupling | zero outgoing frames -- host-side, or not exercised |
| Offsets 17 / 19 blip | ~3.0 s after the Launcher starts, in every capture **including the no-user-interaction INIT capture** -- Launcher handshake event, not user- or feature-related. Ignore. |
| Offsets 139-140 ramp (129-136 in INIT) | first ~0.12 s of every capture -- device/connection startup settling. Ignore. |
| Offsets 157-176 / 221-232 | free-running meter data embedded in the state report; exact byte->channel mapping not pinned down (cross-check against `0x75` offsets 32-43) |
| Channel-link readback bit | none found; may not exist |
| dB curve past -60 dB, and per-channel | only channel 0, only to -60 dB |
| `0x74` groups `0x19`(64)/`0x03`(15)/`0x04`(4) + singletons | counts + order known (section 4); **names are in no capture on file** -- need a fresh string-descriptor capture or the Launcher routing-tab labels. `0x19`=64 is probably the USB/TB channel stream |
| `bus_block` reserved byte (`30+3N`) | never changed -- padding or unexercised |
| Orion hidraw write length | 320 or 321 bytes? -- `transport.py` writes 320; unverified against Orion's HID descriptor (section 13) |
| Orion gain clamp vs reject | unknown -- the Discrete 8 Pro clamps out-of-range gain; Orion's behaviour untested |

---

## 13. Device family / cross-device notes

Antelope **Synergy Core** interfaces share this HID protocol family (magic
`0x70` command, opcode @4, param_id @16). A peer got an **Antelope Discrete
8 Pro** working with this same driver -- see
`profiles/discrete_8_pro_synergy_core.json` (contributed by PR). Param IDs
are shared; **semantics are not guaranteed to be.** The lessons from that
sibling device, folded into `orion_studio_3.json` as `family_notes`,
`constraints`, and `hazards`:

### Safety (precautionary on Orion -- confirmed on the Discrete 8 Pro, cost a physical power cycle each)

- **Never blind-sweep opcodes.** On the Discrete 8 Pro, opcodes `0x01` and
  `0x02` wedged the USB controller unrecoverably (driver rebind and kernel
  port power-cycle both failed; only unplugging the unit's power worked).
  Send only `constraints.allowed_opcodes` (`0x12`/`0x13`/`0x14`).
- **Out-of-range channel index → firmware BusFault** on the Discrete 8 Pro
  (needs a power cycle). Bound-check against the *right* space: 0-11 for
  channel params, 0-15 for ADAT, `0-5` bus ids for bus params -- and
  *refuse*, don't clamp. (Orion's CLI currently only warns; that's too
  loose given the sibling behaviour.)
- **Enum values are not portable.** `input_mode = 3` is "direct" on Orion
  (fine here) but **crashed the Discrete 8 Pro's firmware** (no direct
  mode). Never pass one device's enum through another's code path.

### Protocol nuances (verify on Orion)

- **HID write length.** The Discrete 8 Pro's report descriptor has no
  Report ID, so Linux hidraw writes there must be **321 bytes** (leading
  `0x00` + 320 payload). `transport.py` writes 320 for Orion with no
  prefix. Check `cat /sys/class/hidraw/hidrawN/device/report_descriptor`
  for a Report ID item (`0x85 ...`); if absent, Orion needs the prefix too.
- **Outgoing byte 0 is cosmetic.** On the Discrete 8 Pro, byte 0 of a
  command is ignored (offset 4 is the discriminator). `0x70` is written
  for family consistency. "Byte 0 = the magic" is a property of the
  *incoming* reports (`0x73`/`0x75`/`0x74`), not the command.
- **`0x61` error frame.** The Discrete 8 Pro replies `0x61` (status @4,
  `0x10` = "unknown opcode") **only** for an unrecognised opcode; a
  recognised opcode gets **silence**. Silence ≠ success (its `0x14` was
  silent and did nothing). Never seen in an Orion capture, but watch for
  it if you probe an opcode. See `frame.error_response`.

### Encoding / range divergences (do not assume they match)

| Param | Orion | Discrete 8 Pro |
|---|---|---|
| `bus_level` `0x47` | `0-96`, `96` = 0 dB unity | plain: value `N` = `-N` dB |
| `gain` `0x50` mic | `0..75` | `-12..65` |
| `gain` `0x50` hiz | `0..65` | `0..40` |
| `gain` `0x50` line | `-6..20` | `-6..20` (same) |
| `input_mode` `0x4f` | `0-3` (incl. direct) | `0-2` (3 = crash) |
| out-of-range `gain` | untested (reject? clamp?) | device clamps to mode range |
| `channel_link` frame | works (frame.link_command) | frame shape does **not** link a pair |
| min write interval | ~20 ms fine (Launcher does ~30-80) | ~250 ms |
