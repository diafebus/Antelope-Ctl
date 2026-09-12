#!/usr/bin/env python3
"""Read and experimentally round-trip one Surround speaker EQ field.

Read-only examples::

    python3 tools/surround_eq_selftest.py
    python3 tools/surround_eq_selftest.py --speaker 0

The write path is intentionally narrow. It changes one selected field in one
selected band, verifies the category-0x1a readback, and restores the complete
116-byte record even when verification fails::

    python3 tools/surround_eq_selftest.py --write --speaker 0 --band 3 --parameter gain --value -1.00 --confirm-experimental-write

The 0x87/0xea frame geometry is known from Launcher captures, but its
per-speaker candidate head (delay/level/invert) has not been dynamically
paired with the category-0x1a readback. Stop the WebUI and any other HID owner
before running this tool. Never use it as a blind sweep.
"""
import argparse
from decimal import Decimal, InvalidOperation
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from antelope import protocol as proto
from antelope.transport import HidTransport, find_hidraw


def _profile_contract(profile):
    contract = profile.get('runtime_contracts', {}).get(
        'surround_speaker_eq')
    if not contract:
        raise ValueError('profile has no surround speaker EQ runtime contract')
    return contract


def _speaker_count(profile):
    return proto._as_int(_profile_contract(profile)['record_count'])


def _record_size(profile):
    return proto._as_int(_profile_contract(profile)['record_size'])


class Device:
    def __init__(self, profile, timeout, settle):
        self.profile = profile
        self.timeout = timeout
        self.settle = settle
        dev = profile['device']
        vid = int(dev['vid'], 16) if isinstance(dev['vid'], str) else dev['vid']
        pid = int(dev['pid'], 16) if isinstance(dev['pid'], str) else dev['pid']
        self.node = find_hidraw(vid, pid)
        self.transport = HidTransport(
            self.node, proto._as_int(profile['transport']['report_size']))

    def read_speaker(self, speaker):
        cat = proto.SURROUND_SPEAKER_EQ_READBACK_CATEGORY
        request = proto.build_readback_query(self.profile, cat, speaker)
        report = self.transport.query(
            request,
            lambda data: proto.is_readback_response(
                self.profile, data, cat, speaker),
            timeout=self.timeout)
        if report is None:
            return None
        body = proto.readback_body(self.profile, report)
        record = proto.parse_surround_speaker_eq_record(self.profile, body)
        return body, record

    def write(self, packet):
        self.transport.write(packet)
        time.sleep(self.settle)


def _raw_field(parameter, band_record):
    if parameter == 'frequency':
        return int.from_bytes(band_record['raw'][0:2], 'little')
    if parameter == 'q':
        return int.from_bytes(band_record['raw'][2:4], 'little')
    if parameter == 'gain':
        return int.from_bytes(band_record['raw'][4:6], 'little', signed=True)
    if parameter == 'mode':
        return band_record['raw'][6]
    raise ValueError(f'unsupported EQ parameter {parameter!r}')


def _scaled_value(text, scale, bounds, label):
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be numeric') from exc
    if not value.is_finite():
        raise ValueError(f'{label} must be finite')
    raw = value * Decimal(scale)
    if raw != raw.to_integral_value():
        raise ValueError(f'{label} has too many decimal places')
    raw = int(raw)
    lo, hi = bounds
    if not lo <= raw <= hi:
        raise ValueError(f'{label} is outside the supported range')
    return raw


def _probe_value(contract, parameter, text):
    if parameter == 'frequency':
        try:
            value = int(text, 0)
        except (TypeError, ValueError) as exc:
            raise ValueError('frequency must be an integer in Hz') from exc
        lo, hi = (proto._as_int(v) for v in contract['frequency_range'])
        if not lo <= value <= hi:
            raise ValueError(f'frequency must be in {lo}..{hi} Hz')
        return value, 'frequency'
    if parameter == 'q':
        bounds = tuple(proto._as_int(v) for v in contract['q_raw_range'])
        return _scaled_value(text, 100, bounds, 'Q'), 'q_raw'
    if parameter == 'gain':
        bounds = tuple(proto._as_int(v) for v in contract['gain_raw_range'])
        return _scaled_value(text, 100, bounds, 'gain'), 'gain_raw'
    if parameter == 'mode':
        try:
            value = int(text, 0)
        except (TypeError, ValueError) as exc:
            raise ValueError('mode must be a byte value, such as 0x02') from exc
        if not 0 <= value <= 0xFF:
            raise ValueError('mode must be in 0..255')
        return value, 'mode'
    raise ValueError(f'unsupported EQ parameter {parameter!r}')


