"""Compile actual transcript ownership helpers; compare every checkpoint with four independent XORs. ISC."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class Algebra(unittest.TestCase):
    def test_all_active_masks_full_width_values_and_256_repeated_checkpoints(self):
        source=r'''#include "partition_fold.h"
#include "four_tile_axes.h"
#include <cstdint>
#include <cstdio>
#include <cstring>
static unsigned rotate(unsigned v){return (v<<13)|(v>>19);}
int main(){
 uint32_t state=123456789;
 auto next=[&](){state^=state<<13;state^=state>>17;state^=state<<5;return state;};
 unsigned long long comparisons=0;
 for(unsigned mask=0;mask<16;++mask)for(unsigned trial=0;trial<5;++trial){
  unsigned lo[32]={},hi[32]={},expected[4][16]={};
  for(unsigned checkpoint=0;checkpoint<256;++checkpoint){
   unsigned v[4][32]={},partial[4][32],temp[4][32],value[32],copy[32];
   for(unsigned lane=0;lane<32;++lane){
    unsigned low[3],high[3];
    for(unsigned slab=0;slab<3;++slab){
     low[slab]=trial==0?0:trial==1?0xffffffffU:trial==2?0x80000000U:next();
     high[slab]=trial==0?0:trial==1?0xffffffffU:trial==2?0x7fffffffU:next();
    }
    for(unsigned tile=0;tile<4;++tile)for(unsigned slab=0;slab<3;++slab)
     v[tile][lane]^=four_fold_value(slab,lane/4,tile,low[slab],high[slab]);
   }
   unsigned slot=checkpoint%16;
   for(unsigned tile=0;tile<4;++tile){
    unsigned reduced=0;for(unsigned lane=0;lane<32;++lane)reduced^=v[tile][lane];
    if(mask&(1U<<tile))expected[tile][slot]=rotate(expected[tile][slot])^reduced;
   }
   std::memcpy(partial,v,sizeof(v));
   for(unsigned delta=1;delta<=2;delta*=2){
    std::memcpy(temp,partial,sizeof(partial));
    for(unsigned tile=0;tile<4;++tile)for(unsigned lane=0;lane<32;++lane)
     partial[tile][lane]=temp[tile][lane]^temp[tile][lane^delta];
   }
   for(unsigned lane=0;lane<32;++lane)value[lane]=partition_pick(partial[0][lane],partial[1][lane],partial[2][lane],partial[3][lane],lane);
   for(unsigned delta=4;delta<=16;delta*=2){
    std::memcpy(copy,value,sizeof(value));
    for(unsigned lane=0;lane<32;++lane)value[lane]=copy[lane]^copy[lane^delta];
   }
   for(unsigned lane=0;lane<32;++lane)partition_store(value[lane],lane,slot,lo[lane],hi[lane]);
   for(unsigned tile=0;tile<4;++tile)if(mask&(1U<<tile))for(unsigned i=0;i<16;++i){
    unsigned lane=partition_source(tile,i),actual=i<8?lo[lane]:hi[lane];
    if(lane>=32||actual!=expected[tile][i])return 1;
    ++comparisons;
   }
  }
 }
 std::printf("%llu full transcript word comparisons passed\n",comparisons);
 return comparisons==655360ULL?0:2;
}
'''
        with tempfile.TemporaryDirectory()as temp:
            folder=Path(temp);(folder/'test.cpp').write_text(source)
            subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                '-fno-sanitize-recover=all','-I'+str(ROOT/'gpu'),str(folder/'test.cpp'),'-o',str(folder/'test')],check=True)
            result=subprocess.run([str(folder/'test')],check=True,capture_output=True,text=True)
            self.assertIn('655360 full transcript word comparisons passed',result.stdout)

if __name__=='__main__':unittest.main()
