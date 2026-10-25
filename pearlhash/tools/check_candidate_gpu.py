#!/usr/bin/env python3
"""Offline candidate-only search checks plus a fresh V3 proof. ISC. No pool IO."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from reference.native_hash import small_hash
from reference.patterns import PeriodicPattern
from reference.pool_nonce import nonce_tail
from reference.tile_ranges import PatternDomain
from tools.candidate_scan import CandidateScanner, decode_queue, find_nonce_candidate, verify_returned
from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import MAX_BOUND
from tools.global_range import GlobalRangePlan
from tools.offline_nonce_search import make_job, prepare_base, prepare_nonce, build_candidate
from tools.virtual_scan import VirtualTables, global_reference


def cases():
    a = small_hash(b'pearlhash/candidate/v019/A')
    b = small_hash(b'pearlhash/candidate/v019/B')
    tail = nonce_tail(bytes(range(8)), bytes(range(8, 16)))
    single = PeriodicPattern(bytes(6))
    profile = ConstantProfile(3, 70, 1024, 32, 64, tail, a, b)
    plan = GlobalRangePlan(PatternDomain(3, single), PatternDomain(70, single))
    yield '64-global-queries', profile, next(plan.batches(80, 144)).queries()
    rows = PeriodicPattern.from_list([0, 1, 8, 9, 16, 17, 24, 25, 32, 33])
    cols = PeriodicPattern.from_list([0, 1, 8, 9, 32, 33, 40, 41, 64, 65, 72, 73, 96, 97, 104, 105])
    profile = ConstantProfile(5121, 262144, 32768, 128, 64, tail, a, b)
    plan = GlobalRangePlan(PatternDomain(profile.m, rows), PatternDomain(profile.n, cols))
    yield 'production-row-boundary', profile, next(plan.batches(plan.b.count - 1, plan.b.count + 1)).queries()


def emulated_queue(reference, bounds, capacity, generation):
    # Development CPU emulation only, never a GPU/candidate-only-work claim.
    hits = {i: digest for i, (_, digest) in enumerate(reference)
            if int.from_bytes(digest, 'little') <= bounds[i]}
    raw = b''.join(struct.pack('<IQ', tile, generation) + digest
                   for tile, digest in list(hits.items())[:capacity])
    raw += bytes(capacity * 44 - len(raw))
    return decode_queue(raw, struct.pack('<2I', len(hits), int(len(hits) > capacity)),
                        bounds, capacity, generation)


def check_case(device, name, profile, queries):
    # The TEST harness computes every reference to detect missed GPU hits.
    # CandidateScanner itself sees only descriptors/targets, not these references.
    reference = global_reference(profile, queries)
    digests = [int.from_bytes(digest, 'little') for _, digest in reference]
    if any(digest == 0 for digest in digests):
        raise RuntimeError('test profile unexpectedly has a zero digest')
    n = len(queries)
    scenarios = [('all-hits', [MAX_BOUND]*n, n), ('no-hits', [0]*n, n),
                 ('mixed', [MAX_BOUND if i % 2 else 0 for i in range(n)], n),
                 ('inclusive-equality', digests, n),
                 ('digest-minus-one', [value-1 for value in digests], n),
                 ('overflow-one', [MAX_BOUND]*n, 1), ('overflow-zero', [MAX_BOUND]*n, 0)]
    tables = VirtualTables(device, profile) if device is not None else None
    checks = []
    try:
        for index, (label, bounds, capacity) in enumerate(scenarios):
            generation = 0x1900000012345678 + index
            verified_before = device.verified_tiles if device is not None else 0
            if device is not None:
                result = device.scan_candidates(tables, queries, bounds, capacity, generation)
                verified = device.verified_tiles - verified_before
            else:
                result = emulated_queue(reference, bounds, capacity, generation)
                verified = verify_returned(result, queries,
                    lambda query: global_reference(profile, (query,))[0][1])
            expected = {i: digest for i, (_, digest) in enumerate(reference)
                        if int.from_bytes(digest, 'little') <= bounds[i]}
            overflow = len(expected) > capacity
            if (result.total != len(expected) or result.overflow != overflow
                    or len(result.records) != min(len(expected), capacity)
                    or any(expected.get(i) != digest for i, digest in result.records.items())
                    or verified != (0 if overflow else len(expected))):
                raise RuntimeError('candidate queue or verification count differs from full CPU reference')
            if overflow:
                try:
                    result.require_complete()
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError('partial candidate queue was accepted')
            elif result.require_complete() != expected:
                raise RuntimeError('complete GPU candidate set differs from CPU reference')
            checks.append({'scenario': label, 'hits': result.total,
                           'verified_returned_tiles': verified, 'overflow': overflow})
        mode = 'PASS' if device is not None else 'CPU-ONLY'
        print(f'{mode}: {name}: {n} queries x 7 queue/target cases; complete hit sets match; '
              'zero CPU candidate recomputations for misses or partial queues', flush=True)
        return {'name': name, 'queries': n, 'gpu_checked': device is not None, 'checks': checks}
    finally:
        if tables is not None:
            tables.close()


def fresh_proof(device, oracle, out):
    seed = secrets.token_bytes(32)
    job = make_job(seed, 3)
    base = prepare_base(job)
    worker = secrets.token_bytes(8)
    found = None
    before = device.verified_tiles if device is not None else 0
    for attempt in range(3):
        context = prepare_nonce(job, base, worker, secrets.token_bytes(8), 19 + attempt)
        found, cursor = find_nonce_candidate(context, device)
        if found is not None:
            break
    if found is None:
        raise RuntimeError('bounded fresh nonce search found no candidate')
    proof, _ = build_candidate(context, found)
    path = out / 'candidate-proof-v3.json'
    value = {'cert_version': 3, 'header_base64': base64.b64encode(job.header).decode(),
             'plain_proof_base64': base64.b64encode(proof).decode(), 'share_nbits': None,
             'provenance': {'scope': 'fresh synthetic candidate-only-search proof; no pool verdict',
                            'synthetic_seed_hex': seed.hex(), 'worker_nonce': context.worker.hex(),
                            'miner_nonce': context.miner.hex(), 'generation': context.generation,
                            'tile_id': found.tile}}
    path.write_text(json.dumps(value, indent=2) + '\n')
    if oracle is not None:
        subprocess.run([str(oracle), 'verify', str(path)], check=True, timeout=120,
                       env=dict(os.environ, RAYON_NUM_THREADS='2'))
        print('PASS: fresh V3 candidate-only GPU search -> independent proof -> official offline verifier', flush=True)
    else:
        print('CPU-ONLY: fresh V3 search/proof prepared; GPU and official verifier NOT RUN', flush=True)
    return {'tiles_scanned': cursor.next_tile, 'tile_id': found.tile,
            'gpu_candidate_tiles_cpu_verified': device.verified_tiles-before if device is not None else None,
            'official_cpu_verifier': 'passed' if oracle is not None else 'not run'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--oracle', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--cpu-only', action='store_true')
    args = parser.parse_args()
    oracle = args.oracle.resolve() if args.oracle else None
    if (not args.cpu_only and oracle is None) or (oracle is not None and
            (not oracle.is_file() or not os.access(oracle, os.X_OK))):
        raise ValueError('existing official CPU verifier executable is required')
    if args.output_dir.exists():
        raise ValueError('output directory already exists')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    device = None
    checks = []
    try:
        if not args.cpu_only:
            device = CandidateScanner()
            device.start(args.module)
        for name, profile, queries in cases():
            print(f'Checking candidate-only dispatch: {name}...', flush=True)
            checks.append(check_case(device, name, profile, queries))
        print('Checking a fresh nonce/proof through the NEW candidate-only search path...', flush=True)
        proof = fresh_proof(device, oracle, args.output_dir)
        if device is not None and device.allocations:
            raise RuntimeError('candidate search leaked device allocations')
    finally:
        if device is not None:
            device.close()
    manifest = {'complete': True, 'gpu_checked': not args.cpu_only, 'checks': checks,
                'fresh_v3': proof, 'official_cpu_verifier': proof['official_cpu_verifier'],
                'kernel': 'unchanged v0.0.17 PTX',
                'scope': 'candidate-only CPU validation in GPU search; full-reference harness checks; '
                         'fresh synthetic V3 proof; no pool submission or performance claim'}
    (args.output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Completion saved. Offline only; no full production nonce or pool verdict.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('FAIL:', error, flush=True)
        raise SystemExit(1)
