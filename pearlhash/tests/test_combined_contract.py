"""Exact winning-source preservation and actual compiled combination contracts. ISC."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from tools import compare_combined as bench
from tools.combined_scan import BACKENDS,new_combined_search
from tools.four_tile_scan import FourSearch
from tools.cta_b_scan import CtaBSearch
from test_partition_contract import loop
import test_combined as lifecycle
ROOT=Path(__file__).resolve().parents[1]

def device_function(source,name):
    return source.split('extern "C" __global__ void '+name+'(PH_BQ_ARGS) {',1)[1].split('\n}\n',1)[0]

class Contract(unittest.TestCase):
    def test_actual_partition_control_is_identical_to_v071(self):
        original=(ROOT/'gpu/partition_scan.cu').read_text();new=(ROOT/'gpu/combined_scan.cu').read_text()
        self.assertEqual(device_function(original,'partition_pointer_scan'),device_function(new,'partition_pointer_scan'))
        self.assertIn('#include "cta_b_scan.cu"',new)
        self.assertIn('#include "partition_fold.h"',new)
    def test_combination_changes_only_transcript_storage_fold_and_gather_in_v070_body(self):
        old=(ROOT/'gpu/cta_b_scan.cu').read_text().split('template<unsigned Steps>',1)[1].split('\nextern "C"',1)[0]
        new=(ROOT/'gpu/combined_scan.cu').read_text().split('template<unsigned Steps>',1)[1].split('\nextern "C"',1)[0]
        old=old.replace('cta_b_body','combined_body').replace('unsigned word0=0,word1=0,word2=0,word3=0,group=lane/4,thread=lane%4;','unsigned transcript_low=0,transcript_high=0,group=lane/4,thread=lane%4;')
        self.assertEqual(new.split('            if(active0)four_fold(',1)[0].split('            unsigned v0=',1)[0],old.split('            if(active0)four_fold(',1)[0])
        # Every row/MMA/pointer update and all barriers before/after the fold stay intact.
        self.assertEqual(new.split('        if(offset+32U<32768U){',1)[1].split('    unsigned words0[16];',1)[0],old.split('        if(offset+32U<32768U){',1)[1].split('    unsigned words0[16];',1)[0])
        self.assertEqual(new.split('    if(lane)return;',1)[1],old.split('    if(lane)return;',1)[1])
        for tile in range(4):
            expected='^'.join(f'four_fold_value({slab}U,group,{tile}U,low{slab},high{slab})'for slab in range(3))
            self.assertIn(f'unsigned v{tile}={expected};',new)
            self.assertIn(f'if(active{tile})words{tile}[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source({tile}U,i));',new)
        self.assertEqual(new.count('__syncthreads();'),3)
        self.assertIn('if(__syncthreads_or(invalid))return;',new)
        self.assertNotIn('if(!live)return',new)
        self.assertIn('partition_fold(v0,v1,v2,v3,lane,slot,transcript_low,transcript_high);',new)
    def test_actual_PTX_six_MMA_24_slots_7KiB_and_reduced_fold(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.72-scan-sm120.ptx').read_text()
        for name,shuffle,barriers in (('cta_b8_scan',28,3),('partition_pointer_scan',19,0),('combined_scan',19,3)):
            body=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertEqual(body.count('bar.sync'),barriers)
            code=loop(body);self.assertEqual(code.count('mma.sync.'),6);self.assertEqual(code.count('shfl.sync'),shuffle)
            if name=='combined_scan':
                self.assertIn('uniform_cache[3072]',body);self.assertIn('fragments[4096]',body);self.assertIn('bar.red',body)
    def test_combined_must_beat_faster_control_by_margin(self):
        setup={m:0.1 for m in bench.MODES}
        def choose(a,b,c):return bench.summary({m:[v]*12 for m,v in zip(bench.MODES,(a,b,c))},setup)
        self.assertEqual(choose(1.,.95,.96)['preferred'],'partition-v071')
        self.assertEqual(choose(1.,.95,.94)['preferred'],'partition-v071')
        self.assertEqual(choose(1.,.95,.90)['preferred'],'combined-v072')
        self.assertEqual(choose(1.,1.05,.98)['preferred'],'cta8-v070')
        result=choose(1.,.95,.90)
        self.assertAlmostEqual(result['speedup_over_v070']['combined-v072'],1/.9)
        self.assertAlmostEqual(result['speedup_over_v071']['combined-v072'],.95/.9)
        with self.assertRaises(ValueError):choose(1.,.95,float('nan'))
    def test_balanced_orders_and_unique_work_fit_single_nonce(self):
        self.assertEqual(tuple(BACKENDS),bench.MODES)
        self.assertEqual((bench.ROUNDS,bench.WINDOW),(12,524288))
        self.assertLessEqual((bench.ROUNDS+2)*bench.WINDOW,512*16384)
        for position in range(3):
            for mode in bench.MODES:self.assertEqual(sum(order[position]==mode for order in bench.ORDERS)*2,4)

class Bindings(unittest.TestCase):
    maps=True
    setUp=lifecycle.Offset.setUp
    tearDown=lifecycle.Offset.tearDown
    def test_actual_entries_distinct_traversals_and_exclusive_owners(self):
        for mode,kind,entry in (('cta8-v070',CtaBSearch,b'cta_b8_scan'),('partition-v071',FourSearch,b'partition_pointer_scan'),('combined-v072',CtaBSearch,b'combined_scan')):
            with new_combined_search(self.context,self.device,self.session.is_current,self.b,self.owner,mode=mode)as search:
                self.assertIs(type(search),kind)
                self.assertEqual(search.backend.dispatch.kernel_entry,entry)
                self.assertIs(search.plan,self.owner.plan)
                self.assertTrue(self.owner.leased);self.assertTrue(self.b.leased)
            self.assertFalse(self.owner.leased);self.assertFalse(self.b.leased)

if __name__=='__main__':unittest.main()
