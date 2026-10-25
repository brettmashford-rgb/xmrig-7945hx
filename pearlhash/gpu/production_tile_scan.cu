// ISC. Exact 10x16/rank128/K32768/fill64 specialization with warp-owned cache.
#include "warp_tile_scan.cu"

__device__ __forceinline__ unsigned production_pack(const signed char *cache,
    const unsigned *pairs,unsigned row,unsigned offset,const signed char *tail,
    bool live,bool tail_row) {
    if(!live)return 0;
    unsigned packed=0;
    #pragma unroll
    for(unsigned byte=0;byte<4;++byte) {
        unsigned l=offset+byte,pair=pairs[l];
        int signal=tail_row&&l>=32752?int(tail[l-32752]):64;
        int value=signal+int(cache[(pair&65535)*26+row])-int(cache[(pair>>16)*26+row]);
        packed|=(unsigned(value)&255U)<<(byte*8);
    }
    return packed;
}

extern "C" __global__ void production_virtual_tile_scan(const signed char *ua,const signed char *ub,
    const unsigned *pa,const unsigned *pb,const signed char *tail,
    const unsigned *descriptors,const unsigned *bounds,const unsigned *key,
    unsigned *status,unsigned *candidates,unsigned *audit_words,unsigned audit,
    unsigned capacity,unsigned query_count,unsigned m,unsigned n,unsigned k,
    unsigned rank,int fill,unsigned long long generation) {
    unsigned warp=threadIdx.x/32,lane=threadIdx.x%32,query=blockIdx.x*8+warp;
    VirtualScanInput inputs{ua,ub,pa,pb,tail,m,n,k,rank,fill};
    if(blockDim.x!=256||query>=query_count||!inputs.valid()||k!=32768||rank!=128||fill!=64)return;
    const unsigned *desc=descriptors+query*66;
    if(desc[0]!=10||desc[1]!=16)return;
    const unsigned *ra=desc+2,*cb=desc+34;
    bool invalid=lane<10?ra[lane]>=m:(lane<26?cb[lane-10]>=n:false);
    if(__any_sync(0xffffffffU,invalid))return;
    // Transposed small uniform table: 26 rows x128 coefficients per query.
    // Each warp owns a disjoint slice; only a warp fence is required.
    __shared__ signed char uniform_cache[8][26*128];
    signed char *cache=uniform_cache[warp];
    for(unsigned i=lane;i<26*128;i+=32) {
        unsigned row=i/128,index=i%128;
        cache[index*26+row]=row<10?ua[ra[row]*128+index]:ub[cb[row-10]*128+index];
    }
    __syncwarp(0xffffffffU);
    unsigned group=lane/4,thread=lane%4;
    bool last0=ra[group]==m-1,last1=group<2&&ra[group+8]==m-1;
    int d0=0,d1=0,d2=0,d3=0,e0=0,e1=0,e2=0,e3=0;
    unsigned word=0;
    for(unsigned offset=0;offset<32768;offset+=32) {
        unsigned a0=production_pack(cache,pa,group,offset+thread*4,tail,true,last0);
        unsigned a1=production_pack(cache,pa,group+8,offset+thread*4,tail,group<2,last1);
        unsigned a2=production_pack(cache,pa,group,offset+thread*4+16,tail,true,last0);
        unsigned a3=production_pack(cache,pa,group+8,offset+thread*4+16,tail,group<2,last1);
        unsigned b0=production_pack(cache,pb,10+group,offset+thread*4,tail,true,false);
        unsigned b1=production_pack(cache,pb,10+group,offset+thread*4+16,tail,true,false);
        unsigned c0=production_pack(cache,pb,18+group,offset+thread*4,tail,true,false);
        unsigned c1=production_pack(cache,pb,18+group,offset+thread*4+16,tail,true,false);
        mma_accumulate(a0,a1,a2,a3,b0,b1,d0,d1,d2,d3);
        mma_accumulate(a0,a1,a2,a3,c0,c1,e0,e1,e2,e3);
        if((offset+32)%128==0) {
            unsigned folded=unsigned(d0)^unsigned(d1)^unsigned(e0)^unsigned(e1);
            if(group<2)folded^=unsigned(d2)^unsigned(d3)^unsigned(e2)^unsigned(e3);
            for(unsigned delta=16;delta;delta>>=1)folded^=__shfl_xor_sync(0xffffffffU,folded,delta);
            unsigned slot=((offset+32)/128-1)%16;
            if(lane==slot)word=((word<<13)|(word>>19))^folded;
        }
    }
    unsigned words[16];
    #pragma unroll
    for(unsigned i=0;i<16;++i)words[i]=__shfl_sync(0xffffffffU,word,i);
    if(lane)return;
    unsigned digest[8];ph::keyed64(words,key,digest);
    if(audit)for(unsigned i=0;i<16;++i)audit_words[query*16+i]=words[i];
    if(!ph::digest_meets_bound(digest,bounds+query*8))return;
    unsigned slot=atomicAdd(status,1U);
    if(slot>=capacity){atomicExch(status+1,1U);return;}
    unsigned *out=candidates+slot*11;
    out[0]=query;out[1]=unsigned(generation);out[2]=unsigned(generation>>32);
    for(unsigned i=0;i<8;++i)out[3+i]=digest[i];
}
