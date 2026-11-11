"""Exercise the complete offline benchmark orchestration and diagnostic contract without CUDA. ISC."""
from contextlib import ExitStack,redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import compare_combined as bench
from tools.fast_plan import FastPlan

class Benchmark(unittest.TestCase):
    def exercise(self,broken=None):
        session,job=bench.production_session();plan=FastPlan.from_job(job)
        device=SimpleNamespace(start=lambda p:None,close=lambda:None,allocations=[],api=lambda *a:None)
        owner=lambda *a,**kw:SimpleNamespace(close=lambda:None)
        searches=[]
        def factory(*a,**kwargs):
            search=SimpleNamespace(plan=plan,cursor=SimpleNamespace(next_tile=0),close=lambda:None,
                backend=SimpleNamespace(dispatch=object(),stats=lambda:dict(prepare_seconds=0,scan_seconds=0,dispatches=0,prepared_batches=0)))
            searches.append(search);return search
        def window(search,mode,tiles=bench.WINDOW):
            self.assertEqual(tiles,524288);first=search.cursor.next_tile
            for i in range(128):
                device.api('cuMemsetD32Async',[],0,0,2,0)
                device.api('cuLaunchKernel',[]);device.api('cuLaunchKernel',[])
                device.api('cuStreamSynchronize',[])
                device.api('cuMemcpyDtoH_v2',[],0,0,500 if broken=='driver'else 504)
            search.cursor.next_tile+=tiles+(1 if broken=='range'and mode==bench.MODES[2]else 0)
            return first,search.cursor.next_tile
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            report=Path(temp)/'report.json'
            for name,value in [('production_session',lambda:(session,job)),('prepare_gpu_base',lambda *a:None),
                ('prepare_nonce',lambda *a:object()),('ProductionCandidateScanner',lambda:device),
                ('JobGeometry',owner),('JobBTables',owner),('new_combined_search',factory),
                ('kernel_resources',lambda d:{}),('run_window',window)]:stack.enter_context(patch.object(bench,name,value))
            stack.enter_context(patch('sys.argv',['compare','--module','test.ptx','--commitment-module','merkle.ptx','--report',str(report)]))
            with redirect_stdout(io.StringIO()):code=bench.main()
            result=json.loads(report.read_text())
            if broken:
                self.assertEqual(code,1);self.assertFalse(result['complete']);self.assertIsNotNone(result['error'])
            else:
                self.assertEqual(code,0);self.assertTrue(result['complete']);self.assertEqual(len(searches),3)
                self.assertEqual(result['loop_comparison']['unique_timed_tiles_per_mode'],6291456)
                self.assertTrue(result['canonical_work_sets_checked']);self.assertTrue(result['readback_contract_checked'])
            return result
    def test_complete_three_way_rounds_and_production_geometry(self):self.exercise()
    def test_different_work_ranges_fail(self):self.assertIn('different global tile ranges',self.exercise('range')['error'])
    def test_changed_driver_readback_contract_fails(self):self.assertIn('driver diagnostic',self.exercise('driver')['error'])

if __name__=='__main__':unittest.main()
