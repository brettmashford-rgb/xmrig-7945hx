#!/usr/bin/env python3
"""Receive one fresh pool job through the new independent state handler. ISC.

One configured pool connection/login; no GPU, mining, proof or share submission.
Credentials are read locally and never printed or copied to the result report.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import threading

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
from pool.receiver import PoolReceiver
from pool.session import MiningProfile, PoolSession
from reference.patterns import PeriodicPattern


def saved_wallet(path):
    if path.stat().st_size > 1024**2:
        raise ValueError('saved login exceeds credential input cap')
    data = json.loads(path.read_text())
    if (not isinstance(data, dict) or data.get('schema') != 'pearlhash-login-probe-1'
            or data.get('error') is not None):
        raise ValueError('expected completed local independent login probe')
    requests = [r['json'] for r in data['records'] if r.get('direction') == 'out'
                and r.get('json', {}).get('method') == 'login']
    if len(requests) != 1:
        raise ValueError('saved login request is not unique')
    params = requests[0].get('params')
    if not isinstance(params, list) or len(params) != 3 or type(params[0]) is not str:
        raise ValueError('saved login credential schema differs')
    return params[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--login-file', type=Path, required=True)
    parser.add_argument('--worker', default='5060-dev-receiver')
    parser.add_argument('--m', type=int, required=True)
    parser.add_argument('--n', type=int, required=True)
    parser.add_argument('--k', type=int, required=True)
    parser.add_argument('--rank', type=int, required=True)
    parser.add_argument('--rows', required=True)
    parser.add_argument('--cols', required=True)
    parser.add_argument('--cert-version', type=int, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    profile = MiningProfile(args.m, args.n, args.k, args.rank,
                            PeriodicPattern(bytes.fromhex(args.rows)), PeriodicPattern(bytes.fromhex(args.cols)))
    session = PoolSession(profile, cert_version=args.cert_version)
    wallet = saved_wallet(args.login_file)
    receiver = PoolReceiver(session, args.host, args.port, wallet, args.worker)
    stop = threading.Event()
    observed = []
    def on_job(job):
        if not session.is_current(job):
            raise ValueError('received job is stale')
        observed.append({'generation': job.generation, 'header_bytes': len(job.header),
                         'config_bytes': len(job.profile.config), 'job_key_bytes': len(job.job_key),
                         'assigned_extranonce_bytes': len(job.assigned_extranonce),
                         'opaque_metadata_bytes': len(job.opaque_metadata),
                         'scaled_target_bits': job.share_bound.bit_length()})
        print('PASS: fresh pool login + assigned extranonce + supported V3 notification produced a current job', flush=True)
        print(f'Header76 + explicit config52 -> job key32; scaled target {job.share_bound.bit_length()} bits', flush=True)
        stop.set()
    # Reserve a private result file before connecting; never overwrite a prior run.
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    error = None
    result = None
    try:
        print(f'Connecting once to {args.host}:{args.port}; waiting up to 30 seconds for a current job.', flush=True)
        result = receiver.run(on_job, stop=stop, seconds=30)
        if not observed:
            raise RuntimeError(f'no ready job before receiver ended ({result.stop_reason})')
        if session.snapshot() is not None or session.is_current(None):
            raise RuntimeError('connection end retained active work')
        print('PASS: connection closed and its active work invalidated', flush=True)
    except (OSError, ValueError, RuntimeError, UnicodeError, RecursionError) as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    finally:
        report = {'complete': error is None, 'endpoint': [args.host, args.port],
                  'live_job_observed': bool(observed), 'job_shapes': observed,
                  'receiver': asdict(result) if result is not None else None, 'error': error,
                  'gpu_executed': False, 'submitted_shares': 0,
                  'extranonce_worker_role_verified': False,
                  'scope': 'live job reception/state only; not mining or pool share acceptance'}
        with os.fdopen(fd, 'w') as output:
            json.dump(report, output, indent=2)
            output.write('\n')
    if error is not None:
        print('STOP:', error, flush=True)
        return 1
    print('Completion saved. No GPU work, proof, submitted share, service or clock change.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        print('STOP:', error, flush=True)
        raise SystemExit(1)
