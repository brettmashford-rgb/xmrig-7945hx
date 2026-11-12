"""Separate clocks, exact event placement and restoration after profiling faults. ISC."""
import ctypes as C
from types import SimpleNamespace
import unittest
from tools.dispatch_profile import profile_control


class Profile(unittest.TestCase):
    def exercise(self,fail=False):
        calls=[];waits=[];events=[]
        def api(name,types,*args):
            calls.append((name,args))
            if name=='cuEventCreate':
                value=len(events)+100;events.append(value);C.cast(args[0],C.POINTER(C.c_void_p))[0]=value
            if name=='cuEventElapsedTime':C.cast(args[0],C.POINTER(C.c_float))[0]=1.
        device=SimpleNamespace(api=api);d=SimpleNamespace(device=device,stream=C.c_void_p(1),function=C.c_void_p(77),wait=lambda:waits.append(True))
        cursor=SimpleNamespace(next_tile=0)
        def advance(tiles):
            device.api('cuMemsetD32Async',[])
            device.api('cuLaunchKernel',[],C.c_void_p(77))
            if fail:raise RuntimeError('profile work failed')
            device.api('cuLaunchKernel',[],C.c_void_p(88))
            device.api('cuStreamSynchronize',[]);device.api('cuMemcpyDtoH_v2',[])
            cursor.next_tile+=tiles;return None,cursor
        search=SimpleNamespace(backend=SimpleNamespace(dispatch=d),cursor=cursor,advance=advance)
        if fail:
            with self.assertRaisesRegex(RuntimeError,'work failed'):profile_control(search,2)
        else:
            report=profile_control(search,2)
            self.assertEqual(report['windows'],2);self.assertEqual(report['tiles'],32768)
            self.assertEqual(report['scanner_event_seconds'],.002)
            self.assertEqual(report['api_counts'],dict(cuMemsetD32Async=2,cuLaunchKernel=4,cuStreamSynchronize=2,cuMemcpyDtoH_v2=2))
            self.assertGreaterEqual(report['python_and_bookkeeping_seconds'],0)
            self.assertAlmostEqual(report['wall_seconds'],sum(report['host_api_seconds'].values())+report['event_instrumentation_seconds']+report['python_and_bookkeeping_seconds'])
            names=[name for name,args in calls]
            first=names.index('cuMemsetD32Async');self.assertEqual(names[first:first+6],['cuMemsetD32Async','cuEventRecord','cuLaunchKernel','cuEventRecord','cuLaunchKernel','cuStreamSynchronize'])
        self.assertIs(device.api,api);self.assertEqual(len(waits),1)
        self.assertEqual(sum(n=='cuEventDestroy_v2'for n,a in calls),2)
    def test_profile_clocks_are_separate_and_control_counts_unchanged(self):self.exercise()
    def test_work_failure_restores_API_and_destroys_events(self):self.exercise(True)

if __name__=='__main__':unittest.main()
