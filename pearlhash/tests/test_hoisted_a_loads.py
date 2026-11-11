"""Compile real address helpers and compare every K fragment with original four_a_word. ISC."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class Loads(unittest.TestCase):
    def test_actual_helpers_full_K_random_axes_and_padding(self):
        old=(ROOT/'gpu/four_tile_scan.cu').read_text().split('__device__ __forceinline__ unsigned four_a_word',1)[1].split('__device__ __forceinline__ void four_fold',1)[0]
        source='''#include "hoisted_a.h"
#include "cached_a_pack.h"
#include <vector>
#include <cstdint>
#include <cstdio>
'''+ 'inline unsigned four_a_word'+old+'''
int main(){
 constexpr unsigned rows=257;
 std::vector<unsigned> data(rows*8192),axes(512*32);
 uint32_t state=123456789;
 auto next=[&](){state^=state<<13;state^=state>>17;state^=state<<5;return state;};
 for(auto &v:data)v=next();
 for(auto &v:axes)v=next()%rows;
 // Include the very last row; advancing pointers must never form beyond-one-past values.
 for(unsigned i=0;i<10;++i)axes[511*32+i]=rows-1;
 const auto *input=reinterpret_cast<const signed char*>(data.data());
 unsigned long long checked=0;
 for(unsigned base:{0U,4U,508U})for(unsigned group=0;group<8;++group)for(unsigned thread=0;thread<4;++thread){
  const unsigned *pointers[6];unsigned bases[6];
  for(unsigned slab=0;slab<6;++slab){
   unsigned row=slab*8+group;
   bases[slab]=hoisted_a_base(axes.data(),base,row,thread);
   pointers[slab]=hoisted_a_pointer(input,bases[slab]);
  }
  for(unsigned offset=0;offset<32768;offset+=32){
   for(unsigned slab=0;slab<6;++slab)for(unsigned add:{0U,16U}){
    unsigned expected=four_a_word(input,axes.data(),base,slab*8+group,offset+thread*4+add);
    unsigned compact=hoisted_a_load(input,bases[slab],offset/4+add/4);
    unsigned advanced=pointers[slab]?pointers[slab][add/4]:0U;
    if(expected!=compact||expected!=advanced)return 1;
    ++checked;
   }
   if(offset+32U<32768U)for(auto &ptr:pointers)if(ptr)ptr+=8U;
  }
 }
 if(hoisted_a_base(nullptr,0,40,0)!=0xffffffffU||hoisted_a_load(nullptr,0xffffffffU,0)!=0U||hoisted_a_pointer(nullptr,0xffffffffU)!=nullptr)return 2;
 std::printf("%llu fragment comparisons passed\\n",checked);
 return checked==1179648ULL?0:3;
}
'''
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp);(path/'check.cpp').write_text(source)
            subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-unknown-pragmas',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'gpu'),str(path/'check.cpp'),'-o',str(path/'check')],check=True)
            result=subprocess.run([str(path/'check')],capture_output=True,text=True,check=True)
            self.assertIn('1179648 fragment comparisons passed',result.stdout)

if __name__=='__main__':unittest.main()
