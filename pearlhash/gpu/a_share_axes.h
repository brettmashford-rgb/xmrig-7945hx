// ISC. v079 paired-column traversal and shared A/B staging indices.
#pragma once
#ifdef __CUDACC__
#define PH_AS_HD __host__ __device__
#else
#define PH_AS_HD
#endif
PH_AS_HD inline unsigned a_pair_members(unsigned rows){return rows<16U?rows:16U;}
PH_AS_HD inline unsigned a_pair_block(unsigned ordinal,unsigned rows,unsigned cols){unsigned m=a_pair_members(rows),period=m*cols;return (ordinal/period)*((cols+1U)/2U)+(ordinal%period)/(2U*m);}
PH_AS_HD inline unsigned a_pair_first(unsigned block,unsigned rows,unsigned cols){unsigned m=a_pair_members(rows),pairs=(cols+1U)/2U;return (block/pairs)*(m*cols)+(block%pairs)*(2U*m);}
PH_AS_HD inline unsigned a_pair_row_base(unsigned block,unsigned rows,unsigned cols){return (block/((cols+1U)/2U))*a_pair_members(rows);}
PH_AS_HD inline unsigned a_pair_col_base(unsigned block,unsigned cols){return 2U*(block%((cols+1U)/2U));}
PH_AS_HD inline unsigned a_pair_canonical(unsigned ordinal,unsigned rows,unsigned cols){unsigned m=a_pair_members(rows),period=m*cols,local=ordinal%period,pair=local/(2U*m),inside=local%(2U*m);return ((ordinal/period)*m+inside%m)*cols+pair*2U+inside/m;}
PH_AS_HD inline unsigned a_pair_inverse(unsigned tile,unsigned rows,unsigned cols){unsigned m=a_pair_members(rows),row=tile/cols,col=tile%cols;return (row/m)*(m*cols)+(col/2U)*(2U*m)+(col%2U)*m+row%m;}
PH_AS_HD inline unsigned a_share_index(unsigned quartet,unsigned step,unsigned item,unsigned lane){return ((quartet*4U+step)*10U+item)*32U+lane;}
PH_AS_HD inline unsigned a_pair_b_index(unsigned side,unsigned step,unsigned fragment,unsigned lane){return ((side*4U+step)*4U+fragment)*32U+lane;}
#undef PH_AS_HD
