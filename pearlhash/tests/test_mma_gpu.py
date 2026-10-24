"""Scalar math and bounded local fixture parsing; no GPU claims. ISC."""
import copy
import struct
import unittest
from tools.check_mma_gpu import MatrixCase,parse_fixture,scalar_reference,synthetic_cases


def fixture(case):
    products,words,digest=scalar_reference(case)
    raw=b'PHGPU02\0'+struct.pack('<4I',case.rows,case.cols,case.k,case.rank)
    raw+=struct.pack(f'<{len(case.a)+len(case.bt)}i',*(case.a+case.bt))
    raw+=words+case.key+bytes(32)+bytes((case.rows+case.cols)*4)
    raw+=bytes((case.rows+case.cols)*case.k*4)+digest
    return raw


class MmaReferenceTests(unittest.TestCase):
    def test_signed_extreme_and_prefix_persistence(self):
        case=next(synthetic_cases());products,words,digest=scalar_reference(case)
        self.assertEqual(struct.unpack('<i',products),(-127*127*32,))
        self.assertEqual(struct.unpack('<16I',words)[0],(-127*127*32)&0xffffffff)
        case=MatrixCase('persistent',1,1,64,32,[1]*64,[2]*64,bytes(32))
        products,_,_=scalar_reference(case)
        self.assertEqual(struct.unpack('<2i',products),(64,128))

    def test_fixture_roundtrip_and_rejections(self):
        case=next(synthetic_cases());raw=fixture(case);decoded=parse_fixture(raw)
        self.assertEqual(scalar_reference(decoded),scalar_reference(case))
        for bad in (b'wrong!!!'+raw[8:],raw[:-1],raw+b'x',raw[:8]+struct.pack('<I',33)+raw[12:]):
            with self.assertRaises(ValueError):parse_fixture(bad)
        bad=bytearray(raw);bad[24:28]=struct.pack('<i',-128)
        with self.assertRaises(ValueError):parse_fixture(bytes(bad))
        bad=bytearray(raw);bad[24+(case.rows+case.cols)*case.k*4]^=1
        with self.assertRaises(ValueError):scalar_reference(parse_fixture(bytes(bad)))
        bad=bytearray(raw);bad[-1]^=1
        with self.assertRaises(ValueError):scalar_reference(parse_fixture(bytes(bad)))

    def test_scalar_one_hot_edges_and_slot_reuse(self):
        cases=list(synthetic_cases());case=cases[1]
        products,_,_=scalar_reference(case);values=struct.unpack(f'<{len(products)//4}i',products)
        for step in range(2):
            for row in range(case.rows):
                offset=(row*7)%case.k;amplitude=(-1 if row%2 else 1)*(row%7+1)
                for col in range(case.cols):
                    expected=amplitude*case.bt[col*case.k+offset]if offset<(step+1)*32 else 0
                    self.assertEqual(values[step*case.rows*case.cols+row*case.cols+col],expected)
        case=MatrixCase('slot-reuse',1,1,1056,32,[1]*1056,[1]*1056,bytes(32))
        _,words,_=scalar_reference(case);expected=[0]*16
        for step in range(33):
            slot=step%16;old=expected[slot]
            expected[slot]=(((old<<13)|(old>>19))&0xffffffff)^((step+1)*32)
        self.assertEqual(struct.unpack('<16I',words),tuple(expected))

if __name__=='__main__':unittest.main()
