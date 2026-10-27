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

## BAE-1023

The directed vendor load at frame2327 in
`unattended-20261026T091415Z-load-bae1023/Orion.pcapng` establishes Orion
type24/instance0 in channel1 slot0, with seven empty slots. The native panel is
`Neve1023`; the compatibility identifier remains `neve_1023`.

Parameter blocks use `0x1d / 0xd5 / 0x0b`, type byte18/instance byte19.
The separate High-pass/Output endpoint job
`scan-Neve1023-20261026T100833281Z/Neve1023-channel2.pcapng` accepted four
phases (30,498 packets, zero drops). The coaxial job
`scan-Neve1023CoaxialRanges-20261026T104903760Z/Neve1023CoaxialRanges-channel2.pcapng`
accepted twelve phases (99,948 packets, zero drops).

| Control | Byte | Raw endpoint candidates | Source frames |
|---|---|---|---|
| Output (compatibility ID `gain`) | 20 | 236, 10 | 18971/26647, separate job |
| High Frequency | 21 | 0, 5 | 86953/95529, coaxial job |
| High Gain | 22 | 0, 100 | 69251/78715, coaxial job |
| Peak Frequency | 23 | 0, 11 | 52877/61125, coaxial job |
| Peak Gain | 24 | 0, 100 | 35785/44797, coaxial job |
| Low Frequency | 25 | 0, 4 | 20069/27853, coaxial job |
| Low Gain | 26 | 0, 100 | 4265/12749, coaxial job |
| High-pass | 27 | 0, 4 | 3965/11481, separate job |

Output values are literal unsigned wire bytes; signed interpretation and physical
scaling remain unverified. The concentric frequency/gain pairs share UIA bounds.
Directed native routing trials establish six distinct one-byte fields using
reviewed inner/outer interaction points, rather than inferring hit zones from
those bounds. The initial high-gain return stopped one raw unit short; a fresh
visual reconciliation and bounded five-pixel return restored the full original
payload. Quiet and stopped calibration records remain in the capture archive.

The completed `unattended-20261026T091415Z-bae1023-frequency-map` contains
48 bounded 32-pixel GUI steps, isolated field observations and pointer images.
Every position is observed, other payload bytes are preserved, and the final
full parameter payload matches the starting maximum block. Printed labels are
retained literally:

| Selector | Raw values | Printed labels in order |
|---|---|---|
| Low Frequency | 0–4 | Off, 220, 110, 60, 35 |
| Peak Frequency | 0–11 | Off, 10k, 8k2, 7k2, 4k8, 3k2, 1k6, 700, 510, 360, 270, 160 |
| High Frequency | 0–5 | Off, 10k, 12k, 16k, 20k, 24k |
| High-pass | 0–4 | Off, 50, 80, 160, 300 |

The last Peak Frequency position is printed 160 Hz; it is not inferred from a
similarly named equalizer. Phase is a separate byte28 two-state control:
`unattended-20261026T091415Z-bae1023-phase-first/Orion.pcapng` frame1665
changes 0→1; `-phase-return/Orion.pcapng` frame941 changes 1→0. The return
verification confirms the full parameter payload and exact RGB matches for
High-pass, all three coaxial regions, Output, Phase and EQ.

The separate EQ processing switch uses `0x14 / 0x98`, with instance17/type18/
state19. In `unattended-20261026T091415Z-bae1023-processing/first/Orion.pcapng`,
frame3485 carries `00 18 00`; return frame855 in
`unattended-20261026T091415Z-bae1023-processing/return/Orion.pcapng` carries
`00 18 01`. All seven checked control regions return exactly to baseline RGB.
Processing polarity and audible behavior remain unverified.

This completes the observed editable controls. The separately observed
`NevePeakMeter` display does not establish a telemetry contract. Physical and
intermediate scaling, independent parameter/processing readback, meter telemetry,
audible/stereo behavior and runtime contracts remain unverified. Captured vendor
writes and image restoration do not enable a runtime writer or expand query bounds.

## NEU-PEV

The directed vendor load at frame2511 in
`unattended-20261026T091415Z-load-neu-pev/Orion.pcapng` establishes Orion
type13/instance0 in channel1 slot0, with seven empty slots. The observed native
panel is `NeumannPev`; the compatibility identifier is `neumann_pev`.

Parameter blocks use `0x19 / 0xd5 / 0x07`, type byte18/instance byte19.
The initial job `scan-NeumannPev-20261026T161447638Z` stopped during priming
because that passive family was unrecognized; zero sweep actions were accepted.
Its observed low-gain writes and subsequent fresh GUI reconciliation are retained
as calibration evidence, without a blind restoration. The corrected native job
`scan-NeumannPev-20261026T161740457Z/NeumannPev-channel2.pcapng` accepted all
ten endpoint phases, with 78,812 packets and zero drops. Each phase changes
only its mapped parameter byte.

