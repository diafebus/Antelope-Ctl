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


def build_global_command(profile: dict, param, value: int) -> bytes:
    """Build a SET_GLOBAL frame (profile['frame']['global_command'], opcode
    0x12) for a device-global param that has no per-channel/per-bus target.
    Unlike SET_PARAM the value byte sits at value_offset (17), not 18.
    `param` is a param name in profile['params'] or a raw param_id int."""
    if 'global_command' not in profile['frame']:
        raise KeyError('this profile has no frame.global_command -- SET_GLOBAL not available')
    f = profile['frame']['global_command']
    if isinstance(param, str):
        pdef = profile['params'].get(param)
        if pdef is None:
            raise KeyError(f'unknown param "{param}" -- add it to the profile first')
        if pdef.get('id') is None:
            raise ValueError(f'param "{param}" has no confirmed param_id yet')
        param_id = _as_int(pdef['id'])
    else:
        param_id = _as_int(param)
    check_opcode(profile, _as_int(f['opcode']))
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = param_id & 0xFF
    pkt[_as_int(f['value_offset'])] = value & 0xFF
    return bytes(pkt)


def build_mix_command(profile: dict, mix: int, channel: int, fader: int,
                      pan_deg: int, send: int, mute: bool = False,
                      solo: bool = False) -> bytes:
    """Build a SET_MIX frame (profile['frame']['mix_command'], opcode 0x17) --
    one virtual-mixer strip's whole state. `mix` 0-3, `channel` **0-32** --
    1-32 are the input strips and **0 is the mix master** (the Launcher writes
    channel 0 itself; see parse_mixer_record for the evidence),
    `fader` 0-90 (dB attenuation), `pan_deg` -30..+30, `send` 0-96. The frame
    carries every field every time (no partial update) -- read the current
    strip back first with parse_mixer_record if you only mean to change one
    field."""
    if 'mix_command' not in profile['frame']:
        raise KeyError('this profile has no frame.mix_command -- SET_MIX not available')
    f = profile['frame']['mix_command']
    check_opcode(profile, _as_int(f['opcode']))
    pan_center = _as_int(f.get('pan_center', 32))
    pan_mask = _as_int(f.get('pan_mask', 0x3f))
    pan_flags = ((pan_center + pan_deg) & pan_mask)
    if mute:
        pan_flags |= _as_int(f.get('mute_bit', 0x40))
    if solo:
        pan_flags |= _as_int(f.get('solo_bit', 0x80))
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = _as_int(f['param_id'])
    pkt[_as_int(f['subcmd_offset'])] = _as_int(f['subcmd'])
    pkt[_as_int(f['mix_offset'])] = mix & 0xFF
    pkt[_as_int(f['channel_offset'])] = channel & 0xFF
    pkt[_as_int(f['fader_offset'])] = fader & 0xFF
    pkt[_as_int(f['pan_flags_offset'])] = pan_flags & 0xFF
    pkt[_as_int(f['send_offset'])] = send & 0xFF
    return bytes(pkt)


# canonical AuraVerb control order (matches the Launcher UI top-to-bottom).
# The wire order is different (see frame.auraverb_command.param_offsets); the
# builder maps by name so order here is purely cosmetic for the CLI.
AURAVERB_PARAMS = (
    'color', 'pre_delay', 'early_reflection_gain', 'late_reflection_delay',
    'richness', 'reverb_time', 'room_size', 'reverb_level',
)


def auraverb_defaults(profile: dict) -> dict:
    """The device power-on values for the 8 AuraVerb params (from the profile,
    originally the frozen frame in macos-auraverb-on-off)."""
    f = profile['frame'].get('auraverb_command')
    if not f:
        raise KeyError('this profile has no frame.auraverb_command -- AuraVerb not available')
    return dict(f.get('defaults', {}))


