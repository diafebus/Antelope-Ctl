# Profile labels and feature manifests

Device profiles are also the launcher manifest.  A new client should not have
to recognize a product name and then carry a second table of labels and
feature switches in its own code.

The profile has three related, but separate, jobs:

1. `frame`, `params`, `channels`, `buses`, and the other protocol blocks record
   device facts and safety limits.
2. `labels` supplies human-facing text for stable semantic keys.
3. `features` says which launcher surfaces are intentionally exposed for this
   device and which controls they contain.

The protocol blocks remain authoritative for whether a command is safe.  A
feature being listed as enabled never bypasses `constraints`, an unconfirmed
frame status, or a readback bound.

## Profile contract

Every device profile should have this shape at the top level:

```json
{
  "profile_schema": {
    "id": "antelope-device-profile",
    "version": 1
  },
  "labels": {
    "sections": {
      "inputs": "Inputs",
      "digital_inputs": "Digital Inputs",
      "outputs": "Output Buses",
      "routing": "Routing",
      "mixer": "Virtual Mixer",
      "settings": "Settings",
      "diagnostics": "Protocol Readback"
    },
    "spaces": {
      "input": {
        "label": "Preamps",
        "item_format": "Preamp {index}"
      },
      "adat": {
        "label": "ADAT",
        "item_format": "ADAT {index}"
      },
      "spdif": {
        "label": "S/PDIF",
        "item_format": "S/PDIF {side}"
      },
      "bus": {
        "label": "Output",
        "item_format": "{label}"
      }
    },
    "params": {
      "gain": "Gain",
      "input_mode": "Input Mode",
      "phantom": "48V Phantom",
      "phase_invert": "Phase Invert"
    }
  },
  "features": {
    "inputs": {
      "kind": "channel_strips",
      "label": "Inputs",
      "enabled": true,
      "space": "input",
      "controls": ["gain", "input_mode", "phantom", "phase_invert"]
    }
  }
}
```

`profile_schema.id` is fixed for this format.  Increase `version` only when
the meaning or required shape of the labeling/feature contract changes.
Unknown keys remain allowed so a client can ignore a newer optional field.

### Stable keys versus labels

Keys are API identifiers; labels are display text.  Never parse a label to
discover what a control means.

- `gain`, `input_mode`, `phantom`, `mix_fader`, and `bus_level` are stable
  parameter keys.
- `preamp`, `compplay`, `adat`, `spdif`, and `mute` are stable routing source
  keys in `frame.routing_command.source_semantics`.
- A bus's `name` is its canonical machine name; its `label` is what a launcher
  displays.  The same rule applies to source and feature objects.
- Numeric ids, parameter ids, ranges, enum values, offsets, and frame shapes
  are facts for the selected device.  They must not be inferred from a label
  or copied merely because another device uses the same id.

For example, both Orion and Zen Go may use the parameter key `gain` and the
display label `Gain`, while their ranges, state offsets, mixer frames, and
channel counts remain profile-specific.

## `labels`

The common label namespaces are:

- `sections`: top-level launcher panels.
- `spaces`: address spaces such as physical inputs, ADAT, S/PDIF, and output
  buses. `item_format` supports `{index}`, `{side}`, and `{label}`.
- `params`: stable parameter key to display label. Keep labels for shared
  parameters identical across profiles unless the physical meaning really
  differs.

Entity-specific labels stay beside the entity's protocol definition:

- `buses.known.<id>.name` is the stable name and `.label` is the display name.
- `frame.routing_command.source_semantics.<bank>.key` is the stable source key
  and `.label` is its display group name.
- `frame.routing_command.destination_labels.<id>` gives a display name for a
  routing destination while `addressable_destinations.<id>` remains its stable
  protocol name.

When a label is missing, clients should fall back to the stable key or a
clearly marked numeric label such as `Bus 5`; they should not borrow text from
another profile.

## `features`

Feature ids are stable launcher concepts.  A feature object should contain:

- `kind`: rendering/behavior contract, such as `channel_strips`,
  `output_buses`, `routing_matrix`, `virtual_mixer`, or `bundled_effect`.
- `label`: panel or control-group label.
- `enabled`: whether the launcher should consider the feature for this
  profile. Use `false` when the feature is known or suspected but not safe to
  expose yet; omit an unknown feature altogether.
- `controls`: stable parameter keys or feature-specific action keys.
- feature-specific dimensions, such as `space`, `mix_ids`, `channels`, or
  `destination_ids`.
- `status`, `notes`, and `evidence` when the declaration is provisional or
  capture-dependent.

The feature manifest is declarative.  A client may use it to add or remove
panels without an `if device == ...` branch, but it still must validate that
the referenced `params` and `frame` blocks exist and that their status and
constraints permit the requested operation.

For a feature that is a logical view of several wire records, describe that
in the profile rather than hiding it in a product-name check:

```json
"routing": {
  "kind": "routing_matrix",
  "label": "Routing",
  "enabled": true,
  "destination_ids": [6],
  "destinations": [
    {
      "id": 6,
      "key": "mixer_input_assignments",
      "label": "Mixer Inputs",
      "channels": 16,
      "write_destinations": [6, 7, 8, 9]
    }
  ]
}
```

That is how Zen Go declares one logical 16-strip map backed by four mirrored
destination records.  Orion can instead expose all of its addressable
destinations through the same feature kind.

## Adding a new device

1. Copy the closest profile, then set `device`, `transport`, and every wire
   layout from captures for the new hardware.
2. Add `profile_schema`, `labels.sections`, `labels.spaces`, and `labels.params`.
3. Reuse an existing semantic parameter key only when the behavior is the
   same. Keep the key and common label (`gain` → `Gain`) but put the new id,
   range, encoding, frame, and readback in the new profile.
4. Add `label` to each known bus and routing source. Add a `key` to every
   `source_semantics` entry; never make a future client reverse-engineer the
   key from `name`.
5. Declare each launcher surface under `features`. Set `enabled: false` or
   leave a feature out when its frame/readback is not confirmed. Do not copy a
   sibling's feature declaration just because the product family is similar.
6. Run the profile validation and tests before connecting hardware. A profile
   with a conservative disabled feature is preferable to one that sends an
   unverified frame.

## Keeping the family consistent

When a parameter is genuinely shared, keep all of these consistent:

- the semantic key in `params`;
- the label in `labels.params`;
- the feature control reference;
- the meaning of the value and its units.

Keep these device-specific even when the semantic key is shared:

- wire parameter id and opcode;
- frame offsets and frame shape;
- ranges, enum values, encoding, and side effects;
- state/readback offsets and safe record counts;
- channel/bus/source/destination counts and mappings.

This gives Python, Rust, and future launchers one vocabulary without making
the profiles pretend that sibling devices are wire-compatible.
