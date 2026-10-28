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

## VEQ-4K PINK

The directed vendor load at frame2217 in
`unattended-20261027T015403Z-load-veq4k-pink/Orion.pcapng` establishes Orion
type16/instance0 in channel1 slot0, with seven empty slots. The native panel is
`SslPink`; the compatibility identifier is `ssl_pink`.

The first native attempt rejected the measured lower-row UIA overflow before
any input. Those five 140-pixel rotary rectangles extend14 pixels below the
panel; seven upper rectangles extend12 pixels above it. A capture-backed
allowance retains original-panel interaction-area, full-root containment and
native point/focus guards. The subsequent priming job
`scan-SslPink-20261027T020747657Z` stopped with zero accepted endpoint phases
when its actual `0x23 / 0xd5 / 0x11` family was unrecognized. Both historical
stops remain in the evidence archive.

The corrected native job
`scan-SslPink-20261027T021124243Z/SslPink-channel2.pcapng` accepted all
twenty-six endpoint phases, with 229,820 packets and zero drops. Parameter blocks
use type byte18/instance byte19. Only each directed control field changes.
Endpoint scans intentionally finish at their captured maxima.

| Control | Byte | Raw endpoint candidates, minimum/maximum gestures | Source frames |
|---|---|---|---|
| Low Cut | 20 | 0, 100 | 4239/11503 |
| High Cut | 21 | 0, 100 | 19001/25915 |
| HF Gain | 22 | 0, 100 | 34229/41993 |
| HF Frequency | 23 | 0, 100 | 50003/57363 |
| HMF Gain | 25 | 0, 100 | 66125/74255 |
| HMF Frequency | 26 | 0, 100 | 82745/90524 |
| HMF Quality | 27 | 0, 100 | 99829/108515 |
| LMF Gain | 28 | 0, 100 | 117463/126487 |
| LMF Frequency | 29 | 0, 100 | 135657/144279 |
| LMF Quality | 30 | 0, 100 | 154349/163827 |
| LF Gain | 32 | 0, 100 | 173595/183439 |
| LF Frequency | 33 | 0, 100 | 193387/202879 |
| Output | 34 | 232, 12 | 213647/223711 |

Raw0/100 observations do not establish physical units or intermediate gain,
frequency or quality laws. Output byte34 retains unsigned wire232/12 with signed
candidates -24/+12; signed interpretation and physical/intermediate scaling
remain unverified.

The isolated `unattended-20261027T015403Z-veq4k-pink-modes` trials establish
the two actual printed mode labels and their LED associations:

| Visible label | Compatibility ID | Byte | First/return frames | Observed states |
|---|---|---|---|---|
| LMF ÷3 | `lf_bell` | 31 | 706/630 | 0 LED Dark → 1 LED Lit → 0 LED Dark |
| HMF ×3 | `hf_bell` | 24 | 731/707 | 0 LED Dark → 1 LED Lit → 0 LED Dark |

Each mode round trip returned the full captured parameter body and checked
static panel images. These are literal printed-label/LED observations; the
compatibility IDs do not establish bell semantics, frequency laws or audible
behavior.

The separate processing switch uses `0x14 / 0x98`, instance17/type18/state19.
`unattended-20261027T015403Z-veq4k-pink-processing/first/Orion.pcapng`
frame2865 carries `00 10 00`; frame645 in
`unattended-20261027T015403Z-veq4k-pink-processing/return/Orion.pcapng` carries
`00 10 01`. Processing returned its checked static baseline, with both panel
segments matching exactly; the animated peak meter is excluded. Processing
polarity remains unverified.

This completes the observed editable controls. `SslPeakMeter` and three native
`AfxLed` widgets remain separate display inventory observations; signal telemetry
is unknown. Independent parameter/processing readback, physical/intermediate
scaling, audible/stereo behavior and runtime contracts remain unverified.
No runtime writer or query bounds are expanded.

## VEQ-4K ORANGE

The directed vendor load at frame2113 in
`unattended-20261027T015403Z-load-veq4k-orange/Orion.pcapng` independently
establishes Orion type17/instance0 in channel1 slot0, with seven empty slots.
The native panel is `SslOrange`; the compatibility identifier is `ssl_orange`.

