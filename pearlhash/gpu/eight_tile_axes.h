// ISC. Eight-row-axis traversal and packed 80-row slab ownership.
#pragma once
#ifdef __CUDACC__
#define PH_EIGHT_HD __host__ __device__
#else
#define PH_EIGHT_HD
#endif
PH_EIGHT_HD inline unsigned eight_tile_row(unsigned ordinal,unsigned columns){return 8U*((ordinal/8U)/columns)+(ordinal&7U);}
PH_EIGHT_HD inline unsigned eight_tile_column(unsigned ordinal,unsigned columns){return (ordinal/8U)%columns;}
PH_EIGHT_HD inline unsigned eight_tile_canonical(unsigned ordinal,unsigned columns){return eight_tile_row(ordinal,columns)*columns+eight_tile_column(ordinal,columns);}
PH_EIGHT_HD inline unsigned eight_tile_ordinal(unsigned tile,unsigned columns){unsigned row=tile/columns;return (row/8U)*(8U*columns)+8U*(tile%columns)+(row&7U);}
PH_EIGHT_HD inline unsigned eight_packed_tile(unsigned row){return row/10U;}
PH_EIGHT_HD inline unsigned eight_packed_row(unsigned row){return row%10U;}
PH_EIGHT_HD inline unsigned eight_fold_value(unsigned slab,unsigned group,unsigned tile,unsigned low,unsigned high){
 unsigned a=slab*16U+group,b=a+8U;
 return ((a<80U&&a/10U==tile)?low:0U)^((b<80U&&b/10U==tile)?high:0U);
}
#undef PH_EIGHT_HD
