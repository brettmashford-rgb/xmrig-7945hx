#!/usr/bin/env python3
"""Decode local Pearlhash PCAP; correlate submit responses without guessing jobs.

ISC license. Standard library only. No network connections or share generation.
Raw decoded messages remain in a private local JSON file; console omits logins.
"""
import argparse
import hashlib
import heapq
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


def frame_events(group, body):
    """First capture packet making each LF frame available in TCP order.

    Sweep first-seen byte ranges, retaining prefix dependencies. A late gap fill
    delays every later frame; an identical retransmission cannot move it later.
    Packet ordinals determine capture order, even with equal/backward timestamps.
    """
    origin = group['parts'][0][0]
    spans = [(((seq-origin+0x80000000)&0xffffffff)-0x80000000,
              len(part), packet, stamp) for seq, part, packet, stamp in group['events']]
    base = min(s[0] for s in spans)
    spans = sorted((start-base, start-base+size, packet, stamp)
                   for start, size, packet, stamp in spans)
    boundaries = sorted({p for start, end, _, _ in spans for p in (start, end)})
    ends = [i+1 for i, byte in enumerate(body) if byte == 10]
    heap, result = [], []
    cursor = frame = 0
    latest = (0, 0)
    for start, end in zip(boundaries, boundaries[1:]):
        while cursor < len(spans) and spans[cursor][0] <= start:
            _, stop, packet, stamp = spans[cursor]
            heapq.heappush(heap, (packet, stop, stamp))
            cursor += 1
        while heap and heap[0][1] <= start:
            heapq.heappop(heap)
        if not heap:
            raise ValueError('TCP sequence gap in frame timing')
        packet, _, stamp = heap[0]
        if packet > latest[0]:
            latest = (packet, stamp)
        while frame < len(ends) and ends[frame] <= end:
            result.append(latest)
            frame += 1
    if frame != len(ends):
        raise ValueError('incomplete frame timing')
    return result


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
        timing = frame_events(group, body)
        for index, line in enumerate(lines):
            try:
                message = decode(line+b'\n', max_line=MAX_STREAM)
            except (ValueError, UnicodeError, RecursionError):
                if index == 0 and not group['syn']:
                    warnings.append(f'{connection}: undecodable initial fragment omitted')
                    continue
                raise ValueError(f'{connection}: invalid complete encoded frame at line {index}') from None
            records.append({'connection': connection, 'direction': 'out' if outbound else 'in',
                            'packet': timing[index][0], 'timestamp_ns': timing[index][1],
                            'stream_line': index, 'json': message})
    records.sort(key=lambda r: (r['packet'], r['stream_line']))
    requests = {}
    responses = {}
    for record in records:
        message = record['json']
        key = request_key(message.get('id'))
        if key is None:
            continue
        key = (record['connection'], key)
        if record['direction'] == 'out':
            requests.setdefault(key, []).append(record)
        elif message.get('id') != -1:
            responses.setdefault(key, []).append(record)
    submits = []
    for key, candidates in requests.items():
        for request in candidates:
            message = request['json']
            if message.get('method') != 'submit':
                continue
            replies = responses.get(key, [])
            ambiguous = len(candidates) != 1 or len(replies) > 1
            preceding = bool(len(replies) == 1 and replies[0]['packet'] <= request['packet'])
            submits.append({'connection': key[0], 'request': message,
                            'response': replies[0]['json'] if len(replies) == 1 and not ambiguous and not preceding else None,
                            'ambiguous_id': ambiguous, 'response_before_request': preceding,
                            'request_packet': request['packet'],
                            'response_packet': replies[0]['packet'] if len(replies) == 1 else None})
    return {'schema': 'pearlhash-decoded-capture-2', 'sha256': hashlib.sha256(data).hexdigest(),
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
