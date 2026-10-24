"""Native fragment/table differential checks and profile/global descriptor caps. ISC."""
import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from reference.dense import _random_hash
from reference.tile_ranges import RangeBatch
from tools.check_range_scan_gpu import ConstantProfile
from tools.check_noise_mma_gpu import reference_tables
from tools.check_tile_scan_gpu import TileQuery
from tools.virtual_scan import table_payload,pack_global_queries,global_reference,VirtualRangeBackend
from tools.offline_nonce_search import make_job,prepare_base,prepare_nonce,find_candidate,build_candidate

BASE=Path(__file__).resolve().parents[1]


class VirtualScanTests(unittest.TestCase):
    def test_actual_native_uniform_body_and_virtual_loader_all_signed_bytes(self):
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'virtual-check.so'
            subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC',str(BASE/'tests/virtual_input_cpu.cpp'),'-o',str(path)],check=True)
            lib=C.CDLL(str(path));lib.check_uniform_range.argtypes=[C.c_void_p]*2+[C.c_uint]*3
            lib.check_virtual_pack.argtypes=[C.c_void_p]*5+[C.c_uint]*4+[C.c_int,C.c_uint,C.c_void_p]+[C.c_uint]*3
            lib.check_virtual_pack.restype=C.c_uint
            key=bytes(range(32));domain=int.from_bytes(b'A_te','little')
            for first,count in ((0,129),(65535,3),(8388606,3),((1<<27)-3,3),(0,0)):
                raw=C.create_string_buffer(b'\xa5'*(count*32+32),count*32+32)
                lib.check_uniform_range(key,C.byref(raw,16),first,count,domain)
                expected=bytes(((v&63)-32)&255 for block in range(first,first+count)
                               for v in _random_hash(block,b'A_tensor',key,0))
                self.assertEqual(raw.raw,b'\xa5'*16+expected+b'\xa5'*16)
            for rank,k,fill in ((32,1056,64),(128,2048,0),(1024,2048,-64)):
                profile=ConstantProfile(3,4,k,rank,fill,bytes([192,64]*8),key,key[::-1])
                ra=(2,0,2);cb=(3,1,0)
                batch=RangeBatch(0,1,ra,cb,((tuple(range(3)),tuple(range(3))),))
                matrix=profile.case(batch).matrix()
                ua,pa=reference_tables(list(range(3)),k,rank,b'A_tensor',key)
                ub,pb=reference_tables(list(range(4)),k,rank,b'B_tensor',key[::-1])
                for side,rows,values in ((0,ra,matrix.a),(1,cb,matrix.bt)):
                    mapping=(C.c_uint*len(rows))(*rows);actual=bytearray()
                    for row in range(len(rows)):
                        for offset in range(0,k,4):
                            word=lib.check_virtual_pack(ua,ub,pa,pb,profile.tail,3,4,k,rank,fill,side,mapping,row,len(rows),offset)
                            actual.extend(struct.pack('<I',word))
                    self.assertEqual(actual,bytes(v&255 for v in values))
                    # Padded rows must not dereference a map or read tables.
                    self.assertEqual(lib.check_virtual_pack(ua,ub,pa,pb,profile.tail,3,4,k,rank,fill,side,None,3,3,0),0)

    def test_global_descriptors_and_memory_cap(self):
        p=ConstantProfile(5121,262144,32768,128,64,bytes(16),bytes(32),bytes(32))
        self.assertEqual(table_payload(p),34472080)
        queries=[TileQuery((5120,),(262143,))]
        raw=pack_global_queries(p,queries)
        self.assertEqual(struct.unpack_from('<I',raw,8)[0],5120)
        self.assertEqual(struct.unpack_from('<I',raw,34*4)[0],262143)
        for bad in ([],[TileQuery((True,),(0,))],[TileQuery((5121,),(0,))],[TileQuery((0,),(262144,))]):
            with self.assertRaises(ValueError):pack_global_queries(p,bad)
        oversized=ConstantProfile(5121,262144,32768,256,64,bytes(16),bytes(32),bytes(32))
        with self.assertRaisesRegex(ValueError,'64-MiB'):table_payload(oversized)

    def test_virtual_backend_cpu_preparation_binds_fresh_nonce_proof(self):
        job=make_job(bytes(range(32)),3);base=prepare_base(job)
        context=prepare_nonce(job,base,bytes(range(8)),bytes(range(8,16)),17)
        found,cursor=find_candidate(context,backend_factory=VirtualRangeBackend)
        self.assertIsNotNone(found);self.assertGreater(cursor.next_tile,0)
        proof,words=build_candidate(context,found)
        self.assertGreater(len(proof),0);self.assertEqual(len(words),64)


if __name__=='__main__':unittest.main()
