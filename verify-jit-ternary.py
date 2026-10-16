#!/usr/bin/env python3
"""Execute FDIV_M emitted by the patched JIT against its unchanged fallback.
Requires Linux x86-64, g++, AVX512F/VL with OS support, and patched source path.
This is a component test, not a complete RandomX consensus/hash test.
"""
import pathlib, subprocess, sys, tempfile
source = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.work/xmrig-jit-ternary')
text = (source / 'src/crypto/randomx/jit_compiler_x86.cpp').read_text()
def method(marker):
    start = text.index(marker)
    brace = text.index('{', start)
    level = 1
    end = brace + 1
    while level:
        level += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]
address = method('FORCE_INLINE void JitCompilerX86::genAddressReg(')
address = 'template<bool rax>\n' + address.replace('FORCE_INLINE ', '')
division = method('void JitCompilerX86::h_FDIV_M(')
assert 'ternaryMask' in division, 'Source does not contain the ternary rewrite'
cpp = r'''
#include <cstdint>
#include <cstring>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <immintrin.h>
#include <sys/mman.h>
static const unsigned RegisterNeedsSib=4, RegisterCountFlt=4;
static const uint32_t AddressMask[4]={262136,16376,16376,16376};
struct Instruction {
 unsigned src,dst,mod,imm;
 unsigned getImm32() const {return imm;}
 unsigned getModMem() const {return mod&3;}
};
class JitCompilerX86 {
public:
 uint8_t code[256] = {};
 uint32_t codePos=0, prevFPOperation=0;
 bool hasTernaryLogic=false, hasXOP=false;
 template<bool rax> static void genAddressReg(const Instruction&,unsigned,uint8_t*,uint32_t&);
 static void emitByte(uint8_t v,uint8_t*p,uint32_t&pos){p[pos++]=v;}
 static void emit32(uint32_t v,uint8_t*p,uint32_t&pos){memcpy(p+pos,&v,4);pos+=4;}
 template<size_t N> static void emit(const uint8_t(&v)[N],uint8_t*p,uint32_t&pos){memcpy(p+pos,v,N);pos+=N;}
 void h_FDIV_M(const Instruction&);
};
'''+address+'\n'+division+r'''
using Fn=void(*)(const void*,const uint64_t*,const void*,const void*,void*);
static Fn build(void*page,const Instruction&i,bool ternary){
 std::vector<uint8_t>b;
 auto add=[&](std::initializer_list<uint8_t>x){b.insert(b.end(),x);};
 // Preserve ABI registers, save output pointer; establish the RandomX registers.
 add({0x53,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,0x41,0x50});
 add({0x48,0x89,0xf0,0x48,0x89,0xfe}); // rax=regs, rsi=scratch
 for(unsigned j=0;j<4;++j)add({0x66,0x0f,0x10,uint8_t(0x62+j*8),uint8_t(j*16)});
 add({0x66,0x44,0x0f,0x10,0x29,0x66,0x44,0x0f,0x10,0x71,0x10});
 for(unsigned j=0;j<8;++j)add({0x4c,0x8b,uint8_t(0x40+j*8),uint8_t(j*8)});
 JitCompilerX86 jit;jit.hasTernaryLogic=ternary;jit.h_FDIV_M(i);
 b.insert(b.end(),jit.code,jit.code+jit.codePos);
 add({0x58}); // output pointer
 for(unsigned j=0;j<4;++j)add({0x66,0x0f,0x11,uint8_t(0x60+j*8),uint8_t(j*16)});
 add({0x41,0x5f,0x41,0x5e,0x41,0x5d,0x41,0x5c,0x5b,0xc3});
 memcpy(page,b.data(),b.size());return reinterpret_cast<Fn>(page);
}
int main(){
 __builtin_cpu_init();
 if(!__builtin_cpu_supports("avx512f")||!__builtin_cpu_supports("avx512vl")){
  puts("SKIP: AVX512F/VL and OS support required");return 77;
 }
 void*p=mmap(nullptr,8192,PROT_READ|PROT_WRITE|PROT_EXEC,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(p==MAP_FAILED)return 2;
 std::vector<uint64_t>pad(2097152/8);
 uint64_t rng=0x123456789abcdef0ULL;
 auto next=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
 for(auto&v:pad)v=next();
 alignas(16) uint64_t regs[8],fp[8],masks[4],a[8],b[8];
 const uint32_t imms[]={0,1,0x7fffffff,0x80000000,0xffffffff,0x12345678};
 const unsigned saved=_mm_getcsr();unsigned checks=0;
 for(unsigned src=0;src<8;++src)for(unsigned dst=0;dst<8;++dst)
 for(unsigned mod=0;mod<4;++mod)for(auto imm:imms){
  Instruction i{src,dst,mod,imm};
  Fn old=build(p,i,false), neo=build(static_cast<uint8_t*>(p)+4096,i,true);
  for(unsigned sample=0;sample<32;++sample){
   for(auto&v:regs)v=next();
   for(auto&v:fp)v=next();
   masks[0]=masks[1]=0x00ffffffffffffffULL;
   masks[2]=0x3000000000000000ULL|(next()&0x3fffff);
   masks[3]=0x3000000000000000ULL|(next()&0x3fffff);
   for(unsigned rounding=0;rounding<4;++rounding){
    const unsigned csr=0x9fc0|(rounding<<13);
    _mm_setcsr(csr);old(pad.data(),regs,fp,masks,a);unsigned ca=_mm_getcsr();
    _mm_setcsr(csr);neo(pad.data(),regs,fp,masks,b);unsigned cb=_mm_getcsr();
    if(memcmp(a,b,sizeof a)||ca!=cb){fprintf(stderr,"Mismatch src=%u dst=%u mod=%u imm=%x\n",src,dst,mod,imm);return 1;}
    ++checks;
   }
  }
 }
 _mm_setcsr(saved);munmap(p,8192);
 printf("PASS: %u emitted FDIV_M comparisons, all registers/address modes, four rounding modes; FP bits and MXCSR match\n",checks);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    path = pathlib.Path(tmp)
    (path/'test.cpp').write_text(cpp)
    subprocess.run(['g++','-std=c++11','-O2',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
