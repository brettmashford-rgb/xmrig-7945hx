// ISC. Explicit small-block and bounded-panel traversal helpers.
#pragma once
#ifdef __CUDACC__
#define PH_X_HD __host__ __device__
#else
#define PH_X_HD
#endif
PH_X_HD inline unsigned experiment_row(unsigned ordinal,unsigned columns,unsigned rows,unsigned width){unsigned g=rows<width?rows:width;return g*((ordinal/g)/columns)+ordinal%g;}
PH_X_HD inline unsigned experiment_col(unsigned ordinal,unsigned columns,unsigned rows,unsigned width){unsigned g=rows<width?rows:width;return (ordinal/g)%columns;}
PH_X_HD inline unsigned panel_first(unsigned ordinal,unsigned rows,unsigned columns){unsigned full=columns/16U,tiles=rows*16U;return ordinal<full*tiles?(ordinal/tiles)*16U:full*16U;}
PH_X_HD inline unsigned panel_width(unsigned first,unsigned columns){return columns-first<16U?columns-first:16U;}
PH_X_HD inline unsigned panel_local(unsigned ordinal,unsigned rows,unsigned columns){unsigned full=columns/16U,tiles=rows*16U;return ordinal<full*tiles?ordinal%tiles:ordinal-full*tiles;}
PH_X_HD inline unsigned panel_canonical(unsigned ordinal,unsigned rows,unsigned columns){unsigned first=panel_first(ordinal,rows,columns),width=panel_width(first,columns),local=panel_local(ordinal,rows,columns);return experiment_row(local,width,rows,32U)*columns+first+experiment_col(local,width,rows,32U);}
PH_X_HD inline bool experiment_snapshot_valid(unsigned threads,unsigned guards,unsigned count){return threads==128U&&guards>=1U&&guards<=64U&&count>=1U&&count<=16384U;}
#undef PH_X_HD
