"""Exact four-step control, stage parameterisation and all-K fragment/checkpoint coverage. ISC."""
from pathlib import Path
import re,subprocess,tempfile
from types import SimpleNamespace
import unittest
from tools.pair_depth_scan import MODES,DEPTHS,THREADS,canonical,inverse
from tools.a_share_scan import canonical as previous
from tools.check_pair_depth import argument_parser
ROOT=Path(__file__).resolve().parents[1]
class Contract(unittest.TestCase):
    def test_real_parser_and_identical_paired_traversal(self):
        for mode in MODES:
            args=argument_parser().parse_args(['--module','m','--commitment-module','c','--oracle','o','--output-dir','d','--mode',mode]);self.assertEqual(args.mode,mode)
            self.assertEqual(THREADS[mode],256)
        self.assertEqual([DEPTHS[m]for m in MODES],[4,2,8])
        for rows in (4,8,12,16,32,64):
            for cols in (1,3,5,12,32):
                plan=SimpleNamespace(rows=range(rows),cols=range(cols),count=rows*cols)
                for mode in MODES:
                    for i in range(plan.count):
                        tile=canonical(plan,mode,i);self.assertEqual(tile,previous(plan,'pair-direct',i));self.assertEqual(inverse(plan,mode,tile),i)
    def test_entire_candidate_body_is_parameterised_original_with_direct_A(self):
        old=(ROOT/'gpu/a_share_scan.cu').read_text().split('template<bool ShareA>',1)[1].split('extern "C" __global__ void a_pair_direct_scan',1)[0]
        expected=old.replace('a_pair_body','pair_depth_body').replace('constexpr unsigned Steps=4;','constexpr bool ShareA=false;')
        a=expected.index('        unsigned producer_column=');b=expected.index('        if constexpr(ShareA){',a)
        expected=expected[:a]+'''        unsigned producer_column=warp/4U;
        #pragma unroll
        for(unsigned producer_step=warp%4U;producer_step<Steps;producer_step+=4U){
            unsigned b0=0,b1=0,c0=0,c1=0;
            if(producer_column<width)
                b_transpose6_fragments(uniform_cache[producer_column],pb,chunk+producer_step*32U,lane,b0,b1,c0,c1);
            fragments[pair_depth_b_index(producer_column,producer_step,0U,lane,Steps)]=b0;
            fragments[pair_depth_b_index(producer_column,producer_step,1U,lane,Steps)]=b1;
            fragments[pair_depth_b_index(producer_column,producer_step,2U,lane,Steps)]=c0;
            fragments[pair_depth_b_index(producer_column,producer_step,3U,lane,Steps)]=c1;
        }
'''+expected[b:]
        for i in range(4):expected=expected.replace(f'a_pair_b_index(column_lane,step,{i}U,lane)',f'pair_depth_b_index(column_lane,step,{i}U,lane,Steps)')
        new=(ROOT/'gpu/pair_depth_scan.cu').read_text().split('template<unsigned Steps>',1)[1].split('extern "C" __global__ void pair_step2_scan',1)[0]
        self.assertEqual(new,expected)
    def test_compiled_control_ABI_MMA_and_shared_memory(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.80-scan-sm120.ptx').read_text();old=(ROOT/'releases/pearlhash-dev-v0.0.79-scan-sm120.ptx').read_text()
        def entry(ptx,name):return ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].split('\n\t// .globl',1)[0]
        for name,shared in [('a_pair_direct_scan',10240),('pair_step2_scan',8192),('pair_step8_scan',14336)]:
            body=entry(raw,name);self.assertEqual(body.split(')')[0].count('.param '),24);self.assertEqual(body.count('mma.sync'),6)
            self.assertGreaterEqual(body.count('bar.sync'),3)
            self.assertEqual(sum(map(int,re.findall(r'\.shared \.align 4 \.b8 [^\n]+\[(\d+)\];',body))),shared)
        self.assertEqual(entry(raw,'a_pair_direct_scan'),entry(old,'a_pair_direct_scan'))
        self.assertEqual(entry(raw,'resident_guard_snapshot'),entry(old,'resident_guard_snapshot'))
    def test_compiled_stage_coverage_operands_final_A_bounds_and_all_256_checkpoints(self):
        source=r'''
#include "a_share_axes.h"
#include "pair_depth_axes.h"
#include <vector>
#include <cassert>
static unsigned word(unsigned side,unsigned offset,unsigned fragment,unsigned lane){return (offset*2654435761U)^(side*789221U)^(fragment*123471U)^(lane*9001U);}
int main(){
 for(unsigned side=0;side<2;++side)for(unsigned step=0;step<4;++step)for(unsigned f=0;f<4;++f)for(unsigned lane=0;lane<32;++lane)
  assert(pair_depth_b_index(side,step,f,lane,4)==a_pair_b_index(side,step,f,lane));
 for(unsigned depth: {2U,4U,8U}){
  unsigned next_A_word=0;std::vector<unsigned> checkpoints;
  for(unsigned chunk=0;chunk<32768;chunk+=depth*32){
   std::vector<unsigned> stage(2*depth*4*32),seen(stage.size());
   for(unsigned warp=0;warp<8;++warp)for(unsigned step=warp%4;step<depth;step+=4)for(unsigned f=0;f<4;++f)for(unsigned lane=0;lane<32;++lane){
    unsigned side=warp/4,index=pair_depth_b_index(side,step,f,lane,depth);
    assert(index<stage.size()&&!seen[index]);seen[index]=1;
    stage[index]=word(side,chunk+step*32,f,lane);
   }
   for(auto value:seen)assert(value==1);
   for(unsigned step=0;step<depth;++step){
    unsigned offset=chunk+step*32;assert(offset<32768&&next_A_word==offset/4);
    // Both column groups' quartet consumers read the exact flat-reference B fragment.
    for(unsigned q=0;q<4;++q)for(unsigned side=0;side<2;++side)for(unsigned f=0;f<4;++f)for(unsigned lane=0;lane<32;++lane)
     assert(stage[pair_depth_b_index(side,step,f,lane,depth)]==word(side,offset,f,lane));
    // Include final physical row: every per-lane low/high K32 word remains in bounds.
    for(unsigned thread=0;thread<4;++thread)for(unsigned high: {0U,4U})assert(5120U*8192U+thread+next_A_word+high<5121U*8192U);
    if((offset+32)%128==0)checkpoints.push_back(offset+32);
    if(offset+32<32768)next_A_word+=8;
   }
  }
  assert(next_A_word==8184&&checkpoints.size()==256);
  for(unsigned i=0;i<checkpoints.size();++i)assert(checkpoints[i]==(i+1)*128);
 }
}
'''
        with tempfile.TemporaryDirectory()as tmp:
            cpp=Path(tmp)/'contract.cpp';out=Path(tmp)/'contract';cpp.write_text(source)
            subprocess.run(['g++','-O2','-std=c++17','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'gpu'),str(cpp),'-o',str(out)],check=True,capture_output=True)
            subprocess.run([str(out)],check=True,capture_output=True,timeout=30)
if __name__=='__main__':unittest.main()