The native job
`scan-SslOrange-20261027T022803586Z/SslOrange-channel2.pcapng` accepted all
twenty-six endpoint phases: 227,598 packets, zero drops. Its actual parameter
family is `0x23 / 0xd5 / 0x11`, type byte18/instance byte19. Each directed
phase changes only its mapped field. Endpoint scans intentionally finish at
their captured maxima.

| Control | Byte | Raw endpoint candidates, minimum/maximum gestures | Source frames |
|---|---|---|---|
| Low Cut | 20 | 0, 100 | 4193/11451 |
| High Cut | 21 | 0, 100 | 18969/25735 |
| HF Gain | 22 | 0, 100 | 34096/41713 |
| HF Frequency | 23 | 0, 100 | 49577/56889 |
| HMF Gain | 25 | 0, 100 | 65547/73581 |
| HMF Frequency | 26 | 0, 100 | 82129/89809 |
| HMF Quality | 27 | 0, 100 | 99011/107545 |
| LMF Gain | 28 | 0, 100 | 116441/125275 |
| LMF Frequency | 29 | 0, 100 | 134397/142917 |
| LMF Quality | 30 | 0, 100 | 152835/162305 |
| LF Gain | 32 | 0, 100 | 171977/181609 |
| LF Frequency | 33 | 0, 100 | 191575/200857 |
| Output | 34 | 232, 12 | 211589/221563 |

Raw0/100 observations do not establish physical units or intermediate gain,
frequency or quality laws. Output byte34 retains unsigned wire232/12 with signed
candidates -24/+12; signed interpretation and physical/intermediate scaling
remain unverified.

The separate `unattended-20261027T015403Z-veq4k-orange-modes` trials identify
the actual printed BELL labels under the LF and HF groups:

| Visible label | Compatibility ID | Byte | First/return frames | Observed states |
|---|---|---|---|---|
| LF BELL | `lf_bell` | 31 | 781/743 | 0 LED Dark → 1 LED Lit → 0 LED Dark |
| HF BELL | `hf_bell` | 24 | 781/705 | 0 LED Dark → 1 LED Lit → 0 LED Dark |

Independent image review establishes these literal labels and raw-to-LED
associations. Each mode round trip returns the full captured parameter body and
checked static panel images. No frequency-range behavior, numeric Q values or
audible effect is inferred from these labels or from other equalizer models.

The separate processing switch uses `0x14 / 0x98`, instance17/type18/state19.
`unattended-20261027T015403Z-veq4k-orange-processing/first/Orion.pcapng`
frame2881 carries `00 11 00`; frame715 in
`unattended-20261027T015403Z-veq4k-orange-processing/return/Orion.pcapng`
carries `00 11 01`. Processing returns its checked static baseline, with both
panel segments matching exactly; the animated peak meter is excluded.
Processing polarity remains unverified.

This completes the observed editable controls. `SslPeakMeter` and three native
`AfxLed` widgets remain separate display inventory observations; signal telemetry
is unknown. Independent parameter/processing readback, physical/intermediate
scaling, audible/stereo behavior and runtime contracts remain unverified.
No runtime writer or query bounds are expanded.

## VEQ-4K BROWN

The directed vendor load at frame2179 in
`unattended-20261027T015403Z-load-veq4k-brown/Orion.pcapng` independently
establishes Orion type19/instance0 in channel1 slot0, with seven empty slots.
The native panel is `SslBrown`; the compatibility identifier is `ssl_brown`.

The native job
`scan-SslBrown-20261027T024419020Z/SslBrown-channel2.pcapng` accepted all
twenty-six endpoint phases: 226,014 packets, zero drops. Its actual parameter
family is `0x23 / 0xd5 / 0x11`, type byte18/instance byte19. Each directed
phase changes only its mapped field. Endpoint scans intentionally finish at
their captured maxima.

