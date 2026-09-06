#!/usr/bin/env python3
"""
antelope-ctl web UI -- DRAFT / sandbox.

A thin local daemon: one background thread owns the HID device, keeps an
in-memory state snapshot, and pushes it to the browser over a WebSocket.
Commands from the browser are queued and executed by that same thread, so
there is exactly one writer/reader on the node.

Two kinds of state:

  * FAST  -- the free-running 0x73 state report + 0x75 meters, parsed every
             loop and streamed at ~12 Hz over SSE (channels, buses,
             brightness, meters). SSE, not a WebSocket, so it needs no
             package beyond fastapi + uvicorn.
  * SLOW  -- the routing matrix (readback cat 0x03) and the virtual mixer
             (readback cat 0x04), refreshed on connect, after every write,
             and on a slow timer. The snapshot carries a monotonic `rb_ver`;
             the browser refetches /api/routing + /api/mixer when it bumps.

⚠ HARDWARE RULE (see ../antelope-ctl/CLAUDE.md "STANDING HARDWARE RULE"):
never query a readback index past a category's record count -- it BusFaults
the Orion (physical power cycle). Every query here goes through
protocol.build_readback_query, which enforces protocol.check_readback_index
against frame.readback.category_counts. The routing/mixer indices we use
(dest groups 0..14 for cat 0x03, mixes 0..3 for cat 0x04) are all inside
those bounds.

Run:  pip install -r requirements.txt  &&  python3 server.py
Then: http://127.0.0.1:8714
"""
import asyncio
import glob
import json
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from antelope import protocol as proto
from antelope.transport import list_connected_hid, open_transport

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(HERE, "..", "profiles")
DEFAULT_PROFILE = os.path.join(PROFILE_DIR, "orion_studio_sc.json")


def _profile_device_ids(path):
    """(vid, pid) as ints from a profile's device block, or None if absent."""
    try:
        with open(path) as f:
            dev = json.load(f).get("device", {})
    except (OSError, ValueError):
        return None
    vid, pid = dev.get("vid"), dev.get("pid")
    if vid is None or pid is None:
        return None
    try:
        return (int(vid, 16) if isinstance(vid, str) else int(vid),
                int(pid, 16) if isinstance(pid, str) else int(pid))
    except (TypeError, ValueError):
        return None


def resolve_profile():
    """Pick the device profile. ANTELOPE_PROFILE (path or profiles/ basename)
    always wins. Otherwise match a connected HID node against profiles/*.json
    by device vid/pid; fall back to the Orion Studio III profile when nothing
    is plugged in, nothing matches, or the host can't be scanned."""
    env = os.environ.get("ANTELOPE_PROFILE")
    if env:
        if not os.path.exists(env):
            cand = os.path.join(PROFILE_DIR, env if env.endswith(".json") else env + ".json")
            if os.path.exists(cand):
                return cand, "ANTELOPE_PROFILE"
        return env, "ANTELOPE_PROFILE"

    connected = list_connected_hid()
    if connected:
        for path in sorted(glob.glob(os.path.join(PROFILE_DIR, "*.json"))):
            ids = _profile_device_ids(path)
            if ids and ids in connected:
                return path, "autodetected"
    return DEFAULT_PROFILE, "default (no match)" if connected else "default (no scan)"


PROFILE_PATH, _profile_why = resolve_profile()
PROFILE = proto.load_profile(PROFILE_PATH)
print(f"[antelope-ctl] profile: {os.path.basename(PROFILE_PATH)} "
      f"-- {PROFILE.get('device', {}).get('name', '?')} ({_profile_why})",
      file=sys.stderr, flush=True)

ROUTING_CAT = proto.ROUTING_READBACK_CATEGORY   # 0x03
MIXER_CAT = proto.MIXER_READBACK_CATEGORY       # 0x04
READBACK_REFRESH_S = 45.0   # slow background poll; a write triggers one immediately

# The free-running meter report and a readback RESPONSE are BOTH magic 0x75.
# They differ only at byte 1: meter = 0x1f, readback response = 0x00 (see
# frame.readback.discriminator_note). transport.read_one() matches byte 0
# only, so meters must be filtered here or a stray readback frame lands in
# the meter array.
METER_DISCRIMINATOR_OFFSET = 1
METER_DISCRIMINATOR = 0x1F

# ---------------------------------------------------------------- device thread

