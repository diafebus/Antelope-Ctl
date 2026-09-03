# Antelope Orion Studio Synergy Core -- protocol & hardware reference

Everything reverse-engineered so far about how the device talks, in one
place. `README.md` is the user-facing guide; this file is the spec you
reach for once you've read it. `profiles/orion_studio_sc.json` is the
machine-readable source of truth -- if the two ever disagree, the profile
wins and this file is stale. For what the profile JSON's keys *mean*, see
`docs/profile-schema.md`. Sibling devices are in §14
(`profiles/zen_go_sc.json`, `profiles/discrete_8_pro_sc.json`).

All offsets are **byte offsets into the 320-byte HID report**, 0-indexed.
"2026-08" on a claim means it was confirmed by capture in that session;
see `README.md` and the profile's `evidence` fields for which capture.

---

## 1. Device & transport

| | |
|---|---|
| Device | Antelope Orion Studio Synergy Core (a.k.a. "Orion Studio III") |
| USB VID:PID | `0x23e5:0xa221` |
| bcdDevice | 7.00 |
| Control interface | vendor **HID, interface 3** (the UAC2 audio-control interface is a stub -- 1 clock, 4 terminals `nrChannels=1`, no Feature Units -- all control is HID) |
| Report size | **320 bytes**, fixed, both directions (but see §14 -- Linux hidraw writes may need a leading `0x00`, making them 321; unverified on Orion) |
| Control OUT endpoint | `0x01` (host -> device commands), interrupt |
| Control IN endpoint | `0x82` (device -> host reports), interrupt |
| Audio stream endpoints | `0x05` OUT / `0x84` IN, isochronous, 24-ch / 24-bit in the class-compliant descriptor -- **unrelated to control** |
| Device address | 2 (`usb.dst 1.2.x` in the captures) |
| Poll interval | 4 ms |
| GET / query opcode | **`0x74` request / `0x75` response, in-band on the interrupt endpoints** (decoded 2026-08-31 -- see §4a). Not a HID Feature report and not a control transfer (the report descriptor has none, and the device STALLs every control-pipe `GET_REPORT`), which is why the earlier analysis missed it. Routing, mixer, AuraVerb, EQ, device id -- all live-readable by `(category, index)`. |
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
| `0x12` | SET_GLOBAL | param | `value` @17 (no channel byte; @18 unused) | talkback_button, talkback_source, talkback_gain, screen_brightness (`0x0e`), sample_rate (`0x03`), **clock_source (`0x04`)**, oscillator panel (`0x0a`, packed byte), **pan_law (`0x24`)**, DC-coupling (`0x26`) |
| `0x14` | SET_LINK | `0xa2` (fixed) | `space` @17 (0 = physical+ADAT, 1 = S/PDIF, **3 = mixer**), `pair_index` @18, `enabled` @19 | channel_link, adat_channel_link, spdif_channel_link, mix_channel_link |
| `0x17` | SET_MIX | `0xd4` | `0x05` @17 (const), `mix` @18, `channel` @19, `fader` @20, `pan+flags` @21, `send` @22 -- see §12 | virtual mixer (Mix 1-4) |
| `0x17` | SET_MIC_MODELING | `0xe5` | `0x05` @17 (const), `channel` @18 (0-based idx − 4), `enabled` @19, `model` @20, `swap` @21, `pattern` @22 -- see §12 | mic modeling / emuMic (preamps 5-12) |
| `0x1d` | SET_AURAVERB | `0xda` | 8 DSP params (Room Size @19, Color @20, Pre-Delay @21, Early Ref Gain @23, Late Ref Delay @24, Richness @25, Reverb Time @26, Reverb Level @27, each 0-100), `enabled` @28 | AuraVerb (Mix 1) |
| `0x53` | SET_ROUTE | `0xd3` | `0x41` @17 (const), `destination` @18, then a `(bank,index)` pair per output channel from @19 (stride 2) -- see §7 | routing matrix |
| `0xab` | SET_SURROUND (global) | `0xeb` | whole-state: `[18]` bit 7 = EQ pre/post, `[18]`/`[19]` = format, `[20]` = delay, `[22-23]` = level, `[25-30]` = bypass/mute/dim -- §11 | surround tab global (level/dim/mute/delay/bypass/EQ/format) |
| `0x87` | SET_SURROUND_SPEAKER | `0xea` | per-speaker: `[18]` = speaker 0-15, `[19-20]` delay, `[21-22]` level (+`[22]` bit7 invert), then 16 EQ bands (2 UI pages of 8) -- §11 | surround tab per-speaker strip (×16) |

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
| `0x73` | state report | continuous (~every 4-8 ms) | the passive readback for preamp/bus/etc -- see section 5. **Also carries the per-channel input meters** at offset `157 + channel` (section 9). Same frame family as a readback response for "category 0". |
| `0x75` byte1 `0x1f` | meter report | continuous | on this device this is NOT per-channel -- only byte 32 is live (a monitor sum) and byte 33 is a flag. Per-channel meters are in `0x73`. See section 9. |
| `0x75` byte1 `0x00` | **readback response** | on request | reply to a `0x74` query -- `(category, index)` at @8/@12, payload from @16. See §4a. |
| `0x74` | readback / enumeration | at connect, then on demand | the host walking `(category, index)` -- see §4 / §4a |

Per-channel input meters: one byte per channel from **`0x73` offset 157**
(mirror copies at 169 and 221), same channel order as gain/status. Scale is
**inverted** -- `0x60` (96) at rest/silence, falls toward `0x00` as the
signal gets louder. Calibration in section 9. The separate `0x75` meter
frame is a monitor/summed level only on this unit (byte 32), not per-channel.

### 2026-08 caveat, REVISED 2026-08-31

Passively, the device streams only `0x70` (out) / `0x73` / `0x75` (meter).
But `0x74` is not just a one-shot connect dump -- **the host can send a
`0x74` query at any time and the device answers with a `0x75`/byte1-`0x00`
response** carrying live state (routing, mixer, AuraVerb, EQ, ...). See
§4a. The earlier "there is no hidden fourth report type" was right about
*passive* traffic and wrong about *solicited* traffic.

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

## 4. Magic `0x74` -- the connect enumeration walk

At device connect the Launcher walks its internal categories with `0x74`
queries (t=7.5-16 s of `all_reports_AntelopeINIT.tsv`, 113 records). **This
is the readback protocol of §4a** -- each record is a `(category, index)`
query, and the device replies (the reply frames just weren't in that
HID-only capture). The `0x74` request record layout:

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

### What the categories are (resolved 2026-08-31 via §4a)

- **`0x03` = 15** -- the **routing matrix**: 15 destination groups
  (line_out, hp1/2, mona/b, reamp, comp_rec, adat_out, spdif_out, afx_in,
  mix_ch1-4, surround_in). The `0x74` reply for `(0x03, dest)` is that
  group's full source list.
- **`0x04` = 4** -- the **virtual mixer**: 4 mixes. Reply = that mix's
  strips.
- **`0x19` = 64** -- the 64 USB/TB streaming channels (reply bodies are
  empty in the connect walk).
- **`0x1a` = 16** ADAT, **`0x11` = 2** S/PDIF -- confirmed earlier.
- Singletons `0x0a` (AuraVerb -- decoded), `0x15`/`0x0c` (90-entry
  `<id><flags>` tables, not the link table), `0x16` (unknown -- not trim,
  not pan-law), `0x1b` (repeating `[80][80][600][0]` -- maybe the surround
  tab / EQ-band template), `0x07` (EQ) -- see the §4a category table.
