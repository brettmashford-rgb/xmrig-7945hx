"""End-to-end orchestration, common work sets, driver counts and automatic power phase. ISC."""
from contextlib import ExitStack,redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from tools import compare_pair_depth as bench
from tools.gpu_power import summarize,TelemetryError

class Benchmark(unittest.TestCase):
    def exercise(self,broken=None):
        session,job=bench.production_session();searches=[]
        device=SimpleNamespace(start=lambda p:None,close=lambda:None,allocations=[],api=lambda *a:None)
        owner=lambda *a,**kw:SimpleNamespace(close=lambda:None)
        def factory(*a,mode,**kw):
            d=SimpleNamespace(mode=mode,device=device);s=SimpleNamespace(mode=mode,closed=False,cursor=SimpleNamespace(next_tile=0),backend=SimpleNamespace(dispatch=d))
            s.close=lambda:setattr(s,'closed',True);searches.append(s);return s
        def window(search,tiles):
            first=search.cursor.next_tile
            for i in range(tiles//16384):
                device.api('cuMemsetD32Async',[]);device.api('cuLaunchKernel',[]);device.api('cuLaunchKernel',[])
                device.api('cuStreamSynchronize',[]);device.api('cuMemcpyDtoH_v2',[],0,0,500 if broken=='driver'else 504)
            search.cursor.next_tile+=tiles+(1 if broken=='range'and search.mode!=bench.MODES[0]else 0)
            return first,search.cursor.next_tile
        power=dict(attempted=True,available=False,error='sensor not supported')
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            path=Path(temp)/'report.json'
            for name,value in [('production_session',lambda:(session,job)),('prepare_gpu_base',lambda *a:None),
                ('prepare_cached_nonce',lambda *a:object()),('ProductionCandidateScanner',lambda:device),('JobGeometry',owner),('JobBTables',owner),
                ('new_search',factory),('resources',lambda d:{}),('run_window',window)]:stack.enter_context(patch.object(bench,name,value))
            power_mock=stack.enter_context(patch.object(bench,'power_phase',return_value=power))
            stack.enter_context(patch.object(bench.NonceCommitmentCache,'build',return_value=None))
            stack.enter_context(patch('sys.argv',['bench','--module','m','--commitment-module','c','--report',str(path)]))
            with redirect_stdout(io.StringIO()):code=bench.main()
            result=json.loads(path.read_text());self.assertTrue(all(s.closed for s in searches))
            if broken:self.assertEqual(code,1);self.assertFalse(result['complete']);power_mock.assert_not_called()
            else:
                self.assertEqual(code,0);self.assertTrue(result['complete']);self.assertTrue(result['power_monitoring_attempted']);power_mock.assert_called_once()
                self.assertEqual(result['comparison']['unique_timed_tiles_per_mode'],6291456)
                for mode in bench.MODES:self.assertEqual(result['driver_diagnostic'][mode]['calls']['cuLaunchKernel'],64)
    def test_complete_with_unsupported_sensor_still_reports_speed(self):self.exercise()
    def test_driver_mismatch_fails(self):self.exercise('driver')
    def test_work_set_mismatch_fails(self):self.exercise('range')
    def test_speed_promotion_is_against_16K_and_incremental_scheduling(self):
        modes=bench.MODES;samples={m:[v]*12 for m,v in zip(modes,(1.,.9,.8))}
        r=bench.summary(samples,{},100);self.assertEqual(r['preferred'],modes[2]);self.assertAlmostEqual(r['step8_speedup_over_step2'],1.125)
        samples[modes[2]][0]=float('nan')
        with self.assertRaises(ValueError):bench.summary(samples,{},100)
    def test_sustained_power_trials_do_equal_complete_nonces_and_close(self):
        closed=[];work=[];contexts=[]
        session,job=bench.production_session();owners={m:(object(),object())for m in bench.MODES}
        def context(job,base,worker,nonce,*args):contexts.append(nonce);return SimpleNamespace(nonce=nonce)
        class Search:
            def __init__(self,ctx,mode):self.context=ctx;self.mode=mode;self.plan=SimpleNamespace(count=bench.FULL_NONCE)
            def __enter__(self):return self
            def __exit__(self,*args):closed.append(self)
        class Reader:
            pci_bus_id='0000:03:00.0'
            def __init__(self,d):self.closed=False;readers.append(self)
            def read(self):return {}
            def close(self):self.closed=True
        class Sampler:
            def __init__(self,r):pass
            def measure(self,fn,tiles):
                fn();rows=[dict(monotonic_seconds=i*.2,power_w=100,gpu_activity_pct=90,memory_activity_pct=20,sm_clock_mhz=2400,
                    memory_clock_mhz=14000,temperature_c=60,power_limit_w=145,pstate=0,clock_event_bits=0)for i in range(61)]
                return summarize(rows,tiles)
        readers=[]
        def window(s,tiles):work.append((s.mode,s.context.nonce,tiles));return (0,tiles)
        with patch.object(bench,'NvmlReader',Reader),patch.object(bench,'PowerSampler',Sampler),patch.object(bench,'prepare_cached_nonce',context),\
            patch.object(bench,'new_search',side_effect=lambda ctx,*a,mode:Search(ctx,mode)),patch.object(bench,'run_window',window),redirect_stdout(io.StringIO()):
            r=bench.power_phase(object(),job,None,None,session,owners)
        self.assertTrue(r['available']);self.assertEqual(len(r['trials']),6);self.assertEqual(len(work),24);self.assertEqual(len(closed),24)
        self.assertTrue(readers[0].closed)
        for mode in bench.MODES:self.assertEqual(r['summary'][mode]['measured_tiles'],6*bench.FULL_NONCE)
        for round_id in (1,2):
            trials=[t for t in r['trials']if t['round']==round_id]
            self.assertEqual(len({tuple(t['nonces_hex'])for t in trials}),1)
        session.close()
    def test_missing_nvml_explicitly_marks_power_unavailable(self):
        with patch.object(bench,'NvmlReader',side_effect=TelemetryError('unavailable')):
            r=bench.power_phase(None,None,None,None,None,{})
        self.assertTrue(r['attempted']);self.assertFalse(r['available']);self.assertEqual(r['error'],'unavailable')
if __name__=='__main__':unittest.main()
