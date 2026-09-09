# webui -- DRAFT

A throwaway prototype of the "local daemon + thin browser UI" architecture
(see the discussion in the main repo's SUMMARY / this sandbox's `SANDBOX.md`).

## What it is

- **`server.py`** -- a small FastAPI daemon. One background thread owns the
  HID device. It pushes two kinds of state to the browser:
  - **fast** -- the free-running `0x73` state and meters, over SSE at up to
    ~25 Hz (channels, buses, brightness, meters). The raw `0x75` diagnostic
    bank is sampled separately at a lower rate.
  - **slow** -- the routing matrix (readback cat `0x03`), virtual mixer
    (cat `0x04`), and Orion AuraVerb state (cat `0x0a`), refreshed one record
    per meter cycle on connect and every 45 s. Route/mixer/AuraVerb writes
    update their serialized caches directly. Queries use Orion's bounded
    category counts or a profile's explicit confirmed layout, so the BusFault
    hazard is never hit.
    The snapshot carries an `rb_ver` counter; the browser refetches the slow
    APIs when it changes.

  Commands are queued as callables run one per meter cycle on the device
  thread, so control bursts cannot monopolize the live meter path.
- **`static/index.html`** -- one file, vanilla JS, no build step:
  - input strips styled after `ideas/PreampUI.svg` -- 270° gain knob
    (drag / wheel), mode select, 48V + Ø buttons, vertical meter;
  - output buses, screen brightness;
  - a **Routing** panel with `Routing | Mix 1 | Mix 2 | Mix 3 | Mix 4` tabs;
    each Mix tab contains a compact horizontal board of vertical strips with
    fader, pan, mute, solo, and the selected raw mixer meter. Orion's Mix 1
    input strips additionally expose the AuraVerb send; Mix 2-4 and all
    master strips deliberately do not. Selecting a Mix tab automatically
    selects its matching mixer meter bank; multiple Solo buttons may be
    stacked and the original mute/solo state is restored when the last Solo
    is released;
  - device-specific panels are selected by the presentation registry in
    `webui/device_ui.py`: Zen Go shows its input-source selectors, while Orion
    Mix 1 exposes the closed-by-default AuraVerb panel;
  - reconnect UX -- the UI dims and goes non-interactive while the device
    is offline, and EventSource reconnects automatically.

  Channel count, modes, gain limits, Hi-Z channels, digital inputs and mixer
  ranges come from the active profile. The daemon autodetects the connected
  VID/PID and exposes only capabilities with safe, profile-declared readback.
  Zen Go renders its two capture-confirmed mixer layouts while routing remains
  hidden until its own readback map is confirmed. The mixer fader artwork is
  served from `/webui/assets/fader-shadow.svg`.

  The Zen Go source selectors are intentionally read-only for now. Its route
  command rewrites a whole group and the safe routing readback is still
  unconfirmed, so the WebUI will not guess the other strip assignments. See
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

Profile: defaults to `../profiles/orion_studio_sc.json`; override with
`ANTELOPE_PROFILE=/path/to/profile.json`.

## If this direction is worth keeping

Copy `webui/` into the real repo (`../antelope-ctl`), add `fastapi` /
`uvicorn` to a `webui/requirements.txt` there (keep `antelope/` itself
stdlib-only), and grow it: routing/mixer panels (bounded readback),
device reconnect UX, a `--host` flag + token for LAN use, a systemd user
unit. Otherwise `rm -rf` this whole sandbox.
