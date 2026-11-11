"""Exact source delta and readable PTX contracts for the v069 experiment. ISC."""
from pathlib import Path
import unittest
from types import SimpleNamespace
from tools import compare_eight_tile as bench
from tools.eight_tile_scan import BACKENDS
ROOT=Path(__file__).resolve().parents[1]

class Contract(unittest.TestCase):
    def test_compiled_entries_abi_tensor_math_and_barriers(self):
        ptx=(ROOT/'releases/pearlhash-dev-v0.0.69-scan-sm120.ptx').read_text()
        self.assertIn('.target sm_120',ptx)
        for name,mma in (('hoisted_a_pointer_scan',6),('eight_tile_packed_scan',10),('eight_tile_serial_scan',10)):
            body=ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertEqual(body.count('mma.sync.'),mma)
            self.assertNotIn('bar.sync',body)
    def test_both_modes_share_exact_five_slab_compute_and_guards(self):
        source=(ROOT/'gpu/eight_tile_scan.cu').read_text()
        packed=source.split('extern "C" __global__ void eight_tile_packed_scan',1)[1].split('    unsigned words0[16];',1)[0]
        serial=source.split('extern "C" __global__ void eight_tile_serial_scan',1)[1].split('    if(active0){\n        unsigned words[16];',1)[0]
        self.assertEqual(packed,serial)
        self.assertIn('(row_count&7U)',packed);self.assertIn('t<8',packed)
        self.assertEqual(packed.count('mma_accumulate('),10)
        self.assertEqual(packed.count('four_fold('),8)
        self.assertEqual(packed.count('+=8U;'),10)
        self.assertIn('if(offset+32U<32768U){',packed)
        for i in range(8):self.assertIn(f'active{i}=ordinal+{i}U>=first&&ordinal+{i}U<first+query_count;',packed)
        epilogue=source.split('    if(active0){\n        unsigned words[16];',1)[1]
        self.assertNotIn('if(lane)return',epilogue)
        self.assertEqual(epilogue.count('__syncwarp(0xffffffffU);'),8)
    def test_actual_dispatch_selection(self):
        self.assertEqual(tuple(BACKENDS),bench.MODES)
        self.assertEqual([BACKENDS[m].dispatch_type.kernel_entry for m in bench.MODES],
            [b'hoisted_a_pointer_scan',b'eight_tile_packed_scan',b'eight_tile_serial_scan'])
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
