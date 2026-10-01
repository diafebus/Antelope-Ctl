#!/usr/bin/env python3
"""Record changed Orion AFX readbacks through the WebUI's single device actor.

Read-only GETs; no raw HID access, parameter writes or discovery sweeps. The
current API supplies Memory Cat parameters for captured instances0-2 only.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

PARAMETERS = ('blend', 'level', 'feedback', 'chrs_vibr', 'depth', 'delay', 'lpf_fc', 'size')


def read_snapshot(base_url, channel):
    url = f'{base_url.rstrip("/")}/api/afx/memorycat-test?channel={channel}&refresh=true'
    try:
        with urlopen(url, timeout=15) as response:
            state = json.load(response)
    except (HTTPError, URLError) as error:
        raise RuntimeError(f'AFX read request failed: {error}') from None
    if not state.get('available') or not state.get('online'):
        raise RuntimeError('The Orion AFX device is unavailable; recording stopped')
    pair = channel // 2
    linked = state.get('links', [None] * 16)[pair]
    channels = [channel, channel ^ 1] if linked is True else [channel]
    chains = {}
    for index in channels:
        rows = state.get('channels', {}).get(str(index))
        chains[str(index)] = None if rows is None else [
            {'type': row['type'], 'instance': row['instance']} for row in rows]
    loaded = {str(row['instance']) for rows in chains.values() if rows
              for row in rows if row['type'] == 73}
    states = {}
    for instance in loaded:
        item = state.get('parameter_states', {}).get(instance)
        if item:
            states[instance] = {'values': {name: item['values'][name] for name in PARAMETERS},
                                'bypassed': item['bypassed'], 'source': 'readback'}
    return {'session': state['session'], 'selected_channel': channel,
            'linked': linked, 'chains': chains, 'memorycat_states': states,
            'read_errors': {index: state.get('parameter_read_errors', {}).get(index)
                            for index in loaded if index in state.get('parameter_read_errors', {})}}


def record(base_url, channel, seconds, interval, output):
    started = time.monotonic()
    previous, session, changes = None, None, 0
    with output.open('x') as stream:
        stream.write(json.dumps({'kind': 'metadata', 'profile': 'orion_studio_sc.json',
            'started_utc': datetime.now(timezone.utc).isoformat(), 'device_writes': False,
            'source': 'WebUI actor readbacks', 'channel': channel, 'seconds': seconds,
            'parameter_scope': 'captured Memory Cat instances0-2'}) + '\n')
        while True:
            state = read_snapshot(base_url, channel)
            if session is not None and state['session'] != session:
                raise RuntimeError('Device connection changed; start a new recording')
            session = state['session']
            if state != previous:
                stream.write(json.dumps({'kind': 'state', 'seconds': round(time.monotonic()-started, 3),
                                         **state}) + '\n')
                stream.flush()
                previous, changes = state, changes + 1
            remaining = started + seconds - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8714', help='running WebUI URL')
    parser.add_argument('--channel', type=int, choices=range(1,33), default=1, help='AFX channel1-32')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--interval', type=float, default=1, help='seconds between fresh readbacks, minimum0.5')
    parser.add_argument('--output', type=Path, required=True, help='new local JSONL file, normally under captures/')
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600 or not .5 <= args.interval <= 60:
        parser.error('seconds must be0-3600 and interval0.5-60')
    try:
        changes = record(args.url, args.channel-1, args.seconds, args.interval, args.output)
    except (RuntimeError, OSError, KeyError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    except KeyboardInterrupt:
        parser.exit(0, 'Recording stopped; completed states remain in the local file.\n')
    print(f'Recorded {changes} changed states in {args.output}; no device settings written')


if __name__ == '__main__':
    main()
