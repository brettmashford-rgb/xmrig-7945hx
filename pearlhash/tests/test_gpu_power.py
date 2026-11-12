"""NVML C ABI and GPU binding, energy integration, gap rejection and sampler lifecycle. ISC."""
import ctypes as C
import math
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch
from tools.gpu_power import NvmlReader,PowerSampler,TelemetryError,Utilization,summarize

def sample(t,power=100):return dict(monotonic_seconds=t,power_w=power,gpu_activity_pct=90,memory_activity_pct=20,
    sm_clock_mhz=2400,memory_clock_mhz=14000,temperature_c=60,power_limit_w=145,pstate=0,clock_event_bits=4)
class Power(unittest.TestCase):
    def rows(self):return [sample(i*.2,80+i*.5)for i in range(51)]
    def test_known_variable_power_energy_integrated(self):
        r=summarize(self.rows(),10000);self.assertTrue(r['available']);self.assertAlmostEqual(r['energy_joules'],925)
        self.assertAlmostEqual(r['average_power_w'],92.5);self.assertAlmostEqual(r['tiles_per_joule'],10000/925)
        self.assertEqual(r['average_gpu_activity_pct'],90);self.assertEqual(r['clock_limit_time_fraction']['software_power_cap'],1)
        self.assertEqual(r['clock_limit_time_fraction']['software_thermal_slowdown'],0)
    def test_short_gapped_missing_or_invalid_power_never_claim_efficiency(self):
        for rows in ([sample(0),sample(.1)],[sample(0),sample(6)],[],[sample(0)],
            [dict(row,power_w=None)for row in self.rows()],[dict(row,power_w=float('nan'))for row in self.rows()]):
            self.assertFalse(summarize(rows,10)['available'])
    def test_optional_metrics_missing_do_not_invent_zeroes(self):
        rows=[dict(row,sm_clock_mhz=None,clock_event_bits=None)for row in self.rows()];r=summarize(rows,100)
        self.assertTrue(r['available']);self.assertIsNone(r['average_sm_clock_mhz']);self.assertIsNone(r['clock_limit_time_fraction']['software_power_cap'])
    def test_nonmonotonic_timestamps_rejected(self):
        for rows in ([sample(1),sample(1)],[sample(1),sample(0)],[sample(float('nan')),sample(5)]):
            with self.assertRaises(ValueError):summarize(rows,100)
    def test_sampler_stops_after_work_exception(self):
        reader=SimpleNamespace(read=lambda:{k:v for k,v in sample(0).items()if k!='monotonic_seconds'})
        sampler=PowerSampler(reader,.002)
        def work():time.sleep(.01);raise RuntimeError('scan failed')
        with self.assertRaisesRegex(RuntimeError,'scan failed'):sampler.measure(work,100)
        self.assertFalse(sampler.thread.is_alive());self.assertTrue(sampler.stop_event.is_set());self.assertGreaterEqual(len(sampler.samples),2)
    def test_sampler_read_failure_cannot_mask_scan_failure(self):
        calls=[0]
        def read():
            calls[0]+=1
            if calls[0]>1:raise TelemetryError('sensor failed')
            return sample(0)
        sampler=PowerSampler(SimpleNamespace(read=read))
        def work():raise RuntimeError('scan failed')
        with self.assertRaisesRegex(RuntimeError,'scan failed'):sampler.measure(work,100)
        self.assertFalse(sampler.thread.is_alive())
    def fake_nvml(self,missing_power=False):
        calls=[]
        def make(name):
            def fn(*args):
                calls.append(name)
                if name=='nvmlDeviceGetHandleByPciBusId_v2':
                    self.assertEqual(args[0],b'0000:03:00.0');C.cast(args[1],C.POINTER(C.c_void_p))[0]=C.c_void_p(7)
                elif name=='nvmlDeviceGetUtilizationRates':C.cast(args[-1],C.POINTER(Utilization))[0]=Utilization(91,22)
                elif name not in ('nvmlInit_v2','nvmlShutdown'):
                    if missing_power and name=='nvmlDeviceGetPowerUsage':return 3
                    value={'nvmlDeviceGetPowerUsage':100000,'nvmlDeviceGetEnforcedPowerLimit':145000,'nvmlDeviceGetClockInfo':2400,
                        'nvmlDeviceGetTemperature':60,'nvmlDeviceGetPerformanceState':0,'nvmlDeviceGetCurrentClocksThrottleReasons':4}[name]
                    typ=C.c_ulonglong if name.endswith('Reasons')else C.c_uint;C.cast(args[-1],C.POINTER(typ))[0]=typ(value)
                return 0
            return fn
        names=('nvmlInit_v2','nvmlShutdown','nvmlDeviceGetHandleByPciBusId_v2','nvmlDeviceGetPowerUsage','nvmlDeviceGetEnforcedPowerLimit',
            'nvmlDeviceGetUtilizationRates','nvmlDeviceGetClockInfo','nvmlDeviceGetTemperature','nvmlDeviceGetPerformanceState','nvmlDeviceGetCurrentClocksThrottleReasons')
        lib=SimpleNamespace(**{name:make(name)for name in names})
        def api(name,types,*args):
            if name=='cuCtxGetDevice':C.cast(args[0],C.POINTER(C.c_int))[0]=C.c_int(0)
            elif name=='cuDeviceGetPCIBusId':C.memmove(args[0],b'0000:03:00.0\0',13)
            else:raise AssertionError(name)
        return lib,SimpleNamespace(api=api),calls
    def test_actual_ctypes_reader_matches_CUDA_PCI_and_converts_milliwatts(self):
        lib,device,calls=self.fake_nvml()
        with patch('tools.gpu_power.C.CDLL',return_value=lib):
            reader=NvmlReader(device);r=reader.read();reader.close();reader.close()
        self.assertEqual(r['power_w'],100);self.assertEqual(r['power_limit_w'],145);self.assertEqual(r['gpu_activity_pct'],91)
        self.assertEqual(r['clock_event_bits'],4);self.assertEqual(calls.count('nvmlShutdown'),1)
        self.assertFalse(any('Set'in name for name in calls))
    def test_missing_power_marks_unavailable_and_library_missing_is_clear(self):
        lib,device,calls=self.fake_nvml(True)
        with patch('tools.gpu_power.C.CDLL',return_value=lib):
            reader=NvmlReader(device)
            try:
                with self.assertRaises(TelemetryError):reader.read()
            finally:reader.close()
        with patch('tools.gpu_power.C.CDLL',side_effect=OSError('missing NVML')):
            with self.assertRaisesRegex(TelemetryError,'missing NVML'):NvmlReader(device)
if __name__=='__main__':unittest.main()
