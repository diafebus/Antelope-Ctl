# webui

The in-repository local daemon + thin browser UI for `antelope-ctl`.

## What it is

The application-facing name for the bundled reverb is **Gazelle Reverb**.
**AuraVerb** is retained here only when referring to the device's protocol
evidence; profile/API identifiers such as `auraverb` are kept unchanged for
compatibility.

- **`server.py`** -- a small FastAPI daemon. One background thread owns the
  HID device. It pushes two kinds of state to the browser:
  - **fast** -- the free-running `0x73` state and meters, over SSE at up to
    ~25 Hz (channels, buses, brightness, meters). The raw `0x75` diagnostic
    bank is sampled separately at a lower rate.
  - **slow** -- the routing matrix (readback cat `0x03`), virtual mixer
    (cat `0x04`), profile-confirmed Gazelle Reverb and Surround state, and any
    profile-declared nested readback records, refreshed one record per meter
    cycle on connect and every 45 s. Route/mixer/Gazelle Reverb writes update
    their serialized caches directly. The Surround tab exposes the bounded
    `0x1b` global and `0x1a` speaker EQ/head records; the 2.0/2.1 global
    format and delay/level paths, 2.0/2.1 Bass Management fields, and
    confirmed EQ PRE/POST write using fresh complete-state reads. The bounded
    per-speaker delay/level/phase and EQ knob paths write one field from a
    fresh complete state and compare the next readback. Direct EQ graph drags
    are the bounded exception: `/api/surround/eq/point` updates frequency and
    gain together in one complete-state frame so one pointer gesture stays
    coherent. The speaker bypass mask uses the same complete-state approach.
    The EQ Reset action writes the profile preset for only the displayed
    speaker. `/api/readbacks` exposes the structured records
    to diagnostics and `/api/surround` serves the decoded Surround surface. Queries use the active
    profile's bounded category counts or explicit capture-confirmed layouts, so
    the BusFault hazard is never hit; schema-only layouts are displayed as
    capture-required and are never probed.
    The snapshot carries an `rb_ver` counter; the browser refetches the slow
    APIs when it changes.

  Commands are queued as callables run one per meter cycle on the device
  thread, so control bursts cannot monopolize the live meter path.
- **`static/index.html`** -- the small HTML shell, with ordered vanilla-JS
  modules in `static/ui/` and styles in `static/app.css`; there is no build
  step:
  - `core.js` -- shared state, storage, API helpers, and control primitives;
  - `inputs.js`, `settings.js`, and `preamp.js` -- input and device settings;
  - `meters.js` and `buses.js` -- meter and output-bus rendering;
  - `routing.js` and `mixer.js` -- routing and mixer surfaces;
  - `surround.js` -- profile-driven Surround monitor and EQ readback;
  - `readback.js` and `boot.js` -- diagnostics, state fan-out, and startup.

  The UI itself contains:
  - input strips styled after `assets/PreampUI.svg` -- 270° gain knob
    (drag / wheel), mode select, 48V + Ø buttons, vertical meter;
  - output buses (device-confirmed attenuation: raw 0 = 0 dB maximum,
    raw 96 = -inf/silent), screen brightness;
  - a **Routing** panel with `Routing | Mix 1 | Mix 2 | Mix 3 | Mix 4 | Surround` tabs;
    each Mix tab contains a compact horizontal board of vertical strips with
    fader, pan, mute, solo, and the selected raw mixer meter. Orion's Mix 1
    input strips additionally expose the Gazelle Reverb send; Mix 2-4 and all
    master strips deliberately do not. Selecting a Mix tab automatically
    selects its matching mixer surface/meter bank; multiple Solo buttons may be
    stacked and the original mute/solo state is restored when the last Solo
    is released;
  - a **Surround** panel packs global delay/level rotary controls, EQ position,
    and the Bass Management launcher into one control box. Its speaker map
    centralizes selection plus bypass/mute/dim feedback: inactive speakers are
    grey, while the selected active speaker glows. Per-speaker delay/level,
    phase, bypass, and 16-band EQ controls are shown below. EQ points can be
    dragged with damped frequency/gain movement; the wheel changes Q only
    while directly over a point, and the response curve updates live;
  - the **Bass Management** popup shows only active format channels, places
    2.1 as L · R · LFE, and groups strips with colored bars. Its fader readout
    accepts an exact value on double-click. Fader thumbs use a reload-safe
    percentage of the profile range and an 18 px top/bottom travel inset so
    the original artwork does not overlap the readout or Mute/Solo controls.
    Confirmed 2.0/2.1 writes include filter type, Link, Solo, fader, mute,
    bypass, order, and cutoff. The global format selector allows 2.0 and 2.1;
  - a **Protocol readback** diagnostics section renders profile-declared link
    tables, mic-emulation state, AFX instance counts, and AFX strip order. It
    seeds mixer-pair link state from a complete profile-confirmed bitmap when
    one is available, while keeping other link values observational;
  - device-specific panels are selected by the presentation registry in
    `webui/device_ui.py`: Zen Go shows its input-source selectors, while any
    profile with a complete confirmed Gazelle Reverb (AuraVerb protocol)
    contract exposes the closed-by-default panel;
  - rotary controls use relative vertical drags (240 px full-scale by default,
    with slower per-control travel for Surround monitor values). Wheel changes
    are accepted only while the pointer is actually over the knob, so normal
    page scrolling cannot accidentally alter a control;
  - reconnect UX -- the UI dims and goes non-interactive while the device
    is offline, and EventSource reconnects automatically.

  Channel count, modes, gain limits, Hi-Z channels, digital inputs and mixer
  ranges come from the active profile. The daemon autodetects the connected
  VID/PID and exposes only capabilities with safe, profile-declared readback.
  Zen Go renders its two capture-confirmed mixer layouts and profile-bounded
  routing/source controls. Its 16 strip meters use the profile's
  surface-gated `0x73` lanes, and its complete q0b/03 link bitmap can seed the
  visible mixer-pair state. The mixer fader artwork is served from
  `/webui/assets/fader-shadow.svg`.

  The Zen Go source selectors are writable because the profile marks routing
  indices 6-9 as capture-confirmed; each change reads all four mirrored
  records, updates one slot, and writes the complete groups back. See
  `webui/DEVICE_UI.md` for the presentation-layer feature split.

## What it deliberately does NOT do

- **No unbounded readback.** Orion routing/mixer indices are inside
  `frame.readback.category_counts`; profiles without a complete count may use
  only an explicitly capture-confirmed feature layout. The incremental sweep
  never invents additional indices.
- No auth (binds to `127.0.0.1` only).
- No packaging. It is a sketch.

## Run

```
cd webui
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 server.py
```

Open <http://127.0.0.1:8714>. Needs the Antelope attached and the udev
rule in place (same as the CLI). Stop anything else that holds the HID
node (the CLI, `selftest.py`) -- only one process can own it.

Stop the foreground service from that same terminal with Ctrl+C. The server
passes the signal through Uvicorn, immediately wakes its HID worker, closes
the active transport, and then performs a bounded worker join before exiting.
The `.venv` is only the Python environment; it is not a separate daemon.

Profile: defaults to `../profiles/orion_studio_sc.json`; override with
`ANTELOPE_PROFILE=/path/to/profile.json`.
