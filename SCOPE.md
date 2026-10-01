# SCOPE.md -- what this project does, and the lines it will not cross

`antelope-ctl` is an **interoperability** project: a clean-room-style
reverse-engineering of the USB-HID *control protocol* of Antelope audio
interfaces, and a stdlib-only tool that speaks it, so the hardware can be
controlled on Linux (and, later, from a community web UI).

This document is **project scope**, agreed by contributors. It is not
legal advice and does not decide whether any particular use is lawful.

**Naming convention:** application-facing UI and software use **Gazelle
Reverb**. **AuraVerb** is retained for the device's original feature name in
protocol findings, captures, and other research evidence. Internal
wire-compatible identifiers are not renamed casually.

---

## 1. What is in scope

- The **control protocol** on the vendor HID interface: command frames,
  the state/meter/enumeration reports, the in-band readback protocol.
- **Preamps** (gain, mode, phantom, phase), **channel/ADAT/S-PDIF link**,
  the **routing matrix**, the **virtual mixer**, **output buses**
  (monitor / headphone / line / reamp), **clocking / sample rate**,
  **talkback**, **output trim**, **screen brightness**, the **oscillator**
  / test-tone generator, **DC-coupling**, the **surround monitoring** tab.
- **Mic modelling / emuMic** device-side DSP control (enable / model id /
  polar pattern / capsule swap). The *model catalogue* is account-bound
  and lives in a separate data file, not in the device profile.
- **Gazelle Reverb** -- the one bundled effect (called AuraVerb in the
  hardware/protocol evidence; ships with the device, **no per-plugin
  activation**). Decoding and exposing its parameters is in scope; it was
  the deliberate safe pilot for effect-frame shape.

## 2. Reverse-engineering sources -- what is allowed

**Allowed:**

- **Observed USB traffic** to and from hardware a contributor **owns**.
  This is the whole basis of the project.
- **Publicly published Antelope documentation** -- user manuals, spec
  sheets, block / signal-flow diagrams from Antelope's own public download
  pages. Extract **facts only** (channel counts, feature names, signal
  flow, parameter ranges). Cite the document + version + page in the
  `evidence` field. **Never** paste manual text, tables, or diagrams into
  the repo.

**Not allowed, ever:**

- Antelope **software, firmware, or source** -- no disassembly, no
  decompilation, no lifting strings/tables/constants out of their
  binaries.
- Anything **behind their login** -- SDKs, service manuals, developer
  docs, partner materials.
- Capturing, committing, or analysing-for-replication any **licensing /
  activation / entitlement** traffic (see §4, bucket F).

**Captures are never committed.** `captures/` is gitignored. Diagnostic
tool output that can contain a device serial is gitignored
(`tools/*_out.txt`). A **device serial never enters a tracked file** --
profiles describe the *layout* of the identity record, never a value.

## 3. License boundary

Do not treat Native or Cosmos terms as the license for device-side AFX
controls. Antelope describes **Synergy Core Real-Time** effects as running
on a supported device's DSP/FPGA, with a Real-Time license assigned to the
device through Antelope Launcher. **Native** plugins run on the computer in
a DAW and use iLok; a **Cosmos** membership grants access to Native versions
and does not grant Real-Time versions. A purchase may include both formats,
but their execution and activation paths are distinct. Sources and limits
of this summary are recorded in `EULA-ANALYSIS.md`.

The Cosmos EULA describes the Cosmos bundle's computer programs. This
project has no basis to apply it automatically to device-side AFX
parameter control. The exact terms governing a Real-Time license assigned
to a particular device have not been established here. The general EULA's
application to a contributor's Launcher use is also a separate question.
This document sets project scope; it is not a legal ruling or a claim that
any method is legally cleared.

---

## 4. AFX / Synergy Core Real-Time controls

Here, **AFX** means device-side Synergy Core Real-Time effects assigned to
and processed by a supported interface. This is distinct from **Native**
plugins, which run on the computer in a DAW, and **Cosmos**, which provides
access to Native plugins. A Cosmos membership does not provide the
device-side Real-Time license. See `EULA-ANALYSIS.md` for the official
product-format source and the limits of what is known about applicable
terms.

Controlling a parameter on an AFX Real-Time effect that is already
available under a license assigned to the target device is in scope as
device control, like changing a preamp setting. The project may observe,
document, and implement those parameter controls using captures from
hardware the contributor owns. This scope does not include reproducing the
effect's DSP implementation or handling its license, entitlement, or
activation.

