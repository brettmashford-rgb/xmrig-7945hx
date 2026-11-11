"""Exact preserved compute and readable PTX contracts for the v068 experiment. ISC."""
from pathlib import Path
import unittest
import re
from types import SimpleNamespace
from tools import compare_hoisted_a as bench
from tools.hoisted_a_scan import BACKENDS
ROOT=Path(__file__).resolve().parents[1]

class Contract(unittest.TestCase):
    def test_unchanged_fold_and_concurrent_epilogue(self):
        original=(ROOT/'gpu/four_tile_scan.cu').read_text().split('extern "C" __global__ void four_tile_packed_scan',1)[1]
        source=(ROOT/'gpu/hoisted_a_scan.cu').read_text()
        for name in ('hoisted_a_offset_scan','hoisted_a_pointer_scan'):
            body=source.split('extern "C" __global__ void '+name,1)[1].split('\nextern "C"',1)[0]
            self.assertEqual(body.split('    unsigned words0[16];',1)[1].split('\n#undef',1)[0].strip(),original.split('    unsigned words0[16];',1)[1].split('\n#undef',1)[0].strip())
            fold=body.split('        if((offset+32)%128==0){',1)[1].split('        }',1)[0]
            self.assertEqual(fold,original.split('        if((offset+32)%128==0){',1)[1].split('        }',1)[0])
            self.assertEqual(body.split('    __syncwarp(0xffffffffU);',1)[0],original.split('    __syncwarp(0xffffffffU);',1)[0])
            loop=body.split('for(unsigned offset=0;offset<32768;offset+=32){',1)[1].split('    unsigned words0[16];',1)[0]
            self.assertNotIn('row_axes',loop);self.assertNotIn('four_a_word',loop)
            self.assertIn('b_transpose6_fragments(cache,pb,offset,lane,b0,b1,c0,c1);',loop)
            self.assertEqual(loop.count('mma_accumulate('),6)
        pointer=source.split('extern "C" __global__ void hoisted_a_pointer_scan',1)[1]
        self.assertIn('if(offset+32U<32768U){',pointer)
    def test_compiled_entries_abi_tensor_math_and_barriers(self):
        ptx=(ROOT/'releases/pearlhash-dev-v0.0.68-scan-sm120.ptx').read_text()
        self.assertIn('.target sm_120',ptx)
        for name,redux in (('four_tile_packed_scan',0),('hoisted_a_offset_scan',0),('hoisted_a_pointer_scan',0)):
            body=ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertEqual(body.count('mma.sync.'),6)
            self.assertEqual(body.count('redux.sync.xor'),redux)
            self.assertNotIn('bar.sync',body)
    def test_compiled_K_loop_removes_five_repeated_map_loads(self):
        ptx=(ROOT/'releases/pearlhash-dev-v0.0.68-scan-sm120.ptx').read_text()
        counts=[];multiplies=[]
        for name in ('four_tile_packed_scan','hoisted_a_offset_scan','hoisted_a_pointer_scan'):
            lines=ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].splitlines()
            labels={line.rstrip(':'):i for i,line in enumerate(lines)if line.startswith('$L__')and line.endswith(':')}
            edges=[]
            for i,line in enumerate(lines):
                match=re.search(r'bra\s+(\$L__[\w_]+);',line)
                if match and match[1]in labels and labels[match[1]]<i and any('mma.sync.'in value for value in lines[labels[match[1]]:i]):
                    edges.append((i-labels[match[1]],labels[match[1]],i))
            _,start,stop=max(edges);loop='\n'.join(lines[start:stop+1])
            self.assertEqual(loop.count('mma.sync.'),6)
            counts.append(loop.count('ld.global'));multiplies.append(loop.count('mul.wide'))
        self.assertEqual(counts,[17,12,12]);self.assertEqual(multiplies,[13,11,5])
    def test_actual_dispatch_selection(self):
        self.assertEqual(tuple(BACKENDS),bench.MODES)
        self.assertEqual([BACKENDS[m].dispatch_type.kernel_entry for m in bench.MODES],
            [b'four_tile_packed_scan',b'hoisted_a_offset_scan',b'hoisted_a_pointer_scan'])
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
