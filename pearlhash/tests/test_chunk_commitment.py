"""Commitment leaf boundaries and BLAKE3 CV/root domain checks. ISC."""
import json
from pathlib import Path
import unittest
from reference.native_hash import chunk_value,parents,small_hash
from tools.check_commitment_gpu import cases,validate_case,TWO_CHUNK_ROOT

class ChunkCommitmentTests(unittest.TestCase):
    def test_official_compressor_synthetic_goldens(self):
        goldens=json.loads((Path(__file__).parent/'chunk-cv-goldens.json').read_text())['batches']
        batches=list(cases());self.assertEqual(len(batches),len(goldens))
        for (first,count,key,data,expected),golden in zip(batches,goldens):
            validate_case(first,count,key,data,expected)
            self.assertEqual((first,count,key.hex()),(golden['first'],golden['count'],golden['key']))
            self.assertEqual(expected.hex(),''.join(golden['cvs']))

    def test_chaining_value_is_not_a_root_digest(self):
        first,count,key,data,expected=next(cases())
        self.assertNotEqual(expected[:32],small_hash(data[:1024],key))
        self.assertEqual(parents([expected[:32],expected[32:64]],key,root=True)[0],TWO_CHUNK_ROOT)

    def test_invalid_counter_and_range(self):
        key=bytes(32);block=bytes(1024)
        for index in (-1,1<<64,True,1.5):
            with self.assertRaises(ValueError):chunk_value(block,index,key)
        with self.assertRaises(ValueError):chunk_value(block[:-1],0,key)
        for first,count in ((-1,1),(1<<64,0),((1<<64)-1,2),(0,4097)):
            with self.assertRaises(ValueError):validate_case(first,count,key,b'',b'')

if __name__=='__main__':unittest.main()
