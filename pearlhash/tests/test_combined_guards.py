"""The rig guard diagnostic restores changed map words and requires uniform rejection. ISC."""
import ctypes as C
import struct
from types import SimpleNamespace
import unittest
from tools.check_combined import cta_guard_cases
from tools.cta_b_scan import cta_canonical_tile
from tools.check_prepared_job import synthetic_session
from tools.fast_plan import FastPlan

class Guards(unittest.TestCase):
    def exercise(self,failure=None):
        session,job,_=synthetic_session(bytes(32));plan=FastPlan.from_job(job)
        addresses=(1000,100000,200000)
        memory={addresses[0]:bytearray(b''.join(a.packed for a in plan.rows)),
            addresses[1]:bytearray(b''.join(a.packed for a in plan.cols)),addresses[2]:bytearray(4096*32)}
        original={a:bytes(memory[a])for a in addresses[:2]};calls=[]
        def access(pointer,data=None,size=None):
            address=pointer.value
            for base,raw in memory.items():
                if base<=address<base+len(raw):
                    offset=address-base
                    if data is not None:raw[offset:offset+len(data)]=data;return
                    return bytes(raw[offset:offset+size])
            raise AssertionError('unexpected diagnostic pointer')
        profile=SimpleNamespace(m=160,n=192)
        d=SimpleNamespace(bound=job.share_bound,targets=(None,C.c_ulonglong(addresses[2])),
            axes=[(None,C.c_ulonglong(addresses[0]),len(memory[addresses[0]])),(None,C.c_ulonglong(addresses[1]),len(memory[addresses[1]]))],
            upload=lambda p,data:access(p,data=data),tables=SimpleNamespace(read=lambda p,o,n:access(C.c_ulonglong(p.value+o),size=n)),
            prepare_window=lambda batch:batch)
        def scan(batch,prepared,generation,**kwargs):
            calls.append(batch.start)
            if failure=='raise':raise RuntimeError('injected launch error')
            tile=cta_canonical_tile(plan,batch.start);col=tile%len(plan.cols)
            group=min(32,len(plan.rows));first_row=(tile//len(plan.cols)//group)*group
            rows=[struct.unpack_from('<I',memory[addresses[0]],r*128)[0]for r in range(first_row,first_row+group)]
            column=struct.unpack_from('<I',memory[addresses[1]],col*128)[0]
            self.assertTrue(any(r>=160 for r in rows)or column>=192)
            return SimpleNamespace(total=int(failure=='accept'),records={})
        d.scan_window=scan
        search=SimpleNamespace(plan=plan,backend=SimpleNamespace(dispatch=d),context=SimpleNamespace(profile=profile,job=job))
        try:
            report={'cta_guard_cases':0}
            if failure:
                with self.assertRaises(RuntimeError):cta_guard_cases(search,report)
            else:
                cta_guard_cases(search,report)
                self.assertEqual(report['cta_guard_cases'],5);self.assertEqual(len(calls),5)
                self.assertEqual(d.bound,job.share_bound)
            for base,raw in original.items():self.assertEqual(bytes(memory[base]),raw)
        finally:session.close()
    def test_all_five_partial_block_guard_paths(self):self.exercise()
    def test_launch_failure_restores_mutated_row(self):self.exercise('raise')
    def test_invalid_map_acceptance_stops_and_restores(self):self.exercise('accept')

if __name__=='__main__':unittest.main()
