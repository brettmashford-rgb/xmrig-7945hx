// ISC. Instantiate the validated four-row B body at strides six and seven.
#include "b_quad_scan.cu"

#define PH_BQ_ARGS const signed char *ua,const signed char *ub, \
    const unsigned *pa,const unsigned *pb,const signed char *tail, \
    const unsigned *row_axes,const unsigned *bounds,const unsigned *key, \
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit, \
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k, \
    unsigned rank,int fill,unsigned long long generation, \
    const unsigned *column_axes,unsigned row_count,unsigned column_count,unsigned first
#define PH_BQ_VALUES ua,ub,pa,pb,tail,row_axes,bounds,key,status,candidates,audit_words,audit,capacity,query_count,m,n,k,rank,fill,generation,column_axes,row_count,column_count,first

extern "C" __global__ void b_quad_stride6_scan(PH_BQ_ARGS) {b_quad_scan_body<6>(PH_BQ_VALUES);}
extern "C" __global__ void b_quad_stride7_scan(PH_BQ_ARGS) {b_quad_scan_body<7>(PH_BQ_VALUES);}
#undef PH_BQ_VALUES
#undef PH_BQ_ARGS