def build_auraverb_command(profile: dict, params: dict, enabled: bool = True,
                           mix: int = 0) -> bytes:
    """Build a SET_AURAVERB frame (profile['frame']['auraverb_command'], opcode
    0x1d) -- the whole AuraVerb state for one mix's reverb. `params` must
    carry all 8 DSP controls (keys = frame.auraverb_command.param_offsets,
    values 0-100); the caller fills any it isn't changing from cache/defaults,
    since the frame has no partial update and no device readback. `enabled`
    is the on/off bit. `mix` is the mix index (only 0 / Mix 1 is confirmed)."""
    f = profile['frame'].get('auraverb_command')
    if not f:
        raise KeyError('this profile has no frame.auraverb_command -- AuraVerb not available')
    check_opcode(profile, _as_int(f['opcode']))
    offs = f['param_offsets']
    lo, hi = f.get('param_range', [0, 100])
    missing = [k for k in offs if k not in params]
    if missing:
        raise ValueError(f'build_auraverb_command needs all {len(offs)} params; '
                         f'missing {", ".join(sorted(missing))}')
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = _as_int(f['param_id'])
    pkt[_as_int(f['subcmd_offset'])] = _as_int(f['subcmd'])
    pkt[_as_int(f['mix_offset'])] = mix & 0xFF
    if 'mix_wet_offset' in f:
        pkt[_as_int(f['mix_wet_offset'])] = _as_int(f['mix_wet_constant']) & 0xFF
    for name, off in offs.items():
        v = int(params[name])
        if not (lo <= v <= hi):
            raise ValueError(f'AuraVerb {name} = {v} outside {lo}..{hi}')
        pkt[_as_int(off)] = v & 0xFF
    pkt[_as_int(f['enabled_offset'])] = 1 if enabled else 0
    return bytes(pkt)


def build_micmodeling_command(profile: dict, channel: int, enabled: bool,
                              pattern: int = 50, swap: bool = False,
                              model: int = 0) -> bytes:
    """Build a SET_MIC_MODELING frame (profile['frame']['micmodeling_command'],
    opcode 0x17 / param 0xe5) -- the 'emuMic' mic-modeling DSP on a preamp.
    `channel` is the 0-based input channel index (mic modeling exists only on
    preamps 7-12, i.e. channel 6-11); it is written as channel + channel_bias.
    `model` is the emulation model id (0 = EdgeDuo / raw, no emulation).
    `pattern` is the polar-pattern byte -- with model 0 it is the 0-100
    continuous morph (0 omni / 50 cardioid / 100 figure-8); with an emulation
    model the Launcher writes that model's pattern-class code (see
    profiles/mic_models.json), so pass the model's `pattern_class` there.
    `swap` is the channel-order swap toggle.
    Whole state every frame, no readback. Does NOT do the Launcher's side
    effects (auto phantom-on, preamp-pair link)."""
    f = profile['frame'].get('micmodeling_command')
    if not f:
        raise KeyError('this profile has no frame.micmodeling_command')
    check_opcode(profile, _as_int(f['opcode']))
    lo, hi = f.get('pattern_range', [0, 100])
    if not (lo <= int(pattern) <= hi):
        raise ValueError(f'mic-modeling pattern {pattern} outside {lo}..{hi}')
    tgt = channel + _as_int(f.get('channel_bias', 0))
    if tgt < 0:
        raise ValueError(f'channel {channel} has no mic modeling (preamps 7-12 only)')
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = _as_int(f['param_id'])
    pkt[_as_int(f['subcmd_offset'])] = _as_int(f['subcmd'])
    pkt[_as_int(f['channel_offset'])] = tgt & 0xFF
    pkt[_as_int(f['enabled_offset'])] = 1 if enabled else 0
    if enabled:
        pkt[_as_int(f['model_offset'])] = int(model) & 0xFF
        pkt[_as_int(f['swap_offset'])] = 1 if swap else 0
        pkt[_as_int(f['pattern_offset'])] = int(pattern) & 0xFF
    return bytes(pkt)


# ---- routing matrix (frame.routing_command, opcode 0x53) ----
#
# EXPERIMENTAL, but the frame model is now understood (macOS captures
# ch1-12-mute-hp1L / -hp1R, 2026-08):
#
#   d3 41 <dest> | <bank0> <idx0> | <bank1> <idx1> | <bank2> <idx2> | ...
#
# The frame carries the WHOLE destination group's per-channel routing, one
# (bank, index) pair per output channel, starting at channel_list_offset
# (19) with channel_stride (2). Channel 0 = output 1 (L on a stereo pair);
# multichannel groups (line out = 16 confirmed, ADAT out, mix channels,
# ...) just have more pairs. There are NO separate "op bytes" -- the old
# output_ops model was a misread of the OTHER channel's unchanged (bank,
# index). Source banks 0x05-0x0a (AFX / mix 1-4 / surround) decoded 2026-08.
#
# Consequence: to change one channel you must resend every channel of the
# group -- the CLI reads the current group from the device first
# (frame.readback category 0x03, parse_routing_record) and after the write
# reads it back to confirm. mute is the pseudo-source (bank 0x0b, index 0);
# there is no "no source".

