#!/usr/bin/env python3
"""GPU table noise -> signed bytes -> integer MMA, offline correctness only.

Seeds and selected signal rows are supplied. No private data is uploaded, and
there is no network, job search, target test, submission or performance claim.
"""
import argparse
import ctypes as C
from dataclasses import dataclass
from itertools import chain
import json
from pathlib import Path
import random
import struct
import sys

BASE=Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:sys.path.insert(0,str(BASE))
from reference.dense import _random_hash,noise_rows
from tools.check_mma_gpu import MatrixCase,MmaDevice,parse_fixture,scalar_reference


@dataclass
class NoiseCase:
    name:str
    k:int
    rank:int
    indices_a:list
    indices_b:list
    signal_a:list
    signal_b:list
    seed_a:bytes
    seed_b:bytes
    fixture:MatrixCase|None=None

    def validate(self):
        if (type(self.k)is not int or type(self.rank)is not int
            or not 32<=self.rank<=1024 or self.rank&(self.rank-1)
            or not 0<self.k<=65536 or self.k%self.rank
            or not 1<=len(self.indices_a)<=32 or not 1<=len(self.indices_b)<=32
            or len(self.signal_a)!=len(self.indices_a)*self.k
            or len(self.signal_b)!=len(self.indices_b)*self.k
            or any(type(seed)is not bytes or len(seed)!=32 for seed in (self.seed_a,self.seed_b))
            or any(type(i)is not int or not 0<=i<=0xffffffff//self.rank
                   for i in chain(self.indices_a,self.indices_b))
            or any(type(v)is not int or not -64<=v<=64 for v in chain(self.signal_a,self.signal_b))):
            raise ValueError('invalid bounded noise input')

    def matrix(self):
        self.validate();values=[]
        for indices,signals,seed,label in self.sides():
            noise=noise_rows(self.k,self.rank,indices,label,seed)
            values.append([s+n for s,n in zip(signals,chain.from_iterable(noise),strict=True)])
        matrix=MatrixCase(self.name,len(self.indices_a),len(self.indices_b),self.k,self.rank,
                          values[0],values[1],self.seed_a)
        matrix.validate()
        if self.fixture:
            if matrix.a!=self.fixture.a or matrix.bt!=self.fixture.bt:
                raise ValueError('generated CPU noise differs from local fixture matrices')
            matrix.fixture_words=self.fixture.fixture_words
            matrix.fixture_digest=self.fixture.fixture_digest
        return matrix

    def sides(self):
        return ((self.indices_a,self.signal_a,self.seed_a,b'A_tensor'),
                (self.indices_b,self.signal_b,self.seed_b,b'B_tensor'))


