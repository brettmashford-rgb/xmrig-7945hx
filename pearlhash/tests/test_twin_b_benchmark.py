"""Unique-work accounting, matched diagnostic, energy inclusion and fail-closed gates. ISC."""
from contextlib import ExitStack,redirect_stdout
import io,json
from pathlib import Path
from types import SimpleNamespace
import tempfile,unittest
from unittest.mock import patch
from tools import compare_twin_b as bench,check_twin_b as gate
from tools.gpu_power import summarize,TelemetryError


class Benchmark(unittest.TestCase):
    def test_summary_uses_two_distinct_domains_and_never_promotes_private_diagnostic(self):
        r=bench.summary({m:[v]*12 for m,v in zip(bench.MODES,(1,.5,.99))},.1)
        self.assertEqual(r['unique_timed_tiles_per_mode'],12582912)
        self.assertEqual(r['median_unique_tiles_per_second']['pair-direct'],1048576)
        self.assertEqual(r['preferred'],'pair-direct')
        r=bench.summary({m:[v]*12 for m,v in zip(bench.MODES,(1,.95,.8))},.1)
        self.assertEqual(r['preferred'],'twin-shared-b');self.assertAlmostEqual(r['reuse_speedup_over_matched_private'],.95/.8)
        for invalid in(float('nan'),float('inf'),0,-1):
            with self.assertRaises(ValueError):bench.summary({m:[invalid]*12 for m in bench.MODES},0)
    def test_actual_driver_diagnostic_counts_both_guards_and_shared_stream(self):
        device=SimpleNamespace(api=lambda *args:None)
        def run(mode,first,stop):
            for _ in range((stop-first)//16384):
                for _ in range(2):device.api('cuMemsetD32Async',[])
                for _ in range(4 if mode=='pair-direct'else 3):device.api('cuLaunchKernel',[])
                for _ in range(2 if mode=='pair-direct'else 1):device.api('cuStreamSynchronize',[])
                for _ in range(2):device.api('cuMemcpyDtoH_v2',[],0,0,504)
        t=SimpleNamespace(device=device,run=run)
        for mode in bench.MODES:
            r=bench.diagnostic(t,mode);self.assertEqual(r['copy_bytes']['cuMemcpyDtoH_v2'],32256)
        with patch.object(t,'run',side_effect=lambda *args:device.api('cuCtxSynchronize',[])):
            with self.assertRaises(RuntimeError):bench.diagnostic(t,'twin-shared-b')
    def exercise(self,broken=False):
        device=SimpleNamespace(start=lambda p:None,close=lambda:None,allocations=[],api=lambda *args:None)
        session,job=bench.production_session();closed=[];runs=[];powers=[]
        class FakeTwin:
            def __init__(self,*args):
                self.dispatches=[SimpleNamespace(device=device)];self.functions={m:object()for m in bench.MODES[1:]}
            def run(self,mode,first,stop):runs.append((mode,first,stop));return(first,stop+int(broken))
            def close(self):closed.append(self)
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            path=Path(temp)/'report.json'
            for name,value in [('production_session',lambda:(session,job)),('prepare_gpu_base',lambda *a:None),
                    ('contexts_for',lambda *a:('c0','c1')),('ProductionCandidateScanner',lambda:device),
                    ('JobInputs',lambda *a:SimpleNamespace(close=lambda:None)),('Twin',FakeTwin),('resources',lambda *a:{}),
                    ('diagnostic',lambda *a:{}),('power_phase',lambda *a:powers.append(True)or dict(attempted=True,available=False))]:
                stack.enter_context(patch.object(bench,name,value))
            stack.enter_context(patch.object(bench.NonceCommitmentCache,'build',return_value=None))
            stack.enter_context(patch('sys.argv',['bench','--module','m','--commitment-module','c','--report',str(path)]))
            with redirect_stdout(io.StringIO()):code=bench.main()
            report=json.loads(path.read_text());self.assertTrue(closed)
        if broken:self.assertEqual(code,1);self.assertFalse(powers);self.assertFalse(report['complete'])
        else:
            self.assertEqual(code,0);self.assertTrue(report['complete']);self.assertEqual(len(powers),1)
            self.assertEqual(report['comparison']['unique_timed_tiles_per_mode'],12582912)
            for round_id in range(12):
                group=runs[3+round_id*3:6+round_id*3]
                self.assertEqual({(first,stop)for mode,first,stop in group},{((round_id+1)*bench.WINDOW,(round_id+2)*bench.WINDOW)})
    def test_orchestration_uses_same_pair_and_intervals_before_power(self):self.exercise()
    def test_incomplete_second_nonce_interval_blocks_energy_and_success(self):self.exercise(True)
    def test_full_energy_includes_preparation_and_closes_each_fresh_pair(self):
        work=[];readers=[];closed=[];preparations=[]
        class Reader:
            pci_bus_id='test'
            def __init__(self,*args):self.closed=False;readers.append(self)
            def read(self):return{}
            def close(self):self.closed=True
        class Sampler:
            def __init__(self,*a):pass
            def measure(self,fn,tiles):
                fn();rows=[dict(monotonic_seconds=i*.2,power_w=80,gpu_activity_pct=95,memory_activity_pct=4,
                    sm_clock_mhz=2500,memory_clock_mhz=810,temperature_c=60,power_limit_w=145,pstate=0,clock_event_bits=0)for i in range(61)]
                return summarize(rows,tiles)
        class FakeTwin:
            def __init__(self,contexts,*args):self.contexts=contexts;self.plan=SimpleNamespace(count=bench.FULL_NONCE);self.completed_unique_tiles=0
            def __enter__(self):return self
            def __exit__(self,*args):closed.append(self)
            def run(self,mode,first,stop):work.append((mode,self.contexts,first,stop));self.completed_unique_tiles+=2*(stop-first)
        def prepare(job,base,worker,miner,*args):preparations.append(miner);return miner
        with patch.object(bench,'NvmlReader',Reader),patch.object(bench,'PowerSampler',Sampler),patch.object(bench,'Twin',FakeTwin),\
                patch('tools.nonce_cache.prepare_cached_nonce',side_effect=prepare),redirect_stdout(io.StringIO()):
            r=bench.power_phase(object(),object(),None,None,SimpleNamespace(is_current=lambda job:True),object())
        self.assertTrue(r['available']);self.assertEqual(len(work),24);self.assertEqual(len(closed),24);self.assertEqual(len(preparations),48)
        self.assertTrue(readers[0].closed)
        for mode in bench.MODES:
            self.assertEqual(r['summary'][mode]['measured_tiles'],100663296)
            self.assertEqual(len([w for w in work if w[0]==mode]),8)
        # Each round compares the same conditioning/measured nonce pairs in all three modes.
        for start in(0,12):
            groups=[tuple(row[1]for row in work[start+i*4:start+(i+1)*4])for i in range(3)]
            self.assertEqual(groups[0],groups[1]);self.assertEqual(groups[1],groups[2])
            self.assertTrue(all(a!=b for a,b in groups[0]))
    def test_unsupported_power_is_explicit_without_efficiency_claim(self):
        with patch.object(bench,'NvmlReader',side_effect=TelemetryError('unsupported')):
            r=bench.power_phase(None,None,None,None,None,None)
        self.assertFalse(r['available']);self.assertIn('unsupported',r['error']);self.assertNotIn('most_efficient',r)


class Gates(unittest.TestCase):
    def test_preflight_failure_blocks_subsequent_gates(self):
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            output=Path(temp)/'preflight'
            stack.enter_context(patch('sys.argv',['check','--module','m','--commitment-module','c','--oracle','o','--mode','twin-shared-b','--output-dir',str(output)]))
            stack.enter_context(patch.object(gate,'production_checks',side_effect=RuntimeError('second nonce mismatch')))
            odd=stack.enter_context(patch.object(gate,'odd_checks'));proof=stack.enter_context(patch.object(gate,'proof_guard_checks'))
            with redirect_stdout(io.StringIO()):self.assertEqual(gate.main(),1)
            self.assertFalse(json.loads((output/'manifest.json').read_text())['complete']);odd.assert_not_called();proof.assert_not_called()

if __name__=='__main__':unittest.main()