ROUTE_SOURCE_SPECS = {
    # canonical name: (source_bank, first_index, count, label, user_base)
    # user_base = the number the user types that maps to first_index
    # (1 for everything except emumic, which the Launcher labels by preamp
    # number 5-12).
    'preamp':   (0x00, 0, 12, 'preamp 1-12', 1),
    'emumic':   (0x01, 0, 8,  'emumic / mic-modeled preamp 5-12 (the EMU button is on 7-12 only; '
                              '5-6 exist in the matrix but have no model UI)', 5),
    'compplay': (0x02, 0, 32, 'computer playback (24 on VM, up to 32 on macOS)', 1),
    'adat':     (0x03, 0, 16, 'ADAT in 1-16', 1),
    'afx':      (0x05, 0, 32, 'AFX out 1-32', 1),
    'surround': (0x0a, 0, 16, 'surround out 1-16', 1),
    'osc':      (0x0c, 0, 2,  'oscillator 1-2', 1),
}

# stereo (L/R) source banks -- name -> bank
ROUTE_STEREO_SOURCE_BANKS = {
    'spdif': 0x04, 'mix1': 0x06, 'mix2': 0x07, 'mix3': 0x08, 'mix4': 0x09,
}

# accepted spellings -> canonical key
ROUTE_SOURCE_ALIASES = {
    'compplay': 'compplay', 'comp': 'compplay', 'compplayback': 'compplay',
    'playback': 'compplay', 'daw': 'compplay', 'usb': 'compplay',
    'preamp': 'preamp', 'pre': 'preamp', 'mic': 'preamp',
    'adat': 'adat',
    'afx': 'afx', 'fx': 'afx',
    'surround': 'surround', 'surr': 'surround', 'srnd': 'surround',
    'osc': 'osc', 'oscillator': 'osc',
    'emumic': 'emumic', 'emu': 'emumic', 'micmodel': 'emumic',
    'modeledmic': 'emumic', 'micemulation': 'emumic',
}

ROUTE_MUTE = (0x0b, 0)


def _lr_index(number):
    return {'l': 0, 'r': 1, '1': 0, '2': 1}.get(str(number).strip().lower())


def resolve_route_source(profile: dict, kind: str, number):
    """Map a source spec to (bank, index). `kind` is a numbered bank
    ('preamp'|'compplay'|'adat'|'afx'|'surround'|'osc', aliases in
    ROUTE_SOURCE_ALIASES) with a 1-based `number`, a stereo bank
    ('spdif'|'mix1'..'mix4') with number 'L'/'R'/1/2, or 'mute'. Raises
    ValueError on a bad spec."""
    kind = kind.lower()
    if kind == 'mute':
        return ROUTE_MUTE
    if kind in ROUTE_STEREO_SOURCE_BANKS:
        idx = _lr_index(number)
        if idx is None:
            raise ValueError(f"{kind} source needs L or R")
        return ROUTE_STEREO_SOURCE_BANKS[kind], idx
    canon = ROUTE_SOURCE_ALIASES.get(kind, kind)
    if canon in ROUTE_SOURCE_SPECS:
        bank, first, count, label, base = ROUTE_SOURCE_SPECS[canon]
        n = int(number)
        if not (base <= n <= base + count - 1):
            raise ValueError(f"{canon} number {n} out of range "
                             f"{base}..{base + count - 1} ({label})")
        return bank, first + (n - base)
    raise ValueError(f"unknown routing source kind '{kind}' -- one of: "
                     f"preamp, emumic, compplay, adat, afx, surround, osc, "
                     f"spdif, mix1..mix4, mute")