class Device:
    """Owns the HID node. All device I/O happens on .run()'s thread.

    The command queue holds callables `fn(transport)`; the web handlers build
    the closure (so a routing/mixer write can read-modify-write on this
    thread, the only place it is safe to touch the node)."""

    def __init__(self, profile):
        self.profile = profile
        dev = profile["device"]
        self.vid = int(dev["vid"], 16) if isinstance(dev["vid"], str) else dev["vid"]
        self.pid = int(dev["pid"], 16) if isinstance(dev["pid"], str) else dev["pid"]
        self.report_size = profile["transport"]["report_size"]
        self.n_ch = proto.space_channel_count(profile, "input") or 12
        self.n_adat = int(profile.get("adat", {}).get("count", 0))
        self.n_spdif = int(profile.get("spdif", {}).get("count", 0))
        self.bus_ids = sorted(int(x) for x in proto.constraints(profile).get("bus_ids", []))
        self.state_magic = proto.state_report_magic(profile)
        self.meter_magic = proto.meter_report_magic(profile)

        rc = profile["frame"].get("routing_command", {})
        self.route_dests = sorted(int(k) for k in rc.get("destination_channels", {}))
        self.n_mixes = proto.readback_category_count(profile, MIXER_CAT) or 4

        self.cmds = queue.Queue()          # callables: fn(transport) -> None
        self.snapshot = {"online": False}  # last known state, read by the web side
        self.version = 0
        self.rb_ver = 0
        self.routing = {}                  # dest_id(int) -> [(bank, idx), ...]
        self.mixer = {}                    # mix(int)     -> [slot dict, ...]
        self._lock = threading.Lock()
        self._t = None
        self._want_readback = threading.Event()

    def start(self):
        self._t = threading.Thread(target=self.run, daemon=True)
        self._t.start()

    def submit(self, fn, readback=False):
        """Queue fn(transport). readback=True also schedules a routing+mixer
        re-read after it (for route/mix writes). Plain param writes (gain,
        toggle, mode, bus, brightness) show up in the free-running 0x73 stream
        on their own, so they skip the readback pass -- that pass is slow and
        was the source of the knob 'snap back then jump'."""
        self.cmds.put((fn, readback))

    def request_readback(self):
        self._want_readback.set()

    def get(self):
        with self._lock:
            return dict(self.snapshot), self.version

    def routing_json(self):
        with self._lock:
            return {
                str(d): [
                    {"bank": b, "idx": i,
                     "label": proto.route_source_label(self.profile, b, i)}
                    for b, i in pairs
                ]
                for d, pairs in self.routing.items()
            }

    def mixer_json(self):
        with self._lock:
            return {
                str(m): [
                    {"ch": i, "fader": s["fader"], "pan": s["pan"],
                     "send": s["send"], "mute": s["mute"], "solo": s["solo"]}
                    for i, s in enumerate(slots)
                ]
                for m, slots in self.mixer.items()
            }

    def _publish(self, snap):
        with self._lock:
            snap["rb_ver"] = self.rb_ver
            self.snapshot = snap
            self.version += 1

    def run(self):
        transport = None
        while True:
            if transport is None:
                try:
                    transport = open_transport(self.vid, self.pid, self.report_size)
                except SystemExit:
                    self._publish({"online": False})
                    time.sleep(2.0)
                    continue
                self._want_readback.set()
                last_readback = 0.0

            # 1. run queued commands (writes + read-modify-writes)
            ran_cmd = ran_cmd_rb = False
            try:
                while True:
                    fn, want_rb = self.cmds.get_nowait()
                    try:
                        fn(transport)
                        ran_cmd = True
                        ran_cmd_rb = ran_cmd_rb or want_rb
                    except OSError:
                        transport = None
                        break
                    except Exception as e:                       # noqa: BLE001
                        print(f"[cmd] {e!r}", file=sys.stderr)
                    time.sleep(0.02)
            except queue.Empty:
                pass
            if transport is None:
                self._publish({"online": False})
                continue
            if ran_cmd_rb:
                time.sleep(0.15)            # let the device apply before we read it back
                self._want_readback.set()

            # 2. slow state: routing matrix + virtual mixer (bounded readback)
            now = time.time()
            if self._want_readback.is_set() or now - last_readback > READBACK_REFRESH_S:
                self._want_readback.clear()
                try:
                    self._refresh_readback(transport)
                except OSError:
                    transport = None
                    self._publish({"online": False})
                    continue
                last_readback = time.time()

            # 3. fast state: one 0x73 read + one filtered 0x75 read
            try:
                state = transport.read_one(self.state_magic, timeout=0.4)
                meter = self._read_meter(transport, timeout=0.2)
            except OSError:
                transport = None
                self._publish({"online": False})
                continue

            snap = {"online": True, "ts": time.time()}
            if state:
                snap["channels"] = self._parse_channels(state)
                snap["buses"] = self._parse_buses(state)
                snap["adat"] = self._parse_adat(state)
                snap["spdif"] = self._parse_spdif(state)
                snap["trim"] = self._parse_output_trim(state)
                try:
                    snap["brightness"] = proto.parse_state_scalar(
                        self.profile, state, "screen_brightness_byte_offset")
                except Exception:
                    pass
                try:
                    snap["sample_rate_idx"] = proto.parse_state_scalar(
                        self.profile, state, "sample_rate_byte_offset")
                except Exception:
                    pass
                try:
                    snap["clock_source_idx"] = proto.parse_state_scalar(
                        self.profile, state, "clock_source_byte_offset")
                except Exception:
                    pass
                # per-channel input meters: 0x73 @ 157 + channel (confirmed
                # 2026-09-01, see profile state_report.channel_meter_notes).
                snap["meters_db"] = self._parse_meters(state)
                # raw slice of the same region for ?meterdebug=1.
                snap["state_raw"] = {"base": 150, "bytes": list(state[150:236])}
            if meter:
                # 0x75 frame -- on this unit only byte 32 is live (a monitor
                # sum) and byte 33 is a flag; kept for ?meterdebug=1 only.
                base = int(self.profile["frame"]["meter_report"]
                           ["channel_meter_base_offset"])
                snap["meters_raw"] = {"base": base,
                                      "bytes": list(meter[base:base + 32])}
            # keep last values if this cycle only got one of the two frames
            with self._lock:
                for k in ("channels", "buses", "adat", "spdif", "trim", "brightness",
                          "sample_rate_idx", "clock_source_idx", "meters_db", "state_raw"):
                    if k not in snap and k in self.snapshot:
                        snap[k] = self.snapshot[k]
            self._publish(snap)

    # -- readback (routing + mixer) -----------------------------------------

    def _refresh_readback(self, transport):
        """Re-read the routing matrix (cat 0x03) and virtual mixer (cat 0x04).

        Only bounded indices -- build_readback_query raises ConstraintError
        past a category's record count and we skip it, so this can never hit
        the BusFault. A group that simply doesn't answer keeps its last value.
        """
        changed = False
        misses = 0
        for d in self.route_dests:
            try:
                req = proto.build_readback_query(self.profile, ROUTING_CAT, d)
            except proto.ConstraintError:
                continue
            data = transport.query(
                req,
                lambda x, d=d: proto.is_readback_response(self.profile, x, ROUTING_CAT, d),
                timeout=0.5)
            if data is None:
                misses += 1
                if misses >= 4 and not self.routing:
                    break               # device isn't answering readback at all
                continue
            misses = 0
            try:
                _did, pairs = proto.parse_routing_record(
                    self.profile, proto.readback_body(self.profile, data))
            except ValueError:
                continue
            with self._lock:
                if self.routing.get(d) != pairs:
                    self.routing[d] = pairs
                    changed = True

        for m in range(self.n_mixes):
            try:
                req = proto.build_readback_query(self.profile, MIXER_CAT, m)
            except proto.ConstraintError:
                continue
            data = transport.query(
                req,
                lambda x, m=m: proto.is_readback_response(self.profile, x, MIXER_CAT, m),
                timeout=0.5)
            if data is None:
                continue
            try:
                slots = proto.parse_mixer_record(
                    self.profile, proto.readback_body(self.profile, data))
            except ValueError:
                continue
            with self._lock:
                if self.mixer.get(m) != slots:
                    self.mixer[m] = slots
                    changed = True

        if changed:
            with self._lock:
                self.rb_ver += 1

    def _read_meter(self, transport, timeout=0.2):
        """A meter frame, not a readback response. Both are magic 0x75; only
        byte 1 tells them apart (0x1f meter / 0x00 readback). read_one matches
        byte 0 only, so filter here."""
        for data in transport.read_reports(self.meter_magic, timeout):
            if len(data) > METER_DISCRIMINATOR_OFFSET \
                    and data[METER_DISCRIMINATOR_OFFSET] == METER_DISCRIMINATOR:
                return data
        return None

    # -- fast-state parsers ------------------------------------------------

    def _parse_channels(self, data):
        out = []
        for ch in range(self.n_ch):
            try:
                s = proto.parse_state(self.profile, data, ch)
            except ValueError:
                break
            out.append({
                "ch": ch,
                "gain": s["gain"],
                "mode": proto.mode_name(self.profile, s.get("input_mode", -1)),
                "phantom": bool(s.get("phantom")),
                "phase_invert": bool(s.get("phase_invert")),
            })
        return out

    def _parse_buses(self, data):
        out = []
        for bid in self.bus_ids:
            try:
                b = proto.parse_bus_state(self.profile, data, bid)
            except ValueError:
                continue
            out.append({
                "bus": bid,
                "name": proto.bus_name(self.profile, bid),
                "level": b["level"],
                "dim": bool(b.get("dim")),
                "mute": bool(b.get("mute")),
                "mono": bool(b.get("mono")),
            })
        return out

    def _parse_adat(self, data):
        """The 16 ADAT input gains (int8 dB) from the 0x73 state report at
        state_report.adat_gain_base_offset + channel. ADAT has gain + link
        only -- no mode / phantom / phase / meter. See profile["adat"]."""
        out = []
        for ch in range(self.n_adat):
            try:
                out.append({"ch": ch,
                            "gain": proto.parse_adat_gain(self.profile, data, ch)})
            except ValueError:
                break
        return out

    def _parse_spdif(self, data):
        """The 2 S/PDIF input gains (0 = L, 1 = R), int8 dB, from
        state_report.spdif_gain_base_offset + channel. Gain + link only."""
        out = []
        for ch in range(self.n_spdif):
            try:
                out.append({"ch": ch,
                            "gain": proto.parse_spdif_gain(self.profile, data, ch)})
            except ValueError:
                break
        return out

    def _parse_output_trim(self, data):
        """The 3 settings-tab output-trim selectors (0-6) from the packed
        state_report.output_trim_block: target 0 = Monitor A, 1 = Monitor B,
        2 = Line Out. Physical meaning of the 7 steps is not decoded -- raw
        index only (see profile params.output_trim)."""
        blk = self.profile["frame"]["state_report"].get("output_trim_block")
        if not blk:
            return {}
        out = {}
        names = {0: "monitor_a", 1: "monitor_b", 2: "line_out"}
        for key, f in blk.get("fields", {}).items():
            off = int(f["byte_offset"])
            if off >= len(data):
                continue
            tgt = int(key.rsplit("_", 1)[1])
            mask = int(f["mask"], 16) if isinstance(f["mask"], str) else int(f["mask"])
            out[names.get(tgt, str(tgt))] = (data[off] & mask) >> int(f["shift"])
        return out

    def _parse_meters(self, state):
        """Per-channel input meters from the 0x73 state report at
        state_report.channel_meter_base_offset (157) + channel. Inverted scale,
        reuse meter_report.db_curve (raw ~= -dBFS)."""
        base = self.profile["frame"]["state_report"].get("channel_meter_base_offset")
        if base is None:
            return []
        base = int(base)
        out = []
        for ch in range(self.n_ch):
            off = base + ch
            if off >= len(state):
                break
            db = proto.raw_to_db(self.profile, state[off])
            out.append(round(db, 1) if db is not None else None)
        return out


