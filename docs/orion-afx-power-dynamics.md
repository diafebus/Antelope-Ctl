# Orion dynamics capture findings

These are directed vendor GUI observations on Orion Studio Synergy Core.
The [catalog](../profiles/afx_effects.json) owns model-local encodings, capture
hashes and confirmation status. Captured writes do not establish independent
readback or a runtime writer.

## PowerGate

The labelled vendor-menu load at frame2959 in
`unattended-20261025-load-powergate/Orion.pcapng` assigns type39/instance0 to
slot0 of channel1 (AFX2), with seven empty slots. The six visible knob targets
are `PowerGate*Pan` classes. `PowerGateBypassPot` is the processing lever and
must not be swept as a knob.

Parameter writes use `0x1d / 0xd5 / 0x0b`, type byte18 and instance byte19.
The first priming capture established that previously unrecognized message
family; it stopped with zero accepted phases and remains historical evidence.

| Control | Bytes | Captured raw endpoints | Displayed endpoints | Source frames |
|---|---|---|---|---|
| Threshold | 20 | 0, 120 | 0, 120 | A:8188/14706 |
| Attack | 22–23 | 1, 750; candidate uint16LE | 0.1, 75.0 | A:26074/30450 |
| Hold | 26–27 | 0, 5000; candidate uint16LE | 0, 5000 | B:11977/19833 |
| Range | 21 | 0, 20 | 0, 20 | B:34467/37713 |
| Decay | 24–25 | 1, 1000; candidate uint16LE | 1, 1000 | B:50073/54491 |
| Gain | 28 | 232, 12; candidate int8 −24, 12 | −24, 12 | B:67347/71085 |

A is `scan-PowerGate-20261025T093705223Z/PowerGate-channel2.pcapng`.
It accepted four phases for Threshold/Attack, then stopped on focus loss during
Hold. B is `scan-PowerGate-20261025T094022183Z/PowerGate-channel2.pcapng`.
Its reviewed remaining plan skipped those completed controls and accepted the
eight phases for Hold/Range/Decay/Gain. The combined twelve phases have stable
captured endpoint blocks; each minimum/maximum pair differs only in the listed
field. The complete original job is still a failed job. Knobs finish at maximum
as authorized.

The processing lever sends `0x14 / 0x98`, instance17/type18/state19.
`unattended-20261025-powergate-lever-first/Orion.pcapng` frame2685 carries
`00 27 00`; the return capture frame1557 carries `00 27 01`. Lever and LED
RGB pixels match the initial image exactly after the pointer is moved away,
and all six displayed knob values are unchanged. Independent processing-state
readback, polarity and audible confirmation remain unverified.

This completes the observed six knobs and processing lever. No preset selector
was observed on this panel. Endpoint displays alone do not prove physical units,
intermediate-value laws, full wire ranges or signedness away from those endpoints.
Runtime parameter/loading/bypass contracts remain disabled or unconfirmed.

## PowerEx

The labelled vendor-menu load at frame4473 in
`unattended-20261025-load-powerex/Orion.pcapng` assigns type51/instance0 to
channel1 slot0, with seven empty slots. This independently establishes Orion
identity without inheriting the sibling-device type ID.

The inspected panel exposes six distinct `Pan` knob targets: Threshold, Range,
Attack, Decay, Ratio and Gain. Native launcher job
`scan-PowerEx-20261025T094607276Z/PowerEx-channel2.pcapng` accepted all twelve
knob phases in one batch, with 110,974 packets and zero drops. Parameter writes
use `0x1d / 0xd5 / 0x0b`, type51/instance0. Each endpoint pair changes only its
listed field; runtime writers remain disabled.

| Control | Bytes | Captured raw endpoints | Displayed endpoints | Source frames |
|---|---|---|---|---|
| Threshold | 20 | 0, 80 | 0, 80 | 4505/13811 |
| Range | 21 | 0, 80 | 0, 80 | 22719/32787 |
| Attack | 22–23 | 1, 750; candidate uint16LE | 1, 750 | 43605/52491 |
| Decay | 24–25 | 1, 1000; candidate uint16LE | 1, 1000 | 60135/68143 |
| Ratio | 26–27 | 100, 2000; candidate uint16LE | 1.0, 20.0 | 76575/85097 |
| Gain | 28 | 232, 12; candidate int8 −24, 12 | −24, 12 | 93375/103399 |

