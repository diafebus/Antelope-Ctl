"""
Profile-driven frame construction/parsing.

Key design rule: this file must never contain a hardcoded param_id, offset,
or magic byte. If you find yourself typing 0x4f or 49 in here, it belongs
in the JSON profile instead. That's what keeps this reusable across devices
and across newly-discovered params.

v3 adds two new areas, both still profile-driven:
  - "buses" (monitor A/B, headphone 1/2): a *bus* is an output, addressed
    with the same byte position as a channel (frame.command.channel_offset)
    but the id means something different -- see resolve_bus_id().
  - "channel_link": pairs of input channels (ch1&2, ch3&4, ...) that can be
    linked together. This uses a DIFFERENT frame shape from every other
    param (frame.link_command, not frame.command/SET_PARAM) -- see
    build_link_command(). If you're adding a new feature and it turns out
    to need its own frame shape too, follow that pattern: add a new block
    under profile["frame"] rather than bending SET_PARAM to fit.
"""
import json


def load_profile(path: str) -> dict:
    with open(path) as f:
        profile = json.load(f)
    return profile


def _as_int(v):
    """Profile values are stored as hex strings ('0x4f') or ints; normalize."""
    if isinstance(v, str):
        return int(v, 16)
    return v


def i8(b: int) -> int:
    b = int(b) & 0xFF
    return b - 256 if b > 127 else b


def build_command(profile: dict, param_name: str, channel: int, value: int) -> bytes:
    """Build a SET_PARAM-style command frame for a param defined in profile['params'].

    Works for both per-input-channel params (gain, input_mode, ...) and the
    per-bus params (bus_level, bus_dim, ...) -- for the latter, pass the bus
    id (see resolve_bus_id()) as `channel`. The wire format is identical;
    only the meaning of that byte differs, which is why this function
    doesn't need to know which kind of param it's building.
    """
    params = profile['params']
    if param_name not in params:
        raise KeyError(f'unknown param "{param_name}" -- add it to the profile first')
    pdef = params[param_name]
    if pdef.get('id') is None:
        raise ValueError(
            f'param "{param_name}" has no confirmed param_id yet (status={pdef.get("status")}). '
            'Capture it first, then fill in profile["params"]["%s"]["id"].' % param_name
        )
    return build_raw_command(profile, _as_int(pdef['id']), channel, value)


def build_raw_command(profile: dict, param_id: int, channel: int, value: int) -> bytes:
    """Escape hatch: build a frame from a raw param_id, for params not yet in the profile.
    Use this while you're still reverse-engineering something new (e.g. routing).
    Only valid for the SET_PARAM frame shape (profile['frame']['command']) -- for
    channel_link, use build_link_command() instead, since it's a different shape."""
    f = profile['frame']['command']
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = param_id & 0xFF
    pkt[_as_int(f['channel_offset'])] = channel & 0xFF
    pkt[_as_int(f['value_offset'])] = value & 0xFF
    return bytes(pkt)


def build_link_command(profile: dict, pair_index: int, enabled: bool) -> bytes:
    """Build a SET_LINK frame (profile['frame']['link_command']) to engage/disengage
    one channel-link pair. This is NOT the SET_PARAM shape -- param_id still lives
    at param_id_offset, but the per-channel byte is unused and pair_index/enabled
    live at their own offsets a byte further along. See frame.link_command.notes
    in the profile for how this was worked out from a real capture."""
    if 'link_command' not in profile['frame']:
        raise KeyError('this profile has no frame.link_command -- channel link is not available')
    f = profile['frame']['link_command']
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = _as_int(f['param_id'])
    pkt[_as_int(f['pair_index_offset'])] = pair_index & 0xFF
    pkt[_as_int(f['enabled_offset'])] = 1 if enabled else 0
    return bytes(pkt)


def pair_index_for_channel(channel: int) -> int:
    """channels.link_pairs.formula: pair_index = channel_index // 2. Kept as a
    tiny helper (not read from the profile) since it's arithmetic, not a magic
    number -- but if a future device paired channels differently, the CLI
    caller should read channels.link_pairs.formula itself rather than assume
    this helper still applies."""
    return channel // 2


def parse_state(profile: dict, data: bytes, channel: int) -> dict:
    sr = profile['frame']['state_report']
    gain_off = _as_int(sr['gain_base_offset']) + channel
    status_off = _as_int(sr['status_base_offset']) + channel
    if status_off >= len(data):
        raise ValueError(f'state report too short for channel {channel}')

    status_byte = data[status_off]
    result = {'channel': channel, 'gain': i8(data[gain_off])}
    for bit_name, bit_def in sr['status_bits'].items():
        mask = _as_int(bit_def['mask'])
        shift = bit_def['shift']
        result[bit_name] = (status_byte & mask) >> shift
    return result


def state_report_magic(profile: dict) -> int:
    return _as_int(profile['frame']['state_report']['magic'])


def meter_report_magic(profile: dict) -> int:
    return _as_int(profile['frame']['meter_report']['magic'])


def parse_meter_level(profile: dict, data: bytes, channel: int) -> int:
    """Read a channel's raw meter byte, if this profile has a (possibly unconfirmed)
    channel_meter_base_offset. Returns the raw byte value -- caller decides how to
    interpret the scale (see meter_report.channel_meter_scale in the profile)."""
    mr = profile['frame']['meter_report']
    base = mr.get('channel_meter_base_offset')
    if base is None:
        raise ValueError('this profile has no channel_meter_base_offset yet -- meter reading not available')
    off = _as_int(base) + channel
    if off >= len(data):
        raise ValueError(f'meter report too short for channel {channel}')
    return data[off]


