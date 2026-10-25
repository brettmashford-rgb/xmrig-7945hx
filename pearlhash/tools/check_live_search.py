#!/usr/bin/env python3
"""One live job -> production commitments -> bounded GPU tile search. ISC.

No share submission, proof construction or miner/service/clock changes.
Assigned extranonce is used provisionally as worker nonce for this no-submit
experiment only. Its compact-submit role remains unverified.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
from pool.receiver import PoolReceiver
from pool.search import prepare_base, prepare_nonce, search_nonce, plan_for
from pool.session import MiningProfile, PoolSession
from pool.worker import LatestJobWorker
from reference.patterns import PeriodicPattern
from tools.candidate_scan import CandidateScanner
from tools.check_live_job import saved_wallet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--login-file', type=Path, required=True)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--tiles', type=int, default=16)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300 or not 1 <= args.tiles <= 64:
        raise ValueError('receive window or tile cap outside bounded experiment')
    rows = PeriodicPattern(bytes.fromhex('000103040000'))
    cols = PeriodicPattern(bytes.fromhex('000103010103'))
    profile = MiningProfile(5121, 262144, 32768, 128, rows, cols)
    session = PoolSession(profile, cert_version=3)
    wallet = saved_wallet(args.login_file)
    receiver = PoolReceiver(session, args.host, args.port, wallet, '5060-dev-live-search')
    stop = threading.Event()
    heartbeat_done = threading.Event()
    results = []
    stage_lock = threading.Lock()
    stage = ['waiting for a live job']
    def progress(label):
        with stage_lock:
            stage[0] = label
        print(label, flush=True)
    def heartbeat():
        while not heartbeat_done.wait(15):
            with stage_lock:
                label = stage[0]
            print('Still running: '+label, flush=True)
    def process(job, current):
        started = time.monotonic()
        progress('Fresh job: streaming the production B commitment on CPU (8 GiB logical; no full matrix allocation).')
        base = prepare_base(job, current)
        base_seconds = time.monotonic()-started
        progress('B commitment ready; preparing one fresh nonce and its production seeds.')
        nonce_started = time.monotonic()
        context = prepare_nonce(job, base, job.assigned_extranonce, secrets.token_bytes(8), current)
        nonce_seconds = time.monotonic()-nonce_started
        device = CandidateScanner()
        try:
            progress('Starting this worker thread\'s own GPU context and bounded production tile search.')
            device.start(args.module)
            scan_started = time.monotonic()
            found, cursor = search_nonce(context, device, current, stop=args.tiles)
            return {'generation': job.generation, 'scaled_target_bits': job.share_bound.bit_length(),
                    'production_domain_tiles': plan_for(job).count, 'tiles_scanned': cursor.next_tile,
                    'candidate_found': found is not None, 'cpu_checked_candidates': device.verified_tiles,
                    'gpu_dispatches': device.dispatches, 'base_seconds': round(base_seconds, 3),
                    'nonce_seconds': round(nonce_seconds, 3),
                    'bounded_scan_seconds': round(time.monotonic()-scan_started, 3)}
        finally:
            device.close()
    def completed(job, result):
        results.append(result)
        print(f'PASS: fresh live job -> production commitments/seeds -> {result["tiles_scanned"]} GPU tiles; actual pool target retained', flush=True)
        stop.set()
    worker = LatestJobWorker(session, process, completed, stop=stop)
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    error = None
    received = None
    heartbeat_thread = threading.Thread(target=heartbeat, name='pearlhash-progress', daemon=True)
    try:
        worker.start()
        heartbeat_thread.start()
        print(f'One connection to {args.host}:{args.port}; up to {args.seconds} seconds of receiving.', flush=True)
        print('Receiver stays active during CPU/GPU work; replacements discard stale work.', flush=True)
        received = receiver.run(worker.publish, stop=stop, seconds=args.seconds)
    except (OSError, ValueError, RuntimeError, UnicodeError, RecursionError) as exc:
        error = type(exc).__name__+': '+str(exc)
    finally:
        stop.set()
        session.close()
        progress('Connection closed; joining our search worker. An in-flight native commitment must finish first.')
        worker.close()
        heartbeat_done.set()
        if heartbeat_thread.is_alive():
            heartbeat_thread.join()
        if worker.error is not None:
            error = type(worker.error).__name__+': '+str(worker.error)
        if error is None and not results:
            error = 'No current-job GPU window completed before connection ended; see worker counters.'
        report = {'complete': error is None and bool(results), 'endpoint': [args.host, args.port],
                  'receiver': asdict(received) if received is not None else None,
                  'worker': worker.stats(), 'windows': results, 'error': error,
                  'gpu_checked': bool(results), 'submitted_shares': 0,
                  'proof_constructed': False, 'extranonce_worker_role_verified': False,
                  'scope': 'bounded live production search experiment; no full nonce or pool share verdict'}
        with os.fdopen(fd, 'w') as output:
            json.dump(report, output, indent=2)
            output.write('\n')
    if error:
        print('STOP:', error, flush=True)
        print('Worker counters:', worker.stats(), flush=True)
        return 1
    result = results[0]
    print('PASS: receiver closed; worker joined; active job invalidated', flush=True)
    print(f'Timings: B commitment {result["base_seconds"]}s; nonce {result["nonce_seconds"]}s; bounded scan {result["bounded_scan_seconds"]}s', flush=True)
    print('No share submitted. No full-nonce or throughput claim. Miners and clocks unchanged.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError) as exc:
        print('STOP:', exc, flush=True)
        raise SystemExit(1)
