// ISC. Resolve immutable packed A row addresses once, after the kernel bounds guards.
#pragma once
#include "four_tile_axes.h"
#ifdef __CUDACC__
#define PH_HA __host__ __device__
#else
#define PH_HA
#endif
PH_HA inline unsigned hoisted_a_base(const unsigned *axes,unsigned base,unsigned packed_row,unsigned thread){
 return packed_row<40U?axes[(base+four_packed_tile(packed_row))*32U+four_packed_row(packed_row)]*8192U+thread:0xffffffffU;
}
PH_HA inline unsigned hoisted_a_load(const signed char *input,unsigned word_base,unsigned offset_words){
 return word_base==0xffffffffU?0U:reinterpret_cast<const unsigned*>(input)[word_base+offset_words];
}
PH_HA inline const unsigned *hoisted_a_pointer(const signed char *input,unsigned word_base){
 return word_base==0xffffffffU?nullptr:reinterpret_cast<const unsigned*>(input)+word_base;
}
#undef PH_HA
