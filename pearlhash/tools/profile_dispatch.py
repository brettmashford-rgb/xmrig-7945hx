#!/usr/bin/env python3
"""Offline dispatch profiling of already-validated kernels. ISC license.

Host buckets are exclusive wall times. GPU event intervals overlap host waiting
and MUST NOT be added to those buckets. Event intervals can include scheduling
or host submission gaps; they are not GPU instruction-cycle measurements.
No pool connection, proofs, live inputs, service changes or mining-rate claim.
"""
import argparse
from collections import defaultdict
import ctypes as C
import json
import os
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
from tools.cached_scan import CachedCandidateScanner
from tools.cooperative_scan import CooperativeCache, cooperative_queries
from tools.virtual_scan import VirtualTables
from tools.check_production_gpu import cases
from reference.patterns import PeriodicPattern
from reference.tile_ranges import PatternDomain


def bucket(name):
    return {'cuMemAlloc_v2': 'allocation', 'cuMemFree_v2': 'free',
            'cuMemcpyHtoD_v2': 'upload', 'cuMemcpyDtoH_v2': 'download',
            'cuCtxSynchronize': 'synchronize_wait',
            'cuLaunchKernel': 'launch_api'}.get(name, 'other_driver')


def summarize(wall, host, counts, gpu):
    # GPU is a second, overlapping clock, deliberately outside host_seconds.
    remaining = wall - sum(host.values())
    if remaining < -1e-6:
        raise RuntimeError('overlapping host profiling buckets')
    return {'wall_seconds': wall,
            'host_seconds': {**host, 'python_and_bookkeeping': max(0., remaining)},
            'api_counts': dict(counts), 'gpu_event_seconds': gpu}


