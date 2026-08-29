#!/usr/bin/env python3
"""
Generic Antelope HID control CLI.

Per-input-channel controls (physical inputs 1-12, addressed 0-11):

    antelope-ctl --profile profiles/orion_studio_3.json status
    antelope-ctl --profile profiles/orion_studio_3.json set-mode 0 mic
    antelope-ctl --profile profiles/orion_studio_3.json set-gain 0 12
    antelope-ctl --profile profiles/orion_studio_3.json set-phantom 0 on
    antelope-ctl --profile profiles/orion_studio_3.json set-invert 0 on
    antelope-ctl --profile profiles/orion_studio_3.json set-link 0 on      # links ch1+ch2
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

    antelope-ctl --profile profiles/orion_studio_3.json adat-status
    antelope-ctl --profile profiles/orion_studio_3.json set-adat-gain 0 6
    antelope-ctl --profile profiles/orion_studio_3.json set-adat-link 0 on   # links ADAT ch1+ch2
                                                                            # (mirrors gain to the
                                                                            # partner while linked,
                                                                            # exactly like set-link;
                                                                            # for pairs 0-5 the frame
                                                                            # is identical to the
                                                                            # physical link -- see
                                                                            # set-adat-link help)

Output-bus controls (monitor A/B, headphone 1/2 -- NOT the same "channel"
numbers as inputs above; buses accept either their numeric id or a name,
see profiles/orion_studio_3.json -> "buses"):

    antelope-ctl --profile profiles/orion_studio_3.json bus-status
    antelope-ctl --profile profiles/orion_studio_3.json set-bus-level monitor_a 60
    antelope-ctl --profile profiles/orion_studio_3.json set-bus-dim mona on
    antelope-ctl --profile profiles/orion_studio_3.json set-bus-mute hp1 on
    antelope-ctl --profile profiles/orion_studio_3.json set-bus-mono hp2 off

Escape hatch for anything not yet in the profile:

    antelope-ctl --profile profiles/orion_studio_3.json raw-set 0 0x53 7   # for a param
                                                                            # not yet in
                                                                            # the profile

Adding a device: write a new profiles/<name>.json and point --profile at it.
Adding a param: once you've captured+confirmed it, add it under "params" in
the profile; the raw-set command works before that, for exploration.
"""
import argparse
import json
import os
import sys
import time

try:
    from . import protocol as proto
    from .transport import HidTransport, find_hidraw
except ImportError:
    # Allows running this file directly (python3 antelope/cli.py ...)
    # instead of only via `python3 -m antelope.cli ...`.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from antelope import protocol as proto
    from antelope.transport import HidTransport, find_hidraw


def get_transport(profile) -> HidTransport:
    dev = profile['device']
    vid = int(dev['vid'], 16) if isinstance(dev['vid'], str) else dev['vid']
    pid = int(dev['pid'], 16) if isinstance(dev['pid'], str) else dev['pid']
    path = find_hidraw(vid, pid)
    return HidTransport(path, profile['transport']['report_size'])


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


