#!/usr/bin/env python3
"""Offline global-batch cancellation/retry checks using the existing v17 PTX. ISC."""
import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from reference.native_hash import small_hash
from reference.patterns import PeriodicPattern
from reference.pool_nonce import nonce_tail
from reference.tile_ranges import PatternDomain, RangeCursor, run_range
from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import MAX_BOUND
from tools.global_range import GlobalRangeBackend, GlobalRangePlan
from tools.virtual_scan import VirtualScanner


def profiles():
    a = small_hash(b'pearlhash/global-range/v018/A')
    b = small_hash(b'pearlhash/global-range/v018/B')
    tail = nonce_tail(bytes(range(8)), bytes(range(8, 16)))
    profile = ConstantProfile(3, 70, 1024, 32, 64, tail, a, b)
    single = PeriodicPattern(bytes(6))
    plan = GlobalRangePlan(PatternDomain(profile.m, single), PatternDomain(profile.n, single))
    yield '64-query-global-batches', profile, plan, 80, 210
    profile = ConstantProfile(5121, 262144, 32768, 128, 64, tail, a, b)
    rows = PeriodicPattern.from_list([0, 1, 8, 9, 16, 17, 24, 25, 32, 33])
    cols = PeriodicPattern.from_list([0, 1, 8, 9, 32, 33, 40, 41, 64, 65, 72, 73, 96, 97, 104, 105])
    plan = GlobalRangePlan(PatternDomain(profile.m, rows), PatternDomain(profile.n, cols))
    if plan.count != 8388608:
        raise RuntimeError('production domain size differs')
    # Two adjacent global IDs cross an A-pattern row boundary. Not a full nonce.
    yield 'production-row-boundary', profile, plan, plan.b.count - 1, plan.b.count + 1


def exercise(profile, plan, start, stop, device, *, cancellation):
    backend = GlobalRangeBackend(profile, device)
    cursor = RangeCursor(0x1800000012345678, start, stop)
    current = [cursor.generation]
    seen = {}

    def deliver(records):
        for tile, digest, generation in records:
            if tile in seen or generation != cursor.generation:
                raise RuntimeError('duplicate or stale global candidate')
            seen[tile] = digest
        if cancellation and cursor.batches_done == 0:
            current[0] += 1

    try:
        tables = backend.tables
        run_range(plan, cursor, backend, lambda: current[0], deliver)
        if cancellation:
            if cursor.status != 'cancelled' or cursor.next_tile != start + 64:
                raise RuntimeError('global range cancellation checkpoint differs')
            current[0] = cursor.generation
            run_range(plan, cursor, backend, lambda: current[0], deliver)
        if (cursor.status != 'complete' or cursor.next_tile != stop
                or set(seen) != set(range(start, stop))
                or backend.reference_batches != cursor.batches_done
                or backend.tables is not tables or cursor.retries == 0):
            raise RuntimeError('global range coverage/cache/retry check failed')

        # Change generation after a completed launch but before delivery. Its
        # results must be discarded and the cursor must remain at batch start.
        stale = RangeCursor(cursor.generation, start, min(start + 2, stop))
        delivered = []
        def invalidate(batch, capacity, generation):
            result = backend(batch, capacity, generation)
            current[0] = generation + 1
            return result
        run_range(plan, stale, invalidate, lambda: current[0], delivered.extend)
        if stale.status != 'cancelled' or stale.next_tile != start or delivered:
            raise RuntimeError('stale in-flight batch was delivered or committed')
        current[0] = stale.generation
        run_range(plan, stale, backend, lambda: current[0], delivered.extend)
        if stale.status != 'complete' or {r[0] for r in delivered} != set(range(start, stale.stop)):
            raise RuntimeError('stale global batch did not resume completely')

        return {'tiles_checked': stop - start, 'batch_sizes':
                [len(batch.maps) for batch in plan.batches(start, stop)],
                'overflow_retries': cursor.retries, 'cancel_resume_checked': cancellation,
                'stale_inflight_discard_resume_checked': True, 'gpu_checked': device is not None}
    finally:
        backend.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--cpu-only', action='store_true')
    args = parser.parse_args()
    if args.report.exists() or not args.report.parent.is_dir():
        raise ValueError('report exists or parent directory is missing')
    device = None
    checks = []
    try:
        if not args.cpu_only:
            device = VirtualScanner()
            device.start(args.module)
        for name, profile, plan, start, stop in profiles():
            print(f'Checking {name}: {stop-start} tiles; one reusable noise cache...', flush=True)
            result = exercise(profile, plan, start, stop, device,
                              cancellation=(name == '64-query-global-batches'))
            result['name'] = name
            checks.append(result)
            mode = 'CPU-ONLY' if args.cpu_only else 'PASS'
            print(f'{mode}: {name}: batches {result["batch_sizes"]}; CPU references, '
                  'overflow retry, global IDs and stale-result discard/resume checked', flush=True)
            if device is not None and device.allocations:
                raise RuntimeError('global range test leaked device allocations')
    finally:
        if device is not None:
            device.close()
    with args.report.open('x') as out:
        json.dump({'complete': True, 'gpu_checked': not args.cpu_only, 'checks': checks,
                   'kernel': 'unchanged v0.0.17 source/PTX',
                   'scope': 'bounded synthetic global-batch checks; CPU references every tile; '
                            'no full production nonce, new proof check, pool submission or performance claim'},
                  out, indent=2)
        out.write('\n')
    print('Completion saved. No pool connection or performance claim.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print('FAIL:', error, flush=True)
        raise SystemExit(1)