- `0x0b` -- still a structural section marker in the walk.

Full raw dump of every category: `tools/readback_enum.py`.

---

## 4a. In-band readback protocol (`0x74` request / `0x75` response)

**Decoded 2026-08-31.** CAPTURE E' -- `usbmon` on the Linux host while the
Windows Launcher connected to the Orion over QEMU USB passthrough -- caught
the Launcher sending `0x74` frames on EP `0x01` OUT and the device
replying on EP `0x82` IN. Replayed and enumerated directly from Linux with
`tools/readback_enum.py`. This is a real device→host readback: **not** a
HID Feature report and **not** a control transfer (the report descriptor
has neither and the device STALLs `GET_REPORT`), which is why
`tools/hid_probe.py` and `tools/readback_probe.py --poke` came up empty --
`--poke` sent a bare `0x74` with no sub-header, and the device ignores
that.

**It was in the INIT captures the whole time.** Re-scanned 2026-08-31:
`AntelopeINIT.pcapng` (Windows) has all 113 `0x74` requests **and** 41
non-empty `0x75`/@1=`0x00` responses, incl. `cat 0x03` idx 0-14.
`macos-antelopeINIT-poweron` has 209 requests / 66 responses. And the
`macos-antelopeINIT-poweroff-on2` / `-on3` pair -- the two captures used
to conclude "no routing readback at connect" -- carry `cat 0x03 idx 0`
with the **deliberately swapped** LineOut routing the user had set
(on2 = compIn 1-12 + preamp 1-4; on3 = preamp 1-12 + compIn 1-4). We had
the diff; we were reading the `0x74` *request* bytes (identical -- same
category walk both times) and filtering the `0x75` responses as meter
noise (see the discriminator note). The USB-only captures were never the
problem.

```
REQUEST   host → device, EP 0x01 OUT, full 320-byte report
  @0   0x74
  @4   0x10                (sub-command, constant)
  @8   u32  category
  @12  u32  index
  @16+ zero

RESPONSE  device → host, EP 0x82 IN, full 320-byte report
  @0   0x75
  @1   0x00                <- discriminator: meter report is 0x75/@1=0x1f
  @4   0x0140  (u16 le)
  @8   u32  category       (echoed)
  @12  u32  index          (echoed)
  @16+ payload             (zero-padded to 320)
```

The `0x73` state report is the same frame family (magic `0x73`, `@1`=0x00,
category 0) pushed continuously. The device answers every **in-range**
`(category, index)` -- one it has no record for just returns an empty
payload, so "non-empty payload" is the liveness test. Scalar categories
return the same record for every index.

### ⚠ HAZARD -- an out-of-range index crashes the device

**The firmware does not bounds-check the index.** One index past a
category's record count returns *adjacent memory* with a completely
different layout; a little further and it faults.

Confirmed on real hardware, 2026-08-31 -- `category 0x04 index 5` hard-
crashed the device. Front panel:

```
CRITICAL ERROR!
Failure.c

L: 204   E: 0
BusFault_Handler
```

That is an ARM Cortex-M **BusFault** (invalid memory access) trapped in
its exception vector; the MCU hangs. USB still enumerates (`lsusb` shows
the device -- the USB PHY is separate silicon) but **nothing** works: no
readback, no `0x73` state stream. Only a physical power cycle recovers
it. It happened twice this session; NVRAM state survived both times.

**Diagnostic signature, in order:**

| index | response | meaning |
|---|---|---|
| in range | consistent layout | real records |
| first over-range | answers, **wrong layout** | reading adjacent memory |
| next | **no response at all**, endpoint dies | BusFault, MCU hung |

An *empty* answer is normal. **No** answer means the MCU just died inside
the handler.

> **This supersedes the earlier diagnosis.** Previous notes here and in
> `tools/readback_enum.py` blamed the halted endpoint on *hammering* --
> "hundreds of rapid queries". That was wrong. The 2026-08-31 crash took
> about **ten slow queries**; the fatal one was simply out of range. Rate
> was never the trigger. Pacing is still polite (it keeps the free-running
> `0x73`/`0x75` stream readable) but it is **not** the safety mechanism.
> The index bound is.

**Safe bound: `frame.readback.category_counts`**, taken from the device's
own `0x74` connect enumeration (§4 -- 113 records = 16+2+64+15+4+4+8, so
those ten categories are the entire walk):

| cat | records | | cat | records |
|---|---|---|---|---|
| `0x03` | 15 | | `0x16` | 1 |
| `0x04` | 4 | | `0x19` | 64 |
| `0x0a` | 1 | | `0x1a` | 16 |
| `0x0b` | 8 | | `0x1b` | 1 |
| `0x11` | 2 | | `0x15` | 1 |

Categories that answer but are **not** in the connect walk (`0x00`,
`0x01`, `0x02`, `0x05`, `0x06`, `0x07`, `0x0c`, `0x0d`, `0x12`) have **no
known count** and cannot be bounded -- treat any index above 0 on those as
unproven and dangerous.

Note `0x03` answers with distinct bodies at idx 15-24 even though there
are only 15 destination groups: that is *already* adjacent memory, not
extra routing data.

Enforced in code by `protocol.check_readback_index`, called from
`build_readback_query`. The CLI's `readback --force` additionally requires
`ANTELOPE_ALLOW_UNSAFE_READBACK=1`; `tools/readback_enum.py` clamps every
sweep to the declared count unless `--unsafe`.

### Category map (Orion Studio Synergy Core, 2026-08-31)

| cat | payload | status |
|---|---|---|
| `0x00` | device id + firmware string (`4.41`) | — |
| `0x01` | model name `OrionStudio_III` + **serial** + hw rev `7.0` | keep raw dumps out of git |
| `0x02` | per-channel present flag (scalar `01`), idx 0..63 | — |
| **`0x03`** | **routing matrix** -- 1 record per destination group, idx = dest_id 0-14. Record = `<dest_id>` then a `(source_bank, source_index)` pair per output channel (`destination_channels[dest]` pairs) -- the **same array as the `0x53` write frame**. | **decoded, verified byte-identical against CLI-written routes** |
| **`0x04`** | **virtual mixer** -- 1 record per mix, idx = mix 0-3. Record = 33 × 3-byte slots `<fader> <pan\|mute\|solo> <send>`, the **same field order as the `0x17`/`0xd4` write frame**; slot N = the strip written as `channel` N. See below. | **decoded, hardware round-trip verified** |
| `0x05` | **preamp gain** -- 1 byte/channel = gain in dB (line/direct = 0). Independent copy of `0x73` @49. | **decoded + differential-write confirmed 2026-09-03** |
| `0x06` | **channel status** -- 1 byte/channel, same packing as `0x73` @61: `(phase<<6)\|(phantom<<4)\|(mode&3)`. | **decoded + differential-write confirmed 2026-09-03** (phantom bit inferred from the shared encoding) |
| `0x07` | EQ curve, freq points ~30/200/1k/5k/15k Hz, 8 records | undecoded |
| **`0x0a`** | **AuraVerb** -- 1 record (idx 0), a `0x00` header then 4 × 11-byte blocks (Mix 1..4; block 4 truncated to 9 B). Block = `0x1d` payload minus the mix byte: `[0]room_size [1]color [2]pre_delay [3]0x64 [4]early_ref_gain [5]late_ref_delay [6]richness [7]reverb_time [8]reverb_level [9]enabled [10]0xff`. | **decoded + hardware round-trip verified 2026-09-03** (differential readback) |
| `0x0c` / `0x15` | ~90-entry per-channel link/config tables | undecoded |
| `0x11` | S/PDIF + a 128-B capability bitmask | undecoded |
| `0x16` | **UNKNOWN** -- NOT output trim, NOT pan law (both ruled out live 2026-09-03). Seen all-zero and `00 00 00 32 ×2 …` | undecoded |
| `0x1a` | EQ curve, 8 bands, freq ~30-14000 Hz (116 B) | undecoded |
| `0x1b` | mixer bus level/range table | undecoded |
| `0x19` | 64 entries, empty bodies -- the 64-ch USB/TB slots | — |
| `0x1c`-`0x60` | answer, empty bodies | — |

