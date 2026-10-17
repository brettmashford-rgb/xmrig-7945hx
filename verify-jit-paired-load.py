#!/usr/bin/env python3
"""Compare actual paired-load template bytes and original assembly on Linux x86-64.
Requires g++, as, objcopy and AVX2/OS support. Optional --bench times this
component only; its timings cannot predict whole-miner performance.
"""
import pathlib, re, subprocess, sys, tempfile
base=pathlib.Path(__file__).resolve().parent
source=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '.work/xmrig-jit-paired-load')
s=(source/'src/crypto/randomx/jit_compiler_x86.cpp').read_text()
encoded=re.search(r'pairedLoopLoad\[\] = \{(.*?)\};',s,re.S)
assert encoded, 'Patched paired-load template not found'
actual=bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})',encoded.group(1)))
original=(source/'src/crypto/randomx/asm/program_loop_load.inc').read_text()
paired=(base/'jit-paired-load.inc').read_text()
cpp='#include <initializer_list>\n#include <immintrin.h>\n#include <cstdint>\n#include <cstdio>\n#include <cstring>\n#include <chrono>\nextern "C" void original(const void*,void*,uint64_t,const void*,const uint64_t*);\nextern "C" void wide(const void*,void*,uint64_t,const void*,const uint64_t*);\nint main(int argc,char**){\n __builtin_cpu_init();if(!__builtin_cpu_supports("avx2"))return 77;\n alignas(64) uint64_t mem[1024],mask[4],a[42],b[42],offsets[2];uint64_t rng=7;\n auto next=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};\n auto saved=_mm_getcsr();unsigned checks=0;\n for(int i=0;i<10000;++i){\n  offsets[0]=(next()%1000)*8;offsets[1]=(i%4==0)?offsets[0]:(next()%1000)*8;\n  for(auto&v:mem)v=(i==0?0:i==1?~uint64_t(0):i==2?0x8000000080000000ULL:i==3?0x7fffffff7fffffffULL:next()); mask[0]=mask[1]=0x00ffffffffffffffULL;\n  mask[2]=0x3000000000000000ULL|(next()&0x3fffff);mask[3]=0x3000000000000000ULL|(next()&0x3fffff);\n  for(unsigned r=0;r<4;++r){unsigned csr=0x9fc0|(r<<13);\n   _mm_setcsr(csr);original(mem,a,3,mask,offsets);unsigned ca=_mm_getcsr();\n   _mm_setcsr(csr);wide(mem,b,3,mask,offsets);unsigned cb=_mm_getcsr();\n   if(memcmp(a,b,sizeof a)||ca!=cb){printf("FAIL %d %u\\n",i,r);return 1;}++checks;\n  }\n }\n _mm_setcsr(saved);printf("PASS %u output/MXCSR comparisons\\n",checks);\n if(argc<2)return 0;\n for(int i=0;i<8;++i){for(auto fn:{original,wide}){\n  auto start=std::chrono::steady_clock::now();fn(mem,a,10000000,mask,offsets);auto end=std::chrono::steady_clock::now();\n  printf("%s %.2f ns/loop\\n",fn==original?"original":"wide",std::chrono::duration<double,std::nano>(end-start).count()/10000000);\n }}\n}\n'
with tempfile.TemporaryDirectory() as temp:
 p=pathlib.Path(temp)
 (p/'block.S').write_text('.intel_syntax noprefix\n.text\n'+paired)
 subprocess.run(['as',str(p/'block.S'),'-o',str(p/'block.o')],check=True)
 subprocess.run(['objcopy','-O','binary','--only-section=.text',str(p/'block.o'),str(p/'block.bin')],check=True)
 assert (p/'block.bin').read_bytes()==actual, 'Assembly differs from JIT template bytes'
 asm='.intel_syntax noprefix\n.text\n'
 for name,body in [('original',original),('wide','.byte '+','.join(str(x) for x in actual)+'\n')]:
  asm+=f""".global {name}
{name}:
 push rbx
 push r12
 push r13
 push r14
 push r15
 sub rsp,64
 mov [rsp+32],rsi
 mov rsi,rdi
 mov rbx,rdx
 movdqu xmm13,[rcx]
 movdqu xmm14,[rcx+16]
 movdqu xmm8,[rcx]
 movdqu xmm9,[rcx]
 movdqu xmm10,[rcx]
 movdqu xmm11,[rcx]
 movdqu xmm15,[rcx+16]
 mov rax,[r8]
 mov rdx,[r8+8]
 mov r8,1
 mov r9,2
 mov r10,3
 mov r11,4
 mov r12,5
 mov r13,6
 mov r14,7
 mov r15,8
 .balign 64
{name}_loop:
{body}
 dec rbx
 jnz {name}_loop
 mov rcx,[rsp+32]
"""
  for j in range(8):asm+=f' mov [rcx+{j*8}],r{8+j}\n'
  for j in range(8):asm+=f' movdqu [rcx+{64+j*16}],xmm{j}\n'
  for j,reg in enumerate([8,9,10,11,13,14,15]):asm+=f' movdqu [rcx+{192+j*16}],xmm{reg}\n'
  asm+=' mov rdi,[rsp+16]\n mov [rcx+304],rdi\n mov rdi,[rsp+24]\n mov [rcx+312],rdi\n mov [rcx+320],rax\n mov [rcx+328],rdx\n'
  asm+=' vzeroupper\n add rsp,64\n pop r15\n pop r14\n pop r13\n pop r12\n pop rbx\n ret\n'
 asm+='.section .note.GNU-stack,"",@progbits\n'
 (p/'test.S').write_text(asm);(p/'test.cpp').write_text(cpp)
 subprocess.run(['g++','-std=c++11','-O2',str(p/'test.cpp'),str(p/'test.S'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')]+(['--bench'] if '--bench' in sys.argv else []),check=True)
 print('PASS: assembled template equals the bytes embedded in the patched JIT')
