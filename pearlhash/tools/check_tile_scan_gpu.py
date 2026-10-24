#!/usr/bin/env python3
"""Bounded GPU tile search correctness; no nonce loop, pool IO or benchmark.

An already-scaled u256 bound is supplied for each tile. No difficulty/version
semantics are inferred. Candidate records carry a caller-chosen generation tag.
"""
import argparse
import ctypes as C
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import sys

BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from tools.check_mma_gpu import MatrixCase,scalar_reference
from tools.check_noise_mma_gpu import NoiseCase,NoiseMmaDevice,parse_noise_fixture,synthetic_cases

MAX_BOUND=(1<<256)-1


@dataclass(frozen=True)
class TileQuery:
    rows:tuple
    cols:tuple


def pack_queries(queries,pool_rows,pool_cols):
    if (not 1<=pool_rows<=32 or not 1<=pool_cols<=32 or not 1<=len(queries)<=64):
        raise ValueError('invalid bounded tile batch dimensions')
    words=[]
    for query in queries:
        for slots,limit in ((query.rows,pool_rows),(query.cols,pool_cols)):
            if (not 1<=len(slots)<=32 or any(type(i)is not int or not 0<=i<limit for i in slots)):
                raise ValueError('invalid tile row/column slots')
        words.extend((len(query.rows),len(query.cols)))
        words.extend((*query.rows,*([0]*(32-len(query.rows)))))
        words.extend((*query.cols,*([0]*(32-len(query.cols)))))
    return struct.pack(f'<{len(words)}I',*words)


def query_reference(matrix,queries):
    matrix.validate();pack_queries(queries,matrix.rows,matrix.cols)
    result=[]
    for query in queries:
        a=[v for row in query.rows for v in matrix.a[row*matrix.k:(row+1)*matrix.k]]
        bt=[v for col in query.cols for v in matrix.bt[col*matrix.k:(col+1)*matrix.k]]
        selected=MatrixCase('selected tile',len(query.rows),len(query.cols),matrix.k,matrix.rank,a,bt,matrix.key)
        _,words,digest=scalar_reference(selected);result.append((words,digest))
    return result


def validate_scan(bounds,capacity,generation):
    if (not 1<=len(bounds)<=64 or type(capacity)is not int or not 0<=capacity<=64
        or type(generation)is not int or not 0<=generation<=0xffffffffffffffff
        or any(type(bound)is not int or not 0<=bound<=MAX_BOUND for bound in bounds)):
        raise ValueError('invalid target, capacity or generation')


@dataclass
class ScanResult:
    total:int
    overflow:bool
    records:dict

    def require_complete(self):
        if self.overflow:raise RuntimeError('candidate queue overflow; batch must be retried with sufficient capacity')
        return self.records


def decode_candidates(raw,status,bounds,capacity,generation,reference):
    """Validate unordered GPU candidates against independent CPU tile digests."""
    validate_scan(bounds,capacity,generation)
    if len(raw)!=capacity*44 or len(status)!=8 or len(reference)!=len(bounds):
        raise ValueError('candidate/status length differs')
    total,overflow=struct.unpack('<2I',status)
    hits={i for i,((_,digest),bound)in enumerate(zip(reference,bounds))
          if int.from_bytes(digest,'little')<=bound}
    if total!=len(hits)or overflow!=int(total>capacity):
        raise ValueError('GPU hit count or overflow flag differs from CPU reference')
    records={}
    for offset in range(min(total,capacity)):
        start=offset*44;tile,lo,hi=struct.unpack_from('<3I',raw,start)
        digest=raw[start+12:start+44]
        if (tile not in hits or tile in records or (lo|(hi<<32))!=generation
            or digest!=reference[tile][1]):
            raise ValueError('invalid, duplicate or stale GPU candidate')
        records[tile]=digest
    if not overflow and set(records)!=hits:raise ValueError('GPU candidate set differs')
    return ScanResult(total,bool(overflow),records)


def tile_queries(rows,cols):
    # Full pool, reversed maps, padded/one-output tiles and duplicate slots.
    result=[TileQuery(tuple(range(rows)),tuple(range(cols))),
            TileQuery(tuple(reversed(range(rows))),tuple(range(cols-1,-1,-1))),
            TileQuery((rows-1,),(0,)),
            TileQuery(tuple(range(0,rows,2)),tuple(range(0,cols,2))),
            TileQuery((0,0,rows-1),(cols-1,0,cols-1))]
    pack_queries(result,rows,cols);return result


def scan_cases():
    yield from synthetic_cases()
    # Eight active warps, 33 prefix steps and many CTAs sharing the same inputs.
    k=1056;rank=32
    yield NoiseCase('eight-warp-tile',k,rank,list(range(32)),list(range(32)),
                    [((i*7+11)%129)-64 for i in range(32*k)],
                    [((i*13+3)%129)-64 for i in range(32*k)],bytes(range(32)),bytes(range(31,-1,-1)))


