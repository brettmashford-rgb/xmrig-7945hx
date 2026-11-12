// ISC. v081 fixed-work rectangular CTA traversal; columns 2/4/8.
#pragma once
#ifdef __CUDACC__
#define PH_LW __host__ __device__
#else
#define PH_LW
#endif
PH_LW inline unsigned lw_members(unsigned rows,unsigned columns){unsigned limit=32U/columns;return rows<limit?rows:limit;}
PH_LW inline unsigned lw_block(unsigned ordinal,unsigned rows,unsigned cols,unsigned columns){unsigned m=lw_members(rows,columns),period=m*cols;return (ordinal/period)*((cols+columns-1U)/columns)+(ordinal%period)/(columns*m);}
PH_LW inline unsigned lw_first(unsigned block,unsigned rows,unsigned cols,unsigned columns){unsigned m=lw_members(rows,columns),groups=(cols+columns-1U)/columns;return (block/groups)*(m*cols)+(block%groups)*(columns*m);}
PH_LW inline unsigned lw_row_base(unsigned block,unsigned rows,unsigned cols,unsigned columns){return (block/((cols+columns-1U)/columns))*lw_members(rows,columns);}
PH_LW inline unsigned lw_col_base(unsigned block,unsigned cols,unsigned columns){return columns*(block%((cols+columns-1U)/columns));}
PH_LW inline unsigned lw_canonical(unsigned ordinal,unsigned rows,unsigned cols,unsigned columns){unsigned m=lw_members(rows,columns),period=m*cols,local=ordinal%period,inside=local%(columns*m);return ((ordinal/period)*m+inside%m)*cols+(local/(columns*m))*columns+inside/m;}
PH_LW inline unsigned lw_inverse(unsigned tile,unsigned rows,unsigned cols,unsigned columns){unsigned m=lw_members(rows,columns),row=tile/cols,col=tile%cols;return (row/m)*(m*cols)+(col/columns)*(columns*m)+(col%columns)*m+row%m;}
#undef PH_LW
