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
| Report size | **320 bytes**, fixed, both directions (but see §14 -- Linux hidraw writes may need a leading `0x00`, making them 321; unverified on Orion) |
| Control OUT endpoint | `0x01` (host -> device commands), interrupt |
| Control IN endpoint | `0x82` (device -> host reports), interrupt |
| Audio stream endpoints | `0x05` OUT / `0x84` IN, isochronous, 24-ch / 24-bit in the class-compliant descriptor -- **unrelated to control** |
| Device address | 2 (`usb.dst 1.2.x` in the captures) |
| Poll interval | 4 ms |
| GET / query opcode | **none, and none possible** -- the HID report descriptor (54 B, dumped via `tools/hid_probe.py`) has no Feature report and no report IDs, and the device STALLs every control-pipe `GET_REPORT`. State is only ever read passively from the `0x73`/`0x74`/`0x75` IN reports the device streams -- and routing / mixer / AuraVerb are **not in any of them** (write-only over USB). |
| String descriptors | **never fetched in any capture on file** -- so no channel/bus/category names are recoverable from the USB traffic |

Byte 0 of every **incoming** report is a **magic** that identifies the
frame type. On **outgoing** commands byte 0 (`0x70`) is cosmetic -- the
sibling Discrete 8 Pro ignores it entirely; the opcode at offset 4 is the
real discriminator (§14).

---

## 2. Outgoing command frames (magic `0x70`)

Seven opcodes are known. The opcode is at **offset 4**. The param_id is at
**offset 16** for all of them. What comes after offset 16 depends on the
opcode -- this is the single most important thing to get right:

| Opcode @4 | Name | param_id @16 | Payload | Used by |
|---|---|---|---|---|
| `0x13` | SET_PARAM | param | `channel` @17, `value` @18 | gain, input_mode, phantom, phase_invert, adat_gain, bus_level/dim/mute/mono, output_trim, talkback_dest_assign |
| `0x12` | SET_GLOBAL | param | `value` @17 (no channel byte; @18 unused) | talkback_button, talkback_source, talkback_gain, screen_brightness (`0x0e`), sample_rate (`0x03`) |
| `0x14` | SET_LINK | `0xa2` (fixed) | `space` @17 (0 = physical+ADAT, 1 = S/PDIF, **3 = mixer**), `pair_index` @18, `enabled` @19 | channel_link, adat_channel_link, spdif_channel_link, mix_channel_link |
| `0x17` | SET_MIX | `0xd4` | `0x05` @17 (const), `mix` @18, `channel` @19, `fader` @20, `pan+flags` @21, `send` @22 -- see §12 | virtual mixer (Mix 1-4) |
| `0x17` | SET_MIC_MODELING | `0xe5` | `0x05` @17 (const), `channel` @18 (0-based idx − 4), `enabled` @19, `model` @20, `swap` @21, `pattern` @22 -- see §12 | mic modeling / emuMic (preamps 7-12) |
| `0x1d` | SET_AURAVERB | `0xda` | 8 DSP params (Room Size @19, Color @20, Pre-Delay @21, Early Ref Gain @23, Late Ref Delay @24, Richness @25, Reverb Time @26, Reverb Level @27, each 0-100), `enabled` @28 | AuraVerb (Mix 1) |
| `0x53` | SET_ROUTE | `0xd3` | `0x41` @17 (const), `destination` @18, then a `(bank,index)` pair per output channel from @19 (stride 2) -- see §7 | routing matrix |
| `0xab` | (surround-EQ?) | `0xeb` | `99 b0 <flags@19> 06 00 58 02` (@17..23), **barely decoded** -- 2 frames, bit 7 of @19 is the toggle | surround-EQ pre/post (probably) |

Notes:
- **`0x17` is overloaded** -- the param_id at @16 is the real discriminator:
  `0xd4` = virtual mixer, `0xe5` = mic modeling. Same `0x05` sub-cmd byte
  at @17.
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
magics (plus `0x74` in the INIT captures -- Windows `AntelopeINIT` and the
four macOS `macos-antelopeINIT-*`). There is no hidden fourth report type
carrying link state, oscillator state, routing state, etc.

**Connect handshake (cross-platform confirmed).** The Launcher's entire
host→device init traffic is a single frame:
`SET_PARAM(param 0x49, channel 1, value 0)` -- seen in the Windows
`AntelopeINIT.tsv` and in all four macOS INIT captures. The device answers
with the `0x74` enumeration burst + normal `0x73`/`0x75` polling. A
just-connected Launcher may also send a short `SET_PARAM(gain 0x50)` step
sequence on the first channels -- in `on2` that was the user nudging the
gain sliders to force the (buggy) Launcher to flush state, not a device
or handshake behaviour.

