// ISC. Adjacent row-pair traversal, a bijection onto canonical row-major IDs.
#pragma once
#ifdef __CUDACC__
#define PH_SB_HD __host__ __device__
#else
#define PH_SB_HD
#endif
PH_SB_HD inline unsigned shared_b_row(unsigned ordinal,unsigned columns) {
    return 2U*((ordinal/2U)/columns)+(ordinal&1U);
}
PH_SB_HD inline unsigned shared_b_column(unsigned ordinal,unsigned columns) {
    return (ordinal/2U)%columns;
}
PH_SB_HD inline unsigned shared_b_tile(unsigned ordinal,unsigned columns) {
    return shared_b_row(ordinal,columns)*columns+shared_b_column(ordinal,columns);
}
PH_SB_HD inline unsigned shared_b_ordinal(unsigned tile,unsigned columns) {
    unsigned row=tile/columns,col=tile%columns;
    return (row/2U)*(2U*columns)+2U*col+(row&1U);
}
#undef PH_SB_HD
