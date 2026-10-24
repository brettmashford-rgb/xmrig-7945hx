"""Independent CPU differential checks. No GPU execution claims. ISC."""
import copy
import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from tools.check_noise_mma_gpu import parse_noise_fixture,reference_tables,synthetic_cases
from tools.check_mma_gpu import scalar_reference

BASE=Path(__file__).resolve().parents[1]


def as_fixture(case):
    matrix=case.matrix();_,words,digest=scalar_reference(matrix)
    values=matrix.a+matrix.bt;indices=case.indices_a+case.indices_b
    signals=case.signal_a+case.signal_b
    return (b'PHGPU02\0'+struct.pack('<4I',matrix.rows,matrix.cols,case.k,case.rank)
            +struct.pack(f'<{len(values)}i',*values)+words+case.seed_a+case.seed_b
            +struct.pack(f'<{len(indices)}I',*indices)+struct.pack(f'<{len(signals)}i',*signals)+digest)


class NoiseMmaTests(unittest.TestCase):
    def test_official_generated_v2_v3_noise_matches_saved_matrices_and_digest(self):
        for version in (2,3):
            path=BASE/f'tests/gpu-noise/official-v{version}.bin'
            if not path.is_file():self.skipTest('large official-generated fixtures not bundled')
            case=parse_noise_fixture(path.read_bytes());matrix=case.matrix()
            scalar_reference(matrix)

    def test_local_fixture_signal_seed_index_and_digest_corruption_reject(self):
        case=next(synthetic_cases());raw=as_fixture(case)
        actual=parse_noise_fixture(raw)
        self.assertEqual(actual.matrix().a,case.matrix().a)
        matrix=actual.matrix();scalar_reference(matrix)
        size=(len(case.indices_a)+len(case.indices_b))*case.k*4
        index_pos=24+size+128
        signal_pos=index_pos+(len(case.indices_a)+len(case.indices_b))*4
        for pos in (24+size+64,signal_pos,len(raw)-1):
            bad=bytearray(raw);bad[pos]^=1
            with self.assertRaises(ValueError):scalar_reference(parse_noise_fixture(bytes(bad)).matrix())
        for pos,value in ((index_pos,0xffffffff),(signal_pos,65)):
            bad=bytearray(raw);struct.pack_into('<I',bad,pos,value)
            with self.assertRaises(ValueError):parse_noise_fixture(bytes(bad))
        bad=copy.deepcopy(case);bad.indices_a[0]=True
        with self.assertRaises(ValueError):bad.validate()
        bad=copy.deepcopy(case);bad.signal_a[0]=65
        with self.assertRaises(ValueError):bad.validate()

    def test_cpu_execution_of_actual_noise_kernel_bodies_and_guards(self):
        with tempfile.TemporaryDirectory()as tmp:
            libpath=Path(tmp)/'noise-check.so'
            subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC',
                            str(BASE/'tests/noise_tables_cpu.cpp'),'-o',str(libpath)],check=True)
            lib=C.CDLL(str(libpath))
            lib.check_noise_uniform.argtypes=[C.c_void_p]*3+[C.c_uint]*3
            lib.check_noise_permutation.argtypes=[C.c_void_p]*2+[C.c_uint]*3
            lib.check_noise_apply.argtypes=[C.c_void_p]*4+[C.c_uint]*3
            def guarded(n):
                buffer=C.create_string_buffer(b'\xa5'*(n+32),n+32)
                return buffer,C.cast(C.byref(buffer,16),C.c_void_p)
            for case in synthetic_cases():
                matrix=case.matrix()
                for side,expected in zip(case.sides(),(matrix.a,matrix.bt)):
                    indices,signal,key,label=side;rows=len(indices)
                    uniform,pairs=reference_tables(indices,case.k,case.rank,label,key)
                    ub,u=guarded(len(uniform));pb,p=guarded(len(pairs));nb,n=guarded(len(expected))
                    domain=int.from_bytes(label[:4],'little')
                    packed=struct.pack(f'<{rows}I',*indices)
                    lib.check_noise_uniform(packed,key,u,rows,case.rank,domain)
                    lib.check_noise_permutation(key,p,case.k,case.rank,domain)
                    lib.check_noise_apply(bytes(v&255 for v in signal),u,p,n,rows,case.k,case.rank)
                    for buffer,value in ((ub,uniform),(pb,pairs),(nb,bytes(v&255 for v in expected))):
                        self.assertEqual(buffer.raw[:16],b'\xa5'*16)
                        self.assertEqual(buffer.raw[-16:],b'\xa5'*16)
                        self.assertEqual(buffer.raw[16:-16],value)


if __name__=='__main__':unittest.main()
