#!/usr/bin/env python3
"""Exact integer tensor-core prefix checks; no network, mining or timing claims.

Inputs are already-noised selected matrices. Compare EVERY rank-boundary
product, transcript word and digest against a separate scalar CPU calculation.
A user-local PHGPU02 fixture can be supplied; its contents are never uploaded.
"""
import argparse
import ctypes as C
from dataclasses import dataclass
import hashlib
import json
from itertools import chain
from pathlib import Path
import random
import struct
import sys
BASE=Path(__file__).resolve().parents[1]
if str(BASE)not in sys.path:sys.path.insert(0,str(BASE))
from reference.native_hash import small_hash
from tools.cuda_driver import CudaDevice


@dataclass
class MatrixCase:
    name:str
    rows:int
    cols:int
    k:int
    rank:int
    a:list
    bt:list
    key:bytes
    fixture_words:tuple|None=None
    fixture_digest:bytes|None=None

    def validate(self):
        if (any(type(v)is not int for v in (self.rows,self.cols,self.k,self.rank))
            or not 1<=self.rows<=32 or not 1<=self.cols<=32
            or not 32<=self.rank<=1024 or self.rank&(self.rank-1)
            or not 0<self.k<=65536 or self.k%self.rank
            or self.k*127*127>0x7fffffff or type(self.key)is not bytes or len(self.key)!=32
            or len(self.a)!=self.rows*self.k or len(self.bt)!=self.cols*self.k
            or any(type(v)is not int or not -127<=v<=127 for v in chain(self.a,self.bt))):
            raise ValueError('invalid bounded integer matrix case')


def scalar_reference(case):
    case.validate();pairs=case.rows*case.cols;steps=case.k//case.rank
    products=[0]*(pairs*steps)
    for row in range(case.rows):
        for col in range(case.cols):
            accumulator=0
            for step in range(steps):
                start=step*case.rank
                accumulator+=sum(case.a[row*case.k+l]*case.bt[col*case.k+l]
                                 for l in range(start,start+case.rank))
                products[step*pairs+row*case.cols+col]=accumulator
    words=[0]*16
    for step in range(steps):
        folded=0
        for value in products[step*pairs:(step+1)*pairs]:folded^=value&0xffffffff
        slot=step%16;old=words[slot]
        words[slot]=(((old<<13)|(old>>19))&0xffffffff)^folded
    digest=small_hash(struct.pack('<16I',*words),case.key)
    if case.fixture_words is not None and tuple(words)!=case.fixture_words:
        raise ValueError('local fixture transcript differs from independent scalar calculation')
    if case.fixture_digest is not None and digest!=case.fixture_digest:
        raise ValueError('local fixture digest differs from independent CPU hash')
    return struct.pack(f'<{len(products)}i',*products),struct.pack('<16I',*words),digest


def synthetic_cases():
    def key(name):return hashlib.sha256(b'pearlhash/mma/v012/'+name.encode()).digest()
    yield MatrixCase('signed-extreme',1,1,32,32,[-127]*32,[127]*32,key('signed-extreme'))
    rows,cols,k=17,9,64
    a=[0]*(rows*k)
    for r in range(rows):a[r*k+(r*7)%k]=(-1 if r%2 else 1)*(r%7+1)
    bt=[(c*11+l*3)%255-127 for c in range(cols)for l in range(k)]
    yield MatrixCase('one-hot-edges',rows,cols,k,32,a,bt,key('one-hot-edges'))
    rng=random.Random(506012);rows=cols=32;k=1056
    yield MatrixCase('multi-warp-slot-reuse',rows,cols,k,32,
                     [rng.randrange(-127,128)for _ in range(rows*k)],
                     [rng.randrange(-127,128)for _ in range(cols*k)],key('multi-warp-slot-reuse'))
    rows=cols=16;k=4096
    yield MatrixCase('long-extreme-prefix',rows,cols,k,128,[127]*(rows*k),[-127]*(cols*k),key('long-extreme-prefix'))


def parse_fixture(raw):
    if type(raw)is not bytes or not 24<=len(raw)<=8*1024*1024 or raw[:8]!=b'PHGPU02\0':
        raise ValueError('expected bounded PHGPU02 fixture')
    rows,cols,k,rank=struct.unpack_from('<4I',raw,8)
    if (not 1<=rows<=32 or not 1<=cols<=32 or not 32<=rank<=1024
        or rank&(rank-1)or not 0<k<=65536 or k%rank):raise ValueError('invalid fixture dimensions')
    size=(rows+cols)*k*4
    if len(raw)!=184+size*2+(rows+cols)*4:raise ValueError('fixture length/trailing bytes differ')
    values=list(struct.unpack_from(f'<{(rows+cols)*k}i',raw,24))
    position=24+size;words=struct.unpack_from('<16I',raw,position);key=raw[position+64:position+96]
    case=MatrixCase('local PHGPU02 fixture',rows,cols,k,rank,values[:rows*k],values[rows*k:],key,words,raw[-32:])
    case.validate();return case


