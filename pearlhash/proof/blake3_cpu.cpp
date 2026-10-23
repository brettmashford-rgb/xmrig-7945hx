// ISC license; see ../LICENSE. Independent CPU BLAKE3 primitives for proofs.
// Separate from the validated GPU implementation to cross-check both paths.
#include <cstddef>
#include <cstdint>
#include <cstring>
using W=uint32_t;
static const W IV[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                     0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
static W load(const unsigned char *p){return W(p[0])|W(p[1])<<8|W(p[2])<<16|W(p[3])<<24;}
static void store(unsigned char *p,W x){for(int i=0;i<4;++i)p[i]=(x>>(8*i))&255;}
static W rot(W x,int n){return (x>>n)|(x<<(32-n));}
static void g(W *v,int a,int b,int c,int d,W x,W y){
 v[a]+=v[b]+x;v[d]=rot(v[d]^v[a],16);v[c]+=v[d];v[b]=rot(v[b]^v[c],12);
 v[a]+=v[b]+y;v[d]=rot(v[d]^v[a],8);v[c]+=v[d];v[b]=rot(v[b]^v[c],7);
}
static void compress(const W *cv,const unsigned char *block,uint64_t counter,W len,W flags,W *out){
 W v[16],m[16];for(int i=0;i<8;++i)v[i]=cv[i];
 for(int i=0;i<4;++i)v[8+i]=IV[i];
 v[12]=W(counter);v[13]=W(counter>>32);v[14]=len;v[15]=flags;
 for(int i=0;i<16;++i)m[i]=load(block+4*i);
 const int p[16]={2,6,3,10,7,0,4,13,1,11,12,5,9,14,15,8};
 for(int r=0;r<7;++r){
  g(v,0,4,8,12,m[0],m[1]);g(v,1,5,9,13,m[2],m[3]);
  g(v,2,6,10,14,m[4],m[5]);g(v,3,7,11,15,m[6],m[7]);
  g(v,0,5,10,15,m[8],m[9]);g(v,1,6,11,12,m[10],m[11]);
  g(v,2,7,8,13,m[12],m[13]);g(v,3,4,9,14,m[14],m[15]);
  W next[16];for(int i=0;i<16;++i)next[i]=m[p[i]];
  for(int i=0;i<16;++i)m[i]=next[i];
 }
 for(int i=0;i<8;++i)out[i]=v[i]^v[i+8];
}
static W init(const unsigned char *key,W *words){
 for(int i=0;i<8;++i)words[i]=key?load(key+4*i):IV[i];
 return key?16:0;
}
static void chunk(const unsigned char *data,size_t len,const unsigned char *key,
                  uint64_t index,bool root,unsigned char *out){
 W cv[8];W flags=init(key,cv);
 size_t blocks=len?(len+63)/64:1;
 for(size_t b=0;b<blocks;++b){
  unsigned char block[64]={};size_t start=b*64,size=start<len?(len-start<64?len-start:64):0;
  if(size)std::memcpy(block,data+start,size);
  W f=flags|(b==0?1:0)|(b+1==blocks?2:0)|((root && b+1==blocks)?8:0);
  W result[8];compress(cv,block,index,W(size),f,result);
  for(int i=0;i<8;++i)cv[i]=result[i];
 }
 for(int i=0;i<8;++i)store(out+4*i,cv[i]);
}
#define API extern "C" __attribute__((visibility("default")))
API int ph_hash_small(const unsigned char *data,size_t len,const unsigned char *key,unsigned char *out){
 if(len>1024 || !out || (len && !data))return 1;
 chunk(data,len,key,0,true,out);return 0;
}
API int ph_chunk_cvs(const unsigned char *data,size_t count,const unsigned char *key,unsigned char *out){
 if(!data || !key || !out || !count || count>65536)return 1;
 for(size_t i=0;i<count;++i)chunk(data+i*1024,1024,key,i,false,out+i*32);
 return 0;
}
API int ph_chunk_value(const unsigned char *data,uint64_t index,const unsigned char *key,unsigned char *out){
 if(!data || !key || !out || index>=65536)return 1;
 chunk(data,1024,key,index,false,out);return 0;
}
API int ph_parent_cvs(const unsigned char *children,size_t pairs,const unsigned char *key,
                      int root,unsigned char *out){
 if(!children || !key || !out || !pairs || pairs>32768 || (root && pairs!=1))return 1;
 W cv[8];init(key,cv);
 for(size_t p=0;p<pairs;++p){
  W result[8];compress(cv,children+p*64,0,64,16|4|(root?8:0),result);
  for(int i=0;i<8;++i)store(out+p*32+4*i,result[i]);
 }
 return 0;
}
