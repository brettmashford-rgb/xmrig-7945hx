"""Actual C++ descriptor layout, retained maps and stale builder ownership. ISC."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.resident_scan import ResidentBackend
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from test_cached_a import Device,Tables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class Resident(unittest.TestCase):
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=Device();self.tables=Tables(self.device,self.p)
        self.gen=[self.job.generation]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=ResidentBackend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_actual_header_words_match_canonical_descriptors(self):
        from tools.compare_search_loops import production_session
        session,job=production_session();plan=FastPlan.from_job(job)
        try:
            with tempfile.TemporaryDirectory()as temp:
                folder=Path(temp);source=folder/'words.cpp'
                source.write_text('#include "resident_descriptors.h"\nextern "C" unsigned word(const unsigned*a,const unsigned*b,unsigned n,unsigned t,unsigned w){return resident_descriptor_word(a,b,n,t,w);}\n')
                subprocess.run(['g++','-O2','-fPIC','-shared','-I'+str(ROOT/'gpu'),str(source),'-o',str(folder/'words.so')],check=True)
                lib=C.CDLL(str(folder/'words.so'));lib.word.argtypes=[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_uint];lib.word.restype=C.c_uint
                for candidate in (self.plan,plan):
                    ra=b''.join(v.packed for v in candidate.rows);cb=b''.join(v.packed for v in candidate.cols)
                    points=sorted({0,1,len(candidate.cols)-1,len(candidate.cols),candidate.count//2,candidate.count-1})
                    for tile in points:
                        batch=FastBatch(candidate,tile,tile+1);expected=candidate.prepare(object(),batch,0,4096).descriptors
                        actual=struct.pack('<66I',*(lib.word(ra,cb,len(candidate.cols),tile,w)for w in range(66)))
                        self.assertEqual(actual,expected)
        finally:session.close()
    def test_windows_upload_status_only_and_keep_axes_and_buffers(self):
        owned=tuple(p.value for p in self.device.allocations);self.device.calls.clear()
        first=FastBatch(self.plan,0,5);second=FastBatch(self.plan,5,12)
        self.assertEqual(self.backend(first,1,self.gen[0]).total,0)
        self.assertEqual(self.backend(second,1,self.gen[0]).total,0)
        self.assertEqual(self.device.calls.count('cuMemcpyHtoD_v2'),2)
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),4)
        self.assertEqual(tuple(p.value for p in self.device.allocations),owned)
        self.assertEqual(self.backend.prepared.descriptors,b'');self.assertEqual(self.backend.prepared.targets,b'')
    def test_retry_reuses_preparation(self):
        batch=FastBatch(self.plan,0,5);self.backend(batch,0,self.gen[0]);self.backend(batch,5,self.gen[0])
        self.assertEqual(self.backend.preparations,1)
    def test_replacement_after_builder_prevents_scanner_and_cleanup_drains(self):
        self.device.calls.clear();self.device.after_launch=lambda:self.gen.__setitem__(0,self.gen[0]+1)
        with self.assertRaisesRegex(RuntimeError,'stale'):self.backend(FastBatch(self.plan,0,2),1,self.job.generation)
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),1)
        self.backend.close();self.assertEqual(self.device.allocations,[])
    def test_axis_guard_corruption_is_detected(self):
        raw=self.backend.dispatch.axes[0][0];self.device.memory[raw.value][-1]=0
        with self.assertRaisesRegex(RuntimeError,'guard'):self.backend(FastBatch(self.plan,0,2),1,self.gen[0])
    def test_foreign_plan_is_rejected(self):
        other=FastPlan.from_job(self.job)
        with self.assertRaisesRegex(ValueError,'foreign'):self.backend(FastBatch(other,0,1),1,self.gen[0])


if __name__=='__main__':unittest.main()
