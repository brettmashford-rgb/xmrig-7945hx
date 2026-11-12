"""Full-domain C++/Python bijection, partial blocks, producer ownership and unchanged arithmetic. ISC."""
from pathlib import Path
import re,subprocess,tempfile,unittest
from types import SimpleNamespace
from tools.layout_width_scan import MODES,COLUMNS,canonical,inverse,pair_block
ROOT=Path(__file__).resolve().parents[1]
class Contract(unittest.TestCase):
 def test_python_partial_columns_and_block_extents(self):
  for rows in (4,8,16,32,64,512):
   for cols in (1,2,3,5,7,8,9,16,33):
    plan=SimpleNamespace(rows=range(rows),cols=range(cols),count=rows*cols)
    for mode in MODES:
     mapped=[canonical(plan,mode,i)for i in range(plan.count)]
     self.assertEqual(sorted(mapped),list(range(plan.count)))
     for i,tile in enumerate(mapped):self.assertEqual(inverse(plan,mode,tile),i)
     blocks=[pair_block(plan,mode,i)for i in range(plan.count)]
     self.assertEqual(set(blocks),set(range(max(blocks)+1)))
 def test_arithmetic_pointer_advancement_and_checkpoint_body_unchanged(self):
  old=(ROOT/'gpu/pair_depth_scan.cu').read_text();new=(ROOT/'gpu/layout_width_scan.cu').read_text()
  a='        if constexpr(ShareA){';b='extern "C" __global__'
  self.assertEqual(old.split(a,1)[1].split(b,1)[0],new.split(a,1)[1].split(b,1)[0])
  for required in ('column_lane=warp%Columns,quartet=warp/Columns','producer_column=warp%Columns','producer_step=warp/Columns','producer_step+=8U/Columns','constexpr unsigned Steps=4;','fragments[Columns*Steps*4*32]'):
   self.assertIn(required,new)
 def test_ptx_control_unchanged_and_candidate_resources(self):
  raw=(ROOT/'releases/pearlhash-dev-v0.0.81-scan-sm120.ptx').read_text();old=(ROOT/'releases/pearlhash-dev-v0.0.80-scan-sm120.ptx').read_text()
  def entry(ptx,name):return ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].split('\n\t// .globl',1)[0]
  for name,shared in [('a_pair_direct_scan',10240),('layout_col4_scan',20480),('layout_col8_scan',40960)]:
   body=entry(raw,name);self.assertEqual(body.split(')')[0].count('.param '),24);self.assertEqual(body.count('mma.sync'),6)
   self.assertGreaterEqual(body.count('bar.sync'),3)
   self.assertEqual(sum(map(int,re.findall(r'\.shared \.align 4 \.b8 [^\n]+\[(\d+)\];',body))),shared)
  for name in ('a_pair_direct_scan','resident_guard_snapshot'):self.assertEqual(entry(raw,name),entry(old,name))
 def test_compiled_full_domain_equal_timed_sets_and_all_producer_fragments(self):
  code=r'''
#include "layout_width_axes.h"
#include "a_share_axes.h"
#include "pair_depth_axes.h"
#include <cassert>
#include <vector>
int main(){
 for(unsigned columns:{2U,4U,8U}){
  std::vector<unsigned char> seen(8388608);
  for(unsigned ordinal=0;ordinal<8388608;++ordinal){
   unsigned tile=lw_canonical(ordinal,512,16384,columns);
   assert(tile<seen.size()&&!seen[tile]);seen[tile]=1;
   assert(lw_inverse(tile,512,16384,columns)==ordinal);
   if(columns==2)assert(tile==a_pair_canonical(ordinal,512,16384));
   // Each 524288-tile benchmark interval is exactly the same canonical row band.
   assert(tile/524288==ordinal/524288);
  }
  for(unsigned rows:{4U,8U,16U,32U,512U})for(unsigned cols:{1U,3U,5U,9U,16384U}){
   unsigned members=lw_members(rows,columns);
   for(unsigned block=0;block<(rows/members)*((cols+columns-1)/columns);++block){
    unsigned first=lw_first(block,rows,cols,columns),rb=lw_row_base(block,rows,cols,columns),cb=lw_col_base(block,cols,columns);
    unsigned width=cols-cb<columns?cols-cb:columns;
    for(unsigned warp=0;warp<8;++warp)for(unsigned tile=0;tile<4;++tile){
     unsigned side=warp%columns,quartet=warp/columns;
     if(side>=width||quartet*4>=members)continue;
     unsigned ordinal=first+side*members+quartet*4+tile;
     assert(lw_block(ordinal,rows,cols,columns)==block);
     assert(lw_canonical(ordinal,rows,cols,columns)==(rb+quartet*4+tile)*cols+cb+side);
    }
   }
  }
  for(unsigned chunk=0;chunk<32768;chunk+=128){
   std::vector<unsigned> stage(columns*4*4*32),count(stage.size());
   for(unsigned warp=0;warp<8;++warp)for(unsigned step=warp/columns;step<4;step+=8/columns)
    for(unsigned f=0;f<4;++f)for(unsigned lane=0;lane<32;++lane){
     unsigned side=warp%columns,index=pair_depth_b_index(side,step,f,lane,4);
     assert(index<stage.size()&&++count[index]==1);stage[index]=(chunk+step*32)*100+side*4+f;
    }
   for(auto c:count)assert(c==1);
   for(unsigned warp=0;warp<8;++warp)for(unsigned step=0;step<4;++step)for(unsigned f=0;f<4;++f)for(unsigned lane=0;lane<32;++lane){
    unsigned side=warp%columns;
    assert(stage[pair_depth_b_index(side,step,f,lane,4)]==(chunk+step*32)*100+side*4+f);
   }
  }
 }
}
'''
  with tempfile.TemporaryDirectory()as temp:
   source=Path(temp)/'contract.cpp';out=Path(temp)/'contract';source.write_text(code)
   subprocess.run(['g++','-O2','-std=c++17','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'gpu'),str(source),'-o',str(out)],check=True,capture_output=True)
   subprocess.run([str(out)],check=True,capture_output=True,timeout=60)
if __name__=='__main__':unittest.main()