PowerEx's Attack display differs from PowerGate's despite matching raw endpoints;
do not transfer physical scaling between effects. The endpoint evidence alone
does not establish intermediate-value laws, units or full signed wire ranges.

The separate processing-switch trial uses `0x14 / 0x98`, instance17/type18/state19.
First-click frame2627 in `unattended-20261025-powerex-switch-first/Orion.pcapng`
carries `00 33 00`; return frame1889 carries `00 33 01`. Switch and LED RGB
pixels match the baseline exactly after moving the pointer away, with endpoint
displays unchanged. Polarity, independent readback and audible confirmation are
unverified. This completes the six observed knobs and processing switch; no
preset selector was observed on this panel.


## VCA160 — visible control pass, 2026-10-28

`unattended-20261028T145303Z-load-vca160/Orion.pcapng` frame1535 establishes
Orion type33/instance0, independently of another model's IDs. The native panel
is `Dbx160`. `scan-Dbx160-20261028T152511931Z/Dbx160-channel2.pcapng`
accepts all six phases,49,456 packets with zero drops. Parameter family is
`0x17 / 0xd5 / 0x05`, type byte18/instance byte19. Each phase changes only
its own one-byte field; minimum/maximum screenshots independently associate
these printed endpoints:

| Control | Byte | Raw candidates | Printed endpoints | Frames |
|---|---|---|---|---|
| Threshold (dB) | 20 | 0/100 | −50 / 0 | 4567/12151 |
| Compression | 21 | 0/60 | 1 / ∞ | 20731/27917 |
| Output Gain | 22 | 0/100 | −20 / +20 | 36669/44667 |

Only Threshold explicitly prints(dB) in this inventory. Printed endpoint
associations do not establish an intermediate scale, calibrated gain response,
audible behavior or a complete finite map from raw quantization. The priming
source `unattended-20261028T145303Z-vca160-priming` contains frames2247/2295,
body `32 15 3a`→`32 15 3b`, with onlybyte22 changing after the first block;
preservation before that first report is not established. Range scans end at maxima.

A separate labelled POWER round trip is preserved in
`unattended-20261028T145303Z-vca160-processing`. First frame2911 carries
`0x14 / 0x98`, actual instance17/type18/state19 tuple `00 21 00`; return
frame679 carries `00 21 01`. Native rack BP goes Off→On→Off; the POWER lamp
is lit→dark→lit. All five checked static regions, including knobs, POWER lamp
and rack BP, restore exactly. Below/Above LEDs, VU and peak meters are excluded.
This is GUI correlation without an audible polarity or independent readback claim.

`Dbx160BelowLed`, `Dbx160AboveLed`, `Dbx160VuMeter`, `Dbx160Peakmeter` and
the POWER lamp inside `Dbx160BypassButton` are GUI observations. Signal sources,
scales and telemetry remain unverified. Own trial removal frame693 in
`unattended-20261028T145303Z-remove-vca160/Orion.pcapng` restores eight empty
AFX2 slots. Runtime commands remain null; no writer or query bound is expanded.


## ALT-436C — visible control pass, 2026-10-28

Directed vendor load frame1553 in
`unattended-20261028T145303Z-load-altec436c/Orion.pcapng` establishes Orion
type35/instance0. Native panel `Altec436C` has four parameter knobs and a
separate POWER rotary. Individual native-container overflow allowances are
measured: Input0, Threshold14, Release14, Output7 pixels. Starting areas and
pointer paths remain within the physical panel; entire native bounds remain
inside the AFX window. The geometry/method received read-only planner review.

`scan-Altec436C-20261028T154214904Z/Altec436C-channel2.pcapng` accepts eight
isolated phases with62,804packets and zero drops. Parameter family is
`0x19 / 0xd5 / 0x07`, type byte18/instance byte19.

| Control | Byte | Raw candidates | Printed endpoints | Frames |
|---|---|---|---|---|
| VOLUME (`input`) | 20 | 0/100 | 0 / 10 | 4647/11425 |
| Threshold | 21 | 0/100 | 0 / +16 | 19691/26285 |
| Release Time | 22 | 0/100 | .3 / 1.3 | 35161/42035 |
| Output (dB) | 23 | 232/24 | −24 / +24 | 50973/57787 |