def _validate_record(profile, record):
    contract = _profile_contract(profile)
    expected = proto._as_int(contract['band_count'])
    bands = record.get('bands', [])
    if len(bands) != expected:
        raise ValueError(f'readback has {len(bands)} bands, expected {expected}')
    flo, fhi = (proto._as_int(v) for v in contract['frequency_range'])
    qlo, qhi = (proto._as_int(v) for v in contract['q_raw_range'])
    glo, ghi = (proto._as_int(v) for v in contract['gain_raw_range'])
    for index, band in enumerate(bands):
        raw = band['raw']
        frequency = int.from_bytes(raw[0:2], 'little')
        q_raw = int.from_bytes(raw[2:4], 'little')
        gain_raw = int.from_bytes(raw[4:6], 'little', signed=True)
        if not flo <= frequency <= fhi:
            raise ValueError(f'band {index + 1} frequency {frequency} outside range')
        if not qlo <= q_raw <= qhi:
            raise ValueError(f'band {index + 1} Q raw {q_raw} outside range')
        if not glo <= gain_raw <= ghi:
            raise ValueError(f'band {index + 1} gain raw {gain_raw} outside range')
    return bands


def _format_band(index, band):
    return (f'band {index + 1:>2}: {band["freq_hz"]:>5} Hz  '
            f'Q {band["q"]:>5.2f}  {band["gain_db"]:+.2f} dB  '
            f'mode {band["mode"]:#04x}')


def read_only(dev, profile, speaker):
    speakers = range(_speaker_count(profile)) if speaker is None else [speaker]
    failures = 0
    for index in speakers:
        result = dev.read_speaker(index)
        if result is None:
            print(f'[FAIL] speaker {index}: no category-0x1a response')
            failures += 1
            continue
        body, record = result
        try:
            bands = _validate_record(profile, record)
        except ValueError as exc:
            print(f'[FAIL] speaker {index}: {exc}')
            failures += 1
            continue
        print(f'\nspeaker {index}: {len(bands)} bands, candidate head '
              f'{record["header"].hex()}')
        for band_index, band in enumerate(bands):
            print(f'  {_format_band(band_index, band)}')
        if len(body) < _record_size(profile):
            print(f'[FAIL] speaker {index}: body is shorter than the contract')
            failures += 1
    return 1 if failures else 0


def _target_body_offset(profile, band, parameter):
    contract = _profile_contract(profile)
    write = contract.get('write_contract', {}) or {}
    offsets = {
        'frequency': ('frequency_offset', 2),
        'q': ('q_offset', 2),
        'gain': ('gain_offset', 2),
        'mode': ('mode_offset', 1),
    }
    offset_key, width = offsets[parameter]
    return (proto._as_int(write.get('band_data_offset',
                                    contract['candidate_head_size']))
            + band * proto._as_int(contract['band_stride'])
            + proto._as_int(contract[offset_key]), width)


def _masked_equal(before, after, offset, width):
    before = bytes(before)
    after = bytes(after)
    return (len(before) == len(after)
            and before[:offset] == after[:offset]
            and before[offset + width:] == after[offset + width:])


