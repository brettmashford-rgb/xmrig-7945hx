"""All four complete orchestration paths, cold panel accounting and changed driver costs. ISC."""
from contextlib import ExitStack,redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from tools import compare_experiments as bench
from tools.fast_plan import FastPlan

class Benchmark(unittest.TestCase):
    def exercise(self,experiment,broken=None):
        session,job=bench.production_session();plan=FastPlan.from_job(job)
        device=SimpleNamespace(start=lambda p:None,close=lambda:None,allocations=[],api=lambda *a:None)
        owner=lambda *a,**kw:SimpleNamespace(close=lambda:None)
        searches=[]
        def factory(*a,mode,**kw):
            dispatch=SimpleNamespace(mode=mode,device=device,panel_builds=0,panel_seconds=0.,snapshot=(0,0,504 if mode.startswith('panel')else 472))
            search=SimpleNamespace(mode=mode,plan=plan,cursor=SimpleNamespace(next_tile=0),closed=False,
                backend=SimpleNamespace(dispatch=dispatch,stats=lambda:dict(dispatches=0)))
            search.close=lambda:setattr(search,'closed',True);searches.append(search);return search
        def window(search,tiles):
            first=search.cursor.next_tile;d=search.backend.dispatch
            count=tiles//(16384 if d.mode=='wide16k'else 4096)
            for i in range(count):
                device.api('cuMemsetD32Async',[],0,0,2,0)
                device.api('cuLaunchKernel',[]);device.api('cuLaunchKernel',[]);device.api('cuStreamSynchronize',[])
                device.api('cuMemcpyDtoH_v2',[],0,0,501 if broken=='driver'else d.snapshot[2]+32)
            if d.mode=='panel':
                builds=1023 if broken=='panel-builds'else 1024
                d.panel_builds+=builds
                for i in range(builds):
                    device.api('cuLaunchKernel',[]);device.api('cuStreamSynchronize',[]);device.api('cuMemcpyDtoH_v2',[],0,0,64)
            search.cursor.next_tile+=tiles+(1 if broken=='range'and d.mode!='control'else 0)
            return first,search.cursor.next_tile
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            report=Path(temp)/'report.json'
            for name,value in [('production_session',lambda:(session,job)),('prepare_gpu_base',lambda *a:None),
                ('prepare_cached_nonce',lambda *a:object()),('ProductionCandidateScanner',lambda:device),
                ('JobGeometry',owner),('JobBTables',owner),('new_search',factory),('resources',lambda d:{}),
                ('run_window',window)]:stack.enter_context(patch.object(bench,name,value))
            stack.enter_context(patch.object(bench.NonceCommitmentCache,'build',return_value=None))
            stack.enter_context(patch('sys.argv',['bench','--module','test.ptx','--commitment-module','merkle.ptx','--report',str(report),'--experiment',experiment]))
            with redirect_stdout(io.StringIO()):code=bench.main()
            result=json.loads(report.read_text())
            if broken:self.assertEqual(code,1);self.assertFalse(result['complete']);self.assertIsNotNone(result['error'])
            else:
                self.assertEqual(code,0);self.assertTrue(result['complete']);self.assertTrue(result['readback_contract_checked'])
                self.assertTrue(result['canonical_work_sets_checked'])
                self.assertEqual(result['comparison']['rounds'],6 if experiment=='panel'else 12)
            self.assertTrue(all(s.closed for s in searches))
            return result
    def test_blocks_complete(self):self.exercise('blocks')
    def test_pipeline_complete(self):self.exercise('pipeline')
    def test_batching_readback_frequency_four_times_lower(self):
        result=self.exercise('batching');d=result['driver_diagnostic']
        self.assertEqual(d['control']['calls']['cuLaunchKernel'],4*d['wide16k']['calls']['cuLaunchKernel'])
    def test_panel_full_domain_and_all_builds_included(self):
        result=self.exercise('panel');self.assertEqual(result['driver_diagnostic']['panel']['panel_builds'],1024)
        self.assertEqual(result['comparison']['unique_timed_tiles_per_mode'],50331648)
    def test_driver_change_fails(self):self.exercise('blocks','driver')
    def test_different_ranges_fail(self):self.exercise('pipeline','range')
    def test_missing_panel_build_fails(self):self.exercise('panel','panel-builds')
    def test_promotion_and_bad_samples(self):
        samples={'control':[1.]*12,'small4':[.98]*12};setup={m:[]for m in samples}
        self.assertEqual(bench.summary(samples,setup,100)['preferred'],'control')
        samples['small4']=[.9]*12;self.assertEqual(bench.summary(samples,setup,100)['preferred'],'small4')
        samples['small4'][0]=float('nan')
        with self.assertRaises(ValueError):bench.summary(samples,setup,100)

if __name__=='__main__':unittest.main()