**macOS capture format.** Native-macOS (Darwin "XHC") pcapng: each vendor
HID report is a 40-byte Darwin pseudo-header + 320-byte payload =
`frame.len == 360`; payload byte 0 is the usual magic. Header byte 30 =
endpoint (`0x01` OUT / `0x82` IN); VID/PID at header bytes 36-39. The
`0x74` enumeration arrives on IN endpoint 1, `0x73`/`0x75` on IN endpoint
2. tshark's `usb.src`/`usb.dst` direction labels are unreliable here --
discriminate outgoing frames by magic `0x70` + opcode instead.

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
| 18 | **sample rate** | index 0-6 (0=32k, 1=44.1k, 2=48k, 3=88.2k, 4=96k, 5=176.4k, 6=192k) | confirmed (`macos-smplrt-...`) |
| 21-23, 27 | clock / PLL / buffer state | only move at the 88.2k & 176.4k steps; 27 halves 16→8→4 | undecoded (§13) |
| 24 | output_trim target 0 | `value << 4` (bits 4-6) | confirmed |
| 25 | output_trim targets 1 & 2 | t1 = `value << 2` (bits 2-4); t2 = `value << 5` (bits 5-7) | confirmed |
| 26 | **screen brightness** | plain byte, 0-100 (= commanded value) | confirmed (`macos-scrbrght-0-100-50-multvalue`) |
| 27 | (unmapped) | -- | -- |
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
| `0x03` | virtual mixer (Mix 1-4 strips) | `channel // 2` (§12) |

`0x01` discovered from `spdif-gain-link`, `0x03` from
`macos-mix1-send-pan-fader-mute-solo-link` (both 2026-08). Previously this
byte was thought to be unused/always-0. `0x02` unseen.

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

### Routing matrix (frame model decoded, 2026-08)

A distinct command shape (not the SET_PARAM layout): opcode `0x53`, param `0xd3` (`frame.routing_command`).

```
d3 41 <dest> | <bank0> <idx0> | <bank1> <idx1> | <bank2> <idx2> | ...
```

| byte | meaning |
|---|---|
| 16 | `0xd3` param |
| 17 | `0x41` constant |
| 18 | **destination group** (see map below) |
| 19 + 2·c | **source bank** for output channel `c` of that group |
| 20 + 2·c | **source index** for output channel `c`, 0-based within the bank |

The frame after byte 18 is a **plain array of `(source_bank, source_index)`
pairs, one per output channel of the destination group** -- channel 0 = L /
output 1 / Reamp 1, channel 1 = R / output 2 / Reamp 2. Multichannel groups
(line out, ADAT out = 16, mix channels, …) just have more pairs. There is
**no separate op code** and **no "no source"** -- to clear a channel you
route the **mute** pseudo-source (`bank 0x0b, idx 0x00`).

**The whole group is always sent.** To change one channel you resend every
channel of that group -- the changed one plus the others unchanged. There
is no single-channel frame.

**Source banks** (`frame.routing_command.source_banks`):

| bank | source | index |
|---|---|---|
| `0x00` | preamps | 0-11 |
| `0x01` | **emumic** -- the mic-modeling DSP output (wet tap; the DSP is `0x17`/`0xe5`, §12) | 0-7 = preamps 5-12 (the Launcher numbers them by preamp; EMU button only on 7-12, so idx 0-1 are configless) |
| `0x02` | **compplay** (Computer Playback / USB) | 0-23 on the VM driver, 0-31 on native macOS |
| `0x03` | ADAT in | 0-15 |
| `0x04` | S/PDIF in | 0-1 (L/R) |
| `0x05` | **AFX out** (Synergy Core FX returns) | 0-31 |
| `0x06`-`0x09` | **mix 1-4** (virtual mixes) | 0/1 = L/R |
| `0x0a` | **surround out** | 0-15 |
| `0x0b` | **mute** pseudo-source | 0 |
| `0x0c` | oscillator | 0/1 |

`0x05`-`0x0a` decoded 2026-08 from `macos-matrix-afx1-19-to-line1-...`
(AFX 1-19 → idx `0x00`-`0x12`, 29-32 → `0x1c`-`0x1f`),
`macos-matrix-mix1234-lineo1-invphch6` (mix 1/2/3/4 → banks `0x06`/`0x07`/
`0x08`/`0x09`, each idx 0/1 = L/R), `macos-matrix-surrnd1-16-to-lineo1`
(surround 1-16 → bank `0x0a` idx `0x00`-`0x0f`). Bank `0x01` (emumic)
confirmed 2026-08-31 from `emumic-5to 12` (Windows KVM): emumic routed
into line-out ch 1-8 one at a time → pairs `(0x01, 0)`…`(0x01, 7)`. The
Launcher lists emumic as *preamps 5-12*, so `0x01` idx = preamp − 5. The
front-panel EMU button is only on preamps 7-12, so idx 0-1 (preamps 5-6)
are selectable matrix sources with no model UI -- a Launcher bug or
unfinished feature; **untested** whether the card outputs audio there.
**All 12 source banks are now identified.**

