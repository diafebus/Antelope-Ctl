#!/usr/bin/env python3
"""Summarize owned-Orion AFX captures without exporting identity or account data.

Uses tshark offline; never opens the device or sends commands. Reports full
slot orders, link/bypass actions, parameter byte changes and mirrored writes.
Byte ranges describe captured bytes, not inferred knob units or ownership.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess


PARAMETER_OPCODES = {0x1c, 0x20, 0x7c}


def _tshark(path, *arguments):
    return subprocess.run(['tshark', '-r', str(path), *arguments],
                          capture_output=True, text=True, check=True).stdout


def extract_reports(path):
    locations = set()
    for line in _tshark(path, '-Y', 'usb.idVendor == 0x23e5 && usb.idProduct == 0xa221',
                        '-T', 'fields', '-e', 'usb.bus_id', '-e', 'usb.device_address').splitlines():
        fields = line.split('\t')
        if len(fields) == 2 and all(fields):
            locations.add(tuple(fields))
    reports = []
    if locations:
        output = _tshark(path, '-Y', 'usb.data_len == 320 && (usb.endpoint_address == 0x01 || usb.endpoint_address == 0x82)',
                         '-T', 'fields', '-e', 'frame.number', '-e', 'frame.time_relative',
                         '-e', 'usb.bus_id', '-e', 'usb.device_address',
                         '-e', 'usb.endpoint_address', '-e', 'usbhid.data', '-e', 'usb.capdata')
        for line in output.splitlines():
            fields = line.split('\t')
            if len(fields) < 6 or tuple(fields[2:4]) not in locations:
                continue
            raw = next((field for field in fields[5:] if field), '')
            payload = bytes.fromhex(raw.replace(':', ''))
            if len(payload) == 320:
                reports.append((int(fields[0]), float(fields[1]), int(fields[4], 0), payload))
        if reports:
            return reports
    # Darwin captures carry VID/PID and endpoint in a 40-byte pseudo-header.
    packets = json.loads(_tshark(path, '-Y', 'frame.len == 360', '-T', 'json', '-x'))
    for packet in packets:
        layers = packet['_source']['layers']
        raw = bytes.fromhex(layers['frame_raw'][0])
        header, payload = raw[:40], raw[40:]
        if len(payload) != 320 or header[30] not in (1, 0x82):
            continue
        if not any(int.from_bytes(header[36:38], endian) == 0x23e5
                   and int.from_bytes(header[38:40], endian) == 0xa221
                   for endian in ('little', 'big')):
            continue
        frame = layers['frame']
        reports.append((int(frame['frame.number']), float(frame['frame.time_relative']), header[30], payload))
    if not reports:
        raise ValueError('No Orion HID reports with verified VID/PID were found')
    return reports


def analyze_reports(reports):
    operations, parameters = [], defaultdict(list)
    readback_queries = Counter()
    for number, timestamp, endpoint, payload in reports:
        if len(payload) != 320 or endpoint != 1:
            continue
        if payload[0] == 0x74 and payload[4] == 0x10:
            if payload[8] in (0x0b, 0x0c, 0x15, 0x19):
                readback_queries[(payload[8], int.from_bytes(payload[12:16], 'little'))] += 1
            continue
        if payload[0] != 0x70:
            continue
        base = {'frame': number, 'seconds': timestamp}
        opcode, selector = payload[4], payload[16]
        if opcode == 0x23 and selector == 0xd7 and payload[17] == 0x11:
            operations.append({**base, 'kind': 'chain', 'channel_index': payload[18],
                               'slots': [{'type': effect_type, 'instance': instance}
                                         for effect_type, instance in zip(payload[19:35:2], payload[20:35:2])]})
        elif opcode == 0x14 and selector == 0xa2 and payload[17] == 4:
            operations.append({**base, 'kind': 'link', 'pair_index': payload[18], 'value': payload[19]})
        elif opcode == 0x14 and selector == 0x98:
            operations.append({**base, 'kind': 'bypass', 'state': payload[17],
                               'type': payload[18], 'instance': payload[19], 'polarity_confirmed': False})
        elif opcode in PARAMETER_OPCODES and selector == 0xd5:
            parameters[(opcode, payload[17], payload[18])].append(
                (number, timestamp, payload[19], payload[20:]))
    groups = []
    for (opcode, subcommand, effect_type), samples in sorted(parameters.items()):
        varying = [20 + i for i in range(300) if len({sample[3][i] for sample in samples}) > 1]
        mirrored = Counter()
        for previous, current in zip(samples, samples[1:]):
            if (previous[2] != current[2] and previous[3] == current[3]
                    and 0 <= current[1] - previous[1] <= .020):
                mirrored[(previous[2], current[2])] += 1
        targets = []
        for instance in sorted({sample[2] for sample in samples}):
            selected = [sample for sample in samples if sample[2] == instance]
            runs = []
            for previous, current in zip(selected, selected[1:]):
                offsets = [20 + i for i, (a, b) in enumerate(zip(previous[3], current[3])) if a != b]
                if not offsets:
                    continue
                if runs and runs[-1]['offsets'] == offsets:
                    runs[-1]['last_frame'] = current[0]
                    runs[-1]['samples'] += 1
                else:
                    runs.append({'offsets': offsets, 'first_frame': current[0],
                                 'last_frame': current[0], 'samples': 1})
            targets.append({'instance': instance, 'frames': len(selected), 'change_runs': runs})
        groups.append({'opcode': hex(opcode), 'subcommand': hex(subcommand), 'type': effect_type,
                       'frames': len(samples), 'first_frame': samples[0][0], 'last_frame': samples[-1][0],
                       'varying_offsets': varying,
                       'observed_byte_ranges': {str(offset): [min(s[3][offset-20] for s in samples),
                                                             max(s[3][offset-20] for s in samples)] for offset in varying},
                       'mirrored_writes': [{'from_instance': a, 'to_instance': b, 'pairs': count}
                                           for (a, b), count in sorted(mirrored.items())], 'targets': targets})
    return {'report_offsets_exclude_usb_header': True, 'device_commands_sent': False,
            'ownership_inferred': False, 'operations': operations, 'parameter_groups': groups,
            'readback_queries': [{'category': hex(category), 'index': index, 'count': count}
                                 for (category, index), count in sorted(readback_queries.items())]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, help='save sanitized analysis locally instead of printing')
    args = parser.parse_args()
    result = json.dumps(analyze_reports(extract_reports(args.capture)), indent=2) + '\n'
    if args.output:
        args.output.write_text(result)
        print(f'AFX analysis saved to {args.output}')
    else:
        print(result, end='')


if __name__ == '__main__':
    main()
