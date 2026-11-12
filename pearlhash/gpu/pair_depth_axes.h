// ISC. v080 B fragment staging index, parameterised by K32 stage depth.
#pragma once
#ifdef __CUDACC__
#define PH_PD_HD __host__ __device__
#else
#define PH_PD_HD
#endif
PH_PD_HD inline unsigned pair_depth_b_index(unsigned side,unsigned step,unsigned fragment,unsigned lane,unsigned steps){return ((side*steps+step)*4U+fragment)*32U+lane;}
#undef PH_PD_HD
