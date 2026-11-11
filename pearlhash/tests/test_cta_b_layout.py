"""Compile actual CTA traversal/staging helpers; exercise every production ID and partial blocks. ISC."""
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from tools.cta_b_scan import CtaBDispatch,CtaBQueries,cta_canonical_tile,cta_traversal_ordinal,cta_coverage_interval,require_cta_plan
from tools.check_cta_b import canonical_window
from tools.check_prepared_job import synthetic_session
from tools.fast_plan import FastPlan,FastBatch
from tools.four_tile_scan import four_canonical_tile
ROOT=Path(__file__).resolve().parents[1]

class Layout(unittest.TestCase):
    def test_actual_Cpp_full_domain_and_cooperative_buffer_ownership(self):
        source=r'''#include "cta_b_axes.h"
#include <vector>
#include <cstdio>
int main(){
 unsigned long long tiles=0,fragments=0;
 for(unsigned rows:{4U,12U,16U,28U,32U,64U,512U}){
  unsigned cols=rows==512?16384:19,count=rows*cols,period=cta_group(rows)*cols;
  std::vector<unsigned char> seen(count,0);
  for(unsigned i=0;i<count;++i){
   unsigned t=cta_tile_canonical(i,cols,rows);
   if(t>=count||seen[t]++||cta_tile_ordinal(t,cols,rows)!=i||t/period!=i/period)return 1;
   ++tiles;
  }
 }
 for(unsigned steps:{8U,16U}){
  std::vector<unsigned> buffer(steps*4*32),owners(steps*4*32);
  for(unsigned chunk=0;chunk<32768;chunk+=steps*32){
   for(auto &x:owners)x=0;
   for(unsigned warp=0;warp<8;++warp)for(unsigned lane=0;lane<32;++lane)
    for(unsigned s=warp;s<steps;s+=8)for(unsigned f=0;f<4;++f){
     unsigned index=cta_fragment_index(s,f,lane);
     if(index>=buffer.size()||owners[index]++)return 2;
     buffer[index]=((chunk+s*32)*131U)^(f*32+lane);
    }
   for(auto x:owners)if(x!=1)return 3;
   for(unsigned warp=0;warp<8;++warp)for(unsigned s=0;s<steps;++s)
    for(unsigned lane=0;lane<32;++lane)for(unsigned f=0;f<4;++f){
     if(buffer[cta_fragment_index(s,f,lane)]!=(((chunk+s*32)*131U)^(f*32+lane)))return 4;
     ++fragments;
    }
  }
 }
 if(tiles<8388608||fragments!=2097152)return 5;
 std::puts("full production bijection and 2097152 shared fragment reads passed");
}
'''
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp);(path/'check.cpp').write_text(source)
            subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                '-fno-sanitize-recover=all','-I'+str(ROOT/'gpu'),str(path/'check.cpp'),'-o',str(path/'check')],check=True)
            result=subprocess.run([str(path/'check')],check=True,capture_output=True,text=True)
            self.assertIn('2097152 shared fragment reads passed',result.stdout)
    def test_query_ids_and_inverse_match_plan(self):
        session,job,_=synthetic_session(bytes(32));plan=FastPlan.from_job(job)
        try:
            for ordinal in range(plan.count):
                tile=cta_canonical_tile(plan,ordinal)
                self.assertEqual(cta_traversal_ordinal(plan,tile),ordinal)
                query=CtaBQueries(FastBatch(plan,ordinal,ordinal+1))[0]
                self.assertEqual((query.rows,query.cols),plan.indices(tile))
            for ordinal in (-1,plan.count,True):
                with self.assertRaises(ValueError):cta_canonical_tile(plan,ordinal)
            self.assertEqual(cta_coverage_interval(plan,0,plan.count),(0,plan.count))
            with self.assertRaises(ValueError):cta_coverage_interval(plan,1,plan.count)
            with self.assertRaises(ValueError):require_cta_plan(replace(plan,rows=plan.rows[:3]))
        finally:session.close()
    def test_every_partial_block_keeps_all_threads_and_exact_output_interval(self):
        dispatch=object.__new__(CtaBDispatch)
        for members in (4,12,16,28,32):
            dispatch.plan=SimpleNamespace(rows=tuple(range(members)))
            for first in range(64):
                for count in (1,2,5,7,31,32,33,67,4096):
                    found=[]
                    for block in range(dispatch.grid(count,first)):
                        block_first=(first//members)*members+block*members
                        for warp in range(8):
                            ordinal=block_first+warp*4
                            live=warp*4<members and ordinal<first+count and ordinal+4>first
                            if live:
                                for t in range(4):
                                    if first<=ordinal+t<first+count:found.append(ordinal+t)
                    self.assertEqual(found,list(range(first,first+count)))
    def test_canonical_reordering_against_actual_control_traversal(self):
        session,job,_=synthetic_session(bytes(32));plan=FastPlan.from_job(job)
        device=SimpleNamespace(last_transcripts=None)
        class Dispatch:
            def prepare_window(self,batch):return batch
            def scan_window(self,batch,prepared,generation,**kwargs):
                device.last_transcripts=tuple((four_canonical_tile(plan,i),)*16 for i in range(batch.start,batch.stop))
                return SimpleNamespace(total=0)
        d=Dispatch();d.device=device;control=SimpleNamespace(plan=plan,backend=SimpleNamespace(dispatch=d))
        try:
            for first,count in ((0,67),(5,7),(plan.count-67,67)):
                batch=FastBatch(plan,first,first+count)
                self.assertEqual(canonical_window(control,batch,job.generation),tuple((cta_canonical_tile(plan,i),)*16 for i in range(first,first+count)))
        finally:session.close()

if __name__=='__main__':unittest.main()