| Control | Byte | Raw endpoint candidates, minimum/maximum gestures | Source frames |
|---|---|---|---|
| Low Cut | 20 | 0, 100 | 4059/11303 |
| High Cut | 21 | 0, 100 | 18767/25559 |
| HF Gain | 22 | 0, 100 | 33723/41373 |
| HF Frequency | 23 | 0, 100 | 49179/56475 |
| HMF Gain | 25 | 0, 100 | 65131/73187 |
| HMF Frequency | 26 | 0, 100 | 81517/89175 |
| HMF Quality | 27 | 0, 100 | 98139/106719 |
| LMF Gain | 28 | 0, 100 | 115479/124207 |
| LMF Frequency | 29 | 0, 100 | 133229/141706 |
| LMF Quality | 30 | 0, 100 | 151543/160953 |
| LF Gain | 32 | 0, 100 | 170519/180183 |
| LF Frequency | 33 | 0, 100 | 190073/199307 |
| Output | 34 | 232, 12 | 210021/220089 |

Raw0/100 observations do not establish physical units or intermediate gain,
frequency or quality laws. Output byte34 retains unsigned wire232/12 with signed
candidates -24/+12; signed interpretation and physical/intermediate scaling
remain unverified.

The separate `unattended-20261027T015403Z-veq4k-brown-modes` trials identify
the actual printed BELL labels under the LF and HF groups:

| Visible label | Compatibility ID | Byte | First/return frames | Observed states |
|---|---|---|---|---|
| LF BELL | `lf_bell` | 31 | 771/681 | 0 LED Dark → 1 LED Lit → 0 LED Dark |
| HF BELL | `hf_bell` | 24 | 765/727 | 0 LED Dark → 1 LED Lit → 0 LED Dark |

Independent image review establishes these literal labels and raw-to-LED
associations. Each mode round trip returns the full captured parameter body and
checked static panel images. No frequency-range behavior, numeric Q values or
audible effect is inferred from these labels or from other equalizer models.

The separate processing switch uses `0x14 / 0x98`, instance17/type18/state19.
`unattended-20261027T015403Z-veq4k-brown-processing/first/Orion.pcapng`
frame2981 carries `00 13 00`; frame659 in
`unattended-20261027T015403Z-veq4k-brown-processing/return/Orion.pcapng`
carries `00 13 01`. Processing returns its checked static baseline, with both
panel segments matching exactly; the animated peak meter is excluded.
Processing polarity remains unverified.

This completes the observed editable controls. `SslPeakMeter` and three native
`AfxLed` widgets remain separate display inventory observations; signal telemetry
is unknown. Independent parameter/processing readback, physical/intermediate
scaling, audible/stereo behavior and runtime contracts remain unverified.
No runtime writer or query bounds are expanded.

## VEQ-STU 900

The directed vendor load at frame2469 in
`unattended-20261027T015403Z-load-veqstu900/Orion.pcapng` establishes Orion
type23/instance0 in channel1 slot0, with seven empty slots. The native panel is
`Studer900`; the compatibility identifier is `veq_stu_900`.

Native job `scan-Studer900-20261027T030034849Z/Studer900-channel2.pcapng`
accepted all twenty-two endpoint phases: 187,642 packets, zero drops. Its
observed parameter family is `0x23 / 0xd5 / 0x11`, type byte18/instance byte19.
Each directed phase changes only its mapped field. Endpoint scans intentionally
finish at their captured maxima.

| Control | Byte | Raw endpoint candidates, minimum/maximum gestures | Source frames |
|---|---|---|---|
| Low Cut | 20 | 0, 100 | 4119/10939 |
| High Cut | 21 | 0, 100 | 19113/26677 |
| LF Gain | 22 | 0, 100 | 34337/42061 |
| LF Frequency | 23 | 0, 100 | 50015/57425 |
| LMF Gain | 25 | 0, 100 | 66199/74311 |
| LMF Frequency | 26 | 0, 100 | 82715/90479 |
| HMF Gain | 28 | 0, 100 | 99587/108329 |
| HMF Frequency | 29 | 0, 100 | 117129/125465 |
| HF Gain | 31 | 0, 100 | 135125/144271 |
| HF Frequency | 32 | 0, 100 | 153621/162361 |
| Output | 34 | 232, 12 | 172577/182093 |

Reviewed endpoint images identify Low Cut byte20 raw0 at frame4119 as OFF,
and High Cut (`hi_cut`) byte21 raw100 at frame26677 as OFF. These are different
raw ends; no shared OFF convention or intermediate frequency law is inferred.
Other raw0/100 endpoints do not establish physical gain/frequency units or
intermediate scaling. Output byte34 retains unsigned wire232/12 with signed
candidates -24/+12; signed interpretation and physical scaling remain unverified.

