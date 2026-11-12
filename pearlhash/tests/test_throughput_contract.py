"""Exact arithmetic, compiled controls, full mapping coverage and enlarged ABI limits. ISC."""
from pathlib import Path
from types import SimpleNamespace
import subprocess,tempfile
import unittest
from tools.check_throughput import argument_parser
from tools.throughput_scan import MODES,THREADS,LIMITS,WIDTHS,canonical,inverse
ROOT=Path(__file__).resolve().parents[1]
class Contract(unittest.TestCase):
    def test_all_actual_parser_modes_and_mode_sizes(self):
        for mode in MODES:
            args=argument_parser().parse_args(['--module','m','--commitment-module','c','--oracle','o','--output-dir','d','--mode',mode])
            self.assertEqual(args.mode,mode)
        self.assertEqual([THREADS[m]for m in MODES],[256,512,256,256])
        self.assertEqual([LIMITS[m]for m in MODES],[16384,16384,32768,65536])
    def test_only_block_shape_and_traversal_change_in_candidate_body(self):
        reference=(ROOT/'gpu/cta_b_scan.cu').read_text().split('template<unsigned Steps>',1)[1].split('extern "C" __global__ void cta_b8_scan',1)[0]
        expected=reference.replace('cta_b_body','block64_body').replace('blockDim.x!=256','blockDim.x!=512').replace('(row_count>32&&(row_count&31U))','(row_count>64&&(row_count&63U))')
        expected=expected.replace('cta_group(row_count)','throughput_group(row_count,64U)').replace('cta_tile_column(block_ordinal,column_count,row_count)','throughput_col(block_ordinal,column_count,row_count,64U)').replace('cta_tile_row(block_ordinal,column_count,row_count)','throughput_row(block_ordinal,column_count,row_count,64U)').replace('i+=256','i+=512').replace('step+=8U','step+=16U')
        candidate=(ROOT/'gpu/throughput_scan.cu').read_text().split('template<unsigned Steps>',1)[1].split('extern "C" __global__ void block64_scan',1)[0]
        self.assertEqual(candidate,expected)
    def test_PTX_ABI_control_unchanged_and_extended_snapshot(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.78-scan-sm120.ptx').read_text()
        old=(ROOT/'releases/pearlhash-dev-v0.0.75-scan-sm120.ptx').read_text()
        def entry(ptx,name):return ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].split('\n\t// .globl',1)[0]
        for name in ('cta_b8_scan','block64_scan'):
            body=entry(raw,name);self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertEqual(body.count('mma.sync'),6);self.assertGreaterEqual(body.count('bar.sync'),3)
        self.assertEqual(entry(raw,'cta_b8_scan'),entry(old,'cta_b8_scan'))
        body=entry(raw,'resident_guard_snapshot');self.assertEqual(body.split(')')[0].count('.param '),7)
        self.assertRegex(body,r'\b65536\b|\b65537\b|\b65535\b')
    def test_python_mapping_matches_canonical_definition_at_partial_boundaries(self):
        for rows in (4,8,16,32,64,128,512):
            cols=31;plan=SimpleNamespace(rows=range(rows),cols=range(cols),count=rows*cols)
            for mode in MODES:
                width=min(rows,WIDTHS[mode])
                for ordinal in range(plan.count):
                    tile=canonical(plan,mode,ordinal)
                    row=width*((ordinal//width)//cols)+ordinal%width
                    self.assertEqual(tile,row*cols+(ordinal//width)%cols);self.assertEqual(inverse(plan,mode,tile),ordinal)
    def test_compiled_helper_full_production_bijections_equal_windows_and_boundaries(self):
        source=r'''
#include "throughput_axes.h"
#include <vector>
#include <cassert>
int main(){
 for(unsigned width: {32U,64U}){
  const unsigned rows=512,cols=16384,count=rows*cols,period=64*cols;
  std::vector<unsigned char> seen(count);
  for(unsigned i=0;i<count;++i){
   unsigned tile=throughput_canonical(i,cols,rows,width);
   assert(tile<count&&!seen[tile]);seen[tile]=1;
   assert(throughput_inverse(tile,cols,rows,width)==i);
   assert(tile/period==i/period);
  }
 }
 for(unsigned count=0;count<=65537;++count){
  assert(throughput_snapshot_valid(128,28,count)==(count>=1&&count<=65536));
  assert(!throughput_snapshot_valid(256,28,count));
 }
 for(unsigned guards=0;guards<=65;++guards)
  assert(throughput_snapshot_valid(128,guards,65536)==(guards>=1&&guards<=64));
}
'''
        with tempfile.TemporaryDirectory()as tmp:
            cpp=Path(tmp)/'contract.cpp';out=Path(tmp)/'contract';cpp.write_text(source)
            subprocess.run(['g++','-O2','-std=c++17','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'gpu'),str(cpp),'-o',str(out)],check=True,capture_output=True)
            subprocess.run([str(out)],check=True,capture_output=True,timeout=30)
if __name__=='__main__':unittest.main()
