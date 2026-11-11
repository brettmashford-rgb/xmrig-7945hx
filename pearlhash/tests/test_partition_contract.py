"""Preserve v068 addressing/math/guards and inspect actual v071 PTX. ISC."""
from pathlib import Path
import re
import unittest
from tools import compare_partition as bench
from tools.partition_scan import BACKENDS
ROOT=Path(__file__).resolve().parents[1]

def function(source,name):
    return source.split('extern "C" __global__ void '+name+'(PH_BQ_ARGS) {',1)[1].split('\n}\n',1)[0]

def loop(body):
    lines=body.splitlines();labels={line.rstrip(':'):i for i,line in enumerate(lines)if line.startswith('$L__')and line.endswith(':')};edges=[]
    for i,line in enumerate(lines):
        match=re.search(r'bra\s+(\$L__[\w_]+);',line)
        if match and match[1]in labels and labels[match[1]]<i and any('mma.sync.'in value for value in lines[labels[match[1]]:i]):
            edges.append((i-labels[match[1]],labels[match[1]],i))
    _,start,stop=max(edges);return '\n'.join(lines[start:stop+1])

class Contract(unittest.TestCase):
    def test_only_native_fold_helper_changes_in_native_candidate(self):
        old=function((ROOT/'gpu/hoisted_a_scan.cu').read_text(),'hoisted_a_pointer_scan')
        new=function((ROOT/'gpu/partition_scan.cu').read_text(),'native_pointer_scan')
        self.assertEqual(new,old.replace(')four_fold(',')native_four_fold('))
    def test_partition_guards_B_A_MMA_and_emission_preserved(self):
        old=function((ROOT/'gpu/hoisted_a_scan.cu').read_text(),'hoisted_a_pointer_scan')
        new=function((ROOT/'gpu/partition_scan.cu').read_text(),'partition_pointer_scan')
        old_prefix=old.split('        if((offset+32)%128==0){')[0]
        new_prefix=new.split('        if((offset+32)%128==0){')[0]
        self.assertEqual(new_prefix,old_prefix.replace('unsigned word0=0,word1=0,word2=0,word3=0,group=lane/4,thread=lane%4;','unsigned transcript_low=0,transcript_high=0,group=lane/4,thread=lane%4;'))
        self.assertEqual(new.split('    if(lane)return;',1)[1],old.split('    if(lane)return;',1)[1])
        self.assertIn('if(offset+32U<32768U){\n            ap0+=8U;ap1+=8U;ap2+=8U;ap3+=8U;ap4+=8U;',new)
        for tile in range(4):
            self.assertIn(f'if(active{tile})words{tile}[i]=__shfl_sync(0xffffffffU,i<8U?transcript_low:transcript_high,partition_source({tile}U,i));',new)
        header=(ROOT/'gpu/partition_fold.h').read_text()
        self.assertIn('for(unsigned delta=1;delta<=2;delta*=2)',header)
        self.assertIn('for(unsigned delta=4;delta<=16;delta*=2)',header)
        self.assertIn('partition_store(value,lane,slot,low,high);',header)
    def test_compiled_24_slots_six_MMA_and_static_shuffle_savings(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.71-scan-sm120.ptx').read_text()
        for name,shuffles,redux in (('hoisted_a_pointer_scan',28,0),('partition_pointer_scan',19,0),('native_pointer_scan',8,4)):
            body=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertNotIn('bar.sync',body)
            code=loop(body)
            self.assertEqual(code.count('mma.sync.'),6)
            self.assertEqual(code.count('shfl.sync'),shuffles)
            self.assertEqual(code.count('redux.sync.xor'),redux)
            self.assertEqual(code.count('ld.global'),12)
            self.assertEqual(code.count('mul.wide'),5)
    def test_actual_modes_balanced_orders_and_promotion_threshold(self):
        self.assertEqual(tuple(BACKENDS),bench.MODES)
        self.assertEqual([BACKENDS[m].dispatch_type.kernel_entry for m in bench.MODES],[b'hoisted_a_pointer_scan',b'partition_pointer_scan',b'native_pointer_scan'])
        for position in range(3):
            for mode in bench.MODES:self.assertEqual(sum(order[position]==mode for order in bench.ORDERS)*4,8)
        samples={m:[1.]*24 for m in bench.MODES};setup={m:.1 for m in bench.MODES}
        samples[bench.MODES[1]]=[.98]*24
        self.assertEqual(bench.summary(samples,setup)['preferred'],bench.MODES[0])
        samples[bench.MODES[2]]=[.9]*24
        self.assertEqual(bench.summary(samples,setup)['preferred'],bench.MODES[2])
        samples[bench.MODES[1]][0]=float('nan')
        with self.assertRaises(ValueError):bench.summary(samples,setup)

if __name__=='__main__':unittest.main()
