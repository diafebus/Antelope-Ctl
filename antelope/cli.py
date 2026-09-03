#!/usr/bin/env python3
"""
Generic Antelope HID control CLI.

Per-input-channel controls (physical inputs 1-12, addressed 0-11):

    antelope-ctl --profile profiles/orion_studio_sc.json status
    antelope-ctl --profile profiles/orion_studio_sc.json set-mode 0 mic
    antelope-ctl --profile profiles/orion_studio_sc.json set-gain 0 12
    antelope-ctl --profile profiles/orion_studio_sc.json set-phantom 0 on
    antelope-ctl --profile profiles/orion_studio_sc.json set-invert 0 on
    antelope-ctl --profile profiles/orion_studio_sc.json set-link 0 on      # links ch1+ch2
                                                                            # (checks gain/phantom/phase
                                                                            # sync before+after as an
                                                                            # indirect confirmation, and
                                                                            # caches the result so
                                                                            # `status` can show it --
                                                                            # see cmd_set_link's docstring,
                                                                            # there is still no real
                                                                            # device-side link readback)

ADAT input controls (16 ADAT channels, addressed 0-15 -- a separate space
from the physical inputs; gain + link only, no mode/phantom/phase):

    antelope-ctl --profile profiles/orion_studio_sc.json adat-status
    antelope-ctl --profile profiles/orion_studio_sc.json set-adat-gain 0 6
    antelope-ctl --profile profiles/orion_studio_sc.json set-adat-link 0 on   # links ADAT ch1+ch2
                                                                            # (mirrors gain to the
                                                                            # partner while linked,
                                                                            # exactly like set-link;
                                                                            # for pairs 0-5 the frame
                                                                            # is identical to the
                                                                            # physical link -- see
                                                                            # set-adat-link help)

S/PDIF input controls (2 channels, 0 = L / 1 = R; gain + link only):

    antelope-ctl --profile profiles/orion_studio_sc.json spdif-status
    antelope-ctl --profile profiles/orion_studio_sc.json set-spdif-gain 0 6
    antelope-ctl --profile profiles/orion_studio_sc.json set-spdif-link on    # links L+R (distinct
                                                                            # link frame from the
                                                                            # physical/ADAT one --
                                                                            # no cross-space
                                                                            # ambiguity)

Routing matrix -- EXPERIMENTAL (lineout=16ch, hp1/hp2/mona/monb/reamp=2ch).
Address an output channel 1-based; `L`/`R` = 1/2 for the stereo dests
(hp1/hp2/mona/monb -- NOT reamp, whose two outs are separate mono). The
wire frame carries the WHOLE destination every time, so a per-channel
change resends the others from this CLI's cache. Like the Antelope
Launcher there is no "un-route" -- replace a source or set it to `mute`.
No device readback yet, so verify in the Launcher:

    antelope-ctl ... route hp1 all preamp3 preamp4     # set every channel (seeds the cache)
    antelope-ctl ... route hp1 R preamp7               # change one channel, keep the rest
    antelope-ctl ... route lineout 3 afx5              # line-out channel 3 <- AFX 5
    antelope-ctl ... route lineout 4 mix2R             # <- virtual mix 2, right
    antelope-ctl ... route hp2 mute                    # mute every channel
    antelope-ctl ... route lineout 6 mute              # mute one channel
    antelope-ctl ... matrix-status                     # CLI-cached routes only

Output-bus controls (monitor A/B, headphone 1/2 -- NOT the same "channel"
numbers as inputs above; buses accept either their numeric id or a name,
see profiles/orion_studio_sc.json -> "buses"):

    antelope-ctl --profile profiles/orion_studio_sc.json bus-status
    antelope-ctl --profile profiles/orion_studio_sc.json set-bus-level monitor_a 60
    antelope-ctl --profile profiles/orion_studio_sc.json set-bus-dim mona on
    antelope-ctl --profile profiles/orion_studio_sc.json set-bus-mute hp1 on
    antelope-ctl --profile profiles/orion_studio_sc.json set-bus-mono hp2 off

Device-global settings:

    antelope-ctl --profile profiles/orion_studio_sc.json set-brightness 75    # front-panel screen, 0-100
    antelope-ctl --profile profiles/orion_studio_sc.json sample-rate           # show current rate
    antelope-ctl --profile profiles/orion_studio_sc.json set-sample-rate 96k   # 32k/44.1k/48k/88.2k/96k/176.4k/192k -- re-locks the clock

Escape hatch for anything not yet in the profile:

    antelope-ctl --profile profiles/orion_studio_sc.json raw-set 0 0x53 7   # for a param
                                                                            # not yet in
                                                                            # the profile

Safety: every write command enforces profile["constraints"] -- the target
byte must be a legal index in its address space (channel 0-11, ADAT 0-15,
bus id 0-5), and enum values (input_mode) must be in the allow-list. This
exists because a sibling device in this protocol family BusFaults / wedges
the USB controller on out-of-range input (see profile["hazards"]). Pass
--force to override a bound if you know what you're doing.

Adding a device: write a new profiles/<name>.json and point --profile at it.
Adding a param: once you've captured+confirmed it, add it under "params" in
the profile; the raw-set command works before that, for exploration.
"""
import argparse
import json
import os
import re
import sys
import time

try:
    from . import protocol as proto
    from .transport import open_transport
except ImportError:
    # Allows running this file directly (python3 antelope/cli.py ...)
    # instead of only via `python3 -m antelope.cli ...`.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from antelope import protocol as proto
    from antelope.transport import open_transport


def get_transport(profile):
    dev = profile['device']
    vid = int(dev['vid'], 16) if isinstance(dev['vid'], str) else dev['vid']
    pid = int(dev['pid'], 16) if isinstance(dev['pid'], str) else dev['pid']
    return open_transport(vid, pid, profile['transport']['report_size'])


def read_state(transport, profile, timeout):
    magic = proto.state_report_magic(profile)
    return transport.read_one(magic, timeout)


def require_state(transport, profile, channel, timeout):
    data = read_state(transport, profile, timeout)
    if not data:
        sys.exit('Could not read a state report. Is the device awake and not busy?')
    return proto.parse_state(profile, data, channel)


def warn_unverified_channel(profile, ch):
    confirmed = profile['channels'].get('confirmed_indices', [])
    if confirmed and ch not in confirmed:
        print(f'note: channel {ch} is beyond the explicitly captured '
              f'{confirmed} range for this device profile; likely fine, but unverified.')


# ---- constraints / hazards enforcement (profile['constraints'] + ['hazards']) ----
# Turns protocol.ConstraintError into a clean CLI exit. See the module comment
# in protocol.py: these bounds exist because a sibling device faults hard
# (BusFault / wedged USB) on out-of-range input.

def enforce_target(profile, target, space, force=False):
    """space: 'input' (channel 0-11), 'adat' (0-15), 'bus' (valid bus ids)."""
    try:
        proto.check_target(profile, target, space, force=force)
    except proto.ConstraintError as e:
        sys.exit(str(e))


def enforce_enum(profile, constraint_key, value, label, force=False):
    try:
        proto.check_enum(profile, constraint_key, value, label, force=force)
    except proto.ConstraintError as e:
        sys.exit(str(e))


def fmt_state(profile, s):
    mode = proto.mode_name(profile, s.get('input_mode', -1))
    parts = [f"ch {s['channel']}", f"mode={mode}", f"gain={s['gain']}dB"]
    if 'phantom' in s:
        parts.append(f"48V={'on' if s['phantom'] else 'off'}")
    if 'phase_invert' in s:
        parts.append(f"phase={'on' if s['phase_invert'] else 'off'}")
    return '  '.join(parts)


def fmt_bus_state(profile, s):
    """Mirrors fmt_state() but for an output bus (see resolve_bus() below)."""
    name = proto.bus_name(profile, s['bus'])
    parts = [f"bus {s['bus']} ({name})", f"level={s['level']}/96"]
    if 'dim' in s:
        parts.append(f"dim={'on' if s['dim'] else 'off'}")
    if 'mute' in s:
        parts.append(f"mute={'on' if s['mute'] else 'off'}")
    if 'mono' in s:
        parts.append(f"mono={'on' if s['mono'] else 'off'}")
    return '  '.join(parts)


def resolve_bus(profile, raw):
    """CLI-facing wrapper around protocol.resolve_bus_id() that exits with a
    helpful message instead of raising, matching how the rest of this file
    reports bad input to the user."""
    try:
        return proto.resolve_bus_id(profile, raw)
    except KeyError as e:
        sys.exit(str(e))


def verify(transport, profile, channel, timeout):
    time.sleep(0.1)
    data = read_state(transport, profile, timeout)
    if not data:
        print('sent command, but no immediate readback was available')
        return
    try:
        s = proto.parse_state(profile, data, channel)
        print('readback: ' + fmt_state(profile, s))
    except ValueError as e:
        print(f'readback unavailable: {e}')


def verify_bus(transport, profile, bus_id, timeout):
    """Same idea as verify(), but reads back an output bus's state instead
    of an input channel's."""
    time.sleep(0.1)
    data = read_state(transport, profile, timeout)
    if not data:
        print('sent command, but no immediate readback was available')
        return
    try:
        s = proto.parse_bus_state(profile, data, bus_id)
        print('readback: ' + fmt_bus_state(profile, s))
    except ValueError as e:
        print(f'readback unavailable: {e}')


def send_and_wait(transport, pkt, delay=0.15):
    transport.write(pkt)
    time.sleep(delay)


# ---- subcommands: per-input-channel (physical inputs) ----

def _link_bracket(profile, link_state, ch):
    """Returns a small ASCII bracket glyph for `ch` if this CLI has previously
    sent a set-link command for its pair, e.g.:

        0  mic   0dB  ...  -.
        1  mic   0dB  ...  -'   (linked, pair 0 -- CLI-tracked, not device-confirmed)

    Returns ('', '') if the pair has never been touched by this CLI (link_state
    has no entry) or is cached as off. This is NOT a device readback -- see the
    big comment above cmd_set_link -- so it can be wrong if the Launcher (or
    another instance of this tool) changed the link since this cache last wrote."""
    pairs = profile['channels'].get('link_pairs', {})
    count = pairs.get('count', 0)
    pair = ch // 2
    if pair >= count:
        return '', ''
    if not link_state.get(str(pair)):
        return '', ''
    lo, hi = pair * 2, pair * 2 + 1
    if ch == lo:
        return ' -.', ''
    if ch == hi:
        return " -'", f'  (linked, pair {pair} -- CLI-tracked, not device-confirmed)'
    return '', ''


def _resolve_channel_count(args, profile, space, fallback=None):
    """How many channels to iterate for a `status`/`meter`/`adat-status`
    view: an explicit --channels if the user passed one, otherwise the
    profile's own count for this address space (proto.space_channel_count),
    otherwise `fallback`. Keeps device dimensions out of argparse -- the
    Orion's 12/16 are wrong for a 2-preamp Zen Go or an ADAT-less device."""
    if getattr(args, 'channels', None) is not None:
        return args.channels
    n = proto.space_channel_count(profile, space)
    return n if n is not None else fallback


def cmd_status(args, profile):
    transport = get_transport(profile)
    data = read_state(transport, profile, args.timeout)
    if not data:
        sys.exit('No state report captured. Try again, or run with sudo if permissions are an issue.')
    n_channels = _resolve_channel_count(args, profile, 'input', fallback=12)
    link_state = _load_link_state(profile)
    print(f"{'ch':>2}  {'mode':<7} {'gain':>5}  {'48V':<3} {'phase':<5}")
    for ch in range(n_channels):
        try:
            s = proto.parse_state(profile, data, ch)
        except ValueError:
            break
        mode = proto.mode_name(profile, s.get('input_mode', -1))
        glyph, tail = _link_bracket(profile, link_state, ch)
        print(f"{ch:>2}  {mode:<7} {s['gain']:>5}  "
              f"{'on' if s.get('phantom') else 'off':<3} "
              f"{'on' if s.get('phase_invert') else 'off':<5}"
              f"{glyph}{tail}")
    confirmed = profile['channels'].get('confirmed_indices', [])
    if confirmed and n_channels > max(confirmed) + 1:
        print(f'note: only channels {confirmed} are explicitly verified for this device.')
    if link_state:
        print("note: the '-.'/\"-'\" markers above reflect the last `set-link` command THIS CLI has "
              "sent (cached locally) -- the device has no known link-status readback (see "
              "params.channel_link.notes), so these markers can go stale if link state changes "
              "outside this CLI (Launcher app, another CLI instance, etc).")
    else:
        print("note: channel-link state has no known device readback yet -- see 'set-link' and the "
              "profile's params.channel_link.notes -- so it isn't shown here until you use "
              "`set-link` at least once from this CLI (which caches its own commanded state).")


def _partner_channel(profile, ch):
    """The other physical channel in ch's stereo-link pair (see channels.link_pairs),
    or None if ch is outside any known pair. Pure arithmetic, same caveat as
    protocol.pair_index_for_channel() -- not read from the profile."""
    max_pair = profile['channels'].get('link_pairs', {}).get('count', 0) - 1
    pair = ch // 2
    if not (0 <= pair <= max_pair):
        return None
    return ch + 1 if ch % 2 == 0 else ch - 1