The separate `unattended-20261027T015403Z-veqstu900-modes` trials establish
four individual two-position shape-glyph switches, with no separate switch LEDs:

| Switch | Compatibility ID | Byte | First/return frames | Reviewed positions |
|---|---|---|---|---|
| LF | `lf_switch` | 24 | 703/737 | 0 Upper → 1 Lower → 0 Upper |
| LMF | `lmf_switch` | 27 | 811/747 | 0 Upper → 1 Lower → 0 Upper |
| HMF | `hmf_switch` | 30 | 829/809 | 0 Upper → 1 Lower → 0 Upper |
| HF | `hf_switch` | 33 | 821/835 | 0 Upper → 1 Lower → 0 Upper |

Each switch round trip returns the full captured parameter body and checked
static panel images. These literal position/shape-glyph observations do not
establish numeric Q, bell semantics or audible behavior.

The separate processing switch uses `0x14 / 0x98`, instance17/type18/state19.
`unattended-20261027T015403Z-veqstu900-processing/first/Orion.pcapng`
frame3323 carries `00 17 00`; frame725 in
`unattended-20261027T015403Z-veqstu900-processing/return/Orion.pcapng` carries
`00 17 01`. Processing returns its checked static baseline, with both panel
segments matching exactly; the animated meter is excluded. Processing polarity
remains unverified.

This completes the observed editable controls. `Studer900Peakmeter` and the
embedded red processing lamp in `Studer900Bypass` remain separate display
inventory observations; their presence does not establish signal telemetry.
Independent parameter/processing readback, physical/intermediate scaling,
audible/stereo behavior and runtime contracts remain unverified.
No runtime writer or query bounds are expanded.

## VEQ-STU 169

The directed load at frame2541 in
`unattended-20261027T144257Z-load-veqstu169/Orion.pcapng` establishes Orion
type22/instance0 on AFX2/channel1 slot0, with seven empty slots. Its native
panel is `Studer169`; the compatibility identifier remains `veq_stu_169`.

`scan-Studer169-20261027T144830356Z/Studer169-channel2.pcapng` accepts ten
endpoint phases with 79,046 packets and zero drops. The observed parameter
family is `0x1a / 0xd5 / 0x08`, type byte18/instance byte19. Each phase changes
only its isolated field; the concentric MF Gain and Frequency gestures affect
distinct bytes and preserve their partner.

| Control | Byte | Raw endpoint candidates, minimum/maximum gestures | Source frames |
|---|---|---|---|
| LF Gain | 24 | 0, 100 | 4169/11333 |
| MF Gain, inner knob | 22 | 0, 100 | 19189/26501 |
| MF Frequency, outer red ring | 23 | 0, 100 | 34700/42114 |
| HF Gain | 21 | 0, 100 | 50373/57929 |
| Output | 25 | 232, 12 | 66387/74395 |

Printed gain ticks0-4 and frequency labels150/250/500/1K/2K/4K/7K establish
neither a finite detent map nor a physical/interpolation law. Output retains
unsigned wire232/12 with signed candidates -24/+12; physical units and signed
interpretation remain unverified. Endpoint scans intentionally end at maxima.

The separate `unattended-20261027T144257Z-veqstu169-filter` trial maps the
Filter lever (`hpf_switch`) at byte20: first frame749 raw1 is Lower, return
frame767 raw0 is Upper. Each action changes only that field. The full captured
parameter body and checked static panel return exactly. These positional
labels do not establish filter shape, cutoff, enabled polarity or audio behavior.

The separate processing trial uses `0x14 / 0x98`, instance17/type18/state19.
First frame3027 in
`unattended-20261027T144257Z-veqstu169-processing/first/Orion.pcapng` carries
`00 16 00`; return frame617 in its `return/Orion.pcapng` carries `00 16 01`.
Both static panel segments return exactly, including processing lever/LED,
Filter and all rotary regions; the animated meter is excluded. This is GUI
restoration, without an independent changed-state device readback claim.

