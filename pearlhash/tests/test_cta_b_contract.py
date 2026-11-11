"""Preserve v068 math/epilogue and prevent per-warp returns across CTA barriers. ISC."""
from pathlib import Path
import unittest
from tools import compare_cta_b as bench
from tools.cta_b_scan import BACKENDS
ROOT=Path(__file__).resolve().parents[1]

class Contract(unittest.TestCase):
    def test_compute_and_epilogue_are_verbatim_v068(self):
        old=(ROOT/'gpu/hoisted_a_scan.cu').read_text().split('extern "C" __global__ void hoisted_a_pointer_scan(PH_BQ_ARGS) {',1)[1].split('\n}\n',1)[0]
        new=(ROOT/'gpu/cta_b_scan.cu').read_text()
        marker='        {\n            unsigned x0=ap0'
        compute=old[old.index(marker):old.index('    unsigned words0[16];')].rsplit('    }\n',1)[0]
        self.assertIn(compute,new)
        self.assertIn(old[old.index('    unsigned words0[16];'):],new)
        self.assertEqual(new.count('mma_accumulate('),6)
    def test_block_uniform_validation_before_barriers_and_no_early_warp_exit(self):
        new=(ROOT/'gpu/cta_b_scan.cu').read_text()
        guard=new.index('if(__syncthreads_or(invalid))return;')
        cache=new.index('__syncthreads();',guard)
        self.assertNotIn('if(!live)return',new)
        self.assertNotIn('if(ordinal>=first+query_count)return',new)
        self.assertIn('if(warp*4U<members)',new[:guard])
        loop=new[cache:new.index('    unsigned words0[16];')]
        self.assertNotIn('return;',loop)
        self.assertEqual(loop.count('__syncthreads();'),3)
        self.assertIn('for(unsigned step=warp;step<Steps;step+=8U)',loop)
    def test_actual_PTX_ABI_barriers_and_six_MMA_per_variant(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.70-scan-sm120.ptx').read_text()
        for name in ('hoisted_a_pointer_scan','cta_b8_scan','cta_b16_scan'):
            body=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertEqual(body.count('mma.sync.'),6)
            if name=='hoisted_a_pointer_scan':self.assertNotIn('bar.sync',body)
            else:
                self.assertGreaterEqual(body.count('bar.sync'),3)
                self.assertIn('bar.red',body)
    def test_two_balanced_permutations_fit_one_nonce_and_promotion_needs_margin(self):
        self.assertEqual(tuple(BACKENDS),bench.MODES)
        self.assertEqual([BACKENDS[m].dispatch_type.kernel_entry for m in bench.MODES],[b'hoisted_a_pointer_scan',b'cta_b8_scan',b'cta_b16_scan'])
        self.assertEqual((bench.ROUNDS,bench.WINDOW),(12,524288))
        self.assertLessEqual((bench.ROUNDS+2)*bench.WINDOW,512*16384)
        for pos in range(3):
            for mode in bench.MODES:self.assertEqual(sum(order[pos]==mode for order in bench.ORDERS)*2,4)
        samples={m:[1.]*12 for m in bench.MODES};setup={m:.1 for m in bench.MODES}
        samples[bench.MODES[1]]=[.98]*12
        self.assertEqual(bench.summary(samples,setup)['preferred'],bench.MODES[0])
        samples[bench.MODES[2]]=[.9]*12
        self.assertEqual(bench.summary(samples,setup)['preferred'],bench.MODES[2])

if __name__=='__main__':unittest.main()