def route_source_label(profile: dict, bank: int, index: int) -> str:
    """Reverse of resolve_route_source: (bank, index) -> a human label like
    'compplay 5' / 'mix2 R' / 'MUTE', for showing a decoded/cached route."""
    if (bank, index) == ROUTE_MUTE:
        return 'MUTE'
    for name, b in ROUTE_STEREO_SOURCE_BANKS.items():
        if b == bank:
            return f"{name} {'L' if index == 0 else 'R'}"
    for name, (b, first, count, _label, base) in ROUTE_SOURCE_SPECS.items():
        if b == bank and first <= index <= first + count - 1:
            return f'{name} {index - first + base}'
    return f'bank 0x{bank:02x} idx {index}'


def resolve_route_dest(profile: dict, name):
    """Map a destination name/alias/id to its byte-18 value, restricted to
    frame.routing_command.addressable_destinations (the ones the CLI supports)."""
    f = profile['frame'].get('routing_command', {})
    addr = f.get('addressable_destinations', {})
    s = str(name).strip().lower()
    if s in addr:
        return int(s)
    # resolve against the buses 'known' names/aliases, then check it's addressable
    for id_str, dest_name in addr.items():
        info = profile.get('buses', {}).get('known', {})
        names = [dest_name]
        for bid, binfo in info.items():
            if binfo.get('name') == dest_name:
                names += [binfo.get('name')] + binfo.get('aliases', [])
        if s in (n.lower() for n in names if n):
            return int(id_str)
    choices = ', '.join(f"{i} ({n})" for i, n in addr.items())
    raise ValueError(f"routing destination '{name}' not addressable by the CLI -- "
                     f"choose one of: {choices}. Other outputs (adat out, com rec, "
                     f"mix channels, surround in) use the same frame but their channel "
                     f"counts aren't captured yet.")


def route_dest_channels(profile: dict, dest_id: int) -> int:
    """How many output channels the destination group `dest_id` has, from
    frame.routing_command.destination_channels. Raises if unknown."""
    f = profile['frame'].get('routing_command', {})
    dc = f.get('destination_channels', {})
    n = dc.get(str(dest_id))
    if n is None:
        raise ValueError(f'routing destination {dest_id}: channel count not known '
                         f'(not in frame.routing_command.destination_channels)')
    return int(n)


def resolve_route_channel(profile: dict, dest_id: int, sel) -> int:
    """Map an output-channel selector to a 0-based channel index. `sel` is
    1-based ('1'..'N'), or 'L'/'R' (= 1/2) only for a stereo destination
    (frame.routing_command.stereo_destinations). Validates against the
    group's channel count."""
    n = route_dest_channels(profile, dest_id)
    s = str(sel).strip().lower()
    f = profile['frame'].get('routing_command', {})
    if s in ('l', 'r'):
        if str(dest_id) not in f.get('stereo_destinations', []):
            raise ValueError(f"destination {dest_id} is not a stereo pair -- use a channel "
                             f"number 1..{n}, not L/R")
        s = '1' if s == 'l' else '2'
    if not s.isdigit() or not (1 <= int(s) <= n):
        raise ValueError(f"channel '{sel}' -- expected 1..{n}"
                         + ('  (or L/R)' if str(dest_id) in f.get('stereo_destinations', []) else ''))
    return int(s) - 1


def build_route_command(profile: dict, dest: int, channels) -> bytes:
    """Build a routing frame. `channels` is an ordered list of (bank, index)
    tuples -- one per output channel of the destination GROUP, in channel
    order (0 = L / output 1, 1 = R / output 2, ...). The whole group is
    always sent; there is no way to address a single channel on the wire.
    Use resolve_route_source() / ROUTE_MUTE to build the tuples."""
    f = profile['frame'].get('routing_command')
    if not f:
        raise KeyError('this profile has no frame.routing_command -- routing not available')
    check_opcode(profile, _as_int(f['opcode']))
    base = _as_int(f['channel_list_offset'])
    stride = _as_int(f['channel_stride'])
    size = profile['transport']['report_size']
    if base + stride * len(channels) > size:
        raise ValueError(f'routing frame: {len(channels)} channels overflow the {size}-byte report')
    pkt = bytearray(size)
    pkt[_as_int(f['magic_offset'])] = _as_int(f['magic'])
    pkt[_as_int(f['opcode_offset'])] = _as_int(f['opcode'])
    pkt[_as_int(f['param_id_offset'])] = _as_int(f['param_id'])
    pkt[_as_int(f['subcmd_offset'])] = _as_int(f['subcmd'])
    pkt[_as_int(f['destination_offset'])] = dest & 0xFF
    for c, (bank, index) in enumerate(channels):
        pkt[base + stride * c] = bank & 0xFF
        pkt[base + stride * c + 1] = index & 0xFF
    return bytes(pkt)