try:
    DEV = Device(PROFILE)
except (KeyError, ValueError, TypeError) as _e:
    # Device.__init__ only reads the profile dict (no I/O). Many non-Orion
    # profiles are still stubs -- an autodetected one that can't build a
    # Device would crash the daemon, so fall back to the default and let the
    # user finish that JSON. An explicit ANTELOPE_PROFILE is left to fail.
    if _profile_why != "autodetected" or os.path.abspath(PROFILE_PATH) == os.path.abspath(DEFAULT_PROFILE):
        raise
    print(f"[antelope-ctl] {os.path.basename(PROFILE_PATH)} is incomplete "
          f"({type(_e).__name__}: {_e}) -- falling back to the default profile; "
          f"finish that JSON to use the detected device",
          file=sys.stderr, flush=True)
    PROFILE_PATH, _profile_why = DEFAULT_PROFILE, "default (detected profile incomplete)"
    PROFILE = proto.load_profile(PROFILE_PATH)
    DEV = Device(PROFILE)

# ---------------------------------------------------------------- HTTP / WS

app = FastAPI(title="antelope-ctl webui (draft)")


class Gain(BaseModel):
    channel: int
    db: int

class Toggle(BaseModel):
    channel: int
    param: str          # "phantom" | "phase_invert"
    on: bool