The native inventory contains one `Studer089Peakmeter` and one `AfxLed` on this
STU169 panel. Those observed class names are retained without inferring signal
meaning, scale or a telemetry reader. All visible editable controls now have
capture passes. Independent readback, physical/intermediate scaling,
audible/stereo behavior and runtime contracts remain unverified. No writer or
query bounds are expanded.

## VEQ-STU 089

The directed load at frame1581 in
`unattended-20261027T144257Z-load-veqstu089/Orion.pcapng` establishes Orion
type21/instance0 on AFX2/channel1 slot0, with seven empty slots. Its native
panel is `Studer089`; the compatibility identifier remains `veq_stu_089`.

`scan-Studer089-20261027T150545312Z/Studer089-channel2.pcapng` accepts four
rotary endpoint phases with 32,039 packets and zero drops. The parameter family
is `0x1b / 0xd5 / 0x09`, type byte18/instance byte19. Presence Gain uses byte24:
raw0/100 at frames4475/12839. Output uses byte26: unsigned232/12 at
frames20383/27775, with signed candidates -24/+12 only. Every phase changes
only its isolated field. These are raw endpoint candidates; printed rotary
ticks establish neither detents nor a physical/interpolation law. The endpoint
scan intentionally ends at maxima.

The five vertical sliders require stepped maps. Directed KVM tablet gestures
stop on the first isolated captured change, with a screenshot for each position.
Both visible terminals are witnessed; each control returns the entire captured
parameter body and checked static panel. Equal reverse pixel travel alone was
insufficient during LF Cut calibration: the guard stopped one position short,
and a separately reviewed measured return restored the exact baseline. The
stopped trial and negative input probes remain in the local evidence archive.

| Control | Byte | Captured raw-to-printed-label map |
|---|---|---|
| LF Cut | 20 | 0: –; 1:60; 2:100; 3:150; 4:250 Hz |
| HF Cut | 21 | 0: –; 1:12; 2:8; 3:5; 4:3 kHz |
| LF Shelf, 80Hz | 22 | 4:+8; 3:+6; 2:+4; 1:+2; 0:-; 255:-2; 254:-4; 253:-6; 252:-8 (printed dB) |
| HF Shelf, 8kHz | 23 | 4:+8; 3:+6; 2:+4; 1:+2; 0:-; 255:-2; 254:-4; 253:-6; 252:-8 (printed dB) |
| Presence Frequency | 25 | 0: –; 1:0.4; 2:0.7; 3:1.2; 4:2.2; 5:3.9; 6:6.8 kHz |

