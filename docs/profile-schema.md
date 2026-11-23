# Device profile schema (`profiles/*.json`)

A **profile** is the single source of truth for one Antelope device's
control protocol. `antelope/transport.py`, `antelope/protocol.py` and
`antelope/cli.py` contain **no device-specific values** — every VID/PID,
byte offset, opcode, param id, range and enum comes from the profile
dict. Point `--profile` at a different file and the same code drives a
different device.

This doc describes the keys the code reads and the conventions the
profiles follow. The reference implementations are
`profiles/orion_studio_sc.json` (most complete),
`profiles/zen_go_sc.json` and `profiles/discrete_8_pro_sc.json`.

Application-facing software calls the bundled reverb **Gazelle Reverb**;
`auraverb_command` and related names below are retained as protocol-facing
compatibility keys for the device feature identified as AuraVerb in the
evidence.

---

## Conventions

- **Numbers may be hex strings or ints.** `"0x50"` and `80` are both
  accepted anywhere a byte value is expected — `protocol._as_int()`
  normalises. Offsets are usually plain ints, ids/magics usually hex
  strings. Be consistent within a file.
- **Byte offsets are 0-indexed into the 320-byte HID report**, both
  directions.
- **`status`** on any block: `"confirmed"` / `"capture-confirmed"` /
  `"observed"` (seen in a capture, not decoded) / `"unconfirmed"` / free
  text. Normal automation may rely on `confirmed` and
  `capture-confirmed`; other statuses are descriptive only.
- **`evidence`** / **`notes`**: free text. `evidence` names the capture
  and what it showed; `notes` is everything else. Keep the capture name
  in `evidence` so a claim can be re-checked.
- **Write-evidence rule**: for a new `confirmed` writable parameter, record a
  date, the value sent, the device-side readback before/after, and restoration
  of the original value. Vendor-software traffic or an observed UI/audio
  effect is not a readback witness. If those facts are absent, use
  `observed`/`unconfirmed` and keep the command non-buildable when appropriate.
- **Index bounds**: observed indices confirm that those indices exist; they do
  not prove the first invalid index is safe to send. Mark an untested bound as
  derived and document the hazard.
- **`_comment`** keys are ignored by the code — inline documentation.
- Unknown keys are ignored. Adding a key the code doesn't read yet is
  fine (it documents intent for a future CLI command or the webUI).

---

## Top-level keys

| key | required | purpose |
|---|---|---|
| `device` | yes | identity (VID/PID) — used to find the hidraw node |
| `profile_schema` | yes for labeled profiles | format identifier/version for cross-client profile metadata |
| `labels` | recommended | stable section, address-space, and parameter display labels |
| `features` | recommended | launcher surfaces, controls, dimensions, labels, and enabled/readiness state |
| `transport` | yes | HID report size + endpoints |
| `frame` | yes | every wire frame shape + the incoming report maps |
| `channels` | yes | the physical input channel space |
| `params` | yes | catalogue of settable parameters |
| `buses` | if the device has output buses | output-bus address space + names |
| `adat`, `spdif` | if present on the device | extra input address spaces |
| `mixer` | if decoded | virtual-mixer summary (human-facing; the frame is in `frame.mix_command`), plus optional profile-driven surface/link metadata. `has_master` defaults to true; set false for devices whose channel space starts at 0 with no master strip. |
| `afx` | optional | device AFX channel/slot capacity and reference to the shared effect catalog; descriptive metadata, not a runtime write contract |
| `afx_inserts` | optional | contract for the generic AFX insert codec and builders |
| `constraints` | strongly recommended | machine-enforced bounds (`protocol.check_*`) |
| `hazards` | recommended | *why* each constraint exists (carried across the family) |
| `family_notes` | recommended | what is / isn't shared with sibling devices |
| `unresolved_state_offsets` / `open_questions` | optional | evidence boundaries, so "MVP done" isn't mistaken for "protocol done" |

---

## `device`

```json
"device": {
  "name": "Antelope Zen Go Synergy Core",
  "vid": "0x23e5",
  "pid": "0xa015",
  "bcdDevice": "06.06",
  "status": "confirmed",
  "notes": "...", "evidence": "..."
}
```

`vid` + `pid` are read by `transport.find_hidraw()` to locate
`/dev/hidrawN`. `bcdDevice` is documentation only.

---

## `transport`

```json
"transport": {
  "type": "hid",
  "report_size": 320,
  "out_endpoint": "0x01",
  "in_endpoint": "0x82",
  "poll_interval_ms": 4,
  "uses_numbered_reports": false
}
```

- `report_size` — every build function pads the packet to this length;
  `transport.write()` refuses anything else.
- `out_endpoint` / `in_endpoint` — documentation (hidraw doesn't need
  them); the numbers matter for reading captures.
- `uses_numbered_reports` — if the HID report descriptor has no Report
  ID, Linux hidraw writes need a leading `0x00` (making them 321 bytes).
  Not auto-handled yet — see `family_notes`.

---

## `afx` and the shared effect catalog

AFX capacity is device-specific. An optional top-level block records it:

```json
"afx": {
  "channel_count": 32,
  "slots_per_channel": 8,
  "capacity_status": "documented",
  "catalog": "afx_effects.json",
  "evidence": "Public device documentation or model-local capture reference",
  "notes": "Capacity and protocol-addressing limitations"
}
```

`channel_count` counts mono processing channels; `slots_per_channel` counts
insert positions in each channel's chain. Both are positive integers when
known, or `null` when unknown. Missing `afx` means undeclared capability, not
zero channels. `catalog` resolves relative to the device profile's directory.
Capacity and catalog metadata do not authorize writes; explicit runtime contracts govern the operator test path.
The WebUI uses positive integer counts to expose the AFX popup and size its
channel selector and selected channel's rack layout. Undeclared capacity
hides the launcher; the popup does not infer slot contents, account ownership,
or channel-to-readback mappings.
Each device needs its own capacity evidence; another profile's counts are
not defaults.