| Control | Byte | Raw endpoint candidates, minimum/maximum gestures | Source frames |
|---|---|---|---|
| Low Gain | 20 | 251, 3 | 4185/11775 |
| Presence Gain (`pres_gain`) | 21 | 0, 4 | 18917/26639 |
| Presence Frequency (`pres_freq`) | 22 | 0, 6 | 34205/42141 |
| High Gain | 23 | 251, 4 | 50185/58381 |
| Output (`level`) | 24 | 232, 12 | 66265/74663 |

The completed `unattended-20261026T091415Z-neu-pev-detent-map` records all
four stepped dials across 62 bounded trials, with isolated raw-field observations
and matching pointer images. Other payload bytes are preserved, and the final
full captured parameter payload matches the starting maximum block. The seven
static regions match the last endpoint image exactly: Low Gain, Presence Gain,
Presence Frequency, High Gain, Output body, power and LED. The animated peak
meter is excluded from these image comparisons.

| Selector | Raw values in order | Printed labels in order |
|---|---|---|
| Low Gain | 251, 252, 253, 254, 255, 0, 1, 2, 3 | -15, -12, -9, -6, -3, 0, 3, 6, 9 |
| Presence Gain | 0–4 | 0, 2, 4, 6, 8 |
| Presence Frequency | 0–6 | 0.7, 1, 1.4, 2, 2.8, 4, 5.6 |
| High Gain | 251, 252, 253, 254, 255, 0, 1, 2, 3, 4 | -15, -12, -9, -6, -3, 0, 3, 6, 9, m |

The High Gain label `m` remains literal, without an inferred meaning. Wrapped
unsigned wire values are preserved; dial labels are GUI observations. Output's
wire endpoints 232/12 have signed candidates -24/+12, but signed interpretation,
physical units and intermediate scaling remain unverified.

The separate processing switch uses `0x14 / 0x98`, instance17/type18/state19.
In `unattended-20261026T091415Z-neu-pev-processing/first/Orion.pcapng`,
frame4619 carries `00 0d 00`; frame1247 in
`unattended-20261026T091415Z-neu-pev-processing/return/Orion.pcapng` carries
`00 0d 01`. All seven static control/switch/LED regions return exactly to baseline
RGB. Processing polarity remains unverified.

This completes the observed editable controls. `NeumannPeakMeter` and `AfxLed`
remain separate display inventory observations; their presence does not establish
signal telemetry. Independent parameter/processing readback, signal telemetry,
physical/intermediate scaling, audible/stereo behavior and runtime contracts
remain unverified. No runtime writer or query bounds are expanded.

## NEU-W492

The directed vendor load at frame2285 in
`unattended-20261026T163323Z-load-neu-w492/Orion.pcapng` establishes Orion
type15/instance0 in channel1 slot0, with seven empty slots. The native panel is
`NeumannW492`; the compatibility identifier is `neumann_w492`.

Parameter blocks use the independently observed `0x22 / 0xd5 / 0x10` family,
with type byte18/instance byte19. The historical native priming job
`scan-NeumannW492-20261026T163707526Z` stopped with zero accepted sweep phases
when this family was unrecognized. Its byte21 Low Gain observations are retained
as calibration evidence. After fresh GUI reconciliation, the corrected job
`scan-NeumannW492-20261026T164051354Z/NeumannW492-channel2.pcapng` accepted
all eighteen endpoint phases: 149,536 packets, zero drops.

| Control | Byte | Raw endpoint candidates, minimum/maximum gestures | Source frames |
|---|---|---|---|
| Low Gain | 21 | 0, 100 | 4173/11613 |
| Low-Mid Gain | 24 | 0, 100 | 18731/26321 |
| High-Mid Gain | 27 | 0, 100 | 33655/41545 |
| High Gain | 30 | 0, 100 | 49025/57225 |
| Low Frequency | 22 | 0, 100 | 65197/73395 |
| Low-Mid Frequency | 25 | 0, 100 | 81987/90455 |
| High-Mid Frequency | 28 | 0, 100 | 99193/107971 |
| High Frequency | 31 | 0, 100 | 117153/126071 |
| Output (`level`) | 33 | 232, 12 | 135271/144729 |

These are endpoint candidates; physical gain/frequency units and intermediate
scaling remain unverified. Output retains literal unsigned wire232/12 with signed
candidates -24/+12, without asserting signed interpretation or physical units.

The isolated `unattended-20261026T163323Z-neu-w492-sections` trials establish
four separate section switches. Each first click changes only its listed byte
0→1; the return changes it 1→0 and restores the full captured parameter payload
and static panel image.

| Section | Byte | First/return frames |
|---|---|---|
| Low | 23 | 795/683 |
| Low-Mid | 26 | 723/709 |
| High-Mid | 29 | 707/708 |
| High | 32 | 787/711 |

Raw0 is the observed left position and raw1 the right position. These image
associations do not establish enabled polarity or audible behavior.

The separate `unattended-20261026T163323Z-neu-w492-lowcut` trial observes
Low Cut byte20 cycling 0→1 at frame753, 1→2 at frame778, then 2→0 at frame731
in successive isolated captures. The full captured parameter payload and static
panel image return. Reviewed pointer images establish the literal mapping:

