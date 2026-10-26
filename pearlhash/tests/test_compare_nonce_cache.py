"""Nonce timing includes cache construction and makes no GPU speed claim. ISC."""
import unittest
from tools.compare_nonce_cache import MODES,ROUNDS,summary


class Comparison(unittest.TestCase):
    def test_includes_one_cache_build_in_total_and_preference(self):
        samples={MODES[0]:[1.]*ROUNDS,MODES[1]:[.01]*ROUNDS}
        result=summary(samples,15.)
        self.assertEqual(result['preferred'],MODES[1]);self.assertAlmostEqual(result['speedup_nonce_preparation'],100.)
        self.assertAlmostEqual(result['total_seconds_including_cache_build'][MODES[1]],15.2)
        self.assertEqual(summary(samples,20.)['preferred'],MODES[0])
    def test_invalid_or_incomplete_samples_rejected(self):
        for values in ([1.]*(ROUNDS-1),[float('nan')]*ROUNDS,[float('inf')]*ROUNDS,[0.]*ROUNDS):
            with self.assertRaises(ValueError):summary({MODES[0]:[1.]*ROUNDS,MODES[1]:values},1.)
        for setup in (-1,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):summary({m:[1.]*ROUNDS for m in MODES},setup)
    def test_round_order_is_balanced(self):
        orders=[MODES if i%2==0 else MODES[::-1]for i in range(ROUNDS)]
        self.assertEqual(orders.count(MODES),10);self.assertEqual(orders.count(MODES[::-1]),10)


if __name__=='__main__':unittest.main()
