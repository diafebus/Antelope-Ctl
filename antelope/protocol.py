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


# ---- constraints / hazards (profile['constraints'], see profile['hazards']) ----
#
# These are the machine-readable safety bounds a client MUST enforce before
# writing. They exist because a sibling device in this protocol family
# (Discrete 8 Pro) faults hard -- firmware BusFault, wedged USB controller --
# on out-of-range input, in ways that cost a physical power cycle. The
# effects are not reproduced on Orion, but the shared protocol and the cost
# of being wrong make them precautionary defaults. All values come from the
# profile; nothing here is hardcoded.

def constraints(profile: dict) -> dict:
    return profile.get('constraints', {}) or {}


class ConstraintError(ValueError):
    """Raised when a write would violate profile['constraints']. The CLI
    turns this into a clean exit message; callers that really mean it can
    pass force=True to the check_* helpers to downgrade it to a warning."""


def _opcode_set(profile: dict, key: str) -> set:
    return {_as_int(x) for x in constraints(profile).get(key, [])}


def check_opcode(profile: dict, opcode: int, force: bool = False):
    """Refuse an opcode that is in constraints.forbidden_opcodes, or (if an
    allow-list is defined) one that is not in constraints.allowed_opcodes."""
    c = constraints(profile)
    if not c:
        return
    if opcode in _opcode_set(profile, 'forbidden_opcodes'):
        raise ConstraintError(
            f'opcode 0x{opcode:02x} is in constraints.forbidden_opcodes -- '
            f'on a sibling device it wedged the USB controller unrecoverably '
            f'(see profile hazards.blind_opcode_sweeps). Refusing.')
    allowed = _opcode_set(profile, 'allowed_opcodes')
    if allowed and opcode not in allowed and not force:
        raise ConstraintError(
            f'opcode 0x{opcode:02x} is not in constraints.allowed_opcodes '
            f'{sorted(hex(o) for o in allowed)}. Pass force to send it anyway.')


def channel_space_bounds(profile: dict, space: str):
    """Return the legal target values for a `space`:
      'input' -> (min, max) from constraints.channel_bounds
      'adat'  -> (min, max) from constraints.adat_channel_bounds
      'bus'   -> sorted list from constraints.bus_ids
    Returns None if the profile doesn't define that bound."""
    c = constraints(profile)
    if space == 'input' and 'channel_bounds' in c:
        b = c['channel_bounds']
        return b['min'], b['max']
    if space == 'adat' and 'adat_channel_bounds' in c:
        b = c['adat_channel_bounds']
        return b['min'], b['max']
    if space == 'spdif' and 'spdif_channel_bounds' in c:
        b = c['spdif_channel_bounds']
        return b['min'], b['max']
    if space == 'bus' and 'bus_ids' in c:
        return sorted(int(x) for x in c['bus_ids'])
    return None


def check_target(profile: dict, target: int, space: str, force: bool = False):
    """Refuse a channel/bus/adat target outside its address space's bounds
    (constraints). space is 'input', 'adat', or 'bus'. On a sibling device
    an out-of-range channel index raised a firmware BusFault needing a power
    cycle -- see hazards.channel_index_out_of_range."""
    bounds = channel_space_bounds(profile, space)
    if bounds is None:
        return
    ok = target in bounds if isinstance(bounds, list) else bounds[0] <= target <= bounds[1]
    if ok:
        return
    rng = bounds if isinstance(bounds, list) else f'{bounds[0]}..{bounds[1]}'
    if force:
        return
    raise ConstraintError(
        f'{space} target {target} is outside the allowed range {rng} '
        f'(profile constraints). On a sibling device an out-of-range index '
        f'caused a firmware BusFault needing a physical power cycle -- see '
        f'hazards.channel_index_out_of_range. Pass force to override.')


