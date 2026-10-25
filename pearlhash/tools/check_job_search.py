#!/usr/bin/env python3
"""Fresh synthetic PoolSession job -> GPU search -> independently verified proof.

No network or submissions; supplied worker nonce has no asserted extranonce role.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
from pool.job import _HEADER_MASK, _SCRAMBLE_KEY
from pool.search import StaleWork, prepare_base, prepare_nonce, search_nonce, build_proof
from pool.session import MiningProfile, PoolSession
from reference.patterns import PeriodicPattern
from tools.candidate_scan import CandidateScanner
from tools.offline_nonce_search import make_job


def synthetic_session(seed):
    pattern = PeriodicPattern.from_list([0, 1, 8, 9, 64, 65, 72, 73])
    # Different dimensions from the old 128x128 synthetic search: no hidden
    # dependency on that test's global matrix dimensions or hardcoded bound.
    profile = MiningProfile(160, 192, 4096, 128, pattern, pattern)
    session = PoolSession(profile, cert_version=3)
    header = make_job(seed, 3).header
    payload = bytes(v ^ _HEADER_MASK[i] ^ _SCRAMBLE_KEY[i % 32] for i, v in enumerate(header)) + bytes(124)
    message = {'id': -1, 'status': 1, 'result': ['notify', payload.hex(),
               (1 << 236).to_bytes(32, 'little').hex(), bytes(8).hex(), '3']}
    session.consume({'id': 0, 'status': 1, 'result': True})
    session.consume({'id': -1, 'status': 1, 'result': ['extranonce', bytes(8).hex()]})
    job = session.consume(message)
    return session, job, message


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--oracle', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--cpu-only', action='store_true')
    args = parser.parse_args()
    if not args.cpu_only and (args.oracle is None or not os.access(args.oracle, os.X_OK)):
        raise ValueError('existing official CPU verifier required')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    session, job, message = synthetic_session(secrets.token_bytes(32))
    print('Preparing fresh 160x192 V3 job through PoolSession and the new job-driven engine...', flush=True)
    base = prepare_base(job, session.is_current)
    device = None
    found = None
    try:
        if not args.cpu_only:
            device = CandidateScanner()
            device.start(args.module)
        for attempt in range(4):
            # Explicit independent test worker; deliberately differs from the
            # synthetic assigned extranonce. No live nonce mapping is inferred.
            context = prepare_nonce(job, base, b'TESTWORK', attempt.to_bytes(8, 'little'), session.is_current)
            found, cursor = search_nonce(context, device, session.is_current)
            if found is not None:
                break
        if found is None:
            raise RuntimeError('bounded synthetic search found no candidate')
        proof, _ = build_proof(context, found, session.is_current)
        proof_path = args.output_dir/'job-proof-v3.json'
        proof_path.write_text(json.dumps({'cert_version': 3,
            'header_base64': base64.b64encode(job.header).decode(),
            'plain_proof_base64': base64.b64encode(proof).decode(), 'share_nbits': None})+'\n')
        if args.oracle:
            subprocess.run([str(args.oracle.resolve()), 'verify', str(proof_path.resolve())],
                           check=True, timeout=120, env=dict(os.environ, RAYON_NUM_THREADS='2'))
        print('PASS: job profile/target -> fresh nonce -> '+('CPU-emulated' if args.cpu_only else 'GPU')+
              ' candidate -> independent V3 proof'+(' -> official verifier' if args.oracle else ' (oracle not run)'), flush=True)
        # Replace only the target; the old work must fail at the engine boundary.
        message['result'][2] = (1 << 235).to_bytes(32, 'little').hex()
        replacement = session.consume(message)
        if replacement.job_key != job.job_key or replacement.share_bound*2 != job.share_bound:
            raise RuntimeError('controlled target replacement differs')
        for action in (lambda: prepare_nonce(job, base, b'TESTWORK', bytes(8), session.is_current),
                       lambda: search_nonce(context, device, session.is_current),
                       lambda: build_proof(context, found, session.is_current)):
            try:
                action()
            except StaleWork:
                continue
            raise RuntimeError('stale job entered a search/proof stage')
        print('PASS: target replacement rejects the old nonce, search and proof stages', flush=True)
        report = {'complete': True, 'gpu_checked': not args.cpu_only,
                  'official_cpu_verifier': 'passed' if args.oracle else 'not run',
                  'profile': {'m': 160, 'n': 192, 'k': 4096, 'rank': 128},
                  'tiles_scanned': cursor.next_tile, 'stale_stages_rejected': 3,
                  'gpu_candidate_checks': device.verified_tiles if device else None,
                  'pool_connection': False, 'submitted_shares': 0,
                  'extranonce_worker_role_verified': False,
                  'scope': 'new job-driven engine with synthetic session; no live mining verdict'}
        (args.output_dir/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    finally:
        session.close()
        if device:
            device.close()
    print('Completion saved. Miners, services and clocks unchanged.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('STOP:', exc, flush=True)
        raise SystemExit(1)