Selector sources are
`unattended-20261027T144257Z-veqstu089-selector-maps`; shelf sources are
`unattended-20261027T144257Z-veqstu089-shelf-maps`. Each accepted raw map is
independently checked against the paired pointer image. Exact frames and hashes
belong to each model-local catalog encoding. The literal dash is retained;
the [vendor manual](https://jp.antelopeaudio.com/support/user-manuals/veq-stu-089/)
declares bypass and the printed units, while the directed captures establish
wire order. Printed shelf labels do not verify calibrated audible gain.

The separate processing source is
`unattended-20261027T144257Z-veqstu089-processing`. First frame3863 in
`first/Orion.pcapng` carries tuple `001500`; return frame1055 in
`return/Orion.pcapng` carries `001501`. The family is
`0x14 / 0x98`, instance17/type18/state19. Both checked static panel segments
return exactly, including processing lever/LED and all parameter controls;
the animated peak meter is excluded. This is GUI restoration without an
independent changed-state device readback or polarity claim.

One native `Studer089Peakmeter` and one `AfxLed` record GUI presence only;
signal meaning, scale and telemetry remain unverified. All seven visible
parameter controls and the separate processing switch have capture passes.
Independent per-field readback, rotary scales/interpolation, signed
interpretations, audible/stereo behavior and runtime contracts remain pending.
No runtime writer or query bounds are expanded.

## MG4+

The directed load at frame1869 in
`unattended-20261027T144257Z-load-mg4plus/Orion.pcapng` establishes Orion
type68/instance0 on AFX2/channel1 slot0, with seven empty slots. The native
panel is `Mg4`; the compatibility effect ID remains `mg4`. A fresh read-only
inventory on resume is recorded in
`unattended-20261028T023901Z-mg4plus-resume-inventory/raw-ui.json`.

`scan-Mg4-20261028T024610925Z/Mg4-channel2.pcapng` accepts fourteen endpoint
phases with 114,052 packets and zero drops. Its parameter family is
`0x1c / 0xd5 / 0x0a`, type byte18/instance byte19. Each action changes only
its isolated one-byte field.

| Control | Byte | Raw endpoint candidates, minimum/maximum gestures | Source frames |
|---|---|---|---|
| Output | 20 | 0, 20 | 3995/10815 |
| Sub Gain | 21 | 0, 20 | 19013/26079 |
| 40Hz Gain | 22 | 0, 20 | 34383/42045 |
| 160Hz Gain | 23 | 0, 20 | 50205/57767 |
| 650Hz Gain | 24 | 0, 20 | 66511/74689 |
| 2.5kHz Gain | 25 | 0, 20 | 83184/91263 |
| Sky Gain | 26 | 0, 20 | 100647/109381 |

These are raw endpoint candidates. Sub Gain priming frames2353/2397 in
`unattended-20261028T023901Z-mg4plus-priming/Orion.pcapng`
show post-first byte21 changing11→12; the first observed block has no preceding
captured preservation baseline. This quantization and the printed gain ticks
establish neither a complete finite gain map nor a physical/interpolation law.
In particular, Output raw0/20 is retained without inferring a signed scale or
calibrated gain from its printed endpoint marks. Endpoint scans intentionally
end at maxima.

Sky Band is captured separately as an eleven-position selector at byte27.
The complete raw-to-printed-label map is:

| Raw | Printed Sky Band label |
|---|---|
| 0 | OFF |
| 1 | 2.5 |
| 2 | 3.5 |
| 3 | 5 |
| 4 | 7 |
| 5 | 10 |
| 6 | 15 |
| 7 | 20 |
| 8 | 25 |
| 9 | 30 |
| 10 | 40 |

The panel marks kHz for its frequency choices; OFF remains a literal label.
`unattended-20261028T023901Z-mg4plus-sky-map` contains twenty directed
raw-change trials and two unchanged bounded drags at the visible terminals.
Each accepted change has one captured value, a changed pointer image and
preserved other fields/static controls. Independent raw/image review confirms
every association. The full captured parameter body and both checked static
panel segments return exactly to the baseline. Exact source frames and hashes
are retained in the model-local catalog. These labels do not calibrate the
audible filter response.

The separate processing source is
`unattended-20261028T023901Z-mg4plus-processing`. First frame3233 in
`first/Orion.pcapng` carries tuple `00 44 00`; return frame774 in
`return/Orion.pcapng` carries `00 44 01`. The family is `0x14 / 0x98`,
instance17/type18/state19. Both checked static panel segments return exactly,
including button/embedded blue lamp and all eight rotary regions; the animated
meter is excluded. This establishes GUI restoration without independent
changed-state device readback or a device polarity claim.

The native inventory contains `Mg4PeakMeter` and a visible blue processing lamp
within `Mg4BypassButton`. Their GUI presence establishes no signal source,
scale or telemetry reader. All eight visible parameter controls and processing
have capture passes; independent per-field readback, gain/output scales and
interpolation, audible/stereo behavior and runtime contracts remain unverified.
No runtime writer or query bounds are expanded.


## Audio / Baton — visible control pass, 2026-10-28

Orion type69/instance0 is established by directed vendor loads at frame1627
in `unattended-20261028T023901Z-load-audiobaton/Orion.pcapng` and frame1549
in `unattended-20261028T145303Z-load-audiobaton/Orion.pcapng`. The second
load also emits a parameter initialization block at frame1577 (ten bytes50).
The original one-OUT load guard stops; a separate read-only reconciliation
verifies the sole expected slot/caption and enabled controls. No load is replayed.

The native panel is `AudioBaton`. Nine horizontal rollers have paired vertical
parameter indicators; circular VOLUME keeps compatibility ID `drive`.
Parameter blocks use `0x1e / 0xd5 / 0x0c`, type byte18/instance byte19.
All ten endpoint pairs are now captured. Each source is the named directory's
`AudioBaton-channel2.pcapng`; each accepted pair isolates one field and has zero drops.

| Control | Byte | Raw minimum/maximum candidates | Source directory | Frames |
|---|---|---|---|---|
| 40Hz Gain | 20 | 0/100 | scan-AudioBaton-20261028T034922060Z | 7489/17273 |
| 80Hz Gain | 21 | 0/100 | scan-AudioBaton-20261028T041027439Z | 6385/14811 |
| 160Hz Gain | 22 | 0/100 | scan-AudioBaton-20261028T081055452Z | 6357/14985 |
| 320Hz Gain | 23 | 0/100 | scan-AudioBaton-20261028T081932713Z | 6027/14661 |
| 640Hz Gain | 24 | 0/100 | scan-AudioBaton-20261028T145656344Z | 5747/14531 |
| 1280Hz Gain | 25 | 0/100 | scan-AudioBaton-20261028T145757910Z | 5635/14461 |
| 2560Hz Gain | 26 | 0/100 | scan-AudioBaton-20261028T150138570Z | 5171/14013 |
| 5120Hz Gain | 27 | 0/100 | scan-AudioBaton-20261028T150709189Z | 4807/14793 |
| 10240Hz Gain | 28 | 0/100 | scan-AudioBaton-20261028T150808541Z | 4073/14277 |
| VOLUME (`drive`) | 29 | 0/100 | scan-AudioBaton-20261028T081837554Z | 4629/11965 |

Ranges are raw endpoint candidates; physical scaling/interpolation, independent
readback and audible response remain unverified. Scans intentionally end at maxima.
The early vertical40Hz probe produced noOUT; horizontal frame2665 established
raw50→51 with the paired mark moving y324→323. Stopped geometry trials remain
preserved, including SG640/2560/5120 before fresh successful passes. Each allowed
one-pixel X shift was measured for that control; native class/RID/Y/W/H and other
body/static controls were checked separately, and the source proofs were
independently reviewed. No control's allowance came from its siblings.
Historical four-band short50→51 probes remain routing-only evidence.

The front OUT/IN control's center-click and later isolated8pxvertical-drag
methods produced zeroOUT. The later trial is
`unattended-20261028T145303Z-audiobaton-processing-rotary/first/Orion.pcapng`;
separate read-only reconciliation confirms unchanged staticGUI, and no inverse
gesture was sent. These negative methods do not establish unsupported hardware.

The functional vendor rack BP checkbox is captured separately in
`unattended-20261028T145303Z-audiobaton-rack-bp-processing`.
First frame3071 carries `0x14 / 0x98`, tuple@17..19 `00 45 00`; return
frame643 carries `00 45 01`. Actual instance17/type18/state19 addressing is
verified; the recorder rejects swapped addressing before any return gesture.
Native BP state goes Off→On→Off. Independent screenshot review correlates state0
with the front OUT/left pointer and state1 with IN/right pointer. All three checked
static panel segments and the BP widget return exactly; the green level meter
is excluded. This is GUI correlation, not audible polarity or independent readback.

MagicEyeBackground/left/right PeakMeter widget observations remain GUI-only;
independent meter counts, signal sources, scales and telemetry are unknown.
Slider/SliderMark widgets indicate parameters. See [the display inventory](orion-afx-displays.md).
Own temporary effect removal at frame649 in
`unattended-20261028T145303Z-remove-audiobaton/Orion.pcapng` restores all eight
AFX2 slots empty. The workflow marks the parameter/processing pass complete
without replaying old ranges. Direct front input method, runtime contracts,
physical interpolation, signal telemetry and audible/readback validation remain open.

## Compact preview frequency labels — owner clarification, 2026-10-28

The owner confirmed that high-frequency selector marks such as2/3/5/12/16
denote kilohertz. VEQ-1A and VMEQ-5 local presentation choices now include Hz
or kHz explicitly, including VMEQ-5's mixed-scale Dip Frequency choices
(200–700Hz followed by1–7kHz). These are display-label clarifications; the
original printed-label observations, raw selector keys, model-local encodings
and runtime verification flags remain unchanged. This does not establish an
audible frequency calibration or a continuous interpolation law.