class Mode(BaseModel):
    channel: int
    mode: str           # "mic" | "line" | "hiz" | "direct"

class Link(BaseModel):
    pair: int           # 0-based, pair N = channels 2N & 2N+1
    enabled: bool

class DigGain(BaseModel):
    channel: int        # ADAT 0-15 / S-PDIF 0=L 1=R
    db: int

class DigLink(BaseModel):
    pair: int           # ADAT: 0-7 (ch 2N & 2N+1). S-PDIF: only 0 (L+R)
    enabled: bool

class Trim(BaseModel):
    target: int         # 0 = Monitor A, 1 = Monitor B, 2 = Line Out
    value: int          # 0..6

class BusToggle(BaseModel):
    bus: int
    param: str          # "dim" | "mute" | "mono"
    on: bool

class GlobalToggle(BaseModel):
    on: bool

class EmuMic(BaseModel):
    channel: int
    enabled: bool
    pattern: int | None = None   # model 0: 0..100 morph (0 omni / 50 card / 100 fig-8)
    model: int | None = None     # 0 = EdgeDuo raw
    swap: bool | None = None

class Scalar(BaseModel):
    value: int

class Bus(BaseModel):
    bus: int
    level: int

class Route(BaseModel):
    dest: int
    channel: int              # 0-based output channel within the group
    kind: str                 # "preamp" | "compplay" | ... | "mix1".."mix4" | "spdif" | "mute"
    number: int | str | None = None   # 1-based for numbered banks, "L"/"R" for stereo

