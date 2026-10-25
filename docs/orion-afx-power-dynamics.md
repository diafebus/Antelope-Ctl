# Orion PowerGate and PowerEx capture findings

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
knob phases in one batch, with110974 packets and zero drops. Parameter writes
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
