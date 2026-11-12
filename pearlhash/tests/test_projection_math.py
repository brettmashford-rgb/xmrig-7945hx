"""Independent exact algebra, every checkpoint, signed corrections and PTX contracts. ISC."""
from pathlib import Path
import random,re,struct,subprocess,tempfile,unittest
from tools.projection_reference import project,dot_from_projection,signed8
from reference.dense import noise_rows,_random_hash,jackpot
ROOT=Path(__file__).resolve().parents[1]

class Algebra(unittest.TestCase):
    def test_all_256_checkpoints_and_scalar_transcript_with_tail(self):
        for seed in (bytes(32),bytes([117])*32):
            a_seed=bytes(v^73 for v in seed);rows=[0,5119,5120];cols=[0,262143]
            a=noise_rows(32768,128,rows,b'A_tensor',a_seed);b=noise_rows(32768,128,cols,b'B_tensor',seed)
            a=[[v+64 for v in row]for row in a];b=[[v+64 for v in row]for row in b]
            a[-1][-16:]=[v-128 for v in a[-1][-16:]]
            pairs=[]
            for block in range(4096):
                for v in struct.unpack('<8I',_random_hash(block,b'B_tensor',seed,1)):
                    first=v&127;pairs.append((first,first^(1+((127*v)>>32))))
            uniforms=[]
            for row in cols:
                u=[]
                for block in range(row*4,row*4+4):u.extend((v&63)-32 for v in _random_hash(block,b'B_tensor',seed,0))
                uniforms.append(u)
            direct=[[0]*2 for _ in rows];reformed=[[0]*2 for _ in rows];transcript=[0]*16
            for q in range(256):
                selected=pairs[q*128:(q+1)*128]
                for i in range(3):
                    segment=a[i][q*128:(q+1)*128];p=project(segment,selected)
                    for j in range(2):
                        direct[i][j]+=sum(x*y for x,y in zip(segment,b[j][q*128:(q+1)*128]))
                        reformed[i][j]+=dot_from_projection(p,uniforms[j],selected)
                self.assertEqual(direct,reformed)
                folded=0
                for row in reformed:
                    for v in row:folded^=v&0xffffffff
                slot=q%16;old=transcript[slot];transcript[slot]=(((old<<13)|(old>>19))&0xffffffff)^folded
            self.assertEqual(transcript,jackpot(a,b,128))
    def test_forced_positive_128_coefficient_and_large_tail_corrections(self):
        pairs=[(0,1)]*128;a=[64]*112+[-127]*16;u=[-32,31]+[0]*126
        projected=project(a,pairs)
        self.assertEqual(projected[1],[(0,-12),(1,12)])
        self.assertEqual(dot_from_projection(projected,u,pairs),5136)
        self.assertNotEqual(sum(x*y for x,y in zip(projected[0],u))+64*projected[2]+64*(-8064)+524288,5136)
    def test_general_adversarial_signed_values_and_sparse_assembly(self):
        rng=random.Random(84)
        for case in range(64):
            pairs=[(rng.randrange(128),rng.randrange(128))for _ in range(128)]
            a=[rng.randrange(-127,128)for _ in range(128)];u=[rng.randrange(-32,32)for _ in range(128)]
            expected=sum(v*(64+u[first]-u[second])for v,(first,second)in zip(a,pairs))
            self.assertEqual(dot_from_projection(project(a,pairs),u,pairs),expected)
    def test_XOR_cannot_replace_integer_addition_or_drop_constant_bias(self):
        self.assertNotEqual((1+1)^(2+1),(1^2)^(1^1))
        pairs=[(0,1)]*128;u=[-32,31]+[0]*126
        self.assertEqual(dot_from_projection(project([64]*128,pairs),u,pairs),8192)
    def test_compiled_unsigned_low_and_high_encoding_no_undefined_shift(self):
        code='''#include "projection_math.h"
#include <cassert>
int main(){for(int v=-24448;v<=24448;++v){int lo=projection_low(v),hi=projection_high(v);assert(lo>=-128&&lo<=127);assert(hi>=-128&&hi<=127);assert(lo+256*hi==v);for(unsigned r=0;r<128;r+=7){auto rec=projection_record(r,hi);assert((rec&127U)==r);assert(projection_record_high(rec)==hi);}}}'''
        with tempfile.TemporaryDirectory()as temp:
            source=Path(temp)/'test.cpp';out=Path(temp)/'test';source.write_text(code)
            subprocess.run(['g++','-O2','-std=c++17','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'gpu'),str(source),'-o',str(out)],check=True,capture_output=True)
            subprocess.run([str(out)],check=True,capture_output=True)
    def test_uniform_fragment_layout_matches_documented_MMA_B_layout(self):
        for side in range(2):
            uniform=[[((side*17+row*11+r*7)%64)-32 for r in range(128)]for row in range(16)]
            cache=bytearray(128*24)
            for row in range(16):
                for r in range(128):cache[r*24+row]=uniform[row][r]&255
            for step in range(4):
                for lane in range(32):
                    group,thread=divmod(lane,4)
                    for upper in(0,1):
                        for half in(0,16):
                            offset=step*32+half+thread*4
                            packed=bytes(cache[(offset+i)*24+group+upper*8]for i in range(4))
                            self.assertEqual(tuple(signed8(v)for v in packed),tuple(uniform[group+upper*8][offset:offset+4]))

class Kernel(unittest.TestCase):
    def test_control_and_collector_byte_identical_candidate_six_MMA(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.84-scan-sm120.ptx').read_text();old=(ROOT/'releases/pearlhash-dev-v0.0.80-scan-sm120.ptx').read_text()
        def entry(s,n):return s.split('.visible .entry '+n+'(',1)[1].split('.visible .entry ',1)[0].split('\n\t// .globl',1)[0]
        for name in('a_pair_direct_scan','resident_guard_snapshot'):self.assertEqual(entry(raw,name),entry(old,name))
        body=entry(raw,'projected_pair_scan');self.assertEqual(body.split(')')[0].count('.param '),28);self.assertEqual(body.count('mma.sync'),6)
    def test_all_checkpoint_folding_unchanged_no_B_reconstruction_or_barriers_in_hot_loop(self):
        raw=(ROOT/'gpu/projected_scan.cu').read_text();old=(ROOT/'gpu/a_share_scan.cu').read_text()
        fold='            unsigned slot=((offset+32)/128-1)%16;'
        self.assertEqual(raw.split(fold,1)[1].split('        if(!ShareA',1)[0],old.split(fold,1)[1].split('        if(!ShareA',1)[0])
        self.assertEqual(raw.split('    unsigned words0',1)[1].split('extern "C" __global__',1)[0],old.split('    unsigned words0',1)[1].split('extern "C" __global__',1)[0])
        loop=raw.split('    for(unsigned chunk=0;chunk<32768;chunk+=Steps*32U){',1)[1].split('    unsigned words0',1)[0]
        self.assertNotIn('__syncthreads',loop);self.assertNotIn('b_transpose',loop)
        self.assertEqual(loop.count('projection_adjust('),5);self.assertEqual(loop.count('mma_accumulate('),6)
        self.assertIn('projection_high(v)',raw);self.assertIn('if(v==128)special[q]',raw)

if __name__=='__main__':unittest.main()