class TileScanner(NoiseMmaDevice):
    def scan(self,matrix,queries,reference,a,bt,key,bounds,capacity,generation,*,audit=False):
        validate_scan(bounds,capacity,generation)
        descriptors=pack_queries(queries,matrix.rows,matrix.cols)
        if len(bounds)!=len(queries)or len(reference)!=len(queries):
            raise ValueError('tile/target/reference count differs')
        mark=len(self.allocations)
        try:
            desc=self.allocate(descriptors)
            limits=self.allocate(b''.join(value.to_bytes(32,'little')for value in bounds))
            status,s=self.guarded(8)
            zero=C.create_string_buffer(bytes(8),8)
            self.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],s,zero,8)
            queue,q=self.guarded(capacity*44)
            trace,t=self.guarded(len(queries)*64 if audit else 0)
            arguments=(a,bt,desc,limits,key,s,q,t,C.c_uint(audit),C.c_uint(capacity),
                       C.c_uint(len(queries)),C.c_uint(matrix.rows),C.c_uint(matrix.cols),
                       C.c_uint(matrix.k),C.c_uint(matrix.rank),C.c_ulonglong(generation))
            self.launch(b'tile_scan',arguments,len(queries),256)
            self.api('cuCtxSynchronize',[])
            result=decode_candidates(self.checked_download(queue,capacity*44),
                self.checked_download(status,8),bounds,capacity,generation,reference)
            words=self.checked_download(trace,len(queries)*64 if audit else 0)
            if audit and words!=b''.join(item[0]for item in reference):
                raise RuntimeError('GPU in-kernel transcript differs from scalar CPU reference')
            return result
        finally:
            for pointer in reversed(self.allocations[mark:]):self.release(pointer)

    def exercise(self,case,matrix,queries,reference):
        mark=len(self.allocations)
        try:
            a,key=self.generate_side(case,case.sides()[0],matrix.a)
            bt,_=self.generate_side(case,case.sides()[1],matrix.bt)
            digests=[int.from_bytes(d,'little')for _,d in reference];count=len(queries)
            checks=(('all hits + transcript audit',[MAX_BOUND]*count,count,True),
                    ('digest minus one',[max(0,d-1)for d in digests],count,False),
                    ('digest equality',digests,count,False),
                    ('digest plus one',[min(MAX_BOUND,d+1)for d in digests],count,False),
                    ('zero bound',[0]*count,count,False),
                    ('mixed bounds',[MAX_BOUND if i%2 else 0 for i in range(count)],count,False),
                    ('overflow one slot',[MAX_BOUND]*count,1,False),
                    ('overflow zero slots',[MAX_BOUND]*count,0,False))
            for index,(label,bounds,capacity,audit)in enumerate(checks):
                result=self.scan(matrix,queries,reference,a,bt,key,bounds,capacity,
                                 0xfedcba9801020304+index,audit=audit)
                if result.overflow:
                    try:result.require_complete()
                    except RuntimeError:pass
                    else:raise RuntimeError('overflow was silently accepted')
                else:result.require_complete()
            print(f'PASS: GPU tile scan: {case.name}; {count} tiles x {len(checks)} target/queue checks; '
                  'digests, transcript audit, generation tags and guards match',flush=True)
        finally:
            for pointer in reversed(self.allocations[mark:]):self.release(pointer)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,help='optional LOCAL PHGPU02 input')
    parser.add_argument('--cubin',type=Path,default=BASE/'gpu/tile-scan-sm120.cubin')
    parser.add_argument('--report',type=Path,help='new local completion report')
    parser.add_argument('--cpu-only',action='store_true')
    args=parser.parse_args()
    if args.report and (args.report.exists()or not args.report.parent.is_dir()):
        raise ValueError('report already exists or its parent directory is missing')
    cases=list(scan_cases())
    if args.fixture:
        if args.fixture.stat().st_size>8*1024*1024:raise ValueError('local fixture exceeds 8 MiB')
        cases.append(parse_noise_fixture(args.fixture.read_bytes()))
    prepared=[]
    for case in cases:
        matrix=case.matrix();scalar_reference(matrix) # Also check the local file's saved math.
        queries=tile_queries(matrix.rows,matrix.cols)
        prepared.append((matrix,queries,query_reference(matrix,queries)))
    if args.cpu_only:
        print(f'CPU-ONLY: prepared {len(cases)} tile batches; GPU not run',flush=True)
    else:
        device=TileScanner()
        try:
            device.start(args.cubin)
            for case,(matrix,queries,reference)in zip(cases,prepared):
                device.exercise(case,matrix,queries,reference)
        finally:device.close()
    if args.report:
        with args.report.open('x')as out:
            json.dump({'complete':True,'gpu_checked':not args.cpu_only,'batches':len(cases),
                       'tiles_per_batch':5,'checks_per_batch':8,
                       'scope':'bounded offline GPU tile scan; no full nonce/job search, pool submission or performance claim'},out,indent=2)
    print('Bounded offline tile search only; supplied seeds/signals/scaled bounds. No pool submission or performance claim.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError)as error:
        print('FAIL:',error);raise SystemExit(1)