Orion declares 32 channels and eight slots from
[Antelope's November 2019 demonstration](https://en.antelopeaudio.com/2019/11/ricky-damian-demonstrates-the-capabilities-of-orion-studio-synergy-core/).
The existing `0x19` layout also describes eight slots per strip. Its 64 outer
records are protocol storage. Direct mono load/remove tests verified indices
2–31 against the same write-channel indices on 2026-10-01, restoring every
chain; index 0 was owner-tested earlier. Index 1 mono writes and storage
indices 32–63 remain unexercised by that test. Capacity metadata never changes the safety
bounds in `frame.readback.category_counts`. Channel count times slot count
is the number of insert positions, not a guaranteed simultaneous instance
budget. DSP resources, stereo use, and per-effect instance limits are
separate facts.

`profiles/afx_effects.json` is the shared catalog manifest, separate from device
profiles and `mic_models.json`. Each effect is authored in its own
`profiles/afx/<stable_id>.json` file. The manifest retains catalog-wide metadata
and an ordered `effect_files` array instead of inline `effects`:

```json
{
  "storage_schema": {"id": "antelope-afx-catalog-manifest", "version": 1},
  "effect_files": ["afx/altec_436c.json", "afx/audiobaton.json"]
}
```

This is a storage excerpt, not a complete catalog. `catalog_schema` still
identifies the logical `antelope-afx-effect-catalog`, version 1;
`storage_schema` identifies only the split-file packaging. Existing device
profiles keep `"catalog": "afx_effects.json"`. File references resolve relative
to the manifest, and their order is the effect order.

Python consumers call `antelope.catalog.load_catalog(path)` to obtain the
existing dictionary containing inline `effects`; storage-only fields are
removed. Omitting `path` selects the repository catalog. Legacy inline catalogs are accepted too. Plain `json.load` on the
manifest does not load effect definitions. For tools that require a single
JSON document, export the resolved catalog:

```sh
python3 tools/export_afx_catalog.py --catalog profiles/afx_effects.json \
  --output /tmp/afx-catalog.json
```

Omit `--output` to write JSON to stdout. Exported JSON is derived output, not
another source to edit or commit. Edit an existing plugin directly; when adding
a plugin, add its stable-ID file and an ordered manifest reference. Preserve
its model-specific implementations, unknown fields, evidence and verification
flags. Do not infer new runtime capabilities from this storage layout.

The first reference set contains 80 named
effect types from Gazelle's Discrete 4 read-only measurements dated
2026-09-13, with 729 declaration-derived control names. The source profile
is pinned in `provenance`; unnamed device types are omitted. These entries
are not an Orion effect list or a list of installed/licensed effects.
`catalog_schema` identifies the catalog format and version. Each future
entry has a stable application ID, a presentation category, an original description, controls, and
device-specific implementations. The following is an entry template,
not a decoded effect:

```json
{
  "id": "effect_key",
  "name": "Effect display name",
  "category": "delay",
  "description": "Original description of the effect's purpose.",
  "status": "unconfirmed",
  "evidence": [],
  "controls": [
    {
      "id": "control_key",
      "label": "Control display name",
      "description": "What this control changes.",
      "kind": "continuous",
      "unit": null,
      "range": null,
      "step": null,
      "default": null,
      "enum": null,
      "status": "unconfirmed",
      "evidence": []
    }
  ],
  "implementations": [
    {
      "profile": "orion_studio_sc.json",
      "type_id": null,
      "status": "unconfirmed",
      "commands": {"load": null, "recall": null, "parameters": null},
      "control_encodings": {},
      "evidence": []
    }
  ]
}
```

Catalog IDs are stable names chosen by the project. `type_id` is the device's
effect-type identifier once established; it is distinct from the runtime
instance handle, channel index, and insert-slot index. Never infer a type
ID from a handle observed in a previous session. Names and descriptive
controls may be shared; wire IDs and encodings belong to the implementation
for a particular profile. Do not assume another device uses the same map.

A control's `kind` is `continuous`, `integer`, `boolean`, or `enum`, or
`null` while its semantics remain unknown.
`range` is a display-value `[min, max]`, `step` and `default` use those same
units, and `enum` maps stable option keys to display labels. Use `null` for
unknown values. `control_encodings` is keyed by control ID and records the
byte offset/width, signedness, endian order, scale, bit masks or
wire enum, together with status and evidence. A `capture-observed` mapping
must carry `writable: false`; it records an observed field, not a verified
write contract. Each populated command
definition must describe its frame or ordered frame sequence, runtime
inputs, verification/restoration evidence, and whether it is writable.

`load` denotes assigning an effect to a channel/slot. `recall` denotes
restoring settings on an existing instance; if recall also loads an effect,
document that explicitly. Both remain `null` until the operation is decoded.
Catalog definitions do not enable writes. Generic assignment and parameter
opcode guards remain in force. The separate `runtime_contracts.afx_rack_test`
declares the five captured Orion load types and measured instance indices on
operator-selected mono channel indices 0–31. `verified_channel_indices`
records which channels have completed device trials. `link_pair_records`
maps the 16 pair flags to `0x0b:4` records 0–15 only after direct transition
confirmation; trailing records 16–31 remain unmapped.
`afx_rack_test.linked_chain_edits` records the captured adjacent-pair behavior:
left/right writes with distinct instances, two remaining resources for load,
fresh preflight and both post-write readbacks. Linked slot edits are allowed;
conflicting slots preserve both chains for independent editing. This does not
change the bare link-toggle contract. Memory Cat sharing uses its separate
`afx_memorycat_test.linked_parameters` candidate: same-slot type73 partners,
captured instance frames, fresh flags/chains, right/left writes and captured
post-write reads. Missing/different partners are preserved.

`runtime_contracts.afx_memorycat_test` additionally governs
type 73 parameters on a selected channel: complete blocks from the first
operator edit, then throttled live edits. Its `parameter_readback_contract`
references `frame.afx_slot.instance_state_readback`: request magic/opcode/kind,
tagged effect selector, instance field, reply header, enabled flag and per-effect
parameter offsets/ranges are data. Captured Memory Cat instances0–2 initialize
from fresh device state and verify writes; unknown reads remain guarded.
The shared AFX catalog's Orion implementation links to this layout and records
read offsets and restart evidence without claiming another model's support.
Opening the rack never sends parameters or forces defaults. Failed live sends
require explicit retry; an instance-query timeout blocks more such reads until
reconnect because the reply omits instance identity. Slot writes
start from fresh selected-channel whole-chain reads and verify their results.
A missing or mismatching result disables further AFX writes for that server
session without a blind corrective write; read-only refresh remains available.
Allocation requires all 64 safely bounded `0x19` storage records and a fresh
`0x15:0` resource count, retaining globally distinct captured instances. Link
and slot caches are invalidated on reconnect. The API labels confirmed parameter
readbacks separately from last-sent fallback blocks. Link flags are device
readbacks. No other device
or other-effect stereo parameter writer is enabled. The catalog contains neither
installed-effect state nor account entitlements; licensing/activation traffic is outside its purpose. Gazelle
Reverb retains its separate existing command/readback contract.

Model-local `frame.afx_slot.instance_state_readback.effects` entries may carry
`initialization_observation` with an owner-confirmed trigger, captured query/
reply frame pairs, reply header and opaque payload start. Identical observed
payloads support reusing the envelope; `field_map_verified: false` and
`runtime_query_enabled: false` retain the field-decoding/runtime limits. This
metadata does not add safe query indices or establish initialization-only reads.

The seed entries use `status: reference-only`. The Discrete 4 implementation
records a `readback-observed` type ID, with `type_id_write_status:
unconfirmed`. Owner-labelled loading captures now establish five Orion
type IDs independently of the Discrete 4 observations. Memory Cat Brigade's Orion
implementation contains eight `capture-observed` control encodings, with
local capture and owner-action provenance. Its `parameter_observation`
records the observed header, type/instance addressing and packet span; it is not a
builder template. Offsets exclude the USB capture header. The six knob
fields carry endpoint ranges, with unknown intermediate `scale`/`step`;
the two switches carry owner-confirmed display `options` and raw-to-option
`wire_enum` mappings:0=550ms/Chorus,1=1100ms/Tremolo. The canonical Orion
instance-state fields supply the corresponding raw-keyed options to the live
WebUI. `chrs_vibr` remains the compatibility field ID.
V12 and BBD now have Orion `capture-observed` control encodings and
`parameter_observation.preserved_fields`, with `state_readback: null` and no
runtime parameter commands. Shared `panel.rows`, `panel.switches` and
`panel.dependencies` select display controls without turning opaque fields into
knobs. `panel.display_only_controls` supplies BBD stereo-mode names for local
preview without a wire mapping. Model-local captured membership must be complete
before a preview is exposed; other models inherit no Orion parameter evidence.
Details and source frames: [modulation findings](orion-afx-modulation.md).

An implementation may additionally define `presentation` with
`status: local-preview`, a friendly name/category, rows/switches and explicit
local control ranges, steps, defaults or rotary options. Each parameter control
names the same captured `source_control`; processing controls require a captured
`bypass_observation`. Presentation validation rejects missing model-local sources,
ambiguous membership, invalid ranges and dependency conditions. This metadata is
separate from `control_encodings` and never enables runtime loading or writes.
Local intermediate dial motion and defaults are UI choices, not newly verified
physical conversion laws or device state. The browser receives presentation
fields without wire offsets, commands or instance handles. Model-local friendly
names preserve compatibility effect IDs such as `pultec_eqp` / `pultec_meq`.
Rotary enums retain captured labels and detents; De-Esser Q depends on the two
BandPass choices without assuming a universal captured Q reset value.
`parameter_observation.startup_readback_observation` may record a captured
comparison between a restored parameter write and an initialization reply.
It identifies the compared byte range, instance and query/reply frames.
An optional `startup_reply_offset` on a GUI observation associates that field
with the matching baseline. This does not verify changed-state readback,
authorize runtime queries, or establish unlabelled knob units. Offline tools
preserve the opaque payload and reject ambiguous instance correlation.

Orion observations may also live in
`parameter_observation.labelled_gui_observations` when a named
UI control has not been associated with a compatible declaration ID, or its
encoding remains an endpoint candidate pending runtime verification. Each such
entry records absolute report offset/width, observed values, visual states,
frame provenance and verification limits. Visual restoration is distinct from
device readback; `writable: false` observations do not enable runtime controls.
Integer endpoint candidates may use `encoding: uint8` or `uint16-le`,
`observed_wire_range`, `observed_display_endpoints` and per-phase `endpoints`
with frame/raw values. These remain observed candidates with `writable: false`;
endpoint labels alone do not establish a conversion law. De-Esser additionally
records `mode_dependencies` for coupled filter/Q changes and
`gui_control_methods` for measured selector classes. A checkbox's binary-looking
TogglePattern is not proof of two device states; a measured multi-state method
must override automatic binary discovery. See [De-Esser findings](orion-afx-deesser.md).
Float observations may additionally record `encoding: float32-le`,
`observed_wire_range`, `observed_display_range` and `display_unit`. These are
captured endpoints, not interpolation laws or defaults. Infinite displayed
endpoints use the string `-Infinity` or `Infinity`, never nonstandard numeric
JSON tokens. `minimum_has_action_write: false` distinguishes an unchanged
minimum from a fresh write; its prior full-block source is recorded explicitly.
`parameter_observation.range_capture_summary` reports inventory completion and
remaining controls without enabling runtime parameter commands.
The shared control declarations retain their identifiers, so Orion observations
do not become another model's contract. All three command definitions
remain `null` for every Orion and `discrete_4_sc.json` implementation; the
`zen_go_sc.json` and `discrete_4_a270.json` implementations populate
`commands.parameters` (see [the parameter block](#afx-parameter-blocks-in-the-catalog)). A declared control name carries neither an inferred range
nor an inferred byte width/offset. `source_name` preserves Gazelle's effect
key; `name` uses a public product name only when one has been matched.
Descriptions otherwise remain `null`. Categories now group the menu by
purpose: Dynamics, EQ & Filters, Modulation, Delay & Reverb, Pitch & Tuning,
Amps & Cabinets, Preamps, Saturation & Distortion, and Other. Most were
classified from the existing effect/control names; uncertain purposes remain
Other. This presentation metadata carries no write permission, device-ID
mapping or license evidence. A `#plugins...` or
`#params...` suffix in an evidence URL is a JSON key path within the linked
source document, not an HTML anchor.

### `afx_inserts` (generic insert codec)

`protocol.py` has generic AFX builders that read their whole contract from
this optional block. The codec is used by offline fixtures. The Orion
operator path uses its own captured contracts in `antelope/afx.py`. Missing
or disabled sub-blocks make the builders refuse.

| key | read by | meaning |
|---|---|---|
| `chain_write` `{opcode, param_id, subcmd, strip_offset, slots_offset, ...}` | `build_afx_insert_chain` | whole-rack write: the ordered `{type, instance}` pairs replace the strip's chain; an empty list clears it. The opcode passes `check_opcode` |
| `writes` `{enabled, strips, max_slots, instances}` | `afx_insert_writes`, `build_afx_insert_chain`, `afx_load_defaults` | captured strips, rack length and map of type IDs to measured instances. Each `(type, instance)` can occur once in a rack |
| `writes.effects.<type>.load_defaults` `[hex, ...]` | `afx_load_defaults` | blocks the vendor panel sent right after the chain write that loaded the effect; one per band for a banded effect |
| `parameters.write` `{param_id, length_bias, instances}` | `build_afx_parameter_writes` | captured layout `<param_id> <len> <type> <instance> <block>`, with a map of type IDs to measured instances. Byte 4 is computed from the payload length. The complete frame must fit the report and every mapped value must fit its field |
| `parameters.effects.<type>` `{block_length, fields, bands, editable}` | `afx_parameter_effect` and the builders | one effect's block, inline; a profile instead names its catalogue entries with `parameters.catalog` / `catalog_profile` ([below](#afx-parameter-blocks-in-the-catalog)), never both. `editable: false` refuses parameter edits and state queries. `bands` `{count, length, selector_offset, selector_values}` splits the block into one frame per band with the selector byte put back; given the previous block, only changed bands are sent |
| `parameters.state_query.targets` `{type: [category, subcmd, index]}` | `build_afx_state_query`, `is_afx_state_response` | explicit capture-confirmed tuples. Building requires a confirmed layout and a type present in the caller's freshly read rack. Classic byte indices also pass `check_readback_index`. Tagged indices use the separate exact tuple |
| `parameters.bypass` `{param_id, opcode, instances}` | `build_afx_bypass` | `<param_id> <instance> <type> <01 active / 00 bypassed>` for a mapped type with a measured bypass instance and a permitted opcode |

Each entry of `fields` is `{key, label, offset, type, min, max}` with optional
`values`. `afx_block_get()` / `afx_block_set()` decode and change one field,
little-endian: `u8`/`i8`, `u16`/`i16`, `u32`/`i32` and `f32` (float32), with
raw `min`/`max`. An `f32` field takes an integer or a float and is compared as
stored, after rounding to float32, so a limit such as 0.01 stays in range; NaN
and infinity are refused. Integer fields refuse a float or a bool. A `values`
list replaces the range check for a selector with gaps (FET ratio 0, 1, 2, 4, 8).
Bytes outside the mapped fields are written back unchanged.

Evidence: these frames were captured from the vendor panel on a Zen Go Synergy
Core and a Discrete 4 by a fork contributor. Chain load/remove, bypass and
per-effect parameter writes were then sent from Linux on those units and
checked by read-back, with the racks restored; ClearQ's read layout is still
capture-only, not round-tripped. The parameter
frame also reproduces the Orion Memory Cat capture byte for byte
(`tools/test_afx_codec.py`). Nothing about other Orion effects, bands or
bypass through this path is established; an Orion `afx_inserts` block needs
its own captures and an explicit scope decision.

### AFX parameter blocks in the catalog

The Zen Go (`zen_go_sc.json`) and Discrete 4 `0xa270` (`discrete_4_a270.json`)
implementations in `profiles/afx/<effect_id>.json` carry the parameter block of
each mapped effect in `commands.parameters`; the device-wide frame, state
query and bypass stay in the device profile's `afx_inserts`. The device profile
names its catalogue entries with `afx_inserts.parameters.catalog` (a file name
in the profiles directory, normally `afx_effects.json`) and `catalog_profile`
(its own file name, the implementations' `profile`). No `discrete_4_a270.json`
device profile ships: those implementations are data that the Zen Go's share
and that a future device profile can name.

```json
{
  "profile": "zen_go_sc.json",
  "type_id": 9,
  "status": "readback-verified",
  "commands": {"load": null, "recall": null, "parameters": {
    "frame": "afx_inserts.parameters.write",
    "writable": true,
    "block_length": 5, "read_stride": 6, "read_offset": 1,
    "status": "confirmed",
    "fields_from": "discrete_4_a270.json",
    "notes": "...", "evidence": "..."
  }},
  "control_encodings": {},
  "evidence": [],
  "notes": "..."
}
```

`frame` names the device-wide write layout and `writable` is false only with
`editable: false` (read layout unconfirmed). The remaining keys are the
contract `protocol.afx_parameter_effect(profile, type_id)` returns:
`block_length`, `read_stride`, `read_offset`, `fields`, optional `bands`,
`state_query`, `defaults`, `editable`, `read_layout`, and the device trial's
`status`, `notes` and `evidence`. `fields_from` names another implementation of
the same effect whose `fields` this one shares (same block, same byte meanings);
the Zen Go uses it for the 47 effects it shares with the Discrete 4.
Model-local labels are excluded from inherited fields. A field's
optional `options` maps raw values to model-confirmed printed labels. Orion
labels at the same block offset are retained as `orion_option_candidates`
in the source catalog for comparison. The codec omits these candidates from
resolved fields. The shipped profiles leave the generic codec disabled.
`load_catalog` refuses a malformed contract, a dangling `fields_from` and one
device type ID with parameters in two effects. Resolution is cached per process.

---

## `frame`

The heart of the profile. Each sub-key is one **frame shape**. Outgoing
frames all start `magic 0x70` @0 (cosmetic in this family) with the
opcode at @4 and a param id at @16; what follows @16 is what differs.

### Command frames (host → device)

Every command block has: `magic_offset`+`magic`, `opcode_offset`+`opcode`
(+ optional `opcode_name`), `param_id_offset` (+ `param_id` when the
frame carries a fixed one). Then frame-specific offsets:

| block | opcode | extra keys | built by |
|---|---|---|---|
| `command` | SET_PARAM (`0x13`) | `channel_offset`, `value_offset` | `build_command(profile, param_name, channel, value)` |
| `global_command` | SET_GLOBAL (`0x12`) | `value_offset` (no channel) | `build_global_command(profile, param, value)` |
| `link_command` | SET_LINK (`0x14`) | `space_offset`, `pair_index_offset`, `enabled_offset`, `space_values` (`0`=Preamp, `1`=ADAT, `2`=S/PDIF, `3`=mixer, `4`=AFX stereo-link); optional `readback` distinguishes diagnostic post-write queries from authoritative link-button mappings | `build_link_command(profile, pair, enabled, space)` |
| `mix_command` | SET_MIX (`0x17` Orion / `0x16` Zen Go) | `subcmd_offset`+`subcmd`, `mix_offset`, `channel_offset`, `fader_offset`, `pan_flags_offset`, optional `send_offset`, `pan_center`, `pan_mask`, `mute_bit`, `solo_bit` | `build_mix_command(...)` |
| `auraverb_command` | profile-defined Gazelle Reverb setter (AuraVerb protocol) | `subcmd`, `mix_offset`, `enabled_offset`, `param_offsets{}`, `param_range`, `defaults{}`, `mix_wet_offset`+`mix_wet_constant`, confirmed `contract{readback_category, readback_index, fields[]}` | `build_auraverb_command(profile, params, enabled)`; the WebUI/CLI use the contract's bounded readback target and `parse_auraverb_record` |
| `micmodeling_command` | SET_MIC_MODELING (`0x17`/`0xe5`) | `channel_offset`+`channel_bias`, `enabled_offset`, `model_offset`, `swap_offset`, `pattern_offset`, `pattern_range` | `build_micmodeling_command(...)` |
| `surround_global_command` | SET_SURROUND (`0xab`/`0xeb`) | complete-state template, readback cat/index, bounded delay/level, EQ-position, and Bass Management contracts, and `contract.formats[]` entries with packed `channel_order`; `format_writable` gates normal format writes while `runtime_operations` defines fixed header bytes | `build_surround_global_command(...)` for the verified scalar path, `build_surround_global_format_command(...)` for format changes, `build_surround_global_eq_position_command(...)` for PRE/POST, and `build_surround_global_bass_command(...)` for a declared Bass Management field; all use fresh read-modify-write |
| `runtime_contracts.surround_speaker_eq` (no `frame.*` block) | SET_SURROUND_SPEAKER (`0x87`/`0xea`, per-speaker ×16) | documented byte-for-byte in `params.surround_speaker.field_map`; optional `candidate_head_size`, `head_fields`, and `reset_preset` | `parse_surround_speaker_eq_record(...)` decodes profile-declared head fields; `build_surround_speaker_head_command(...)` performs one guarded delay/level/phase probe, while `build_surround_speaker_eq_command(...)` and `build_surround_speaker_eq_reset_command(...)` preserve the complete head and remaining record state |
| `surround_global_command.contract.speaker_mask_write` | SET_SURROUND (`0xab`/`0xeb`, global per-speaker mask) | category-`0x1b` body offset/width, bit shift, logical bypass polarity, and allowed formats | `build_surround_global_speaker_mask_command(...)` changes one speaker's bypass bit from a fresh complete global readback and preserves every other mask/state bit |

For a per-speaker candidate head, `head_fields` maps each named field to its
byte `offset`/`width`, optional bit `mask`/`shift`, raw bounds, and display
scaling (`step`, `zero`, and `display_offset`). A field is writable only when
its `writable` flag is true and its name is listed in the write contract's
`head_fields`; `head_formats` limits the runtime formats in which the bounded
control is exposed. The builder changes one field and preserves
masked bits in the source record, so the phase/invert probe cannot disturb the
level or delay bits. The separate `speaker_mask_write` contract describes the
speaker-monitor Bypass button, whose logical `true` value clears the device's
active-processing bit.
| `afx_slot` | `0x23`/`0xd7` whole-chain assignment + `0x14`/`0x98` bypass | `assign{}` (channel and eight type/instance pairs), `bypass{}` (state/type/instance), `readback` (cat `0x19` slots; cats `0x0c`/`0x15` counts), `instance_state_readback{}` (tagged query, response and per-effect fields) | Generic AFX writes blocked. Separate runtime contracts permit bounded Orion operator tests. Memory Cat parameter and processing-state reads are confirmed for instances0–2; bypass writes remain disabled. See `PROTOCOL.md` §12a. |
| `routing_command` | SET_ROUTE (`0x53`) | `subcmd`, `destination_offset`, `channel_list_offset`, `channel_stride`, + `addressable_destinations{}`, optional `destination_labels{}`, `stereo_destinations[]`, `destination_channels{}`, `mute_source[]`, `source_banks{}`, `source_semantics{}` | `build_route_command(profile, dest, channels)` |
| `readback` | in-band query (`0x74` request / `0x75` response) | `request_magic`, `response_magic`, `subcmd`, `response_discriminator_offset`+`response_discriminator`, `magic_offset`, `subcmd_offset`, `category_offset`, `index_offset`, `data_offset`, **`category_counts{}`** (read by the code), optional capture-confirmed `layouts[]`, optional nested `record_layouts[]`, + `categories{}` / `hazard` / `liveness` (doc) | `build_readback_query(profile, cat, idx, force=False)`; bounded by `check_readback_index` or an explicitly confirmed feature layout; parsed by `is_readback_response` / `readback_body` / `parse_routing_record` (cat `0x03`) / `parse_mixer_record` (cat `0x04`) / `parse_preamp_gain_record` (cat `0x05`) / `parse_channel_status_record` (cat `0x06`) / `parse_auraverb_record` (cat `0x0a`) / `parse_identity_record` (cat `0x01`) / `parse_firmware_record` (cat `0x00`) / `parse_readback_records` and its profile-specific wrappers; driven by `transport.HidTransport.query` |

> **`frame.readback.category_counts` is safety-critical, not documentation.**
> `{"<cat hex>": <record count>}` — how many records each readback category
> actually has, taken from the device's own `0x74` connect enumeration.
> `protocol.check_readback_index` refuses any index at or above the count,
> because the firmware does **not** bounds-check it and an over-range index
> can crash the MCU outright (Cortex-M BusFault → physical power cycle;
> observed twice on the Orion Studio III, 2026-08-31 — `PROTOCOL.md` §4a).
> A category absent from this map **cannot be bounded**, so the CLI warns and
> a sweeping tool must not walk it. When you add a new device profile, fill
> this in from that device's own connect enumeration before querying
> anything, and leave it empty rather than guessing.

### Nested readback records

Some outer `(category, index)` replies contain an array of smaller records.
Declare those in the optional `frame.readback.record_layouts` list:

```json
{
  "kind": "link_table",
  "category": "0x0b",
  "index": 0,
  "name": "preamp",
  "record_count": 6,
  "record_stride": 1,
  "fields": [{"name": "linked", "offset": 0, "type": "u8"}],
  "status": "capture-confirmed",
  "evidence": "capture or extracted report schema + response log"
}
```

Use `index` for one outer query, or `index_range: [lo, hi]` when the same
inner layout applies to several outer records. `record_count` is the number
of nested records in one response; it is **not** the outer query bound. The
outer bound comes from `category_counts` or an explicitly
`capture-confirmed` `index`/`index_range` in a record layout. A schema-only
layout does not authorize its outer query, because a body shape does not prove
that the device safely exposes that index.

Supported field types are `bool`, `u8`/`i8`, `u16`/`i16`, `u32`/`i32`, and
fixed-width `bytes`/`raw` (with `width`). `protocol.parse_readback_records()`
does the generic decoding; the named wrappers currently used by the Orion
profile are `parse_link_table`, `parse_afx_instance_table`,
`parse_mic_emulations`, `parse_afx_strip_order`,
`parse_surround_speaker_eq_record`, and `parse_surround_global_record`. These parsers only decode
a response already received; they do not probe, expand, or authorize query
indices. `readback_record_layout_indices()` returns only safe layout indices
by default, and `build_readback_query()` applies the same guard. A layout
derived from an application schema still needs a device capture before its
outer index can be used.

`frame.link_command.readback` separately maps an input link command to safe
`link_table` layouts. `post_write_pair_counts` schedules a diagnostic read
after a matching input-link write without assigning the returned bytes to
that input domain. The WebUI uses `pair_counts` to drive link buttons only when
`status` is `confirmed` or `capture-confirmed`, `authoritative` is not false,
the returned table is complete, and
`pair_counts.preamp` / `.adat` stay within both the layout and the declared
channel counts. Only mapped pairs replace browser-cached link icons; an
absent, incomplete, or provisional mapping leaves the cache alone. On Orion,
`0x0b:0` maps six Preamp pairs, `0x0b:1` maps all eight ADAT pairs, and
`0x0b:2` maps the S/PDIF L/R pair. Direct device transitions and Windows VM
checks confirmed these domains on 2026-09-30; the user also verified corrected
WebUI writes/readbacks and link retention across controller restarts.
The primary `pair_counts` contains only Preamp; `additional_tables` uses transition-confirmed
`pair_mappings` for ADAT and S/PDIF. `cache_revision` requests a one-time
browser cache reset after an address correction, followed by device readback.

`channels.link_pairs.space`, `adat.link_pairs.space`, and
`spdif.link_pairs.space` select input write addresses. `input_link_space()`
resolves these fields for CLI and WebUI writers; profiles without the fields
retain their previous selectors. Do not infer one device's selectors for
another device. The corrected Orion values are 0, 1 and 2 respectively.

`opcode` is checked against `constraints.allowed_opcodes` by every build
function (unless `force`). If your device shares an opcode for two
purposes (Zen Go's `0x17` is mixer *and* mic-modeling), the `param_id`
at @16 is the real discriminator — give each its own `frame.*` block.

Mixer link state is keyed by `(mix, pair)`, not by the pair number alone.
Profiles whose `SET_LINK` mixer selectors reserve a range per surface may
declare `mixer.link_pair_index.mix_stride`; `protocol.mixer_link_pair_index`
then translates the logical pair into the wire selector. For example, Zen Go
uses a stride of 16, so logical pair 0 is wire pair 0 on Mix 1 and 16 on Mix 2.

The shared WebUI can use two optional mixer metadata blocks when their status
is `confirmed` or `capture-confirmed`:

```json
"mixer": {
  "surface_selection": {
    "status": "capture-confirmed",
    "param": "param_0x49",
    "target": 0,
    "value_by_mix": {"0": "0x0f", "1": "0x0c"},
    "state_byte_offset": 122
  },
  "link_readback": {
    "status": "capture-confirmed",
    "category": "0x0b", "index": 3,
    "record_count": 24,
    "selector_ranges": {"0": [0, 7], "1": [16, 23]}
  }
}
```

`surface_selection` lets the WebUI select the profile's logical mixer
surface before displaying selector-gated meters. `link_readback` identifies a
complete nested bitmap that may replace cached `(mix, pair)` link state; the
WebUI waits for every declared record before doing so. These blocks describe
device-specific evidence, not a family-wide assumption.

### Labels and launcher features

`profile_schema` identifies the cross-client metadata contract. The current
value is `{"id": "antelope-device-profile", "version": 1}`. `labels` holds
stable section, address-space, and parameter labels. `features` describes
optional launcher surfaces, including their `kind`, `label`, `controls`,
dimensions, and `enabled`/readiness state.

Labels never determine a byte id, enum value, range, offset, or frame shape.
Entity labels stay beside their protocol definitions (`buses.known`, routing
`source_semantics`, and routing destinations); shared parameter labels belong
in `labels.params`. See [`docs/profile-labeling.md`](profile-labeling.md) for
the complete contract and new-device checklist.

### Incoming report maps (device → host)

- **`state_report`** (`magic 0x73` in this family) — the poll readback.
  Keys the code reads:
  - `gain_base_offset` — `parse_state` reads `data[gain_base_offset + channel]`
  - `status_base_offset` — one status byte per channel
  - `status_bits{}` — `{ name: { "mask": "0x10", "shift": 4 } }`, applied
    to the status byte (`input_mode`, `phantom`, `phase_invert`)
  - `adat_gain_base_offset`, `spdif_gain_base_offset` — parallel arrays
  - `<name>_byte_offset` — a plain scalar at that offset, read by
    `parse_state_scalar(profile, data, "<name>_byte_offset")`
    (e.g. `sample_rate_byte_offset`, `screen_brightness_byte_offset`,
    `clock_source_byte_offset`)
  - `clock_rate_hz_offset` — `{ offset, width, endian, family_offset }`,
    the running sample rate in Hz as a `width`-byte big-endian int
    (Orion: `[21..23]`), read by `state_clock_rate_hz(profile, data)`.
    Complements the 0-6 `sample_rate_byte_offset` enum
  - `bus_block_offset` + `bus_block_stride` — bus state array
    (`28 + 3N` on Orion, `28 + 2N` on Zen Go); `bus_block.flags_combine`
    is described under [`constraints`](#constraints)
  - `snapshot_payload_offset` — optional base added to payload-relative
    offsets when the report includes a fixed header (Zen Go: `0x10`)
  - `mixer_strip_meters` — optional profile-confirmed shared mixer meter map
    with `full_report_base_offset` (or `payload_base_offset`), `count`,
    `stride`, `raw_range`, and `silence_raw`; the WebUI combines it with
    `mixer.surface_selection` and never treats the lanes as physical ownership
  - `candidate_preamp_meters` — optional provisional per-input mappings when
    a device has observed preamp-related lanes but no confirmed contiguous
    physical-input bank. Each entry supplies an `input_index`, `offset` (or
    `payload_offset`), `raw_range`, `silence_raw`, and `direction`; consumers
    must preserve its provisional/mixed-signal caveat.
  - `meter_mappings` — optional additional profile mappings. The WebUI
    currently recognizes `target: "physical_output"` as stereo output lanes
    and exposes them as provisional raw meters; `target_index` and `lane`
    identify the logical bus and channel, while `payload_offset` is relative
    to `snapshot_payload_offset` unless the profile says otherwise.

For runtime-exposed Orion settings, `params.<name>.runtime_readback` is the
canonical machine-readable declaration. It names the full-report coordinate
system with `frame: "state_report"`, a semantic, and typed fields. Brightness
uses one scalar field (`offset: 26`, `width: 1`); output trim uses exactly three
`bit_field` records with explicit targets, offsets, masks, and shifts. The
neighboring `readback` string remains informative provenance and is never
parsed to grant capability.
- **`meter_report`** (`0x75` Orion / `0x83` Zen Go) — per-channel meters.
  `channel_meter_base_offset`, plus optional `db_curve` / `led_scale`
  for the `meter` command's dB calibration.
- **`init_enumeration_report`** (`0x74`) — the connect-time walk of the
  readback protocol (`frame.readback`). Documentation only; the live
  reader is `frame.readback`.
- **`name_report`** (`0x75` on Zen Go) — ASCII device name/serial/fw.
- **`error_response`** (`0x61` in the family) — "unknown opcode" reply.

---

## `channels`

The physical input address space.

```json
"channels": {
  "count": 2,                        // or "count_confirmed" / "count_assumed_total"
  "addressing": "0-indexed, written to frame.command.channel_offset",
  "modes": { "0": "mic", "1": "line", "2": "hiz" },
  "link_pairs": { "count": 1, "formula": "pair_index = channel_index // 2" }
}
```

`cli.py` reads these keys **flat under `channels`** (not nested): `count`
(some profiles use `count_confirmed`), `link_pairs` (`.count`,
`.formula`), `hiz_channels`. `link_pairs.formula` is documentation — the
arithmetic (`ch // 2`) lives in `protocol.pair_index_for_channel`; if a
device pairs channels differently, that helper needs the profile.

## `adat` / `spdif`

Same idea, separate index spaces: `count`, `addressing`, `readback`,
`link_pairs`. Only present when the device has those I/O.

---

## `buses`

```json
"buses": {
  "addressing": "bus id in frame.command.channel_offset (@17)",
  "known": {
    "0": { "name": "monitor_a", "label": "Monitor A", "aliases": ["mona", "monitor a"] },
    "1": { "name": "headphone_1", "label": "Headphone 1", "aliases": ["hp1"] }
  },
  "readback": "state_report.bus_block_offset + stride*id"
}
```

`name` is the stable machine key and `label` is display text. If `label` is
omitted, clients fall back to `name`. An optional `level_encoding` documents
the device-specific meaning of the raw level byte; on Orion it is attenuation
(`0` = 0 dB/maximum, `96` = -inf/silent). `resolve_bus_id()` matches a user
string against `name`, `label`, and `aliases`; `bus-status` / `set-bus-*` use
this.

---

## `params`

The catalogue. One entry per settable parameter, keyed by a stable name
the CLI and docs use. Minimum:

```json
"gain": {
  "id": "0x50",
  "status": "confirmed",
  "type": "int8",
  "per_mode_range": { "mic": [0, 75], "line": [-6, 20], "hiz": [0, 65] },
  "evidence": "capture2, gain sweeps per mode"
}
```

- **`id`** — the param byte written at `param_id_offset`. `null` /
  missing = not decoded yet; `build_*` refuses it.
- **`type`** — `int` / `int8` / `bool` / `enum` (documentation; the CLI
  command decides encoding).
- **`values`** — `{ "0": "mic", "1": "line", ... }` for enums.
- **`range`** / **`per_mode_range`** / **`range_by_mode`** — clamp
  bounds. The exact key name varies by param; the CLI command for that
  param reads whichever it expects.
- **`frame`** — which `frame.*` block builds it (free text, e.g.
  `"command (opcode 0x13) -- channel @17, value @18"`).
- **`readback`** — where it reads back in `state_report`, or "none".
- **`constraint`** — a human note like `"mic mode only"`.

Params with no `id` and `status: "observed"` are observational-only: they
document a control seen in a capture without authorizing a writer.

---

## `constraints`

Machine-enforced bounds. `protocol.check_opcode` / `check_target` /
`check_enum` / `channel_space_bounds` read these; `--force` overrides.

| key | enforced by | meaning |
|---|---|---|
| `allowed_opcodes` | `check_opcode` (in every `build_*`) | only these opcodes may be sent |
| `forbidden_opcodes` | `check_opcode` | explicit deny (belt + braces) |
| `channel_bounds` `{min,max}` | `check_target(space="input")` | valid input channel indices |
| `adat_channel_bounds`, `spdif_channel_bounds` | `check_target` | valid ADAT / S/PDIF indices |
| `bus_ids` `[...]` | `check_target(space="bus")` | valid bus ids |
| `input_mode_allowed_values` `[...]` | `check_enum` | portable-enum guard (a foreign value crashed a sibling) |
| `gain_bounds` / `adat_gain_bounds` / `spdif_gain_bounds` | the gain CLI commands | dB clamp ranges |
| `min_write_interval_ms` | (advisory) | rate-limit hint |
| `protected_mute_buses` `[...]` | `protocol.bus_flag_may_release_mute`, WebUI `bus-toggle`, CLI `set-bus-dim` / `set-bus-mono`, and `tools/selftest.py` | optional, default empty. Dim and mono require a complete, current state report showing that a protected bus is unmuted, unless `frame.state_report.bus_block.flags_combine` is true. The self-test skips protected buses. |

`frame.state_report.bus_block.flags_combine` (optional, default false) is true
only when dim and mono writes are both known to preserve mute. The WebUI reads
the bus on its device worker immediately before sending a guarded write.
Ambiguous mute bits, unrecognized status enum values and missing or incomplete
reports cause the write to be refused. When an explicit mute is queued before
the guarded write, the worker waits for muted readback before it can trust a
later unmuted report. Explicit mute and unmute commands remain available.
The shipped Orion profile leaves `protected_mute_buses` unset.

Every bound here should have a matching `hazards` entry saying what goes
wrong without it.

## `hazards`

Free-form `{ hazard_name: { rule, effect_on_<device>, notes, enforced_by } }`.
This is the institutional memory: the Discrete 8 Pro needed a physical
power cycle after blind opcode sweeps, an out-of-range channel index, and
a foreign enum value — those lessons live here and are carried to every
sibling profile as precautionary defaults.

## `family_notes`

What is and isn't shared across the Synergy Core family. At minimum:
`siblings` (list of the other profiles), and a note on which fields are
shared (param ids, transport) vs device-specific (report magics, mixer
frame shape, source-bank numbers). See `PROTOCOL.md` §14.

---

## Adding a device

1. Copy the closest existing profile (usually `orion_studio_sc.json`).
2. Set `device` from the enumeration capture (device descriptor →
   VID/PID/bcd; config descriptor → interfaces/endpoints).
3. Verify **every** `frame` offset against a capture — do **not** assume
   they match the source profile. Report magics, the mixer frame, bus
   strides and source-bank numbers all differ across the family.
4. Fill `constraints` conservatively (narrow `allowed_opcodes`, real
   channel/bus bounds), carry `hazards` verbatim, and keep an
   `open_questions` list.
5. `python3 -c "from antelope import protocol as p; p.load_profile('profiles/<x>.json')"`
   plus a `build_command` / `build_global_command` smoke test.

See `README.md` → *Adding a new param* and *Adding a new Antelope
device* for the capture-and-decode workflow.