Endpoint pointers and printed labels were independently checked. Release shows
40distinct raw values; its three printed marks(.3/.8/1.3) do not establish a
three-state selector. Intermediate scales and unprinted units remain unknown.
Output retains unsigned wire232/24 with signed candidates−24/+24; no complete
signed/interpolation law or calibrated audible gain is claimed. Byte24 stays0
throughout captured parameter reports and remains unidentified, without adopting
another model's linked-field semantics. Scans end at maxima.

The earlier8pxOutput priming frame2201 in
`unattended-20261028T145303Z-altec436c-priming/Orion.pcapng` has body
`1b 45 00 01 00`; there is no preceding captured parameter baseline.
A later bounded8pxdownward POWER gesture produces zeroOUT and checked staticGUI
remains exact in a separate read-only reconciliation. No inverse gesture is sent.
Its source is `unattended-20261028T145303Z-altec436c-power-rotary/first/Orion.pcapng`.

The functional rack BP round trip is separately preserved in
`unattended-20261028T145303Z-altec436c-rack-bp-processing`: first frame3136,
actual instance17/type18/state19 tuple `00 23 00`; return frame729,
`00 23 01`, family `0x14 / 0x98`. Native BP goes Off→On→Off. Independent
images correlate state1 with red lamp lit/POWER pointer up and state0 with
lamp dark/pointer right. POWER has no printed ON/OFF position labels; these
are literal GUI associations. All five checked physical control/lamp/BP regions
restore exactly. Active VU upper area and the four-pixel peak strip are excluded.
No audible polarity or independent changed-state device readback is established.

Displays: `Altec436CVuMeter` (face caption dB COMPRESSION),
`Altects436PeakMeter` (native spelling preserved) and `AfxLed` (Power GUI
correlation). Signal telemetry/scales remain unknown. Own trial removal frame679
in `unattended-20261028T145303Z-remove-altec436c/Orion.pcapng` restores eight
empty AFX2 slots. Runtime commands remain null and query bounds unchanged.


## Liverpool — visible control pass, 2026-10-29

Directed load frame1581 in `unattended-20261028T145303Z-load-liverpool/Orion.pcapng`
establishes Orion type31/instance0. Native panel `Liverpool` exposes Input,
Threshold, Attack, Recovery, Output Attenuator(dB), labelled Mains Power and
its red lamp. `scan-Liverpool-20261028T161230170Z/Liverpool-channel2.pcapng`
accepts ten endpoint phases with 78,704 packets and zero drops. Parameter family
is `0x1a / 0xd5 / 0x08`, type18/instance19.

| Control | Byte | Raw endpoint candidates | Source frames |
|---|---|---|---|
| Input | 20 | 0/100 | 4741/11535 |
| Threshold | 21 | 0/100 | 19847/26669 |
| Attack selector | 22 | 0/10 | 34733/41763 |
| Recovery selector | 23 | 0/10 | 50401/57613 |
| Output selector | 24 | 0/5 | 66103/73607 |

Input and Threshold pointers match printed 0/10; no unit or intermediate law is
established. Byte 25 remains0/unidentified. The first short Output gesture had
zeroOUT and exact nonmeter GUI on separate reconciliation; no inverse sent.
The later Input probe frames 1601/1651 established the family with body
`23 32 05 00 02 00`→`24 32 05 00 02 00`; no preceding parameter baseline exists.

The separate first-change KVM mapping in
`unattended-20261028T145303Z-liverpool-selector-maps` records every state with
an image and source frame. Fifty directed changes and six quiet terminal
witnesses cover all three selectors; each returns the complete captured body
and checked static panel. All raw/image associations were independently reviewed.

| Raw | Attack printed mark | Recovery printed mark |
|---|---|---|
| 0 | 1 (FAST end) | 1 (FAST end) |
| 1 | C between1–2 | H between1–2 |
| 2 | 2 | 2 |
| 3 | C between2–3 | H between2–3 |
| 4 | 3 | 3 |
| 5 | C between3–4 | H between3–4 |
| 6 | 4 | 4 |
| 7 | C between4–5 | H between4–5 |
| 8 | 5 | 5 |
| 9 | C between5–6 | H between5–6 |
| 10 | 6 (SLOW end) | 6 (SLOW end) |

The printed legends are COMP OFF and HOLD. All five C/H raw states stay distinct;
no numeric timing or audible equivalence is inferred. Output raw 0–5 maps to
**30,20,15,10,5,0**, under explicit OUTPUT ATTENUATOR(dB). These are positive
printed attenuation labels; do not turn this selector into continuous signed gain.

