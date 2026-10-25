// ISC. Row-major immutable A fragments. Padding rows contribute zero.
#pragma once
#ifdef __CUDACC__
#define PH_AHD __host__ __device__
#else
#define PH_AHD
#endif
PH_AHD inline unsigned cached_a_word(const signed char *input,unsigned row,unsigned offset,bool live){
 return live?reinterpret_cast<const unsigned *>(input)[row*(32768/4)+offset/4]:0U;
}
// Sixteen B rows, padded to a non-power-of-two shared-memory stride.
PH_AHD inline unsigned cached_b_word(const signed char*cache,const unsigned*pairs,unsigned row,unsigned offset){
 unsigned packed=0;
 #pragma unroll
 for(unsigned byte=0;byte<4;++byte){
  unsigned pair=pairs[offset+byte];
  int value=64+int(cache[(pair&65535)*18+row])-int(cache[(pair>>16)*18+row]);
  packed|=(unsigned(value)&255U)<<(byte*8);
 }
 return packed;
}
#undef PH_AHD
