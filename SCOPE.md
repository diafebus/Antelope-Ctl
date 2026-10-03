# Project scope

`antelope-ctl` is an interoperability project documenting Antelope USB-HID
controls and implementing them in a Linux Python CLI and WebUI. This document
records contributor boundaries; [EULA-ANALYSIS.md](EULA-ANALYSIS.md) contains the
separate source summary of vendor terms.

## 1. What is in scope

- Control commands, state/meter/enumeration reports and in-band readbacks.
- Preamps, input/mixer/AFX links, routing, virtual mixers, output buses, clocking,
  sample rate, talkback, trim, brightness, oscillator and DC-coupling.
- Surround monitoring, including per-speaker EQ/Room Correction.
- Device-side mic modelling/emuMic. Its account-specific model catalogue stays
  separate from device profiles.
- Gazelle Reverb, the bundled effect called AuraVerb in protocol evidence.
- Device-side AFX controls within the boundaries in §4.

## 2. Reverse-engineering sources

Use observed USB traffic from hardware a contributor owns and facts from public
vendor documentation. Cite the source, version/page and capture evidence where
applicable. Public documentation provides facts, not text/tables/diagrams to copy.

Excluded sources are vendor software/firmware/source contents, disassembly or
decompilation, binary-derived strings/tables/constants, login-gated SDK/service/
partner materials, and licensing/activation/entitlement traffic.

Raw captures remain local under ignored `captures/`. Serial values, account data,
tokens and diagnostic dumps containing them stay out of tracked files. Profiles
describe identity layouts rather than values from an individual device.

## 3. Product/license distinction

Device-side Synergy Core Real-Time effects (AFX) are distinct from host-side
Native/Cosmos plugins. Native/Cosmos terms are not a proxy for the device-control
boundary. [EULA-ANALYSIS.md §4](EULA-ANALYSIS.md#4-what-the-public-sources-establish-about-afx-native-and-cosmos)
records the public product-format sources and what they do not establish about
particular device-bound terms. This scope does not make a legal-clearance claim.

Plugin DSP implementations, binaries and license/activation handling are excluded.

## 4. AFX / Synergy Core Real-Time controls

These categories separate device control from effect assignment and licensing:

| Bucket | Activity | Scope |
| --- | --- | --- |
| A | Signal routing | Device routing controls |
| B | Slot bypass/enable | Decode and expose when the command is verified |
| C | Reading slot/parameter state | Decode and display measured device state |
| D | Parameter controls on an effect available under its target-device license | Device control; independent of Native/Cosmos licensing |
| E | Assign/load/remove/reorder effects | Limited to the Orion captured-effect pilot below |
| F | Licensing/activation/entitlement traffic | Excluded from capture, implementation and replication |

A–D follow the same evidence and verification standards as other controls.
Undocumented writes stay disabled except for explicitly requested, captured,
bounded operator candidates. Availability/resource observations alone do not
establish a license or authorize a new write family.

### Orion captured-effect pilot

The owner requested a device rack using owned Orion captures, extending the
initial Preamp1/AFX1 test to all32 AFX channels. The captured load types are
Memory Cat Brigade, Instinct, Master De-Esser, V12 Chorus and demo BBD Chorus.
The pilot includes captured whole-chain add/replace/remove/reorder transactions
and paired linked edits with distinct measured instances.

Memory Cat parameters use the captured complete block; linked same-slot partner
sends are a bounded operator candidate. Other-effect parameter writers and
unmeasured loading paths/devices remain unsupported. Bounded reversible hardware
tests are authorized within these measured contracts.

The Orion profile's `runtime_contracts.afx_rack_test`,
`runtime_contracts.afx_memorycat_test` and `frame.afx_slot.instance_state_readback`
contain the exact instance/query ranges, verification rules and confirmation
status. [PROTOCOL.md §12a](PROTOCOL.md#12a-afx-real-time-chain-and-parameter-controls)
contains wire evidence; [the AFX workflow](docs/orion-afx-workflow.md) describes
implementation/capture passes. Generic raw opcode guards remain enabled.

## 5. Contributor agreement

Contributions must identify owned-device/public sources (§2) and fit the control
boundaries (§4). Contributors are responsible for terms they accepted when using
the Launcher; this project does not decide their application to USB observations.
Keep uncertainty explicit in evidence and confirmation status.
