// ISC license. No matrix allocation: leaves synthesize one constant 1024-byte chunk.
#include "constant_merkle_core.h"
extern "C" __global__ void constant_merkle_leaves(const unsigned*key,unsigned fill,
 unsigned count,const unsigned*tail,unsigned tail_bytes,unsigned*out){
 unsigned i=blockIdx.x*blockDim.x+threadIdx.x;
 if(i>=count)return;
 ph_merkle::constant_chunk(key,fill,i,count==1,tail,tail_bytes==16&&i+1==count,out+i*8);
}
extern "C" __global__ void constant_merkle_parents(const unsigned*children,const unsigned*key,
 unsigned count,unsigned*out){
 unsigned i=blockIdx.x*blockDim.x+threadIdx.x;
 if(i>=(count+1)/2)return;
 if(i*2+1>=count){for(int j=0;j<8;++j)out[i*8+j]=children[i*16+j];return;}
 ph_merkle::parent(children+i*16,key,count==2,out+i*8);
}
