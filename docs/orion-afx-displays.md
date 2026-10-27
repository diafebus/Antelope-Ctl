# Orion AFX meters, indicators and screens

This inventory records observed GUI widgets separately from editable controls.
A completed control pass does **not** mean its meters or screens are decoded.
Class names, widget counts and screenshots establish presence, not protocol
offsets, signal source, physical scales, update rates or calibrated readings.
Overlapping parent/child widgets may represent the same display. Model-local
sources are recorded in the [catalog](../profiles/afx_effects.json).

| Effect | Observed native display classes |
|---|---|
| VEQ-4K ORANGE | `AfxLed` ×3; `SslPeakMeter` |
| VEQ-4K PINK | `AfxLed` ×3; `SslPeakMeter` |
| NEU-W495 | `AfxLed`; `NeumannPeakMeter` |
| NEU-W492 | `AfxLed`; `NeumannPeakMeter` |
| NEU-PEV | `AfxLed`; `NeumannPeakMeter` |
| BAE-1023 | `NevePeakMeter` |
| PowerGate | `AfxLed`; `PowerGateAttackDisplay`; `PowerGateDecayDisplay`; `PowerGateGainDisplay`; `PowerGateHoldDisplay`; `PowerGatePeakMeter`; `PowerGateRangeDisplay`; `PowerGateThresholdDisplay` |
| PowerEx | `PowerExBypassLed`; `PowerExDisplay` ×5; `PowerExPeakMeter`; `PowerExPeakMeterGrNoInheritance`; `RatioDisplay` |
| VEQ-1A | `AfxLed`; `PultecPeakMeter` |
| VMEQ-5 | `AfxLed`; `PultecPeakMeter` |
| VEQ-HLF | `AfxLed`; `PultecPeakMeter` |
| BA-31 | `AfxLed`; `Ba31PeakMeter` |
| Gyratec IX | `AfxLed`; `GyratecIXPeakMeter` |
| VPA 76 | `GainDisplay`; `TelefunkenFlashingPeakMeter` |
| V12 Chorus | `TurboEnsemblerPeakMeter` |
| Memory Cat Brigade | `MemoryBrigadeLED` ×2; `MemoryBrigadePeakMeter` |
| Instinct | `CircularPeakmeter` ×4 |
| ATuner | `ATunerFrequencyLabel`; `ATunerNoteLabel` ×8; `ATunerScreen`; `ATunerScreenBottomLabels`; `ATunerVUMeter` |
| BBD Chorus | `BBDChorusClipLed`; `BBDChorusGainReductionLed`; `BBDChorusLed` ×3; `BBDChorusPeakMeter`; `PeakLed` ×8 |
| Master De-Esser | `DeesserAttackDisplay`; `DeesserCtrlLed` ×4; `DeesserDisplay` ×3; `DeesserFreqDisplay`; `DeesserGRMeterNoInheritance`; `DeesserPeakMeterNoInheritance`; `DeesserQDisplay`; `DeesserRatioDisplay` |

## Deferred display work

The owner explicitly deferred reading ATuner’s screen. Its frequency, note and
cents/needle display is essential to a working tuner; capturing its power button
does not implement tuning. Native screen/meter/label widgets have been identified,
but their live readout and device telemetry source remain unverified.

For the remaining effects, identify which meters show input, output, gain
reduction, overload, modulation or another quantity before assigning semantics.
Preserve captured processing/mode LED observations separately from signal meters.
Animated displays are excluded from static control-image restoration checks.

Each further AFX capture must record visible meters, indicators and live displays
with its source image/native classes, and leave unknown telemetry and scales
explicit. No speculative device queries are authorized by this inventory.
