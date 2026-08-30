# KERNEL.md -- roadmap for upstreaming an in-kernel ALSA driver

**Status: not started. Read this when the userspace protocol work is
essentially done.** This is the plan for turning the reverse-engineered
protocol into a mainline Linux `snd-usb-audio` mixer driver. Nothing
here blocks the current userspace `antelope-ctl` tool -- that ships and
stays useful regardless.

---

## 0. Why bother

A userspace hidraw tool (what we have) works but:
- races with anything else touching the device
- no integration with `alsamixer` / `amixer` / `alsactl store|restore`
- every user needs udev rules / the repo / Python
- no distro ships it

An in-kernel driver exposes every parameter as a standard **ALSA
kcontrol**, so `alsamixer`, `amixer`, `alsactl`, and GUIs
(`alsa-scarlett-gui`-style) all work with zero setup, and distros pick
it up automatically. That is the ultimate-win state.

---

## 1. The precedent to copy

**Focusrite Scarlett Gen 2/3/4 mixer driver** -- `sound/usb/mixer_scarlett2.c`
(older: `mixer_scarlett_gen2.c`). One person (Geoffrey D. Bennett)
reverse-engineered the Focusrite Control Protocol from USB captures and
upstreamed a full mixer + routing-matrix + firmware-update driver.
**This is our situation almost exactly.** Study:

- the driver source and its git history (`git log --follow sound/usb/mixer_scarlett2.c`)
- his `alsa-devel` / `linux-sound` submission threads (patchwork archives)
- `Documentation/sound/cards/` for any Scarlett notes
- `alsa-scarlett-gui` project -- the userspace GUI that sits on the kcontrols

Other references: `mixer_us16x08.c` (Tascam), `mixer_quirks.c` (smaller
vendor quirks), the MOTU AVB code.

---

## 2. Where the code lives

ALSA, not HID. USB audio interfaces are `snd-usb-audio` (`sound/usb/`).
Vendor mixer behaviour goes in `sound/usb/mixer_antelope.c` (new file),
hooked from `mixer_quirks.c` / `mixer.c` by USB VID:PID
(`0x23e5:0xa221` for Orion Studio III).

The device presents the control channel as a **HID vendor interface
(interface 3)**, which `usbhid` binds by default. This is the main
structural wrinkle vs. a normal USB-Audio-Class mixer:

- Option A: `snd-usb-audio` quirk claims interface 3 as well and does
  raw interrupt/control transfers on EP `0x01`/`0x82`.
- Option B: driver coordinates with `usbhid` (detach / `HID_QUIRK_*`).
- Check how Scarlett Gen 4 handles its HID interface -- there is
  precedent for the mixer driver talking to a HID endpoint.

Resolve this early; it shapes the whole driver skeleton.

---

## 3. What the current work becomes

| Userspace now | In-kernel |
|---|---|
| `profiles/orion_studio_3.json` | compiled-in C structs/arrays. **No runtime config files** -- the kernel does not load JSON. |
| `protocol.build_* / parse_*` | kcontrol `.get` / `.put` callbacks issuing `usb_control_msg()` or interrupt-OUT reports |
| CLI subcommands | `snd_kcontrol_new` definitions: volume (`SNDRV_CTL_ELEM_TYPE_INTEGER` + `TLV`), enums, switches, `IEC958` for S/PDIF |
| `PROTOCOL.md` byte maps | C `#define`s + comments -- ports directly, this is the valuable part |
| `~/.cache/antelope-ctl` shadow state | **the device must report state back** -- see blockers |

The reverse-engineering (`PROTOCOL.md`) is the real deliverable and
transfers over intact.

---

## 4. Blockers to clear BEFORE writing driver code

1. **Readback for every exposed parameter.** ALSA kcontrols must return
   the device's current value. Anything we only track in a host-side
   cache is not kernel-ready.
   - **Routing matrix has no `0x73` readback** -- hard blocker. Resolve
     CAPTURE E (readback in the Launcher INIT handshake?) or prove the
     device genuinely never reports routing, in which case the driver
     carries documented shadow state (Scarlett does this for a few
     things -- acceptable only when unavoidable and commented).
   - `channel_link` enabled-bit: still not found in the state report.
   - Confirm bus / trim / talkback / ADAT / S/PDIF readback offsets are
     all solid (they mostly are -- see `state_report` byte-map).
