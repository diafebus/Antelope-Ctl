# SCOPE.md -- what this project does, and the lines it will not cross

`antelope-ctl` is an **interoperability** project: a clean-room-style
reverse-engineering of the USB-HID *control protocol* of Antelope audio
interfaces, and a stdlib-only tool that speaks it, so the hardware can be
controlled on Linux (and, later, from a community web UI).

This document is **project policy**, agreed by all contributors. It is not
legal advice. Where it says "get a lawyer's review first", that is a hard
gate, not a suggestion.

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
- **AuraVerb** -- the one bundled effect (ships with the device, **no
  per-plugin activation**). Decoding and exposing its parameters is in
  scope; it was the deliberate safe pilot for effect-frame shape.

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

## 3. Jurisdiction note

The project is maintained in the EU. EU law (Software Directive
2009/24/EC, Arts. 5(3) and 6) gives mandatory rights to observe/study a
program you may run, and to reverse-engineer for **interoperability** of
an independently created program -- and Art. 8 voids contract terms that
contradict them. US interoperability precedent (Sega v. Accolade, Sony v.
Connectix) points the same way for protocol-level work.

Antelope's own published EULA terms, and how the project stays inside
them, are recorded in **`EULA-ANALYSIS.md`**. The short version: the core
work falls under the general EULA (Bulgarian / EU law -- favourable); any
plug-in-specific work would fall under the Cosmos EULA (Michigan / US law
-- less favourable), which is another reason §4 buckets D/E/F are walled
off. None of this is legal advice; bucket D needs a lawyer first.

---

## 4. AFX / Synergy Core plugin chain -- the bucket policy

Antelope's DSP plugins (Auto-Tune, the modelled EQ / comp / preamp
collections, etc.) are sold **per user** with **online activation**, and
the DSP algorithms are Antelope's IP. This project is interop for the
*mixer / routing / preamp / clocking* feature set. The plugin chain is an
**edge we approach carefully, not a target**.

Every AFX-related frame is classified into one of these buckets **before**
it is ever sent, decoded-for-replication, or documented:

| bucket | example | stance |
|---|---|---|
| **A. Signal routing** | routing an `afx_in` destination; source bank `0x05` (`afx_out`) | **In scope.** It is just the crosspoint matrix (`0x53`), nothing plugin-specific. |
| **B. Slot bypass / enable** | a per-slot on/off (mixer-level, like AuraVerb's enable bit) | **OK to decode + expose.** It is a mute, not the plugin. |
| **C. Reading slot state** | "slot N is occupied", "slot N is bypassed" | **OK to decode + display.** Observation only. |
| **D. Plugin parameter set** | "set slot-N decay = 40" on an already-loaded, already-licensed plugin | **GATED.** Requires (a) a lawyer's review of Antelope's current EULA + activation terms, and (b) that it lives in the separate AFX repo, not here. Never instantiates anything. Behind an explicit opt-in. Skipped unless there is clear user value. |
| **E. Instantiate / load / remove a plugin** | "put Auto-Tune in slot 3" | **OFF-LIMITS.** This is the licensing boundary. |
| **F. Licensing / activation / entitlement traffic** | the activation handshake, license tokens, entitlement checks | **OFF-LIMITS.** Never sent, never decoded for replication, never captured into any repo. |

**This repo (`antelope-ctl`) will contain only buckets A, B, and C**, and
only under a `SCOPE.md`-referenced module. Buckets D/E/F are out of this
repo entirely.

If in doubt about a specific frame, it stays in the **"observed, not
sent, not shipped"** state until a human decides -- default to *not*.

---

## 5. What this repo will never contain

- A parameter map, control-surface description, or preset format for any
  **licensed** AFX plugin (bucket D material).
- Any capture, or analysis of a capture, of plugin **instantiation** or
  **licensing/activation** traffic (buckets E/F).
- Anything derived from Antelope's software, firmware, or login-gated
  materials.
- A device serial, in any tracked file.
- A reference to, or dependency on, the separate AFX-investigation repo.
  The dependency runs one way only: that repo may consume this one as a
  library; this one does not know it exists.

---

## 6. Contributor agreement

By contributing you confirm that:

1. Every device capture you submit is from **hardware you own**, taken by
   observing its USB traffic -- not from Antelope's software, firmware, or
   any login-gated material.
2. You have classified every AFX-related frame per §4 and submitted
   nothing from buckets D/E/F to this repo.
3. You understand that running the official Launcher to generate a
   capture means **you** accepted its EULA, and any RE-clause exposure in
   that EULA is a personal decision you made knowingly.
4. You have not pasted copyrighted manual/UI text or Antelope binary
   contents into your contribution.

Raise anything uncertain in an issue **before** committing it.
