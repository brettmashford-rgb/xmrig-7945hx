"""Preserved arithmetic, paired traversal, shared operands and compiled ABI. ISC."""
from pathlib import Path
import re,subprocess,tempfile
from types import SimpleNamespace
import unittest
from tools.a_share_scan import MODES,THREADS,canonical,inverse,pair_block,Dispatch
from tools.check_a_share import argument_parser,odd_column_session
from reference.tile_ranges import PatternDomain
ROOT=Path(__file__).resolve().parents[1]
class Contract(unittest.TestCase):
    def test_actual_parser_and_odd_profile(self):
        for mode in MODES:
            args=argument_parser().parse_args(['--module','m','--commitment-module','c','--oracle','o','--output-dir','d','--mode',mode]);self.assertEqual(args.mode,mode)
            self.assertEqual(THREADS[mode],256)
        session,job=odd_column_session(bytes(32))
        try:self.assertEqual(PatternDomain(job.profile.n,job.profile.cols).count,3)
        finally:session.close()
    def test_unchanged_MMA_fold_and_emission_with_exact_A_operand_substitution(self):
        old=(ROOT/'gpu/cta_b_scan.cu').read_text();new=(ROOT/'gpu/a_share_scan.cu').read_text()
        def mma(source):return source.split('        {\n            unsigned x0=',1)[1].split('        if((offset+32)%128==0){',1)[0]
        candidate=re.sub(r'ShareA\?a_stage\[a_share_index\(quartet,step,\d+U,lane\)\]:','',mma(new))
        self.assertEqual(candidate,mma(old))
        def fold(source,end):return source.split('        if((offset+32)%128==0){',1)[1].split(end,1)[0]
        self.assertEqual(fold(old,'        if(offset+32U<32768U){'),fold(new,'        if(!ShareA&&offset+32U<32768U){'))
        def emit(source):return source.split('    unsigned words0[16];',1)[1].split('extern "C" __global__',1)[0]
        self.assertEqual(emit(old),emit(new))
        self.assertIn('bool a_loader=rows_exist&&(ShareA?column_lane==0U:live);',new)
        self.assertIn('if(a_loader&&chunk+Steps*32U<32768U)',new)
        self.assertIn('unsigned off=step*8U;',new)
    def test_compiled_ABI_control_and_shared_memory(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.79-scan-sm120.ptx').read_text()
        old=(ROOT/'releases/pearlhash-dev-v0.0.75-scan-sm120.ptx').read_text()
        def entry(ptx,name):return ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].split('\n\t// .globl',1)[0]
        for name,shared in [('cta_b8_scan',7168),('a_pair_direct_scan',10240),('a_pair_shared_scan',30720)]:
            body=entry(raw,name);self.assertEqual(body.split(')')[0].count('.param '),24);self.assertEqual(body.count('mma.sync'),6)
            self.assertGreaterEqual(body.count('bar.sync'),3)
            self.assertEqual(sum(map(int,re.findall(r'\.shared \.align 4 \.b8 [^\n]+\[(\d+)\];',body))),shared)
        self.assertEqual(entry(raw,'cta_b8_scan'),entry(old,'cta_b8_scan'))
        self.assertEqual(entry(raw,'resident_guard_snapshot'),entry(old,'resident_guard_snapshot'))
    def test_python_mapping_odd_column_counts_and_dispatch_grid(self):
        for rows in (4,8,12,16,32,64):
            for cols in (1,3,5,12,32):
                plan=SimpleNamespace(rows=range(rows),cols=range(cols),count=rows*cols)
                for mode in MODES:
                    result=[canonical(plan,mode,i)for i in range(plan.count)]
                    self.assertEqual(sorted(result),list(range(plan.count)))
                    for i,tile in enumerate(result):self.assertEqual(inverse(plan,mode,tile),i)
                    for first in range(plan.count):
                        for count in (1,min(17,plan.count-first),plan.count-first):
                            if mode!='wide16k':
                                d=SimpleNamespace(mode=mode,plan=plan)
                                self.assertEqual(Dispatch.grid(d,count,first),pair_block(plan,first+count-1)-pair_block(plan,first)+1)
    def test_compiled_full_bijection_partial_masks_and_all_K_shared_operands(self):
        source=r'''
#include "a_share_axes.h"
#include "hoisted_a.h"
#include <vector>
#include <cassert>
#include <cstdint>
static uint32_t word(unsigned address){return address*2654435761U^(address>>11)^0x76543210U;}
int main(){
 const unsigned rows=512,cols=16384,count=rows*cols,period=32*cols;
 std::vector<unsigned char> seen(count);
 for(unsigned i=0;i<count;++i){
  unsigned tile=a_pair_canonical(i,rows,cols);assert(tile<count&&!seen[tile]);seen[tile]=1;
  assert(a_pair_inverse(tile,rows,cols)==i);assert(tile/period==i/period);
 }
 for(unsigned rows: {4U,8U,12U,16U,32U,64U})for(unsigned cols: {1U,3U,5U}){
  unsigned count=rows*cols,m=a_pair_members(rows);
  std::vector<unsigned char> check(count);
  for(unsigned i=0;i<count;++i){unsigned tile=a_pair_canonical(i,rows,cols);assert(tile<count&&!check[tile]);check[tile]=1;assert(a_pair_inverse(tile,rows,cols)==i);}
  for(unsigned first=0;first<count;++first)for(unsigned size=1;size<=count-first;size+=7){
   unsigned stop=first+size;std::vector<unsigned char> got(size);
   for(unsigned b=a_pair_block(first,rows,cols);b<=a_pair_block(stop-1,rows,cols);++b){
    unsigned start=a_pair_first(b,rows,cols),width=a_pair_col_base(b,cols)+1<cols?2:1;
    for(unsigned q=0;q<4;++q)for(unsigned side=0;side<2;++side)for(unsigned t=0;t<4;++t){
     unsigned ordinal=start+side*m+q*4+t;
     if(q*4>=m||side>=width||ordinal<first||ordinal>=stop)continue;
     assert(!got[ordinal-first]);got[ordinal-first]=1;
     // The even producer exists even when the first requested ordinal is in side one.
     assert(q*4<m);
    }
   }
   for(auto value:got)assert(value==1);
  }
 }
 std::vector<unsigned char> a_seen(5120),b_seen(1024);
 for(unsigned q=0;q<4;++q)for(unsigned s=0;s<4;++s)for(unsigned i=0;i<10;++i)for(unsigned lane=0;lane<32;++lane){
  unsigned index=a_share_index(q,s,i,lane);assert(index<5120&&!a_seen[index]);a_seen[index]=1;
 }
 for(unsigned col=0;col<2;++col)for(unsigned s=0;s<4;++s)for(unsigned f=0;f<4;++f)for(unsigned lane=0;lane<32;++lane){
  unsigned index=a_pair_b_index(col,s,f,lane);assert(index<1024&&!b_seen[index]);b_seen[index]=1;
 }
 unsigned axes[16*32]={};for(unsigned i=0;i<16;++i)for(unsigned j=0;j<10;++j)axes[i*32+j]=((i*10+j)*97+31)%5121;
 axes[15*32+9]=5120; // Include the final physical A row, with nonmonotone maps elsewhere.
 const unsigned packed[10]={0,8,0,8,16,24,16,24,32,32};
 const unsigned extra[10]={0,0,4,4,0,0,4,4,0,4};
 unsigned stage[5120];uint64_t global_loads=0,shared_reads=0;
 for(unsigned chunk=0;chunk<32768;chunk+=128){
  for(unsigned q=0;q<4;++q)for(unsigned s=0;s<4;++s)for(unsigned i=0;i<10;++i)for(unsigned lane=0;lane<32;++lane){
   unsigned row=packed[i]+lane/4;
   unsigned address=hoisted_a_base(axes,q*4,row,lane%4)+chunk/4+s*8+extra[i];
   assert(address<5121*8192);stage[a_share_index(q,s,i,lane)]=word(address);++global_loads;
  }
  for(unsigned side=0;side<2;++side)for(unsigned q=0;q<4;++q)for(unsigned s=0;s<4;++s)for(unsigned i=0;i<10;++i)for(unsigned lane=0;lane<32;++lane){
   unsigned row=packed[i]+lane/4;
   unsigned address=axes[(q*4+row/10)*32+row%10]*8192+lane%4+chunk/4+s*8+extra[i];
   assert(stage[a_share_index(q,s,i,lane)]==word(address));++shared_reads;
  }
 }
 assert(global_loads==1310720&&shared_reads==2*global_loads);
}
'''
        with tempfile.TemporaryDirectory()as tmp:
            cpp=Path(tmp)/'contract.cpp';out=Path(tmp)/'contract';cpp.write_text(source)
            subprocess.run(['g++','-O2','-std=c++17','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'gpu'),str(cpp),'-o',str(out)],check=True,capture_output=True)
            subprocess.run([str(out)],check=True,capture_output=True,timeout=30)
if __name__=='__main__':unittest.main()