### Reading routing back

For destination group `d`, send `0x74 (category 0x03, index d)` and parse
the reply payload: byte 0 = `d`, then `destination_channels[d]`
`(bank, index)` pairs. Trailing `(0, 0)` (= preamp 1) or `(0x0b, 0)`
(= mute) pairs are real -- do not strip trailing zeros; use the known
channel count.

Code: `protocol.build_readback_query` / `is_readback_response` /
`parse_routing_record`; `transport.HidTransport.query`. CLI:
`antelope-ctl … matrix-status` (full live read of all 15 groups) and
`antelope-ctl … readback <cat> [idx]` (raw). `route` now verifies each
write against a live read and reseeds `keep` from the device.

### Reading the virtual mixer back (category `0x04`) -- decoded 2026-08-31

Send `0x74 (category 0x04, index m)` where `m` = 0-3 (Mix 1-4). **Never
index above 3** -- see the hazard box above; `idx 5` is what crashed the
unit.

The payload is 99 bytes: a flat array of **33 three-byte slots**, in the
*same field order as the `0x17`/`0xd4` write frame* (fader@20, pan|flags@21,
send@22):

```
<fader>  <pan | mute | solo>  <send>
   |            |                |
   |            |                +-- 0-96, 0x60 = 0 dB, 0 = -inf
   |            +-- low 6 bits = pan (0x20 centre, 0x02 = L30, 0x3e = R30)
   |                bit 0x40 = MUTE, bit 0x80 = SOLO
   +-- attenuation in -dB, 0 = unity .. 90 = -90 dB
```

**Slot index maps 1:1 onto the write frame's `channel` field, with no
special case at either end:**

| slot | is |
|---|---|
| `0` | the **mix master** strip |
| `1`-`32` | the 32 input strips |

The readback and the write frame share a layout, the same way routing does.

**Hardware round trip, 2026-08-31 — verified byte-exact:**

| step | result |
|---|---|
| write mix 1 / ch 5 / fader 40 / pan +12 / **mute** / send 33 | frame bytes `28 6c 21` |
| read back cat `0x04` idx 0, slot 5 | **`28 6c 21`** |
| any other slot changed? | **no** — only slot 5 |
| three reads 2.5 s apart | byte-identical |
| restore original | exact |

That last row settles a real ambiguity: the third byte is **stored send
state**, not a live meter. (Mix 1 reads a scatter of 95s and 96s across
its strips, which looks like meter jitter but is stable across reads.)

Reading all four mixes also confirms `[18]` in the write frame really is
the mix number — each index returns its own independent record.

### Slot 0 = the mix master (confirmed 2026-09-01)

Slot 0 reads fader 0 / pan centre `0x20` / send 96 on an untouched mix, and
142 consecutive reads over 150 s never moved a byte. Settled by capturing
the Launcher rather than by probing: `usbmon` on the Linux host while the
Windows Launcher (QEMU passthrough) swept the **Mix 1 master fader** ->
`captures/new/mix1-masterfaderplay.pcapng`.

All 68 command frames in that capture are the *same* `0x17`/`0xd4` mix
frame, and every one of them is:

```
70 .. 17 ..   d4 05 | 00 | 00 | <fader> | 20 | 60
              @16 @17  @18   @19    @20    @21  @22
                       mix=0  ch=0  sweeps  pan  send
```

- **`[19]` = 0** on all 68 frames -- no other channel was touched
- `[20]` swept the full range (21 -> 90 -> 0 -> 90), i.e. 0 dB ... -90 dB
- `[21]`/`[22]` held constant at `0x20` / `0x60`

The sweep ended at fader 90, and slot 0 then read back as **-90 dB**.

So **the Launcher itself writes `channel 0`** -- it is a normal address,
not an out-of-range write, and the earlier caution against probing it was
unnecessary (capturing the Launcher was still the cheaper way to find out).

Code: `protocol.parse_mixer_record` (returns all 33 slots, index == slot ==
channel). CLI: `antelope-ctl mix-status [mix]`, which shows the master as
row `mast`.

### This resolves the cross-machine-persistence question

The device stores routing in NVRAM and **does** report it to the host --
via exactly this. A fresh Launcher connecting reads category `0x03` and
shows whatever the device holds, regardless of which host last wrote it
(confirmed: routes written by the Linux CLI showed up correctly in a
fresh Windows Launcher). It was never Antelope account sync.

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
| 157-168 | **per-channel input meters** -- 12 physical inputs | channel *N* meter @ `157+N`, inverted (96 silence -> 0 loud); mirror copies at 169-180 and 221-232 | confirmed 2026-09-01 (section 9) |

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
**Re-confirmed live on the device 2026-09-03** -- swept all 3 targets,
`[24]`/`[25]` tracked `value << shift` exactly, restored to baseline.

**Value → dBu (all three targets, USER-CONFIRMED against the Launcher /
Orion Studio Synergy Core, 2026-09-02):** it is an output-reference-level
selector, 1 dBu per step — index `0 = 20 dBu`, `1 = 19`, `2 = 18`, `3 = 17`,
`4 = 16`, `5 = 15`, `6 = 14 dBu`. Same scale on Monitor A, Monitor B and
Line Out. Resolves the earlier "physical meaning not known". The 2026-08
sweep hit exactly these 7 stops; the 3-bit field could carry a value 7 but
the hardware has no 8th stop.

Spare bits: offset 24 bits 0-3 and 7; offset 25 bits 0-1 — none of them
carry pan law. **Pan law = `SET_GLOBAL` (opcode `0x12`) / param `0x24` /
value @17, DECODED 2026-09-03** (`panning-law-6-3-45-0`): enum `0` = -6 dB,
`1` = -3 dB, `2` = -4.5 dB, `3` = 0 dB (the Launcher's own button order —
not monotonic in dB). **No readback** — nothing in `0x73` moved through
the sweep, and readback cat `0x16` (once guessed to hold trim/pan-law)
tracks neither. `params.pan_law`; CLI `pan-law [--set N]`.

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
| `0x01` | **emumic** -- the mic-modeling DSP output (wet tap; the DSP is `0x17`/`0xe5`, §12) | 0-7 = preamps 5-12 (8 modeling-capable preamps; the EMU button shows per channel only in Mic mode) |
| `0x02` | **compplay** (Computer Playback / USB) | 0-23 on the VM driver, 0-31 on native macOS -- idx 24-31 (CP 25-32) CONFIRMED via routing readback (webui, 2026-09-03: wrote each of 25..32 into an output slot, all read back unchanged) |
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
8 taps = preamps 5-12, the full modeling-capable range. The
front-panel/Launcher EMU button shows on a channel only in **Mic mode**
(absent in Line/Hi-Z) -- earlier notes said "7-12" because the reference
unit had preamps 5-6 in Line. Confirmed 2026-09-03 (webui): emumic 5/6 =
`(0x01, 0)`/`(0x01, 1)` route + read back on the device exactly like 7-12;
`channel_bias` -4 puts `[18]=0` at preamp 5; the owner confirms the EMU
button appears on 5-6 in Mic mode. Not yet captured: the Launcher emitting
a `0xe5` frame with `[18]=0`/`1`, and a listening test of the wet taps.
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
channels, surround in) use the same array. **All 15 channel counts are now
known** (2026-08-31, read straight off the cat-`0x03` readback records):
line_out 16; hp1/hp2/mona/monb/reamp/spdif_out 2; com_rec/afx_in/mix_ch1-4
32; adat_out/surround_in 16. Old note that adat_out is "15× `03 NN`" fits
the array model exactly: entry 0 = the changed channel, entries 1-15 =
`(0x03, 1..15)` = the ADAT-in passthrough left untouched.

