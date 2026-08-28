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
import sys
import time

try:
    from . import protocol as proto
    from .transport import HidTransport, find_hidraw
except ImportError:
    # Allows running this file directly (python3 antelope/cli.py ...)
    # instead of only via `python3 -m antelope.cli ...`.
    import os
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

def cmd_status(args, profile):
    transport = get_transport(profile)
    data = read_state(transport, profile, args.timeout)
    if not data:
        sys.exit('No state report captured. Try again, or run with sudo if permissions are an issue.')
    print(f"{'ch':>2}  {'mode':<7} {'gain':>5}  {'48V':<3} {'phase':<5}")
    for ch in range(args.channels):
        try:
            s = proto.parse_state(profile, data, ch)
        except ValueError:
            break
        mode = proto.mode_name(profile, s.get('input_mode', -1))
        print(f"{ch:>2}  {mode:<7} {s['gain']:>5}  "
              f"{'on' if s.get('phantom') else 'off':<3} "
              f"{'on' if s.get('phase_invert') else 'off':<5}")
    confirmed = profile['channels'].get('confirmed_indices', [])
    if confirmed and args.channels > max(confirmed) + 1:
        print(f'note: only channels {confirmed} are explicitly verified for this device.')
    print("note: channel-link state has no known readback yet -- see 'set-link' and the "
          "profile's params.channel_link.notes -- so it isn't shown here.")


def cmd_set_mode(args, profile):
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


def cmd_set_gain(args, profile):
    transport = get_transport(profile)
    s = require_state(transport, profile, args.channel, args.timeout)
    mode = proto.mode_name(profile, s.get('input_mode', -1))
    lo, hi = proto.gain_range(profile, mode)
    if not args.force and not (lo <= args.dB <= hi):
        sys.exit(f'Gain {args.dB} outside observed range {lo}..{hi} for mode {mode}. Use --force to override.')
    warn_unverified_channel(profile, args.channel)
    pkt = proto.build_command(profile, 'gain', args.channel, args.dB)
    send_and_wait(transport, pkt)
    verify(transport, profile, args.channel, args.timeout)


def cmd_set_phantom(args, profile):
    transport = get_transport(profile)
    s = require_state(transport, profile, args.channel, args.timeout)
    mic_val = proto.mode_value(profile, 'mic')
    on = 1 if args.state == 'on' else 0
    if on and s.get('input_mode') != mic_val and not args.force:
        sys.exit('Refusing to turn on 48V outside mic mode. Use --force if you are sure.')
    warn_unverified_channel(profile, args.channel)
    pkt = proto.build_command(profile, 'phantom', args.channel, on)
    send_and_wait(transport, pkt)
    verify(transport, profile, args.channel, args.timeout)


def cmd_set_invert(args, profile):
    transport = get_transport(profile)
    require_state(transport, profile, args.channel, args.timeout)
    on = 1 if args.state == 'on' else 0
    warn_unverified_channel(profile, args.channel)
    pkt = proto.build_command(profile, 'phase_invert', args.channel, on)
    send_and_wait(transport, pkt)
    verify(transport, profile, args.channel, args.timeout)


def cmd_set_link(args, profile):
    """Engage/disengage the link for the pair that `channel` belongs to
    (pair_index = channel // 2, see channels.link_pairs in the profile).
    Uses build_link_command(), NOT build_command() -- channel_link is a
    different frame shape (frame.link_command), not a SET_PARAM param."""
    pair = proto.pair_index_for_channel(args.channel)
    max_pair = profile['channels'].get('link_pairs', {}).get('count', 0) - 1
    if not (0 <= pair <= max_pair) and not args.force:
        sys.exit(f'channel {args.channel} maps to link pair {pair}, outside the confirmed '
                 f'0..{max_pair} range. Use --force if you believe this profile is wrong.')

    partner = args.channel + 1 if args.channel % 2 == 0 else args.channel - 1
    print(f'note: this links channels {min(args.channel, partner)} and {max(args.channel, partner)} '
          f'(pair {pair}). Engaging a link has been observed to push the higher-numbered '
          f'channel\'s mode/gain to match the lower one\'s -- see profile params.channel_link.side_effects.')

    transport = get_transport(profile)
    on = args.state == 'on'
    pkt = proto.build_link_command(profile, pair, on)
    send_and_wait(transport, pkt)
    print('sent. note: there is no known way to read link status back from the device yet '
          '(see params.channel_link.notes), so this cannot be verified automatically -- '
          'check the Launcher UI or listen for the expected mode/gain sync on the other channel.')


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
    sp.set_defaults(func=cmd_set_link)

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
