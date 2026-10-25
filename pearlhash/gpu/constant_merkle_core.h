// ISC license. Independent full-chunk constant-input BLAKE3 and parent CVs.
#pragma once
#include "keyed64.h"
#ifdef __CUDACC__
#define PH_MHD __host__ __device__
#else
#define PH_MHD
#endif
namespace ph_merkle {
using W=unsigned;
PH_MHD inline void compress(const W*cv,const W*message,unsigned long long counter,W flags,W*out){
 W v[16],m[16];for(int i=0;i<8;++i)v[i]=cv[i];
 v[8]=0x6a09e667U;v[9]=0xbb67ae85U;v[10]=0x3c6ef372U;v[11]=0xa54ff53aU;
 v[12]=W(counter);v[13]=W(counter>>32);v[14]=64;v[15]=flags;
 for(int i=0;i<16;++i)m[i]=message[i];
 const int p[16]={2,6,3,10,7,0,4,13,1,11,12,5,9,14,15,8};
 for(int r=0;r<7;++r){
  ph::mix(v,0,4,8,12,m[0],m[1]);ph::mix(v,1,5,9,13,m[2],m[3]);
  ph::mix(v,2,6,10,14,m[4],m[5]);ph::mix(v,3,7,11,15,m[6],m[7]);
  ph::mix(v,0,5,10,15,m[8],m[9]);ph::mix(v,1,6,11,12,m[10],m[11]);
  ph::mix(v,2,7,8,13,m[12],m[13]);ph::mix(v,3,4,9,14,m[14],m[15]);
  W next[16];for(int i=0;i<16;++i)next[i]=m[p[i]];
  for(int i=0;i<16;++i)m[i]=next[i];
 }
 for(int i=0;i<8;++i)out[i]=v[i]^v[i+8];
}
PH_MHD inline void constant_chunk(const W*key,W fill,unsigned long long index,bool root,
                                  const W*tail,bool use_tail,W*out){
 W cv[8],message[16];for(int i=0;i<8;++i)cv[i]=key[i];
 W value=(fill&255U)*0x01010101U;
 for(int block=0;block<16;++block){
  for(int i=0;i<16;++i)message[i]=value;
  if(block==15&&use_tail)for(int i=0;i<4;++i)message[12+i]=tail[i];
  W flags=16U|(block==0?1U:0U)|(block==15?2U:0U)|((block==15&&root)?8U:0U);
  W result[8];compress(cv,message,index,flags,result);
  for(int i=0;i<8;++i)cv[i]=result[i];
 }
 for(int i=0;i<8;++i)out[i]=cv[i];
}
PH_MHD inline void parent(const W*children,const W*key,bool root,W*out){
 compress(key,children,0,20U|(root?8U:0U),out);
}
}
#undef PH_MHD