class MmaDevice(CudaDevice):
    def launch(self,name,arguments,blocks,threads):
        function=C.c_void_p()
        self.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],
                 C.byref(function),self.module,name)
        params=(C.c_void_p*len(arguments))(*(C.cast(C.byref(value),C.c_void_p)for value in arguments))
        self.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                 function,blocks,1,1,threads,1,1,0,None,params,None)

    def checked_download(self,pointer,size):
        result=C.create_string_buffer(size+32)
        self.api('cuMemcpyDtoH_v2',[C.c_void_p,C.c_ulonglong,C.c_size_t],result,pointer,len(result))
        if result.raw[:16]!=b'\xa5'*16 or result.raw[-16:]!=b'\xa5'*16:
            raise RuntimeError('tensor-core output guard changed')
        return result.raw[16:-16]

    def run(self,case,expected):
        mark=len(self.allocations)
        try:
            a=self.allocate(bytes(v&255 for v in case.a));bt=self.allocate(bytes(v&255 for v in case.bt))
            key=self.allocate(case.key)
            outputs=[self.allocate(b'\xa5'*(len(value)+32))for value in expected]
            interiors=[C.c_ulonglong(value.value+16)for value in outputs]
            rows,cols,k,rank=(C.c_uint(value)for value in (case.rows,case.cols,case.k,case.rank))
            tiles=((case.rows+15)//16)*((case.cols+7)//8)
            self.launch(b'mma_cumulative',(a,bt,interiors[0],rows,cols,k,rank),(tiles+3)//4,128)
            self.launch(b'mma_fold_digest',(interiors[0],key,interiors[1],interiors[2],
                                          C.c_uint(case.rows*case.cols),C.c_uint(case.k//case.rank)),1,32)
            self.api('cuCtxSynchronize',[])
            for label,pointer,value in zip(('prefix products','transcript','digest'),outputs,expected):
                if self.checked_download(pointer,len(value))!=value:
                    raise RuntimeError(f'tensor-core {label} differs from independent CPU reference')
        finally:
            for pointer in reversed(self.allocations[mark:]):self.release(pointer)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,help='optional LOCAL PHGPU02 file')
    parser.add_argument('--report',type=Path,help='write completion status locally; refuses an existing file')
    parser.add_argument('--cpu-only',action='store_true')
    parser.add_argument('--cubin',type=Path,default=BASE/'gpu/mma-sm120.cubin')
    args=parser.parse_args()
    if args.report and (args.report.exists()or not args.report.parent.is_dir()):
        raise ValueError('report already exists or its parent directory is missing')
    cases=list(synthetic_cases())
    if args.fixture:
        if args.fixture.stat().st_size>8*1024*1024:raise ValueError('local fixture exceeds 8 MiB')
        cases.append(parse_fixture(args.fixture.read_bytes()))
    checks=[scalar_reference(case)for case in cases]
    if args.cpu_only:
        if args.report:
            with args.report.open('x')as out:json.dump({'complete':True,'gpu_checked':False,'cpu_only':True,'cases':len(cases)},out)
        print(f'CPU-ONLY: prepared {len(cases)} scalar prefix/transcript/digest comparisons; GPU not run')
        return 0
    device=MmaDevice()
    try:
        device.start(args.cubin)
        for case,expected in zip(cases,checks):
            device.run(case,expected)
            print(f'PASS: tensor-core prefixes + transcript + digest: {case.name} '
                  f'({case.rows}x{case.cols}, k={case.k}, rank={case.rank}); guards unchanged',flush=True)
        if args.report:
            with args.report.open('x')as out:
                json.dump({'complete':True,'gpu_checked':True,'cases':len(cases),
                           'prefix_products_transcript_digest':'passed','output_guards':'unchanged',
                           'scope':'offline exact integer MMA; no mining search, pool verdict or performance claim'},out,indent=2)
        print('Offline exact integer MMA only; supplied noised inputs, no mining search or pool verdict. No performance claim.')
        return 0
    finally:device.close()


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError) as error:
        print('FAIL:',error);raise SystemExit(1)
