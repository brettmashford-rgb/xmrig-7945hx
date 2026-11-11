// ISC. Partition four warp XOR reductions across the four thread positions.
#pragma once
#ifdef __CUDACC__
#define PH_PF_HD __host__ __device__
#else
#define PH_PF_HD
#endif
PH_PF_HD inline unsigned partition_pick(unsigned v0,unsigned v1,unsigned v2,unsigned v3,unsigned lane){
 return (lane&3U)==0?v0:((lane&3U)==1?v1:((lane&3U)==2?v2:v3));
}
PH_PF_HD inline unsigned partition_source(unsigned tile,unsigned slot){return (slot&7U)*4U+tile;}
PH_PF_HD inline void partition_store(unsigned value,unsigned lane,unsigned slot,unsigned &low,unsigned &high){
 if((lane>>2)==(slot&7U)){
  if(slot<8U)low=((low<<13)|(low>>19))^value;
  else high=((high<<13)|(high>>19))^value;
 }
}
#undef PH_PF_HD
#ifdef __CUDACC__
__device__ __forceinline__ void partition_fold(unsigned v0,unsigned v1,unsigned v2,unsigned v3,
        unsigned lane,unsigned slot,unsigned &low,unsigned &high){
    // First reduce the four thread positions for all four independent values.
    #pragma unroll
    for(unsigned delta=1;delta<=2;delta*=2){
        v0^=__shfl_xor_sync(0xffffffffU,v0,delta);
        v1^=__shfl_xor_sync(0xffffffffU,v1,delta);
        v2^=__shfl_xor_sync(0xffffffffU,v2,delta);
        v3^=__shfl_xor_sync(0xffffffffU,v3,delta);
    }
    // lane&3 owns the tile; remaining reductions preserve those two lane bits.
    unsigned value=partition_pick(v0,v1,v2,v3,lane);
    #pragma unroll
    for(unsigned delta=4;delta<=16;delta*=2)value^=__shfl_xor_sync(0xffffffffU,value,delta);
    partition_store(value,lane,slot,low,high);
}
__device__ __forceinline__ void native_four_fold(unsigned value,unsigned lane,unsigned slot,unsigned &word){
    asm volatile("redux.sync.xor.b32 %0, %1, 0xffffffff;" : "=r"(value) : "r"(value));
    if(lane==slot)word=((word<<13)|(word>>19))^value;
}
#endif
