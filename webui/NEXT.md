# webui -- hand-off for the next session

Sandbox clone `antelope-ctl-UI-test`, branch **`ui-draft`** (no remote).
Canonical protocol repo is **`../antelope-ctl`** -- its `SUMMARY.md` +
`CLAUDE.md` are gitignored there, read them over there for the full decoded
state. `../antelope-ctl` HAS a remote (`origin`, GitHub) and `main` is kept
pushed; this clone is never pushed.

**Standing rule (user, 2026-09-02):** any empirical test result or protocol
discovery not already in `PROTOCOL.md` / `profiles/*.json` must be written up
and landed on **both** repos, kept identical. Refresh canonical first, commit
+ push there, mirror here. `webui/` is sandbox-only; webui code doesn't sync,
but a protocol fact found *through* the webui still does.

**Licence (as of 2026-09-03, canonical `c6d9e3a`):** code + CLI + web UI +
docs are **GPL-3.0-or-later** (`LICENSE`); `profiles/` is **MIT**
(`profiles/LICENSE`). Was GPL-2.0; relicensed while the user was still sole
author. README has a "License" section; new contributions are under the same
split (informal DCO line in the README). Don't reintroduce a GPL-2.0 header
anywhere.

**Project context:** the user is the only one doing hardware/protocol work
and owns the Orion. There's a small group around it now with divergent ideas
-- a "Gazelle" project-scope doc (`webui/ideas/Gazelle - Project Scope…pdf`,
a manifesto proposing a Rust rewrite + multi-vendor + driver/audio/network
management as v1) written by one member, and a separate member pushing a
Python-to-Rust rewrite on taste. The engine here is proven, hardware-tested
Python; a rewrite carries protocol-revalidation risk for zero user-facing
gain until the protocol is *done* and there's a measured reason. Keep
building in Python; the OSC/MIDI bridge can be added to it directly.

## ⚠ Linux quirk -- sample rate & clock source are locked while audio streams

The Orion **ignores** `SET_GLOBAL` sample-rate (`0x03`) and clock-source
(`0x04`) writes over HID **while the host has its USB audio interface
streaming** -- verified 2026-09-03 (set clock→OVEN + stepped every rate,
`0x73` `[18]`/`[19]` never moved; `/proc/asound/card3/stream0` showed
Playback+Capture `Status: Running`, altset 1). This is **not** a device or
protocol limitation -- on macOS the Launcher coordinates with CoreAudio to
release the stream first. On Linux, PipeWire keeps the interface claimed.

**To change the rate/clock from the webUI on Linux, the user must free the
device first:**

```
systemctl --user stop pipewire pipewire-pulse wireplumber pipewire.socket pipewire-pulse.socket
# ... change sample rate / clock source ...
systemctl --user start pipewire pipewire-pulse wireplumber
```

(the `.socket` units matter -- without stopping them, socket activation
restarts pipewire immediately and the device stays claimed).

