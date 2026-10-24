#!/usr/bin/env python3
"""Passively retain an observed notify + existing-miner submit + reply.

Standard library only. No pool connection, share transmission, miner/service or
clock changes. tcpdump is the only process started/stopped; sudo is required.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import struct
import subprocess
import time
if __package__:
    from .decode_pool_capture import decode_capture, MAX_CAPTURE
else:
    from decode_pool_capture import decode_capture, MAX_CAPTURE


def contexts(report):
    """Retain preceding notifies as candidates; timing cannot prove job identity.

    In particular, notify field 3 must not be equated to worker_nonce. The wire
    submit has no explicit field named job_id in the observed schema.
    """
    found = []
    for submit in report['submits']:
        reply = submit['response']
        if not reply or reply.get('status') != 1 or reply.get('result') is not True:
            continue
        params = submit['request'].get('params')
        if not isinstance(params, list) or len(params) != 1 or not isinstance(params[0], dict):
            continue
        matching = []
        for record in report['records']:
            result = record['json'].get('result')
            if (record['connection'] == submit['connection'] and record['direction'] == 'in'
                and record['packet'] < submit['request_packet'] and isinstance(result, list)
                and len(result) == 5 and result[0] == 'notify'):
                matching.append(record)
        if not matching:
            continue
        # Keep the last two candidates for the compact console display. All
        # preceding notifications remain in the local complete decoded report.
        matching = matching[-2:]
        found.append({'connection': submit['connection'],
                      'preceding_notifies': [{'packet': r['packet'], 'json': r['json']} for r in matching],
                      'submit': submit['request'], 'response': reply,
                      'packets': [submit['request_packet'], submit['response_packet']],
                      'job_association': 'unverified; preceding notifications are candidates only'})
    return found


def complete_prefix(data):
    """Exclude only the actively written final PCAP record, never interior bytes."""
    endian = {b'\xd4\xc3\xb2\xa1': '<', b'\xa1\xb2\xc3\xd4': '>',
              b'\x4d\x3c\xb2\xa1': '<', b'\xa1\xb2\x3c\x4d': '>'}
    if len(data) < 24:
        return None
    if data[:4] not in endian:
        raise ValueError('not classic PCAP')
    pos = 24
    while pos+16 <= len(data):
        size, = struct.unpack_from(endian[data[:4]]+'I', data, pos+8)
        if size > MAX_CAPTURE:
            raise ValueError('packet exceeds capture limit')
        if pos+16+size > len(data):
            break
        pos += 16+size
    return data[:pos]


def stop_capture(process):
    if process.poll() is None:
        # Popen creates this distinct process group. No miner PID is looked up.
        stopped = subprocess.run(['sudo', '-n', '/bin/kill', '-INT', '--', '-'+str(process.pid)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if stopped.returncode and process.poll() is None:
            raise RuntimeError('could not interrupt the capture process group')
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        subprocess.run(['sudo', '-n', '/bin/kill', '-KILL', '--', '-'+str(process.pid)], check=True)
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=600)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 900:
        parser.error('duration must be 30..900 seconds')
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'pearl.service']).returncode:
        raise SystemExit('STOP: pearl.service is inactive; nothing restarted')
    subprocess.run(['sudo', '-v'], check=True)
    args.captures.mkdir(parents=True, exist_ok=True)
    stem = args.captures / ('pearl-context-05-'+str(time.time_ns()))
    capture = stem.with_suffix('.pcap')
    fd = os.open(capture, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    log = stem.with_suffix('.tcpdump.log')
    process = None
    last_error = None
    print('Watching existing-miner traffic for up to', args.seconds, 'seconds; stops early on complete context.', flush=True)
    try:
        with log.open('x') as diagnostics:
            process = subprocess.Popen([
                'sudo', '-n', 'timeout', '--signal=INT', '--kill-after=5s', str(args.seconds),
                'tcpdump', '-i', 'any', '-nn', '-s', '0', '-U', '-c', '1024',
                '-Z', pwd.getpwuid(os.getuid()).pw_name, '-w', str(capture), 'tcp', 'port', '9000',
            ], stdout=subprocess.DEVNULL, stderr=diagnostics, start_new_session=True)
            began = last_status = time.monotonic()
            while True:
                with capture.open('rb') as source:
                    raw = source.read(MAX_CAPTURE+1)
                if len(raw) > MAX_CAPTURE:
                    raise ValueError('capture exceeds 32 MiB')
                partial = complete_prefix(raw)
                if partial:
                    try:
                        report = decode_capture(partial)
                        if contexts(report):
                            break
                    except ValueError as error:
                        # A TCP gap can be transient while later packets are arriving.
                        last_error = str(error)
                if process.poll() is not None or time.monotonic()-began > args.seconds+5:
                    break
                if time.monotonic()-last_status >= 60:
                    print('Still watching; existing miner remains running.', flush=True)
                    last_status = time.monotonic()
                time.sleep(1)
    finally:
        if process is not None:
            stop_capture(process)
    if process.returncode not in (0, 124, 130, -2):
        raise SystemExit('STOP: tcpdump exited '+str(process.returncode)+'; diagnostics: '+str(log))
    raw = capture.read_bytes()
    report = decode_capture(raw)  # strict final parse, including record completeness
    selected = contexts(report)
    output = stem.with_suffix('.json')
    document = {'schema': 'pearlhash-share-context-1', 'capture_sha256': report['sha256'],
                'packets': report['packets'], 'contexts': selected, 'warnings': report['warnings'],
                'records': report['records']}
    encoded = json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as destination:
        destination.write(encoded+b'\n')
    print('Saved locally:', output)
    print('CONTEXT_SHA256:', hashlib.sha256(encoded).hexdigest())
    if not selected:
        print('No complete accepted-share context observed. Existing capture retained; no verdict guessed.')
        if last_error:
            print('Last transient decode note:', last_error)
        return 2
    # Print only the selected messages, never a login or an entire PCAP transfer.
    context = selected[0]
    print('PACKETS:', context['packets'])
    for notify in context['preceding_notifies']:
        result = notify['json']['result']
        print('PRECEDING_NOTIFY_PACKET:', notify['packet'])
        print('NOTIFY_PAYLOAD:', result[1])
        print('NOTIFY_FIELDS_2_3_4:', json.dumps(result[2:], separators=(',', ':')))
    print('SUBMIT:', json.dumps(context['submit'], separators=(',', ':')))
    print('RESPONSE:', json.dumps(context['response'], separators=(',', ':')))
    print('Header association still requires mathematical verification; timing alone is insufficient.')
    print('Existing-miner evidence only. No custom shares sent; no service or clock changes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