def cmd_set_mode(args, profile):
    enforce_target(profile, args.channel, 'input', args.force)
    enforce_enum(profile, 'input_mode_allowed_values',
                 proto.mode_value(profile, args.mode), 'input_mode', args.force)
    link_state = _load_link_state(profile)
    if _is_pair_linked(profile, link_state, args.channel) and not args.force:
        partner = _partner_channel(profile, args.channel)
        sys.exit(f'channel {args.channel} is CLI-tracked as linked to channel {partner} (see `status`). '
                 f'input_mode cannot be changed on a linked pair -- confirmed device behavior '
                 f'(params.channel_link.mode_requires_unlink) is: unlink -> set mode independently '
                 f'per channel -> re-link. Use --force to send it anyway (not expected to work as you want).')

    transport = get_transport(profile)
    old = require_state(transport, profile, args.channel, args.timeout)
    new_val = proto.mode_value(profile, args.mode)
    warn_unverified_channel(profile, args.channel)

    hiz_channels = profile['channels'].get('hiz_channels')
    if args.mode == 'hiz' and hiz_channels is not None and args.channel not in hiz_channels:
        if not args.force:
            sys.exit(f'Hi-Z is not available on channel {args.channel} on this device '
                     f'(only {hiz_channels}). Use --force if you believe this profile is wrong.')
        print(f'note: forcing hiz on channel {args.channel}, outside the known hiz_channels {hiz_channels}.')

    mic_val = proto.mode_value(profile, 'mic')
    if old.get('phantom') and old.get('input_mode') == mic_val and new_val != mic_val:
        pkt = proto.build_command(profile, 'phantom', args.channel, 0)
        send_and_wait(transport, pkt)

    pkt = proto.build_command(profile, 'input_mode', args.channel, new_val)
    send_and_wait(transport, pkt)
    verify(transport, profile, args.channel, args.timeout)


def _channel_and_partner_state(transport, profile, channel, timeout):
    """Reads ONE state report and parses both `channel` and its link partner
    (if any) out of it -- cheaper and more temporally consistent than two
    separate HID reads. Returns (state, partner_state_or_None, partner_or_None)."""
    data = read_state(transport, profile, timeout)
    if not data:
        sys.exit('Could not read a state report. Is the device awake and not busy?')
    partner = _partner_channel(profile, channel)
    state = proto.parse_state(profile, data, channel)
    partner_state = proto.parse_state(profile, data, partner) if partner is not None else None
    return state, partner_state, partner


def cmd_set_gain(args, profile):
    enforce_target(profile, args.channel, 'input', args.force)
    transport = get_transport(profile)
    s, s_partner, partner = _channel_and_partner_state(transport, profile, args.channel, args.timeout)
    mode = proto.mode_name(profile, s.get('input_mode', -1))
    lo, hi = proto.gain_range(profile, mode)
    if not args.force and not (lo <= args.dB <= hi):
        sys.exit(f'Gain {args.dB} outside observed range {lo}..{hi} for mode {mode}. Use --force to override.')
    warn_unverified_channel(profile, args.channel)
    pkt = proto.build_command(profile, 'gain', args.channel, args.dB)
    send_and_wait(transport, pkt)
    verify(transport, profile, args.channel, args.timeout)

    link_state = _load_link_state(profile)
    if partner is not None and _is_pair_linked(profile, link_state, args.channel):
        if s_partner and s_partner.get('input_mode') != s.get('input_mode') and not args.force:
            partner_mode = proto.mode_name(profile, s_partner.get('input_mode', -1))
            print(f'note: channel {args.channel} is CLI-tracked as linked to channel {partner}, but '
                  f'their modes currently differ ({mode} vs {partner_mode}) -- the link cache may be '
                  f'stale. NOT mirroring gain to channel {partner}. Re-run `set-link` to re-sync, or '
                  f'use --force to mirror anyway.')
        else:
            print(f'note: mirroring gain to linked channel {partner} -- this is done by THIS CLI, '
                  f'replicating what the official Launcher does. The device itself does not '
                  f'auto-mirror parameter changes across a linked pair (confirmed on real hardware).')
            pkt2 = proto.build_command(profile, 'gain', partner, args.dB)
            send_and_wait(transport, pkt2)
            verify(transport, profile, partner, args.timeout)


def cmd_set_phantom(args, profile):
    enforce_target(profile, args.channel, 'input', args.force)
    transport = get_transport(profile)
    s, s_partner, partner = _channel_and_partner_state(transport, profile, args.channel, args.timeout)
    mic_val = proto.mode_value(profile, 'mic')
    on = 1 if args.state == 'on' else 0
    if on and s.get('input_mode') != mic_val and not args.force:
        sys.exit('Refusing to turn on 48V outside mic mode. Use --force if you are sure.')
    warn_unverified_channel(profile, args.channel)
    pkt = proto.build_command(profile, 'phantom', args.channel, on)
    send_and_wait(transport, pkt)
    verify(transport, profile, args.channel, args.timeout)

    link_state = _load_link_state(profile)
    if partner is not None and _is_pair_linked(profile, link_state, args.channel):
        if on and s_partner and s_partner.get('input_mode') != mic_val and not args.force:
            print(f'note: channel {args.channel} is CLI-tracked as linked to channel {partner}, but '
                  f'channel {partner} is not in mic mode -- NOT mirroring 48V there (it would be '
                  f'refused the same way a direct set-phantom would be). Use --force to attempt it anyway.')
        else:
            print(f'note: mirroring 48V to linked channel {partner} (CLI-side -- see set-gain\'s note).')
            pkt2 = proto.build_command(profile, 'phantom', partner, on)
            send_and_wait(transport, pkt2)
            verify(transport, profile, partner, args.timeout)


def cmd_set_invert(args, profile):
    enforce_target(profile, args.channel, 'input', args.force)
    transport = get_transport(profile)
    s, s_partner, partner = _channel_and_partner_state(transport, profile, args.channel, args.timeout)
    on = 1 if args.state == 'on' else 0
    warn_unverified_channel(profile, args.channel)
    pkt = proto.build_command(profile, 'phase_invert', args.channel, on)
    send_and_wait(transport, pkt)
    verify(transport, profile, args.channel, args.timeout)

    link_state = _load_link_state(profile)
    if partner is not None and _is_pair_linked(profile, link_state, args.channel):
        print(f'note: mirroring phase invert to linked channel {partner} (CLI-side -- see set-gain\'s note).')
        pkt2 = proto.build_command(profile, 'phase_invert', partner, on)
        send_and_wait(transport, pkt2)
        verify(transport, profile, partner, args.timeout)


# ---- channel-link: CLI-side state tracking (NOT a device readback) ----
#
# The protocol has no confirmed "link enabled" bit anywhere in the 0x73 state
# report (see profile params.channel_link.notes -- re-verified independently
# against the raw ch-link-gain-ph-inv-test.tsv capture: the state report is
# byte-for-byte identical immediately before/after all 4 link/unlink commands
# in that session). So "is this pair linked" can't be read back from the
# device at all -- only from a live side effect (gain/phantom/phase mirroring
# while linked), which needs an actual value change to be visible, or from
# remembering what this CLI itself last sent.
#
# What follows is the latter: a small on-disk cache of "what did *this CLI*
# last tell the device", used only to paint an indicator in `status`. It is
# NOT a substitute for a real readback, can drift from truth (the official
# Launcher, or another instance of this CLI, can change link state without
# this cache knowing), and is labeled as such everywhere it's shown.

def _link_state_path(profile, kind=''):
    """Where to cache CLI-issued link state for this device (by vid/pid).
    `kind` selects a separate cache file: '' for physical input channels
    (unchanged filename), 'adat' for the ADAT link space. Returns None
    (caller should just skip caching) if $HOME isn't usable -- this is a
    convenience cache, never something to hard-fail a command over."""
    try:
        home = os.path.expanduser('~')
        if not home or home == '~':
            return None
        dev = profile.get('device', {})
        vid = dev.get('vid', '0'); pid = dev.get('pid', '0')
        vid = int(vid, 16) if isinstance(vid, str) else vid
        pid = int(pid, 16) if isinstance(pid, str) else pid
        d = os.path.join(home, '.cache', 'antelope-ctl')
        os.makedirs(d, exist_ok=True)
        suffix = f'_{kind}' if kind else ''
        return os.path.join(d, f'link_state{suffix}_{vid:04x}_{pid:04x}.json')
    except OSError:
        return None


def _load_link_state(profile, kind=''):
    path = _link_state_path(profile, kind)
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f).get('pairs', {})
    except (OSError, ValueError):
        return {}  # corrupt/unreadable cache -- treat as "nothing known", don't crash