**Routing is exclusive** per channel (one source per output channel) and
**idempotent** (routing an already-present source sends nothing). Summing
is via separate "virtual mixes".

All 12 source banks are identified (bank `0x01` = emumic, idx 0-7 =
preamps 5-12, confirmed 2026-08-31), all 15 destination channel counts are
known (above), and as of 2026-09-01 **`route` can write all 15 groups** --
each was live-read first and its channel count matched
`destination_channels` exactly. Writes were round-trip verified on
`mix_ch4` (a 32-ch group) and `spdif_out` (2-ch, L/R).

**Output mute and oscillator-insert both go through this frame** (bank
`0x0b` and `0x0c`, right-click in the matrix). Un-mute = re-assign a real
source. The settings-tab oscillator panel is separate and sends nothing
(§11). **Talkback is NOT a matrix source** -- its 4 destination toggles
(Mon A / Mon B / HP1 / HP2, which combine) use `talkback_dest_assign`
(`0x13` / `0x5d`).

**Routing readback: FOUND (2026-08-31).** It is the `0x74`/`0x75`
in-band protocol, **category `0x03`** -- one record per destination group,
same `(bank, index)` array as the write frame. See **§4a**. Verified
byte-identical against routes the CLI wrote from Linux, and against a
fresh Windows Launcher. `matrix-status` is now a full live read of all 15
groups; `route` verifies every write against a read-back. The rest of
this section is the **superseded** pre-decode analysis -- kept because the
reasoning (and what it correctly ruled out: HID Feature reports, control
transfers, the connect handshake, preset-load) is still useful. Its one
wrong assumption was that a readback *must* take one of those forms.

---

<details>
<summary>Superseded (pre-2026-08-31) "there is no routing readback" analysis</summary>

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
  (indices only, as always). *(2026-08-31: we compared the `0x74`
  **request** bytes. The device's `0x75`/@1=`0x00` **responses** to those
  requests are in both captures and they DO differ -- `cat 0x03 idx 0` =
  the swapped LineOut routing. §4a. That is the readback; it was here.)*
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

So at connect the Launcher does not push cached routing, and no `0x53` is
sent. What this analysis got wrong: it read routing **is** in the connect
sequence -- the Launcher walks `cat 0x03` with `0x74` queries and the
device answers with the full matrix (`0x75`/@1=`0x00`). We classified
`0x74` as request-only ("indices, not values") and `0x75` as the meter
report, so the responses were filtered out before anyone looked. CAPTURE
E' (`usbmon`, live) made the request→response pairing obvious; re-scanning
these same INIT captures then confirmed the data was always there.

</details>

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
- **There is no channel-link readback anywhere.** CLOSED 2026-09-03 by a
  dedicated live-device whole-report diff: raw `0x14` toggle on preamp
  pair 3 (no gain/mode sync), `0x73` read 3× keeping only bytes stable
  across all reads, before vs after, for both on and off, plus a re-read
  of readback cats `0x0c` / `0x15` / `0x06`. Zero stable bytes changed
  anywhere; the readback tables were byte-identical. The device stores
  link state (front panel shows it) but exposes it nowhere over USB HID.
  Track it client-side.

Any non-Launcher controller must replicate the two-commands-per-change
behaviour itself if it wants Launcher-equivalent results.

---

## 9. Meters

### Where they are (CORRECTED 2026-09-01)

The per-channel input meters are in the **`0x73` state report** at
`157 + channel_index` (12 physical channels). Inverted scale: raw `0x60`
(96) at silence, falling toward `0x00` as level rises. Three byte-identical
mirror copies of the 12-byte block exist at bases **157, 169, 221** -- use
157.

Recapture that pinned it (2026-09-01): feeding preamps 1/2/3/4 in turn drove
offsets 157/158/159/160 to the single digits one after another, each
recovering to ~96 on silence; unfed channels stayed at rest.

The separate **`0x75` meter frame** (byte1 `0x1f`) was previously documented
as `32 + channel`, "confirmed for all 12". That was wrong for this unit: only
byte 32 is live -- a monitor / summed level that responds to any input --
and byte 33 is a 0/1 flag. The old formula rendered byte 33 as channel 1
pinned at clip. `0x75` is still fine as a single monitor meter (byte 32).

`protocol.channel_meter_source()` returns `(magic, base)` -- state report
first, meter report as fallback -- and `parse_channel_meter()` reads it.

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
| routing | `0xd3` | `0x53` | destination group `@18` | array of `(bank,index)` pairs from `@19`, stride 2, one per output channel of the group -- §7 | **`0x74`/`0x75` readback, category `0x03` idx = dest_id -- §4a** |
| surround tab (global) | `0xeb` | `0xab` | - | `[18]` bit7 pre/post + format, `[20]` delay, `[22-23]` level, `[25-30]` bypass/mute/dim (§11) | none |
| surround tab (per-speaker ×16) | `0xea` | `0x87` | speaker 0-15 | delay/level/invert + 16-band EQ (§11) | none |
| oscillator (matrix insert) | `0xd3` | `0x53` | routing frame, source bank `0x0c` idx 0/1 = osc 1/2 (§7) | none |
| oscillator (settings panel: freq/level/mute) | `0x0a` | `0x12` | - | packed value byte @17: `0x01`/`0x04` osc1/2 freq, `0x30` level, `0x40`/`0x80` osc1/2 mute (§11) | none in `0x73` |
| DC-coupling | `0x26` | `0x12` | - | 0/1 @17 (§11) | none in `0x73` |

---

## 11. Settings window -- device-side vs host-side

What the Settings/Device window controls actually do, from the captures
(all Windows-VM Launcher + USBPcap, 2026-08):

