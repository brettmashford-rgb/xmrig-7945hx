#!/usr/bin/env python3
"""Offline keyed chunk-CV check. No pool connection, service or clock changes."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import sys
BASE=Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:sys.path.insert(0,str(BASE))
from reference.native_hash import chunk_value, parents
from tools.cuda_driver import CudaDevice


TWO_CHUNK_ROOT=bytes.fromhex('1130f45cc4c1f26bd6b06c2737e3795ca5d1827ae6cd8d670fac6dc3095db2e1')


def cases():
    # Includes nonaligned launch counts, the former 64-MiB index cap, the
    # 8-GiB chunk boundary, 32-bit carry and the maximum BLAKE3 u64 counter.
    shapes=[(0,129),(65535,3),(8388606,3),(0xffffffff,3),
            (0xfffffffffffffffd,3),(0,0)]
    for number,(first,count) in enumerate(shapes):
        seed=b'pearlhash/chunk-check/v009/'+struct.pack('<I',number)
        key=hashlib.sha256(seed).digest()
        data=hashlib.shake_256(seed).digest(count*1024)
        if number==0:
            data=bytes(1024)+b'\xff'*1024+data[2048:]
        expected=b''.join(chunk_value(data[i*1024:(i+1)*1024],first+i,key)
                          for i in range(count))
        yield first,count,key,data,expected


def validate_case(first,count,key,data,expected):
    if (type(first) is not int or type(count) is not int or not 0<=first<=0xffffffffffffffff
        or not 0<=count<=4096 or (count and first+count-1>0xffffffffffffffff)
        or len(key)!=32 or len(data)!=count*1024 or len(expected)!=count*32):
        raise ValueError('invalid bounded chunk test case')


class ChunkDevice(CudaDevice):
    def run(self,first,count,key,data,expected):
        validate_case(first,count,key,data,expected)
        key_ptr=self.allocate(key)
        source=self.allocate(data or bytes(4))
        destination=self.allocate(b'\xa5'*(len(expected)+32))
        interior=C.c_ulonglong(destination.value+16)
        first_arg=C.c_ulonglong(first);count_arg=C.c_uint(count)
        function=C.c_void_p()
        self.api('cuModuleGetFunction',[C.POINTER(C.c_void_p),C.c_void_p,C.c_char_p],
                 C.byref(function),self.module,b'keyed_chunk_cvs')
        args=(C.c_void_p*5)(*(C.cast(C.byref(v),C.c_void_p)
                             for v in (source,key_ptr,first_arg,count_arg,interior)))
        self.api('cuLaunchKernel',[C.c_void_p]+[C.c_uint]*7+[C.c_void_p]*3,
                 function,max(1,(count+127)//128),1,1,128,1,1,0,None,args,None)
        self.api('cuCtxSynchronize',[])
        result=C.create_string_buffer(len(expected)+32)
        self.api('cuMemcpyDtoH_v2',[C.c_void_p,C.c_ulonglong,C.c_size_t],
                 result,destination,len(result))
        if result.raw[:16]!=b'\xa5'*16 or result.raw[-16:]!=b'\xa5'*16:
            raise RuntimeError('chunk kernel output guard changed')
        if result.raw[16:-16]!=expected:
            raise RuntimeError(f'chunk chaining values differ at first={first}')
        return result.raw[16:-16]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-only',action='store_true')
    parser.add_argument('--write-fixture',type=Path)
    parser.add_argument('--cubin',type=Path,default=BASE/'gpu/chunk-commitment-sm120.cubin')
    args=parser.parse_args();batches=list(cases())
    goldens=json.loads((BASE/'tests/chunk-cv-goldens.json').read_text())['batches']
    if len(goldens)!=len(batches):raise ValueError('golden batch count differs')
    for batch,golden in zip(batches,goldens):
        validate_case(*batch)
        first,count,key,data,expected=batch
        if (first!=golden['first'] or count!=golden['count'] or key.hex()!=golden['key']
            or expected.hex()!=''.join(golden['cvs'])):
            raise ValueError('CPU comparisons differ from official-compressor synthetic goldens')
    if args.write_fixture:
        with args.write_fixture.open('xb') as out:
            out.write(b'PHCHNK01'+struct.pack('<I',len(batches)))
            for first,count,key,data,expected in batches:
                out.write(struct.pack('<QI',first,count)+key+data+expected)
    if args.cpu_only:
        print('CPU-ONLY: 141 keyed chunk CVs plus empty-launch case; GPU not run')
        return 0
    device=ChunkDevice()
    try:
        device.start(args.cubin)
        for first,count,key,data,expected in batches:
            actual=device.run(first,count,key,data,expected)
            # Root-domain check using two GPU CVs as a genuine two-chunk tree.
            if first==0 and count:
                root=parents([actual[:32],actual[32:64]],key,root=True)[0]
                if root!=TWO_CHUNK_ROOT:
                    raise RuntimeError('two-chunk root differs from pinned independent BLAKE3 golden')
            print(f'PASS: keyed chunk CVs first={first} count={count}; guards unchanged',flush=True)
        print('Offline commitment leaves only; no full matrix tree, pool reconstruction or custom share verdict.')
        return 0
    finally:device.close()


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError) as error:
        print('FAIL:',error);raise SystemExit(1)
