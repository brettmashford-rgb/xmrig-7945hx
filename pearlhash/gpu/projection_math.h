// ISC. Exact low-byte projection plus signed correction, usable by host contracts.
#pragma once
#ifdef __CUDACC__
#define PH_PHD __host__ __device__
#else
#define PH_PHD
#endif
PH_PHD inline int projection_low(int v){return int((unsigned(v)&255U)^128U)-128;}
PH_PHD inline int projection_high(int v){return (v-projection_low(v))/256;}
PH_PHD inline unsigned projection_record(unsigned r,int high){return r|((unsigned(high)&255U)<<8);}
PH_PHD inline int projection_record_high(unsigned record){return int((record>>8)^128U)-128;}
#undef PH_PHD