def check_enum(profile: dict, constraint_key: str, value: int, label: str, force: bool = False):
    """Refuse an enum value not in constraints[constraint_key] (e.g.
    input_mode_allowed_values). hazards.foreign_enum_values: on a sibling
    device a value from another device's profile crashed the firmware."""
    allowed = constraints(profile).get(constraint_key)
    if allowed is None:
        return
    allowed = [int(x) for x in allowed]
    if value in allowed or force:
        return
    raise ConstraintError(
        f'{label} value {value} is not in constraints.{constraint_key} {allowed}. '
        f'Enum values are NOT portable across this device family -- see '
        f'hazards.foreign_enum_values. Pass force to override.')


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
    check_opcode(profile, _as_int(f['opcode']))
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = param_id & 0xFF
    pkt[_as_int(f['channel_offset'])] = channel & 0xFF
    pkt[_as_int(f['value_offset'])] = value & 0xFF
    return bytes(pkt)


def build_link_command(profile: dict, pair_index: int, enabled: bool, space: int = 0) -> bytes:
    """Build a SET_LINK frame (profile['frame']['link_command']) to engage/disengage
    one channel-link pair. This is NOT the SET_PARAM shape -- param_id still lives
    at param_id_offset; pair_index and enabled live at their own offsets a byte
    further along. `space` is the domain selector at frame.link_command.space_offset
    (offset 17): 0 for physical + ADAT (see frame.link_command.space_values), 1 for
    S/PDIF. Default 0 keeps physical/ADAT callers unchanged. If the profile has no
    space_offset, `space` is ignored (older profiles)."""
    if 'link_command' not in profile['frame']:
        raise KeyError('this profile has no frame.link_command -- channel link is not available')
    f = profile['frame']['link_command']
    check_opcode(profile, _as_int(f['opcode']))
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = _as_int(f['param_id'])
    if 'space_offset' in f:
        pkt[_as_int(f['space_offset'])] = space & 0xFF
    pkt[_as_int(f['pair_index_offset'])] = pair_index & 0xFF
    pkt[_as_int(f['enabled_offset'])] = 1 if enabled else 0
    return bytes(pkt)


# ---- routing matrix (frame.routing_command, opcode 0x53) ----
#
# EXPERIMENTAL. The routing frame is only partly decoded (see the profile's
# frame.routing_command). For the 5 simple 2-output destinations
# (hp1/hp2/mona/monb/reamp) it is understood: a fixed frame
#   d3 41 <dest> <source_bank> <source_index> <op1> <op2>
# where (op1,op2) comes from output_ops -- (2,1) for output 1, (0,2) for
# output 2, (0,0) for remove. Multichannel destinations (line out, ADAT out,
# ...) use a longer per-channel list that is NOT decoded, so this builder
# refuses them.

ROUTE_SOURCE_SPECS = {
    # name: (source_bank, first_index, count, label)
    'preamp':   (0x00, 0, 12, 'preamp 1-12'),
    'playback': (0x02, 0, 24, 'computer playback 1-24'),
    'adat':     (0x03, 0, 16, 'ADAT in 1-16'),
    'osc':      (0x0c, 0, 2,  'oscillator 1-2'),
}


def resolve_route_source(profile: dict, kind: str, number):
    """Map a source spec to (bank, index). `kind` is 'preamp'|'playback'|'adat'
    |'osc' with a 1-based `number`, or 'spdif' with number 'L'/'R'/1/2, or
    'mute' (number ignored). Raises ValueError on a bad spec."""
    kind = kind.lower()
    if kind == 'mute':
        return 0x0b, 0
    if kind == 'spdif':
        n = str(number).strip().lower()
        idx = {'l': 0, 'r': 1, '1': 0, '2': 1}.get(n)
        if idx is None:
            raise ValueError("spdif source needs L or R")
        return 0x04, idx
    if kind in ROUTE_SOURCE_SPECS:
        bank, first, count, label = ROUTE_SOURCE_SPECS[kind]
        n = int(number)
        if not (1 <= n <= count):
            raise ValueError(f"{kind} number {n} out of range 1..{count} ({label})")
        return bank, first + (n - 1)
    raise ValueError(f"unknown routing source kind '{kind}' -- "
                     f"one of: preamp, playback, adat, spdif, osc, mute")