# ---------------------------------------------------------------------------
# In-band READBACK protocol  (frame.readback)
# ---------------------------------------------------------------------------
# Decoded 2026-08-31 from CAPTURE E' (usbmon on the Linux host while the
# Windows Launcher connected over QEMU USB passthrough) + direct replay from
# Linux (tools/readback_enum.py). The device answers a request/response
# protocol on the SAME HID interrupt endpoints -- NOT a HID Feature report
# and NOT a control transfer, which is why every earlier probe missed it
# (hid_probe.py, the GET_REPORT sweep, tools/readback_probe.py --poke all
# came up empty; --poke failed only because it sent a bare 0x74 with no
# sub-header).
#
#   REQUEST   host->device, EP 0x01 OUT, full report:
#     74 00 00 00 | 10 00 00 00 | <category> 00 00 00 | <index> 00 00 00 | 00...
#   RESPONSE  device->host, EP 0x82 IN, full report:
#     75 00 00 00 | 40 01 00 00 | <category> 00 00 00 | <index> 00 00 00 | <data...>
#
# The response magic is 0x75 but byte 1 = 0x00 -- the free-running METER
# report is 0x75 with byte 1 = 0x1f, and the STATE report is the same family
# with magic 0x73 (effectively "category 0, pushed continuously"). The
# device also answers unknown (category, index) tuples, just with an empty
# body -- so "has a non-empty body" is the liveness signal, not "answered".
# Scalar categories return the same record for every index.
#
# The 0x74 "connect enumeration" documented in frame.init_enumeration_report
# IS this protocol -- the Launcher walking every (category, index).
#
# Category 0x03 = the full routing matrix: one record per destination group
# (index 0..14), each `<dest_id> <bank0> <idx0> <bank1> <idx1> ...` -- the
# SAME (bank, index) array as the 0x53 write frame, one pair per output
# channel of that group. This is the routing readback the earlier analysis
# had ruled out.

ROUTING_READBACK_CATEGORY = 0x03
MIXER_READBACK_CATEGORY = 0x04


def readback_category_count(profile: dict, category: int):
    """How many records a readback category really has, or None if unknown.
    Source: frame.readback.category_counts, which comes from the device's own
    0x74 connect enumeration (frame.init_enumeration_report) -- the only
    evidence-grade record count we have."""
    counts = profile['frame'].get('readback', {}).get('category_counts', {})
    for k, v in counts.items():
        if _as_int(k) == category:
            return int(v)
    return None


def check_readback_index(profile: dict, category: int, index: int) -> None:
    """HAZARD GUARD -- see frame.readback.hazard.

    Querying an index past the end of a category's record array makes the
    firmware read adjacent memory, and one index further crashes it outright:
    on 2026-08-31 `category 0x04 index 5` hard-faulted the Orion Studio III
    (front panel: "CRITICAL ERROR! Failure.c  L: 204  E: 0  BusFault_Handler",
    a Cortex-M BusFault) and the unit needed a power cycle. The symptom is
    distinctive: an out-of-range-but-safe index answers with a WRONG-LAYOUT
    body, and the fatal one answers with NOTHING at all -- the device normally
    answers every (category, index), just with an empty body when it has no
    record. Raises ConstraintError; callers pass force=True at their own risk."""
    n = readback_category_count(profile, category)
    if n is not None and index >= n:
        raise ConstraintError(
            f'readback category {category:#04x} has only {n} record(s) '
            f'(index 0..{n - 1}); index {index} reads past the end of the '
            f"firmware's array and can crash the device with a BusFault "
            f'(needs a power cycle). Use force=True only if you accept that.')