The webUI should: detect the streaming-locked case (a rate/clock write
that doesn't stick within ~2 s), and surface this instruction to the user
rather than silently failing. A future nicety: a "release audio device"
button that shells out to the systemctl stop/start (opt-in, clearly
labelled -- it kills the user's audio for the duration).

## Architecture

Thin **local FastAPI daemon** (`webui/server.py`) owns the one HID handle
and sits between the hardware-tested Python core (`antelope/…`,
`profiles/*.json` -- do NOT rewrite) and a **no-build-step browser UI**
(`webui/static/index.html`, one big vanilla-JS `<script>`). The UI renders
from the profile.

- `server.py`: one background thread owns the device.
  - FAST state: free-running `0x73` state is parsed into an in-memory
    snapshot; raw `0x75` debug lanes are sampled at a lower rate. SSE
    `/api/stream` polls for new snapshots at ~25 Hz.
    EventSource reconnects itself. Snapshot keys include `channels buses adat
    spdif trim input_meters brightness sample_rate_idx clock_source_idx
    state_raw meters_raw` (+ `rb_ver`). Orion `input_meters` samples contain
    `raw`, `db`, `clip`, and `silence`. The current uncalibrated `0x73` source
    returns `null` for `db` and `clip`.
  - SLOW state: routing matrix (readback cat `0x03`) + virtual mixer (cat
    `0x04`) re-read incrementally on connect and every 45 s, one record per
    fast-state cycle. Route/mix commands use the serialized cache after its
    initial verified readback and update it after a successful write.
    Snapshot carries a monotonic `rb_ver`; the browser refetches
    `/api/routing` + `/api/mixer` when it bumps.
  - Commands are queued as callables `fn(transport)` and run at most one per
    fast-state cycle, so control bursts do not starve meter updates.
- **Profile auto-detect (done):** `server.resolve_profile()` -- `ANTELOPE_PROFILE`
  (path or `profiles/` basename) wins; else `transport.list_connected_hid()`
  matches a connected HID node's `(vid,pid)` against `profiles/*.json`
  `device.vid/pid`; else falls back to `orion_studio_sc.json`.
- Endpoints:
  - `GET  /api/profile /api/mic_models /api/state /api/routing /api/mixer /api/stream`
  - `POST /api/gain /api/toggle /api/mode /api/link` (preamp)
  - `POST /api/adat-gain /api/spdif-gain /api/adat-link /api/spdif-link` (digital in)
  - `POST /api/bus` (level) `/api/bus-toggle {bus,param:dim|mute|mono,on}`
  - `POST /api/output-trim {target 0-2,value 0-6}` `/api/dc-coupling {on}`
  - `POST /api/brightness /api/mix /api/emumic`
  - `POST /api/sample-rate {value 0-6}` `/api/clock-source {value 0-6}`
    (SET_GLOBAL enums; read back as `sample_rate_idx` / `clock_source_idx`
    in the `0x73` stream. Both ignored while the host streams audio over
    USB; sample rate also ignored while clock = USB -- the header clock
    bar flags the select + shows the systemctl release-audio steps when a
    write doesn't land in 3.5 s.)
  - `POST /api/route {dest,channel,kind,number}` -- one output channel
  - `POST /api/route-batch {dest,changes:[{channel,kind,number}]}` -- one
    read-modify-write of the whole destination record (group ops, 1:1 fills)
- Run: `cd webui && .venv/bin/python server.py` -> http://127.0.0.1:8714
  (one HID owner -- stop the CLI/selftest first). `.venv` is gitignored.
  No auto-reload -- restart after editing `server.py`; `index.html` is read
  from disk per request. **Stopping it:** SIGTERM can hang (HID reader thread
  doesn't join); `fuser -k 8714/tcp`, or `kill` then `kill -9`.

### UI layout (index.html)

- **Input tabs** `INPUTS | ADAT / S/PDIF` (`.tabbar` / `initTabs()`, last tab
  in localStorage). Inputs = 12 preamp strips on a fixed 8-wide grid. The
  ADAT tab now holds **both** ADAT (16, 8+8) *and* S/PDIF (L/R) as one pane
  with an `<h3 class="dsub">S/PDIF</h3>` divider -- the standalone S/PDIF tab
  was dropped (2 channels didn't earn a tab).
- The three input panes are **stacked in one CSS-grid cell** (`.panewrap`,
  inactive = `visibility:hidden`) so the section keeps the tallest pane's
  height and switching tabs no longer shifts everything below it.
- **Collapsible sections:** any `<h2 class="sechd">` with a `.secmin`
  button (`data-min="<bodyId>"`) toggles `.secbody.min` (persisted
  `localStorage["min:<id>"]`). Wired on **Output Buses** and **Routing**
  by `wireMinButtons()`.
- **Settings gear** top-right of the header (`#gearbtn`, `assets/set-gear.svg`)
  opens `#settings`, a draggable non-blocking panel: output trim, Line Out /
  Reamp levels + Line Out mute, DC coupled, brightness.
- **Three knob families, all separate functions -- do not cross the streams:**
  - preamp: `buildChannels` markup, `paintKnob` / `wireKnob`, `KNOB_C`
    `'54.840942 52.983658'`, red `.kbody`, `viewBox 37.84 35.98 34 34`.
  - monitor rotary (Monitor A/B, Headphone 1/2): `monKnobSVG()` /
    `hpKnobSVG()`, `paintMonKnob` / `wireMonKnob`, `VK_C` `'13.6 13.6'`.
  - ADAT / S-PDIF: `adatKnobSVG()` (art inlined -- the `assets/adat-knob*`
    files were deleted from disk by the user, harmless), `paintDigKnob` /
    `wireDigKnob`, `DIG_KNOB_C` `'11.857 12.054'`, `DIG_RING_*` white arc.
  - **TRAP (cost 2 reverts a prior session):** `buildDig` copy-pasted
    `buildChannels`' knob markup byte-for-byte; string edits anchored on the
    knob block hit the PREAMP copy first and break `paintKnob` ->
    everything below stops rendering. Anchor on path-unique context, assert
    the other block is byte-identical, run a boot() smoke test. Memory
    `webui-shared-knob-markup`.

### Routing UI (the `#routesec` section)

- **Tabs** `Routing | Mix 1 | Mix 2 | Mix 3 | Mix 4` (`#routetabs` /
  `initRouteTabs()`, `[data-rpane]`, persisted). The Mix tabs now host the
  compact vertical-strip virtual mixer: fader, pan, send, mute, solo, and the
  selected raw mixer meter. Selecting a Mix tab automatically selects the
  hardware's matching mixer-window meter bank. Solo is mix-wide, supports
  multiple simultaneous solo channels, and restores the pre-solo flags after
  the last Solo is released.
- `buildRouting()`'s `.rtop` now holds only the `Grid | Matrix` toggle
  (`setRouteView`, persisted). The **Destination `<select>`** lives in
  `renderMatrix()`'s sticky `.rdtitle` bar (right above the grid) -- so it's
  next to the matrix, gone in Grid mode (the bar is inside `#rmx`), and
  follows the matrix into the pop-out.
  - **Grid** (`renderGrid`, `#rpb`): the Launcher-style FROM/TO board. Source
    group rows of numbered cells on top; destination rows below. Every cell
    is a fixed 30px square; each TO cell shows the feeding source as a
    1-letter family tag + number (`cellTag()` -> `P12`, `C32`, `SL`, `✕`,
    `·`), colour carries the family.
  - **Matrix** (`renderMatrix`, `#rmx`): per-destination, sources down the
    side (collapsible groups), one lit cell per output column.
- **Colours** (`SRC_FAM` + `.fam-*` CSS, 4 copies): preamp green `#43c96a`,
  emumic light green `#93e0b4` (its own family now, was sharing preamp's),
  ADAT red `#e05561`, playback blue, afx purple, surround teal, spdif cyan,
  mix orange, mute grey.
- **Select-then-place model** (grid): click a source, then click *or drag*
  onto a destination.
  - `RG_ARMED = { rows:[srcKey…] | ['mute:'], anchor, group }`.
  - **Shift-click** a second source cell in the same group -> selects the
    **range**; place it on a destination cell -> **consecutive fill** from
    that channel (CP 3-6 -> Line Out 10 fills LO 10..13).
  - Source **group label** -> destination -> 1:1 (confirm). `✕ MUTE` row ->
    a destination cell mutes one, -> a destination row label mutes the row
    (confirm). No "Mute all" button any more -- it was a footgun.
  - Drag uses **document-level pointer listeners, no `setPointerCapture`**
    (capture broke `elementFromPoint` so drops never landed). `rgExpand()`
    normalises a single node; `rgRoute(rows, isGroup, destNode)` is the one
    dispatcher for click *and* drag.
- **"Full view" pop-out** (`#routepop`, `openRoutePopup`): a real
  `window.open` (chromeless via `popup=yes,location=no,…` -- no address bar
  on Chrome/Edge; Firefox keeps a slim origin strip it won't let JS remove),
  holding the whole routing UI (Grid *and* Matrix). Its DOM is disposable:
  `buildRouting()` rebuilds `#routing` from `ROUTING` on open and on close,
  so nothing is lost if the window is killed. `routingHome()` / `rq()` /
  `rqa()` resolve every routing query to whichever `#routing` is live.
  Main page shows a "Bring it back" placeholder while it's out.
- **Write feedback:** optimistic -- the cell repaints to the new source
  immediately (`gridMarkPending`). A write resolves the instant a readback
  **newer than it** lands (`ROUTE_PENDING[k].ver` vs `RB_VER`), not on a
  timer -- so no false red "differ" flicker. `RT_TIMEOUT_MS 2500`,
  `RT_FLASH_MS 450`, pulse `0.4s`.

## ⚠ Hard rule -- carry this over

**Never send a `0x74` readback query past a category's record count** -- it
BusFaults the Orion (physical power cycle). All readback goes through
`protocol.build_readback_query` -> `check_readback_index`, bounded indices
only (cat `0x03` idx 0-14, cat `0x04` idx 0-3). See
`../antelope-ctl/CLAUDE.md` "STANDING HARDWARE RULE".

## Done 2026-09-04

### macOS HID -- PROTOTYPED, THEN PARKED (user call 2026-09-04)

Linux is the goal; on macOS the Orion has Antelope's own drivers, so this
isn't worth the effort right now. A working prototype was built and then
**reverted** -- `antelope/transport.py` is back to canonical. Nothing macOS
ships. Notes kept here in case it's ever revisited:

**The prototype (git: commits `252ad5b`..`2961811`, reverted in the commit
right after) did work:**
- Discovery: parse `ioreg -a -l -r -c IOHIDDevice` with stdlib `plistlib`
  (regex fallback on `ioreg` text). Auto-detected the profile on the Mac.
- Transport: IOKit `IOHIDManager` via raw `ctypes` (no dependency, same
  style as the Windows backend). `IOHIDDeviceSetReport` for writes; an
  input-report callback pumped by `CFRunLoopRunInMode` on the device thread
  for the free-running `0x73`/`0x75`. Same surface as `HidTransport`.
- **Verified on the user's Mac** (Orion Studio III `0x23e5:0xa221`, Monterey,
  Intel, class-compliant): discovery + `status` read + `set-gain` write
  round-trip all worked. Needs the terminal granted **Input Monitoring**.

**Why it was parked:**
- With Antelope's macOS driver installed, the driver claims the Orion's HID
  control interface exclusively -- the device leaves the `IOHIDDevice`
  registry entirely (`system_profiler` still shows it on USB;
  `IOCreatePlugInInterfaceForService failed 0xe00002be`). So it's the tool
  **or** Antelope's driver, never both -- like "quit the Launcher" on Linux
  but the holder is a system driver you'd have to uninstall.
- Class-compliant (driver off) the tool works, but audio in Reaper was
  distorted -- most likely a sample-rate/clock mismatch (the device was
  left on a rate/clock the host wasn't matched to), not class-compliant
  audio itself. Not chased.
- One code question left unanswered: the webui VU meters looked wrong on
  macOS while gains parsed fine -- theory was IOKit delivering a shorter
  input report than `transport.report_size` (320), truncating `0x73` before
  the meter block at `[157+]`. Commit `2961811` sized the buffer to the
  descriptor's `MaxInputReportSize` and added `ANTELOPE_HID_DEBUG=1` to
  print delivered report lengths -- never tested.

If revisited: `git show 252ad5b` etc. has the whole implementation.

### Sample rate + clock source (header clock bar)
- New `#clockbar` in the header, left of the settings gear: two `<select>`s
  (`Rate` / `Clock`) populated from `params.sample_rate.values` /
  `params.clock_source.values`. `POST /api/sample-rate` / `/api/clock-source`
  -> `build_global_command(profile, ...)`. No browser-side state -- both read
  back in the `0x73` stream (`sample_rate_idx` / `clock_source_idx`), the
  selects follow the device.
- Streaming-lock handling (the Linux quirk below): a write that doesn't show
  up in the readback within `CLOCK_STUCK_MS` (3.5 s) marks the select amber
  (`.stuck`) and drops the `#clockmsg` strip under the header with the
  `systemctl --user stop pipewire …` release-audio steps.
- **Not yet hardware round-tripped through the webUI.** The device was on
  clock = USB while streaming during dev, so every write was (correctly)
  ignored -- exactly the stuck path. Needs a pass with the audio stack
  stopped + clock on Oven to confirm the happy path end to end.

### Routing -- Grid + Matrix, both usable  (2026-09-03)
- Matrix Phase 1/2 (per-destination grid, `/api/route-batch`, group 1:1) and
  the FROM/TO grid, both hardware-verified against the CLI in prior sessions.
- Grid drag was broken (`setPointerCapture` + `elementFromPoint`); rewritten
  with document listeners. Added click-to-route + shift-click range select +
  consecutive fill. Verified via a faithful DOM simulation (`scratchpad/
  dragtest.js` -- drag / click / range / group all dispatch the right
  `/api/route[-batch]`).
- "Full view" is now a real detachable browser window (was an in-page modal).
- Removed the "Mute all" button (hazard). Drag `✕ MUTE` onto a row label
  still mutes the whole destination, with confirm -- matches the Launcher.

### Layout
- S/PDIF folded into the ADAT tab; standalone S/PDIF tab removed.
- Routing tabs (Routing + 4 compact mixer views).
- Collapse buttons on Output Buses + Routing.
- Tab-switch no longer shifts the page (`.panewrap` grid-stack).
- Grid cells uniform 30px; tighter `cellTag` labels; emumic its own colour.
- Destination selector moved into the matrix's sticky title bar.

### Protocol -- compplay 25-32 confirmed
Wrote each of Computer Playback 25..32 into a spare output slot on the device
and read the routing record back (cat `0x03`) -- all eight stuck unchanged,
no clamping. Bank `0x02` idx 0-31 all valid on the macOS driver. Note
upgraded from "user-observed" to confirmed. **Canonical `2f3f6bf` (pushed)**,
mirrored here `5307e97`.

### Relicensed GPL-3.0-or-later + MIT profiles
Canonical `c6d9e3a` (pushed), mirrored here `71d2ea5`. See the Licence note
near the top of this file.

### emuMic range corrected: preamps 5-12, not 7-12
The EMU button is **Mic-mode-gated** -- it shows on a channel only in Mic
mode. The reference unit had preamps 5-6 in Line, so earlier work saw
"7-12". Confirmed via the webui/live device: routing `emumic 5`/`emumic 6`
(bank 0x01 idx 0/1) into spare slots read back like 7-12; `channel_bias -4`
already put `[18]=0` at preamp 5. `micmodeling_command.channels` is now
`[4..11]` -- the webui is data-driven so the EMU button + pair logic pick
up preamps 5-6 with no code change. Canonical `27bb70a` (pushed), mirror
`39eb06d`. Not yet captured: a Launcher `0xe5` frame with `[18]=0`/`1`.
Making the UI is what surfaced this -- routing showed 8 emumic sources.

## Synced from canonical 2026-09-03 -- readback decode batch (mirror `bfe20e6`)

The shared code + protocol docs are now at canonical `42ba3f5`. New since
the last sync, relevant to the UI:

- **AuraVerb protocol support is decoded, but the WebUI panel is not finished.**
  `antelope-ctl auraverb` reads the device (all 4 mixes) and does a verified
  read-modify-write; `protocol.parse_auraverb_record(profile, body)` decodes
  the cat `0x0a` readback. The current Mix 1 panel is only a presentation
  shell: its controls still need a live end-to-end test and repair so that
  parameter changes and FX on/off reach the active daemon, update the device,
  and can be heard. A browser `404 {"detail":"Not Found"}` means the page is
  being served by an older/different daemon or checkout; after that is ruled
  out, inspect the POST queue, optimistic state, readback refresh, and the
  actual hardware command. The recent captures confirm Orion on/off at byte
  `@28` (`01`/`00`) and the parameter offsets, but do not by themselves prove
  that the WebUI path is working. AuraVerb is intentionally not exposed for
  Zen Go until its profile has a confirmed command and readback contract.
- readback cat `0x05` = preamp gain (1 byte/ch, dB), `0x06` = channel
  status `(phase<<6)|(phantom<<4)|(mode&3)` -- both mirror the `0x73`
  report, decoded + selftest-cross-checked.
- **channel link: there is NO device readback** (proven). Any link
  indicator in the UI is client-tracked, same as the CLI/Launcher.
- **emuMic preamps 5/6 captured on the wire** (`0xe5 [18]=0x00/0x01`) via
  usbmon while THIS webUI drove EMU on preamp 5/6 -- the capture method is
  now documented in `CAPTURING.md` (webUI + usbmon, no VM needed).
- output_trim re-confirmed (dBu scale); pan law is NOT `0x4b` target 3 and
  cat `0x16` tracks neither -- still needs a capture.

## Canonical commits (pushed) -- recent
- `42ba3f5` README: fold in the 2026-09-03 findings
- `e1f2dd9` mic modeling: emuMic on preamps 5/6 captured on the wire
- `3c2de46` channel link: no device-side readback (whole-report diff)
- `244bd8d` auraverb: decode readback cat 0x0a + hw round-trip
- `3d21dce` readback: decode cat 0x05 (preamp gain) + 0x06 (channel status)
- `27bb70a` mic modeling: EMU is preamps 5-12, not 7-12 (Mic-mode-gated)

## Historical meter plan from 2026-09-05 (superseded)

The current implementation supersedes this plan. It reads physical preamps
1..12 from full-report `0x73` offsets 221..232 and publishes `input_meters`.
These samples are raw and uncalibrated. Raw 0 is top-of-scale saturation,
not a CLIP claim. Raw 96 is silence, and a missing sample is unknown.

Current details are in `webui/METERS.md`, `PROTOCOL.md` §9, and
`profiles/orion_studio_sc.json` (`state_report.channel_meter_notes`). The
text below preserves the old proposal as history.

**Historical finding at that date:** the 12 preamp meter strips (`applyMeters` ->
`.pre[data-ch] [data-meter]`, reading `meters_db` from `0x73` offset
`157+ch`) are NOT showing physical preamp input. Bytes 157/158/159/160
are the **4 virtual Mixer buses' own master meters** (Mix 1/2/3/4), which
only look like "preamp N" because each mix bus defaults to being fed by
the matching preamp among its many sources. Repatch `surround_in` or a
`mix_ch` strip away from that default and a "preamp N" meter shows
whatever's actually there instead (Computer Playback, another mix, etc),
silently. No true, routing-independent physical-preamp meter (real clip
detection on the analog input) was found anywhere in the HID control
stream (`0x73`/`0x75`) after an exhaustive scan -- it most likely lives in
the isochronous USB Audio stream instead (confirmed present, endpoint
`0x84` IN, 24-bit PCM, channel layout **undecoded** -- a genuinely
separate, bigger reverse-engineering task, different capture methodology
entirely from anything done on this project so far).

**Historical decision on 2026-09-05, now superseded:** do not change the WebUI code yet.
Seeing *some* meter activity on the preamp strips -- even mislabeled,
even if it's actually Mix-bus content -- is still useful for now (it
tracks the preamps correctly as long as routing is untouched, which is
true for most normal use). Revisit once the real preamp/clip meter is
sorted out (isochronous audio decode, or another approach), rather than
ripping out the current display for nothing in its place.

The superseded plan listed these TODOs:
- Relabel `cli.py meter` (canonical) and this webui's preamp strips from
  "preamp N" to "Mix N master" if the display stays as-is, OR replace it
  with a real decoded preamp/clip meter once the isochronous audio
  channel layout is known.
- The old "Confirm the `157 + ch` meter offset on channels 5-12" item
  below is now moot/wrong -- there is no per-channel 5-12 meter to
  confirm; drop it once this section is acted on.

## Still open / next

1. **Virtual mixer follow-up:** map the master meter lane if one is exposed;
   the current live mapping covers strips 1..32 at `0x73 @157..188`.
2. **Hardware side-by-side for the compact mixer UI** -- verify the new visual
   layout and meter response against the Launcher with a live signal.
3. **More settings, once decoded** -- panel notes what's not wired:
   oscillator (`0x0a` packed byte, fields unconfirmed), pan law (never
   captured -- NOT `0x4b` target 3, ruled out live 2026-09-03), TB latency
   mode (never captured), surround EQ pre/post (`0xeb`, toggle bits not
   isolated -- cat `0x1b` may be its readback, untested). Need dedicated
   captures before wiring (the webUI + usbmon method now works from Linux).
4. **Re-sweep emuMic pattern range** for models 1/12/16/18. ~~Confirm the
   `157 + ch` meter offset on channels 5-12~~ -- MOOT. See the superseded
   historical meter plan above. The current physical-input base is 221.
   (emuMic-range correction is
   CLOSED -- `0xe5` on preamp 5/6 captured 2026-09-03, `[18]=0x00/0x01`;
   listen test done -- `emumic5`==`emumic6` mono for a mono emulation,
   model select audibly correct.) AuraVerb remains an open WebUI integration
   task; see the protocol-support note above.
5. **Hide undeclared sections** -- an empty `<section>` still renders its
   header. Pairs with finishing the non-Orion stub profiles.
6. **`--host` + token** for LAN access; localhost-only now.
7. **Packaging** -- `pip install` + `antelope-ctld` / systemd user unit.
   Keep `antelope/` stdlib-only; FastAPI stays in `webui/`.
8. **OSC / MIDI / WebSocket bridge** -- the group wants controller mapping.
   Add it to the Python service (`python-osc`, `mido`, `websockets`); do not
   let it become a rewrite argument.
9. **Small cleanups:** the static `[data-rpane="matrix"]` hint text still
   reads matrix-only ("click a group to expand") though it sits under both
   views; Firefox pop-out still shows a thin origin strip (browser-imposed).

**Art:** most in-use SVGs are inlined in `index.html`; the mixer
`fader-shadow.svg` is served from `/webui/assets/`; `webui/assets/` holds the
source files (some now `.png`), `webui/ideas/` is the scratch dump
(`popup1-3.svg`, `routing matrix.png`, …). Pattern: inline the SVG, strip
the mesh-polyfill `<script>` + Inkscape cruft, prefix gradient ids per
instance, toggle state with a CSS class / `data-rot` group.
