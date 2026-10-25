#!/usr/bin/env python3
"""Inspect retained notify metadata from an already-verified LOCAL replay. ISC.

No network, GPU, proof rebuild or submission. XOR views are hypotheses only;
none is promoted to a protocol decoder. Session/header/nonces are not printed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
from pool.job import Notify, _SCRAMBLE_KEY


def load_object(path, limit):
    if path.stat().st_size > limit:
        raise ValueError('local input exceeds size cap')
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('expected local JSON object')
    return raw, value


def inspect(context_path, replay_manifest):
    _, manifest = load_object(replay_manifest, 1024*1024)
    if (manifest.get('gpu_math_checked') is not True
            or manifest.get('official_cpu_verifier') != 'passed'):
        raise ValueError('existing captured-share replay has not passed')
    raw, data = load_object(context_path, 8*1024*1024)
    if hashlib.sha256(raw.removesuffix(b'\n')).hexdigest() != manifest.get('private_context_sha256'):
        raise ValueError('saved context differs from completed replay')
    config = bytes.fromhex(manifest['facts']['config'])
    if len(config) != 52:
        raise ValueError('verified replay configuration width differs')
    contexts = [c for c in data['contexts']
                if c['submit'].get('id') == manifest['selected_submit_id']]
    if len(contexts) != 1:
        raise ValueError('verified replay submission is not unique')
    selected = contexts[0]
    records = []
    for record in data['records']:
        if record.get('direction') != 'in' or record.get('connection') != selected['connection']:
            continue
        message = record.get('json', {})
        result = message.get('result')
        if isinstance(result, list) and result and result[0] == 'notify':
            records.append((record['packet'], Notify.parse(message)))
    if not records:
        raise ValueError('saved notifications missing')
    selected_notify = [notify for packet, notify in records
                       if packet == manifest['selected_notify_packet']]
    if len(selected_notify) != 1:
        raise ValueError('verified replay notification is not unique')

    print('Saved context matches completed replay. No previous test repeated.')
    print('Notifications:', len(records), '; distinct retained metadata tails:',
          len({notify.payload[76:] for _, notify in records}))
    print('Observed markers:', ','.join(sorted({notify.version_marker for _, notify in records})),
          '(not used alone to select consensus rules)')
    k, rank, reserved = struct.unpack_from('<IHH', config)
    print(f'Verified replay config: k={k}; rank={rank}; reserved={reserved}')
    print('Verified pattern encodings:', config[8:14].hex(), config[14:20].hex())
    print('Verified config suffix zero:', config[20:] == bytes(32))
    params = selected['submit']['params'][0]
    for name in ('m', 'n', 'tile_h', 'tile_w', 'sb', 'tail_mode'):
        value = params.get(name)
        if type(value) is not int:
            raise ValueError('saved profile field has unexpected type')
        print(f'{name}={value}', end='; ')
    print()
    payload = selected_notify[0].payload
    views = [
        ('RAW retained bytes', payload[76:]),
        ('XOR32 aligned to payload start: UNVERIFIED',
         bytes(value ^ _SCRAMBLE_KEY[(76+i) % 32] for i, value in enumerate(payload[76:]))),
        ('XOR32 aligned to metadata start: UNVERIFIED',
         bytes(value ^ _SCRAMBLE_KEY[i % 32] for i, value in enumerate(payload[76:]))),
    ]
    for name, value in views:
        print(name)
        for offset in range(0, len(value), 32):
            print(f'  {76+offset:03d}: {value[offset:offset+32].hex()}')
        offset = value.find(config)
        print('  Exact 52-byte config match:', 'none' if offset < 0 else str(76+offset))
    print('Inspection complete. These views do not establish metadata meanings.')
    print('No network, GPU work, proof rebuild, submitted share or miner change.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--replay-manifest', type=Path, required=True)
    args = parser.parse_args()
    inspect(args.context, args.replay_manifest)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print('STOP:', error, flush=True)
        raise SystemExit(1)