The final Mains Power round trip is in
`unattended-20261028T230645Z-liverpool-processing`. First frame 7413 carries
`0x14 / 0x98`, actual instance17/type18/state 19 tuple `00 1f 00`; return 625
carries `00 1f 01`. State 0 is switch DOWN/OFF, lamp dark and native BP On;
state 1 is UP/ON, lamp lit and BP Off. All five checked static regions return
exactly. The VU and four-pixel peak meter are excluded. This is GUI correlation,
not audible polarity or independent changed-state device readback.

`LiverpoolVuMeter` has the visible GAIN REDUCTION caption; `LiverpoolPeakMeter`
and the Power lamp `AfxLed` are also inventoried. Signal telemetry/scales remain
unverified. Own trial removal frame1139 in
`unattended-20261028T230645Z-remove-liverpool/Orion.pcapng` restores all eight
AFX2 slots empty. Owner requested pause; no further effects started. Runtime
commands remain null; no writer or query bound is expanded.

## Stay-Levin — visible control pass, 2026-11-03

Directed menu load in `unattended-20261103T144909Z-load-staylevin/Orion.pcapng`
frame1083 establishes Orion type34/instance0 on empty, unlinked AFX2 slot0.
Native panel `StayLevin` exposes Input, Output, Recovery Time, Mode and Power.
The three-knob job `scan-StayLevin-20261103T145457652Z/StayLevin-channel2.pcapng`
accepts six phases,80,036 packets with zero drops. Parameter family is
`0x18 / 0xd5 / 0x06`, type byte18/instance byte19. Every accepted endpoint
phase changes only its mapped byte:

| Control | Byte | Raw endpoints | Printed endpoints | Frames |
|---|---|---|---|---|
| Input | 20 | 0 / 100 | 0 / 20 | 9091 / 23713 |
| Output | 21 | 0 / 100 | 0 / 20 | 68315 / 75661 |
| Recovery Time | 22 | 0 / 4 | SLOW / FAST | 41001 / 56841 |

`unattended-20261103T144909Z-staylevin-recovery-map2` captures eight adjacent
changes,4→3→2→1→0→1→2→3→4, with one isolated byte22 write per trial.
Raw0 is the leftmost SLOW dot; raw4 is the rightmost FAST dot. Raw1/2/3 point
to the unlabelled upper-left/top/upper-right dots. Their timing meanings remain
unknown; positional evidence supplies neither numerical times nor usable named
timing choices. The complete captured parameter body and three checked static
panel regions returned exactly. An earlier8px gesture produced no OUT; a local
aggregation import failure was reconciled offline without replaying gestures.

The printed MODE switch maps byte23 raw0 to lower DOUBLE and raw1 to upper
SINGLE. First frame3081 in `unattended-20261103T144909Z-staylevin-mode-first2`
and return frame709 in `unattended-20261103T144909Z-staylevin-mode-return`
change only byte23 and restore the complete captured parameter body/static
regions. Compatibility ID `attack` is retained; these mode labels do not
establish attack-time semantics. The initial focus rejection occurred before
control input and is retained separately.

Power uses `0x14 / 0x98`, instance17/type18/state19. In
`unattended-20261103T144909Z-staylevin-processing`, first frame2869 carries
`00 22 00` (OFF/lamp dark), return frame679 carries `00 22 01` (ON/lamp lit).
Three static regions returned exactly; the VU and peak displays were excluded.
Independent changed-state readback and audible polarity remain unverified.
Removal frame739 in `unattended-20261103T144909Z-remove-staylevin` restores
all eight AFX2 slots to empty. The owner's AFX1 V12 Chorus was preserved.

The visible control pass is complete, with the three intermediate Recovery
contacts' timing meanings explicitly pending. Printed gain marks do not prove
calibration or interpolation. `StayLevinVuMeter` (dB COMPRESSION face),
`StayLevinPeakMeter` and `AfxLed` record GUI presence/correlation separately
from signal telemetry. No runtime writer, query bound or readback contract is
expanded. No restart/power-cycle retention or audible/stereo behavior is claimed.

## SMT-100A — visible control pass, 2026-11-03

Directed load frame729 in `unattended-20261103T144909Z-load-smt100a`
assigns Orion type36/instance0 to empty, unlinked AFX2 slot0. Native panel
`Summit100A` prints GAIN and GAIN REDUCTION on the two knobs; compatibility
IDs/classes `output`/`Summit100AOutputPot` and `input`/`Summit100AInputPot`
remain unchanged. The four-phase job `scan-Summit100A-20261103T150522388Z`
records30,382 packets with zero drops. Parameter family is
`0x18 / 0xd5 / 0x06`, type byte18/instance byte19.

