// ISC. v078 traversal and snapshot limits, compiled in host contract tests.
#pragma once
#ifdef __CUDACC__
#define PH_TP_HD __host__ __device__
#else
#define PH_TP_HD
#endif
PH_TP_HD inline unsigned throughput_group(unsigned rows,unsigned width){return rows<width?rows:width;}
PH_TP_HD inline unsigned throughput_row(unsigned ordinal,unsigned columns,unsigned rows,unsigned width){unsigned g=throughput_group(rows,width);return g*((ordinal/g)/columns)+ordinal%g;}
PH_TP_HD inline unsigned throughput_col(unsigned ordinal,unsigned columns,unsigned rows,unsigned width){return (ordinal/throughput_group(rows,width))%columns;}
PH_TP_HD inline unsigned throughput_canonical(unsigned ordinal,unsigned columns,unsigned rows,unsigned width){return throughput_row(ordinal,columns,rows,width)*columns+throughput_col(ordinal,columns,rows,width);}
PH_TP_HD inline unsigned throughput_inverse(unsigned tile,unsigned columns,unsigned rows,unsigned width){unsigned g=throughput_group(rows,width),row=tile/columns;return (row/g)*(g*columns)+(tile%columns)*g+row%g;}
PH_TP_HD inline bool throughput_snapshot_valid(unsigned threads,unsigned guards,unsigned count){return threads==128U&&guards>=1U&&guards<=64U&&count>=1U&&count<=65536U;}
#undef PH_TP_HD