def resolve_route_dest(profile: dict, name):
    """Map a destination name/alias/id to its byte-18 value, restricted to
    frame.routing_command.addressable_destinations (the 5 the CLI supports)."""
    f = profile['frame'].get('routing_command', {})
    addr = f.get('addressable_destinations', {})
    s = str(name).strip().lower()
    if s in addr:
        return int(s)
    # resolve against the buses 'known' names/aliases, then check it's addressable
    for id_str, dest_name in addr.items():
        info = profile.get('buses', {}).get('known', {})
        # match on the routing dest name or a bus alias for the same output
        names = [dest_name]
        for bid, binfo in info.items():
            if binfo.get('name') == dest_name:
                names += [binfo.get('name')] + binfo.get('aliases', [])
        if s in (n.lower() for n in names if n):
            return int(id_str)
    choices = ', '.join(f"{i} ({n})" for i, n in addr.items())
    raise ValueError(f"routing destination '{name}' not addressable by the CLI -- "
                     f"choose one of: {choices} (multichannel outs like line out / ADAT out "
                     f"aren't supported -- their frame isn't decoded)")


def build_route_command(profile: dict, dest: int, source_bank: int,
                        source_index: int, output) -> bytes:
    """Build a routing frame for a simple 2-output destination.
    `output` is 1, 2, or 'remove'. See the module comment above."""
    f = profile['frame'].get('routing_command')
    if not f:
        raise KeyError('this profile has no frame.routing_command -- routing not available')
    check_opcode(profile, _as_int(f['opcode']))
    ops = f['output_ops']
    key = str(output).lower()
    if key not in ops:
        raise ValueError(f"routing output '{output}' -- expected 1, 2, or 'remove'")
    op1, op2 = ops[key]
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = _as_int(f['param_id'])
    pkt[_as_int(f['subcmd_offset'])] = _as_int(f['subcmd'])
    pkt[_as_int(f['destination_offset'])] = dest & 0xFF
    pkt[_as_int(f['source_bank_offset'])] = source_bank & 0xFF
    pkt[_as_int(f['source_index_offset'])] = source_index & 0xFF
    pkt[_as_int(f['op1_offset'])] = op1 & 0xFF
    pkt[_as_int(f['op2_offset'])] = op2 & 0xFF
    return bytes(pkt)


def pair_index_for_channel(channel: int) -> int:
    """channels.link_pairs.formula: pair_index = channel_index // 2. Kept as a
    tiny helper (not read from the profile) since it's arithmetic, not a magic
    number -- but if a future device paired channels differently, the CLI
    caller should read channels.link_pairs.formula itself rather than assume
    this helper still applies. The same formula holds for ADAT channels
    (adat.link_pairs.formula), just over the 16-channel ADAT index space."""
    return channel // 2


def parse_adat_gain(profile: dict, data: bytes, adat_channel: int) -> int:
    """Read one ADAT channel's gain (int8 dB) from the state report, using
    state_report.adat_gain_base_offset. ADAT channels have no status byte
    (gain + link only), so this returns a bare int rather than a dict."""
    sr = profile['frame']['state_report']
    base = sr.get('adat_gain_base_offset')
    if base is None:
        raise ValueError('this profile has no state_report.adat_gain_base_offset -- ADAT gain readback not available')
    off = _as_int(base) + adat_channel
    if off >= len(data):
        raise ValueError(f'state report too short for ADAT channel {adat_channel}')
    return i8(data[off])


def adat_gain_range(profile: dict):
    """[lo, hi] dB range for adat_gain, from the profile (default wide-open)."""
    lo, hi = profile['params'].get('adat_gain', {}).get('range', [-128, 127])
    return lo, hi


def parse_spdif_gain(profile: dict, data: bytes, spdif_channel: int) -> int:
    """Read one S/PDIF channel's gain (int8 dB, 0=L 1=R) from the state report,
    using state_report.spdif_gain_base_offset. Like ADAT, no status byte."""
    sr = profile['frame']['state_report']
    base = sr.get('spdif_gain_base_offset')
    if base is None:
        raise ValueError('this profile has no state_report.spdif_gain_base_offset -- S/PDIF gain readback not available')
    off = _as_int(base) + spdif_channel
    if off >= len(data):
        raise ValueError(f'state report too short for S/PDIF channel {spdif_channel}')
    return i8(data[off])


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
