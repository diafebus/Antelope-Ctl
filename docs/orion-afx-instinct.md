# Orion Instinct capture findings

These are directed vendor GUI observations on Orion Studio Synergy Core.
The [catalog](../profiles/afx_effects.json) owns individual field mappings and
source frames. DEMO availability does not establish license ownership.

The prior labelled batches establish21 knob endpoint candidates and three
parameter switches (ALT Morph, Filter and Post-Filter). Knobs use float32-le
fields with differing raw ranges; physical interpolation remains unverified.
The compatibility declaration IDs are not inferred from control order.

## Model and processing completion, 2026-10-26

The fresh labelled load in
`unattended-20261026T091415Z-load-instinct/Orion.pcapng` frame4245 establishes
type75/instance1 in AFX2/channel1 slot0, with seven empty slots. The native
panel is `Instinct`. The test preserves other channels and instances.

A previously measured ALT Morph round trip seeds a fresh full parameter block:
first frame4819 changes ALT byte72 to1, return frame656 restores0. The return
preserves all other parameter bytes and matches the checked visual baselines.
No pre-seed full-payload preservation claim or independent readback is made.

The separate `ModelSwitchButton` trial uses `0x7c / 0xd5 / 0x6a`, type75,
instance1. First frame1779 in
`unattended-20261026T091415Z-instinct-model-first/Orion.pcapng` changes only
byte68 from0to1; return frame651 in `-instinct-model-return` changes only68
back to0. Raw0 selects the left icon, raw1 the right. The final full parameter
payload equals the fresh ALT-return baseline, and all checked stable control
regions match exactly. Algorithm naming and correspondence to imported
`driveModel` remain unverified.

The processing widget is the `PFEnable` at the panel origin, distinct from the
Post-Filter widget with the same class. Its `0x14 / 0x98` round trip in
`unattended-20261026T091415Z-instinct-processing` carries tuples at17..19
`01 4b 00` (first frame3045) and `01 4b 01` (return frame649). This independently
establishes instance17/type18/state19. The processing button and20other stable
regions match their baseline RGB images. Animated meter regions are excluded.
Processing polarity has no new audible confirmation.

## Factory preset inventory

The read-only `unattended-20261026T091415Z-instinct-presets` inventory records
60 factory menu entries across nine categories:

| Category | Entries |
|---|---|
| Bus | 3 |
| Creative | 11 |
| Dynamics | 6 |
| FX | 6 |
| Noise | 6 |
| Tape | 4 |
| TheMute | 6 |
| Transistor | 7 |
| Tube | 11 |

Only category menus were expanded. No preset was applied, and inventory/close
captures contain no device writes. Menus close with a bounded owned-popup
Escape sequence; checked control images return exactly. Factory entry labels
are recorded in the model-local catalog. User presets are outside this factory
inventory; no preset index or parameter encoding is inferred.

This completes the observed visible controls. Physical interpolation,
algorithm/declaration naming, independent state readback, preset encodings,
audible behavior and runtime contracts remain unverified.