| Control | Byte | Raw endpoints | Printed endpoints | Frames |
|---|---|---|---|---|
| Gain (`output`) | 20 | 0 / 100 | 0 / 10 | 4659 / 11083 |
| Gain Reduction (`input`) | 23 | 0 / 100 | 0 / 10 | 19430 / 26252 |

ATTACK byte21 and RELEASE byte22 each have three observed contacts:
raw0 right/SLOW, raw1 center/unlabelled, raw2 left/FAST. The center meanings
remain unknown; neither Medium/Auto labels nor numerical times are inferred.
A read-only hover over centered Attack produced no tooltip in its retained image.

Attack started at raw1. Its first isolated click emitted raw2 at frame2959 in
`unattended-20261103T144909Z-smt100a-attack/first`; the binary expectation
stopped the helper before any return. After image/raw review, the next directed
click emitted raw0 at frame779 in `...-smt100a-attack-next`, and the final
click restored raw1 at frame797 in `...-smt100a-attack-return`. Release started
at raw2 and cycled0→1→2 at frames1473/4289/7113 in
`unattended-20261103T144909Z-smt100a-release-cycle`. Each isolated action
changes only its selector byte. Both cycles return the whole captured parameter
body and five checked static regions; the VU/peak displays are excluded.

Power `0x14 / 0x98` uses instance17/type18/state19. In
`unattended-20261103T144909Z-smt100a-processing`, first frame3011 carries
`00 24 00`: switch right, away from ON, lamp dark. Return frame769 carries
`00 24 01`: switch left at ON, lamp lit. Five static regions returned exactly.
No unprinted OFF label, independent changed-state readback or audible polarity
is claimed. Removal frame783 in `unattended-20261103T144909Z-remove-smt100a`
verifies all eight AFX2 slots empty; the owner's AFX1 V12 Chorus was preserved.

This completes visible-control capture with both centered timing meanings
explicitly pending. `Summit100AVuMeter` (VU face), `Summit100APeakMeter` and
`AfxLed` remain separate GUI observations. Printed knob scales do not establish
calibrated units/interpolation, timing, telemetry, independent readback,
audible/stereo behavior or runtime contracts. No query bound or writer is expanded.

## X903 — visible control pass, 2026-11-03

Directed load frame889 in `unattended-20261103T144909Z-load-x903` establishes
Orion type29/instance0 in empty, unlinked AFX2 slot0. Native panel `Dbx903`
has Threshold, Ratio, Output and IN. Six accepted endpoint phases in
`scan-Dbx903-20261103T151417999Z/Dbx903-channel2.pcapng` record45,462 packets
with zero drops. Parameter family is `0x17 / 0xd5 / 0x05`, type byte18/instance
byte19; every accepted phase changes only its mapped field.

| Control | Byte | Raw endpoints | Printed endpoints | Frames |
|---|---|---|---|---|
| Threshold | 20 | 0 / 100 | −60 dB / 0 dB | 4151 / 10703 |
| Ratio | 21 | 0 / 60 | 1:1 / −1:1 | 18599 / 25349 |
| Output | 22 | 0 / 100 | −20 dB / +20 dB | 33915 / 40919 |

Ratio's negative endpoint is the literal printed label. Do not transfer VCA160's
compression law despite matching raw endpoints/family, or infer intermediate
ratios, gain calibration or signed arithmetic from these captures.

IN `0x14 / 0x98` uses instance17/type18/state19. In
`unattended-20261103T144909Z-x903-processing`, first frame3065 carries
`00 1d 00` with IN lamp dark; return frame705 carries `00 1d 01` with lamp lit.
Four static regions returned exactly, excluding both animated meter rows.
The separate native inventory identifies `Dbx903GRPeakMeter` (GAIN REDUCTION),
`Dbx903PeakMeter` (LEVEL), two overlapping `Dbx903PeakMeterBackground` widgets
and `AfxLed`. Their signal telemetry is unverified. The sole test insert was
removed afterward with all eight AFX2 slots verified empty; owner AFX1 V12 was
preserved. Independent state readback, physical/intermediate scales, audible
processing polarity, stereo behavior and runtime contracts remain unverified.
No writer or query bound is expanded.