class RouteChange(BaseModel):
    channel: int
    kind: str
    number: int | str | None = None

class RouteBatch(BaseModel):
    dest: int
    changes: list[RouteChange]

class MixStrip(BaseModel):
    mix: int                  # 0-based
    channel: int              # 0 = mix master, 1..32 = input strips
    fader: int | None = None  # dB of attenuation, 0..90 (sign ignored)
    pan: int | None = None    # -30..+30
    send: int | None = None   # 0..96
    mute: bool | None = None
    solo: bool | None = None


def _bad(msg):
    return JSONResponse({"ok": False, "error": msg}, status_code=400)


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/profile")
def api_profile():
    return PROFILE


_MIC_MODELS_PATH = os.path.join(os.path.dirname(PROFILE_PATH), "mic_models.json")

@app.get("/api/mic_models")
def api_mic_models():
    """The emuMic model catalogue (profiles/mic_models.json). Account-bound --
    it's one account's snapshot, and the id->model mapping may not match the
    user's own pack set. Returns {} if the file isn't present."""
    try:
        with open(_MIC_MODELS_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


@app.get("/api/state")
def api_state():
    snap, ver = DEV.get()
    return {"version": ver, **snap}


@app.post("/api/gain")
def api_gain(g: Gain):
    proto.check_target(PROFILE, g.channel, "input")
    DEV.submit(lambda t: t.write(proto.build_command(PROFILE, "gain", g.channel, g.db)))
    return {"ok": True}


@app.post("/api/toggle")
def api_toggle(t: Toggle):
    if t.param not in ("phantom", "phase_invert"):
        return _bad("bad param")
    proto.check_target(PROFILE, t.channel, "input")
    val = 1 if t.on else 0
    DEV.submit(lambda tr: tr.write(proto.build_command(PROFILE, t.param, t.channel, val)))
    return {"ok": True}


@app.post("/api/link")
def api_link(l: Link):
    """Engage/disengage a preamp-pair link (SET_LINK, frame.link_command).
    There is NO device-side link-status readback, so the browser tracks link
    state itself and the mode/gain sync a Launcher would send is done there
    too -- this endpoint only puts the raw link frame on the wire."""
    npairs = int(PROFILE["channels"].get("link_pairs", {}).get("count", 0))
    if not (0 <= l.pair < npairs):
        return _bad(f"pair {l.pair} out of range 0..{npairs - 1}")
    try:
        pkt = proto.build_link_command(PROFILE, l.pair, l.enabled)
    except (KeyError, proto.ConstraintError) as e:                # noqa: BLE001
        return _bad(str(e))
    DEV.submit(lambda t: t.write(pkt))
    return {"ok": True}


def _dig_gain(space, param, rng, g: "DigGain"):
    """Shared ADAT / S-PDIF gain write. Both are int8-dB SET_PARAM params
    (adat_gain 0x5b / spdif_gain 0x5c) on their own address space; neither
    has a status byte. No constraints.* bounds are defined for these indices,
    so clamp the channel here before it hits the wire."""
    n = DEV.n_adat if space == "adat" else DEV.n_spdif
    if not (0 <= g.channel < n):
        return _bad(f"{space} channel {g.channel} out of range 0..{n - 1}")
    lo, hi = rng
    db = max(lo, min(hi, g.db))
    DEV.submit(lambda t: t.write(proto.build_command(PROFILE, param, g.channel, db)))
    return {"ok": True}


@app.post("/api/adat-gain")
def api_adat_gain(g: DigGain):
    return _dig_gain("adat", "adat_gain", proto.adat_gain_range(PROFILE), g)


@app.post("/api/spdif-gain")
def api_spdif_gain(g: DigGain):
    rng = PROFILE["params"].get("spdif_gain", {}).get("range", [-128, 127])
    return _dig_gain("spdif", "spdif_gain", rng, g)


def _dig_link(space_name, space_byte, npairs, l: "DigLink"):
    """SET_LINK for the ADAT (space 0) / S-PDIF (space 1) domains. No device
    readback -- the browser tracks link state, like the preamp link. NOTE the
    ADAT link frame is byte-identical to the physical one (both space 0), so a
    space-0 SET_LINK for pair N may also move physical pair N -- see
    params.adat_channel_link.notes."""
    if not (0 <= l.pair < npairs):
        return _bad(f"{space_name} pair {l.pair} out of range 0..{npairs - 1}")
    try:
        pkt = proto.build_link_command(PROFILE, l.pair, l.enabled, space=space_byte)
    except (KeyError, proto.ConstraintError) as e:                # noqa: BLE001
        return _bad(str(e))
    DEV.submit(lambda t: t.write(pkt))
    return {"ok": True}


@app.post("/api/adat-link")
def api_adat_link(l: DigLink):
    n = int(PROFILE.get("adat", {}).get("link_pairs", {}).get("count", 0))
    return _dig_link("adat", 0, n, l)


@app.post("/api/spdif-link")
def api_spdif_link(l: DigLink):
    n = int(PROFILE.get("spdif", {}).get("link_pairs", {}).get("count", 0))
    return _dig_link("spdif", 1, n, l)


@app.post("/api/output-trim")
def api_output_trim(t: Trim):
    """Settings-tab output-trim selector (param 0x4b, SET_PARAM). 3 targets
    (0/1/2 = Monitor A / B / Line Out), 7-position selector 0..6 -- the raw
    index is all the capture pinned; the physical dB meaning is not decoded.
    Reads back in state_report.output_trim_block."""
    if not (0 <= t.target <= 2):
        return _bad(f"trim target {t.target} out of range 0..2")
    v = max(0, min(6, t.value))
    DEV.submit(lambda tr: tr.write(proto.build_command(PROFILE, "output_trim", t.target, v)))
    return {"ok": True}


@app.post("/api/bus-toggle")
def api_bus_toggle(t: BusToggle):
    """bus_dim / bus_mute / bus_mono (SET_PARAM 0x68 / 0x48 / 0x69), bus id at
    the channel offset. Confirmed for monitor buses; bus_mute also confirmed on
    the line output (bus 3). dim/mono may not apply to line/reamp."""
    pname = {"dim": "bus_dim", "mute": "bus_mute", "mono": "bus_mono"}.get(t.param)
    if pname is None:
        return _bad("bad param -- dim|mute|mono")
    DEV.submit(lambda tr: tr.write(proto.build_command(PROFILE, pname, t.bus, 1 if t.on else 0)))
    return {"ok": True}


@app.post("/api/dc-coupling")
def api_dc_coupling(t: GlobalToggle):
    """Output DC-coupling on/off (param 0x26, SET_GLOBAL 0x12). No 0x73
    readback -- the browser tracks the state, like the preamp link."""
    DEV.submit(lambda tr: tr.write(proto.build_global_command(PROFILE, "dc_coupling", 1 if t.on else 0)))
    return {"ok": True}


@app.post("/api/emumic")
def api_emumic(e: EmuMic):
    """emuMic / mic-modeling DSP toggle (SET_MIC_MODELING, 0x17/0xe5).
    Preamps 5-12 (the EMU button is Mic-mode-gated). No device readback --
    the browser tracks state. This
    endpoint does NOT do the Launcher's side effects (auto 48V, pair link)."""
    fr = PROFILE["frame"].get("micmodeling_command")
    if not fr:
        return _bad("this device has no mic modeling")
    chans = fr.get("channels") or []
    if e.channel not in chans:
        return _bad(f"channel {e.channel} has no EMU button (channels {chans})")
    kw = {}
    if e.pattern is not None: kw["pattern"] = e.pattern
    if e.model is not None:   kw["model"] = e.model
    if e.swap is not None:    kw["swap"] = e.swap
    try:
        pkt = proto.build_micmodeling_command(PROFILE, e.channel, e.enabled, **kw)
    except (KeyError, ValueError, proto.ConstraintError) as ex:   # noqa: BLE001
        return _bad(str(ex))
    DEV.submit(lambda t: t.write(pkt))
    return {"ok": True}


@app.post("/api/mode")
def api_mode(m: Mode):
    proto.check_target(PROFILE, m.channel, "input")
    try:
        val = proto.mode_value(PROFILE, m.mode)
        proto.check_enum(PROFILE, "input_mode_allowed_values", val, "input_mode")
    except Exception as e:                                       # noqa: BLE001
        return _bad(str(e))
    DEV.submit(lambda t: t.write(proto.build_command(PROFILE, "input_mode", m.channel, val)))
    return {"ok": True}


@app.post("/api/sample-rate")
def api_sample_rate(s: Scalar):
    """Device sample rate (SET_GLOBAL 0x12 / param 0x03), enum index 0..6.
    Reads back in the 0x73 stream as sample_rate_idx. DISRUPTIVE -- the device
    drops audio and re-locks its clock (~1 s). The Orion IGNORES this write
    while the host holds the USB audio interface streaming, and also while the
    clock source is USB (it defers to the host clock) -- see
    params.sample_rate.notes; the browser surfaces that when the write doesn't
    land."""
    vals = PROFILE["params"].get("sample_rate", {}).get("values", {})
    if not vals:
        return _bad("this profile has no params.sample_rate")
    if str(s.value) not in vals:
        return _bad(f"sample-rate index {s.value} not in {sorted(int(k) for k in vals)}")
    DEV.submit(lambda t: t.write(proto.build_global_command(PROFILE, "sample_rate", s.value)))
    return {"ok": True}


@app.post("/api/clock-source")
def api_clock_source(s: Scalar):
    """Device clock source (SET_GLOBAL 0x12 / param 0x04), enum index 0..6
    (0 = Oven ... 6 = USB, see params.clock_source.values). Reads back in the
    0x73 stream as clock_source_idx. DISRUPTIVE -- selecting a source that is
    not present/locked unlocks the device clock. Same host-streaming caveat as
    the sample rate."""
    vals = PROFILE["params"].get("clock_source", {}).get("values", {})
    if not vals:
        return _bad("this profile has no params.clock_source")
    if str(s.value) not in vals:
        return _bad(f"clock-source index {s.value} not in {sorted(int(k) for k in vals)}")
    DEV.submit(lambda t: t.write(proto.build_global_command(PROFILE, "clock_source", s.value)))
    return {"ok": True}


@app.post("/api/brightness")
def api_brightness(s: Scalar):
    v = max(0, min(100, s.value))
    DEV.submit(lambda t: t.write(proto.build_global_command(PROFILE, "screen_brightness", v)))
    return {"ok": True}


@app.post("/api/bus")
def api_bus(b: Bus):
    proto.check_target(PROFILE, b.bus, "bus")
    lo, hi = proto.bus_level_range(PROFILE)
    v = max(lo, min(hi, b.level))
    DEV.submit(lambda t: t.write(proto.build_command(PROFILE, "bus_level", b.bus, v)))
    return {"ok": True}


# -- routing ---------------------------------------------------------------

@app.get("/api/routing")
def api_routing():
    rc = PROFILE["frame"].get("routing_command", {})
    dc = rc.get("destination_channels", {})
    addr = rc.get("addressable_destinations", {})
    stereo = set(rc.get("stereo_destinations", []))
    dests = [
        {"id": int(k), "name": addr.get(k, f"dest{k}"),
         "channels": int(v), "stereo": k in stereo}
        for k, v in sorted(dc.items(), key=lambda x: int(x[0]))
    ]
    sources = []
    for name, (_bank, _first, count, label, base) in proto.ROUTE_SOURCE_SPECS.items():
        sources.append({"kind": name, "label": label, "count": count,
                        "base": base, "stereo": False})
    for name in proto.ROUTE_STEREO_SOURCE_BANKS:
        sources.append({"kind": name, "label": name, "count": 2,
                        "base": None, "stereo": True})
    sources.append({"kind": "mute", "label": "MUTE", "count": 0,
                    "base": None, "stereo": False})
    return {"dests": dests, "sources": sources, "current": DEV.routing_json()}


@app.post("/api/route")
def api_route(r: Route):
    dc = PROFILE["frame"].get("routing_command", {}).get("destination_channels", {})
    if str(r.dest) not in dc:
        return _bad(f"unknown routing destination {r.dest}")
    nch = int(dc[str(r.dest)])
    if not 0 <= r.channel < nch:
        return _bad(f"channel {r.channel} out of range 0..{nch - 1} for dest {r.dest}")
    try:
        tgt = proto.ROUTE_MUTE if r.kind == "mute" \
            else proto.resolve_route_source(PROFILE, r.kind, r.number)
    except ValueError as e:
        return _bad(str(e))

    def do(t, dest=r.dest, ch=r.channel, tgt=tgt):
        req = proto.build_readback_query(PROFILE, ROUTING_CAT, dest)
        data = t.query(
            req, lambda x: proto.is_readback_response(PROFILE, x, ROUTING_CAT, dest),
            timeout=1.5)
        if data is None:
            raise RuntimeError(f"no routing readback for dest {dest} -- not writing blind")
        _d, pairs = proto.parse_routing_record(PROFILE, proto.readback_body(PROFILE, data))
        pairs = list(pairs)
        pairs[ch] = tgt
        t.write(proto.build_route_command(PROFILE, dest, pairs))

    DEV.submit(do, readback=True)
    return {"ok": True}


@app.post("/api/route-batch")
def api_route_batch(b: RouteBatch):
    """Several route changes for ONE destination group in a single
    read-modify-write (one 0x74 readback + one 0x53 write) -- for the matrix
    group ops (1:1, mute all) and, later, patchbay group drops. Same
    'refuse to write blind' guard as /api/route."""
    dc = PROFILE["frame"].get("routing_command", {}).get("destination_channels", {})
    if str(b.dest) not in dc:
        return _bad(f"unknown routing destination {b.dest}")
    nch = int(dc[str(b.dest)])
    if not b.changes:
        return _bad("no changes")
    resolved = []
    for c in b.changes:
        if not 0 <= c.channel < nch:
            return _bad(f"channel {c.channel} out of range 0..{nch - 1} for dest {b.dest}")
        try:
            tgt = proto.ROUTE_MUTE if c.kind == "mute" \
                else proto.resolve_route_source(PROFILE, c.kind, c.number)
        except ValueError as e:                                  # noqa: BLE001
            return _bad(str(e))
        resolved.append((c.channel, tgt))

    def do(t, dest=b.dest, changes=resolved):
        req = proto.build_readback_query(PROFILE, ROUTING_CAT, dest)
        data = t.query(
            req, lambda x: proto.is_readback_response(PROFILE, x, ROUTING_CAT, dest),
            timeout=1.5)
        if data is None:
            raise RuntimeError(f"no routing readback for dest {dest} -- not writing blind")
        _d, pairs = proto.parse_routing_record(PROFILE, proto.readback_body(PROFILE, data))
        pairs = list(pairs)
        for ch, tgt in changes:
            pairs[ch] = tgt
        t.write(proto.build_route_command(PROFILE, dest, pairs))

    DEV.submit(do, readback=True)
    return {"ok": True, "n": len(resolved)}


# -- virtual mixer -------------------------------------------------------

@app.get("/api/mixer")
def api_mixer():
    p = PROFILE.get("params", {})
    return {
        "n_mixes": DEV.n_mixes,
        "has_send": proto.mix_has_send(PROFILE),
        "ranges": {
            "fader": p.get("mix_fader", {}).get("range", [0, 90]),
            "pan": p.get("mix_pan", {}).get("range", [-30, 30]),
            "send": p.get("mix_send", {}).get("range", [0, 96]),
        },
        "current": DEV.mixer_json(),
    }


@app.post("/api/mix")
def api_mix(s: MixStrip):
    if not 0 <= s.mix < DEV.n_mixes:
        return _bad(f"mix {s.mix} out of range 0..{DEV.n_mixes - 1}")
    if not 0 <= s.channel <= 32:
        return _bad(f"channel {s.channel} out of range 0..32 (0 = master)")
    has_send = proto.mix_has_send(PROFILE)

    def do(t, m=s.mix, ch=s.channel):
        req = proto.build_readback_query(PROFILE, MIXER_CAT, m)
        data = t.query(
            req, lambda x: proto.is_readback_response(PROFILE, x, MIXER_CAT, m),
            timeout=1.5)
        if data is None:
            raise RuntimeError(f"no mixer readback for mix {m} -- not writing blind")
        slots = proto.parse_mixer_record(PROFILE, proto.readback_body(PROFILE, data))
        cur = slots[ch] if ch < len(slots) else {
            "fader": 0, "pan": 0, "send": 0, "mute": False, "solo": False}
        fader = cur["fader"] if s.fader is None else max(0, min(90, abs(s.fader)))
        pan = cur["pan"] if s.pan is None else max(-30, min(30, s.pan))
        send = cur["send"] if s.send is None else max(0, min(96, s.send))
        mute = cur["mute"] if s.mute is None else bool(s.mute)
        solo = cur["solo"] if s.solo is None else bool(s.solo)
        t.write(proto.build_mix_command(PROFILE, m, ch, fader, pan,
                                        send if has_send else 0, mute, solo))

    DEV.submit(do, readback=True)
    return {"ok": True}


@app.get("/api/stream")
async def stream():
    """Server-Sent Events: one JSON snapshot per line whenever the version
    bumps, ~12 Hz. EventSource on the browser side reconnects on its own."""
    async def gen():
        last = -1
        # prime the stream so a just-connected client gets state immediately
        while True:
            snap, ver = DEV.get()
            if ver != last:
                last = ver
                yield f"data: {json.dumps({'version': ver, **snap})}\n\n"
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.08)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    DEV.start()
    uvicorn.run(app, host="127.0.0.1", port=8714, log_level="warning")