**Destination map** (byte 18) -- confirmed from `matrix-compplay-allouts-1`:

| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| line out | HP1 | HP2 | Mon A | Mon B | Reamp | com rec | ADAT out | S/PDIF out | AFX in | mix ch1 | mix ch2 | mix ch3 | mix ch4 | surround in |

**Evidence** (`macos-matrix-ch1-12-mute-hp1L` / `-hp1R`, 2026-08):

- hp1L: swept preamp 1-12 into **HP1 L**. Every frame `d3 41 01 | 00 (n-1)
  | 00 02` -- `[19][20]` = the changing L source, `[21][22]` = `(0x00,
  0x02)` = **preamp 3** = HP1 R's *untouched* source.
- hp1R: then swept preamp 1-12 into **HP1 R**. Every frame `d3 41 01 | 0b
  00 | 00 (n-1)` -- `[19][20]` = `(0x0b, 0)` = **mute** (HP1 L, left muted
  by hp1L's last frame), `[21][22]` = the changing R source.
- The two captures are sequential and the L=mute state carries between
  them -- decisive.
- Final mutes: hp1L → `d3 41 01 | 0b 00 | 00 02` (mute L, keep R); hp1R →
  `d3 41 01 | 0b 00 | 0b 00` (mute both).

> **This corrects the old model.** Bytes 21-22 were previously read as op
> codes: `02 01` = "output 1", `00 02` = "output 2". Wrong -- `00 02` is
> literally `(bank 0x00, index 0x02)` = preamp 3, the *other channel's*
> routing. The old CLI shipped this: `route hp1 R preamp4` put preamp4 in
> the L slot and preamp3 in R, so the Launcher showed HP1 L=preamp4,
> R=preamp3 (user-observed, 2026-08). Fixed.

**Line out = a 16-channel destination group** (byte 18 = `0x00`).
Confirmed from the `afx*`/`surrnd*`/`mix1234*` captures: each frame is
`d3 41 00 <bank0> <idx0> | <bank1> <idx1> | ... | <bank15> <idx15>` --
channel 0 (the one being changed) then the other 15 untouched, ending at
byte 50. (A channel routed to `(bank 0, idx 0)` would read as `00 00` and
be invisible, but 16 matches the Launcher's matrix.) In those captures
channels 1-15 held preamp 2-12 then compplay 1-4 -- whatever the user had
set, not a fixed default.

**CLI:** `route <dest> <chan> <source>` sets one output channel (1-based;
`L`/`R` = 1/2 for `stereo_destinations`) and resends the rest from the
local cache; `route <dest> all <s1>...<sN>` sets the whole group;
`route <dest> mute` / `route <dest> <chan> mute` mute. In `all`, a range
token like `compplay1..16` expands to N sequential sources (so a 16-ch
seed is one line). Wired dests: `line_out` (16) + hp1/hp2/mona/monb/reamp
(2). Like the Launcher there is **no un-route**. `0x53` is in
`constraints.allowed_opcodes`. **Hardware round-trip confirmed
(2026-08-31)** for every wired dest -- preamps->hp1/hp2 and a seeded
16-ch line_out both persisted correctly in the Windows Launcher.

**Other multichannel destinations** (ADAT out, com rec, AFX in, the mix
channels, surround in) use the same array; their channel counts aren't
captured yet. Old note that adat_out is "15× `03 NN`" fits the array model
exactly: entry 0 = the changed channel, entries 1-15 =
`(0x03, 1..15)` = the ADAT-in passthrough left untouched.

**Routing is exclusive** per channel (one source per output channel) and
**idempotent** (routing an already-present source sends nothing). Summing
is via separate "virtual mixes".

All 12 source banks are now identified (bank `0x01` = emumic, idx 0-7 =
preamps 5-12, confirmed 2026-08-31). Still open: the channel counts of
the ADAT out / com rec / AFX in / mix / surround-in destinations.

**Output mute and oscillator-insert both go through this frame** (bank
`0x0b` and `0x0c`, right-click in the matrix). Un-mute = re-assign a real
source. The settings-tab oscillator panel is separate and sends nothing
(§11). **Talkback is NOT a matrix source** -- its 4 destination toggles
(Mon A / Mon B / HP1 / HP2, which combine) use `talkback_dest_assign`
(`0x13` / `0x5d`).

**There is no USB routing readback. This is now near-certain (2026-08-31),
not just "not found yet":**

- **The HID report descriptor forbids it.** Dumped from Linux hidraw
  (`tools/hid_probe.py`), the interface 3 report descriptor is 54 bytes
  and declares **exactly one 320-byte Input report and one 320-byte
  Output report -- no Feature report, no report IDs**. The device
  **STALLs (EPIPE) every control-pipe `GET_REPORT`** -- both
  `GET_FEATURE` and `GET_REPORT(Input)`, at every length tried. So the
  only thing the device ever sends is the unsolicited `0x73`/`0x74`/`0x75`
  interrupt stream, and none of those carry routing (verified full-width
  on the on2/on3 diff pair and every `matrix-*` capture).
- **UAC2 can't carry it either** -- the audio-control interface is a stub
  (1 clock, 4 terminals, no Feature/Selector/Mixer units).
- **Loading a preset is pure push.** `macos-session-load-pre-afx-to-line`
  (8 preset loads): each is `SET_GLOBAL(0x2c, 1)` → the `0x53` routing
  frame(s) → `SET_GLOBAL(0x2c, 0)` (a batch/edit-lock marker,
  `params.routing_batch_marker`), plus gain frames. The Launcher **never
  queries** -- it writes the file's contents.
- **Cross-machine persistence** (the original reason to expect a readback)
  is real -- the device stores routing in NVRAM (front panel; survives a
  power cycle) -- but the *host-to-host* agreement the user saw is almost
  certainly the **Antelope Launcher's own account/session sync**
  (server-side), not a device→host report.

**Last stone -- the offline-persistence test.** With **WiFi off**, change
routing in the Launcher on one OS, then reboot to the other (macOS ↔
Windows VM), still offline, and check whether the routing carried over.
(Also: change a route from the device's own front panel with no computer,
then open a fresh offline Launcher.) If routing persists **offline** →
the device really does report it to the host, and there is a vendor
request to find (CAPTURE E′, filtered to VID `0x23e5`). If it only
persists **online** → it is Antelope-account sync, there is **no device
readback**, and the CLI cache is the correct and only design (the
Launcher holds session state the same way).

*(Note: our macOS captures were never filtered to the Antelope -- the
`session-load` capture is full of a Realtek USB SSD, a Logitech mouse and
a Keychron keyboard on other endpoints. None of that is Antelope. Filter
future captures to `usb.idVendor == 0x23e5`.)*

What CAPTURE E ruled out is the **connect handshake**. The macOS
`macos-antelopeINIT-poweroff-on2/on3` captures: device powered fully off,
Launcher quit, start recording, launch Launcher, power on device. on2 and
on3 had **deliberately different LineOut routing** (preamp 1-12 vs
comp-play, swapped). Diffing the two complete connect sequences:

- `0x73` state report -- final states differ only at offset 50 (one
  preamp gain byte, unrelated) and free-running meter-noise offsets. No
  routing.
- `0x74` topology enumeration -- **byte-identical** between the two
  (indices only, as always).
- USB control transfers (EP0) -- byte-identical: plain descriptors
  (device / config / strings "Orion Studio III" etc / UAC2). No routing.
- 48-byte HID interface -- only idle keepalives. No routing.
- Outgoing commands -- the *entire* host→device handshake is **one**
  frame: `SET_PARAM(param 0x49, channel 1, value 0)` (present in all four
  macOS INIT captures; matches the lone `0x49` in the Windows
  `AntelopeINIT.tsv` -- now cross-platform confirmed). on2 additionally
  had an 18-frame `SET_PARAM(gain 0x50)` step sequence on ch0/ch1 -- the
  user deliberately wiggling the gain sliders to force Antelope's buggy
  Launcher to actually flush state to the device (their words: gain,
  phase-invert and phantom are "more solid"; routing changes sometimes
  don't register). Not device behaviour, not routing. **No `0x53`, no
  routing query.**

So at connect the Launcher neither reads routing from the device nor
pushes cached routing. Combined with the HID-descriptor finding above,
the conclusion is that **there is no routing readback over USB** -- pending
only the front-panel test. See `params.routing.readback`.

`matrix-status` is a local cache and goes stale if routing is changed
outside this CLI -- and that is a permanent property of the device, not a
gap to be closed.

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
  - While linked: every gain / phantom / phase_invert change *made in the
    Launcher UI* is sent **twice**, once per channel (~2 ms apart).
  - **Turning the physical gain wheel** on a linked channel moves *only
    that channel* (user-confirmed) -- the wheel bypasses host software, so
    this is the cleanest proof the device has no link logic, and the
    Launcher only mirrors its own UI actions, not hardware-wheel changes.
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
| mix_channel_link | `0xa2` | `0x14` | **space=3** @17, pair_index @18 | enabled @19 | none found (software-mirrored, §12) |
| mix_fader / mix_pan / mix_send / mix_mute / mix_solo | `0xd4` | `0x17` | `mix` @18, `channel` @19 (1-32) | fader @20 (0-90 dB), pan @21 bits 0-5 (0x20=centre), mute @21 bit 6, solo @21 bit 7, send @22 (0-96) | none (§12) |
| talkback_button | `0x1f` | `0x12` | - | 1=press, 0=release @17 | offset 73 bit 6 |
| talkback_source | `0x27` | `0x12` | - | 0-12 @17 -- `0` = INT (built-in talkback mic behind the physical TB button), `1-12` = preamps 1-12 (user-confirmed) | offset 73 bits 0-1 (low bits only) |
| talkback_gain | `0x20` | `0x12` | - | 0-96 @17 (per selected source) | offset 74 |
| sample_rate | `0x03` | `0x12` | - | index 0-6 @17 (0=32k … 6=192k) | offset 18 (~1 s clock-relock lag) |
| talkback_dest_assign | `0x5d` | `0x13` | dest 0-3 = Mon A / Mon B / HP1 / HP2 (menu toggles, not the matrix) | 0/1 @18 | offset 73 bits 2-5 |
| routing | `0xd3` | `0x53` | destination group `@18` | array of `(bank,index)` pairs from `@19`, stride 2, one per output channel of the group -- §7 | none decoded (exists) |
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
| **Screen brightness** | `macos-scrbrght-0-100-50-multvalue` | opcode `0x12` / param `0x0e` / value 0-100 @17 | **real, confirmed (native macOS)** -- readback @26; in CLI (`set-brightness`). VM sent nothing because the slider is a no-op under the VM. |
| **Thunderbolt / latency / DC-coupling** | `settigs-thunderb-lat-dccp` | **zero frames** | host driver settings; TB is inactive while connected over USB, so this tab does nothing in this setup |

So the Settings window is a genuine mix: output levels/mute, the three
trims, surround-EQ pre/post and **screen brightness** are real device
commands; the oscillator panel and latency are host-side. **Lesson: the
VM Launcher silently no-ops some controls -- "zero frames under the VM"
does not mean host-side. Re-check on native macOS before concluding.**

### Oscillator -- two access points

**In the routing matrix:** right-click an output → insert oscillator. It
becomes a matrix source, bank `0x0c` (idx 0/1 = oscillator 1/2), sent as
the normal `0x53` routing frame (confirmed, §7). So *inserting* an
oscillator into an output IS a real device command.

**The settings-tab oscillator panel** (freq 1kHz/400Hz, level 0..−18 dBFS,
mute): `settings-osc1-2-fq-lvl.pcapng` had **zero** outgoing frames over
27.7 s. So the per-signal parameters are configured host-side or via an
uncaptured path -- only the matrix "insert into output" half is confirmed.

### Screen brightness -- RESOLVED (native macOS, 2026-08)

`settings-scrbrght-surroundEQ.pcapng` (VM) sent nothing for the
brightness slider -- because the VM Launcher no-ops it. Recaptured on
native macOS as `macos-scrbrght-0-100-50-multvalue`, with the user
watching the device's physical screen dim and brighten:

- **Command:** `global_command` (opcode `0x12`), param `0x0e`, value
  **0-100** (`0x00`-`0x64`) at payload offset 17. No target byte.
- **Readback:** `0x73` state report **offset 26** = the value, exact,
  1:1, on all 25 commands in the capture. Sits in the gap between
  `output_trim_block` (24-25) and `bus_block` (28-45); offset 27 still
  unmapped.
- First confirmed `0x12` param with a plain `0x73` readback (talkback's
  `0x12` params read back in the packed `talkback_block`).

**CLI:** `set-brightness <0-100>`, built by
`protocol.build_global_command(profile, 'screen_brightness', value)` --
the first `SET_GLOBAL` builder (opcode `0x12`, value @17). Readback via
`protocol.parse_state_scalar(profile, data, 'screen_brightness_byte_offset')`.
The talkback params (`0x1f`/`0x20`/`0x27`) can use `build_global_command`
too. See `params.screen_brightness`.

### Surround-EQ

The one Settings-window control here that does talk to the device:
opcode `0xab` / param `0xeb` (its own command shape), 2 frames, bit 7 of
payload byte @19 toggles. No `0x73` effect. Needs a dedicated capture to
decode the `0xab` layout.

### Thunderbolt / latency / DC-coupling

`settigs-thunderb-lat-dccp.pcapng` -- zero outgoing frames. Latency/buffer
is a host driver setting. Thunderbolt is inactive over USB. DC-coupling
*should* be hardware but wasn't exercised (or is TB-gated) -- worth an
isolated recapture, ideally on macOS.

---

## 12. Virtual mixer (0x17/0xd4) + mic modeling (0x17/0xe5) + AuraVerb (0x1d)

A 6th command shape (`frame.mix_command`). The **Mix windows are a
separate UI from the routing matrix**: mixing happens here, then each mix's
L/R appears as a *source* in the matrix (banks `0x06`-`0x09`, §7).

```
d4 05 <mix> <ch> <fader> <pan|flags> <send>
```

| byte | field | encoding |
|---|---|---|
| 16 | `0xd4` param | |
| 17 | `0x05` const | |
| 18 | **mix** | 0 = Mix 1 (1/2/3 = Mix 2/3/4 presumed; only 0 captured) |
| 19 | **channel** | 1-32 (each mix has 32 input strips) |
| 20 | **fader** | attenuation in dB: `0` = 0 dB / unity … `90` = −90 dB |
| 21 | **pan + flags** | bits 0-5 = pan: `0x02` = L30, `0x20` = centre, `0x3e` = R30 (raw = `0x20` + degrees); bit `0x40` = **mute**; bit `0x80` = **solo** |
| 22 | **send** | this channel's send *into* this mix, `0`-`96` (`96` = 0 dB, same scale as `bus_level`) |

One frame per `(mix, channel)` strip; it carries the whole strip state
every time. Confirmed from `macos-mix1-send-pan-fader-mute-solo-link`
(2026-08, native macOS): send / pan / fader sweeps each moved exactly one
byte 1:1; mute → `[21] |= 0x40`; solo → `[21] |= 0x80`.

**Solo mutes the rest host-side** -- clicking solo on one channel makes
the Launcher re-send a `mix_command` for **all 32 channels** of that mix
(a handy channel-count probe -- that's how we know it's 32).

**Mix channel link** = `SET_LINK` with a **new `space` byte `0x03`**
(0 = physical/ADAT, 1 = S/PDIF, 3 = mixer). `pair_index = channel // 2`.
Software-mirrored like every other link: while linked, the Launcher
re-sends both strips' `mix_command` frames on each change; the device does
not propagate.

**No readback** -- the whole capture moved only meter-jitter bytes, and
(like routing) the HID descriptor has no Feature report and the device
STALLs control-pipe `GET_REPORT`. Mixer state is write-only over USB.

**Not in the CLI yet.** `protocol.build_mix_command(profile, mix, channel,
fader, pan_deg, send, mute, solo)` builds the frame; `0x17` is in
`constraints.allowed_opcodes`.

### Mic modeling / "emuMic" (`0x17` / `0xe5`) -- decoded 2026-08-31

The front-panel **EMU** button, present only on **preamps 7-12** (6
channels). Runs Antelope's mic-emulation DSP on that preamp (for use with
their Edge Solo / Edge Duo / Edge Note modelling mics + model packs). Same
opcode `0x17` as the mixer -- `[16]` is `0xe5` instead of `0xd4`.

```
e5 05 <ch> <enabled> <model> <swap> <pattern>
@16      @18            @20     @21     @22
```

| byte | field | encoding |
|---|---|---|
| 16 | `0xe5` param | |
| 17 | `0x05` const | |
| 18 | **channel** | 0-based input channel index − 4 (preamp 7 → `2` … preamp 12 → `7`) |
| 19 | **enabled** | `1` = modeling on, `0` = off (also zeros @20-22) |
| 20 | **model id** | `0` = EdgeDuo / raw (no emulation, default); `1`…`N` = the emulation models (`profiles/mic_models.json`) |
| 21 | **channel-order swap** | `0`/`1` -- a switch that swaps the pair's channel order |
| 22 | **polar pattern** | with model `0`: `0` omni / `50` cardioid / `100` figure-8, continuous. With a selected model: that model's **pattern-class** code -- `0` = fixed native pattern, `1` = 3-way switchable, `4` = continuously variable |

Whole state every frame; params **mirror across the linked preamp pair**
host-side (Launcher sends `[18]=N` then `[18]=N+1`). From
`macos-ch7-8-micmodeling-*` / `macos-ch9-10_11-12-micmodeling-*` (model 0,
pattern swept 0→100 step 4; swap; enable/disable) and
`emumic-model-select-tokyo800t-…-b47TU` (18 models cycled on preamps 7-8
→ `[20]` = `0x01`…`0x12`, `[22]` = the model's class code).

**Enabling also triggers side effects** (the Launcher does these, not the
device): 48 V **phantom on** for the pair (`SET_PARAM` param `0x51`) and a
**preamp-pair link** (`SET_LINK` space 0, pairs 3/4/5). The only `0x73`
change is the phantom bit (`0x10`) for those channels -- the modeling
params themselves have **no readback** (write-only, like the rest of the
`0x17` family).

**Model selection** is the SAME frame -- byte `[20]`. Captured
2026-08-31 (`emumic-model-select-…`): 18 emulations, ids `1`-`18`, in the
order in that capture's filename. Id `0` = EdgeDuo (raw mic, emulation
bypassed) is the default. **This list is account-bound** -- Edge mics +
model packs activate against an Antelope account, so the usable models
are per-user, and it is not confirmed whether the ids are global or just
positions in the list the Launcher shows you. Full id→name→pattern_class
table in `profiles/mic_models.json`; no readback (write-only).
Antelope's own naming (Berlin / Vienna / Tokyo / …) is used; the classic
mics being emulated are not spelled out (that's the licensed IP).

The modeled signal is routing **source bank `0x01`** ("emumic", §7),
confirmed 2026-08-31 to have 8 indices = preamps 5-12. The EMU *button*
is only on preamps 7-12, so bank `0x01` idx 0-1 (preamps 5-6) can be
selected as a source but have no way to load a model -- a Launcher bug or
unfinished feature; untested whether the card produces audio there.

`protocol.build_micmodeling_command(profile, channel, enabled, pattern,
swap, model)` builds the frame; not in the CLI.

### AuraVerb (`0x1d` / `0xda`) -- on/off + 8 DSP params, DECODED

A 7th command shape. AuraVerb is a bundled reverb on the **Mix 1**
window. The frame carries the whole state every time (like the mixer):

```
da 0b 00 RS CO PD 64 EG LD RI RT RL .. .. .. .. <enabled>
@16      @19            @22          ..          @28
```

| offset | control | range | power-on default |
|---|---|---|---|
| 19 | Room Size | 0-100 | 0x51 (81) |
| 20 | Color | 0-100 (dark→bright) | 0x64 (100) |
| 21 | Pre-Delay | 0-100 → 0-32 ms | 0x00 (0) |
| 22 | *(constant `0x64`)* -- never swept; assumed wet/mix locked at 100% | -- | 0x64 |
| 23 | Early Reflection Gain | 0-100 | 0x0b (11) |
| 24 | Late Reflection Delay | 0-100 | 0x0d (13) |
| 25 | Richness | 0-100 | 0x18 (24) |
| 26 | Reverb Time | 0-100 | 0x42 (66) |
| 27 | Reverb Level | 0-100 | 0x32 (50) |
| 28 | enabled | 0/1 | 0x01 |

`@17` = `0x0b` constant sub-cmd; `@18` = `0x00` (only Mix 1 captured --
likely the mix index). Every param is a plain byte 0-100; UI drags land
on even steps but odd values are presumably legal. Evidence:
`macos-auraverb-on-off` (on/off = @28) + `macos-auraverb-ctl-color-\
predelay-earlyrefgaij-laterefdelay-richness-reverbtime-roomsize-\
reverblevel` (2026-08-31, each of the 8 controls swept in isolation →
one byte each). Control names/ranges cross-checked against the Orion
Studio Synergy Core manual p.50 and antelopeaudio.com/products/auraverb
(facts only). **No `0x73` readback** (checked the whole capture) → the
CLI caches CLI-issued state. AuraVerb is device-*bundled* (no per-plugin
activation) so it is **in scope**; still off-limits is the licensed AFX
plugin chain and anything touching license state. `0x1d` is now in
`constraints.allowed_opcodes`; `protocol.build_auraverb_command`; CLI
`auraverb`. Not hardware round-trip tested yet.

---

## 13. Open questions

| Item | Status |
|---|---|
| Routing frame (`0x53` / `0xd3`) | §7: destination map (0-14), **all 12 source banks** (`0x00`-`0x0c`, bank `0x01` = emumic confirmed 2026-08-31), and the `(bank,index)`-per-channel array model all confirmed. CLI `route <dest> <chan> <source>` covers line out (16 ch) + HP1/HP2/Mon A/Mon B/Reamp (2 ch), sources incl. `emumicN`. Open: channel counts of the other multichannel destinations. **No routing readback over USB** (HID descriptor has no Feature report; device STALLs `GET_REPORT`; not in `0x73`/`0x74`; preset-load is pure push) -- pending only the offline-persistence test. The CLI cache is the correct design. |
| Virtual mixer (`0x17` / `0xd4`) | §12: frame decoded 2026-08 (`macos-mix1-...`) -- `mix`/`channel`(1-32)/`fader`(0-90)/`pan`(0x20=centre)/`mute`(@21 bit6)/`solo`(@21 bit7)/`send`(0-96), plus mix link via `SET_LINK` space `0x03`. Open: only Mix 1 (`[18]=0`) captured; no readback found (like routing); not in the CLI. |
| Mic modeling / emuMic (`0x17` / `0xe5`) | §12: enable / model id `[20]` / polar-pattern `[22]` / channel-order swap all decoded 2026-08-31 (`macos-ch7-8-micmodeling-*`, `emumic-model-select-…`). 18 emulation models + a pattern-class code in `profiles/mic_models.json` (account-bound list). `build_micmodeling_command`; not in CLI. Open: how a variable-pattern model's pattern is set after selection; whether model ids are global or list-position. |
| ADAT vs physical `SET_LINK` | both use `space` byte `0x00` -- byte-identical frames (§7). S/PDIF (space `0x01`) is now distinguishable. Open: does one space-0 command link pair N in *both* physical and ADAT? Needs different per-channel gains or a hardware test |
| Pan law | never captured; likely offset 25 bits 0-1 |
| S/PDIF gain + link | **confirmed** (`spdif-gain-link`, 2026-08): gain param `0x5c`, readback `91`/`92`, link via `space=1`. In the CLI. |
| Oscillator | matrix insert is a real command (routing bank `0x0c`, §7); the settings-panel freq/level/mute sends nothing |
| Screen brightness | **resolved (native macOS)** -- opcode `0x12` / param `0x0e` / value 0-100 @17, readback @26 (`macos-scrbrght-0-100-50-multvalue`). VM had no traffic only because the VM Launcher no-ops the slider. |
| Sample rate | **resolved (native macOS)** -- opcode `0x12` / param `0x03` / index 0-6 @17, readback @18 (`macos-smplrt-...`). CLI `sample-rate` / `set-sample-rate`. Open: the clock/PLL/buffer bytes @21-23,27 that move only at 88.2k/176.4k. |
| Surround-EQ pre/post | new opcode `0xab` / param `0xeb` seen (2 frames); layout undecoded, no `0x73` effect |
| Thunderbolt / latency / DC-coupling | zero outgoing frames -- host-side, or not exercised |
| Offsets 17 / 19 blip | ~3.0 s after the Launcher starts, in every capture **including the no-user-interaction INIT capture** -- Launcher handshake event, not user- or feature-related. Ignore. |
| Offsets 139-140 ramp (129-136 in INIT) | first ~0.12 s of every capture -- device/connection startup settling. Ignore. |
| Offsets 157-176 / 221-232 | free-running meter data embedded in the state report; exact byte->channel mapping not pinned down (cross-check against `0x75` offsets 32-43) |
| Channel-link readback bit | none found; may not exist |
| dB curve past -60 dB, and per-channel | only channel 0, only to -60 dB |
| `0x74` groups `0x19`(64)/`0x03`(15)/`0x04`(4) + singletons | counts + order known (section 4); **names are in no capture on file** -- need a fresh string-descriptor capture or the Launcher routing-tab labels. `0x19`=64 is probably the USB/TB channel stream |
| `bus_block` reserved byte (`30+3N`) | never changed -- padding or unexercised |
| Orion hidraw write length | 320 or 321 bytes? -- `transport.py` writes 320; unverified against Orion's HID descriptor (section 14) |
| Orion gain clamp vs reject | unknown -- the Discrete 8 Pro clamps out-of-range gain; Orion's behaviour untested |

---

## 14. Device family / cross-device notes

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
  Send only `constraints.allowed_opcodes` (`0x12`/`0x13`/`0x14`, plus
  `0x53` for the experimental `route` command).
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

### Zen Go Synergy Core (`profiles/zen_go_sc.json`, PID `0xa015`)

First-pass profile from USBPcap captures (2026-08-31). Same transport
(HID iface 3, EP `0x01`/`0x82`, 320-byte reports) and most param IDs
(`0x50` gain, `0x4f` mode, `0x51` phantom, `0x52` phase, `0x47`/`0x48`
bus, `0x12`/`0x03` sample rate, `0x14`/`0xa2` link, `0x53`/`0xd3`
routing). **Divergences from Orion:**

| Thing | Orion | Zen Go |
|---|---|---|
| meter report magic | `0x75` | **`0x83`** |
| connect name/topology report | `0x74` only (no names ever) | `0x74` + **`0x75` = ASCII device name / serial / fw** |
| mixer frame | opcode `0x17`, subcmd `0x05`, has a **send** byte @22 | opcode **`0x16`**, subcmd **`0x04`**, **no send** byte |
| mixes / strips | 4 mixes × 32 | 2 mixes × 16 |
| preamps | 12 | 2 (A1 = ch0, A2 = ch1) |
| gain array offset | `0x73` @49 | `0x73` **@40** |
| status array offset | `0x73` @61 | `0x73` **@42** |
| bus block | `28 + 3N` | `28 + 2N` |
| clock source readback | — | `0x73` **@19** (`0x12`/`0x04`, 3 sources, no word clock) |
| source bank: mute / osc / emumic | `0x0b` / `0x0c` / `0x01` | **`0x08` / `0x09` / `0x0a`** |
| new: output volume | buses | *also* an `0x16`/`0xd4` strip at `(mix 1, ch 3)` |
| new: DSP opcodes | `0x1d` AuraVerb | **`0x1a` / `0x1c` (`0xd5`), `0x23` (`0xd7`)** -- undecoded, forbidden |

Still open: full routing map (dests 3/5/6/7/8/9), DSP/mic-modelling
frames, meter byte-map, the two output-volume paths, `param 0x66` (bus
dim/mono?), `param 0x49` (set to 12/15 during mixer use). See
`open_questions` in the profile.
