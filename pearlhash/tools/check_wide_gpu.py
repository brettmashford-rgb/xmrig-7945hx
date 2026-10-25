#!/usr/bin/env python3
"""Check large grids/queues against independent bounded CPU references. ISC."""
import argparse
import json
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path: sys.path.insert(0, str(BASE))
from reference.native_hash import small_hash
from reference.pool_nonce import nonce_tail
from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import MAX_BOUND, TileQuery
from tools.virtual_scan import VirtualTables, global_reference
from tools.wide_scan import WideCandidateScanner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    fd = os.open(args.report, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    device = None; tables = None; results = []; error = None
    try:
        profile = ConstantProfile(3, 7, 1024, 32, 64, nonce_tail(b'TESTWORK', bytes(8)),
                                  small_hash(b'wide/v025/A'), small_hash(b'wide/v025/B'))
        unique = (TileQuery((0,), (0,)), TileQuery((2,), (6,)),
                  TileQuery((0,2), (1,6)), TileQuery((0,1,2), (0,3,6)))
        reference = dict(zip(unique, (d for _,d in global_reference(profile, unique))))
        queries = tuple(unique[i%4] for i in range(4096))
        mixed = [int.from_bytes(reference[q], 'little') if i%2 == 0 else 0
                 for i,q in enumerate(queries)]
        scenarios = [('all-hit-max-grid', queries, [MAX_BOUND]*4096, 4096),
                     ('all-miss-zero-queue', queries, [0]*4096, 0),
                     ('mixed-overflow', queries, mixed, 1),
                     ('mixed-complete', queries, mixed, 4096),
                     ('partial-grid-zero-queue', queries[:67], [MAX_BOUND]*67, 0)]
        device = WideCandidateScanner(); device.start(args.module)
        tables = VirtualTables(device, profile)
        for name, qs, bounds, capacity in scenarios:
            expected = {i:reference[q] for i,q in enumerate(qs)
                        if int.from_bytes(reference[q], 'little') <= bounds[i]}
            checked_before = device.verified_tiles
            result = device.scan_wide(tables, qs, bounds, capacity, (1<<63)+17)
            if result.total != len(expected) or result.overflow != (len(expected)>capacity):
                raise RuntimeError('wide GPU count/overflow differs from independent CPU set')
            if result.overflow:
                if len(result.records) != capacity or any(expected.get(i)!=d for i,d in result.records.items()):
                    raise RuntimeError('wide partial GPU queue differs')
                if device.verified_tiles != checked_before:
                    raise RuntimeError('partial queue was treated as a complete candidate set')
            elif result.records != expected:
                raise RuntimeError('wide complete GPU hit set differs')
            results.append({'name':name,'queries':len(qs),'capacity':capacity,
                            'hits':result.total,'overflow':result.overflow})
            print(f'PASS: {name}; {len(qs)} queries; {result.total} hits; overflow={result.overflow}; guards unchanged', flush=True)
    except (OSError, ValueError, RuntimeError) as exc:
        error = type(exc).__name__+': '+str(exc)
    finally:
        if tables: tables.close()
        if device: device.close()
        with os.fdopen(fd,'w') as output:
            json.dump({'complete':error is None,'gpu_checked':device is not None and error is None,
                       'cases':results,'error':error,'submitted_shares':0,
                       'scope':'large-dispatch correctness using four independent small CPU references; not mining throughput'},output,indent=2)
            output.write('\n')
    if error: print('STOP:',error,flush=True);return 1
    print('Wide-grid checks complete; no pool connection or submission.',flush=True)
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print('STOP:',exc,flush=True);raise SystemExit(1)