The **Gazelle Reverb** (AuraVerb in protocol evidence; §1) and the
**surround per-speaker EQ / Room Correction** remain in scope as device
features. Their existing status does not determine the status of licensed
AFX effects, and neither should be conflated with Native or Cosmos plugins.

Every AFX-related frame is classified into one of these buckets **before**
it is ever sent, decoded-for-replication, or documented:

| bucket | example | stance |
|---|---|---|
| **A. Signal routing** | routing an `afx_in` destination; source bank `0x05` (`afx_out`) | **In scope.** It is just the crosspoint matrix (`0x53`), nothing plugin-specific. |
| **B. Slot bypass / enable** | a per-slot on/off (mixer-level, like AuraVerb's enable bit) | **OK to decode + expose.** It is a mute, not the plugin. |
| **C. Reading slot state** | "slot N is occupied", "slot N is bypassed" | **OK to decode + display.** Observation only. |
| **D. AFX Real-Time parameter control** | "set slot-N decay = 40" on an effect already available under a license assigned to the target device | **In scope.** Observe and implement the device control. Do not load an effect or interact with its license/activation state. Native/Cosmos licensing is not a prerequisite or proxy for this work. |
| **E. Assign / load / remove an effect** | "put Auto-Tune in slot 3" | **Generally out of scope.** The Orion captured-effect pilot below is an explicit, bounded exception. |
| **F. Licensing / activation / entitlement traffic** | the activation handshake, license tokens, entitlement checks | **OFF-LIMITS.** Never sent, never decoded for replication, never captured into any repo. |

**This repo (`antelope-ctl`) may contain buckets A through D.** D remains
subject to the same evidence, hardware ownership, and safe-write standards
as other device controls. F remains outside project scope. E is limited to
the explicitly requested pilot below.

An undocumented or unverified frame stays **unsent** until its meaning and
write behavior are established, except for the captured, explicitly
operator-driven pilot tests described below. A frame is not out of scope merely because
it controls a licensed AFX effect.

### Orion captured-effect pilot

The owner explicitly requested a WebUI that loads and reorders Memory Cat
Brigade and provided owned-device captures on 2026-09-30. This extends scope
to observing the submitted load/remove/reorder sequences and implementing
operator-driven tests on Orion insert channel index 0
(the owner's Preamp 1 test). On 2026-10-01 the owner requested effect selectors. This extends the same
verified chain path to the five independently captured Orion load types:
Memory Cat, Instinct, Master De-Esser, V12 Chorus and BBD-Chorus. The owner
further requested loading on channels other than AFX 1, extending these
bounded operator tests to Orion channels 0–31. Channel-specific fresh reads
and post-write verification remain mandatory. Other loading paths remain
excluded. The owner also authorized bounded, reversible hardware tests to
resolve the required protocol mappings; this does not authorize unsafe
readback indices or licensing/activation traffic.

Typed test builders use the captured complete eight-slot chain, preserve
other effects, allocate only measured instance indices, and start from
fresh bounded device readbacks. Slot mutations verify their resulting
readback and stop further testing if verification fails. Generic raw AFX
opcode guards stay enabled. Parameter tests initialize with an explicit
complete settings Apply, then permit throttled live edits from last-sent
settings; they do not claim parameter readback or automatic restoration.
Stereo parameter sharing, other effects' parameter writes, unmeasured load
types, and other devices remain unsupported by this pilot. No licensing or
activation traffic is handled.

---

## 5. What this repo will never contain

- Plugin DSP implementation, binaries, or source code.
- Licensing/activation traffic (bucket F), or loading implementations outside
  the explicitly requested Orion captured-effect pilot. Owner-submitted Orion
  chain captures may be observed without enabling those effects' writes.
- Anything derived from Antelope's software, firmware, or login-gated
  materials.
- A device serial, in any tracked file.

---

## 6. Contributor agreement

By contributing you confirm that:

1. Every device capture you submit is from **hardware you own**, taken by
   observing its USB traffic -- not from Antelope's software, firmware, or
   any login-gated material.
2. You have classified every AFX-related frame per §4 and submitted
   nothing from bucket F or from E outside the Orion pilot to this repo. Bucket D work controls only an
   effect already available under a license assigned to the target device.
3. You are responsible for the Antelope terms presented to and accepted
   by you when using the Launcher. This project does not determine how
   those terms apply to your contribution or to USB device control.
4. You have not pasted copyrighted manual/UI text or Antelope binary
   contents into your contribution.

Raise anything uncertain in an issue **before** committing it.
