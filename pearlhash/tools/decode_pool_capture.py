#!/usr/bin/env python3
"""Decode local Pearlhash PCAP; correlate submit responses without guessing jobs.

ISC license. Standard library only. No network connections or share generation.
Raw decoded messages remain in a private local JSON file; console omits logins.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

if __package__:
    from .inspect_pool_capture import payloads, reassemble
    from .pool_probe import decode
else:
    from inspect_pool_capture import payloads, reassemble
    from pool_probe import decode

MAX_CAPTURE = 32 * 1024 * 1024
MAX_STREAM = 8 * 1024 * 1024


def request_key(value):
    # bool is not an integer request id, despite Python's subclass relationship.
    if type(value) not in (int, str):
        return None
    return (type(value).__name__, value)


def decode_capture(data, port=9000):
    if len(data) > MAX_CAPTURE:
        raise ValueError('capture exceeds 32 MiB limit')
    packets, groups = payloads(data, port)
    records, warnings = [], []
    for (addresses, src, dst), group in groups.items():
        if not group['parts']:
            continue
        if group['syn']:
            start = group['start']
            first = min(((seq-start+0x80000000)&0xffffffff)-0x80000000
                        for seq, _ in group['parts'])
            if first != 0:
                raise ValueError('missing initial TCP bytes')
        body = reassemble(group['parts'])
        if len(body) > MAX_STREAM:
            raise ValueError('stream exceeds 8 MiB limit')
        outbound = dst == port
        identity = (addresses + src.to_bytes(2, 'big') + dst.to_bytes(2, 'big')
                    if outbound else addresses[4:] + addresses[:4]
                    + dst.to_bytes(2, 'big') + src.to_bytes(2, 'big'))
        connection = hashlib.sha256(identity).hexdigest()[:16]
        lines = body.split(b'\n')
        tail = lines.pop()
        if tail:
            warnings.append(f'{connection}: incomplete final line omitted ({len(tail)} bytes)')
        if not group['syn']:
            warnings.append(f'{connection}: capture starts mid-session; initial boundary unverified')
        for index, line in enumerate(lines):
            try:
                message = decode(line+b'\n', max_line=MAX_STREAM)
            except (ValueError, UnicodeError, RecursionError):
                if index == 0 and not group['syn']:
                    warnings.append(f'{connection}: undecodable initial fragment omitted')
                    continue
                raise ValueError(f'{connection}: invalid complete encoded frame at line {index}') from None
            records.append({'connection': connection, 'direction': 'out' if outbound else 'in',
                            'json': message})
    requests = {}
    responses = {}
    for record in records:
        message = record['json']
        key = request_key(message.get('id'))
        if key is None:
            continue
        key = (record['connection'], key)
        if record['direction'] == 'out':
            requests.setdefault(key, []).append(message)
        elif message.get('id') != -1:
            responses.setdefault(key, []).append(message)
    submits = []
    for key, candidates in requests.items():
        for message in candidates:
            if message.get('method') != 'submit':
                continue
            replies = responses.get(key, [])
            ambiguous = len(candidates) != 1 or len(replies) > 1
            submits.append({'connection': key[0], 'request': message,
                            'response': replies[0] if len(replies) == 1 and not ambiguous else None,
                            'ambiguous_id': ambiguous})
    return {'schema': 'pearlhash-decoded-capture-1', 'sha256': hashlib.sha256(data).hexdigest(),
            'packets': packets, 'records': records, 'submits': submits, 'warnings': warnings}


def describe(value):
    """Bound console output; no automatic printing of large proofs/arrays."""
    if isinstance(value, dict):
        return {str(k): describe(v) for k, v in list(value.items())[:32]}
    if isinstance(value, list):
        return [describe(v) for v in value] if len(value) <= 32 else {'array_length': len(value)}
    if isinstance(value, str) and len(value) > 160:
        return {'string_characters': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest()}
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.capture.open('rb') as source:
        data = source.read(MAX_CAPTURE+1)
    report = decode_capture(data)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write('\n')
    print('PCAP SHA256:', report['sha256'])
    print('Packets:', report['packets'], 'decoded messages:', len(report['records']))
    for warning in report['warnings']:
        print('NOTE:', warning)
    methods = {}
    for record in report['records']:
        if record['direction'] == 'out':
            method = record['json'].get('method', '(absent)')
            if not isinstance(method, str):
                method = '(invalid type)'
            methods[method] = methods.get(method, 0) + 1
    print('Captured outbound methods:', json.dumps(methods, sort_keys=True))
    print('Existing-miner submit requests:', len(report['submits']))
    for submit in report['submits'][:3]:
        print('SUBMIT REQUEST:', json.dumps(describe(submit['request']), separators=(',', ':')))
        print('MATCHED RESPONSE:', json.dumps(describe(submit['response']), separators=(',', ':')))
        if submit['ambiguous_id']:
            print('STOP: duplicate request/response id; correlation is ambiguous')
    print('Private decoded transcript:', args.output)
    print('These are captured existing-miner messages, not custom-miner shares.')
    if not report['submits']:
        print('No submit captured; no share verdict inferred.')


if __name__ == '__main__':
    main()
