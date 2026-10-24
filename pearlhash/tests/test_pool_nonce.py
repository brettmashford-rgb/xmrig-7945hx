import unittest
from reference.pool_nonce import nonce_tail
from tools.check_nonce_gpu import cases


class NonceTailTests(unittest.TestCase):
    def test_synthetic_trace_goldens(self):
        vectors = [
            ('00'*8, '00'*8, '24321e37e3c430cbc42a151a02e315cc'),
            ('ff'*8, 'ff'*8, '02c6c525fb31dac73508e3ffc4e8fdec'),
            ('0001020304050607', '0706050403020100', 'e33439e6e70cc21b23402b3a1d070fea'),
        ]
        for worker, miner, expected in vectors:
            self.assertEqual(nonce_tail(bytes.fromhex(worker), bytes.fromhex(miner)).hex(), expected)

    def test_reject_invalid_nonce_widths_and_types(self):
        for bad in [bytes(7), bytes(9), bytearray(8), '00'*8, 0, None]:
            for worker, miner in [(bad, bytes(8)), (bytes(8), bad)]:
                with self.assertRaises(ValueError):
                    nonce_tail(worker, miner)

    def test_batch_boundaries_and_signal_range(self):
        inputs, expected = cases()
        self.assertEqual(len(inputs), 263*16)
        self.assertEqual(len(expected), len(inputs))
        self.assertTrue(all(-64 <= (v if v < 128 else v-256) <= 64 for v in expected))
        self.assertNotEqual(expected[4*16:5*16], expected[5*16:6*16])
        self.assertEqual((inputs, expected), cases())


if __name__ == '__main__':
    unittest.main()
