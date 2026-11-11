"""Exact source delta and readable PTX contracts for the v067 experiment. ISC."""
from pathlib import Path
import unittest
from types import SimpleNamespace
from tools import compare_serial_emit as bench
from tools.serial_emit import BACKENDS
ROOT=Path(__file__).resolve().parents[1]

class Contract(unittest.TestCase):
    def test_compute_prefix_is_identical_to_packed_control(self):
        original=(ROOT/'gpu/four_tile_scan.cu').read_text().split('extern "C" __global__ void four_tile_packed_scan',1)[1].split('    unsigned words0[16];',1)[0]
        source=(ROOT/'gpu/serial_emit_scan.cu').read_text()
        for name in ('serial_emit_scan','serial_emit_redux_scan'):
            body=source.split('extern "C" __global__ void '+name,1)[1].split('    if(active0){\n        unsigned words[16];',1)[0]
            self.assertEqual(body.replace('serial_redux_fold(','four_fold('),original)
    def test_sequential_emission_has_all_lane_gather_and_reconvergence(self):
        source=(ROOT/'gpu/serial_emit_scan.cu').read_text()
        for name in ('serial_emit_scan','serial_emit_redux_scan'):
            body=source.split('extern "C" __global__ void '+name,1)[1].split('\nextern "C"',1)[0]
            epilogue=body[body.index('    if(active0){\n        unsigned words[16];'):]
            self.assertNotIn('if(lane)return',epilogue)
            self.assertEqual(epilogue.count('unsigned words[16];'),4)
            self.assertEqual(epilogue.count('__syncwarp(0xffffffffU);'),4)
            for i in range(4):
                self.assertIn(f'word{i},i);\n        if(lane==0)shared_b_emit(words',epilogue)
                self.assertIn(f'ordinal+{i}U-first,generation);',epilogue)
    def test_compiled_entries_abi_tensor_math_and_barriers(self):
        ptx=(ROOT/'releases/pearlhash-dev-v0.0.67-scan-sm120.ptx').read_text()
        self.assertIn('.target sm_120',ptx)
        for name,redux in (('four_tile_packed_scan',0),('serial_emit_scan',0),('serial_emit_redux_scan',4)):
            body=ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertEqual(body.count('mma.sync.'),6)
            self.assertEqual(body.count('redux.sync.xor'),redux)
            self.assertNotIn('bar.sync',body)
    def test_actual_dispatch_selection(self):
        self.assertEqual(tuple(BACKENDS),bench.MODES)
        self.assertEqual([BACKENDS[m].dispatch_type.kernel_entry for m in bench.MODES],
            [b'four_tile_packed_scan',b'serial_emit_scan',b'serial_emit_redux_scan'])
    def test_balanced_order_and_promotion_margin(self):
        self.assertEqual(len(bench.ORDERS),6)
        for position in range(3):
            for mode in bench.MODES:self.assertEqual(sum(order[position]==mode for order in bench.ORDERS)*4,8)
        samples={m:[1.0]*24 for m in bench.MODES};setup={m:0.1 for m in bench.MODES}
        samples[bench.MODES[1]]=[.98]*24
        self.assertEqual(bench.summary(samples,setup)['preferred'],bench.MODES[0])
        samples[bench.MODES[2]]=[.95]*24
        self.assertEqual(bench.summary(samples,setup)['preferred'],bench.MODES[2])
        samples[bench.MODES[2]][0]=float('nan')
        with self.assertRaises(ValueError):bench.summary(samples,setup)
    def test_driver_diagnostic_restores_api_even_after_failure(self):
        def api(*args):raise RuntimeError('driver failure')
        device=SimpleNamespace(api=api)
        with self.assertRaises(RuntimeError):
            with bench.DriverCounts(device):device.api('cuMemcpyDtoH_v2',[],0,0,504)
        self.assertIs(device.api,api)

if __name__=='__main__':unittest.main()
