"""Actual GPU ABI, scoped barriers, producer roles and panel layout contracts. ISC."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]

class Contract(unittest.TestCase):
    def test_PTX_ABI_MMA_and_barrier_changes(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.73-scan-sm120.ptx').read_text()
        for name in ('cta_b8_scan','small4_scan','small8_scan','pipeline_scan','panel_scan'):
            body=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertEqual(body.count('mma.sync.'),6)
            if name=='panel_scan':self.assertNotIn('bar.sync',body);self.assertIn('bar.red',body)
            else:self.assertGreaterEqual(body.count('bar.sync'),3)
        producer=raw.split('.visible .entry build_b_panel(',1)[1].split('.visible .entry ',1)[0]
        self.assertEqual(producer.split(')')[0].count('.param '),6);self.assertNotIn('mma.sync',producer)
    def test_pipeline_consumes_current_and_produces_other_buffer(self):
        source=(ROOT/'gpu/experiments_scan.cu').read_text().split('void pipeline_body(',1)[1].split('extern "C" __global__ void pipeline_scan',1)[0]
        self.assertIn('blockDim.x!=320',source);self.assertIn('bool consumer=physical>=2U;',source)
        self.assertIn('bool live=consumer&&',source);self.assertIn('if(consumer&&warp*4U<members)',source)
        self.assertIn('if(__syncthreads_or(invalid))return;',source)
        self.assertIn('fragments+(current^1U)*1024U',source);self.assertIn('fragments+current*1024U',source)
        loop=source.split('for(unsigned chunk=0;chunk<32768U;chunk+=256U){',1)[1].split('    unsigned words0[16];',1)[0]
        self.assertEqual(loop.count('__syncthreads();'),1);self.assertNotIn('return;',loop)
        self.assertIn('if(!consumer&&chunk+256U<32768U)',loop)
    def test_materialized_B_has_aligned_fragment_header_and_validity_words(self):
        source=(ROOT/'gpu/experiments_scan.cu').read_text()
        producer=source.split('void build_b_panel(',1)[1].split('void panel_body(',1)[0]
        consumer=source.split('void panel_body(',1)[1]
        self.assertIn('out[col]=invalid?0U:1U',producer);self.assertIn('out+28U+col*131072U',producer)
        self.assertIn('reinterpret_cast<const unsigned*>(ub)+28U+col*131072U',consumer)
        self.assertNotIn('b_transpose6_fragments(',consumer)
        self.assertEqual((16+28*4)%128,0)
    def test_small_blocks_keep_four_query_accumulators(self):
        source=(ROOT/'gpu/experiments_scan.cu').read_text().split('void small_body(',1)[1].split('extern "C" __global__ void small4_scan',1)[0]
        self.assertIn('blockDim.x!=128',source);self.assertIn('step+=4U',source)
        self.assertEqual(source.count('mma_accumulate('),6)
        self.assertIn('(row_count<16U?row_count:16U)',source)
        self.assertIn('if(offset+32U<32768U)',source)

if __name__=='__main__':unittest.main()
