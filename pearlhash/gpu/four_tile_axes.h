// ISC. Four-row-axis traversal and packed 40-row slab ownership.
#pragma once
#ifdef __CUDACC__
#define PH_FOUR_HD __host__ __device__
#else
#define PH_FOUR_HD
#endif
PH_FOUR_HD inline unsigned four_tile_row(unsigned ordinal,unsigned columns){return 4U*((ordinal/4U)/columns)+(ordinal&3U);}
PH_FOUR_HD inline unsigned four_tile_column(unsigned ordinal,unsigned columns){return (ordinal/4U)%columns;}
PH_FOUR_HD inline unsigned four_tile_canonical(unsigned ordinal,unsigned columns){return four_tile_row(ordinal,columns)*columns+four_tile_column(ordinal,columns);}
PH_FOUR_HD inline unsigned four_tile_ordinal(unsigned tile,unsigned columns){unsigned row=tile/columns;return (row/4U)*(4U*columns)+4U*(tile%columns)+(row&3U);}
PH_FOUR_HD inline unsigned four_packed_tile(unsigned row){return row/10U;}
PH_FOUR_HD inline unsigned four_packed_row(unsigned row){return row%10U;}
PH_FOUR_HD inline unsigned four_fold_value(unsigned slab,unsigned group,unsigned tile,unsigned low,unsigned high){
 unsigned a=slab*16U+group,b=a+8U;
 return ((a<40U&&a/10U==tile)?low:0U)^((b<40U&&b/10U==tile)?high:0U);
}
#undef PH_FOUR_HD
