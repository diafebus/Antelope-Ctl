# Orion AFX meters, indicators and screens

This inventory records observed GUI widgets separately from editable controls.
A completed control pass does **not** mean its meters or screens are decoded.
Class names, widget counts and screenshots establish presence, not protocol
offsets, signal source, physical scales, update rates or calibrated readings.
Overlapping parent/child widgets may represent the same display. Model-local
sources are recorded in the [catalog](../profiles/afx_effects.json).

| Effect | Observed native display classes |
|---|---|
| Audio / Baton | `AudioBatonMagicEyeBackground`; `AudioBatonPeakMeter_left`; `AudioBatonPeakMeter_right` |
| MG4+ | `Mg4BypassButton`; `Mg4PeakMeter` |
| VEQ-STU 089 | `AfxLed`; `Studer089Peakmeter` |
| VEQ-STU 169 | `AfxLed`; `Studer089Peakmeter` |
| VEQ-STU 900 | `Studer900Bypass`; `Studer900Peakmeter` |
| VEQ-4K BROWN | `AfxLed` ×3; `SslPeakMeter` |
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
| VCA160 | `Dbx160BelowLed`, `Dbx160AboveLed`, `Dbx160VuMeter`, `Dbx160Peakmeter`; POWER lamp within `Dbx160BypassButton` (processing GUI correlation only) |
| ALT-436C | `Altec436CVuMeter` (dB COMPRESSION face), `Altects436PeakMeter`, `AfxLed` (Power GUI association only) |
| Liverpool | `LiverpoolVuMeter` (GAIN REDUCTION face), `LiverpoolPeakMeter`, `AfxLed` (Mains Power GUI association only) |
| Stay-Levin | `StayLevinVuMeter` (dB COMPRESSION face), `StayLevinPeakMeter`, `AfxLed` (POWER lamp; signal telemetry unverified) |
| SMT-100A | `Summit100AVuMeter` (VU face), `Summit100APeakMeter`, `AfxLed` (POWER lamp; signal telemetry unverified) |
| X903 | `Dbx903GRPeakMeter` (GAIN REDUCTION row), `Dbx903PeakMeter` (LEVEL row), `Dbx903PeakMeterBackground` ×2, `AfxLed` (IN lamp; signal telemetry unverified) |
| FET-A78 | `UadVuMeter` (VU face), `UadPeakMeter`, `AfxLed` (POWER lamp; signal telemetry unverified) |
| FET-A76 | `UadVuMeter` (VU face), `UadPeakMeter`; embedded ON lamp in `Uad1176BypassButton` (signal telemetry unverified) |
| Impresser (partial controls) | `ImpresserGRMeter`; `PeakLed` ×16; `ClipLed`; `ImpresserLed` ×4; `OptoLed`; `DistortionLed` ×2; `RatioDisplay` (parameter readout) |
| Comp-4K-Bus | `Ssl4kBusVuMeter`; `Ssl4kBusPeakMeter`; embedded IN lamp in `Ssl4kBusBypassButton` (processing GUI correlation only; signal telemetry unverified) |
| NEU-473A | `U473APeakMeter`, `U473AGainReductionLedPeakMeter` with eight `PeakLed` segments, `U473ABypassLed`, `U473AGreenLed` and `U473ARedLed`. Signal telemetry remains unverified. |

Impresser's `OptoLed` does not return to its initial appearance after the
eight-label Ratio cycle: it is bright before raw3/4:1, dark after the full
captured parameter body and Ratio display return, and remains dark on a
read-only recheck. The exact difference occupies `(1024,402)–(1040,418)`.
`supervised-20261104T012645Z-impresser-ratio/reconciliation.json` preserves
the original static-check failure and source images; the lamp's meaning and
origin remain unresolved. No repair or replay was attempted. This indicator
discrepancy establishes no card-telemetry field or signal-meter contract.
See the [partial dynamics findings](orion-afx-power-dynamics.md#impresser--partial-control-capture-2026-11-04).

## Dedicated card-telemetry session

The owner reserved meter investigation for a separate session. The target is
live readings returned by the Orion card. Oscillator levels, control positions,
last-sent gain values and GUI animations are experimental references; none is
a substitute for device meter readback. Do not implement simulated meters or
derive displayed activity solely from the oscillator or parameter settings.

Use the [native oscillator/matrix capture procedure](orion-afx-workflow.md#dedicated-native-meter-session)
through an isolated AFX test path, without the official Launcher. Record routing,
measured frequency and level alongside native observations and passive card-to-host
HID reports; existing panel captures can supply reference labels. Establish
silence, then repeat measured level steps
and tone on/off transitions. Change one variable at a time to distinguish input,
output, gain reduction, overload and other meter sources. For special meters,
use relevant measured effect gain/dynamics controls, or a documented meter
gain/sensitivity control if present, to exercise the display. Record which gain
was changed; do not assume a meter has its own gain control.

For each candidate telemetry field, record source frames, byte/bit layout,
effect type/actual instance/channel correlation, raw readings and available
reference labels. Repeat across levels and independently changed instances/channels to
establish ownership. Use tone transitions to measure update rate, attack/release,
peak hold, clipping and silence behavior where observable. Derive any display
conversion from measured raw/label pairs and retain unverified regions as unknown;
do not impose a guessed meter curve.

Runtime meters require an established card-telemetry source and correlation
contract. Missing or stale readings must remain unknown/unavailable rather than
showing invented activity or a false zero. If passive captures do not reveal a
source, leave support pending and review existing startup/query evidence before
planning any bounded query trial. This plan does not authorize speculative
queries, index sweeps or competing HID actors. It schedules no automation and
starts no hardware trial; routing and trial changes must be verified and restored
within the eventual session's bounded plan.

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
