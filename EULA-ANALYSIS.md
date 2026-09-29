# EULA analysis -- Antelope Audio license terms vs. this project

This is a limited source summary, not a legal opinion or a determination
that any particular method is lawful. It distinguishes device-side AFX
Real-Time effects from host-side Native/Cosmos plugins; the Cosmos EULA
must not be used as a proxy for the terms covering device-side AFX control.
Sources are Antelope's **own publicly published** pages:

- General EULA -- <https://en.antelopeaudio.com/legal-terms/eula/>
- Cosmos plug-in EULA -- <https://en.antelopeaudio.com/legal-terms/antelope-cosmos-eula/>
  (version stated on the page: **1.12.2023**)
- Software effects ecosystem guide -- <https://support.antelopeaudio.com/en/support/solutions/articles/42000104538-understanding-the-antelope-audio-s-software-effects-ecosystem>

Checked 2026-09-30. Quotes below are from the EULA pages as retrieved on
that date; verify current terms and the agreement presented to a user before
relying on them.

**This is not legal advice.** The project scope for device-side parameter
control is in `SCOPE.md` §4. That scope is not a legal clearance, and the
Cosmos EULA is not the basis for it.

---

## 1. The clauses that matter

### General EULA -- "LIMITATIONS AND RESTRICTIONS"

> Licensee shall not: (i) transfer, lease, sub license, distribute or
> assign its rights to any other person or entity, without prior written
> approval of the Company; **(ii) decompile, disassemble or
> reverse-engineer the Software; (iii) modify, adapt or create derivatives
> of the Software; combine or merge any part of the Software with or into
> any other software; (iv) otherwise use the Software as part of any
> effort to develop software having any functional attributes, visual
> expressions, or other features similar to those of the Software;**
> (v) use Software that is licensed for a specific device, whether
> physical or virtual, on another device, unless expressly authorized by
> the Company in writing (vi) remove, modify or conceal any Software
> identification, copyright, proprietary, intellectual property notices or
> other marks on or within the Software; (vii) make copies of the Software
> unless reasonably necessary for back-up, archiver or disaster recovery
> purposes.

### General EULA -- "LICENSE" (grant)

> Subject to compliance with this Agreement, and provided that Licensee
> has only acquired the Software directly from the Company or an
> Authorized Dealer, Antelope Audio grants Licensee a limited,
> non-exclusive, non-transferable license to Use the Software solely for
> Licensee's internal business operations.

### General EULA -- definitions

> **"Software"**: computer programs and any Upgrades, including any and all
> third party-licensed software incorporated therein
>
> **"Use" / "Using"**: to download, install, activate, access or otherwise
> use the Software

### General EULA -- "PROPRIETARY RIGHTS"

> Antelope Audio is and remains the sole and exclusive owner ... The
> Software is licensed, not sold. No title, intellectual property rights
> or ownership rights to the Software are transferred to the Licensee.

### General EULA -- "GENERAL REGULATIONS -- Governing Law. Dispute Resolution."

> This Agreement shall be governed by and construed in accordance with the
> laws of the Republic of Bulgaria. Any dispute ... shall be referred to
> the Arbitration Court of the Bulgarian Chamber of Commerce and Industry

### Cosmos plug-in EULA

Same (ii) reverse-engineer / (iii) modify-or-combine / (iv)
develop-similar-software restrictions. Differences:

> This Agreement shall be governed by and construed in accordance with the
> laws of the State of Michigan, USA

> The License gives you the right to use it on two concurrent activation
> locations (iLok USB Hardware Dongle or iLok Cloud)

Subscription / membership model, iLok-based activation.

Its definition of "Software" is limited to the computer programs included
in the Antelope Cosmos plugin bundles. The EULA is therefore not used here
as a stand-in for terms governing device-side AFX Real-Time control.

---

## 2. Who these terms bind