| Feature | Capture | Device traffic | Verdict |
|---|---|---|---|
| **Line-out level + mute** | `settings-linevol-...` | `bus_level` `0x47` / `bus_mute` `0x48` on **bus 3** | **real, confirmed** -- in CLI (`set-bus-level line` / `set-bus-mute line`) |
| **Reamp-out level** | `settings-linevol-...` | `bus_level` `0x47` on **bus 4** | **real, confirmed** -- in CLI (`set-bus-level reamp`) |
| **Output trim** (Mon A / Mon B / Line) | `settings-trim-...` | param `0x4b`, 20 frames | **real, confirmed** -- readback @24-25 (section 6); not yet in CLI |
| **Surround tab** | `macos-srrnd-tab` + `srrnd-20-21` + `srrnd-L/R-*` + `srrnd-EQ-L/R-*` | `0xab`/`0xeb` global + `0x87`/`0xea` per-speaker ×16 | **decoded 2026-09-03** -- pre/post = `[18]` bit7 (not `[19]`), per-speaker level/invert/delay/**16-band** EQ (2 UI pages); open: EQ Q byte, HPF/LPF mode-flag values (§11) |
| **Pan law** | `panning-law-6-3-45-0` (usbmon, 2026-09-03) | `SET_GLOBAL` `0x12` / param `0x24` / value @17 | **DECODED** -- enum `0`=-6 `1`=-3 `2`=-4.5 `3`=0 dB (Launcher button order); no readback. CLI `pan-law` |
| **Clock source** | `clock-source-WC-adat-adatx2-adatx4-spdif-usb-oven` (usbmon, 2026-09-03) | `SET_GLOBAL` `0x12` / param `0x04` / value @17 | **DECODED** -- enum `0`=Oven `1`=WordClock `2`=ADAT `3`=ADATx2 `4`=ADATx4 `5`=S/PDIF `6`=USB; readback `0x73` @19. CLI `clock-source` |
| **Reamp mute** | `reamp-mute` (usbmon, 2026-09-03) | `SET_PARAM` `0x13` / param `0x48` (`bus_mute`) / bus `4` | **confirmed** — reamp is bus 4; `bus_mute` works there |
| **Oscillator** -- matrix insert | `matrix-source-enum` | `0x53` routing frame, source bank `0x0c` | **real device command** (§7) |
| **Oscillator** -- settings panel (freq/level/mute) | `macos-settings-osc1-mute-1khz` etc. | opcode `0x12` / param `0x0a` / packed value @17 | **DECODED (native macOS, 2026-09-01)** -- the old "zero frames" was an inbound-only capture; see §11 below |
| **Screen brightness** | `macos-scrbrght-0-100-50-multvalue` | opcode `0x12` / param `0x0e` / value 0-100 @17 | **real, confirmed (native macOS)** -- readback @26; in CLI (`set-brightness`). VM sent nothing because the slider is a no-op under the VM. |
| **DC-coupling** | `macos-settings-tb-fast-normal-safe-DC-Coupling-Off-on` | opcode `0x12` / param `0x26` / value 0-1 @17 | **DECODED (native macOS, 2026-09-01); HW round-trip confirmed 2026-09-02 (user, via webui)** -- talkback fast/normal/safe modes in the same capture sent nothing |

So the Settings window is a genuine mix: output levels/mute, the three
trims, surround-EQ pre/post, screen brightness, **the oscillator panel**
and **DC-coupling** are real device commands; talkback latency modes and
Thunderbolt/buffer settings are host-side. **Lesson (seen twice now, osc +
readback): an inbound-only or VM capture that shows "zero frames" is not
proof a control is host-side -- recapture with the OUT endpoint on native
macOS before concluding.**

### Oscillator -- two access points (settings panel DECODED 2026-09-01)

**In the routing matrix:** right-click an output → insert oscillator. It
becomes a matrix source, bank `0x0c` (idx 0/1 = oscillator 1/2), sent as
the normal `0x53` routing frame (confirmed, §7).

**The settings-tab oscillator panel** (two oscillators, each freq
1kHz/400Hz + mute, plus a level selector): `SET_GLOBAL` (opcode `0x12`),
param **`0x0a`**, one **packed value byte** at offset 17:

| bit | field |
|---|---|
| `0x01` | osc 1 frequency (0 / 1) |
| `0x04` | osc 2 frequency (0 / 1) |
| `0x30` | level, 2-bit field @ bits 4-5: `0`=0 dBFS `1`=−6 `2`=−12 `3`=−18 |
| `0x40` | osc 1 mute |
| `0x80` | osc 2 mute |

No `0x73` readback (state stream shows only meter jitter through every
change). Open: whether the level field is shared or per-oscillator (the
capture only moved one); bits `0x02`/`0x08` unused. The earlier
"`settings-osc1-2-fq-lvl` sent zero frames" was an **inbound-only
capture** -- the recapture with the OUT endpoint present
(`macos-settings-osc1-mute-1khz` / `-osc2-mute-400hz-1khz` /
`-osclvl-6-12-18-0db`) shows every click is a `0x12`/`0x0a`.

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

### Surround monitoring tab -- two frames

The Surround tab has a **global** whole-state frame and a **per-speaker**
one. No `0x73` / `0x74` readback for any surround param. Both opcodes are
`constraints.observed_opcodes_launcher_only` -- no builder, never sent.

Antelope's docs say the Orion Studio SC surround system covers **23+
layouts, stereo → Dolby Atmos 9.1.6**, but the full feature **needs the
MRC (Multichannel Remote Control)** hardware. Without it only **2.0**
(`[18]`/`[19]` = `0x02`/`0x9f`) and **2.1** (`0x23`/`0x82`) are selectable
— all that could be captured. Manual p.76 has the full layout list. A
**Room Correction** subsystem also exists (undecoded).

**Global: `0xab` / `0xeb`** (`macos-settings-srrndeq-post-pre` +
`macos-srrnd-tab-...` + `srrnd-20-21`):

| off | field | notes |
|---|---|---|
| 16-17 | `0xeb` param, `0x99` const | |
| 18 | **flags A — bitfield** | **bit 0** = LFE / 2.1 (`0x02` 2.0 → `0x03` 2.1). **bit 5 (`0x20`) = bass-management on** (`srrnd-bass-management-on-off`: 2.1 BM-on `0x23` / BM-off `0x03`; BM defaults on when you enable 2.1). **bit 7 (`0x80`) = EQ pre/post** (`macos-srrnd-tab` `0x02`↔`0x82`; the 2026-09-01 note wrongly put this on `[19]`). `[19]` also moves with format (`0x9f` 2.0 / `0x82` 2.1) |
| 19 | flags B (base `0x9f`) | moves only with the format (`0x9f` 2.0 / `0x82` 2.1) |
| 20 | **global surround delay**, uint8, 0.1 ms/step (base `0x06` = 0.6 ms floor) | swept `0x06`..`0x2d` |
| 22-23 | **surround monitor level**, LE16 (base `600` = 0 dB) | 0..760 = **−60..+16 dB** at 0.1 dB/step (user-confirmed 2026-09-03) |
| 25-26 | **per-speaker BYPASS mask**, LE16 — bit N = speaker N (1 = active, 0 = bypassed); default `0xFFFF` | confirmed (`srrnd-L-bypass`: bypassing L → `0xFFFF`→`0xFFFE`) |
| 27-28 / 29-30 | **mute / dim**, per-speaker LE16 masks | mute confirmed by the Ctrl-click SOLO ("mute all others") writing only the selected bit |
| 23-95 | **2.1 bass-management window** — structure identified (`srrnd-bassmanagement-*`): a HIGH-PASS section + LOW-PASS section (each: cutoff LE16 Hz 20–320, type Butterworth/Linkwitz-Riley, order 2/4/8 one-hot, bypass — packed as bits near `[25]`/`[26]`) + a MIXER (per-channel fader + mute/solo = high bit on a level word). Full byte-map = a focused pass; frames saved | `[23-24]` = `04 64` = LFE marker |
| 40-168 | fixed default template | `23 00 00` then `[80][80][600][0]` repeated -- **not** the live EQ curve (that's the `0x87` frame) |

**Per-speaker: `0x87` / `0xea`** -- DECODED 2026-09-03 (`srrnd-L/R-*`,
`srrnd-EQ-L/R-*`). `[17]` = `0x75` const, `[18]` = speaker `0..15`. The
Launcher sends 16 (one per speaker) when the tab opens or the format
changes. Per speaker:

| off | field | notes |
|---|---|---|
| 19-20 | **delay**, LE16, **0.1 ms/step** (UI 0.6–100.6 ms, user-confirmed) | |
| 21-22 | **level**, LE16 (base `600` = 0 dB, 0.1 dB/step, **−60..+16 dB**, user-confirmed) | **`[22]` bit 7 = phase invert** (level tops at 760 = `0x02F8`, so bit 7 is free) |
| 23… | **16 parametric EQ bands**, 7-byte stride — **fully decoded** (`srrnd-EQ-Q-and-mode`) | The frame carries all 16; the Launcher shows them as 2 pages of 8. **Band N at `23 + 7·N` (N 0-15): `<freq LE16 Hz> <Q LE16> <gain LE16 signed> <mode byte>`.** Freq = literal Hz, 20–20000 Hz/band. **Q = LE16, value ×100** — `10`=0.1 … `1800`=18.0, default `0x0047`=71=Q 0.71 (the byte earlier mislabelled a `0x47` marker is the Q low byte). Gain = LE16 signed 0.01 dB, `−2400`…`+1200` = −24…+12 dB. **Mode byte:** `0x02` = bell (bands 2-15). **Bands 1 & 16 are the end slots** — two user modes each (shelving / band-pass; a "flat" UI line is just shelf/pass at 0 gain). Observed mode-byte values: band 1 `{0x00, 0x04}`, band 16 `{0x01, 0x03}` (both rest at `0x00` before first touch) — not a clean bitfield; which value is shelf vs band-pass not yet pinned. Gain + Q work in both modes (Q sets the slope). Centre channel: end bands are bell (`0x02`) only. **LFE** (`srrnd-LFE`) = speaker index 2 in 2.1, a normal `0x87` strip (same 16 bands, level, delay, invert). Ranges user-confirmed |

R speaker = index 1, byte-identical to L. `copy speaker` / `paste speaker`
just re-send `0x87` frames. Essentially fully decoded — only the exact
end-band mode-byte ↔ UI-label mapping and formats past 2.1 (need the MRC)
remain. `params.surround_monitor` + `params.surround_speaker`.

### DC-coupling (`0x12` / `0x26`) -- DECODED 2026-09-01

`macos-settings-tb-fast-normal-safe-DC-Coupling-Off-on`: the DC-coupling
toggle is `SET_GLOBAL` (opcode `0x12`), param **`0x26`**, value `0`/`1`.
**Hardware round-trip confirmed 2026-09-02** (user, via the webui
`POST /api/dc-coupling`): the toggle does what it should on the outputs.
No `0x73` readback, so state is tracked client-side.
No `0x73` readback. The **talkback latency modes** (fast / normal / safe)
in the same capture sent **nothing** -- host-side, or a path not on this
interface. This closes the old `settigs-thunderb-lat-dccp` "zero frames"
item: DC-coupling does talk to the device.

### Clock source (`0x12` / `0x04`) -- DECODED 2026-09-03

`clock-source-WC-adat-adatx2-adatx4-spdif-usb-oven` (usbmon): `SET_GLOBAL`
(opcode `0x12`), param **`0x04`**, value @17:

| value | source |
|---|---|
| 0 | Oven (internal OCXO — power-on default) |
| 1 | Word Clock (BNC in) |
| 2 | ADAT |
| 3 | ADAT x2 (S/MUX2) |
| 4 | ADAT x4 (S/MUX4) |
| 5 | S/PDIF |
| 6 | USB (follow host) |

**Readback = `0x73` offset 19**, 1:1 with the commanded value. This
resolves the "`0x73` @19 blips `0x06`→`0x00` ~3 s after connect" startup
artifact that appears in *every* capture: `[19]` is the clock source, and
at connect the device is USB-clocked (`6`) then re-locks to its saved
source (`0` on the reference unit). (Offset 17's separate `0x08`→`0x00`
blip is probably a clock-lock status byte — still undecoded, but now
clearly distinct from 19.) Same param `0x12`/`0x04` as the Zen Go, which
has only 3 sources and no word clock. CLI `clock-source [--set N]`.

**⚠ Host-side lock (Linux):** the Orion **ignores** both this frame and
`sample_rate` (`0x03`) while the host has its USB audio interface
**streaming** — verified 2026-09-03 (PipeWire holding
`/dev/snd/pcmC3D0p`, stream `Running` altset 1; set clock→OVEN and stepped
every rate → `0x73` `[18]`/`[19]` never moved, at any poll delay). Not a
device or protocol limit — on macOS the Launcher releases the CoreAudio
stream first. On Linux: `systemctl --user stop pipewire pipewire-pulse
wireplumber pipewire.socket pipewire-pulse.socket`, change, restart. This
is why `set-sample-rate` was never hardware-round-tripped.

### Pan law (`0x12` / `0x24`) -- DECODED 2026-09-03

`panning-law-6-3-45-0` (usbmon): `SET_GLOBAL` (opcode `0x12`), param
**`0x24`**, value @17 — a 4-way enum:

| value | centre attenuation |
|---|---|
| 0 | -6 dB |
| 1 | -3 dB |
| 2 | -4.5 dB |
| 3 | 0 dB |

The order is the Launcher's own button order (not monotonic in dB). **No
readback** — nothing in `0x73` moved through the whole sweep, and cat
`0x16` (once suspected) tracks it neither. Closes the long-open "pan law
never captured" item, and confirms it is *not* a 4th target of
`output_trim` `0x4b` (ruled out by a live probe the same day). CLI
`pan-law [--set N]` (CLI-cached, no device verify).

### Thunderbolt / latency

`settigs-thunderb-lat-dccp.pcapng` -- zero outgoing frames. Latency/buffer
is a host driver setting; Thunderbolt is inactive over USB. (DC-coupling,
which that capture never exercised, is now decoded -- see above, `0x12`/`0x26`.)

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

**No readback in the passive stream** -- but mixer state IS available via
the `0x74`/`0x75` query protocol: **category `0x04`, index = mix number
0-3**, now **fully decoded and hardware round-trip verified** (§4a). The
record is 33 three-byte slots in this frame's own field order, and slot N
is the strip this frame writes as `channel` N. That round trip also
confirmed `[18]` is genuinely the mix number (all four mixes return their
own record -- previously only mix 0 had ever been observed) and that
`[22]` is stored send state rather than a meter. So "write-only over USB"
was wrong for the mixer too. AuraVerb is category `0x0a` (decoded +
hardware round-trip verified 2026-09-03 -- see the §12 AuraVerb section);
`0x1b` is the mixer bus level/range table (still undecoded).

**Both directions are in the CLI.** `mix-status [mix]` is the live read
(`protocol.parse_mixer_record`); `mix-set <mix> <ch|master> [--fader dB]
[--pan] [--send] [--mute] [--solo]` is the write.

Because this frame carries the strip's **whole** state every time, a
partial write would silently reset every field the user didn't name. So
`mix-set` read-modify-writes: read category `0x04`, apply the named flags,
write the strip, re-read to verify. No local cache -- and if the read
fails it refuses to write rather than clobber blindly. It also reports
when *other* strips moved, which happens with a linked pair or when solo
re-mutes the rest (both host-side, as in the Launcher).

`protocol.build_mix_command(...)` builds the frame directly; `0x17` is in
`constraints.allowed_opcodes`. Note the builder emits the send byte only
if the profile declares a `send_offset` -- the Zen Go's mixer strip has no
send (`protocol.mix_has_send`).

### Mic modeling / "emuMic" (`0x17` / `0xe5`) -- decoded 2026-08-31

The front-panel **EMU** button, on **preamps 5-12** (8 channels -- the 8
emumic routing taps). It shows on a channel only in **Mic mode**; earlier
notes said "7-12" because the reference unit had 5-6 in Line (corrected
2026-09-03). Runs Antelope's mic-emulation DSP on that preamp (for use with
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
| 18 | **channel** | 0-based input channel index − 4 (preamp 5 → `0` … preamp 7 → `2` … preamp 12 → `7`) |
| 19 | **enabled** | `1` = modeling on, `0` = off (also zeros @20-22) |
| 20 | **model id** | `0` = EdgeDuo / raw (no emulation, default); `1`…`N` = the emulation models (`profiles/mic_models.json`) |
| 21 | **channel-order swap** | `0`/`1` -- a switch that swaps the pair's channel order |
| 22 | **polar pattern** | a **0-based index**, always. Model `0`: `0`-`100` continuous morph (`0` omni / `50` cardioid / `100` figure-8). A selected emulation model: a small index into that model's pattern list -- range per model: `0` only (fixed mic), `0`-`2` (3-way omni/cardioid/fig-8), or `0`-`8` (9-detent multipattern). Selecting a model presets `[22]` to the model's **default** index (`0` / `1` / `4`) -- this preset value is what `mic_models.json` earlier called `pattern_class` |

Whole state every frame; params **mirror across the linked preamp pair**
host-side (Launcher sends `[18]=N` then `[18]=N+1`). From
`macos-ch7-8-micmodeling-*` / `macos-ch9-10_11-12-micmodeling-*` (model 0,
pattern swept 0→100 step 4; swap; enable/disable),
`emumic-model-select-tokyo800t-…-b47TU` (18 models cycled on preamps 7-8
→ `[20]` = `0x01`…`0x12`), and **`macos-emumic-polar-patterns`
(2026-09-01)** -- every model 0-18 selected and its polar-pattern control
swept: `[22]` fixed at `0` for models 2/5/6/8/13/14/15/17, `0`-`1` for
1/12/16/18 (a 3rd value not exercised), `0`-`2` for 3/4/7, `0`-`8` for
9/10/11. `[21]`/`[23]`/`[24]` stayed `0`.

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
positions in the list the Launcher shows you. Full id→name→default-pattern
table in `profiles/mic_models.json` (+ each model's observed `[22]` range);
readback category not identified yet (§4a).
Antelope's own naming (Berlin / Vienna / Tokyo / …) is used; the classic
mics being emulated are not spelled out (that's the licensed IP).

The modeled signal is routing **source bank `0x01`** ("emumic", §7),
8 indices = preamps 5-12 -- the full modeling range. The EMU *button*
shows on a channel only in **Mic mode** (hence the earlier "7-12": 5-6
were in Line on the reference unit).

**Preamps 5-6 -- CAPTURED 2026-09-03** (`webui-emumic-preamp56-...frames.txt`,
usbmon while the webUI drove EMU on preamp 5/6). Directly on the wire:

- `[18] = 0x00` for **preamp 5**, `0x01` for **preamp 6** -- the
  `channel_bias -4` mapping holds to the bottom of the range (was
  extrapolation). Each change is written to **both** channels of the pair,
  `[18]=1` then `[18]=0`, ~72 ms apart (same two-per-pair pattern as the
  Launcher's link sync).
- `[20]` model seen `0x01`/`0x08`/`0x10`; selecting a model presets `[22]`
  to that model's default (model 8 -> 0, model 16 -> 1). `[21]` swap and
  `[22]` pattern both exercised (0 and 1).
- **Disable** = `e5` with `[19]=0` and model/swap/pattern zeroed, then
  `SET_PARAM 0x51` ch 4 & 5 = 0 (phantom off), then a `SET_PARAM 0x50`
  ch 4 & 5 gain re-sync (both channels stepped to the same values), then
  `SET_LINK 0x14 a2 00 02` enable 0 (**unlink pair 2** = preamps 5&6).
  So preamps 5-6 are link pair 2, and the phantom/gain sync addresses
  them as channel index 4 & 5.

**Listening test -- CONFIRMED 2026-09-03 (webUI).** The `emumic` taps
carry the *modeled* signal and it is correct: an R112 model sounds like an
R112, a U87 model has the expected character, switching the model audibly
changes it -- matching the Launcher. **`emumic5` and `emumic6` carry the
same mono signal** for a mono emulation: the Edge Duo's 2 inputs collapse
to one signal on both taps, so only one is needed; the two distinct taps
matter only for a stereo modelling mic (Edge Quadro: 4 inputs -> 2
signals).

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
| 22 | *(constant `0x64`)* -- wet/mix locked at 100%; stayed 100 through the 2026-09-03 differential sweep and is mirrored as such in the `0x0a` readback (not a hidden 9th control) | -- | 0x64 |
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
(facts only). AuraVerb is device-*bundled* (no per-plugin activation) so
it is **in scope**; still off-limits is the licensed AFX plugin chain and
anything touching license state. `0x1d` is in `constraints.allowed_opcodes`;
`protocol.build_auraverb_command`; CLI `auraverb`.

**Readback + hardware round-trip -- DONE 2026-09-03.** No `0x73` effect,
but there is a dedicated readback: **`0x74` category `0x0a`** (§4a table).
One record: a `0x00` header then four 11-byte blocks (Mix 1..4), each the
`0x1d` payload minus `@18`, in the same order, then `[9]` = enabled
(`01`/`00`) and `[10]` = `0xff` const. The 43-byte record truncates
Mix 4's block to 9 bytes (no enable byte). Decoded by **differential
readback** against the live Orion: set each param via `auraverb --<flag>`,
re-read `0x0a`, watch which byte of the Mix-1 block moved -- all 8 params
+ the enable bit mapped 1:1, and rewriting the pre-sweep values
reproduced the record byte-for-byte. A reverb-level round trip
(26→33→26) verified against the readback and restored clean.
`protocol.parse_auraverb_record`; CLI `auraverb` now live-reads and does a
verified read-modify-write (cache kept only as an offline fallback);
`selftest.py` `t_auraverb` / `t_write_auraverb`. The `0x0a` block exists
for **all four mixes**, so each mix has its own AuraVerb instance (only
Mix 1 has been written).

---

## 13. Open questions

| Item | Status |
|---|---|
| Routing frame (`0x53` / `0xd3`) | §7: destination map (0-14), all 12 source banks, all 15 destination channel counts, and the `(bank,index)`-per-channel array model all confirmed. **Readback = §4a category `0x03`** (verified byte-identical against CLI writes). CLI `matrix-status` = live read of all 15 groups; `route <dest> <chan> <source>` covers line out (16 ch) + HP1/HP2/Mon A/Mon B/Reamp (2 ch) and self-verifies. Open: wire `route` writes for the other 9 destinations. |
| Virtual mixer (`0x17` / `0xd4`) | §12: frame decoded 2026-08 (`macos-mix1-...`) -- `mix`/`channel`(1-32)/`fader`(0-90)/`pan`(0x20=centre)/`mute`(@21 bit6)/`solo`(@21 bit7)/`send`(0-96), plus mix link via `SET_LINK` space `0x03`. Readback = §4a category `0x04` (idx = mix number) + `0x1b` (bus levels), partly decoded. Not in the CLI. |
| Mic modeling / emuMic (`0x17` / `0xe5`) | §12: enable / model id `[20]` / polar-pattern `[22]` / channel-order swap all decoded (`macos-ch7-8-micmodeling-*`, `emumic-model-select-…`, `macos-emumic-polar-patterns`). `[22]` is a polar-pattern **index** for selected models too (0 / 0-2 / 0-8 by model); model select presets it to the model default. 18 emulation models in `profiles/mic_models.json` (account-bound list). `build_micmodeling_command`; not in CLI. Readback category not yet identified (§4a `0x07`/`0x1a` are the unmapped DSP-EQ candidates). Preamps 5-6 CAPTURED 2026-09-03 (webUI usbmon, `webui-emumic-preamp56-...`): `[18]=0x00`/`0x01` on the wire, pair = link pair 2, disable reverses phantom+gain+link. Open: whether models 1/12/16/18 have a 3rd pattern (only 0-1 swept); whether model ids are global or list-position; the readback category (none found -- `0x07`/`0x1a` are the unmapped DSP-EQ candidates). |
| ADAT vs physical `SET_LINK` | both use `space` byte `0x00` -- byte-identical frames (§7). S/PDIF (space `0x01`) is now distinguishable. Open: does one space-0 command link pair N in *both* physical and ADAT? Needs different per-channel gains or a hardware test |
| ~~Pan law~~ | **DECODED 2026-09-03** — `SET_GLOBAL 0x12` / param `0x24` / 0-3 = -6/-3/-4.5/0 dB (`panning-law-6-3-45-0`). No readback. CLI `pan-law`. |
| ~~Clock source~~ | **DECODED 2026-09-03** — `SET_GLOBAL 0x12` / param `0x04` / 0-6 (Oven / WC / ADAT / ADATx2 / ADATx4 / S/PDIF / USB). Readback `0x73` @19 — which also explains the `0x73` @19 startup blip (USB→saved source re-lock). CLI `clock-source`. |
| S/PDIF gain + link | **confirmed** (`spdif-gain-link`, 2026-08): gain param `0x5c`, readback `91`/`92`, link via `space=1`. In the CLI. |
| Oscillator | **resolved** -- matrix insert = routing bank `0x0c` (§7); settings panel = `0x12`/`0x0a` packed byte (§11). Open: level field shared vs per-oscillator |
| Screen brightness | **resolved (native macOS)** -- opcode `0x12` / param `0x0e` / value 0-100 @17, readback @26 (`macos-scrbrght-0-100-50-multvalue`). VM had no traffic only because the VM Launcher no-ops the slider. |
| Sample rate | **resolved (native macOS)** -- opcode `0x12` / param `0x03` / index 0-6 @17, readback @18 (`macos-smplrt-...`). CLI `sample-rate` / `set-sample-rate`. Open: the clock/PLL/buffer bytes @21-23,27 that move only at 88.2k/176.4k. |
| Surround tab (`0xab`/`0xeb` global + `0x87`/`0xea` per-speaker ×16) | decoded 2026-09-03 (§11). Global = pre/post `[18]` bit7 + format + level + delay + dim/mute/bypass. Per-speaker = level (+invert) + delay + **16 EQ bands** (`<freq><Q><gain><mode>`, 7B each; Q ×100 0.1-18; mode `0x02` bell / `0x00` shelf / `0x04` band-pass on end bands 1 & 16; centre = bell only). No readback. Minor-open: speaker-index↔channel map for formats past 2.0; centre end-band mode value |
| DC-coupling | **resolved** -- `0x12`/`0x26`, value 0/1 (§11). Talkback fast/normal/safe latency modes send nothing (host-side) |
| Thunderbolt / latency | zero outgoing frames -- host driver setting; TB inactive over USB |
| Offsets 17 / 19 blip | ~3.0 s after the Launcher starts, in every capture **including the no-user-interaction INIT capture** -- Launcher handshake event, not user- or feature-related. Ignore. |
| Offsets 139-140 ramp (129-136 in INIT) | first ~0.12 s of every capture -- device/connection startup settling. Ignore. |
| Offsets 157-168 / 169-180 / 221-232 | **resolved 2026-09-01** -- per-channel input meters, `157 + channel` (three mirror copies). §9. |
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
`profiles/discrete_8_pro_sc.json` (contributed by PR). Param IDs
are shared; **semantics are not guaranteed to be.** The lessons from that
sibling device, folded into `orion_studio_sc.json` as `family_notes`,
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
| in-band readback (§4a) | `0x74` req / `0x75`@1=`0x00` resp | **same, byte-identical** (re-checked 2026-09-01) |
| ~~"connect name report"~~ | — | ~~`0x75` = ASCII name/serial/fw~~ **corrected: that IS a readback response, category `0x01`** -- the same category that carries name+serial on the Orion. It only looked device-specific because the Orion's `0x75` responses were being filtered as meter noise. |
| readback connect walk | 113 records / 10 categories | **3 queries only** -- cat `0x00`, `0x01`, `0x11`, all index 0. So **no record counts are known for the Zen Go** → no safe index bounds → **do not sweep** (§4a hazard) |
| mixer frame | opcode `0x17`, subcmd `0x05`, has a **send** byte @22 | opcode **`0x16`**, subcmd **`0x04`**, **no send** byte |
| mixes / strips | 4 mixes × 32 | 2 mixes × 16 |
| preamps | 12 | 2 (A1 = ch0, A2 = ch1) |
| gain array offset | `0x73` @49 | `0x73` **@40** |
| status array offset | `0x73` @61 | `0x73` **@42** |
| bus block | `28 + 3N` | `28 + 2N` |
| clock source readback | **`0x73` @19** (`0x12`/`0x04`, 7 sources incl. word clock — confirmed 2026-09-03) | `0x73` **@19** (`0x12`/`0x04`, 3 sources, no word clock) |
| source bank: mute / osc / emumic | `0x0b` / `0x0c` / `0x01` | **`0x08` / `0x09` / `0x0a`** |
| new: output volume | buses | *also* an `0x16`/`0xd4` strip at `(mix 1, ch 3)` |
| new: DSP opcodes | `0x1d` AuraVerb | **`0x1a` / `0x1c` (`0xd5`), `0x23` (`0xd7`)** -- undecoded, forbidden |

**Routing (`0x53`/`0xd3`) -- decoded 2026-08-31.** Same frame as Orion
(`d3 41 <dest>` then `(bank,idx)` pairs from @19). The slot index in the
mixer strip-input map = **mixer strip number − 1** (slot 0 = strip 1).
Source banks: `0x00` preamp (0-1), `0x01` computer playback (idx N =
playback N+1), `0x02` S/PDIF in (L/R), `0x08` MUTE, `0x09` oscillator
(1/2), `0x0a` emumic; `0x03` (4 ch, strips 1-4's default) unidentified.
Destination groups: **6/7/8/9** are one logical 32-slot map (slots 0-15 =
the 16 strips, 16-31 unused) that the Launcher always writes to all four
in lockstep -- the mixer's *global* strip-input assignment (per-mix
level/pan/mute stays independent); **5** is a separate 4-slot map (strips
1-4 only); **3** an 8-slot map mirroring the first 8 of 6-9.

Still open: source bank `0x03`; the exact role of dest groups 3 and 5;
the DSP/mic-modelling frames; the meter byte-map; the two output-volume
paths; `param 0x66` (bus dim/mono?); `param 0x49` (set to 12/15 during
mixer use). See `open_questions` in the profile.
