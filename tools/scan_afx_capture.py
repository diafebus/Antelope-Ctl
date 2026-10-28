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
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from antelope.catalog import load_catalog


# 0x18: directed Gyratec IX GUI priming, scan-GyratecIX-20261025T203041877Z.
# 0x16: directed VEQ-HLF GUI sweep, scan-PultecHLF-20261025T200435681Z.
# 0x19: directed NEU-PEV GUI priming, scan-NeumannPev-20261026T161447638Z.
# 0x22: directed NEU-W492 GUI priming, scan-NeumannW492-20261026T163707526Z.
# 0x23: directed VEQ-4K PINK GUI priming, scan-SslPink-20261027T020747657Z.
# 0x1a: directed VMEQ-5 GUI sweep, scan-PultecMEQ-20261025T101308607Z.
# 0x1b: directed VEQ-STU089 GUI priming, unattended-20261027T144257Z-veqstu089-priming frame2457.
# 0x1d: directed PowerGate GUI sweep, scan-PowerGate-20261025T093451547Z.
# 0x1e: directed Audio/Baton VOLUME priming, unattended-20261028T023901Z-audiobaton-priming frame2529.
# 0x17: directed VCA160 Output Gain priming, unattended-20261028T145303Z-vca160-priming frames2247/2295.
# These are passive decoder families, not permission to send a command.
PARAMETER_OPCODES = {0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x20, 0x22, 0x23, 0x7c}


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


def observed_instance_readbacks(reports, profile, catalog, max_gap=1.0):
    """Offline only: correlate serialized tagged replies and decode observed fields.

    Replies omit instance IDs. Overlap or a late reply invalidates correlation
    for the remainder of this capture; a time window alone is insufficient.
    max_gap is an analysis limit, never a device query timeout or authorization.
    """
    layout = profile['frame']['afx_slot']['instance_state_readback']
    request, response = layout['request'], layout['response']
    transport = profile['transport']
    size = transport['report_size']
    out_ep, in_ep = (int(transport[k], 0) for k in ('out_endpoint', 'in_endpoint'))
    header = bytes.fromhex(response['header_prefix_hex'])
    definitions = {}
    for effect in catalog['effects']:
        for implementation in effect['implementations']:
            if implementation['profile'] == 'orion_studio_sc.json':
                observation = implementation.get('parameter_observation', {})
                alignment = observation.get('startup_readback_observation')
                if alignment:
                    definitions[implementation['type_id']] = (observation, alignment)
    pending, blocked, states = None, False, []
    for frame, seconds, endpoint, data in reports:
        if len(data) != size or blocked:
            continue
        if endpoint == out_ep and all(data[request[k + '_offset']] == int(request[k], 0)
                                      for k in ('magic', 'opcode', 'kind')):
            offset, width = request['effect_selector_offset'], request['effect_selector_width']
            selector = int.from_bytes(data[offset:offset + width], request['effect_selector_endian'])
            tag = int(request['effect_selector_tag'], 0)
            if not selector & tag:
                continue
            if pending is not None:
                blocked = True
                continue
            offset, width = request['instance_offset'], request['instance_width']
            pending = (frame, seconds, selector, int.from_bytes(data[offset:offset + width], request['instance_endian']))
        elif endpoint == in_ep and data.startswith(header):
            offset, width = response['effect_selector_offset'], response['effect_selector_width']
            selector = int.from_bytes(data[offset:offset + width], request['effect_selector_endian'])
            if pending is None or pending[2] != selector:
                blocked = True
                continue
            query_frame, query_seconds, _, instance = pending
            pending = None
            if not 0 <= seconds - query_seconds <= max_gap:
                blocked = True
                continue
            effect_type = selector & ~int(request['effect_selector_tag'], 0)
            if effect_type not in definitions:
                continue
            observation, alignment = definitions[effect_type]
            values = {}
            fields = observation.get('labelled_gui_observations', {}) if instance == alignment['instance'] else {}
            for name, field in fields.items():
                offset = field.get('startup_reply_offset')
                if offset is not None:
                    raw = data[offset:offset + field['width']]
                    value = int.from_bytes(raw, 'little')
                    values[name] = {'raw': value, 'state': field['visual_states'].get(str(value), 'unknown'),
                                    'status': 'startup baseline association; changed-state readback untested'}
            states.append({'query_frame': query_frame, 'frame': frame, 'type': effect_type,
                           'instance_from_query': instance, 'values': values,
                           'parameter_payload_hex': data[response['parameter_data_offset']:].hex(),
                           'runtime_query_enabled': False, 'alignment_status': alignment['status']})
    return {'states': states, 'correlation_blocked': blocked}


def analyze_reports(reports):
    reports = list(reports)
    operations, parameters = [], defaultdict(list)
    readback_queries = Counter()
    instance_queries, instance_states, pending_instances = [], [], {}
    profile = json.loads((Path(__file__).resolve().parents[1] / 'profiles/orion_studio_sc.json').read_text())
    catalog = load_catalog(Path(__file__).resolve().parents[1] / 'profiles/afx_effects.json')
    bypass_layouts = {i['type_id']: i['bypass_observation'] for e in catalog['effects']
                      for i in e['implementations'] if i['profile'] == 'orion_studio_sc.json'
                      and 'bypass_observation' in i}
    for layout in bypass_layouts.values():
        if (layout['status'] != 'capture-observed' or layout['opcode'] != '0x14' or layout['selector'] != '0x98'
                or sorted(layout[key] for key in ('instance_offset', 'type_offset', 'state_offset')) != [17,18,19]):
            raise ValueError('Invalid captured model-local bypass layout')
    from antelope import afx
    for number, timestamp, endpoint, payload in reports:
        if len(payload) != 320:
            continue
        if endpoint == 0x82 and afx.is_parameter_response(profile, payload):
            state = afx.parse_parameter_response(profile, payload)
            pending = pending_instances.pop(73, None)
            instance_states.append({'frame':number, 'seconds':timestamp, 'type':73,
                'instance_from_query': pending['instance'] if pending else None,
                'query_frame': pending['frame'] if pending else None, **state})
            continue
        if endpoint != 1:
            continue
        if payload[0] == 0x74 and payload[4] == 0x11 and payload[8] == 7 and payload[15] == 0x80:
            selector = int.from_bytes(payload[12:16], 'little')
            query = {'frame':number, 'seconds':timestamp, 'type':selector & 0x7fffffff,
                     'instance':int.from_bytes(payload[16:20], 'little')}
            instance_queries.append(query)
            pending_instances[query['type']] = query
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
            layout = bypass_layouts.get(payload[18])
            operations.append({**base, 'kind': 'bypass',
                               'state': payload[layout['state_offset']] if layout else payload[17],
                               'type': payload[18],
                               'instance': payload[layout['instance_offset']] if layout else payload[19],
                               'polarity_confirmed': False})
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
    observed = observed_instance_readbacks(reports, profile, catalog)
    return {'report_offsets_exclude_usb_header': True, 'device_commands_sent': False,
            'ownership_inferred': False, 'operations': operations, 'parameter_groups': groups,
            'instance_state_queries': instance_queries, 'memorycat_readbacks': instance_states,
            'observed_instance_readbacks': observed,
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