The EULAs describe a **Licensee** who accepts the relevant agreement and
uses the software covered by it. The general EULA defines use to include
downloading, installing, activating, accessing, or otherwise using its
"Software". This text alone does not identify every program or device
feature covered by a contributor's particular Launcher flow.

The Cosmos EULA defines its Software specifically as computer programs in
the Antelope Cosmos plug-in bundles. It therefore describes the Cosmos
Native product path; it is not evidence that a device-side AFX Real-Time
parameter command is Cosmos plugin use. The public ecosystem guide
describes Real-Time effects as running on device DSP/FPGA and their license
as assigned to a supported device through Launcher. The separate agreement
or terms applicable to that device entitlement have not been identified
here.

Contributors remain responsible for the terms they personally accept when
using Antelope software. This memo does not determine who is bound by which
agreement, or whether a particular USB capture or control method complies
with it.

---

## 3. Technical boundaries used by this project

| clause | project posture |
|---|---|
| (ii) reverse-engineer the Software | The project does not decompile, disassemble, or inspect Antelope binaries/firmware. It observes USB control traffic between an app and hardware a contributor owns. This describes the method; it does not decide how a particular agreement applies to it. `SCOPE.md` §2 records the project rule. |
| (iii) modify / combine / merge with other software | `antelope-ctl` contains **no Antelope code** -- not a line, not a table, not a constant. Nothing is combined or merged. |
| (iv) develop software with similar functional attributes | `antelope-ctl` controls the same hardware, so this clause is relevant to the project. This memo does not decide its scope or enforceability. |
| (v) device-bound Software on another device | The general EULA includes a restriction on using software licensed for one device on another. This project does not transfer a device license; AFX bucket D (see `SCOPE.md`) concerns control of an effect already available on the target device. The clause's application to that control is not determined here. |
| (vi) remove/conceal notices | N/A -- no Antelope Software is redistributed. |
| (vii) copying | N/A. Captures are never committed (`SCOPE.md` §2). |

---

## 4. What the public sources establish about AFX, Native, and Cosmos

Antelope's [software effects ecosystem guide](https://support.antelopeaudio.com/en/support/solutions/articles/42000104538-understanding-the-antelope-audio-s-software-effects-ecosystem)
distinguishes these formats:

| Format | Where it runs | License/activation path described by Antelope |
|---|---|---|
| Synergy Core Real-Time (AFX in this project) | FPGA/DSP inside a supported device | A Real-Time license is assigned to the device through Launcher; no iLok is required. |
| Synergy Core Native | Computer, loaded in a DAW | iLok authorization; does not require Antelope hardware. |
| Antelope Cosmos | Membership access to Native plugins | Cosmos membership provides Native versions; it does not provide Synergy Core Real-Time licenses. |

The guide establishes a product and activation distinction. It does not
identify the full agreement applicable to a particular device-bound
Real-Time license, nor decide the legal status of observing or controlling
that device over USB. The Cosmos EULA's Michigan governing-law clause
applies to that agreement; it is not a sound basis for assigning Michigan
law to AFX Real-Time parameter control. The general EULA states Bulgarian
law, but this memo does not determine which software or conduct it governs.

The EU Software Directive and court decisions may be relevant to a legal
analysis, but this document does not predict enforceability, litigation
outcomes, enforcement likelihood, or the result under any jurisdiction.
Those questions are outside this source summary.

---

## 5. Open documentation questions

- [ ] Identify and archive the product or device terms presented for the
      particular AFX Real-Time license/device, if available to the owner.
- [ ] Record which public terms a contributor accepted when using Launcher
      for a capture. Do not assume the Cosmos EULA applies to that capture.
- [ ] Keep protocol work limited to device control on hardware the
      contributor owns and to effects already available under a license
      assigned to that device; do not inspect plugin binaries or capture
      license/activation traffic.

These questions record what this memo has not established. They do not
create a precondition for bucket D protocol work; see `SCOPE.md` §4. The
Cosmos/Native license paths are not the AFX Real-Time device-control path.