| Low Cut raw | Position | Printed label |
|---|---|---|
| 0 | Top | 140 Hz |
| 1 | Middle | 20 Hz |
| 2 | Bottom | 80 Hz |

The state order is retained as observed rather than sorted by frequency.

The separate processing switch uses `0x14 / 0x98`, instance17/type18/state19.
`unattended-20261026T163323Z-neu-w492-processing/first/Orion.pcapng`
frame3065 carries `00 0f 00`; frame699 in
`unattended-20261026T163323Z-neu-w492-processing/return/Orion.pcapng` carries
`00 0f 01`. The static panel segments return exactly; the animated meter is
excluded. Processing polarity remains unverified.

This completes capture of the observed editable controls. Separately inventoried
`NeumannPeakMeter` and `AfxLed` classes do not establish signal telemetry.
Independent parameter/processing readback, physical/intermediate scaling,
signal telemetry, audible/stereo behavior and runtime contracts remain unverified.
No runtime writer or query bounds are expanded.

## NEU-W495

The directed vendor load at frame2209 in
`unattended-20261026T163323Z-load-neu-w495/Orion.pcapng` establishes Orion
type20/instance0 in channel1 slot0, with seven empty slots. The native panel is
`NeumannW495`; the compatibility identifier is `neumann_w495`.

Parameter blocks use `0x1c / 0xd5 / 0x0a`, type byte18/instance byte19.
The native endpoint job
`scan-NeumannW495-20261026T165426097Z/NeumannW495-channel2.pcapng` accepted
all fourteen phases, with 113,326 packets and zero drops. The endpoint scans
intentionally finish at their captured maxima.

| Control | Byte | Raw endpoint candidates, minimum/maximum gestures | Source frames |
|---|---|---|---|
| Low Gain | 21 | 251, 5 | 4309/11643 |
| Low Frequency | 20 | 0, 2 | 18887/26467 |
| Mid Gain | 23 | 251, 5 | 34663/42659 |
| Mid Frequency | 22 | 0, 10 | 50243/58293 |
| High Gain | 26 | 251, 5 | 66184/74384 |
| High Frequency | 25 | 0, 2 | 82583/91083 |
| Output (`level`) | 27 | 232, 12 | 100057/108873 |

The completed `unattended-20261026T163323Z-neu-w495-detent-map` records all
six stepped dials across100 bounded trials, with isolated field observations
and matching pointer images. Every printed position has a reviewed raw-value
association. Wrapped gain bytes retain their actual observed order, without a
misleading contiguous raw range:

| Selector | Raw values in order | Printed labels in order |
|---|---|---|
| Low Gain | 251, 252, 253, 254, 255, 0, 1, 2, 3, 4, 5 | -15, -9, -6, -4, -2, 0, 2, 4, 6, 9, 15 |
| Low Frequency | 0, 1, 2 | 40, 60, 100 |
| Mid Gain | 251, 252, 253, 254, 255, 0, 1, 2, 3, 4, 5 | -10, -8, -6, -4, -2, 0, 2, 4, 6, 8, 10 |
| Mid Frequency | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 | 175, 250, 350, 500, 700, 1k, 1.4k, 2k, 2.8k, 4k, 5.6k |
| High Gain | 251, 252, 253, 254, 255, 0, 1, 2, 3, 4, 5 | -15, -9, -6, -4, -2, 0, 2, 4, 6, 9, 15 |
| High Frequency | 0, 1, 2 | 7, 10, 14 |

The labels remain literal GUI observations; physical units, intermediate scaling
and audible behavior are not inferred. Output byte27 retains unsigned wire
endpoints232/12 with signed candidates -24/+12; signed interpretation and
physical/intermediate scaling remain unverified.

The separate `unattended-20261026T163323Z-neu-w495-bell-quality` cycle changes
only byte24: raw1→2 at frame975, 2→0 at frame935 and 0→1 at frame933 in
successive isolated captures. Reviewed images establish raw0 Left, raw1 Middle
and raw2 Right. The visible label is Bell Quality; the compatibility control ID
remains `mid_q`. These literal positions do not establish numeric Q values.

Dial mapping and Bell Quality round trips returned the full captured parameter
body and checked static panel images. Their return checks are distinct from the
endpoint scans, which intentionally finish at maxima.

The separate processing switch uses `0x14 / 0x98`, instance17/type18/state19.
`unattended-20261026T163323Z-neu-w495-processing/first/Orion.pcapng`
frame3869 carries `00 14 00`; frame1071 in
`unattended-20261026T163323Z-neu-w495-processing/return/Orion.pcapng` carries
`00 14 01`. Processing returned its checked static baseline, with both static
panel segments matching exactly; the animated peak meter is excluded.
Processing polarity remains unverified.

This completes the observed editable controls. Separately inventoried
`NeumannPeakMeter` and `AfxLed` classes do not establish signal telemetry.
Independent parameter/processing readback, signal telemetry, physical/intermediate
scaling, audible/stereo behavior and runtime contracts remain unverified.
No runtime writer or query bounds are expanded.
