"""Actual traversal helpers, all production IDs and the pipelined-buffer ownership model. ISC."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.experiments_scan import canonical,inverse,layout,MODES
from tools.check_prepared_job import synthetic_session
from tools.fast_plan import FastPlan
ROOT=Path(__file__).resolve().parents[1]

class Layout(unittest.TestCase):
    def test_actual_Cpp_bijections_tail_panels_and_pipeline(self):
        source=r'''#include "experiment_axes.h"
#include "cta_b_axes.h"
#include <vector>
#include <cstdio>
int main(){
 for(unsigned rows:{16U,512U})for(unsigned cols:{12U,19U,32U,16384U})for(unsigned mode=0;mode<3;++mode){
  unsigned count=rows*cols;std::vector<unsigned char> seen(count,0);
  for(unsigned i=0;i<count;++i){
   unsigned tile=mode==2?panel_canonical(i,rows,cols):experiment_row(i,cols,rows,mode?16:32)*cols+experiment_col(i,cols,rows,mode?16:32);
   if(tile>=count||seen[tile]++)return 1;
   if(mode<2&&cols==16384&&tile/(32*cols)!=i/(32*cols))return 2;
  }
  for(auto x:seen)if(x!=1)return 3;
 }
 unsigned buffers[2][1024]={};
 auto fill=[&](unsigned buf,unsigned chunk){
  for(unsigned producer=0;producer<2;++producer)for(unsigned step=producer;step<8;step+=2)
   for(unsigned f=0;f<4;++f)for(unsigned lane=0;lane<32;++lane)
    buffers[buf][cta_fragment_index(step,f,lane)]=(chunk+step*32)*131U+f*32+lane;
 };
 fill(0,0);unsigned current=0;
 for(unsigned chunk=0;chunk<32768;chunk+=256){
  if(chunk+256<32768)fill(current^1,chunk+256);
  for(unsigned consumer=0;consumer<8;++consumer)for(unsigned step=0;step<8;++step)
   for(unsigned f=0;f<4;++f)for(unsigned lane=0;lane<32;++lane)
    if(buffers[current][cta_fragment_index(step,f,lane)]!=(chunk+step*32)*131U+f*32+lane)return 4;
  current^=1;
 }
 std::puts("all production traversal IDs, partial panels and pipeline buffers passed");
}
'''
        with tempfile.TemporaryDirectory()as temp:
            folder=Path(temp);(folder/'check.cpp').write_text(source)
            subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'gpu'),str(folder/'check.cpp'),'-o',str(folder/'check')],check=True)
            result=subprocess.run([str(folder/'check')],check=True,capture_output=True,text=True)
            self.assertIn('all production traversal IDs',result.stdout)
    def test_python_queries_inverse_all_modes_and_panel_width(self):
        session,job,_=synthetic_session(bytes(32));plan=FastPlan.from_job(job)
        try:
            for mode in MODES:
                for ordinal in range(plan.count):self.assertEqual(inverse(plan,mode,canonical(plan,mode,ordinal)),ordinal)
            for ordinal in range(plan.count):
                _,first,width,local=layout(plan,'panel',ordinal)
                self.assertEqual((first,width),(0,len(plan.cols)));self.assertEqual(local,ordinal)
        finally:session.close()

if __name__=='__main__':unittest.main()
