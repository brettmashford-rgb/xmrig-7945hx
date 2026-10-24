"""CPU target-boundary, descriptor, candidate and stale-result checks. ISC."""
import ctypes as C
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest
from tools.check_mma_gpu import MatrixCase
from tools.check_tile_scan_gpu import (MAX_BOUND,TileQuery,decode_candidates,
                                      pack_queries,query_reference,validate_scan)

BASE=Path(__file__).resolve().parents[1]


class TileScanTests(unittest.TestCase):
    def test_actual_native_comparator_at_u256_word_and_equality_boundaries(self):
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'target-check.so'
            source=(f'#include "{BASE}/gpu/scan_target.h"\n'
                    'extern "C" int check(const unsigned *d,const unsigned *t) {'
                    'return ph::digest_meets_bound(d,t);}\n')
            subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC','-x','c++','-',
                            '-o',str(path)],input=source,text=True,check=True)
            lib=C.CDLL(str(path));lib.check.argtypes=[C.c_void_p,C.c_void_p];lib.check.restype=C.c_int
            values=[0,1,255,256,(1<<32)-1,1<<32,(1<<64)-1,1<<64,
                    (1<<128)-1,1<<128,1<<255,MAX_BOUND]
            rng=random.Random(506014)
            pairs=[(a,b)for a in values for b in values]
            pairs.extend((rng.getrandbits(256),rng.getrandbits(256))for _ in range(1000))
            for digest,bound in pairs:
                a=(C.c_uint*8).from_buffer_copy(digest.to_bytes(32,'little'))
                b=(C.c_uint*8).from_buffer_copy(bound.to_bytes(32,'little'))
                self.assertEqual(lib.check(a,b),int(digest<=bound))

    def test_unordered_candidates_generation_overflow_and_rejection(self):
        generation=0xfedcba9801020304
        reference=[(bytes(64),value.to_bytes(32,'little'))for value in (1,256,1<<128,MAX_BOUND)]
        bounds=[1,255,1<<128,MAX_BOUND];hits=[3,2,0]
        def record(tile,tag=generation):
            return struct.pack('<3I',tile,tag&0xffffffff,tag>>32)+reference[tile][1]
        raw=b''.join(record(i)for i in hits)+bytes(44)
        status=struct.pack('<2I',3,0)
        result=decode_candidates(raw,status,bounds,4,generation,reference)
        self.assertEqual(set(result.require_complete()),set(hits))
        for bad in (raw[:-1],record(3,generation-1)+raw[44:],record(1)+raw[44:],
                    record(2)+raw[44:],raw[:12]+bytes(32)+raw[44:]):
            with self.assertRaises(ValueError):decode_candidates(bad,status,bounds,4,generation,reference)
        for capacity in (0,1):
            partial=record(3)if capacity else b''
            result=decode_candidates(partial,struct.pack('<2I',3,1),bounds,capacity,generation,reference)
            with self.assertRaisesRegex(RuntimeError,'retried'):result.require_complete()
        with self.assertRaises(ValueError):decode_candidates(raw,struct.pack('<2I',3,1),bounds,4,generation,reference)

    def test_query_maps_known_products_and_invalid_inputs(self):
        matrix=MatrixCase('known',2,2,32,32,[1]*32+[2]*32,[3]*32+[4]*32,bytes(32))
        queries=[TileQuery((1,),(0,)),TileQuery((0,1),(0,1)),TileQuery((0,0),(1,))]
        packed=pack_queries(queries,2,2);self.assertEqual(len(packed),3*66*4)
        reference=query_reference(matrix,queries)
        # One product: 2*3*32=192. Full fold: 96^128^192^256=288.
        for item,value in zip(reference,(192,288,0)):
            self.assertEqual(struct.unpack('<16I',item[0]),(value,)+(0,)*15)
        for bad in ([],[TileQuery((),(0,))],[TileQuery((2,),(0,))],
                    [TileQuery((True,),(0,))],[TileQuery((0,),tuple(range(33)))],queries*22):
            with self.assertRaises(ValueError):pack_queries(bad,2,2)
        for bounds,capacity,generation in (([-1],1,0),([MAX_BOUND+1],1,0),([True],1,0),
                                          ([1],65,0),([1],1,1<<64),([],1,0)):
            with self.assertRaises(ValueError):validate_scan(bounds,capacity,generation)


if __name__=='__main__':unittest.main()
