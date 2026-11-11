"""Balanced lifecycle timing, setup amortization and actual host Driver API orchestration. ISC."""
from collections import Counter
from contextlib import ExitStack
import ctypes as C
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pool.search import prepare_base
from tools.check_prepared_job import synthetic_session
from tools.compare_job_geometry import MODES,ORDERS,ROUNDS,WINDOW,summary,run_window
from tools import compare_job_geometry as runner
from test_job_b_tables import Device

class RealGuardDevice(Device):
    def guarded(self,size):
        raw=self.allocate(b'\xa5'*(size+32));return raw,C.c_ulonglong(raw.value+16)
    def start(self,module):pass
    def close(self):
        for pointer in reversed(list(self.allocations)):self.release(pointer)

class Comparison(unittest.TestCase):
    def samples(self):
        return ({m:[1.]*ROUNDS for m in MODES},
            {m:[dict(setup=.5,search=.4,close=.1)for _ in range(ROUNDS)]for m in MODES},{m:0. for m in MODES})
    def test_balanced_all_six_orders(self):
        self.assertEqual(len(ORDERS),6);self.assertEqual(ROUNDS%6,0)
        for pos in range(3):self.assertEqual(Counter(order[pos]for order in ORDERS),Counter({m:2 for m in MODES}))
    def test_preference_charges_initial_geometry_build_and_requires_margin(self):
        samples,stages,setup=self.samples();samples[MODES[2]]=[.8]*ROUNDS;setup[MODES[2]]=5.
        self.assertEqual(summary(samples,stages,setup)['preferred'],MODES[0])
        setup[MODES[2]]=.2;result=summary(samples,stages,setup)
        self.assertEqual(result['preferred'],MODES[2]);self.assertEqual(result['unique_timed_tiles_per_mode'],WINDOW*ROUNDS)
        self.assertAlmostEqual(result['total_seconds_including_geometry'][MODES[2]],19.4)
        samples[MODES[2]]=[.98]*ROUNDS;self.assertEqual(summary(samples,stages,setup)['preferred'],MODES[0])
    def test_invalid_and_incomplete_timings_reject(self):
        for bad in ([1.]*(ROUNDS-1),[float('nan')]*ROUNDS,[0.]*ROUNDS,[True]*ROUNDS):
            samples,stages,setup=self.samples();samples[MODES[1]]=bad
            with self.assertRaises(ValueError):summary(samples,stages,setup)
        samples,stages,setup=self.samples();setup[MODES[1]]=float('inf')
        with self.assertRaises(ValueError):summary(samples,stages,setup)
    def test_sixteen_exact_windows_and_miss_cursor_required(self):
        from types import SimpleNamespace
        class Search:
            def __init__(self):self.cursor=SimpleNamespace(next_tile=0);self.steps=[]
            def advance(self,amount):self.steps.append(amount);self.cursor.next_tile+=amount;return None,self.cursor
        search=Search();self.assertEqual(run_window(search),WINDOW);self.assertEqual(search.steps,[4096]*16)
    def test_full_benchmark_orchestration_with_real_allocation_upload_accounting(self):
        session,job,message=synthetic_session(bytes(32));message['result'][2]=(1).to_bytes(32,'little').hex();job=session.consume(message)
        device=RealGuardDevice()
        def windows(search):
            for _ in range(16):
                hit,cursor=search.advance(8);self.assertIsNone(hit)
            self.assertEqual(cursor.next_tile,128);return 128
        with tempfile.TemporaryDirectory()as temp,ExitStack()as stack:
            path=Path(temp)/'report.json'
            stack.enter_context(patch.object(runner,'production_session',return_value=(session,job)))
            stack.enter_context(patch.object(runner,'prepare_gpu_base',side_effect=lambda j,c,m:prepare_base(j,c)))
            stack.enter_context(patch.object(runner,'ProductionCandidateScanner',return_value=device))
            stack.enter_context(patch.object(runner,'WINDOW',128))
            stack.enter_context(patch.object(runner,'run_window',side_effect=windows))
            stack.enter_context(patch('sys.argv',['compare','--module','unused','--commitment-module','unused','--report',str(path)]))
            self.assertEqual(runner.main(),0)
            report=json.loads(path.read_text());self.assertTrue(report['complete'])
            self.assertTrue(report['readback_contract_checked']);self.assertTrue(report['map_upload_savings_checked'])
            self.assertEqual(set(report['geometry_owners']),set(MODES[1:]))
            self.assertEqual(report['geometry_owners'][MODES[2]]['geometry_leases'],26)
            d=report['setup_driver_diagnostic'];self.assertEqual(d['saved_host_upload_bytes_per_reused_nonce'],2*d['map_payload_bytes']+64)
            self.assertEqual(device.allocations,[])

if __name__=='__main__':unittest.main()
