# Orion AFX preamp capture findings

Directed vendor GUI captures on Orion Studio Synergy Core establish these
model-local observations. The [catalog](../profiles/afx_effects.json) owns
field mappings and capture hashes. Runtime writes remain unverified.

## BA-31

The labelled vendor load at frame2367 in
`unattended-20261025T195948Z-load-ba31/Orion.pcapng` establishes Orion type48,
instance0, AFX2/channel1 slot0, with seven empty slots. Native panel `Ba31`
exposes Gain, Trim and a separate power switch; no rotary detents or preset
selector were observed.

Job `scan-Ba31-20261025T202655138Z` accepted all four knob endpoint phases,
with34,232packets and zero drops. Parameter blocks use `0x16 / 0xd5 / 0x04`,
type byte18 and instance byte19. Each directed control changes its own byte,
preserving the other payload fields:

| Control | Byte | Raw endpoints | Source frames |
|---|---|---|---|
| Gain | 20 | 10, 100 | 4445 / 12981 |
| Trim | 21 | 10, 100 | 20471 / 30231 |

These are raw endpoint candidates; physical gain units, scaling and intermediate
laws are unverified. Knobs finish at their captured maximum as authorized.

The separate processing-switch round trip in
`unattended-20261025T195948Z-ba31-processing` uses `0x14 / 0x98`, with
instance17/type18/state19. First frame3197 carries `00 30 00`; return frame743
carries `00 30 01`. Both knobs, switch and LED have exact RGB baseline matches.

This completes the observed visible controls. Independent readback, processing
polarity, audible/stereo behavior and runtime contracts remain unverified.
