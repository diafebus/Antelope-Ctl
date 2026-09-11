#!/usr/bin/env python3
"""
antelope-ctl web UI -- DRAFT / sandbox.

A thin local daemon: one background thread owns the HID device, keeps an
in-memory state snapshot, and pushes it to the browser over SSE.
Commands from the browser are queued and executed by that same thread, so
there is exactly one writer/reader on the node.

Two kinds of state:

  * FAST  -- the free-running 0x73 state report, including visible meters,
             parsed every loop and streamed at ~25 Hz over SSE (channels,
             buses, brightness, meters). The 0x75 bank is retained only for
             lower-rate diagnostics.
  * SLOW  -- routing (readback cat 0x03), virtual mixer (cat 0x04),
             profile-confirmed Gazelle Reverb state, and profile-declared
             nested readback records, refreshed incrementally on connect and
             on a slow timer. Writes use and update their serialized caches,
             querying first if not populated yet. The snapshot carries a
             monotonic `rb_ver`; the browser refetches the slow APIs when it
             bumps.

⚠ HARDWARE RULE (see ../antelope-ctl/CLAUDE.md "STANDING HARDWARE RULE"):
never query a readback index past a category's record count -- it BusFaults
the Orion (physical power cycle). Every query here goes through
protocol.build_readback_query. Orion uses its enumerated category counts;
profiles without those counts can only use explicitly capture-confirmed
feature layouts, such as the Zen Go mixer records.

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
from webui.device_ui import features_for

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
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
UI_FEATURES = features_for(PROFILE_PATH, PROFILE)
print(f"[antelope-ctl] profile: {os.path.basename(PROFILE_PATH)} "
      f"-- {PROFILE.get('device', {}).get('name', '?')} ({_profile_why})",
      file=sys.stderr, flush=True)

ROUTING_CAT = proto.ROUTING_READBACK_CATEGORY   # 0x03
MIXER_CAT = proto.MIXER_READBACK_CATEGORY       # 0x04
READBACK_REFRESH_S = 45.0   # slow background poll, one record per fast-state cycle

STRUCTURED_READBACK_SAFE_STATUSES = frozenset({
    "confirmed", "capture-confirmed",
})


def _record_layout_indices(layout):
    """Return the explicitly declared outer indices for one nested layout."""
    try:
        if layout.get("index") is not None:
            return [proto._as_int(layout["index"])]
        lo, hi = layout["index_range"]
        lo, hi = proto._as_int(lo), proto._as_int(hi)
        return list(range(lo, hi + 1)) if lo <= hi else []
    except (KeyError, TypeError, ValueError):
        return []


def _confirmed_profile_block(block):
    """Whether a profile metadata block is safe to drive automatically."""
    return isinstance(block, dict) and str(block.get("status", "")).strip().lower() in \
        STRUCTURED_READBACK_SAFE_STATUSES


def _mixer_surface_spec(profile):
    """Return a confirmed profile-defined mixer-surface selector, if any."""
    spec = (profile.get("mixer", {}) or {}).get("surface_selection")
    if not _confirmed_profile_block(spec):
        return None
    values = spec.get("value_by_mix")
    return spec if isinstance(values, dict) else None


def _mixer_surface_value(profile, mix):
    """Resolve a logical mixer index to its profile-defined selector value."""
    spec = _mixer_surface_spec(profile)
    if spec is None:
        return None
    values = spec.get("value_by_mix", {})
    raw = values.get(str(mix), values.get(mix))
    if raw is None:
        return None
    try:
        return proto._as_int(raw)
    except (TypeError, ValueError):
        return None


def _mixer_surface_for_value(profile, value):
    """Resolve a state-report selector value to its logical mixer index."""
    spec = _mixer_surface_spec(profile)
    if spec is None:
        return None
    for mix, raw in spec.get("value_by_mix", {}).items():
        try:
            if proto._as_int(raw) == value:
                return proto._as_int(mix)
        except (TypeError, ValueError):
            continue
    return None


def _mixer_surface_packet(profile, mix):
    """Build a confirmed profile-defined mixer surface selection command."""
    spec = _mixer_surface_spec(profile)
    value = _mixer_surface_value(profile, mix)
    if spec is None or value is None:
        return None
    target = proto._as_int(spec.get("target", 0))
    param = spec.get("param")
    if isinstance(param, str) and param in profile.get("params", {}):
        packet = proto.build_command(profile, param, target, value)
    else:
        packet = proto.build_raw_command(profile, proto._as_int(param), target, value)
    return packet, value, target


def _structured_readback_targets(profile):
    """Yield safe ``(category, index)`` targets from record_layouts.

    A nested body schema is not enough to authorize an outer query.  Only the
    profile statuses that carry capture-confirmed outer-index evidence are
    scheduled by the daemon; schema-only entries remain visible through the
    metadata API with ``capture_required`` set.
    """
    layouts = profile.get("frame", {}).get("readback", {}).get(
        "record_layouts", []) or []
    if isinstance(layouts, dict):
        layouts = list(layouts.values())
    seen = set()
    for layout in layouts:
        if not isinstance(layout, dict):
            continue
        if str(layout.get("status", "")).strip().lower() not in \
                STRUCTURED_READBACK_SAFE_STATUSES:
            continue
        try:
            category = proto._as_int(layout["category"])
        except (KeyError, TypeError, ValueError):
            continue
        kind = layout.get("kind")
        for index in _record_layout_indices(layout):
            target = (category, index)
            if target in seen:
                continue
            try:
                # Keep the safety guard in the final scheduling path too. This
                # also handles profiles that declare a malformed range or an
                # index outside their category_counts.
                proto.check_readback_index(profile, category, index)
                if proto.readback_record_layout(profile, category, index,
                                                kind=kind) is None:
                    continue
            except (KeyError, proto.ConstraintError, TypeError, ValueError):
                continue
            seen.add(target)
            yield target

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
        readback_magic = profile["frame"].get("readback", {}).get("response_magic")
        self.meter_shares_readback_magic = (
            isinstance(readback_magic, str)
            and self.meter_magic == int(readback_magic, 0))

        rc = profile["frame"].get("routing_command", {})
        self.route_dests = sorted(int(k) for k in rc.get("destination_channels", {}))
        mixer = profile.get("mixer", {})
        self.n_mixes = int(mixer.get("mixes")
                           or proto.readback_category_count(profile, MIXER_CAT) or 0)
        self.mix_channels = int(mixer.get("channels_per_mix", 0))
        self.mixer_has_master = bool(mixer.get("has_master", True))
        layout_indices = proto.readback_layout_indices(
            profile, MIXER_CAT, kind="mixer_state")
        category_count = proto.readback_category_count(profile, MIXER_CAT)
        self.mixer_indices = layout_indices or (
            list(range(category_count)) if category_count is not None else [])
        input_routing = mixer.get("input_routing", {}) or {}
        self.mixer_source_destinations = [
            int(dest) for dest in input_routing.get("destinations", [])]
        self.routing_readback = proto.readback_indices_available(
            profile, ROUTING_CAT, self.route_dests)
        self.mixer_readback = bool(
            self.n_mixes and all(m in self.mixer_indices
                                 for m in range(self.n_mixes)))
        self.routing_available = bool(self.route_dests and self.routing_readback)
        self.mixer_available = bool(
            self.n_mixes and self.mix_channels and self.mixer_readback
            and profile["frame"].get("mix_command"))
        self.mixer_source_available = bool(
            self.mixer_available
            and self.routing_available
            and self.mixer_source_destinations
            and all(dest in self.route_dests
                    and proto.route_dest_channels(profile, dest) >= self.mix_channels
                    for dest in self.mixer_source_destinations)
            and proto.readback_indices_available(
                profile, ROUTING_CAT, self.mixer_source_destinations))

        self.cmds = queue.Queue()          # callables: fn(transport) -> None
        self.snapshot = {"online": False}  # last known state, read by the web side
        self.version = 0
        self.rb_ver = 0
        self.routing = {}                  # dest_id(int) -> [(bank, idx), ...]
        self.mixer = {}                    # mix(int)     -> [slot dict, ...]
        self.auraverb = {}                 # readback index -> list of mix dicts
        self.structured = {}               # (category, index) -> parsed records
        auraverb_target = proto.auraverb_readback_target(profile)
        self.auraverb_category = (auraverb_target[0]
                                  if auraverb_target is not None
                                  else proto.AURAVERB_READBACK_CATEGORY)
        self.auraverb_index = (auraverb_target[1]
                               if auraverb_target is not None else 0)
        self.auraverb_available = proto.auraverb_readback_available(profile)
        self.solo_state = {}               # mix -> {restore: flags, active: channels}
        self._lock = threading.Lock()
        self._t = None

    def start(self):
        self._t = threading.Thread(target=self.run, daemon=True)
        self._t.start()

    def submit(self, fn):
        """Queue fn(transport). At most one queued function runs per fast
        state cycle, so a burst of controls cannot starve meter updates."""
        self.cmds.put(fn)

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

    def auraverb_json(self):
        with self._lock:
            records = self.auraverb.get(self.auraverb_index)
            if records is None:
                return None
            return [{
                "params": dict(record.get("params", {})),
                "enabled": record.get("enabled"),
                "wet": record.get("wet"),
            } for record in records]

    def structured_readbacks_json(self):
        """Serialize profile-declared nested readbacks for the WebUI.

        ``raw`` bytes are represented as hex so this endpoint stays ordinary
        JSON.  Unsafe schema-only layouts are included as metadata, but their
        ``current`` map is deliberately empty because the daemon never probes
        their unbounded outer indices.
        """
        layouts = self.profile.get("frame", {}).get("readback", {}).get(
            "record_layouts", []) or []
        if isinstance(layouts, dict):
            layouts = list(layouts.values())
        with self._lock:
            cached = dict(self.structured)
        out = []
        for layout in layouts:
            if not isinstance(layout, dict):
                continue
            try:
                category = proto._as_int(layout["category"])
            except (KeyError, TypeError, ValueError):
                continue
            indices = _record_layout_indices(layout)
            status = str(layout.get("status", ""))
            safe = status.strip().lower() in STRUCTURED_READBACK_SAFE_STATUSES
            current = {}
            if safe:
                for index in indices:
                    records = cached.get((category, index))
                    if records is None:
                        continue
                    current[str(index)] = [
                        {key: (value.hex() if isinstance(value, bytes) else value)
                         for key, value in record.items()}
                        for record in records
                    ]
            item = {
                "kind": layout.get("kind"),
                "name": layout.get("name", layout.get("kind", "readback")),
                "category": category,
                "status": status,
                "safe": safe,
                "capture_required": not safe,
                "indices": indices,
                "record_count": layout.get("record_count"),
                "record_stride": layout.get("record_stride"),
                "fields": layout.get("fields", []),
                "current": current,
            }
            if layout.get("index") is not None:
                item["index"] = proto._as_int(layout["index"])
            elif layout.get("index_range") is not None:
                item["index_range"] = list(layout["index_range"])
            out.append(item)
        return {
            "available": bool(out),
            "refresh_seconds": READBACK_REFRESH_S,
            "layouts": out,
        }

    def _publish(self, snap):
        with self._lock:
            snap["rb_ver"] = self.rb_ver
            self.snapshot = snap
            self.version += 1

    def _cache_routing(self, dest, pairs):
        """Store the serialized routing record after a successful write."""
        with self._lock:
            if self.routing.get(dest) == pairs:
                return
            self.routing[dest] = pairs
            self.rb_ver += 1

    def _cache_mixer(self, mix, slots):
        """Store the serialized mixer record after a successful write."""
        with self._lock:
            if self.mixer.get(mix) == slots:
                return
            self.mixer[mix] = slots
            self.rb_ver += 1

    def _cache_auraverb(self, records):
        with self._lock:
            if self.auraverb.get(self.auraverb_index) == records:
                return
            self.auraverb[self.auraverb_index] = records
            self.rb_ver += 1

    def _routing_record_for_write(self, transport, dest):
        """Copy the serialized cache, querying once only if it is not ready."""
        with self._lock:
            cached = self.routing.get(dest)
            if cached is not None:
                return list(cached)
        req = proto.build_readback_query(self.profile, ROUTING_CAT, dest)
        data = transport.query(
            req,
            lambda x: proto.is_readback_response(self.profile, x, ROUTING_CAT, dest),
            timeout=1.5)
        if data is None:
            raise RuntimeError(f"no routing readback for dest {dest} -- not writing blind")
        _dest, pairs = proto.parse_routing_record(
            self.profile, proto.readback_body(self.profile, data))
        return list(pairs)

    def _set_mixer_source(self, transport, channel, target):
        """Change one global mixer-input slot across Zen Go's four mirrors.

        The device's 6/7/8/9 records are four serialized views of the same
        32-slot input map.  Read every group before writing any group so a
        missing readback never leaves the map partially changed.
        """
        records = []
        for dest in self.mixer_source_destinations:
            pairs = self._routing_record_for_write(transport, dest)
            if channel >= len(pairs):
                raise RuntimeError(
                    f"routing destination {dest} has no mixer slot {channel}")
            pairs[channel] = target
            records.append((dest, pairs))
        for dest, pairs in records:
            transport.write(proto.build_route_command(
                self.profile, dest, pairs))
            self._cache_routing(dest, pairs)

    def _mixer_record_for_write(self, transport, mix):
        """Copy the serialized cache, querying once only if it is not ready."""
        with self._lock:
            cached = self.mixer.get(mix)
            if cached is not None:
                return [dict(slot) for slot in cached]
        if mix not in self.mixer_indices:
            raise RuntimeError(
                f"mixer readback index {mix} is not declared safe for this profile")
        req = proto.build_readback_query(self.profile, MIXER_CAT, mix)
        data = transport.query(
            req,
            lambda x: proto.is_readback_response(self.profile, x, MIXER_CAT, mix),
            timeout=1.5)
        if data is None:
            raise RuntimeError(f"no mixer readback for mix {mix} -- not writing blind")
        return proto.parse_mixer_record(
            self.profile, proto.readback_body(self.profile, data))

    def _auraverb_record_for_write(self, transport):
        """Return the full Gazelle Reverb readback, refusing a blind write."""
        with self._lock:
            cached = self.auraverb.get(self.auraverb_index)
            if cached is not None:
                return [{**record, "params": dict(record.get("params", {}))}
                        for record in cached]
        if not self.auraverb_available:
            raise RuntimeError("Gazelle Reverb readback is not safely mapped for this profile")
        req = proto.build_readback_query(
            self.profile, self.auraverb_category, self.auraverb_index)
        data = transport.query(
            req,
            lambda x: proto.is_readback_response(
                self.profile, x, self.auraverb_category, self.auraverb_index),
            timeout=1.5)
        if data is None:
            raise RuntimeError("no Gazelle Reverb readback -- not writing blind")
        return proto.parse_auraverb_record(
            self.profile, proto.readback_body(self.profile, data))

    def run(self):
        transport = None
        readback_plan = []
        readback_changed = False
        last_debug_meter = 0.0
        while True:
            if transport is None:
                try:
                    transport = open_transport(self.vid, self.pid, self.report_size)
                except SystemExit:
                    self._publish({"online": False})
                    time.sleep(2.0)
                    continue
                last_readback = time.time()
                readback_plan = self._readback_plan()
                readback_changed = False

            # 1. Run at most one queued command. Draining the queue here used
            # to freeze meters for the duration of every pending HID write.
            try:
                fn = self.cmds.get_nowait()
                try:
                    fn(transport)
                except OSError:
                    transport = None
                except Exception as e:                           # noqa: BLE001
                    print(f"[cmd] {e!r}", file=sys.stderr)
            except queue.Empty:
                pass
            if transport is None:
                self._publish({"online": False})
                continue

            # 2. Prepare a bounded slow-state sweep. Only one record is read
            # after each fast-state publish below, keeping meter cadence live.
            now = time.time()
            if not readback_plan and now - last_readback > READBACK_REFRESH_S:
                readback_plan = self._readback_plan()
                readback_changed = False
                last_readback = now

            # 3. Fast state. Visible meters live in 0x73. Sample the legacy
            # 0x75 diagnostic bank only twice a second; polling it every loop
            # added avoidable latency without improving any visible meter.
            try:
                state = transport.read_one(self.state_magic, timeout=0.4)
                meter = None
                monotonic_now = time.monotonic()
                if monotonic_now - last_debug_meter >= 0.5:
                    meter = self._read_meter(transport, timeout=0.01)
                    last_debug_meter = monotonic_now
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
                # Profile-declared physical/preamp meter bank (when available).
                snap["input_meters"] = self._parse_meters(state)
                # Profile-declared selected mixer surface/meter bank.
                mixer_meters = self._parse_mixer_meters(state)
                if mixer_meters is not None:
                    snap["mixer_meters"] = mixer_meters
                # Raw slice covering the profile's mixer/preamp meter region
                # for ?meterdebug=1; it remains diagnostic only.
                snap["state_raw"] = {"base": 150, "bytes": list(state[150:236])}
            if meter:
                # 0x75 @32/@48 and @33/@49 are route-correlated lane pairs.
                # Their fixed ownership is unresolved; retain raw debug only.
                base = self.profile["frame"]["meter_report"].get(
                    "channel_meter_base_offset")
                # Some profiles identify a meter report without having a
                # confirmed channel offset yet (Zen Go). Keep the report
                # available to future mapping work, but never crash the
                # device thread by treating an unknown offset as Orion's.
                if base is not None:
                    base = int(base)
                    snap["meters_raw"] = {"base": base,
                                          "bytes": list(meter[base:base + 32])}
            # keep last values if this cycle only got one of the two frames
            with self._lock:
                for k in ("channels", "buses", "adat", "spdif", "trim", "brightness",
                          "sample_rate_idx", "clock_source_idx", "input_meters",
                          "mixer_meters", "state_raw", "meters_raw"):
                    if k not in snap and k in self.snapshot:
                        snap[k] = self.snapshot[k]
            self._publish(snap)

            # 4. One slow readback record per meter cycle. Changes are
            # announced together when the sweep completes, avoiding a browser
            # refetch after every individual routing destination.
            if readback_plan:
                category, index = readback_plan.pop(0)
                try:
                    readback_changed = self._refresh_readback_one(
                        transport, category, index) or readback_changed
                except OSError:
                    transport = None
                    self._publish({"online": False})
                    continue
                if not readback_plan and readback_changed:
                    with self._lock:
                        self.rb_ver += 1

    # -- readback (routing + mixer + structured state) ----------------------

    def _readback_plan(self):
        routes = [(ROUTING_CAT, d) for d in self.route_dests] \
            if self.routing_available else []
        mixes = [(MIXER_CAT, m) for m in self.mixer_indices
                 if 0 <= m < self.n_mixes] \
            if self.mixer_available else []
        auraverb = [(self.auraverb_category, self.auraverb_index)] \
            if self.auraverb_available else []
        structured = list(_structured_readback_targets(self.profile))
        return routes + mixes + auraverb + structured

    def _refresh_readback_one(self, transport, category, index):
        """Read one bounded slow-state record; return whether it changed."""
        try:
            req = proto.build_readback_query(self.profile, category, index)
        except proto.ConstraintError:
            return False
        data = transport.query(
            req,
            lambda x: proto.is_readback_response(self.profile, x, category, index),
            timeout=0.1)
        if data is None:
            return False
        try:
            body = proto.readback_body(self.profile, data)
            layout = proto.readback_record_layout(self.profile, category, index)
            if layout is not None:
                value = proto.parse_readback_records(
                    self.profile, body, category, index,
                    kind=layout.get("kind"))
                cache = self.structured
                cache_key = (category, index)
            elif category == ROUTING_CAT:
                _dest, value = proto.parse_routing_record(self.profile, body)
                cache = self.routing
                cache_key = index
            elif category == MIXER_CAT:
                value = proto.parse_mixer_record(self.profile, body)
                cache = self.mixer
                cache_key = index
            elif category == self.auraverb_category:
                value = proto.parse_auraverb_record(self.profile, body)
                cache = self.auraverb
                cache_key = index
            else:
                return False
        except (TypeError, ValueError):
            return False
        with self._lock:
            if cache.get(cache_key) == value:
                return False
            cache[cache_key] = value
            return True

    def _read_meter(self, transport, timeout=0.03):
        """Read a meter frame, filtering readbacks only where they share the
        meter report magic (as they do on the Orion)."""
        for data in transport.read_reports(self.meter_magic, timeout):
            if not self.meter_shares_readback_magic or (
                    len(data) > METER_DISCRIMINATOR_OFFSET
                    and data[METER_DISCRIMINATOR_OFFSET] == METER_DISCRIMINATOR):
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
        """Return source-aware samples from the configured 0x73 meter bank."""
        source = "state_report"
        spec = self.profile["frame"][source]
        base = spec.get("channel_meter_base_offset")
        if base is None:
            return []
        base = int(base)
        raw_range = spec.get("physical_meter_raw_range")
        silence_raw = (int(raw_range[1])
                       if spec.get("physical_meter_direction") == "inverted"
                       and isinstance(raw_range, list) and len(raw_range) == 2
                       else None)
        out = []
        for ch in range(self.n_ch):
            off = base + ch
            if off >= len(state):
                break
            raw = state[off]
            db = proto.raw_to_db(self.profile, raw, source)
            led = proto.meter_led(self.profile, db, source)
            out.append({
                "raw": raw,
                "db": round(db, 1) if db is not None else None,
                "clip": led["clip"] if led is not None else None,
                "silence": raw == silence_raw if silence_raw is not None else None,
            })
        return out

    def _parse_mixer_meters(self, state):
        """Return the profile-declared virtual-mixer strip meter bank.

        Orion profiles use ``mixer_window_selection`` plus a
        ``meter_mappings`` entry. Zen Go uses the TUI-confirmed
        ``mixer_strip_meters`` lanes and its profile-defined surface selector.
        Both paths return the same browser-facing shape.
        """
        spec = self.profile["frame"].get("state_report", {})
        selection = spec.get("mixer_window_selection", {})
        mapping = next((m for m in spec.get("meter_mappings", [])
                        if m.get("target") == "mixer_window_strip"), None)
        if selection and mapping:
            try:
                selector_off = proto._as_int(selection.get("state_byte_offset", 122))
                base = proto._as_int(mapping.get("payload_offset_base", 157))
                strip_range = mapping.get("strip_index_range", [1, 32])
                raw_range = mapping.get("raw_range", [0, 96])
                raw_lo, raw_hi = (proto._as_int(raw_range[0]),
                                  proto._as_int(raw_range[1]))
                silence_raw = proto._as_int(mapping.get("silence_raw", raw_hi))
            except (KeyError, TypeError, ValueError, IndexError):
                return None
            if selector_off < 0 or selector_off >= len(state) or len(strip_range) != 2:
                return None
            selected = state[selector_off]
            allowed = {proto._as_int(v) for v in selection.get("values", [])}
            if allowed and selected not in allowed:
                return {"mix": selected, "strips": [],
                        "raw_range": [raw_lo, raw_hi],
                        "silence_raw": silence_raw}
            first, last = proto._as_int(strip_range[0]), proto._as_int(strip_range[1])
            strips = []
            for ch in range(first, last + 1):
                off = base + (ch - first)
                if off < 0 or off >= len(state):
                    break
                raw = state[off]
                strips.append({"ch": ch, "raw": raw,
                               "silence": raw == silence_raw})
            return {"mix": selected, "strips": strips,
                    "raw_range": [raw_lo, raw_hi],
                    "silence_raw": silence_raw}

        # Zen Go: the selected front-panel surface gates the 16 shared
        # mixer-strip lanes at the profile's full-report base offset.
        mapping = spec.get("mixer_strip_meters")
        surface = _mixer_surface_spec(self.profile)
        if not isinstance(mapping, dict) or surface is None:
            return None
        try:
            selector_off = proto._as_int(surface.get("state_byte_offset", 122))
            base = mapping.get("full_report_base_offset")
            if base is None:
                base = (proto._as_int(mapping["payload_base_offset"])
                        + proto._as_int(spec.get("snapshot_payload_offset", 16)))
            else:
                base = proto._as_int(base)
            count = proto._as_int(mapping.get("count", 0))
            stride = proto._as_int(mapping.get("stride", 1))
            raw_range = mapping.get("raw_range", [0, 96])
            raw_lo, raw_hi = (proto._as_int(raw_range[0]),
                              proto._as_int(raw_range[1]))
            silence_raw = proto._as_int(mapping.get("silence_raw", raw_hi))
        except (KeyError, TypeError, ValueError, IndexError):
            return None
        if selector_off < 0 or selector_off >= len(state) or count <= 0 or stride <= 0:
            return None
        selected = state[selector_off]
        mix = _mixer_surface_for_value(self.profile, selected)
        if mix is None:
            return {"mix": -1, "selector": selected, "strips": [],
                    "raw_range": [raw_lo, raw_hi],
                    "silence_raw": silence_raw}
        strips = []
        for channel in range(count):
            off = base + channel * stride
            if off < 0 or off >= len(state):
                break
            raw = state[off]
            strips.append({"ch": channel, "raw": raw,
                           "silence": raw == silence_raw})
        return {"mix": mix, "selector": selected, "strips": strips,
                "raw_range": [raw_lo, raw_hi],
                "silence_raw": silence_raw}


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

# ---------------------------------------------------------------- HTTP / SSE

app = FastAPI(title="antelope-ctl webui (draft)")
app.mount("/webui/assets", StaticFiles(directory=os.path.join(HERE, "assets")),
          name="webui-assets")


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

class MixerSelect(BaseModel):
    mix: int                  # 0-based mix index; profile may have no selector

class MixerSource(BaseModel):
    mix: int                  # 0-based mixer tab containing the selector
    channel: int              # 0-based mixer input strip
    source: str               # profile-provided source option key

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
    channel: int              # profile-defined slot (Orion master is slot 0)
    fader: int | None = None  # profile-defined dB attenuation (sign ignored)
    pan: int | None = None    # profile-defined panorama range
    send: int | None = None   # profile-defined Gazelle Reverb send range
    mute: bool | None = None
    solo: bool | None = None

class MixSolo(BaseModel):
    mix: int
    channel: int
    on: bool


class AuraVerbChange(BaseModel):
    mix: int = 0
    param: str | None = None
    value: int | None = None
    enabled: bool | None = None


class MixerLink(BaseModel):
    """A virtual-mixer stereo pair scoped to one mix."""
    pair: int
    enabled: bool
    mix: int = 0


def _bad(msg):
    return JSONResponse({"ok": False, "error": msg}, status_code=400)


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/profile")
def api_profile():
    return {**PROFILE, "webui": {
        "routing": DEV.routing_available,
        "mixer": DEV.mixer_available,
        "mixes": DEV.n_mixes if DEV.mixer_available else 0,
        "mix_channels": DEV.mix_channels if DEV.mixer_available else 0,
        "features": UI_FEATURES,
    }}


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


@app.get("/api/readbacks")
def api_readbacks():
    """Profile-driven nested readback state for the diagnostics panel.

    This is intentionally read-only.  The device thread polls only layouts
    with capture-confirmed outer indices; schema-only layouts are returned so
    the UI can explain why a new capture is still required.
    """
    return DEV.structured_readbacks_json()


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
    The profile may expose a 0x0b link-table readback, but transition/polarity
    correlation is still capture-pending for Orion. The browser therefore
    keeps its last-commanded state as the control fallback; this endpoint only
    puts the raw link frame on the wire."""
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
    """SET_LINK for the ADAT (space 0) / S-PDIF (space 1) domains. No link
    transition has been correlated yet -- the browser tracks link state, like
    the preamp link. The extracted Orion schema maps these spaces into the
    category-0x0b link tables, but a controlled on/off capture is still
    required. NOTE the ADAT link frame is byte-identical to the physical one
    (both space 0), so a space-0 SET_LINK for pair N may also move physical
    pair N -- see params.adat_channel_link.notes."""
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
    """bus_dim / bus_mute / bus_mono (SET_PARAM 0x66/0x48/0x69 on Zen Go;
    Orion uses 0x68 for dim), bus id at
    the channel offset. Confirmed for monitor buses; bus_mute also confirmed on
    the line output (bus 3). dim/mono may not apply to line/reamp."""
    pname = {"dim": "bus_dim", "mute": "bus_mute", "mono": "bus_mono"}.get(t.param)
    if pname is None:
        return _bad("bad param -- dim|mute|mono")
    try:
        proto.check_target(PROFILE, t.bus, "bus")
        packet = proto.build_command(PROFILE, pname, t.bus, 1 if t.on else 0)
    except (KeyError, ValueError, proto.ConstraintError) as e:
        return _bad(str(e))
    DEV.submit(lambda tr, packet=packet: tr.write(packet))
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
    Preamps 5-12 (the EMU button is Mic-mode-gated). Current state is exposed
    by the profile-declared category-0x16 nested readback; the write path has
    not yet been verified by a write/readback round-trip, so the controls keep
    their local optimistic state. This endpoint does NOT do the Launcher's
    side effects (auto 48V, pair link)."""
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
    sources = proto.route_source_options(PROFILE)
    return {"dests": dests, "sources": sources, "current": DEV.routing_json()}


@app.post("/api/route")
def api_route(r: Route):
    if not DEV.routing_available:
        return _bad("routing readback is not safely mapped for this profile")
    dc = PROFILE["frame"].get("routing_command", {}).get("destination_channels", {})
    if str(r.dest) not in dc:
        return _bad(f"unknown routing destination {r.dest}")
    nch = int(dc[str(r.dest)])
    if not 0 <= r.channel < nch:
        return _bad(f"channel {r.channel} out of range 0..{nch - 1} for dest {r.dest}")
    try:
        tgt = proto.route_mute_source(PROFILE) if r.kind == "mute" \
            else proto.resolve_route_source(PROFILE, r.kind, r.number)
    except ValueError as e:
        return _bad(str(e))

    def do(t, dest=r.dest, ch=r.channel, tgt=tgt):
        pairs = DEV._routing_record_for_write(t, dest)
        pairs[ch] = tgt
        t.write(proto.build_route_command(PROFILE, dest, pairs))
        DEV._cache_routing(dest, pairs)

    DEV.submit(do)
    return {"ok": True}


@app.post("/api/route-batch")
def api_route_batch(b: RouteBatch):
    """Several route changes for ONE destination group in a single
    read-modify-write (one 0x74 readback + one 0x53 write) -- for the matrix
    group ops (1:1, mute all) and, later, patchbay group drops. Same
    'refuse to write blind' guard as /api/route."""
    if not DEV.routing_available:
        return _bad("routing readback is not safely mapped for this profile")
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
            tgt = proto.route_mute_source(PROFILE) if c.kind == "mute" \
                else proto.resolve_route_source(PROFILE, c.kind, c.number)
        except ValueError as e:                                  # noqa: BLE001
            return _bad(str(e))
        resolved.append((c.channel, tgt))

    def do(t, dest=b.dest, changes=resolved):
        pairs = DEV._routing_record_for_write(t, dest)
        for ch, tgt in changes:
            pairs[ch] = tgt
        t.write(proto.build_route_command(PROFILE, dest, pairs))
        DEV._cache_routing(dest, pairs)

    DEV.submit(do)
    return {"ok": True, "n": len(resolved)}


# -- virtual mixer -------------------------------------------------------

@app.post("/api/mixer-source")
def api_mixer_source(s: MixerSource):
    """Update one slot in the Zen Go's shared mixer input map.

    The browser sends an option key from the profile-derived feature list;
    the server resolves that key back to a bank/index pair and refuses any
    source that is not declared by the active profile.
    """
    if not DEV.mixer_source_available:
        return _bad("mixer input routing is not safely mapped for this profile")
    if not 0 <= s.mix < DEV.n_mixes:
        return _bad(f"mix {s.mix} out of range 0..{DEV.n_mixes - 1}")
    if not 0 <= s.channel < DEV.mix_channels:
        return _bad(f"mixer channel {s.channel} out of range 0..{DEV.mix_channels - 1}")
    feature = UI_FEATURES.get("mixer_sources", {})
    option = next((item for item in feature.get("options", [])
                   if item.get("key") == s.source), None)
    if option is None:
        return _bad(f"unknown mixer source option {s.source!r}")
    try:
        target = (proto._as_int(option["bank"]),
                  proto._as_int(option["index"]))
    except (KeyError, TypeError, ValueError) as e:
        return _bad(f"invalid mixer source option: {e}")
    DEV.submit(lambda t: DEV._set_mixer_source(t, s.channel, target))
    return {"ok": True, "mix": s.mix, "channel": s.channel,
            "source": s.source}

@app.post("/api/mixer-select")
def api_mixer_select(s: MixerSelect):
    """Select a profile-defined mixer surface or meter bank.

    This is a UI selection, not a routing change. Orion profiles use the
    legacy ``frame.state_report.mixer_window_selection`` selector; profiles
    such as Zen Go can instead declare a confirmed ``mixer.surface_selection``
    command with a per-mix value map.
    """
    if not DEV.mixer_available:
        return _bad("mixer readback is not safely mapped for this profile")
    if not 0 <= s.mix < DEV.n_mixes:
        return _bad(f"mix {s.mix} out of range 0..{DEV.n_mixes - 1}")
    try:
        surface_packet = _mixer_surface_packet(PROFILE, s.mix)
    except (KeyError, TypeError, ValueError, proto.ConstraintError) as e:
        return _bad(str(e))
    if surface_packet is not None:
        pkt, value, target = surface_packet
        DEV.submit(lambda t: t.write(pkt))
        return {"ok": True, "mix": s.mix, "selected": True,
                "selector": value, "target": target}
    selector = PROFILE["frame"].get("state_report", {}).get("mixer_window_selection", {})
    if not selector:
        # Some devices expose each mix's controls without the Orion's
        # selector-gated meter bank.  The tab still changes locally; there is
        # simply no selector command to send for that profile.
        return {"ok": True, "mix": s.mix, "selected": False}
    try:
        param_id = selector["param_id"]
        param_id = int(param_id, 0) if isinstance(param_id, str) else int(param_id)
        target = int(selector.get("target", 1))
        pkt = proto.build_raw_command(PROFILE, param_id, target, s.mix)
    except (KeyError, TypeError, ValueError, proto.ConstraintError) as e:
        return _bad(str(e))
    DEV.submit(lambda t: t.write(pkt))
    return {"ok": True, "mix": s.mix}


@app.post("/api/mix-link")
def api_mix_link(link: MixerLink):
    """Toggle one virtual-mixer pair (SET_LINK space 3).

    Linked value mirroring is Launcher-side behavior, so the browser owns
    that companion state. Profiles may additionally declare a complete,
    capture-confirmed link bitmap for reconnect-time state seeding.
    """
    if not DEV.mixer_available:
        return _bad("mixer readback is not safely mapped for this profile")
    if not 0 <= link.mix < DEV.n_mixes:
        return _bad(f"mix {link.mix} out of range 0..{DEV.n_mixes - 1}")
    pairs = DEV.mix_channels // 2
    if not 0 <= link.pair < pairs:
        return _bad(f"pair {link.pair} out of range 0..{pairs - 1}")
    try:
        wire_pair = proto.mixer_link_pair_index(PROFILE, link.mix, link.pair)
        pkt = proto.build_link_command(PROFILE, wire_pair, link.enabled, space=3)
    except (KeyError, proto.ConstraintError) as e:                # noqa: BLE001
        return _bad(str(e))
    DEV.submit(lambda t: t.write(pkt))
    return {"ok": True, "mix": link.mix, "pair": link.pair,
            "wire_pair": wire_pair, "enabled": link.enabled}

@app.post("/api/mix-solo")
def api_mix_solo(s: MixSolo):
    """Apply a mix-wide solo, matching the Launcher's host-side behavior.

    One or more channels may be soloed together. While any solo is active,
    non-solo channels are muted; when the last Solo is released, restore the
    flags that existed before the first Solo instead of blindly unmuting.
    """
    if not DEV.mixer_available:
        return _bad("mixer readback is not safely mapped for this profile")
    if not 0 <= s.mix < DEV.n_mixes:
        return _bad(f"mix {s.mix} out of range 0..{DEV.n_mixes - 1}")
    first_channel = 1 if DEV.mixer_has_master else 0
    last_channel = DEV.mix_channels if DEV.mixer_has_master else DEV.mix_channels - 1
    if not first_channel <= s.channel <= last_channel:
        if DEV.mixer_has_master:
            return _bad(
                f"channel {s.channel} out of range {first_channel}..{last_channel}; "
                "master has no Solo")
        return _bad(
            f"channel {s.channel} out of range {first_channel}..{last_channel}")

    def do(t, m=s.mix, ch=s.channel, on=s.on):
        slots = DEV._mixer_record_for_write(t, m)
        n_slots = DEV.mix_channels + int(DEV.mixer_has_master)
        if len(slots) < n_slots:
            raise RuntimeError(
                f"mixer {m} returned {len(slots)} slots; expected {n_slots}")

        def solo_update(active):
            # A mix master is deliberately outside Solo: its strip has only
            # fader and mute, and muting it would silence every soloed input.
            return [(bool(slot["mute"]), bool(slot["solo"]))
                    if DEV.mixer_has_master and idx == 0
                    else (idx not in active, idx in active)
                    for idx, slot in enumerate(slots[:n_slots])]

        if on:
            group = DEV.solo_state.get(m)
            if group is None:
                group = {
                    "restore": [
                        (bool(slot["mute"]), bool(slot["solo"]))
                        for slot in slots[:n_slots]
                    ],
                    "active": set(),
                }
                DEV.solo_state[m] = group
            group["active"].add(ch)
            active = group["active"]
            updated = solo_update(active)
        else:
            group = DEV.solo_state.get(m)
            if group is None:
                updated = [(False, False) for _ in range(n_slots)]
            else:
                group["active"].discard(ch)
                active = group["active"]
                if active:
                    updated = solo_update(active)
                else:
                    updated = group["restore"]
                    DEV.solo_state.pop(m, None)

        for idx, slot in enumerate(slots[:n_slots]):
            mute, solo = updated[idx]
            t.write(proto.build_mix_command(
                PROFILE, m, idx, slot["fader"], slot["pan"], slot["send"],
                mute, solo))
            slots[idx] = {**slot, "mute": mute, "solo": solo}
        DEV._cache_mixer(m, slots)

    DEV.submit(do)
    return {"ok": True, "mix": s.mix, "channel": s.channel, "on": s.on}


@app.get("/api/auraverb")
def api_auraverb():
    command = PROFILE["frame"].get("auraverb_command", {})
    param_names = list(command.get("param_offsets", {}))
    lo, hi = command.get("param_range", [0, 100])
    return {
        "available": bool(UI_FEATURES.get("auraverb", {}).get("enabled")
                           and DEV.auraverb_available),
        "mix": UI_FEATURES.get("auraverb", {}).get("mix", 0),
        "params": param_names,
        "range": [lo, hi],
        "current": DEV.auraverb_json(),
    }


@app.post("/api/auraverb")
def api_auraverb_change(change: AuraVerbChange):
    spec = UI_FEATURES.get("auraverb", {})
    command = PROFILE["frame"].get("auraverb_command", {})
    if not spec.get("enabled") or not DEV.auraverb_available:
        return _bad("Gazelle Reverb is not safely mapped for this profile")
    if change.mix != int(spec.get("mix", 0)):
        return _bad("only the profile-confirmed Gazelle Reverb mix is available")
    if (change.param is None) != (change.value is None):
        return _bad("param and value must be supplied together")
    if change.param is None and change.enabled is None:
        return _bad("provide a Gazelle Reverb parameter or enabled state")
    names = command.get("param_offsets", {})
    if change.param is not None and change.param not in names:
        return _bad(f"unknown Gazelle Reverb parameter {change.param!r}")
    lo, hi = command.get("param_range", [0, 100])
    if change.value is not None and not lo <= change.value <= hi:
        return _bad(f"Gazelle Reverb value {change.value} outside {lo}..{hi}")

    def do(t):
        records = DEV._auraverb_record_for_write(t)
        mix = int(spec.get("mix", 0))
        if mix >= len(records):
            raise RuntimeError(f"Gazelle Reverb readback has no Mix {mix + 1} record")
        current = records[mix]
        params = dict(current.get("params", {}))
        if set(params) != set(names):
            raise RuntimeError("Gazelle Reverb readback is incomplete -- not writing blind")
        enabled = current.get("enabled")
        if enabled is None:
            raise RuntimeError("Gazelle Reverb enabled state is unknown -- not writing blind")
        if change.param is not None:
            params[change.param] = change.value
        if change.enabled is not None:
            enabled = bool(change.enabled)
        packet = proto.build_auraverb_command(
            PROFILE, params, enabled, mix=mix)
        t.write(packet)
        records[mix] = {**current, "params": params, "enabled": enabled}
        DEV._cache_auraverb(records)

    DEV.submit(do)
    return {"ok": True, "mix": change.mix,
            "param": change.param, "value": change.value,
            "enabled": change.enabled}


@app.get("/api/mixer")
def api_mixer():
    p = PROFILE.get("params", {})
    mixer = PROFILE.get("mixer", {})
    send = p.get("mix_send", {})
    fader = p.get("mix_fader", {}).get("range",
                                        mixer.get("fader", {}).get("range", [0, 90]))
    pan = p.get("mix_pan", {}).get("range",
                                    mixer.get("pan", {}).get("range_deg", [-30, 30]))
    send_range = send.get("range", [0, 96])
    return {
        "available": DEV.mixer_available,
        "n_mixes": DEV.n_mixes,
        "channels_per_mix": DEV.mix_channels,
        "has_master": DEV.mixer_has_master,
        "has_send": proto.mix_has_send(PROFILE),
        "send_mixes": [int(m) for m in send.get("mix_indices", [])],
        "send_master": bool(send.get("include_master", False)),
        "ranges": {
            "fader": fader,
            "pan": pan,
            "send": send_range,
        },
        "current": DEV.mixer_json(),
    }


@app.post("/api/mix")
def api_mix(s: MixStrip):
    if not DEV.mixer_available:
        return _bad("mixer readback is not safely mapped for this profile")
    if not 0 <= s.mix < DEV.n_mixes:
        return _bad(f"mix {s.mix} out of range 0..{DEV.n_mixes - 1}")
    first_channel = 0
    last_channel = DEV.mix_channels if DEV.mixer_has_master else DEV.mix_channels - 1
    if not first_channel <= s.channel <= last_channel:
        label = "0 = master" if DEV.mixer_has_master else "no master strip"
        return _bad(f"channel {s.channel} out of range {first_channel}..{last_channel} ({label})")
    has_send = proto.mix_has_send(PROFILE)
    mixer = PROFILE.get("mixer", {})
    f_lo, f_hi = PROFILE.get("params", {}).get("mix_fader", {}).get(
        "range", mixer.get("fader", {}).get("range", [0, 90]))
    p_lo, p_hi = PROFILE.get("params", {}).get("mix_pan", {}).get(
        "range", mixer.get("pan", {}).get("range_deg", [-30, 30]))
    send_spec = PROFILE.get("params", {}).get("mix_send", {})
    s_lo, s_hi = send_spec.get("range", [0, 96])
    send_mixes = {int(m) for m in send_spec.get("mix_indices", [])}
    send_allowed = has_send and s.mix in send_mixes \
        and (not DEV.mixer_has_master or s.channel != 0
             or bool(send_spec.get("include_master", False)))
    if s.send is not None and not send_allowed:
        return _bad("this mixer strip has no Gazelle Reverb send")

    def do(t, m=s.mix, ch=s.channel):
        slots = DEV._mixer_record_for_write(t, m)
        if ch >= len(slots):
            raise RuntimeError(
                f"mixer {m} returned {len(slots)} slots; channel {ch} is unavailable")
        cur = slots[ch]
        fader = cur["fader"] if s.fader is None else max(f_lo, min(f_hi, abs(s.fader)))
        pan = cur["pan"] if s.pan is None else max(p_lo, min(p_hi, s.pan))
        send = cur["send"] if s.send is None else max(s_lo, min(s_hi, s.send))
        mute = cur["mute"] if s.mute is None else bool(s.mute)
        solo = cur["solo"] if s.solo is None else bool(s.solo)
        t.write(proto.build_mix_command(PROFILE, m, ch, fader, pan,
                                        send if has_send else 0, mute, solo))
        slots[ch] = {**cur, "fader": fader, "pan": pan, "send": send,
                     "mute": mute, "solo": solo}
        DEV._cache_mixer(m, slots)

    DEV.submit(do)
    return {"ok": True}


@app.get("/api/stream")
async def stream():
    """Server-Sent Events: one JSON snapshot per line whenever the version
    bumps, ~25 Hz. EventSource on the browser side reconnects on its own."""
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
            await asyncio.sleep(0.04)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    DEV.start()
    uvicorn.run(app, host="127.0.0.1", port=8714, log_level="warning")
