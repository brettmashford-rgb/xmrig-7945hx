"""CPU packed-byte versus GPU u32 transcript regression. ISC."""
import struct
import unittest

from tools.check_warp_gpu import expected_transcripts
from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import TileQuery
from tools.virtual_scan import global_reference


class WarpTranscriptTests(unittest.TestCase):
    def test_full_u32_words_are_decoded_not_compared_as_bytes(self):
        q=TileQuery((0,),(0,))
        words=(0,0xffffffff,0x80000000,0x12345678)+tuple(range(12))
        raw=struct.pack('<16I',*words)
        refs={q:(raw,bytes(32))}
        self.assertEqual(expected_transcripts(refs,(q,q)),(words,words))
        self.assertNotEqual(tuple(raw),words)
        for malformed in(raw[:-1],raw+b'\0',list(raw)):
            with self.assertRaises(ValueError):expected_transcripts({q:(malformed,bytes(32))},(q,))

    def test_real_cpu_reference_matches_gpu_audit_representation(self):
        p=ConstantProfile(3,7,1024,32,64,bytes(16),bytes(32),bytes([1])*32)
        qs=(TileQuery((0,),(0,)),TileQuery((2,),(6,)))
        refs=dict(zip(qs,global_reference(p,qs)))
        expected=expected_transcripts(refs,qs)
        self.assertEqual(tuple(len(w)for w in expected),(16,16))
        for q,words in zip(qs,expected):
            self.assertEqual(struct.pack('<16I',*words),refs[q][0])
            self.assertNotEqual(tuple(refs[q][0]),words)


if __name__=='__main__':unittest.main()
