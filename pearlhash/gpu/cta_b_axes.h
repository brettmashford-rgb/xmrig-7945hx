// ISC. A block shares one B column axis across up to eight independent quartets.
#pragma once
#ifdef __CUDACC__
#define PH_CTA_HD __host__ __device__
#else
#define PH_CTA_HD
#endif
PH_CTA_HD inline unsigned cta_group(unsigned rows){return rows<32U?rows:32U;}
PH_CTA_HD inline unsigned cta_tile_row(unsigned ordinal,unsigned columns,unsigned rows){unsigned g=cta_group(rows);return g*((ordinal/g)/columns)+ordinal%g;}
PH_CTA_HD inline unsigned cta_tile_column(unsigned ordinal,unsigned columns,unsigned rows){return (ordinal/cta_group(rows))%columns;}
PH_CTA_HD inline unsigned cta_tile_canonical(unsigned ordinal,unsigned columns,unsigned rows){return cta_tile_row(ordinal,columns,rows)*columns+cta_tile_column(ordinal,columns,rows);}
PH_CTA_HD inline unsigned cta_tile_ordinal(unsigned tile,unsigned columns,unsigned rows){unsigned g=cta_group(rows),row=tile/columns;return (row/g)*(g*columns)+g*(tile%columns)+row%g;}
PH_CTA_HD inline unsigned cta_fragment_index(unsigned step,unsigned fragment,unsigned lane){return (step*4U+fragment)*32U+lane;}
#undef PH_CTA_HD
