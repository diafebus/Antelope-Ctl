# Orion AFX EQ capture findings

These findings describe directed vendor GUI captures on Orion Studio Synergy
Core. Model-local encodings, hashes and per-position evidence belong in the
[AFX catalog](../profiles/afx_effects.json). Runtime parameter writers and
independent parameter readback remain unverified.

## VEQ-1A

The labelled vendor load is frame3703 of
`unattended-20261025-load-veq-1a/Orion.pcapng`: AFX2/channel1, slot0
type6/instance0, seven empty slots. The observed panel class is `PultecEQP`.

Native launcher job `scan-PultecEQP-20261025T095310973Z` accepted all sixteen
endpoint phases for five continuous knobs and three rotary selectors, with
209,758 packets and zero drops. Parameter writes use `0x1c / 0xd5 / 0x0a`,
type byte18 and instance byte19. Only each listed field differs between its
minimum/maximum blocks.

| Control | Byte | Raw endpoints | Source frames |
|---|---|---|---|
| Low Boost | 21 | 0, 100 | 7801/20743 |
| Low Attenuation | 22 | 0, 100 | 31751/42839 |
| High Boost | 24 | 0, 100 | 52119/60573 |
| High Attenuation | 25 | 0, 100 | 71207/84037 |
| Bandwidth | 26 | 0, 100 | 99733/118533 |
| Low Frequency | 20 | 0, 3 | 132735/149685 |
| High Frequency | 23 | 0, 6 | 165519/180417 |
| Attenuation Frequency | 27 | 0, 2 | 193741/204717 |

The five continuous dial pointers reach printed 0/10. This does not establish
physical gain units, intermediate laws or a linear raw-to-physical conversion.
Knobs finish at their captured maximum as authorized.

Separate bounded GUI drags map every visible rotary detent, with a pointer
image and an isolated one-byte parameter observation for each position:

| Selector | Raw values in order | Printed labels in order |
|---|---|---|
| Low Frequency | 0, 1, 2, 3 | 20, 30, 60, 100; panel marked CPS |
| High Frequency | 0, 1, 2, 3, 4, 5, 6 | 3, 4, 5, 8, 10, 12, 16; panel marked KCS |
| Attenuation Frequency | 0, 1, 2 | 5, 10, 20 |

The endpoint sweep had skipped Low Frequency raw 1; it was captured in the
directed detent pass rather than inferred. Low Frequency mapping is the completed
subset in `unattended-20261025-veq1a-rotary-map`. That whole mapper stopped for
calibration after High Frequency 8 pixel drags produced no writes; it remains a
stopped job. `unattended-20261025-veq1a-rotary-map2` completes the remaining
High Frequency/Attenuation Frequency maps with GUI steps of 16/32 pixels. Every action
preserves the other parameter bytes, and the final captured parameter payload
matches the pre-mapping maximum block exactly. This is captured-write
restoration, not independent device readback.

The processing switch has its own `0x14 / 0x98` round trip:
`unattended-20261025-veq1a-switch-first/Orion.pcapng` frame2859 carries
instance17/type18/state19=`00 06 00`; return frame2773 carries `00 06 01`.
Switch, LED and all eight control regions have exact RGB baseline matches
after moving the pointer away. Polarity and audible confirmation remain
unverified. No preset selector was observed on this panel.

This completes the observed visible controls. Physical scaling, independent
readback, audible/stereo behavior and runtime contracts remain open.

## VMEQ-5

The directed load at frame3481 in
`unattended-20261025-load-vmeq-5/Orion.pcapng` independently establishes Orion
type5/instance0 in channel1 slot0, with seven empty slots. The native panel is
`PultecMEQ`: three gain knobs, three rotary frequency selectors and a separate
processing switch. Its Dip dial visibly has eleven printed choices.

Native launcher job `scan-PultecMEQ-20261025T101459165Z` accepted all twelve
endpoint phases with 135,320 packets and zero drops. Parameter writes use
`0x1a / 0xd5 / 0x08`, type5/instance0. The earlier priming job stopped with
zero accepted phases because that family was unrecognized; its nine observed
writes remain evidence and its failed status is preserved.