def raw_to_db(profile: dict, raw_value: int):
    """Convert a raw meter byte to dBFS using profile['frame']['meter_report']['db_curve'],
    a list of [raw_byte, db] calibration points (any order), piecewise-linearly
    interpolated. Returns None if the profile has no db_curve yet -- callers should
    treat that as "no calibrated reading available" and fall back to the raw byte /
    uncalibrated bar, not invent a scale. This intentionally does NOT default to
    assuming the 0-96 range is linear dB; that shape is explicitly unconfirmed (see
    meter_report.channel_meter_scale notes) and gain's own per_mode_range shows this
    protocol doesn't always use a flat linear scale."""
    mr = profile['frame'].get('meter_report', {})
    curve = mr.get('db_curve')
    if not curve:
        return None
    pts = sorted(((_as_int(r), float(d)) for r, d in curve), key=lambda p: p[0])
    if raw_value <= pts[0][0]:
        return pts[0][1]
    if raw_value >= pts[-1][0]:
        return pts[-1][1]
    for (r0, d0), (r1, d1) in zip(pts, pts[1:]):
        if r0 <= raw_value <= r1:
            if r1 == r0:
                return d0
            frac = (raw_value - r0) / (r1 - r0)
            return d0 + frac * (d1 - d0)
    return pts[-1][1]  # unreachable given the bounds checks above, kept defensive


def meter_led(profile: dict, db):
    """Map a dBFS value to a color/clip verdict using profile['frame']['meter_report']
    ['led_scale']. Returns None if db is None (no calibration yet) or the profile has
    no led_scale. Pure lookup -- has no opinion on how `db` was derived."""
    if db is None:
        return None
    mr = profile['frame'].get('meter_report', {})
    scale = mr.get('led_scale')
    if not scale:
        return None
    for band in scale['bands']:
        lo = band['min_db']
        hi = band['max_db']
        if (lo is None or db >= lo) and (hi is None or db < hi):
            return {'color': band['color'], 'clip': band['clip']}
    return None


def mode_name(profile: dict, mode_val: int) -> str:
    values = profile['params']['input_mode']['values']
    return values.get(str(mode_val), f'?{mode_val}')


def mode_value(profile: dict, name: str) -> int:
    values = profile['params']['input_mode']['values']
    for k, v in values.items():
        if v == name:
            return int(k)
    raise KeyError(f'unknown mode name "{name}"')


def gain_range(profile: dict, mode_name_str: str):
    ranges = profile['params']['gain'].get('per_mode_range', {})
    lo, hi = ranges.get(mode_name_str, (-128, 127))
    return lo, hi


# ---- buses (monitor A/B, headphone 1/2) ----

def resolve_bus_id(profile: dict, bus) -> int:
    """Accept either a raw bus id ('0', 0) or a name/alias ('monitor_a', 'mona', ...)
    and return the integer bus id. Raises KeyError with the list of known names/ids
    if it can't be resolved, so the CLI can show the user something useful."""
    known = profile.get('buses', {}).get('known', {})
    bus_str = str(bus).strip().lower()

    # Already a valid known id?
    if bus_str in known:
        return int(bus_str)
    # Try as a plain integer id even if not in 'known' (e.g. an id under
    # investigation that hasn't been added to the profile yet).
    try:
        return int(bus_str)
    except ValueError:
        pass
    # Try matching against name/aliases.
    for id_str, info in known.items():
        names = [info.get('name', '')] + info.get('aliases', [])
        if bus_str in (n.lower() for n in names):
            return int(id_str)

    choices = ', '.join(f"{i} ({v.get('name')})" for i, v in known.items())
    raise KeyError(f'unknown bus "{bus}" -- known buses: {choices}')


def bus_name(profile: dict, bus_id: int) -> str:
    """Reverse of resolve_bus_id, for display. Falls back to the raw id for
    buses not in profile['buses']['known'] (e.g. the unassigned ids 3/4)."""
    known = profile.get('buses', {}).get('known', {})
    info = known.get(str(bus_id))
    return info['name'] if info else f'bus{bus_id}'


def parse_bus_state(profile: dict, data: bytes, bus_id: int) -> dict:
    """Read one bus's level + dim/mute/mono flags from the state report,
    using state_report.bus_block. Mirrors parse_state()'s shape/approach
    for per-channel data."""
    bb = profile['frame']['state_report']['bus_block']
    base = _as_int(bb['base_offset']) + _as_int(bb['bytes_per_bus']) * bus_id
    level_off = base + _as_int(bb['level_byte_offset'])
    status_off = base + _as_int(bb['status_byte_offset'])
    if status_off >= len(data):
        raise ValueError(f'state report too short for bus {bus_id}')

    status_byte = data[status_off]
    result = {'bus': bus_id, 'level': data[level_off]}
    for bit_name, bit_def in bb['status_bits'].items():
        mask = _as_int(bit_def['mask'])
        shift = bit_def['shift']
        result[bit_name] = (status_byte & mask) >> shift
    return result


def bus_level_range(profile: dict):
    lo, hi = profile['params']['bus_level'].get('range', [0, 96])
    return lo, hi
