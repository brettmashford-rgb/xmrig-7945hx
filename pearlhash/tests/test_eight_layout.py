"""Actual octet mapping/load/fold helpers, exhaustive production coverage and partial windows. ISC."""
from pathlib import Path
from dataclasses import replace
import random
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from tools.eight_tile_scan import (EightDispatch,EightQueries,eight_canonical_tile,eight_traversal_ordinal,
    eight_coverage_interval,require_eight_plan)
from tools.four_tile_scan import four_canonical_tile
from tools.fast_plan import FastPlan,FastBatch
from tools.check_prepared_job import synthetic_session
from tools.check_eight_tile import canonical_window
ROOT=Path(__file__).resolve().parents[1]

class Layout(unittest.TestCase):
    def test_actual_Cpp_full_domain_five_slabs_and_every_A_fragment(self):
        helper=(ROOT/'gpu/eight_tile_scan.cu').read_text().split('__device__ __forceinline__ const unsigned *eight_a_pointer',1)[1].split('extern "C"',1)[0]
        source='''#include "eight_tile_axes.h"
#include <vector>
#include <cstdint>
#include <cstdio>
'''+ 'inline const unsigned *eight_a_pointer'+helper+'''
int main(){
 constexpr unsigned count=512*16384,period=8*16384;
 std::vector<unsigned char> seen(count,0);
 for(unsigned ord=0;ord<count;++ord){
  unsigned tile=eight_tile_canonical(ord,16384);
  if(tile>=count||seen[tile]++||eight_tile_ordinal(tile,16384)!=ord||tile/period!=ord/period)return 1;
 }
 unsigned ownership[8]={};
 for(unsigned slab=0;slab<5;++slab)for(unsigned group=0;group<8;++group){
  unsigned low=1U<<(group%31),high=1U<<((group+8)%31);
  unsigned hits=0;
  for(unsigned owner=0;owner<8;++owner){
   unsigned a=slab*16+group,b=a+8;
   unsigned expected=(a/10==owner?low:0U)^(b/10==owner?high:0U);
   if(eight_fold_value(slab,group,owner,low,high)!=expected)return 2;
   if(a/10==owner){++ownership[owner];++hits;}
   if(b/10==owner){++ownership[owner];++hits;}
  }
  if(hits!=2)return 3;
 }
 for(auto owned:ownership)if(owned!=10)return 4;
 constexpr unsigned rows=257;
 std::vector<unsigned> data(rows*8192),axes(512*32);
 uint32_t state=123456789;
 auto next=[&](){state^=state<<13;state^=state>>17;state^=state<<5;return state;};
 for(auto &v:data)v=next();for(auto &v:axes)v=next()%rows;
 for(unsigned i=0;i<10;++i)axes[511*32+i]=rows-1;
 auto *input=reinterpret_cast<const signed char*>(data.data());
 unsigned long long checked=0;
 for(unsigned base:{0U,8U,504U})for(unsigned group=0;group<8;++group)for(unsigned thread=0;thread<4;++thread){
  const unsigned *pointers[10];
  for(unsigned slab=0;slab<10;++slab)pointers[slab]=eight_a_pointer(input,axes.data(),base,slab*8+group,thread);
  for(unsigned offset=0;offset<32768;offset+=32){
   for(unsigned slab=0;slab<10;++slab)for(unsigned add:{0U,16U}){
    unsigned packed=slab*8+group,row=axes[(base+packed/10)*32+packed%10];
    unsigned expected=data[row*8192+offset/4+thread+add/4];
    if(expected!=pointers[slab][add/4])return 5;++checked;
   }
   if(offset+32U<32768U)for(auto &ptr:pointers)ptr+=8U;
  }
 }
 if(checked!=1966080ULL)return 6;
 std::puts("8388608 canonical IDs and 1966080 A fragments passed");
}
'''
        with tempfile.TemporaryDirectory()as temp:
            folder=Path(temp);(folder/'test.cpp').write_text(source)
            subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'gpu'),str(folder/'test.cpp'),'-o',str(folder/'test')],check=True)
            result=subprocess.run([str(folder/'test')],check=True,capture_output=True,text=True)
            self.assertIn('8388608 canonical IDs and 1966080 A fragments passed',result.stdout)
    def test_python_mapping_inverse_queries_and_non_octet_rejections(self):
        session,job,_=synthetic_session(bytes(32));plan=FastPlan.from_job(job)
        try:
            for ordinal in range(plan.count):
                tile=eight_canonical_tile(plan,ordinal)
                self.assertEqual(eight_traversal_ordinal(plan,tile),ordinal)
                batch=FastBatch(plan,ordinal,ordinal+1)
                q=EightQueries(batch)[0]
                self.assertEqual((q.rows,q.cols),plan.indices(tile))
            for ordinal in (-1,plan.count,True):
                with self.assertRaises(ValueError):eight_canonical_tile(plan,ordinal)
            with self.assertRaises(ValueError):require_eight_plan(replace(plan,rows=plan.rows[:12]))
            with self.assertRaises(ValueError):eight_coverage_interval(plan,1,plan.count)
            self.assertEqual(eight_coverage_interval(plan,0,plan.count),(0,plan.count))
        finally:session.close()
    def test_every_partial_octet_is_covered_once_by_launch_grid(self):
        dispatch=object.__new__(EightDispatch)
        for first in range(128):
            for count in (1,2,5,7,8,9,63,64,65,67,4096):
                covered=[]
                for block in range(dispatch.grid(count,first)):
                    for warp in range(8):
                        ordinal=(first&~7)+(block*8+warp)*8
                        for member in range(8):
                            query=ordinal+member
                            if first<=query<first+count:covered.append(query)
                self.assertEqual(covered,list(range(first,first+count)))
    def test_reordered_actual_control_windows_compare_canonical_IDs(self):
        session,job,_=synthetic_session(bytes(32));plan=FastPlan.from_job(job)
        device=SimpleNamespace(last_transcripts=None);calls=[]
        class Dispatch:
            def prepare_window(self,batch):return batch
            def scan_window(self,batch,prepared,generation,**kwargs):
                calls.append((batch.start,batch.stop));self.device.last_transcripts=tuple((four_canonical_tile(plan,i),)*16 for i in range(batch.start,batch.stop))
                return SimpleNamespace(total=0)
        dispatch=Dispatch();dispatch.device=device;control=SimpleNamespace(plan=plan,backend=SimpleNamespace(dispatch=dispatch))
        try:
            for first,count in ((0,67),(5,7),(8*len(plan.cols)-7,67),(plan.count-67,67)):
                batch=FastBatch(plan,first,first+count);words=canonical_window(control,batch,job.generation)
                self.assertEqual(words,tuple((eight_canonical_tile(plan,i),)*16 for i in range(first,first+count)))
            self.assertTrue(calls)
        finally:session.close()

if __name__=='__main__':unittest.main()