2. **No "experimental / not hardware-tested" controls.** Every kcontrol
   must be confirmed on real hardware in both directions. No guesswork
   in a kbuild driver.
3. **Interface-claiming decision made** (section 2).
4. **Enumerate what the device actually has** -- the `0x74` topology
   burst gives counts; map `0x19`/`0x03`/`0x04`/singletons to real
   I/O so the routing source/destination lists are complete, not "TBD".
5. **Multi-device support** -- Orion Studio III + the peer's Discrete 8
   Pro under one driver (a per-model descriptor table) makes the
   submission much stronger: shows a real device family, not a one-off.
   Coordinate with the Discrete 8 Pro contributor.

---

## 5. Scope for v1 (keep it small)

Ship the minimum that is fully confirmed + readable:

- preamp: gain, mode (mic/line/hi-z), phantom, phase invert, link
- monitor / headphone / line / reamp buses: level, dim, mute, mono
- output trim
- ADAT input gain + link
- S/PDIF input gain + link (+ `IEC958` status if decoded)
- meters (optional -- can be a follow-up; `SNDRV_CTL_ELEM_ACCESS_VOLATILE`)

Defer to later series:
- routing matrix (needs readback solved; big, do it as its own patch set
  like Scarlett did)
- talkback
- oscillator / test tones
- clock source selection (not reverse-engineered yet)

Explicitly **never**: AFX / Synergy Core effects (licensing + online
activation -- out of scope for the whole project).

---

## 6. Development process

1. **Out-of-tree module first.** Build `snd-usb-audio` +
   `mixer_antelope.c` against your running kernel, iterate, ship as
   DKMS, get real users. This is where coverage gets proven.
2. **Licensing / provenance** (mostly done -- repo is GPL-2.0):
   - `// SPDX-License-Identifier: GPL-2.0-only` on every file
   - `MODULE_LICENSE("GPL")`
   - a `Documentation/sound/cards/antelope.rst` describing the device
     and stating the protocol was obtained by **black-box USB
     observation of hardware the authors own** (EU Software Directive
     2009/24/EC Art. 5(3)) -- no decompilation, no vendor code, no NDA
     docs. Matches the README disclaimer.
3. **Kernel style / hygiene:**
   - `scripts/checkpatch.pl --strict` clean
   - kernel coding style (`Documentation/process/coding-style.rst`)
   - one logical change per patch; a patch series with a cover letter
   - real name in `Signed-off-by:` (Developer's Certificate of Origin --
     `Documentation/process/submitting-patches.rst`)
4. **Submit:**
   - `scripts/get_maintainer.pl` on the diff -- expect Takashi Iwai
     (ALSA maintainer), Jaroslav Kysela
   - lists: `linux-sound@vger.kernel.org`, `alsa-devel@alsa-project.org`
   - `git send-email`, plain text, no attachments
   - follow `Documentation/process/submitting-patches.rst` +
     `submitting-drivers.rst`
5. **Iterate on review.** The Scarlett driver took many revisions over
   ~2 years and is still growing. Budget months. Address every comment,
   resend as `v2`, `v3`, ...
6. **After merge:** maintain it -- new firmware revisions, bug reports,
   adding the deferred controls as follow-up series.

---

## 7. Realistic staging

```
[now] ..... finish + confirm userspace protocol (routing readback, 0x74 map,
            channel_link bit, remaining captures)
   |
   v
[milestone] protocol substantially complete, everything hardware-verified
   |
   v
   write out-of-tree mixer_antelope.c  ->  DKMS  ->  real users
   |
   v
   v1 patch series (section 5 scope)  ->  alsa-devel  ->  review loop  ->  merge
   |
   v
   follow-up series: routing matrix, talkback, meters, more models
```

Do **not** start driver C code until section 4 blockers are cleared --
a driver built on unconfirmed/unreadable params will not survive review
and will waste the effort.

---

## 8. People / resources

- Geoffrey D. Bennett -- Scarlett driver author; has been openly helpful
  to others doing the same. Read his patchwork threads first.
- `alsa-devel@alsa-project.org` -- the list; lurk before posting.
- `Documentation/process/` in the kernel tree -- submitting-patches,
  coding-style, 5.Posting, submitting-drivers.
- `Documentation/sound/` -- ALSA-specific driver docs.
- `alsa-scarlett-gui` -- template for the eventual userspace GUI on top
  of the kcontrols (our current CLI could be rebased onto ALSA controls
  as an interim).