def reference_tables(indices,k,rank,label,key):
    """CPU table bytes, using the independent CPU BLAKE3 implementation."""
    uniform=bytes((v&63)-32 & 255 for row in indices
        for block in range(row*(rank//32),(row+1)*(rank//32))
        for v in _random_hash(block,label,key,0))
    pairs=[]
    for block in range(k//8):
        for value in struct.unpack('<8I',_random_hash(block,label,key,1)):
            first=value&(rank-1);second=first^(1+(((rank-1)*value)>>32))
            pairs.append(first|(second<<16))
    return uniform,struct.pack(f'<{k}I',*pairs)


def parse_noise_fixture(raw):
    fixture=parse_fixture(raw);rows,cols,k,rank=fixture.rows,fixture.cols,fixture.k,fixture.rank
    size=(rows+cols)*k*4;pos=24+size+64
    seed_a,seed_b=raw[pos:pos+32],raw[pos+32:pos+64];pos+=64
    indices=struct.unpack_from(f'<{rows+cols}I',raw,pos);pos+=(rows+cols)*4
    signals=list(struct.unpack_from(f'<{(rows+cols)*k}i',raw,pos))
    case=NoiseCase('local PHGPU02 fixture',k,rank,list(indices[:rows]),list(indices[rows:]),
                   signals[:rows*k],signals[rows*k:],seed_a,seed_b,fixture)
    case.validate();return case


def synthetic_cases():
    rng=random.Random(506013)
    for name,k,rank,ia,ib in (
        ('rank32-index-boundary',1056,32,[0,31,0xffffffff//32],[65537,3]),
        ('rank128-padded-tile',256,128,list(range(17)),list(range(9))),
        ('rank1024-repeated-indices',2048,1024,[0xffffffff//1024,0,0],[2,65537,2]),
    ):
        signals=[]
        for indices in (ia,ib):
            signals.append([(-64 if p%3==0 else 64 if p%3==1 else rng.randrange(-64,65))
                            for p in range(len(indices)*k)])
        yield NoiseCase(name,k,rank,ia,ib,*signals,rng.randbytes(32),rng.randbytes(32))


class NoiseMmaDevice(MmaDevice):
    def guarded(self,size):
        pointer=self.allocate(b'\xa5'*(size+32))
        return pointer,C.c_ulonglong(pointer.value+16)

    def generate_side(self,case,side,expected_values):
        indices,signal,seed,label=side;rows=len(indices)
        key=self.allocate(seed);index=self.allocate(struct.pack(f'<{rows}I',*indices))
        source=self.allocate(bytes(v&255 for v in signal))
        expected_uniform,expected_pairs=reference_tables(indices,case.k,case.rank,label,seed)
        uniform,u=self.guarded(len(expected_uniform));pairs,p=self.guarded(len(expected_pairs))
        noised,n=self.guarded(rows*case.k)
        r,k,rank=(C.c_uint(v)for v in (rows,case.k,case.rank))
        domain=C.c_uint(int.from_bytes(label[:4],'little'))
        self.launch(b'noise_uniform',(index,key,u,r,rank,domain),(rows*case.rank//32+127)//128,128)
        self.launch(b'noise_permutation',(key,p,k,rank,domain),(case.k//8+127)//128,128)
        self.launch(b'noise_apply',(source,u,p,n,r,k,rank),(rows*case.k+127)//128,128)
        self.api('cuCtxSynchronize',[])
        for name,pointer,expected in (
            ('uniform table',uniform,expected_uniform),('permutation table',pairs,expected_pairs),
            ('noised signed bytes',noised,bytes(v&255 for v in expected_values))):
            if self.checked_download(pointer,len(expected))!=expected:
                raise RuntimeError(f'GPU {name} differs from independent CPU calculation')
        return n,key

    def run_noise(self,case,matrix,expected):
        mark=len(self.allocations)
        try:
            a,key=self.generate_side(case,case.sides()[0],matrix.a)
            bt,_=self.generate_side(case,case.sides()[1],matrix.bt)
            # Consume actual device-produced signed bytes, without re-uploading
            # their downloaded reference-check copies or CPU noised matrices.
            self.check_products(matrix,expected,a,bt,key)
        finally:
            for pointer in reversed(self.allocations[mark:]):self.release(pointer)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,help='optional LOCAL PHGPU02 input')
    parser.add_argument('--cubin',type=Path,default=BASE/'gpu/noise-mma-sm120.cubin')
    parser.add_argument('--report',type=Path,help='new local completion report')
    parser.add_argument('--cpu-only',action='store_true')
    args=parser.parse_args()
    if args.report and (args.report.exists()or not args.report.parent.is_dir()):
        raise ValueError('report already exists or its parent directory is missing')
    cases=list(synthetic_cases())
    if args.fixture:
        if args.fixture.stat().st_size>8*1024*1024:raise ValueError('local fixture exceeds 8 MiB')
        cases.append(parse_noise_fixture(args.fixture.read_bytes()))
    checks=[]
    for case in cases:
        matrix=case.matrix();checks.append((matrix,scalar_reference(matrix)))
    if args.cpu_only:
        print(f'CPU-ONLY: prepared {len(cases)} noise/matrix comparisons; GPU not run',flush=True)
    else:
        device=NoiseMmaDevice()
        try:
            device.start(args.cubin)
            for case,(matrix,expected)in zip(cases,checks):
                device.run_noise(case,matrix,expected)
                print(f'PASS: GPU noise tables + signed bytes + tensor-core prefixes + transcript + digest: '
                      f'{case.name} ({matrix.rows}x{matrix.cols}, k={case.k}, rank={case.rank}); guards unchanged',flush=True)
        finally:device.close()
    if args.report:
        with args.report.open('x')as out:
            json.dump({'complete':True,'gpu_checked':not args.cpu_only,'cases':len(cases),
                       'scope':'offline GPU noise-to-MMA component; no mining search, pool verdict or performance claim'},out,indent=2)
    print('Offline component only; supplied seeds/signals, no mining search, pool verdict or performance claim.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError)as error:
        print('FAIL:',error);raise SystemExit(1)
