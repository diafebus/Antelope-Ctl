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
209758 packets and zero drops. Parameter writes use `0x1c / 0xd5 / 0x0a`,
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

The five continuous dial pointers reach printed0/10. This does not establish
physical gain units, intermediate laws or a linear raw-to-physical conversion.
Knobs finish at their captured maximum as authorized.

Separate bounded GUI drags map every visible rotary detent, with a pointer
image and an isolated one-byte parameter observation for each position:

| Selector | Raw values in order | Printed labels in order |
|---|---|---|
| Low Frequency | 0, 1, 2, 3 | 20, 30, 60, 100; panel marked CPS |
| High Frequency | 0, 1, 2, 3, 4, 5, 6 | 3, 4, 5, 8, 10, 12, 16; panel marked KCS |
| Attenuation Frequency | 0, 1, 2 | 5, 10, 20 |

The endpoint sweep had skipped Low Frequency raw1; it was captured in the
directed detent pass rather than inferred. Low Frequency mapping is the completed
subset in `unattended-20261025-veq1a-rotary-map`. That whole mapper stopped for
calibration after High Frequency8pixel drags produced no writes; it remains a
stopped job. `unattended-20261025-veq1a-rotary-map2` completes the remaining
High Frequency/Attenuation Frequency maps with16/32pixel steps. Every action
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
processing switch. Its Dip dial visibly has eleven printed choices. Control
capture is in progress; neither its mappings nor its runtime contracts are
inherited from VEQ-1A or a sibling device.
