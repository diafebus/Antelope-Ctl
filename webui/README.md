# webui -- DRAFT

A throwaway prototype of the "local daemon + thin browser UI" architecture
(see the discussion in the main repo's SUMMARY / this sandbox's `SANDBOX.md`).

## What it is

- **`server.py`** -- a small FastAPI daemon. One background thread owns the
  HID device. It pushes two kinds of state to the browser:
  - **fast** -- the free-running `0x73` state + `0x75` meters, over a
    WebSocket at ~12 Hz (channels, buses, brightness, meters).
  - **slow** -- the routing matrix (readback cat `0x03`) and virtual mixer
    (cat `0x04`), refreshed on connect / after each write / on a 20 s
    timer. Every query is bounds-checked by
    `protocol.check_readback_index`, so the BusFault hazard is never hit.
    The snapshot carries an `rb_ver` counter; the browser refetches
    `/api/routing` + `/api/mixer` when it changes.

  Commands are queued as callables run on the device thread, so a
  routing/mixer write can read-modify-write there (the only safe place).
- **`static/index.html`** -- one file, vanilla JS, no build step:
  - input strips styled after `ideas/PreampUI.svg` -- 270° gain knob
    (drag / wheel), mode select, 48V + Ø buttons, vertical meter;
  - output buses, screen brightness;
  - a **routing matrix** panel (collapsible per destination group) and a
    **virtual mixer** panel (per mix: master + 32 strips);
  - reconnect UX -- the UI dims and goes non-interactive while the device
    is offline, the WebSocket reconnects with backoff.

  Channel count, modes, gain limits, Hi-Z channels and the mixer ranges
  all come from `GET /api/profile` / `/api/routing` / `/api/mixer`, so a
  different device profile gets a UI without frontend changes.

## What it deliberately does NOT do

- **No unbounded readback.** Routing/mixer indices are always inside
  `frame.readback.category_counts`; it never sweeps.
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