class ProfileScanner(CachedCandidateScanner):
    def __init__(self):
        super().__init__()
        self.profiling = False
        self.events = []
        self.host = defaultdict(float)
        self.counts = defaultdict(int)
        self.launches = 0

    def event_api(self, name, types, *args):
        # Bypass this profiler to prevent recursive/double-counted buckets.
        return super().api(name, types, *args)

    def create_events(self):
        for _ in range(2):
            event = C.c_void_p()
            self.event_api('cuEventCreate', [C.POINTER(C.c_void_p), C.c_uint], C.byref(event), 0)
            self.events.append(event)

    def record(self, event):
        started = time.perf_counter()
        self.event_api('cuEventRecord', [C.c_void_p, C.c_void_p], event, None)
        self.host['event_instrumentation'] += time.perf_counter() - started

    def api(self, name, types, *args):
        if not self.profiling:
            return super().api(name, types, *args)
        if name == 'cuLaunchKernel':
            if self.launches:
                raise RuntimeError('expected exactly one kernel per measured dispatch')
            self.launches += 1
            self.record(self.events[0])
        started = time.perf_counter()
        try:
            return super().api(name, types, *args)
        finally:
            self.host[bucket(name)] += time.perf_counter() - started
            self.counts[name] += 1
            if name == 'cuLaunchKernel':
                self.record(self.events[1])

    def measure(self, operation):
        self.host.clear(); self.counts.clear(); self.launches = 0
        started = time.perf_counter()
        self.profiling = True
        try:
            result = operation()
        finally:
            self.profiling = False
        wall = time.perf_counter() - started
        if self.launches != 1:
            raise RuntimeError('measured dispatch did not launch exactly one kernel')
        # Existing scan synchronizes before download and return. Explicit event
        # completion check also makes this safe if scan internals later change.
        self.event_api('cuEventSynchronize', [C.c_void_p], self.events[1])
        elapsed = C.c_float()
        self.event_api('cuEventElapsedTime', [C.POINTER(C.c_float), C.c_void_p, C.c_void_p],
                       C.byref(elapsed), *self.events)
        return result, summarize(wall, dict(self.host), self.counts, elapsed.value / 1000.)

    def close(self):
        try:
            for event in self.events:
                self.event_api('cuEventDestroy_v2', [C.c_void_p], event)
        finally:
            self.events.clear()
            super().close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    device = tables = cache = None
    report = {'complete': False, 'submitted_shares': 0, 'rounds': {},
              'scope': 'repeated synthetic dispatch profiling; no mining throughput or pool verdict',
              'gpu_clock_note': 'CUDA event interval overlaps host waits; do not sum with host buckets'}
    error = None
    try:
        device = ProfileScanner(); device.start(args.module); device.create_events()
        profile = list(cases())[1][1]
        ad = PatternDomain(profile.m, PeriodicPattern(bytes.fromhex('000103040000')))
        bd = PatternDomain(profile.n, PeriodicPattern(bytes.fromhex('000103010103')))
        queries = cooperative_queries(tuple(ad.indices(i*(ad.count-1)//31) for i in range(32)),
                                      tuple(bd.indices(j*(bd.count-1)//127) for j in range(128)))
        started = time.perf_counter(); tables = VirtualTables(device, profile)
        report['noise_setup_seconds'] = time.perf_counter()-started
        started = time.perf_counter(); cache = CooperativeCache(tables, queries)
        report['materialization_seconds'] = time.perf_counter()-started
        report['cache_bytes'] = cache.bytes
        bounds = [0]*len(queries)
        def scan(label, generation, audit=False):
            if label == 'virtual':
                return device.scan_wide(tables, queries, bounds, 0, generation, audit=audit)
            cache.selected_scan_kernel = (b'cooperative_tile_scan' if label == 'cooperative'
                                          else b'fragment_cached_tile_scan')
            return device.scan_cached(cache, queries, bounds, 0, generation, audit=audit)
        labels = ('virtual', 'fragment', 'cooperative')
        transcript = None
        for label in labels:
            result = scan(label, (1<<63)+34, audit=True)
            if result.total or result.overflow:
                raise RuntimeError('unexpected zero-target candidate')
            if transcript is None:
                transcript = device.last_transcripts
            elif device.last_transcripts != transcript:
                raise RuntimeError('profiling path transcript mismatch')
        print('PASS: full 4096-tile transcripts match across all three paths.', flush=True)
        report['transcripts_match'] = True
        for repeat in range(8):
            order = labels[repeat%3:]+labels[:repeat%3]
            for label in order:
                # Alternate paired order to expose instrumentation disturbance.
                pair = {}
                modes = ('profiled', 'plain') if repeat%2 == 0 else ('plain', 'profiled')
                for mode in modes:
                    if mode == 'profiled':
                        result, measured = device.measure(lambda: scan(label, repeat))
                        pair.update(measured)
                    else:
                        started = time.perf_counter(); result = scan(label, repeat)
                        pair['plain_wall_seconds'] = time.perf_counter()-started
                    if result.total or result.overflow:
                        raise RuntimeError('unexpected timing candidate')
                report['rounds'].setdefault(label, []).append(pair)
            print('Profiling round '+str(repeat+1)+'/8 complete.', flush=True)
        for label, records in report['rounds'].items():
            host = {key: sum(r['host_seconds'].get(key, 0.) for r in records)
                    for key in {k for r in records for k in r['host_seconds']}}
            summary = {'wall_seconds': sum(r['wall_seconds'] for r in records),
                       'plain_wall_seconds': sum(r['plain_wall_seconds'] for r in records),
                       'gpu_event_seconds': sum(r['gpu_event_seconds'] for r in records),
                       'host_seconds': host, 'queries_per_round': len(queries), 'rounds': len(records)}
            report.setdefault('summary', {})[label] = summary
            print('PROFILE '+label+': '+json.dumps(summary, sort_keys=True), flush=True)
        report['complete'] = True
    except (OSError, ValueError, RuntimeError) as exc:
        error = type(exc).__name__+': '+str(exc)
    finally:
        # A cleanup failure must not hide the original measurement failure.
        for resource in (cache, tables, device):
            if resource is not None:
                try: resource.close()
                except Exception as exc:
                    error = error or ('cleanup: '+str(exc))
        report['error'] = error
        report['complete'] = report['complete'] and error is None
        with os.fdopen(fd, 'w') as output:
            json.dump(report, output, indent=2); output.write('\n')
    if error:
        print('STOP: '+error, flush=True); return 1
    print('Profiling complete. No pool connection or shares sent.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