| Control | Byte | Raw endpoints | Source frames |
|---|---|---|---|
| Low Peak Gain | 21 | 0, 100 | 9291/27473 |
| Mid Dip Gain | 23 | 0, 100 | 38711/53893 |
| High Peak Gain | 25 | 0, 100 | 69869/78027 |
| Low Peak Frequency | 20 | 0, 4 | 85829/95337 |
| Mid Dip Frequency | 22 | 0, 10 | 104215/113193 |
| High Peak Frequency | 24 | 0, 4 | 121571/130623 |

The gain dial pointers reach printed 0/10; intermediate physical scaling remains
unverified. All three frequency controls are stepped selectors. The separate
`unattended-20261025-vmeq5-rotary-map` pass captures every printed position:

| Selector | Raw values in order | Printed labels in order |
|---|---|---|
| Low Peak Frequency | 0–4 | 200, 300, 500, 700, 1000 |
| Mid Dip Frequency | 0–10 | 200, 300, 500, 700, 1, 1.5, 2, 3, 4, 5, 7 |
| High Peak Frequency | 0–4 | 1.5, 2, 3, 4, 5 |

Each of the36 bounded16pixel GUI steps changes exactly one selector detent,
with an isolated field observation and matching pointer image. All other
parameter bytes are preserved. The final full parameter payload matches the
pre-mapping maximum block exactly. Printed mixed notation is retained without
guessing units or interpolating between detents.

The separate processing-switch round trip is `0x14 / 0x98` with
instance17/type18/state19. First-click frame5701 in
`unattended-20261025-vmeq5-switch-first/Orion.pcapng` carries `00 05 00`;
return frame3169 carries `00 05 01`. Switch, LED and all six control regions
have exact RGB baseline matches after moving the pointer away.

This completes the observed visible controls; no preset selector was observed.
Physical scaling, independent readback, processing polarity, audible/stereo
behavior and runtime contracts remain unverified. The final test insert was
removed at frame2617 in `unattended-20261025-final-vmeq5-remove/Orion.pcapng`,
leaving all eight AFX2 slots empty for the owner handoff.

## VEQ-HLF

The directed vendor load at frame2281 in
`unattended-20261025T195948Z-load-veq-hlf/Orion.pcapng` establishes Orion
type11/instance0 in channel1 slot0, with seven empty slots. The native panel is
`PultecHLF`. Its two cut-off selectors retain the compatibility identifiers
`low_shelf` and `high_shelf` in the catalog.

Native job `scan-PultecHLF-20261025T200723927Z` accepted all four endpoint phases,
with 30,528 packets and zero drops. Parameter blocks use `0x16 / 0xd5 / 0x04`,
type byte18/instance byte19. Low Cut-off byte20 reaches raw0/10 at frames4185/11737;
High Cut-off byte21 reaches raw0/10 at frames19085/26861. The earlier decoder
rejection remains a failed priming job with zero accepted phases.

The separate `unattended-20261025T195948Z-veqhlf-rotary-map` pass records every
position, each with an isolated raw-field observation and pointer image:

| Selector | Raw values | Printed labels in order |
|---|---|---|
| Low Cut-off | 0–10 | Off, 50, 80, 100, 150, 250, 500, 750, 1000, 1500, 2000 |
| High Cut-off | 0–10 | 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 15, Off |

All40 bounded16pixel GUI steps change one detent and preserve the other payload
bytes. The final full parameter payload matches the starting maximum block.
The processing-switch `0x14 / 0x98` round trip carries tuples at17..19
`00 0b 00` (first frame2443) and `00 0b 01` (return frame1527), respectively
in `unattended-20261025T195948Z-veqhlf-switch-first` and `-switch-return`.
The switch, LED and both selector regions have exact RGB baseline matches.

This completes the observed visible controls. Printed labels are retained
without guessing physical units. Independent readback, processing polarity,
audible/stereo behavior and runtime contracts remain unverified.
