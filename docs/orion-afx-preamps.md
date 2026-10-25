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

## Gyratec IX

The labelled load at frame2485 in
`unattended-20261025T195948Z-load-gyratecix/Orion.pcapng` independently establishes
Orion type43/instance0 in channel1 slot0, with seven empty slots. The native
panel is `GyratecIX`; compatibility identifier `gyratex_ix` is retained.

Fresh job `scan-GyratecIX-20261025T203215463Z` accepted all eight endpoint phases,
with64,210packets and zero drops. Blocks use `0x18 / 0xd5 / 0x06`, type byte18
and instance byte19. The earlier priming job remains failed with zero accepted
phases; it supplied the observed family for the passive decoder.

| Control | Byte | Raw endpoints | Source frames |
|---|---|---|---|
| Gain | 20 | 0, 100 | 4129 / 12617 |
| Output | 21 | 0, 100 | 19815 / 28629 |
| Phase | 22 | 0, 1 | 35669 / 43551 |
| Low-Cut | 23 | 0, 2 | 51653 / 59687 |

Each directed field preserves the other payload bytes. Gain/Output physical
scaling is unverified. Phase is a two-position selector: raw0=`−`, raw1=`+`.
Low-Cut is a three-position selector: raw0=Off, raw1=Low, raw2=High.
Each position has a directed raw observation and pointer image in
`unattended-20261025T195948Z-gyratecix-rotary-map` (Phase subset) and
`unattended-20261025T195948Z-gyratecix-rotary-map2` (Low-Cut). The first mapper
stopped after skipping Low-Cut's middle position; its status is preserved.
Four-pixel steps capture that position after bounded one/two-pixel quiet trials.
The second mapper completes all positions and returns the full parameter payload
to its starting maximum block.

The processing-switch round trip in
`unattended-20261025T195948Z-gyratecix-processing` uses `0x14 / 0x98`, with
instance17/type18/state19. First frame3493 carries `00 2b 00`; return frame779
carries `00 2b 01`. Switch, LED and all four control regions match their baseline
RGB images exactly. These observations complete the visible-control pass;
independent readback, physical scaling, audible/stereo behavior, processing
polarity and runtime contracts remain unverified.
