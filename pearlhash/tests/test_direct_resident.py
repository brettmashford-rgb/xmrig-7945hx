"""Direct map ABI, exact unchanged tile body and cancellation ownership. ISC."""
import ctypes as C
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.direct_resident import DirectBackend,new_direct_search
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork
from types import SimpleNamespace
from test_cached_a import Device,Tables
from test_prepared_dispatch import profile
ROOT=Path(__file__).resolve().parents[1]


class Direct(unittest.TestCase):
    def setUp(self):
        self.session,self.job,_=synthetic_session(bytes(32));self.plan=FastPlan.from_job(self.job)
        self.p=replace(profile(),m=160,n=192);self.device=Device();self.tables=Tables(self.device,self.p);self.gen=[self.job.generation]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            self.backend=DirectBackend(self.p,self.device,plan=self.plan,bound=0,current_generation=lambda:self.gen[0])
    def tearDown(self):self.backend.close();self.session.close()
    def test_actual_axis_helper_matches_all_boundary_maps(self):
        from tools.compare_resident_loops import production_session
        session,job=production_session();plan=FastPlan.from_job(job)
        try:
            with tempfile.TemporaryDirectory()as temp:
                folder=Path(temp);source=folder/'offsets.cpp'
                source.write_text('#include "direct_axes.h"\nextern "C" unsigned axis(unsigned f,unsigned q,unsigned n,unsigned side){auto v=resident_axis_offsets(f,q,n);return side?v.col:v.row;}\n')
                subprocess.run(['g++','-O2','-fPIC','-shared','-I'+str(ROOT/'gpu'),str(source),'-o',str(folder/'axis.so')],check=True)
                lib=C.CDLL(str(folder/'axis.so'));lib.axis.argtypes=[C.c_uint]*4;lib.axis.restype=C.c_uint
                for p in (self.plan,plan):
                    for tile in (0,1,len(p.cols)-1,len(p.cols),p.count//2,p.count-1):
                        first=max(0,tile-33);query=tile-first
                        a=lib.axis(first,query,len(p.cols),0);b=lib.axis(first,query,len(p.cols),1)
                        self.assertEqual((p.rows[a].indices,p.cols[b].indices),p.indices(tile))
        finally:session.close()
    def test_new_kernel_preserves_exact_validated_tile_math_body(self):
        old=(ROOT/'gpu/cached_a_tile_scan.cu').read_text();new=(ROOT/'gpu/direct_resident_scan.cu').read_text()
        self.assertEqual(old[old.index('    bool invalid='):],new[new.index('    bool invalid='):])
    def test_one_launch_per_window_and_no_descriptors_uploaded(self):
        self.device.calls.clear();owned=tuple(p.value for p in self.device.allocations)
        self.backend(FastBatch(self.plan,0,5),1,self.gen[0]);self.backend(FastBatch(self.plan,5,12),1,self.gen[0])
        self.assertEqual(self.device.calls.count('cuLaunchKernel'),2)
        self.assertEqual(self.device.calls.count('cuMemcpyHtoD_v2'),2)
        self.assertEqual(tuple(p.value for p in self.device.allocations),owned)
        self.assertEqual(len(self.backend.dispatch.arguments),24)
        self.assertEqual(self.backend.dispatch.arguments[5].value,self.backend.dispatch.axes[0][1].value)
        self.assertEqual(self.backend.dispatch.arguments[20].value,self.backend.dispatch.axes[1][1].value)
        self.assertEqual(self.backend.dispatch.arguments[23].value,5)
    def test_replacement_after_launch_drains_and_prevents_cursor_credit(self):
        context=SimpleNamespace(job=self.job,profile=self.p);current=[True]
        with patch('tools.resident_scan.VirtualTables',return_value=self.tables):
            search=new_direct_search(context,self.device,lambda job:current[0])
        self.device.after_launch=lambda:current.__setitem__(0,False)
        try:
            with self.assertRaises(StaleWork):search.advance(2)
            self.assertEqual(search.cursor.next_tile,0);self.assertTrue(search.closed)
            self.assertFalse(search.backend.dispatch.pending)
        finally:search.close()
    def test_axis_guard_remains_checked(self):
        raw=self.backend.dispatch.axes[1][0];self.device.memory[raw.value][-1]=0
        with self.assertRaisesRegex(RuntimeError,'guard'):self.backend(FastBatch(self.plan,0,2),1,self.gen[0])
    def test_current_check_blocks_prelaunch_stale_generation(self):
        self.gen[0]+=1;self.device.calls.clear()
        with self.assertRaisesRegex(ValueError,'stale'):self.backend(FastBatch(self.plan,0,1),1,self.job.generation)
        self.assertNotIn('cuLaunchKernel',self.device.calls)


if __name__=='__main__':unittest.main()