def build_readback_query(profile: dict, category: int, index: int = 0,
                         force: bool = False) -> bytes:
    """Build a readback REQUEST frame (frame.readback.request). Read-only --
    this is exactly what the Launcher issues on connect. Bounds-checked
    against frame.readback.category_counts unless `force` (see
    check_readback_index -- an out-of-range index can crash the device)."""
    r = profile['frame'].get('readback')
    if not r:
        raise KeyError('this profile has no frame.readback -- readback not available')
    if not force:
        check_readback_index(profile, category, index)
    size = profile['transport']['report_size']
    pkt = bytearray(size)
    pkt[_as_int(r['magic_offset'])] = _as_int(r['request_magic'])
    pkt[_as_int(r['subcmd_offset'])] = _as_int(r['subcmd'])
    pkt[_as_int(r['category_offset'])] = category & 0xFF
    pkt[_as_int(r['index_offset'])] = index & 0xFF
    return bytes(pkt)


def is_readback_response(profile: dict, data: bytes, category: int, index: int) -> bool:
    """True if `data` is the readback RESPONSE for (category, index) -- and
    not a free-running 0x73 state / 0x75 meter report."""
    r = profile['frame'].get('readback')
    if not r or data is None or len(data) <= _as_int(r['data_offset']):
        return False
    return (data[_as_int(r['magic_offset'])] == _as_int(r['response_magic'])
            and data[_as_int(r['response_discriminator_offset'])]
            == _as_int(r['response_discriminator'])
            and data[_as_int(r['category_offset'])] == (category & 0xFF)
            and data[_as_int(r['index_offset'])] == (index & 0xFF))


def readback_body(profile: dict, data: bytes):
    """The payload of a readback response, after the 16-byte header. Trailing
    zero padding is NOT stripped (a routing record can legitimately end in
    (bank 0, idx 0) = preamp 1, or in mute = (0x0b, 0))."""
    r = profile['frame']['readback']
    return data[_as_int(r['data_offset']):]


def parse_routing_record(profile: dict, body: bytes):
    """Decode one category-0x03 record. Returns (dest_id, [(bank, idx), ...])
    with exactly destination_channels[dest_id] pairs (the wire record is
    zero-padded to the report size). Raises if the destination's channel
    count is unknown."""
    if not body:
        raise ValueError('empty routing record')
    dest_id = body[0]
    n = route_dest_channels(profile, dest_id)
    pairs = []
    for c in range(n):
        o = 1 + 2 * c
        if o + 1 >= len(body):
            raise ValueError(f'routing record for dest {dest_id} truncated at channel {c}')
        pairs.append((body[o], body[o + 1]))
    return dest_id, pairs


def parse_mixer_record(profile: dict, body: bytes):
    """Decode one category-0x04 record -- the whole state of one virtual mix.
    The readback index IS the mix number (0..3 = Mix 1..4).

    The record is a flat array of 3-byte slots, SAME field order as the
    frame.mix_command write frame (fader@20, pan|flags@21, send@22):

        <fader> <pan|mute|solo> <send>

    Slot index maps 1:1 onto the write frame's `channel` field, with no
    special case: **slot N == frame.mix_command channel N, for N = 0..32.**

      slot 0      = the MIX MASTER strip
      slots 1..32 = the 32 input strips

    Both halves are hardware-confirmed (2026-08-31):
      * inputs -- wrote mix 1 / ch 5 / fader 40 / pan +12 / mute / send 33
        (`28 6c 21`), read back at slot 5 as `28 6c 21`, no other slot moved.
      * master -- a usbmon capture of the Launcher sweeping the Mix 1 master
        fader (`captures/new/mix1-masterfaderplay.pcapng`) shows 68 frames,
        every one `d4 05 00 00 <fader> 20 60`: same opcode/param, mix 0,
        **channel 0**, pan and send constant. The sweep ended at fader 90 and
        slot 0 then read back as -90 dB. So the Launcher itself writes
        channel 0 -- it is a normal address, not out of range.

    Returns all 33 slots; list index == slot number == channel number.
    Each entry is a dict: fader (0-90 dB of attenuation), pan (-30..+30),
    send (0-96), mute, solo, raw (the 3 bytes)."""
    if not body:
        raise ValueError('empty mixer record')
    f = profile['frame'].get('mix_command', {})
    pan_center = _as_int(f.get('pan_center', 32))
    pan_mask = _as_int(f.get('pan_mask', 0x3f))
    mute_bit = _as_int(f.get('mute_bit', 0x40))
    solo_bit = _as_int(f.get('solo_bit', 0x80))
    # the record is exactly 3 * n_slots bytes; the wire frame is zero-padded to
    # the report size and an all-zero slot is not a legal strip (pan 0 would be
    # -32, outside the +-30 range), so trailing zeros are padding, not data.
    body = body.rstrip(b'\x00')
    slots = []
    for o in range(0, len(body) - 2, 3):
        fader, flags, send = body[o], body[o + 1], body[o + 2]
        slots.append({
            'fader': fader,
            'pan': (flags & pan_mask) - pan_center,
            'send': send,
            'mute': bool(flags & mute_bit),
            'solo': bool(flags & solo_bit),
            'raw': bytes(body[o:o + 3]),
        })
    return slots


