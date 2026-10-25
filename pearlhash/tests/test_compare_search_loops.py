"""Equal-range live window cadence and uninstrumented primary timing logic. ISC."""
from types import SimpleNamespace
import unittest
from tools.compare_search_loops import run_window,summary,DriverCounts,MODES,ROUNDS,WINDOW,production_session


class Compare(unittest.TestCase):
    def test_both_modes_cover_same_range_using_live_window_sizes(self):
        for mode,step in zip(MODES,(4096,8192)):
            calls=[];cursor=SimpleNamespace(next_tile=123)
            def advance(n):calls.append(n);cursor.next_tile+=n;return None,cursor
            search=SimpleNamespace(cursor=cursor,advance=advance)
            self.assertEqual(run_window(search,mode),(123,123+WINDOW))
            self.assertEqual(calls,[step]*(WINDOW//step))
    def test_odd_tail_and_bad_cursor_cannot_be_credited(self):
        cursor=SimpleNamespace(next_tile=0);calls=[]
        def advance(n):calls.append(n);cursor.next_tile+=n;return None,cursor
        self.assertEqual(run_window(SimpleNamespace(cursor=cursor,advance=advance),'two-streams',8193),(0,8193))
        self.assertEqual(calls,[8192,1])
        with self.assertRaises(RuntimeError):run_window(SimpleNamespace(cursor=cursor,advance=lambda n:(None,cursor)),'one-stream',1)
    def test_candidate_fails_controlled_miss_comparison(self):
        cursor=SimpleNamespace(next_tile=1)
        with self.assertRaises(RuntimeError):run_window(SimpleNamespace(cursor=cursor,advance=lambda n:(object(),cursor)),'one-stream',1)
    def test_median_choice_requires_three_percent_margin(self):
        setup={m:.1 for m in MODES}
        samples={'one-stream':[1.]*ROUNDS,'two-streams':[.98]*ROUNDS}
        self.assertEqual(summary(samples,setup)['preferred'],'one-stream')
        samples['two-streams']=[.8]*ROUNDS
        self.assertEqual(summary(samples,setup)['preferred'],'two-streams')
        samples['two-streams'][-1]=float('nan')
        with self.assertRaises(ValueError):summary(samples,setup)
    def test_counter_restores_driver_on_error_and_records_bytes(self):
        calls=[];original=lambda name,types,*args:calls.append(name)
        device=SimpleNamespace(api=original)
        with self.assertRaises(RuntimeError):
            with DriverCounts(device)as counter:
                device.api('cuMemcpyDtoH_v2',[],None,None,44)
                device.api('cuLaunchKernel',[])
                raise RuntimeError('test')
        self.assertIs(device.api,original)
        self.assertEqual(counter.report()['copy_bytes'],{'cuMemcpyDtoH_v2':44})
    def test_synthetic_session_is_production_and_current_without_network(self):
        session,job=production_session()
        try:
            self.assertEqual((job.profile.m,job.profile.n),(5121,262144))
            self.assertTrue(session.is_current(job));self.assertEqual(job.assigned_extranonce,b'TESTWORK')
        finally:session.close()


if __name__=='__main__':unittest.main()
