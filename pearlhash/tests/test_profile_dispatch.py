"""CUDA timing instrumentation lifecycle with a fake driver, no GPU. ISC."""
from collections import defaultdict
import ctypes as C
import unittest
from unittest.mock import patch

from tools.cuda_driver import CudaDevice
from tools.profile_dispatch import ProfileScanner, summarize


class ProfileTests(unittest.TestCase):
    def scanner(self):
        obj = object.__new__(ProfileScanner)
        obj.profiling = False; obj.events = [C.c_void_p(1), C.c_void_p(2)]
        obj.host = defaultdict(float); obj.counts = defaultdict(int); obj.launches = 0
        return obj

    def test_event_order_host_accounting_and_gpu_clock_are_separate(self):
        device = self.scanner(); calls = []
        def driver(self, name, types, *args):
            calls.append(name)
            if name == 'cuEventElapsedTime':
                C.cast(args[0], C.POINTER(C.c_float))[0] = 25.
        def operation():
            for name in ('cuMemAlloc_v2', 'cuMemcpyHtoD_v2', 'cuLaunchKernel',
                         'cuCtxSynchronize', 'cuMemcpyDtoH_v2', 'cuMemFree_v2'):
                device.api(name, [])
            return 'result'
        with patch.object(CudaDevice, 'api', driver):
            result, measurement = device.measure(operation)
        self.assertEqual(result, 'result')
        self.assertAlmostEqual(measurement['gpu_event_seconds'], .025)
        self.assertAlmostEqual(sum(measurement['host_seconds'].values()), measurement['wall_seconds'])
        launch = calls.index('cuLaunchKernel')
        self.assertEqual(calls[launch-1:launch+2], ['cuEventRecord','cuLaunchKernel','cuEventRecord'])
        self.assertLess(calls.index('cuCtxSynchronize'), calls.index('cuEventElapsedTime'))
        self.assertNotIn('cuEventRecord', measurement['api_counts'])
        self.assertEqual(measurement['api_counts']['cuLaunchKernel'], 1)
        self.assertFalse(device.profiling)

    def test_operation_failure_disables_profiling(self):
        device = self.scanner()
        with self.assertRaisesRegex(RuntimeError, 'test failure'):
            device.measure(lambda: (_ for _ in ()).throw(RuntimeError('test failure')))
        self.assertFalse(device.profiling)

    def test_multiple_kernels_and_overlapping_host_buckets_are_rejected(self):
        device = self.scanner()
        with patch.object(CudaDevice, 'api', return_value=None):
            def operation():
                device.api('cuLaunchKernel', []); device.api('cuLaunchKernel', [])
            with self.assertRaisesRegex(RuntimeError, 'exactly one'):
                device.measure(operation)
        with self.assertRaisesRegex(RuntimeError, 'overlapping'):
            summarize(.1, {'allocation': .2}, {}, .3)


if __name__ == '__main__':
    unittest.main()