IDENTITY_READBACK_CATEGORY = 0x01
FIRMWARE_READBACK_CATEGORY = 0x00


def parse_identity_record(profile: dict, body: bytes) -> dict:
    """Decode a category-0x01 record: the device's own name, SERIAL and
    hardware revision, as fixed-offset NUL-terminated ASCII fields.

    The serial is deliberately NOT stored anywhere in this repo -- profiles
    describe the *layout*, and the value is read from the device on demand.
    Ask for it only when you actually need it, and don't write it to a file.

    Layout (frame.readback.identity; identical on Orion Studio III and Zen Go
    Synergy Core, so it looks like a family-wide record):

        @0   model name        e.g. 'OrionStudio_III', 'Zen Go Synergy Core'
        @20  serial            13 chars
        @36  hardware revision e.g. '7.0', '6.6'
        @44  4 bytes, binary   little-endian u32; plausibly a build/calibration
                               unix timestamp (both units decode to mid-2021),
                               but that is a guess, not confirmed.

    Returns {'name', 'serial', 'revision', 'stamp'}; missing fields come back
    as None rather than raising, since this record is device-reported."""
    ident = profile['frame'].get('readback', {}).get('identity', {})
    if not body:
        raise ValueError('empty identity record')

    def field(key, default):
        off = ident.get(key)
        off = _as_int(off) if off is not None else default
        if off is None or off >= len(body):
            return None
        raw = body[off:].split(b'\x00')[0]
        return raw.decode('latin1', 'replace') or None

    stamp = None
    so = ident.get('stamp_offset')
    so = _as_int(so) if so is not None else 44
    if so is not None and so + 4 <= len(body):
        stamp = int.from_bytes(body[so:so + 4], 'little')
    return {
        'name': field('name_offset', 0),
        'serial': field('serial_offset', 20),
        'revision': field('revision_offset', 36),
        'stamp': stamp,
    }


def parse_firmware_record(profile: dict, body: bytes):
    """Decode a category-0x00 record -> the firmware version string, or None.

    On the Orion Studio III this is ASCII at offset 8 ('4.41'). On the Zen Go
    the record is only 2 bytes and binary (`01 5a`) with no string at all, so
    this returns None there rather than inventing a version."""
    ident = profile['frame'].get('readback', {}).get('identity', {})
    off = ident.get('firmware_offset')
    off = _as_int(off) if off is not None else 8
    if body is None or off is None or off >= len(body):
        return None
    raw = body[off:].split(b'\x00')[0]
    txt = raw.decode('latin1', 'replace').strip()
    return txt or None


def readback_categories(profile: dict) -> dict:
    """frame.readback.categories -- {hex_str: description}, for display/tools."""
    return profile['frame'].get('readback', {}).get('categories', {})


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


def parse_state_scalar(profile: dict, data: bytes, sr_key: str) -> int:
    """Read one plain unsigned byte from the state report, at the offset named
    by profile['frame']['state_report'][sr_key]. That value may be a bare int
    or a {'offset': N, ...} dict. Used for simple single-byte params like
    screen_brightness (state_report.screen_brightness_byte_offset)."""
    sr = profile['frame']['state_report']
    spec = sr.get(sr_key)
    if spec is None:
        raise ValueError(f'this profile has no state_report.{sr_key}')
    off = _as_int(spec['offset'] if isinstance(spec, dict) else spec)
    if off >= len(data):
        raise ValueError(f'state report too short (need offset {off}, got {len(data)} bytes)')
    return data[off]


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
