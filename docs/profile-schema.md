# Device profile schema (`profiles/*.json`)

A **profile** is the single source of truth for one Antelope device's
control protocol. `antelope/transport.py`, `antelope/protocol.py` and
`antelope/cli.py` contain **no device-specific values** — every VID/PID,
byte offset, opcode, param id, range and enum comes from the profile
dict. Point `--profile` at a different file and the same code drives a
different device.

This doc describes the keys the code reads and the conventions the
profiles follow. The reference implementations are
`profiles/orion_studio_3.json` (most complete),
`profiles/zen_go_sc.json` and `profiles/discrete_8_pro_synergy_core.json`.

---

## Conventions

- **Numbers may be hex strings or ints.** `"0x50"` and `80` are both
  accepted anywhere a byte value is expected — `protocol._as_int()`
  normalises. Offsets are usually plain ints, ids/magics usually hex
  strings. Be consistent within a file.
- **Byte offsets are 0-indexed into the 320-byte HID report**, both
  directions.
- **`status`** on any block: `"confirmed"` / `"observed"` (seen in a
  capture, not decoded) / `"unconfirmed"` / free text. Anything not
  `confirmed` must not be relied on by a normal CLI command.
- **`evidence`** / **`notes`**: free text. `evidence` names the capture
  and what it showed; `notes` is everything else. Keep the capture name
  in `evidence` so a claim can be re-checked.
- **`_comment`** keys are ignored by the code — inline documentation.
- Unknown keys are ignored. Adding a key the code doesn't read yet is
  fine (it documents intent for a future CLI command or the webUI).

---

## Top-level keys

| key | required | purpose |
|---|---|---|
| `device` | yes | identity (VID/PID) — used to find the hidraw node |
| `transport` | yes | HID report size + endpoints |
| `frame` | yes | every wire frame shape + the incoming report maps |
| `channels` | yes | the physical input channel space |
| `params` | yes | catalogue of settable parameters |
| `buses` | if the device has output buses | output-bus address space + names |
| `adat`, `spdif` | if present on the device | extra input address spaces |
| `mixer` | if decoded | virtual-mixer summary (human-facing; the frame is in `frame.mix_command`) |
| `constraints` | strongly recommended | machine-enforced bounds (`protocol.check_*`) |
| `hazards` | recommended | *why* each constraint exists (carried across the family) |
| `family_notes` | recommended | what is / isn't shared with sibling devices |
| `unresolved_state_offsets` / `open_questions` | optional | the backlog, so "MVP done" isn't mistaken for "protocol done" |

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
| `link_command` | SET_LINK (`0x14`) | `space_offset`, `pair_index_offset`, `enabled_offset`, `space_values` | `build_link_command(profile, pair, enabled, space)` |
| `mix_command` | SET_MIX (`0x17` Orion / `0x16` Zen Go) | `subcmd_offset`+`subcmd`, `mix_offset`, `channel_offset`, `fader_offset`, `pan_flags_offset`, optional `send_offset`, `pan_center`, `pan_mask`, `mute_bit`, `solo_bit` | `build_mix_command(...)` |
| `auraverb_command` | SET_AURAVERB (`0x1d`) | `subcmd`, `mix_offset`, `enabled_offset`, `param_offsets{}`, `param_range`, `defaults{}`, `mix_wet_offset`+`mix_wet_constant` | `build_auraverb_command(profile, params, enabled)` |
| `micmodeling_command` | SET_MIC_MODELING (`0x17`/`0xe5`) | `channel_offset`+`channel_bias`, `enabled_offset`, `model_offset`, `swap_offset`, `pattern_offset`, `pattern_range` | `build_micmodeling_command(...)` |
| `routing_command` | SET_ROUTE (`0x53`) | `subcmd`, `destination_offset`, `channel_list_offset`, `channel_stride`, + `addressable_destinations{}`, `stereo_destinations[]`, `destination_channels{}`, `mute_source[]`, `source_banks{}` | `build_route_command(profile, dest, channels)` |
| `readback` | in-band query (`0x74` request / `0x75` response) | `request_magic`, `response_magic`, `subcmd`, `response_discriminator_offset`+`response_discriminator`, `magic_offset`, `subcmd_offset`, `category_offset`, `index_offset`, `data_offset`, + `categories{}` (doc) | `build_readback_query(profile, cat, idx)`; parsed by `is_readback_response` / `readback_body` / `parse_routing_record`; driven by `transport.HidTransport.query` |

`opcode` is checked against `constraints.allowed_opcodes` by every build
function (unless `force`). If your device shares an opcode for two
purposes (Zen Go's `0x17` is mixer *and* mic-modeling), the `param_id`
at @16 is the real discriminator — give each its own `frame.*` block.

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
  - `bus_block_offset` + `bus_block_stride` — bus state array
    (`28 + 3N` on Orion, `28 + 2N` on Zen Go)
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
    "0": { "name": "monitor_a", "aliases": ["mona", "monitor a"] },
    "1": { "name": "headphone_1", "aliases": ["hp1"] }
  },
  "readback": "state_report.bus_block_offset + stride*id"
}
```

`resolve_bus_id()` matches a user string against `name` + `aliases`.
`bus-status` / `set-bus-*` use this.

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

Params with no `id` and `status: "observed"` are the backlog — they
document a control seen in a capture so the next person knows it exists.

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

1. Copy the closest existing profile (usually `orion_studio_3.json`).
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