def cmd_status(args, profile):
    transport = get_transport(profile)
    data = read_state(transport, profile, args.timeout)
    if not data:
        sys.exit('No state report captured. Try again, or run with sudo if permissions are an issue.')
    link_state = _load_link_state(profile)
    print(f"{'ch':>2}  {'mode':<7} {'gain':>5}  {'48V':<3} {'phase':<5}")
    for ch in range(args.channels):
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
    if confirmed and args.channels > max(confirmed) + 1:
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
    transport = get_transport(profile)
    data = read_state(transport, profile, args.timeout)
    if not data:
        sys.exit('No state report captured. Try again, or run with sudo if permissions are an issue.')
    link_state = _load_link_state(profile, 'adat')
    print(f"{'adat':>4}  {'gain':>5}")
    for ch in range(args.channels):
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
    lo, hi = proto.adat_gain_range(profile)
    if not args.force and not (lo <= args.dB <= hi):
        sys.exit(f'ADAT gain {args.dB} outside the confirmed range {lo}..{hi}. Use --force to override.')
    count = profile.get('adat', {}).get('count', 16)
    if not args.force and not (0 <= args.channel < count):
        sys.exit(f'ADAT channel {args.channel} out of range 0..{count - 1}. Use --force to override.')

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
    during a live capture session. See tools/capture_diff.py for finding candidates."""
    transport = get_transport(profile)
    pkt = proto.build_raw_command(profile, args.param_id, args.channel, args.value)
    print(f'sending: param_id={hex(args.param_id)} channel={args.channel} value={args.value}')
    send_and_wait(transport, pkt)
    data = read_state(transport, profile, args.timeout)
    if data:
        print('(state report received -- diff it against a pre-command capture '
              'with tools/capture_diff.py to see what byte(s) this param actually touched)')


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
    `watch` would. frame.meter_report.channel_meter_base_offset is confirmed
    for all 12 channels, but the dB calibration (db_curve) is from a
    channel-0-only sweep and applied to every channel regardless -- treat
    the numbers/colors on channels 1-11 as a reasonable estimate, not an
    independently verified reading. Run with --duration 0 to stream until
    Ctrl-C."""
    mr = profile['frame'].get('meter_report', {})
    if mr.get('channel_meter_base_offset') is None:
        sys.exit('This profile has no channel_meter_base_offset -- meter reading not available yet.')

    transport = get_transport(profile)
    magic = proto.meter_report_magic(profile)
    end = time.time() + args.duration if args.duration else None
    min_interval = 1.0 / args.refresh_hz if args.refresh_hz > 0 else 0
    last_draw = 0.0
    header = 'meter offsets are UNCONFIRMED (candidate only, see profile notes)' \
        if not str(mr.get('status', '')).startswith('confirmed') else ''
    if not mr.get('db_curve'):
        header += (' -- no db_curve calibration in profile, showing raw/uncolored bars '
                   '(fill in meter_report.db_curve from a real sweep to get dB + color)')
    try:
        while True:
            data = transport.read_one(magic, args.timeout)
            if not data:
                sys.stdout.write('\x1b[2J\x1b[H')
                print('no meter report received')
                break
            now = time.time()
            if now - last_draw >= min_interval:
                last_draw = now
                levels = []
                for ch in range(args.channels):
                    try:
                        levels.append(proto.parse_meter_level(profile, data, ch))
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


def main():
    p = argparse.ArgumentParser(description='Generic Antelope HID device control')
    p.add_argument('--profile', required=True, help='Path to device profile JSON')
    sub = p.add_subparsers(dest='cmd', required=True)

    sp = sub.add_parser('status', help='show all physical input channels')
    sp.add_argument('--channels', type=int, default=12)
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

    sp = sub.add_parser('adat-status', help='show the 16 ADAT input channel gains (+ CLI-tracked link markers)')
    sp.add_argument('--channels', type=int, default=16)
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
    sp.set_defaults(func=cmd_set_bus_dim)

    sp = sub.add_parser('set-bus-mute')
    sp.add_argument('bus', help='bus id or name, e.g. 0, monitor_a, mona')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_set_bus_mute)

    sp = sub.add_parser('set-bus-mono')
    sp.add_argument('bus', help='bus id or name, e.g. 0, monitor_a, mona')
    sp.add_argument('state', choices=['on', 'off'])
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_set_bus_mono)

    sp = sub.add_parser('meter', help='live per-channel meter view (dB calibration from ch0 sweep, applied to all channels)')
    sp.add_argument('--channels', type=int, default=12)
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.add_argument('--duration', type=float, default=0.0, help='seconds to stream, 0 = until Ctrl-C (default)')
    sp.add_argument('--refresh-hz', type=float, default=10.0, help='max screen repaints per second')
    sp.set_defaults(func=cmd_meter)

    sp = sub.add_parser('raw-set', help='Send an arbitrary param_id -- for exploring new params')
    sp.add_argument('channel', type=int)
    sp.add_argument('param_id', type=lambda x: int(x, 0))
    sp.add_argument('value', type=lambda x: int(x, 0))
    sp.add_argument('--timeout', type=float, default=3.0)
    sp.set_defaults(func=cmd_raw_set)

    args = p.parse_args()
    profile = proto.load_profile(args.profile)
    args.func(args, profile)


if __name__ == '__main__':
    main()