def _is_pair_linked(profile, link_state, ch):
    """True if THIS CLI's cache (see _load_link_state) thinks ch's pair is
    linked. Not a device fact -- there is no device-side readback (see the
    big comment above this section) -- just the last `set-link`/`mark-link`
    this CLI has issued for that pair. Works for both physical and ADAT
    channels (pair_index = ch // 2 in both spaces); pass the matching
    link_state from _load_link_state(profile, kind)."""
    return bool(link_state.get(str(ch // 2)))


def _save_link_state(profile, pair, enabled, kind=''):
    path = _link_state_path(profile, kind)
    if not path:
        return
    pairs = _load_link_state(profile, kind)
    pairs[str(pair)] = bool(enabled)
    try:
        with open(path, 'w') as f:
            json.dump({'pairs': pairs, 'source': 'cli-issued commands only, not a device readback'}, f)
    except OSError:
        pass  # best-effort cache; never fail the actual command over this


def _pair_channel_snapshot(transport, profile, lo, hi, timeout):
    """Read both channels' gain/phantom/phase_invert -- the three fields
    confirmed (ch-link-gain-ph-inv-test) to live-sync across a linked pair.
    Returns (state_lo, state_hi) dicts, or (None, None) if no report arrived."""
    data = read_state(transport, profile, timeout)
    if not data:
        return None, None
    try:
        return proto.parse_state(profile, data, lo), proto.parse_state(profile, data, hi)
    except ValueError:
        return None, None


def _synced_fields_match(s_lo, s_hi):
    if not s_lo or not s_hi:
        return None
    fields = ['gain', 'phantom', 'phase_invert']
    return all(s_lo.get(f) == s_hi.get(f) for f in fields if f in s_lo and f in s_hi)


def _push_full_sync(transport, profile, target_ch, target_state, source_state):
    """Forces target_ch's mode/gain/phantom/phase_invert to match source_state,
    replicating what the official Launcher sends when a link is first engaged.

    CONFIRMED ON REAL HARDWARE (user report, 2026-08): sending only the raw
    SET_LINK frame engages a real link flag (visible on the Orion's own
    control panel), but the device does NOT itself propagate mode/gain to
    the other channel -- each channel keeps whatever value it already had.
    The apparent "device syncs them" behavior documented in
    params.channel_link.side_effects is the official Launcher software
    sending its own separate SET_PARAM commands right after the link
    command, not a firmware side effect (also directly visible in the
    ch-link-gain-ph-inv-test.tsv capture: every gain change while linked
    shows TWO outgoing SET_PARAM(gain,...) frames, one per channel, a few ms
    apart -- not one frame with device-side fanout). This function is this
    CLI doing the same thing the Launcher does.

    Only sends a command for a field that actually differs, and in an order
    that respects real constraints: mode before gain (gain's valid range
    depends on mode) and before phantom (phantom is mic-only), phantom
    turned off first if leaving mic mode entirely (mirrors cmd_set_mode)."""
    mic_val = proto.mode_value(profile, 'mic')
    src_mode = source_state.get('input_mode')
    tgt_mode = target_state.get('input_mode')

    if src_mode is not None and src_mode != tgt_mode:
        if target_state.get('phantom') and tgt_mode == mic_val and src_mode != mic_val:
            send_and_wait(transport, proto.build_command(profile, 'phantom', target_ch, 0))
        send_and_wait(transport, proto.build_command(profile, 'input_mode', target_ch, src_mode))

    src_gain = source_state.get('gain')
    if src_gain is not None and src_gain != target_state.get('gain'):
        send_and_wait(transport, proto.build_command(profile, 'gain', target_ch, src_gain))

    src_phantom = source_state.get('phantom')
    effective_mode = src_mode if src_mode is not None else tgt_mode
    if src_phantom is not None and src_phantom != target_state.get('phantom') and effective_mode == mic_val:
        send_and_wait(transport, proto.build_command(profile, 'phantom', target_ch, src_phantom))

    src_phase = source_state.get('phase_invert')
    if src_phase is not None and src_phase != target_state.get('phase_invert'):
        send_and_wait(transport, proto.build_command(profile, 'phase_invert', target_ch, src_phase))


def cmd_set_link(args, profile):
    """Engage/disengage the link for the pair that `channel` belongs to
    (pair_index = channel // 2, see channels.link_pairs in the profile).
    Uses build_link_command(), NOT build_command() -- channel_link is a
    different frame shape (frame.link_command), not a SET_PARAM param.

    On link-ON, this now ALSO pushes the higher-numbered channel's
    mode/gain/phantom/phase to match the lower one's (see _push_full_sync)
    -- confirmed necessary on real hardware, since the device itself does
    not do this on receiving the raw link command; the official Launcher
    sends the sync as separate explicit commands, so this CLI does too.
    From then on, `set-gain`/`set-phantom`/`set-invert` will also mirror to
    the linked partner for as long as this CLI's cache says the pair is
    linked -- see those commands and _is_pair_linked.

    Since there's still no device-side link-STATUS readback (see the module
    note above), this also snapshots gain/phantom/phase_invert for both
    channels before/after to report whether the pair's fields agree
    afterward, and caches the commanded state locally so `status` can show
    an indicator -- clearly marked as CLI-tracked, not device-confirmed.
    """
    pair = proto.pair_index_for_channel(args.channel)
    max_pair = profile['channels'].get('link_pairs', {}).get('count', 0) - 1
    if not (0 <= pair <= max_pair) and not args.force:
        sys.exit(f'channel {args.channel} maps to link pair {pair}, outside the confirmed '
                 f'0..{max_pair} range. Use --force if you believe this profile is wrong.')

    lo = pair * 2
    hi = pair * 2 + 1
    print(f'note: this links channels {lo} and {hi} (pair {pair}).')

    transport = get_transport(profile)
    on = args.state == 'on'

    before_lo, before_hi = _pair_channel_snapshot(transport, profile, lo, hi, args.timeout)
    before_match = _synced_fields_match(before_lo, before_hi)

    pkt = proto.build_link_command(profile, pair, on)
    send_and_wait(transport, pkt, delay=0.3)

    if on:
        if before_lo and before_hi:
            if not before_match:
                print(f'pushing channel {hi}\'s mode/gain/phantom/phase to match channel {lo}\'s -- '
                      f'the device does not do this on its own (see _push_full_sync\'s docstring).')
                _push_full_sync(transport, profile, hi, before_hi, before_lo)
            else:
                print(f'channels {lo}/{hi} already matched on gain/phantom/phase_invert -- nothing to push.')
        else:
            print('warning: could not read state before linking, so the mode/gain sync push was '
                  'skipped -- link command was still sent. Check the Launcher UI and consider '
                  're-running set-link.')

    after_lo, after_hi = _pair_channel_snapshot(transport, profile, lo, hi, args.timeout)
    after_match = _synced_fields_match(after_lo, after_hi)

    if on:
        if after_match:
            print('confirmed: gain/phantom/phase_invert now match across the pair. From here, '
                  '`set-gain`/`set-phantom`/`set-invert` on either channel will mirror to the other '
                  'as long as this CLI thinks the pair is linked (see `status`).')
        else:
            print('warning: channels still differ on gain/phantom/phase_invert after syncing -- '
                  'something did not land. Check the Launcher UI before relying on this link.')
    else:
        print('sent. note: disengaging has no known observable state-report effect on its own -- '
              'the practical effect from here is that this CLI stops mirroring set-gain/set-phantom/'
              'set-invert to the other channel, since its cache now says this pair is unlinked.')

    _save_link_state(profile, pair, on)


def cmd_mark_link(args, profile):
    """Update ONLY this CLI's local link-state cache -- no command is sent to
    the device. Use this when a pair was linked/unlinked through the official
    Launcher (or another tool) and you want this CLI's `status` indicator and
    set-gain/set-phantom/set-invert mirroring to reflect that, without
    re-toggling the hardware (which would just re-run the same push again).
    Also useful to correct a stale cache after using both tools in the same
    session."""
    pair = proto.pair_index_for_channel(args.channel)
    max_pair = profile['channels'].get('link_pairs', {}).get('count', 0) - 1
    if not (0 <= pair <= max_pair) and not args.force:
        sys.exit(f'channel {args.channel} maps to link pair {pair}, outside the confirmed '
                 f'0..{max_pair} range. Use --force if you believe this profile is wrong.')
    on = args.state == 'on'
    _save_link_state(profile, pair, on)
    lo, hi = pair * 2, pair * 2 + 1
    print(f'cache updated: pair {pair} (channels {lo}/{hi}) now marked as '
          f'{"linked" if on else "unlinked"} in this CLI\'s local cache. No command was sent to the device.')


# ---- subcommands: ADAT input channels (gain + link) ----
#
# ADAT is a separate 16-channel address space from the 12 physical hybrid
# inputs. ADAT channels have gain and link only -- no mode/phantom/phase.
# The link works exactly like the physical-preamp link (user-confirmed on
# hardware, 2026-08): the device does NOT propagate a gain change to the
# linked partner itself, so -- just like set-gain/set-link -- this CLI
# replicates the Launcher's behaviour by sending a second SET_PARAM(adat_gain)
# for the partner while its cache says the pair is linked. Link state uses a
# separate cache file (kind='adat'); same "not a device readback" caveats as
# the physical link cache (see the big comment above cmd_set_link).

def _adat_partner_channel(profile, ch):
    """The other ADAT channel in ch's link pair (pair_index = ch // 2 over the
    16-channel ADAT space), or None if ch is outside any known pair."""
    max_pair = profile.get('adat', {}).get('link_pairs', {}).get('count', 0) - 1
    pair = ch // 2
    if not (0 <= pair <= max_pair):
        return None
    return ch + 1 if ch % 2 == 0 else ch - 1


def _adat_link_bracket(profile, link_state, ch):
    """Same as _link_bracket() but for the ADAT link space / cache."""
    count = profile.get('adat', {}).get('link_pairs', {}).get('count', 0)
    pair = ch // 2
    if pair >= count or not link_state.get(str(pair)):
        return '', ''
    lo, hi = pair * 2, pair * 2 + 1
    if ch == lo:
        return ' -.', ''
    if ch == hi:
        return " -'", f'  (linked, ADAT pair {pair} -- CLI-tracked, not device-confirmed)'
    return '', ''


def _verify_adat(transport, profile, ch, timeout):
    time.sleep(0.1)
    data = read_state(transport, profile, timeout)
    if not data:
        print('sent command, but no immediate readback was available')
        return
    try:
        print(f'readback: ADAT ch {ch}  gain={proto.parse_adat_gain(profile, data, ch)}dB')
    except ValueError as e:
        print(f'readback unavailable: {e}')


def cmd_adat_status(args, profile):
    n_channels = _resolve_channel_count(args, profile, 'adat')
    if not n_channels:
        sys.exit(f"{profile['device'].get('name', 'this device')} has no ADAT "
                 f"(no `adat` block in the profile). Nothing to show.")
    transport = get_transport(profile)
    data = read_state(transport, profile, args.timeout)
    if not data:
        sys.exit('No state report captured. Try again, or run with sudo if permissions are an issue.')
    link_state = _load_link_state(profile, 'adat')
    print(f"{'adat':>4}  {'gain':>5}")
    for ch in range(n_channels):
        try:
            g = proto.parse_adat_gain(profile, data, ch)
        except ValueError:
            break
        glyph, tail = _adat_link_bracket(profile, link_state, ch)
        print(f"{ch:>4}  {g:>4}dB{glyph}{tail}")
    if link_state:
        print("note: the '-.'/\"-'\" markers reflect the last `set-adat-link` command THIS CLI has "
              "sent (cached locally) -- there is no device-side ADAT link readback, so they can go "
              "stale if link state changes outside this CLI.")


def cmd_set_adat_gain(args, profile):
    enforce_target(profile, args.channel, 'adat', args.force)
    lo, hi = proto.constraints(profile).get('adat_gain_bounds', proto.adat_gain_range(profile))
    if not args.force and not (lo <= args.dB <= hi):
        sys.exit(f'ADAT gain {args.dB} outside the confirmed range {lo}..{hi}. Use --force to override.')

    transport = get_transport(profile)
    send_and_wait(transport, proto.build_command(profile, 'adat_gain', args.channel, args.dB))
    _verify_adat(transport, profile, args.channel, args.timeout)

    partner = _adat_partner_channel(profile, args.channel)
    link_state = _load_link_state(profile, 'adat')
    if partner is not None and _is_pair_linked(profile, link_state, args.channel):
        print(f'note: mirroring gain to linked ADAT channel {partner} -- done by THIS CLI, '
              f'replicating the Launcher. The device does not auto-mirror across a linked pair '
              f'(same as the physical-preamp link).')
        send_and_wait(transport, proto.build_command(profile, 'adat_gain', partner, args.dB))
        _verify_adat(transport, profile, partner, args.timeout)


def _adat_pair_gains(transport, profile, lo, hi, timeout):
    data = read_state(transport, profile, timeout)
    if not data:
        return None, None
    try:
        return proto.parse_adat_gain(profile, data, lo), proto.parse_adat_gain(profile, data, hi)
    except ValueError:
        return None, None


def cmd_set_adat_link(args, profile):
    """Engage/disengage the link for the ADAT pair `channel` belongs to
    (pair_index = channel // 2 over the 16-channel ADAT space, 8 pairs).

    Uses build_link_command() -- the SAME frame the physical channel link
    uses (frame.link_command, opcode 0x14 / param 0xa2). NOTE: that frame is
    byte-for-byte identical between the two spaces and pair_index 0-5 is
    shared, so for ADAT pairs 0-5 this command may also toggle the matching
    PHYSICAL link -- see params.adat_channel_link.notes. Pairs 6-7 are
    ADAT-only.

    On link-ON, pushes the higher-numbered ADAT channel's gain to match the
    lower one's (the device doesn't do this itself), then set-adat-gain will
    mirror to the partner while this CLI's cache says the pair is linked."""
    pair = proto.pair_index_for_channel(args.channel)
    max_pair = profile.get('adat', {}).get('link_pairs', {}).get('count', 0) - 1
    if not (0 <= pair <= max_pair) and not args.force:
        sys.exit(f'ADAT channel {args.channel} maps to link pair {pair}, outside the confirmed '
                 f'0..{max_pair} range. Use --force if you believe this profile is wrong.')

    lo, hi = pair * 2, pair * 2 + 1
    on = args.state == 'on'
    print(f'note: this links ADAT channels {lo} and {hi} (pair {pair}).')
    if pair <= 5:
        print(f'note: the ADAT and physical link frames are identical -- pair {pair} may also '
              f'toggle the physical ch{lo + 1}&ch{hi + 1} link. See params.adat_channel_link.notes.')

    transport = get_transport(profile)
    before_lo, before_hi = _adat_pair_gains(transport, profile, lo, hi, args.timeout)

    send_and_wait(transport, proto.build_link_command(profile, pair, on), delay=0.3)

    if on and before_lo is not None and before_hi is not None and before_lo != before_hi:
        print(f'pushing ADAT ch {hi} gain to match ch {lo} ({before_lo}dB) -- the device does '
              f'not do this on its own.')
        send_and_wait(transport, proto.build_command(profile, 'adat_gain', hi, before_lo))

    after_lo, after_hi = _adat_pair_gains(transport, profile, lo, hi, args.timeout)
    if on:
        if after_lo is not None and after_lo == after_hi:
            print('confirmed: ADAT ch gains now match across the pair. set-adat-gain on either '
                  'channel will mirror to the other while this CLI thinks the pair is linked.')
        else:
            print('warning: ADAT ch gains still differ after syncing -- check the Launcher UI.')
    else:
        print('sent. disengaging has no known observable readback -- the practical effect is that '
              'this CLI stops mirroring set-adat-gain to the partner.')

    _save_link_state(profile, pair, on, 'adat')


def cmd_mark_adat_link(args, profile):
    """Update ONLY this CLI's local ADAT link-state cache -- no device command.
    Use when an ADAT pair was linked/unlinked via the Launcher and you want
    set-adat-gain mirroring / adat-status to reflect it."""
    pair = proto.pair_index_for_channel(args.channel)
    max_pair = profile.get('adat', {}).get('link_pairs', {}).get('count', 0) - 1
    if not (0 <= pair <= max_pair) and not args.force:
        sys.exit(f'ADAT channel {args.channel} maps to link pair {pair}, outside the confirmed '
                 f'0..{max_pair} range. Use --force if you believe this profile is wrong.')
    on = args.state == 'on'
    _save_link_state(profile, pair, on, 'adat')
    lo, hi = pair * 2, pair * 2 + 1
    print(f'cache updated: ADAT pair {pair} (channels {lo}/{hi}) now marked as '
          f'{"linked" if on else "unlinked"} in this CLI\'s local cache. No command was sent.')


# ---- subcommands: S/PDIF input (2 channels L/R, gain + link) ----
#
# S/PDIF is a 2-channel space (0 = L, 1 = R), gain + link only. The link
# frame carries space byte 0x01 (frame.link_command.space_offset), so unlike
# the ADAT link it is NOT ambiguous with the physical link. Gain mirroring
# while linked works exactly like set-gain/set-adat-gain -- the device does
# not propagate, this CLI sends the second SET_PARAM. Separate link cache
# (kind='spdif').

_SPDIF_LINK_SPACE = 1  # frame.link_command space value for S/PDIF; physical/ADAT use 0


def _spdif_partner(ch):
    return 1 - ch if ch in (0, 1) else None


def _spdif_link_bracket(profile, link_state, ch):
    if 'spdif' not in profile or not link_state.get('0'):
        return '', ''
    if ch == 0:
        return ' -.', ''
    if ch == 1:
        return " -'", '  (linked -- CLI-tracked, not device-confirmed)'
    return '', ''


def _verify_spdif(transport, profile, ch, timeout):
    time.sleep(0.1)
    data = read_state(transport, profile, timeout)
    if not data:
        print('sent command, but no immediate readback was available')
        return
    try:
        print(f'readback: S/PDIF ch {ch} ({"L" if ch == 0 else "R"})  gain={proto.parse_spdif_gain(profile, data, ch)}dB')
    except ValueError as e:
        print(f'readback unavailable: {e}')


def cmd_spdif_status(args, profile):
    transport = get_transport(profile)
    data = read_state(transport, profile, args.timeout)
    if not data:
        sys.exit('No state report captured. Try again, or run with sudo if permissions are an issue.')
    link_state = _load_link_state(profile, 'spdif')
    print(f"{'spdif':>5}  {'gain':>5}")
    for ch, name in ((0, 'L'), (1, 'R')):
        try:
            g = proto.parse_spdif_gain(profile, data, ch)
        except ValueError:
            break
        glyph, tail = _spdif_link_bracket(profile, link_state, ch)
        print(f"{ch} ({name})  {g:>4}dB{glyph}{tail}")
    if link_state:
        print("note: link marker reflects the last `set-spdif-link` from THIS CLI (cached) -- "
              "no device-side readback.")


def cmd_set_spdif_gain(args, profile):
    enforce_target(profile, args.channel, 'spdif', args.force)
    lo, hi = proto.constraints(profile).get('spdif_gain_bounds',
                                            profile['params'].get('spdif_gain', {}).get('range', [-128, 127]))
    if not args.force and not (lo <= args.dB <= hi):
        sys.exit(f'S/PDIF gain {args.dB} outside the confirmed range {lo}..{hi}. Use --force to override.')

    transport = get_transport(profile)
    send_and_wait(transport, proto.build_command(profile, 'spdif_gain', args.channel, args.dB))
    _verify_spdif(transport, profile, args.channel, args.timeout)

    partner = _spdif_partner(args.channel)
    if partner is not None and _load_link_state(profile, 'spdif').get('0'):
        print(f'note: mirroring gain to linked S/PDIF channel {partner} -- done by THIS CLI, '
              f'replicating the Launcher (the device does not auto-mirror).')
        send_and_wait(transport, proto.build_command(profile, 'spdif_gain', partner, args.dB))
        _verify_spdif(transport, profile, partner, args.timeout)


def cmd_set_spdif_link(args, profile):
    """Engage/disengage the S/PDIF L/R link. Uses frame.link_command with
    space byte 0x01 (frame.link_command.space_offset) -- distinct from the
    physical/ADAT link (space 0x00), so no cross-space ambiguity. On link-ON
    pushes ch1's gain to match ch0's; from then on set-spdif-gain mirrors to
    the partner while this CLI's cache says the pair is linked."""
    on = args.state == 'on'
    transport = get_transport(profile)

    def gains():
        data = read_state(transport, profile, args.timeout)
        if not data:
            return None, None
        try:
            return proto.parse_spdif_gain(profile, data, 0), proto.parse_spdif_gain(profile, data, 1)
        except ValueError:
            return None, None

    before_l, before_r = gains()
    send_and_wait(transport, proto.build_link_command(profile, 0, on, space=_SPDIF_LINK_SPACE), delay=0.3)

    if on and before_l is not None and before_r is not None and before_l != before_r:
        print(f'pushing S/PDIF ch1 (R) gain to match ch0 (L) ({before_l}dB) -- the device does not do this itself.')
        send_and_wait(transport, proto.build_command(profile, 'spdif_gain', 1, before_l))

    after_l, after_r = gains()
    if on:
        if after_l is not None and after_l == after_r:
            print('confirmed: S/PDIF L/R gains match. set-spdif-gain on either channel now mirrors to the other.')
        else:
            print('warning: S/PDIF L/R gains still differ after syncing -- check the Launcher UI.')
    else:
        print('sent. disengaging has no known readback -- this CLI just stops mirroring set-spdif-gain.')

    _save_link_state(profile, 0, on, 'spdif')


def cmd_mark_spdif_link(args, profile):
    """Update ONLY this CLI's local S/PDIF link cache -- no device command."""
    on = args.state == 'on'
    _save_link_state(profile, 0, on, 'spdif')
    print(f'cache updated: S/PDIF L/R link now marked {"linked" if on else "unlinked"}. No command was sent.')


# ---- subcommands: routing matrix (EXPERIMENTAL) ----
#
# Only the 5 two-channel destinations (hp1/hp2/mona/monb/reamp) are wired
# in. The frame model is decoded (frame.routing_command.frame_model): after
# byte 18 it's an array of (source_bank, source_index) pairs, one per output
# channel of the destination group -- so the WHOLE group is sent every time,
# and to change one channel we must resend the others. There is NO device
# readback yet (frame.routing_command has none; see params.routing.readback),
# so `matrix-status` shows only a local cache of what THIS CLI last sent,
# and `keep` for a channel reads from that cache. Like the Launcher there is
# no un-route: replace a source or set it to mute.

def _matrix_state_path(profile):
    return _link_state_path(profile, 'matrix')


def _load_matrix_state(profile):
    """Return {dest_id_str: {chan_str: {'bank':int,'idx':int,'label':str}}}.
    Silently drops anything not in that shape (e.g. the pre-2026-08 flat
    `{"1.1": "preamp 3"}` cache written by the old buggy route builder)."""
    path = _matrix_state_path(profile)
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            raw = json.load(f).get('routes', {})
    except (OSError, ValueError):
        return {}
    out = {}
    for d, chans in (raw.items() if isinstance(raw, dict) else []):
        if isinstance(chans, dict) and all(
                isinstance(v, dict) and 'bank' in v and 'idx' in v for v in chans.values()):
            out[d] = chans
    return out


def _save_matrix_dest(profile, dest, channels):
    """channels: ordered list of (bank, idx) -- the whole group, as just sent."""
    path = _matrix_state_path(profile)
    if not path:
        return
    routes = _load_matrix_state(profile)
    routes[str(dest)] = {
        str(c): {'bank': b, 'idx': i,
                 'label': proto.route_source_label(profile, b, i)}
        for c, (b, i) in enumerate(channels)
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump({'routes': routes,
                       'source': 'last-known routing (CLI writes + device readbacks, cat 0x03)'}, f)
    except OSError:
        pass


def _parse_route_source(token):
    """'preamp3' -> ('preamp', '3'); 'spdifL' -> ('spdif', 'L'); 'mix2r' ->
    ('mix2', 'r'); 'mute' -> ('mute', None); 'keep' -> ('keep', None)."""
    t = re.sub(r'[\s:_-]+', '', token.strip().lower())  # "comp play 2" -> "compplay2"
    if t in ('mute', 'off'):
        return 'mute', None
    if t in ('keep', 'same', ''):
        return 'keep', None
    m = re.match(r'^([a-z]+[0-9]*?)([0-9]+|[lr])$', t)   # mix2 + r ; preamp + 3
    if not m:
        raise SystemExit(f"can't parse routing source '{token}' -- try "
                         f"preamp3 / emumic7 / compplay1 / adat5 / afx7 / surround2 / "
                         f"spdifL / mix2R / osc1 / mute / keep")
    return m.group(1), m.group(2)


def _expand_route_tokens(tokens):
    """Expand shorthand range tokens in a `route ... all` source list so a
    16-channel dest doesn't need 16 words. `compplay1..16` / `compplay1-16`
    -> compplay1 compplay2 ... compplay16 (ascending or descending). A bare
    `mute` / `keep` / non-range token passes straight through."""
    out = []
    for tok in tokens:
        m = re.match(r'^([a-z]+)\s*([0-9]+)\s*(?:\.\.|-)\s*([0-9]+)$',
                     tok.strip().lower())
        if not m:
            out.append(tok)
            continue
        name, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        step = 1 if b >= a else -1
        out.extend(f'{name}{n}' for n in range(a, b + step, step))
    return out


def _route_source_tuple(profile, token, dest, chan, cache):
    """Resolve one channel's source token to (bank, idx). `keep` -> the cached
    value for (dest, chan), erroring with a hint if there is none."""
    kind, number = _parse_route_source(token)
    if kind == 'keep':
        c = cache.get(str(dest), {}).get(str(chan))
        if not c:
            word = _dest_word(profile, dest)
            sys.exit(f"channel {chan + 1}: no source for it to keep -- the device read "
                     f"of {word} didn't return a value for this channel. Retry, or set the "
                     f"whole group: `route {word} all <src1> <src2> ...` "
                     f"(range shorthand like `compplay1..16` works).")
        return c['bank'], c['idx']
    try:
        return proto.resolve_route_source(profile, kind, number)
    except ValueError as e:
        sys.exit(str(e))


def _dest_word(profile, dest_id):
    addr = profile['frame'].get('routing_command', {}).get('addressable_destinations', {})
    return addr.get(str(dest_id), str(dest_id))


def cmd_route(args, profile):
    """Route sources into an output group.  route <dest> <chan|all|mute> [<source>...]

    The wire frame carries the WHOLE destination group every time, so a
    per-channel change resends the other channels -- read live from the
    device first (frame.readback cat 0x03). After the write we read the
    group back and confirm it matches. Like the Antelope Launcher there is
    no "un-route" -- replace a channel's source or set it to mute.

      route lineout 3 afx5     set line-out channel 3, keep the rest
      route hp1 L preamp3      L = channel 1 for stereo dests (hp1/hp2/mona/monb)
      route hp1 all preamp3 preamp4     set every channel
      route lineout all compplay1..16   range shorthand for a 16-ch set
      route lineout 4 mute     mute one channel
      route hp2 mute           mute every channel
    """
    dest = _resolve_route_dest_cli(profile, args.destination)
    try:
        nchan = proto.route_dest_channels(profile, dest)
    except ValueError as e:
        sys.exit(str(e))
    mute = tuple(profile['frame']['routing_command'].get('mute_source', [11, 0]))
    cache = _load_matrix_state(profile)
    sel = args.selector.strip().lower()
    srcs = _expand_route_tokens(args.source)

    # For a per-channel edit we need the OTHER channels' current sources. The
    # device now supports a live read (frame.readback cat 0x03), so seed the
    # cache from the device instead of erroring when it's empty.
    if sel not in ('mute', 'all') and not cache.get(str(dest)):
        try:
            pairs = _read_routing_dest(get_transport(profile), profile, dest, timeout=args.timeout)
        except SystemExit:
            pairs = None
        if pairs:
            _save_matrix_dest(profile, dest, pairs)
            cache = _load_matrix_state(profile)
            print(f'(read current {args.destination} routing from the device)')

    if sel == 'mute':
        if srcs:
            sys.exit('`route <dest> mute` takes no source argument (it mutes every channel)')
        chans = [mute] * nchan
    elif sel == 'all':
        if len(srcs) != nchan:
            sys.exit(f'`route {args.destination} all` needs exactly {nchan} sources '
                     f'(one per channel), got {len(srcs)}')
        chans = [_route_source_tuple(profile, t, dest, i, cache) for i, t in enumerate(srcs)]
    else:
        try:
            ch = proto.resolve_route_channel(profile, dest, sel)
        except ValueError as e:
            sys.exit(str(e))
        if len(srcs) != 1:
            sys.exit(f'`route {args.destination} {args.selector}` needs exactly one source')
        chans = [_route_source_tuple(profile, 'keep', dest, i, cache) for i in range(nchan)]
        chans[ch] = _route_source_tuple(profile, srcs[0], dest, ch, cache)

    stereo = str(dest) in profile['frame']['routing_command'].get('stereo_destinations', [])
    labels = [proto.route_source_label(profile, b, i) for b, i in chans]
    print(f'routing {args.destination} ({nchan} ch):')
    for i, lab in enumerate(labels):
        tag = {0: ' (L)', 1: ' (R)'}.get(i, '') if stereo else ''
        print(f'  ch {i + 1}{tag}: {lab}')
    transport = get_transport(profile)
    pkt = proto.build_route_command(profile, dest, chans)
    send_and_wait(transport, pkt, delay=0.3)
    _save_matrix_dest(profile, dest, chans)
    # verify against a live read (frame.readback cat 0x03)
    back = _read_routing_dest(transport, profile, dest, timeout=args.timeout)
    if back is not None and back == chans:
        print('verified: device readback matches')
        _save_matrix_dest(profile, dest, back)
    elif back is not None:
        print('WARNING: device readback differs from what was sent:')
        for i, (b, ix) in enumerate(back):
            print(f'  ch {i + 1}: {proto.route_source_label(profile, b, ix)}')
        _save_matrix_dest(profile, dest, back)
    else:
        end = 19 + 2 * len(chans)
        print(f'sent: {pkt[16:end].hex()}  (no readback this time -- see `matrix-status`)')


def _routing_dest_name(profile, dest_id):
    rc = profile['frame'].get('routing_command', {})
    names = dict(rc.get('addressable_destinations', {}))
    for k, v in profile.get('params', {}).get('routing', {}).get('destinations', {}).items():
        names.setdefault(str(k), v.split(' (')[0])
    return names.get(str(dest_id), f'dest{dest_id}')


def _read_routing_dest(transport, profile, dest_id, timeout=2.0):
    """Live-read one destination group's routing via frame.readback cat 0x03.
    Returns an ordered list of (bank, idx), or None if the device didn't answer."""
    cat = proto.ROUTING_READBACK_CATEGORY
    req = proto.build_readback_query(profile, cat, dest_id)
    data = transport.query(req, lambda d: proto.is_readback_response(profile, d, cat, dest_id),
                           timeout=timeout)
    if data is None:
        return None
    try:
        _did, pairs = proto.parse_routing_record(profile, proto.readback_body(profile, data))
    except ValueError:
        return None
    return pairs


def cmd_matrix_status(args, profile):
    """Live-read the routing matrix from the device (frame.readback category
    0x03). Falls back to this CLI's cache if the device is unreachable."""
    rc = profile['frame'].get('routing_command', {})
    stereo = set(rc.get('stereo_destinations', []))
    dest_ids = sorted((int(k) for k in rc.get('destination_channels', {})))

    transport = None
    try:
        transport = get_transport(profile)
    except SystemExit:
        transport = None

    live = {}
    if transport is not None:
        for d in dest_ids:
            pairs = _read_routing_dest(transport, profile, d, timeout=args.timeout)
            if pairs is not None:
                live[d] = pairs

    if live:
        print(f"{'destination':<14} {'channel':<10} {'source (device)'}")
        for d in dest_ids:
            if d not in live:
                continue
            for c, (bank, idx) in enumerate(live[d]):
                n = c + 1
                tag = {1: ' (L)', 2: ' (R)'}.get(n, '') if str(d) in stereo else ''
                print(f"{_routing_dest_name(profile, d):<14} {str(n) + tag:<10} "
                      f"{proto.route_source_label(profile, bank, idx)}")
            _save_matrix_dest(profile, d, live[d])   # keep the cache honest for `route ... keep`
        missing = [d for d in dest_ids if d not in live]
        if missing:
            print(f"note: no response for dest {missing} (retry, or the group may be idle).")
        return

    # no device -> cache fallback
    routes = _load_matrix_state(profile)
    if not routes:
        print('could not read the device, and this CLI has no cached routes yet. '
              'Check the connection (or run with the udev rule / sudo).')
        return
    print(f"{'destination':<14} {'channel':<10} {'source (CLI-cached -- device unreachable)'}")
    for d in sorted(routes, key=lambda x: int(x) if x.isdigit() else x):
        for c in sorted(routes[d], key=lambda x: int(x) if x.isdigit() else x):
            n = int(c) + 1 if c.isdigit() else c
            tag = {1: ' (L)', 2: ' (R)'}.get(n, '') if d in stereo else ''
            print(f"{_routing_dest_name(profile, d):<14} {str(n) + tag:<10} "
                  f"{routes[d][c].get('label', '?')}")


def cmd_identity(args, profile):
    """Ask the device who it is (frame.readback categories 0x01 + 0x00).

    The SERIAL is never stored in this repo -- it is read from the hardware
    on request, and only printed when explicitly asked for with --serial, so
    it can't leak into a pasted terminal log or a bug report by accident."""
    transport = get_transport(profile)

    def read(cat):
        req = proto.build_readback_query(profile, cat, 0)
        data = transport.query(
            req, lambda d: proto.is_readback_response(profile, d, cat, 0),
            timeout=args.timeout)
        return proto.readback_body(profile, data) if data is not None else None

    body = read(proto.IDENTITY_READBACK_CATEGORY)
    if body is None:
        sys.exit('no identity response from the device (category 0x01)')
    ident = proto.parse_identity_record(profile, body)

    fw = proto.parse_firmware_record(profile, read(proto.FIRMWARE_READBACK_CATEGORY))

    print(f"name      {ident['name'] or '-'}")
    print(f"hw rev    {ident['revision'] or '-'}")
    print(f"firmware  {fw or '-'}")
    if ident['stamp']:
        # plausibly a build/calibration unix timestamp -- shown as raw + a
        # best-effort date, flagged, because it is a guess (see protocol.py)
        try:
            when = time.strftime('%Y-%m-%d', time.gmtime(ident['stamp']))
            print(f"stamp     {ident['stamp']} (?= {when}, unconfirmed)")
        except (OSError, OverflowError, ValueError):
            print(f"stamp     {ident['stamp']} (unconfirmed)")
    if args.serial:
        print(f"serial    {ident['serial'] or '-'}")
    else:
        n = len(ident['serial'] or '')
        print(f"serial    <{n} chars, hidden -- pass --serial to show>")


def cmd_mix_status(args, profile):
    """Live-read the virtual mixer from the device (frame.readback category
    0x04, index = mix number 0-3). One record per mix, 33 three-byte slots in
    the same field order as the frame.mix_command write frame; slot N is the
    strip that command addresses as `channel` N."""
    cat = proto.MIXER_READBACK_CATEGORY
    n_mixes = proto.readback_category_count(profile, cat) or 4
    if args.mix is None:
        mixes = list(range(n_mixes))
    else:
        if not 1 <= args.mix <= n_mixes:
            sys.exit(f'mix must be 1..{n_mixes} (this device has {n_mixes} mixes)')
        mixes = [args.mix - 1]

    transport = get_transport(profile)
    for m in mixes:
        req = proto.build_readback_query(profile, cat, m)
        data = transport.query(
            req, lambda d: proto.is_readback_response(profile, d, cat, m),
            timeout=args.timeout)
        if data is None:
            print(f'Mix {m + 1}: no response')
            continue
        slots = proto.parse_mixer_record(profile, proto.readback_body(profile, data))
        print(f'\nMix {m + 1}  (master + {len(slots) - 1} strips)')
        print(f"  {'ch':<6} {'fader':<9} {'pan':>4} {'send':>8}  flags")
        for i, s in enumerate(slots):
            # slot 0 is the mix MASTER -- the Launcher writes it as channel 0
            name = 'mast' if i == 0 else str(i)
            flags = ' '.join(f for f, on in (('MUTE', s['mute']), ('SOLO', s['solo'])) if on)
            fader = f"{-s['fader']} dB"   # stored as attenuation; 0 -> "0 dB"
            print(f"  {name:<6} {fader:<9} {s['pan']:>+4} "
                  f"{str(s['send']) + '/96':>8}  {flags}".rstrip())


def _mix_strip_line(i, s, has_send):
    name = 'master' if i == 0 else f'ch {i}'
    flags = ' '.join(f for f, on in (('MUTE', s['mute']), ('SOLO', s['solo'])) if on)
    send = f"  send {s['send']}/96" if has_send else ''
    return (f"{name}: fader {-s['fader']} dB  pan {s['pan']:+d}{send}"
            f"{'  ' + flags if flags else ''}")


def _resolve_mix_channel(token, n_strips):
    """`master`/`m`/`0` -> slot 0 (the mix master), else a 1-based strip
    number. Slot N is the write frame's `channel` N either way -- see
    protocol.parse_mixer_record."""
    t = str(token).strip().lower()
    if t in ('master', 'mast', 'm'):
        return 0
    try:
        n = int(t, 0)
    except ValueError:
        raise SystemExit(f"bad channel {token!r} -- use 1-{n_strips}, or 'master'")
    if not 0 <= n <= n_strips:
        raise SystemExit(f"channel {n} out of range -- use 1-{n_strips}, "
                         f"or 0/'master' for the mix master")
    return n


def cmd_mix_set(args, profile):
    """Change one virtual-mixer strip (frame.mix_command, opcode 0x17/0xd4).

    The write frame carries the strip's WHOLE state every time, so this reads
    the current strip back first (readback cat 0x04), applies only the flags
    you gave, and writes the result -- the same read-modify-write `route`
    does. No local cache, and it refuses to write blind if the read fails."""
    cat = proto.MIXER_READBACK_CATEGORY
    has_send = proto.mix_has_send(profile)
    if args.send is not None and not has_send:
        sys.exit("this device's mixer strip has no send level "
                 '(frame.mix_command declares no send_offset)')

    n_mixes = proto.readback_category_count(profile, cat) or 4
    if not 1 <= args.mix <= n_mixes:
        sys.exit(f'mix must be 1..{n_mixes} (this device has {n_mixes} mixes)')
    m = args.mix - 1

    transport = get_transport(profile)

    def read_slots():
        req = proto.build_readback_query(profile, cat, m)
        data = transport.query(
            req, lambda d: proto.is_readback_response(profile, d, cat, m),
            timeout=args.timeout)
        if data is None:
            return None
        return proto.parse_mixer_record(profile, proto.readback_body(profile, data))

    slots = read_slots()
    if slots is None:
        sys.exit(f'could not read Mix {args.mix} back from the device '
                 f'(frame.readback cat {cat:#04x}). This frame carries the whole '
                 f'strip every time, so writing now would clobber the fields you '
                 f"didn't name -- refusing to write blind.")

    ch = _resolve_mix_channel(args.channel, len(slots) - 1)
    cur = slots[ch]

    if not any(v is not None for v in
               (args.fader, args.pan, args.send, args.mute, args.solo)):
        print(f'Mix {args.mix} {_mix_strip_line(ch, cur, has_send)}')
        opts = ['--fader', '--pan'] + (['--send'] if has_send else []) + ['--mute', '--solo']
        print(f"(no change requested -- pass {'/'.join(opts)} to set one)")
        return

    fader = cur['fader'] if args.fader is None else abs(args.fader)
    pan = cur['pan'] if args.pan is None else args.pan
    send = cur['send'] if args.send is None else args.send
    mute = cur['mute'] if args.mute is None else (args.mute == 'on')
    solo = cur['solo'] if args.solo is None else (args.solo == 'on')

    def _range(key, default):
        return profile.get('params', {}).get(key, {}).get('range', default)

    # fader is stored as attenuation but the user speaks dB, so report in dB
    lo, hi = _range('mix_fader', (0, 90))
    if not lo <= fader <= hi:
        sys.exit(f'fader {-fader} dB out of range: {-lo} to {-hi} dB')
    for name, val, key, default in (('pan', pan, 'mix_pan', (-30, 30)),
                                    ('send', send, 'mix_send', (0, 96))):
        lo, hi = _range(key, default)
        if not lo <= val <= hi:
            sys.exit(f'{name} {val} out of range {lo}..{hi}')

    pkt = proto.build_mix_command(profile, m, ch, fader, pan, send, mute, solo)
    print(f'Mix {args.mix} {_mix_strip_line(ch, cur, has_send)}')
    send_and_wait(transport, pkt, delay=0.3)

    after = read_slots()
    if after is None:
        print('warning: wrote the strip but could not read it back to verify.')
        return
    got = after[ch]
    print(f'     -> {_mix_strip_line(ch, got, has_send)}')
    want = (fader, pan, send if has_send else got['send'], mute, solo)
    if (got['fader'], got['pan'], got['send'], got['mute'], got['solo']) == want:
        print('verified: device readback matches')
    else:
        print('WARNING: device readback does NOT match what was sent '
              f'(sent fader {fader} pan {pan:+d} '
              + (f'send {send} ' if has_send else '')
              + f'mute {mute} solo {solo}).')
    moved = [i for i, (a, b) in enumerate(zip(slots, after)) if a != b and i != ch]
    if moved:
        print(f'note: other strips also changed: {moved} '
              '(a linked pair, or solo re-muting the rest -- both are '
              'host-side behaviours the Launcher does too)')


def cmd_readback(args, profile):
    """Raw frame.readback query: `readback <category> [index]`. No args ->
    list the known categories."""
    cats = proto.readback_categories(profile)
    if args.category is None:
        if not cats:
            print('this profile has no frame.readback.categories')
            return
        print('known readback categories (raw dump: `readback <cat> [idx]`):')
        for k, v in cats.items():
            if k == 'note':
                continue
            print(f'  {k:<6} {v}')
        if 'note' in cats:
            print(f'  ({cats["note"]})')
        return
    cat = int(args.category, 0)
    idx = args.index
    n = proto.readback_category_count(profile, cat)
    if n is None and idx > 0:
        # no evidence-grade record count for this category -> we cannot bounds
        # check it, and an over-range index can BusFault the device.
        print(f'WARNING: category {cat:#04x} has no known record count, so index '
              f'{idx} cannot be bounds-checked. An index past the end of the '
              f"firmware's array can crash the device (power cycle required). "
              f'See frame.readback.hazard.', file=sys.stderr)
    if args.force and os.environ.get('ANTELOPE_ALLOW_UNSAFE_READBACK') != '1':
        # --force alone is too easy to fire off by reflex -- it was used by
        # accident on 2026-08-31 on the one index already known to be fatal,
        # and crashed the device a second time. Require a deliberate second
        # signal so it can never be a throwaway addition to another command.
        sys.exit('--force needs ANTELOPE_ALLOW_UNSAFE_READBACK=1 in the '
                 'environment too. An out-of-range readback index can crash the '
                 'device firmware (BusFault -- physical power cycle required). '
                 'See frame.readback.hazard.')
    transport = get_transport(profile)
    try:
        req = proto.build_readback_query(profile, cat, idx, force=args.force)
    except proto.ConstraintError as e:
        sys.exit(f'{e}\n(pass --force only if you accept crashing the device.)')
    data = transport.query(req, lambda d: proto.is_readback_response(profile, d, cat, idx),
                           timeout=args.timeout)
    if data is None:
        sys.exit(f'no readback response for category {cat:#04x} index {idx}')
    body = proto.readback_body(profile, data)
    trimmed = body.rstrip(b'\x00')
    if cat == 0x01:
        name = body[:16].split(b'\x00')[0].decode('latin1', 'replace')
        print(f'category 0x01: model name {name!r} (serial + rev not printed)')
        return
    print(f'category {cat:#04x} index {idx}: {len(trimmed)} data bytes')
    print(trimmed.hex())
    if cat == proto.ROUTING_READBACK_CATEGORY:
        try:
            did, pairs = proto.parse_routing_record(profile, body)
            print(f'  dest {did} ({_routing_dest_name(profile, did)}):')
            for c, (b, i) in enumerate(pairs):
                print(f'    ch {c + 1}: {proto.route_source_label(profile, b, i)}')
        except ValueError as e:
            print(f'  (not decodable as a routing record: {e})')
    if cat == proto.MIXER_READBACK_CATEGORY:
        try:
            slots = proto.parse_mixer_record(profile, body)
            print(f'  mix {idx + 1}, {len(slots)} slots '
                  f'(slot 0 = unidentified extra; slot N = mix_command channel N):')
            for i, s in enumerate(slots):
                flags = ''.join(f for f, on in ((' MUTE', s['mute']), (' SOLO', s['solo'])) if on)
                print(f"    slot {i:<3} fader -{s['fader']} dB  pan {s['pan']:+d}  "
                      f"send {s['send']}/96{flags}")
        except ValueError as e:
            print(f'  (not decodable as a mixer record: {e})')
    if cat == proto.AURAVERB_READBACK_CATEGORY:
        try:
            for m, mx in enumerate(proto.parse_auraverb_record(profile, body)):
                en = {True: 'ON', False: 'off', None: '?'}[mx['enabled']]
                vals = '  '.join(f'{f.replace("_", "-")}={mx["params"].get(k)}'
                                 for f, k in _AURAVERB_FLAGS.items())
                print(f'  Mix {m + 1}: {en}   {vals}')
        except ValueError as e:
            print(f'  (not decodable as an auraverb record: {e})')
    if cat == proto.PREAMP_GAIN_READBACK_CATEGORY:
        gains = proto.parse_preamp_gain_record(profile, body)
        print('  preamp gain (dB), per channel:  ' +
              '  '.join(f'{c}:{g}' for c, g in enumerate(gains)))
    if cat == proto.CHANNEL_STATUS_READBACK_CATEGORY:
        for c, s in enumerate(proto.parse_channel_status_record(profile, body)):
            extra = ''.join(t for t, on in ((' +48V', s['phantom']),
                                            (' invert', s['phase_invert'])) if on)
            print(f"    ch {c:<2} {s['mode_name']}{extra}")


def _resolve_route_dest_cli(profile, name):
    try:
        return proto.resolve_route_dest(profile, name)
    except ValueError as e:
        sys.exit(str(e))


# ---- subcommands: output buses (monitor A/B, headphone 1/2) ----

def cmd_bus_status(args, profile):
    transport = get_transport(profile)
    data = read_state(transport, profile, args.timeout)
    if not data:
        sys.exit('No state report captured. Try again, or run with sudo if permissions are an issue.')
    known = profile.get('buses', {}).get('known', {})
    print(f"{'id':>2}  {'name':<12} {'level':>5}  {'dim':<3} {'mute':<4} {'mono':<4}")
    for bus_id_str in sorted(known, key=int):
        bus_id = int(bus_id_str)
        try:
            s = proto.parse_bus_state(profile, data, bus_id)
        except ValueError:
            continue
        print(f"{bus_id:>2}  {proto.bus_name(profile, bus_id):<12} {s['level']:>5}  "
              f"{'on' if s.get('dim') else 'off':<3} "
              f"{'on' if s.get('mute') else 'off':<4} "
              f"{'on' if s.get('mono') else 'off':<4}")
    unassigned = profile.get('buses', {}).get('unassigned_ids', [])
    if unassigned:
        print(f'note: bus ids {unassigned} are unconfirmed/unassigned on this device -- not shown.')


def cmd_set_bus_level(args, profile):
    bus_id = resolve_bus(profile, args.bus)
    enforce_target(profile, bus_id, 'bus', args.force)
    transport = get_transport(profile)
    lo, hi = proto.bus_level_range(profile)
    if not args.force and not (lo <= args.level <= hi):
        sys.exit(f'Level {args.level} outside observed range {lo}..{hi}. Use --force to override.')
    pkt = proto.build_command(profile, 'bus_level', bus_id, args.level)
    send_and_wait(transport, pkt)
    verify_bus(transport, profile, bus_id, args.timeout)


def _bus_bool_command(args, profile, param_name):
    """Shared body for set-bus-dim/set-bus-mute/set-bus-mono -- they only
    differ in which param they send."""
    bus_id = resolve_bus(profile, args.bus)
    enforce_target(profile, bus_id, 'bus', getattr(args, 'force', False))
    transport = get_transport(profile)
    on = 1 if args.state == 'on' else 0
    pkt = proto.build_command(profile, param_name, bus_id, on)
    send_and_wait(transport, pkt)
    verify_bus(transport, profile, bus_id, args.timeout)


def cmd_set_bus_dim(args, profile):
    _bus_bool_command(args, profile, 'bus_dim')


def cmd_set_bus_mute(args, profile):
    _bus_bool_command(args, profile, 'bus_mute')


def cmd_set_bus_mono(args, profile):
    _bus_bool_command(args, profile, 'bus_mono')


def cmd_raw_set(args, profile):
    """Escape hatch for exploring not-yet-confirmed params (e.g. routing)
    during a live capture session. See tools/capture_diff.py for finding candidates.

    Enforces profile['constraints']: the target byte must be a legal index in
    SOME address space (0..max of channel/adat/bus bounds), since for an
    unmapped param_id we don't know which space applies -- and an out-of-range
    index BusFaulted a sibling device (hazards.channel_index_out_of_range).
    --force skips that check."""
    c = proto.constraints(profile)
    if c and not args.force:
        maxes = []
        for sp in ('input', 'adat'):
            b = proto.channel_space_bounds(profile, sp)
            if b:
                maxes.append(b[1])
        bus = proto.channel_space_bounds(profile, 'bus')
        if bus:
            maxes.append(max(bus))
        hard_max = max(maxes) if maxes else None
        if hard_max is not None and not (0 <= args.channel <= hard_max):
            sys.exit(f'raw-set target {args.channel} is outside 0..{hard_max} (the widest '
                     f'address space in profile constraints). An out-of-range index BusFaulted '
                     f'a sibling device -- see hazards.channel_index_out_of_range. Use --force.')

    known_ids = {proto._as_int(p['id']) for p in profile['params'].values() if p.get('id') is not None}
    if args.param_id not in known_ids:
        print(f'HAZARD NOTE: param_id {hex(args.param_id)} is not a confirmed param in this '
              f'profile. On a sibling device, unmapped input faulted the firmware and silence '
              f'from the device does NOT mean the command took effect (see profile hazards / '
              f'frame.error_response). Capture the result and confirm before trusting it.')
        sys.stdout.flush()

    transport = get_transport(profile)
    pkt = proto.build_raw_command(profile, args.param_id, args.channel, args.value)
    print(f'sending: param_id={hex(args.param_id)} channel={args.channel} value={args.value}')
    send_and_wait(transport, pkt)
    data = read_state(transport, profile, args.timeout)
    if data:
        print('(state report received -- diff it against a pre-command capture '
              'with tools/capture_diff.py to see what byte(s) this param actually touched)')


def cmd_set_brightness(args, profile):
    """Set the device's front-panel screen brightness (SET_GLOBAL / param
    screen_brightness). Readback is a plain byte in the state report."""
    pdef = profile['params'].get('screen_brightness')
    if not pdef:
        sys.exit('this profile has no params.screen_brightness')
    lo, hi = pdef.get('range', [0, 100])
    if not args.force and not (lo <= args.value <= hi):
        sys.exit(f'brightness {args.value} outside {lo}..{hi}. Use --force to override.')
    transport = get_transport(profile)
    pkt = proto.build_global_command(profile, 'screen_brightness', args.value)
    print(f'setting screen brightness -> {args.value}  (sent: {pkt[16:18].hex()})')
    send_and_wait(transport, pkt)
    time.sleep(0.1)
    data = read_state(transport, profile, args.timeout)
    if not data:
        print('sent command, but no immediate readback was available')
        return
    try:
        val = proto.parse_state_scalar(profile, data, 'screen_brightness_byte_offset')
        print(f'readback: brightness = {val}' + ('' if val == args.value else '  (!= commanded)'))
    except ValueError as e:
        print(f'readback unavailable: {e}')


def _sample_rate_table(profile):
    """{index: hz} from params.sample_rate.values (keys may be str)."""
    vals = profile['params'].get('sample_rate', {}).get('values', {})
    return {int(k): int(v) for k, v in vals.items()}


def _parse_sample_rate(token, table):
    """'48000' / '48k' / '44.1k' / '44100' -> index. Raises SystemExit."""
    t = str(token).strip().lower().replace(' ', '')
    hz = None
    m = re.match(r'^([0-9]+(?:\.[0-9]+)?)k$', t)
    if m:
        hz = round(float(m.group(1)) * 1000)
    elif t.isdigit():
        hz = int(t)
    if hz is None:
        opts = ' / '.join(f'{v // 1000 if v % 1000 == 0 else v / 1000:g}k' for v in sorted(table.values()))
        sys.exit(f"can't parse sample rate '{token}' -- one of: {opts}")
    for idx, v in table.items():
        if v == hz:
            return idx
    sys.exit(f'{hz} Hz is not a supported rate -- one of: '
             + ', '.join(str(v) for v in sorted(table.values())))


def cmd_sample_rate(args, profile):
    """Show the device's current sample rate (state_report offset 18)."""
    table = _sample_rate_table(profile)
    transport = get_transport(profile)
    data = read_state(transport, profile, args.timeout)
    if not data:
        sys.exit('No state report captured. Try again, or run with sudo.')
    try:
        idx = proto.parse_state_scalar(profile, data, 'sample_rate_byte_offset')
    except ValueError as e:
        sys.exit(str(e))
    hz = table.get(idx)
    print(f'sample rate: {hz} Hz' if hz else f'sample rate: index {idx} (not in the profile table)')
    live_hz = proto.state_clock_rate_hz(profile, data)
    if live_hz is not None:
        note = '' if (hz is None or live_hz == hz) else '  (!= the index -- external clock / re-locking?)'
        print(f'clock rate:  {live_hz} Hz  (measured, 0x73){note}')


def cmd_set_sample_rate(args, profile):
    """Set the device sample rate (SET_GLOBAL / param sample_rate).

    Disruptive: the device drops audio and re-locks its clock (~1 s). If a
    DAW or the OS audio engine holds the stream open it may refuse or
    revert -- change it with nothing streaming.
    """
    table = _sample_rate_table(profile)
    idx = _parse_sample_rate(args.rate, table)
    hz = table[idx]
    transport = get_transport(profile)
    pkt = proto.build_global_command(profile, 'sample_rate', idx)
    print(f'setting sample rate -> {hz} Hz (index {idx})  (sent: {pkt[16:18].hex()})  '
          f'-- device will re-lock its clock, ~1 s')
    send_and_wait(transport, pkt, delay=1.2)
    data = read_state(transport, profile, args.timeout)
    if not data:
        print('sent command, but no immediate readback was available (re-run `sample-rate`)')
        return
    try:
        got = proto.parse_state_scalar(profile, data, 'sample_rate_byte_offset')
        gh = table.get(got, f'index {got}')
        print(f'readback: {gh}{" Hz" if isinstance(gh, int) else ""}'
              + ('' if got == idx else '  (!= commanded -- give it a moment and re-check with `sample-rate`)'))
    except ValueError as e:
        print(f'readback unavailable: {e}')


# ---- subcommands: clock source (0x12/0x04) + pan law (0x12/0x24) ----
#
# Both are SET_GLOBAL enums decoded 2026-09-03. clock_source reads back in
# the 0x73 state report (offset 19); pan_law has no known readback.

def _enum_values(profile, param):
    v = profile['params'].get(param, {}).get('values', {})
    return {int(k): s for k, s in v.items()}


def cmd_clock_source(args, profile):
    """Show, or with `--set N`, set the device clock source (SET_GLOBAL 0x04)."""
    vals = _enum_values(profile, 'clock_source')
    if not vals:
        sys.exit('this profile has no params.clock_source')
    transport = get_transport(profile)
    if args.set is None:
        data = read_state(transport, profile, args.timeout)
        if not data:
            sys.exit('no state report captured')
        cur = proto.parse_state_scalar(profile, data, 'clock_source_byte_offset')
        print(f'clock source: {cur} = {vals.get(cur, "?")}')
        print('options: ' + ', '.join(f'{k}={s.split(" (")[0]}' for k, s in sorted(vals.items())))
        return
    if args.set not in vals and not args.force:
        sys.exit(f'{args.set} is not a known clock source (0..{max(vals)}). --force to send anyway.')
    pkt = proto.build_global_command(profile, 'clock_source', args.set)
    print(f'clock source -> {args.set} = {vals.get(args.set, "?")}  (sent {pkt[16:18].hex()})')
    print('  DISRUPTIVE: if that source is not present/locked the device clock will unlock.')
    send_and_wait(transport, pkt, delay=1.2)
    data = read_state(transport, profile, args.timeout)
    if data:
        got = proto.parse_state_scalar(profile, data, 'clock_source_byte_offset')
        print(f'readback: {got} = {vals.get(got, "?")}'
              + ('' if got == args.set else '  (!= commanded -- give it a moment)'))


def cmd_pan_law(args, profile):
    """Show the cached pan-law setting, or with `--set N` change it
    (SET_GLOBAL 0x24). The device has no known pan-law readback, so a bare
    `pan-law` reports only what this CLI last sent."""
    vals = _enum_values(profile, 'pan_law')
    if not vals:
        sys.exit('this profile has no params.pan_law')
    path = _link_state_path(profile, 'pan_law')
    if args.set is None:
        cached = None
        if path and os.path.exists(path):
            try:
                cached = json.load(open(path)).get('value')
            except (OSError, ValueError):
                pass
        print(f'pan law: {cached} = {vals.get(cached, "unknown -- no device readback; set it once to seed")}'
              if cached is not None else
              'pan law: unknown (no device readback). Options: '
              + ', '.join(f'{k}={s}' for k, s in sorted(vals.items())))
        return
    if args.set not in vals and not args.force:
        sys.exit(f'{args.set} is not a known pan law (0..{max(vals)} = {vals}). --force to send anyway.')
    transport = get_transport(profile)
    pkt = proto.build_global_command(profile, 'pan_law', args.set)
    print(f'pan law -> {args.set} = {vals.get(args.set, "?")}  (sent {pkt[16:18].hex()}, no readback to verify)')
    send_and_wait(transport, pkt, delay=0.3)
    if path:
        try:
            json.dump({'value': args.set, 'source': 'cli-issued, not a device readback'}, open(path, 'w'))
        except OSError:
            pass


# ---- subcommand: AuraVerb (opcode 0x1d) ----
#
# AuraVerb is the device-BUNDLED Synergy Core reverb on the Mix 1 window
# (no per-plugin activation, so in scope). All 8 DSP controls + on/off are
# decoded (frame.auraverb_command). There IS a device readback -- frame.readback
# category 0x0a, decoded 2026-09-03 -- so this command now READS the live state
# from the device (all 4 mixes) and does a read-modify-write for changes, like
# `mix-set`. The local cache (kind 'auraverb') is kept only as an offline
# fallback for when the device is unreachable.

def _auraverb_state_path(profile):
    return _link_state_path(profile, 'auraverb')


def _load_auraverb_state(profile):
    """Return (params_dict_or_None, enabled_or_None) from THIS CLI's cache."""
    path = _auraverb_state_path(profile)
    if not path or not os.path.exists(path):
        return None, None
    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return None, None
    p = raw.get('params')
    if not isinstance(p, dict):
        p = None
    return p, raw.get('enabled')


def _save_auraverb_state(profile, params, enabled):
    path = _auraverb_state_path(profile)
    if not path:
        return
    try:
        with open(path, 'w') as f:
            json.dump({'params': params, 'enabled': bool(enabled),
                       'source': 'cli-issued AuraVerb commands only, not a device readback'}, f)
    except OSError:
        pass


# CLI flag name  <->  profile param key
_AURAVERB_FLAGS = {
    'color': 'color',
    'pre_delay': 'pre_delay',
    'early_reflection_gain': 'early_reflection_gain',
    'late_reflection_delay': 'late_reflection_delay',
    'richness': 'richness',
    'reverb_time': 'reverb_time',
    'room_size': 'room_size',
    'reverb_level': 'reverb_level',
}


def _read_auraverb_live(profile, transport, timeout=1.0):
    """Live-read AuraVerb for all four mixes via frame.readback cat 0x0a.
    Returns proto.parse_auraverb_record()'s list, or None if unreachable."""
    cat = proto.AURAVERB_READBACK_CATEGORY
    try:
        req = proto.build_readback_query(profile, cat, 0)
    except (KeyError, proto.ConstraintError):
        return None
    data = transport.query(
        req, lambda d: proto.is_readback_response(profile, d, cat, 0), timeout=timeout)
    if data is None:
        return None
    try:
        return proto.parse_auraverb_record(profile, proto.readback_body(profile, data))
    except ValueError:
        return None


def cmd_auraverb(args, profile):
    """Show or set the AuraVerb reverb (Mix 1). Reads live device state via
    frame.readback cat 0x0a; changes are a read-modify-write and verified.

      auraverb                         show live AuraVerb state (all 4 mixes)
      auraverb --on                    enable (keeps current params)
      auraverb --off                   disable
      auraverb --reverb-time 55 --color 40 --room-size 70
      auraverb --off --defaults        reset params to the power-on defaults
    """
    try:
        defaults = proto.auraverb_defaults(profile)
    except KeyError as e:
        sys.exit(str(e))

    overrides = {k: getattr(args, flag) for flag, k in _AURAVERB_FLAGS.items()
                 if getattr(args, flag) is not None}
    want_set = bool(overrides) or args.on or args.off or args.defaults

    transport = get_transport(profile)
    live = _read_auraverb_live(profile, transport)
    cached_params, cached_enabled = _load_auraverb_state(profile)

    if not want_set:
        if live:
            print('AuraVerb -- live device readback (frame.readback cat 0x0a):')
            for m, mx in enumerate(live):
                en = {True: 'ON', False: 'off', None: '?'}[mx['enabled']]
                if m == 0:
                    print(f'  Mix 1: {en}')
                    for flag, k in _AURAVERB_FLAGS.items():
                        print(f'    {flag.replace("_", "-"):<24} {mx["params"].get(k)}')
                else:
                    vals = ' '.join(f'{mx["params"].get(k)}' for k in _AURAVERB_FLAGS.values())
                    print(f'  Mix {m + 1}: {en:<3}  [{vals}]')
            return
        print('AuraVerb (Mix 1) -- device unreachable, showing CLI cache (may be stale):')
        base = cached_params or defaults
        en = {True: 'on', False: 'off', None: 'unknown'}[cached_enabled]
        print(f'  enabled: {en}')
        for flag, k in _AURAVERB_FLAGS.items():
            print(f'  {flag.replace("_", "-"):<24} {base.get(k, defaults.get(k))}')
        return

    # base param block: live Mix 1 > CLI cache > power-on defaults
    params = dict(defaults)
    if not args.defaults:
        if live:
            params.update(live[0]['params'])
        elif cached_params:
            params.update({k: v for k, v in cached_params.items() if k in params})
    params.update(overrides)

    lo, hi = profile['frame']['auraverb_command'].get('param_range', [0, 100])
    for k, v in params.items():
        if not args.force and not (lo <= int(v) <= hi):
            sys.exit(f'AuraVerb {k.replace("_", "-")} = {v} outside {lo}..{hi}. Use --force.')

    if args.on and args.off:
        sys.exit('pass only one of --on / --off')
    if args.on:
        enabled = True
    elif args.off:
        enabled = False
    elif live and live[0]['enabled'] is not None:
        enabled = live[0]['enabled']
    elif cached_enabled is not None:
        enabled = bool(cached_enabled)
    else:
        sys.exit("AuraVerb on/off is unknown (no device read, nothing cached) -- the frame "
                 "always carries it, so pass --on or --off with your change this first time.")

    try:
        pkt = proto.build_auraverb_command(profile, params, enabled)
    except (ValueError, KeyError) as e:
        sys.exit(str(e))
    print(f'AuraVerb (Mix 1) -> {"ON" if enabled else "off"}')
    for flag, k in _AURAVERB_FLAGS.items():
        tag = '  <-- changed' if k in overrides else ''
        print(f'  {flag.replace("_", "-"):<24} {params[k]}{tag}')
    send_and_wait(transport, pkt, delay=0.3)
    _save_auraverb_state(profile, params, enabled)

    after = _read_auraverb_live(profile, transport)
    if after:
        got = after[0]
        ok = got['enabled'] == enabled and all(
            got['params'].get(k) == params[k] for k in _AURAVERB_FLAGS.values())
        if ok:
            print('verified: device readback matches')
        else:
            print('WARNING: device readback differs from what was sent:')
            print(f'  enabled={got["enabled"]}  params={got["params"]}')
    else:
        print(f'sent: {pkt[16:29].hex()}  (no readback this time -- re-run `auraverb`)')


_ANSI_COLOR = {'red': '\x1b[31m', 'orange': '\x1b[33m', 'yellow': '\x1b[93m', 'green': '\x1b[32m'}
_ANSI_RESET = '\x1b[0m'
_ANSI_BOLD = '\x1b[1m'


def _meter_bar(raw_value, profile, width=8):
    """Renders one channel's raw byte as a bar. Scale is the 'inverted
    0x60(96)=quiet .. 0x00=loud' one from the profile -- offset formula
    confirmed for all 12 channels; the dB calibration (db_curve) is from a
    channel-0-only sweep, applied to every channel for lack of a per-channel
    one (see meter_report.db_curve_notes).

    If the profile has a filled-in meter_report.db_curve, also colors the bar
    and appends a CLIP marker using meter_report.led_scale (see
    protocol.raw_to_db / protocol.meter_led). Until db_curve is filled in from
    a real sweep, raw_to_db() returns None and this silently falls back to a
    plain, uncolored bar -- same behavior as before this was added.
    """
    level = max(0, min(96, 96 - raw_value))  # 0 = quiet, 96 = loud/near-clip
    filled = round(level / 96 * width)
    bar = '#' * filled + '.' * (width - filled)

    db = proto.raw_to_db(profile, raw_value)
    led = proto.meter_led(profile, db)
    if led is None:
        return bar

    color = _ANSI_COLOR.get(led['color'], '')
    clip_marker = f' {_ANSI_BOLD}{_ANSI_COLOR["red"]}CLIP{_ANSI_RESET}' if led['clip'] else ''
    return f'{color}{bar}{_ANSI_RESET}{clip_marker}'


def cmd_meter(args, profile):
    """EXPERIMENTAL: live per-channel meter view. Clears the screen and redraws
    each frame in place (bulletproof across terminals/multiplexers, unlike
    \\r-based line editing which some setups mishandle). Keeps the HID node
    open and just throttles how often it repaints, instead of re-invoking like
    `watch` would.

    Reads whichever frame actually carries the per-channel input meters for
    this profile -- see protocol.channel_meter_source(). On the Orion Studio
    III that is the 0x73 state report at offset 157+channel; its separate 0x75
    meter frame turned out to be only a monitor sum (see PROTOCOL.md sec 9).
    The dB calibration (db_curve) is from a channel-0-only sweep applied to
    every channel, so treat the numbers/colors on channels 1-11 as a
    reasonable estimate, not an independently verified reading. Run with
    --duration 0 to stream until Ctrl-C."""
    try:
        magic, meter_base = proto.channel_meter_source(profile)
    except ValueError:
        sys.exit('This profile has no channel_meter_base_offset (state_report or '
                 'meter_report) -- meter reading not available yet.')

    n_channels = _resolve_channel_count(args, profile, 'input', fallback=12)
    transport = get_transport(profile)
    end = time.time() + args.duration if args.duration else None
    min_interval = 1.0 / args.refresh_hz if args.refresh_hz > 0 else 0
    last_draw = 0.0
    mr = profile['frame'].get('meter_report', {})
    header = '' if mr.get('db_curve') else (
        'no db_curve calibration in profile, showing raw/uncolored bars '
        '(fill in meter_report.db_curve from a real sweep to get dB + color)')
    try:
        while True:
            data = transport.read_one(magic, args.timeout)
            if not data:
                sys.stdout.write('\x1b[2J\x1b[H')
                print('no meter frame received')
                break
            now = time.time()
            if now - last_draw >= min_interval:
                last_draw = now
                levels = []
                for ch in range(n_channels):
                    try:
                        levels.append(proto.parse_channel_meter(profile, data, ch, meter_base))
                    except ValueError:
                        break
                line = '  '.join(f'ch{ch}[{_meter_bar(v, profile)}]' for ch, v in enumerate(levels))
                sys.stdout.write('\x1b[2J\x1b[H')  # clear screen, cursor to top-left
                if header:
                    sys.stdout.write(header + '\n\n')
                sys.stdout.write(line + '\n')
                sys.stdout.flush()
            if end and time.time() >= end:
                break
    except KeyboardInterrupt:
        pass
    finally:
        print()


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROFILE_ALIASES = {
    'orion': 'orion_studio_sc', 'orion_studio_sc': 'orion_studio_sc',
    'orion_studio_3': 'orion_studio_sc',  # legacy name, kept as a silent alias
    'zen_go': 'zen_go_sc', 'zen_go_sc': 'zen_go_sc',
    'discrete_8_pro': 'discrete_8_pro_sc', 'discrete8pro': 'discrete_8_pro_sc',
    'discrete_8_pro_sc': 'discrete_8_pro_sc',
    'discrete_4': 'discrete_4_sc', 'discrete_4_sc': 'discrete_4_sc',
    'discrete_4_pro': 'discrete_4_pro_sc', 'discrete_4_pro_sc': 'discrete_4_pro_sc',
    # legacy *_synergy_core names, kept as silent aliases
    'discrete_8_pro_synergy_core': 'discrete_8_pro_sc',
    'discrete_4_synergy_core': 'discrete_4_sc',
    'discrete_4_pro_synergy_core': 'discrete_4_pro_sc',
}


def _resolve_profile_path(arg):
    """Accept a path ('profiles/orion_studio_sc.json', './x.json'), a bare
    filename ('orion_studio_sc.json'), or a short name/alias ('orion')."""
    if arg and (os.path.sep in arg or arg.endswith('.json')):
        for cand in (arg, os.path.join(_REPO_ROOT, arg),
                     os.path.join(_REPO_ROOT, 'profiles', os.path.basename(arg))):
            if os.path.exists(cand):
                return cand
        return arg  # let load_profile raise a clear error
    name = _PROFILE_ALIASES.get((arg or '').lower().replace('-', '_'), arg)
    cand = os.path.join(_REPO_ROOT, 'profiles', f'{name}.json')
    if os.path.exists(cand):
        return cand
    sys.exit(f"profile '{arg}' not found. Try a path (profiles/orion_studio_sc.json) "
             f"or a short name: {', '.join(sorted(set(_PROFILE_ALIASES.values())))}")


def main():
    p = argparse.ArgumentParser(description='Generic Antelope HID device control')
    p.add_argument('-p', '--profile', default=os.environ.get('ANTELOPE_PROFILE', 'orion'),
                   help="device profile: a path, a bare .json filename, or a short name "
                        "(orion / zen_go / discrete_8_pro). Default: $ANTELOPE_PROFILE or 'orion'.")
    sub = p.add_subparsers(dest='cmd', required=True)

    sp = sub.add_parser('status', help='show all physical input channels')
    sp.add_argument('--channels', type=int, default=None,
                    help='how many input channels to show (default: from the profile)')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser('set-mode')
    sp.add_argument('channel', type=int)
    sp.add_argument('mode')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_set_mode)

    sp = sub.add_parser('set-gain')
    sp.add_argument('channel', type=int)
    sp.add_argument('dB', type=int)
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_set_gain)

    sp = sub.add_parser('set-phantom')
    sp.add_argument('channel', type=int)
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_set_phantom)

    sp = sub.add_parser('set-invert')
    sp.add_argument('channel', type=int)
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true',
                     help='bypass profile constraints (channel bounds etc) -- see profile hazards')
    sp.set_defaults(func=cmd_set_invert)

    sp = sub.add_parser('set-link',
                         help='engage/disengage the stereo link for the pair channel belongs to '
                              '(e.g. channel 2 or 3 both mean the ch3+ch4 pair)')
    sp.add_argument('channel', type=int, help='any channel index (0-11) in the pair')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--force', action='store_true')
    sp.add_argument('--timeout', type=float, default=3.0,
                     help='seconds to wait for each state-report read used in the before/after '
                          'sync check (see cmd_set_link)')
    sp.set_defaults(func=cmd_set_link)

    sp = sub.add_parser('mark-link',
                         help='update this CLI\'s local link-state cache WITHOUT sending a device '
                              'command -- for when a pair was linked via the official Launcher '
                              'instead of this CLI')
    sp.add_argument('channel', type=int, help='any channel index (0-11) in the pair')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_mark_link)

    sp = sub.add_parser('adat-status', help='show the ADAT input channel gains (+ CLI-tracked link markers)')
    sp.add_argument('--channels', type=int, default=None,
                    help='how many ADAT channels to show (default: from the profile)')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_adat_status)

    sp = sub.add_parser('set-adat-gain', help='set an ADAT input channel gain in dB (ADAT ch 0-15; mirrors to the linked partner)')
    sp.add_argument('channel', type=int, help='ADAT channel index 0-15')
    sp.add_argument('dB', type=int)
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_set_adat_gain)

    sp = sub.add_parser('set-adat-link',
                         help='engage/disengage the stereo link for the ADAT pair channel belongs to '
                              '(pair_index = ch//2 over ADAT ch 0-15). NOTE: for pairs 0-5 this frame '
                              'is identical to the physical link and may also toggle physical ch(N*2+1)&(N*2+2)')
    sp.add_argument('channel', type=int, help='any ADAT channel index (0-15) in the pair')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--force', action='store_true')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_set_adat_link)

    sp = sub.add_parser('mark-adat-link',
                         help='update this CLI\'s local ADAT link-state cache WITHOUT sending a device command')
    sp.add_argument('channel', type=int, help='any ADAT channel index (0-15) in the pair')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_mark_adat_link)

    sp = sub.add_parser('spdif-status', help='show the 2 S/PDIF input channel gains (L/R) + link marker')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_spdif_status)

    sp = sub.add_parser('set-spdif-gain', help='set an S/PDIF input channel gain in dB (0=L, 1=R; mirrors to the linked partner)')
    sp.add_argument('channel', type=int, help='S/PDIF channel: 0 = L, 1 = R')
    sp.add_argument('dB', type=int)
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_set_spdif_gain)

    sp = sub.add_parser('set-spdif-link',
                         help='engage/disengage the S/PDIF L/R stereo link (distinct frame from the '
                              'physical/ADAT link -- no cross-space ambiguity)')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--force', action='store_true')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_set_spdif_link)

    sp = sub.add_parser('mark-spdif-link',
                         help='update this CLI\'s local S/PDIF link-state cache WITHOUT sending a device command')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_mark_spdif_link)

    sp = sub.add_parser('route',
                         help='route sources into lineout/hp1/hp2/mona/monb/reamp '
                              '(whole destination sent every time; each write is verified against a '
                              'live readback -- see also matrix-status / readback)')
    sp.add_argument('destination', help='lineout | hp1 | hp2 | mona | monb | reamp')
    sp.add_argument('selector',
                    help='output channel (1-based; L/R = 1/2 for the stereo dests), '
                         'or "all" (then give one source per channel), or "mute" (mute all)')
    sp.add_argument('source', nargs='*',
                    help='preamp3 | emumic7 (emumic numbered 5-12 by preamp) | compplay1 | '
                         'adat5 | afx7 | surround2 | spdifL | mix2R | osc1 | mute | keep  '
                         '(one for a channel selector; N for "all"; in "all" a range like '
                         'compplay1..16 expands to N sources)')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_route)

    sp = sub.add_parser('matrix-status',
                         help='live-read the routing matrix from the device (frame.readback cat 0x03); '
                              'falls back to the CLI cache if unreachable')
    sp.add_argument('--timeout', type=float, default=2.0)
    sp.set_defaults(func=cmd_matrix_status)

    sp = sub.add_parser('identity',
                         help="ask the device its name / hw rev / firmware "
                              "(readback cat 0x01 + 0x00); serial on request only")
    sp.add_argument('--serial', action='store_true',
                    help='also print the serial number. It is read live from the '
                         'device and never stored in this repo -- avoid pasting it '
                         'into logs, issues or captures.')
    sp.add_argument('--timeout', type=float, default=2.0)
    sp.set_defaults(func=cmd_identity)

    sp = sub.add_parser('mix-status',
                         help='live-read a virtual mix from the device '
                              '(frame.readback cat 0x04); no arg = all four mixes')
    sp.add_argument('mix', nargs='?', type=lambda x: int(x, 0), default=None,
                    help='mix number 1-4 (default: all)')
    sp.add_argument('--all-slots', action='store_true',
                    help=argparse.SUPPRESS)   # kept for compat; master is always shown now
    sp.add_argument('--timeout', type=float, default=2.0)
    sp.set_defaults(func=cmd_mix_status)

    sp = sub.add_parser('mix-set',
                         help='change one virtual-mixer strip '
                              '(reads it back first, so unnamed fields are kept)')
    sp.add_argument('mix', type=lambda x: int(x, 0), help='mix number 1-4')
    sp.add_argument('channel', help="strip number 1-32, or 'master' for the mix master")
    sp.add_argument('--fader', type=int, default=None,
                    help='level in dB, 0 (unity) to -90. The sign is optional -- '
                         'the mixer only attenuates, so 24 and -24 both mean -24 dB.')
    sp.add_argument('--pan', type=int, default=None,
                    help='-30 (full left) .. 0 (centre) .. +30 (full right)')
    sp.add_argument('--send', type=int, default=None,
                    help='send level 0-96 (96 = 0 dB). Not present on every device.')
    sp.add_argument('--mute', choices=['on', 'off'], default=None)
    sp.add_argument('--solo', choices=['on', 'off'], default=None)
    sp.add_argument('--timeout', type=float, default=2.0)
    sp.set_defaults(func=cmd_mix_set)

    sp = sub.add_parser('readback',
                         help='raw frame.readback query: `readback <category> [index]` '
                              '(no args lists the known categories)')
    sp.add_argument('category', nargs='?', default=None,
                    help='category id, e.g. 0x03 (routing), 0x04 (mixer), 0x0a (auraverb)')
    sp.add_argument('index', nargs='?', type=lambda x: int(x, 0), default=0)
    sp.add_argument('--force', action='store_true',
                    help='skip the index bounds check. DANGEROUS: an index past a '
                         'category\'s record count can crash the device firmware '
                         '(BusFault -- needs a power cycle). See frame.readback.hazard.')
    sp.add_argument('--timeout', type=float, default=2.0)
    sp.set_defaults(func=cmd_readback)

    sp = sub.add_parser('bus-status', help='show monitor A/B and headphone 1/2 levels+flags')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_bus_status)

    sp = sub.add_parser('set-bus-level', help='set an output bus volume (0-96)')
    sp.add_argument('bus', help='bus id or name, e.g. 0, monitor_a, mona')
    sp.add_argument('level', type=int)
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true')
    sp.set_defaults(func=cmd_set_bus_level)

    sp = sub.add_parser('set-bus-dim')
    sp.add_argument('bus', help='bus id or name, e.g. 0, monitor_a, mona')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true', help='bypass profile constraints (bus id bounds)')
    sp.set_defaults(func=cmd_set_bus_dim)

    sp = sub.add_parser('set-bus-mute')
    sp.add_argument('bus', help='bus id or name, e.g. 0, monitor_a, mona')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true', help='bypass profile constraints (bus id bounds)')
    sp.set_defaults(func=cmd_set_bus_mute)

    sp = sub.add_parser('set-bus-mono')
    sp.add_argument('bus', help='bus id or name, e.g. 0, monitor_a, mona')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true', help='bypass profile constraints (bus id bounds)')
    sp.set_defaults(func=cmd_set_bus_mono)

    sp = sub.add_parser('meter', help='live per-channel meter view (dB calibration from ch0 sweep, applied to all channels)')
    sp.add_argument('--channels', type=int, default=None,
                    help='how many channels to meter (default: from the profile)')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--duration', type=float, default=0.0, help='seconds to stream, 0 = until Ctrl-C (default)')
    sp.add_argument('--refresh-hz', type=float, default=10.0, help='max screen repaints per second')
    sp.set_defaults(func=cmd_meter)

    sp = sub.add_parser('raw-set', help='Send an arbitrary param_id -- for exploring new params')
    sp.add_argument('channel', type=int)
    sp.add_argument('param_id', type=lambda x: int(x, 0))
    sp.add_argument('value', type=lambda x: int(x, 0))
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true',
                     help='bypass the profile-constraints target-bounds check (see profile hazards)')
    sp.set_defaults(func=cmd_raw_set)

    sp = sub.add_parser('set-brightness',
                         help='set the device front-panel screen brightness (0-100)')
    sp.add_argument('value', type=int, help='0 = darkest, 100 = brightest')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true', help='allow a value outside 0-100')
    sp.set_defaults(func=cmd_set_brightness)

    sp = sub.add_parser('sample-rate', help='show the device sample rate')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_sample_rate)

    sp = sub.add_parser('set-sample-rate',
                         help='set the device sample rate (disruptive -- re-locks the clock, ~1 s)')
    sp.add_argument('rate', help='48000 | 48k | 44.1k | 88.2k | 96k | 176.4k | 192k | 32k')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_set_sample_rate)

    sp = sub.add_parser('clock-source',
                         help='show the clock source (readback 0x73 @19); --set N to change it (disruptive)')
    sp.add_argument('--set', type=int, metavar='N', help='0=Oven 1=WordClock 2=ADAT 3=ADATx2 4=ADATx4 5=SPDIF 6=USB')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true', help='send a value outside the known enum')
    sp.set_defaults(func=cmd_clock_source)

    sp = sub.add_parser('pan-law',
                         help='show/set stereo pan law (SET_GLOBAL 0x24); no device readback -- CLI-cached')
    sp.add_argument('--set', type=int, metavar='N', help='0=-6dB 1=-3dB 2=-4.5dB 3=0dB')
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true', help='send a value outside the known enum')
    sp.set_defaults(func=cmd_pan_law)

    sp = sub.add_parser('auraverb',
                         help='show/set the AuraVerb reverb (Mix 1); live device read via '
                              'frame.readback cat 0x0a, changes are read-modify-write + verified')
    sp.add_argument('--on', action='store_true', help='enable AuraVerb')
    sp.add_argument('--off', action='store_true', help='disable AuraVerb')
    sp.add_argument('--defaults', action='store_true',
                    help='reset all 8 params to the device power-on defaults')
    for _flag in _AURAVERB_FLAGS:
        sp.add_argument('--' + _flag.replace('_', '-'), dest=_flag, type=int, metavar='0-100',
                        help='0-100' + (' (maps to 0-32 ms)' if _flag == 'pre_delay' else ''))
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--force', action='store_true', help='allow a value outside 0-100')
    sp.set_defaults(func=cmd_auraverb)

    args = p.parse_args()
    args.profile = _resolve_profile_path(args.profile)
    profile = proto.load_profile(args.profile)
    args.func(args, profile)


if __name__ == '__main__':
    main()
