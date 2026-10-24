// ISC. Exact constant-signal + deterministic-noise signed-byte fragment loader.
// Uniform tables cover all global rows; permutation table is shared per side.
#pragma once
#ifdef __CUDACC__
#define PH_VIRTUAL __device__ __forceinline__
#else
#define PH_VIRTUAL inline
#endif

struct VirtualScanInput {
    const signed char *ua,*ub;
    const unsigned *pa,*pb;
    const signed char *tail;
    unsigned m,n,k,rank;
    int fill;

    PH_VIRTUAL bool valid()const {
        return m&&n&&rank>=32&&rank<=1024&&!(rank&(rank-1))&&k&&k<=65536&&!(k%rank)&&
            fill>=-64&&fill<=64&&
            (static_cast<unsigned long long>(m)+n)*rank+8ULL*k+16<=64ULL*1024*1024;
    }

    PH_VIRTUAL unsigned pack(bool side_b,const unsigned *map,unsigned row,
                             unsigned rows,unsigned offset)const {
        if(row>=rows || k<4 || offset>k-4)return 0;
        unsigned global=map[row],limit=side_b?n:m;
        if(global>=limit)return 0;
        const signed char *uniform=side_b?ub:ua;
        const unsigned *pairs=side_b?pb:pa;
        unsigned packed=0;
        for(unsigned byte=0;byte<4;++byte) {
            unsigned l=offset+byte,pair=pairs[l];
            int signal=(!side_b&&global==m-1&&l>=k-16)?int(tail[l-(k-16)]):fill;
            int value=signal+int(uniform[global*rank+(pair&65535)])-
                             int(uniform[global*rank+(pair>>16)]);
            packed|=(unsigned(value)&255U)<<(byte*8);
        }
        return packed;
    }

    PH_VIRTUAL unsigned pack_a(const unsigned *map,unsigned row,unsigned rows,unsigned offset)const {
        return pack(false,map,row,rows,offset);
    }
    PH_VIRTUAL unsigned pack_b(const unsigned *map,unsigned row,unsigned rows,unsigned offset)const {
        return pack(true,map,row,rows,offset);
    }
};
#undef PH_VIRTUAL
