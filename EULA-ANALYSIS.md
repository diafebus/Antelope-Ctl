# EULA analysis -- Antelope Audio license terms vs. this project

Phase 0 of the AFX plan ("paper first") and a general due-diligence record.
Sources are Antelope's **own publicly published** legal pages:

- General EULA -- <https://en.antelopeaudio.com/legal-terms/eula/>
- Cosmos plug-in EULA -- <https://en.antelopeaudio.com/legal-terms/antelope-cosmos-eula/>
  (version stated on the page: **1.12.2023**)

Retrieved 2026-09-01. Quotes below are verbatim from those pages; if they
have since changed, re-check before relying on this.

**This is not legal advice.** It is a contributor-facing record of what the
terms say and how the project stays on the right side of them. Bucket D
(see `SCOPE.md` §4) still needs an actual IP lawyer's review before it
proceeds.

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

---

## 2. Who these terms bind

The restrictions bind a **"Licensee"** -- someone who accepted the EULA by
"Using" the Software, defined as "download, install, activate, access or
otherwise use". In practice:

- **A contributor who installs and runs the Antelope Launcher is a
  Licensee** and is bound by (ii)/(iii)/(iv).
- Someone who only ever interacts with the **USB hardware** and never
  installs Antelope's software is not a Licensee *of the Software* and did
  not accept this EULA. (Device firmware may be covered by a separate
  agreement -- not reviewed here.)

The exposure therefore sits on **whoever runs the Launcher to produce a
capture** -- a personal, contract-law matter, not a claim against the repo
or downstream users. This is why the contributor agreement in `SCOPE.md`
§6 and the AFX-repo charter both call it out.

---

## 3. How the project stays inside the lines

| clause | project posture |
|---|---|
| (ii) reverse-engineer the Software | The project **never decompiles, disassembles, or inspects Antelope binaries/firmware**. It observes **USB traffic on the wire** between the app and hardware a contributor owns -- black-box observation of externally visible behaviour, not inspection of the program's code. `SCOPE.md` §2 makes this a hard rule. |
| (iii) modify / combine / merge with other software | `antelope-ctl` contains **no Antelope code** -- not a line, not a table, not a constant. Nothing is combined or merged. |
| (iv) develop software with similar functional attributes | This is the clause with real bite: `antelope-ctl` *is* software that controls the same device. See §4 -- its enforceability turns on jurisdiction. |
| (v) device-bound Software on another device | Not applicable to a controller. Relevant to plug-in / mic-model licensing being account+device bound -- which is exactly why AFX bucket D is limited to a plug-in **already loaded and licensed on the target device**, and why the emuMic catalogue is a separate account-bound data file. |
| (vi) remove/conceal notices | N/A -- no Antelope Software is redistributed. |
| (vii) copying | N/A. Captures are never committed (`SCOPE.md` §2). |

---

## 4. Jurisdiction -- the split that shapes the plan

- **Core work** (mixer / routing / preamp / clocking, via the Launcher and
  the **general EULA**) -> **Bulgarian law**, i.e. **EU law**. The EU
  Software Directive (2009/24/EC) gives mandatory rights to **observe,
  study and test** a program you are entitled to run in order to determine
  its underlying ideas and principles (Art. 5(3)), and to **decompile for
  interoperability** (Art. 6). **Art. 8 makes contract terms that
  contradict those rights null and void.** A EULA clause forbidding
  black-box protocol observation *for interoperability* is, to that
  extent, likely unenforceable in the EU. This is a genuine and
  reasonably strong shield for the core project.

- **Plug-in work** (if it ever touches Cosmos or a similarly licensed
  plug-in, under the **Cosmos EULA**) -> **Michigan / US law**. No
  equivalent statutory interoperability carve-out; US courts have enforced
  contractual anti-reverse-engineering clauses in EULAs and held them not
  preempted by copyright (*Bowers v. Baystate*, Fed. Cir. 2003). **The
  plug-in chain sits in the less favourable jurisdiction.**

This reinforces the structure in `SCOPE.md` §4 and the AFX-repo charter:
keep the core work here under the EU-law umbrella, and firewall anything
plug-in-specific into a separate repo, gated on a lawyer's review.

---

## 5. Practical enforcement picture

Antelope's realistic options against an individual EU contributor:

1. A **cease-and-desist letter** -- cheap to send, and the separate-repo
   structure limits what one letter can reach.
2. A **GitHub DMCA notice** -- but that is a *copyright* mechanism, and the
   copyright claim against protocol-level interop work is weak (facts, not
   expression; interop precedent). Counter-notice restores the repo.
3. **Initiating arbitration** in Sofia (general EULA) or Detroit (Cosmos)
   -- expensive, cross-border, slow, uncertain outcome on the merits given
   §4.

The mitigations already in place: no Antelope code in the repo, black-box
observation only, a documented interoperability purpose, `captures/`
never committed, offline `git bundle` backups, and (for the risky part)
a separate, separately-hosted repo.

---

## 6. Open items before AFX bucket D

- [ ] Confirm there is no **separate hardware / firmware click-through**
      agreement with stricter terms (check the box, the registration flow,
      the firmware updater).
- [ ] Re-fetch both EULAs and diff against the quotes above (they are
      undated except Cosmos).
- [ ] **One hour with an IP lawyer** who knows software licensing and the
      EU Software Directive, specifically on: (a) whether Launcher protocol
      capture is within Art. 5(3); (b) clause (iv) enforceability under
      Bulgarian law; (c) the Michigan exposure for any plug-in work.