def write_probe(dev, profile, speaker, band, parameter, value_text):
    contract = _profile_contract(profile)
    result = dev.read_speaker(speaker)
    if result is None:
        print(f'[FAIL] speaker {speaker}: could not capture the original EQ')
        return 1
    original_body, original_record = result
    try:
        bands = _validate_record(profile, original_record)
        new_value, change_key = _probe_value(contract, parameter, value_text)
    except ValueError as exc:
        print(f'[FAIL] invalid baseline or probe: {exc}')
        return 1

    original = bytes(original_body[:_record_size(profile)])
    old_value = _raw_field(parameter, bands[band])
    if new_value == old_value:
        print(f'[FAIL] requested {parameter} value is already active '
              f'({old_value}); choose a different probe value')
        return 1

    target_offset, target_width = _target_body_offset(profile, band, parameter)
    probe_packet = proto.build_surround_speaker_eq_command(
        profile, original_body, speaker, band,
        {change_key: new_value}, allow_experimental=True)
    restore_packet = proto.build_surround_speaker_eq_command(
        profile, original_body, speaker, band, {}, allow_experimental=True)

    probe_ok = False
    untouched_ok = False
    restore_ok = False
    print(f'speaker {speaker}, band {band + 1}: {parameter} '
          f'{old_value} -> {new_value}')
    try:
        dev.write(probe_packet)
        changed = dev.read_speaker(speaker)
        if changed is None:
            print('[FAIL] probe write: no category-0x1a response')
        else:
            changed_body, changed_record = changed
            try:
                changed_bands = _validate_record(profile, changed_record)
                actual = _raw_field(parameter, changed_bands[band])
                probe_ok = actual == new_value
                untouched_ok = _masked_equal(
                    original, changed_body[:_record_size(profile)],
                    target_offset, target_width)
                print(f'[{"PASS" if probe_ok else "FAIL"}] probe readback: '
                      f'got {actual}, wanted {new_value}')
                print(f'[{"PASS" if untouched_ok else "FAIL"}] probe preserved '
                      'the other meaningful record bytes')
            except ValueError as exc:
                print(f'[FAIL] probe readback: {exc}')
    finally:
        try:
            dev.write(restore_packet)
            restored = dev.read_speaker(speaker)
            if restored is not None:
                restored_body, _ = restored
                restore_ok = bytes(restored_body[:_record_size(profile)]) == original
            print(f'[{"PASS" if restore_ok else "FAIL"}] restored original '
                  f'{_record_size(profile)}-byte speaker record')
        except Exception as exc:
            print(f'[FAIL] restore raised {exc}')

    return 0 if probe_ok and untouched_ok and restore_ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-p', '--profile', default='orion',
                    help='profile path, filename, or short name (default: orion)')
    ap.add_argument('--speaker', type=lambda value: int(value, 0),
                    help='speaker index 0-15; read-only defaults to all speakers')
    ap.add_argument('--band', type=int,
                    help='EQ band number 1-16; required for --write')
    ap.add_argument('--parameter', choices=('frequency', 'q', 'gain', 'mode'),
                    help='one EQ field to probe; required for --write')
    ap.add_argument('--value',
                    help='new value: Hz, Q, dB, or a raw mode byte (e.g. 0x02)')
    ap.add_argument('--write', action='store_true',
                    help='perform one experimental write and restore round trip')
    ap.add_argument('--confirm-experimental-write', action='store_true',
                    help='acknowledge that 0x87 per-speaker write semantics are unverified')
    ap.add_argument('--timeout', type=float, default=2.0)
    ap.add_argument('--settle', type=float, default=0.5,
                    help='seconds to wait after each write (default 0.5)')
    args = ap.parse_args()

    if args.write:
        missing = [name for name, value in (
            ('--speaker', args.speaker), ('--band', args.band),
            ('--parameter', args.parameter), ('--value', args.value))
                   if value is None]
        if missing:
            ap.error('--write requires ' + ', '.join(missing))
        if not args.confirm_experimental_write:
            ap.error('--write also requires --confirm-experimental-write')
        if not 0 <= args.band <= 16:
            ap.error('--band must be 1..16')
    elif args.band is not None or args.parameter is not None or args.value is not None:
        ap.error('--band, --parameter, and --value are only used with --write')

    from antelope.cli import _resolve_profile_path
    try:
        profile = proto.load_profile(_resolve_profile_path(args.profile))
        count = _speaker_count(profile)
        if args.speaker is not None and not 0 <= args.speaker < count:
            ap.error(f'--speaker must be 0..{count - 1}')
        dev = Device(profile, args.timeout, args.settle)
        if args.write:
            return write_probe(dev, profile, args.speaker, args.band - 1,
                               args.parameter, args.value)
        return read_only(dev, profile, args.speaker)
    except (OSError, ValueError, proto.ConstraintError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
