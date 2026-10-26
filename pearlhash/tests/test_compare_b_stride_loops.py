"""Balanced same-range timing and conservative three-way selection. ISC."""
from collections import Counter
from types import SimpleNamespace
import unittest
from tools.compare_b_stride_loops import MODES,ORDERS,ROUNDS,WINDOW,summary,run_window


class Comparison(unittest.TestCase):
    def test_all_six_orders_are_balanced(self):
        self.assertEqual(len(ORDERS),6);self.assertEqual(ROUNDS%6,0)
        for position in range(3):self.assertEqual(Counter(order[position]for order in ORDERS),Counter({m:2 for m in MODES}))
    def test_requires_margin_over_baseline(self):
        setup={m:.2 for m in MODES};samples={m:[1.]*ROUNDS for m in MODES}
        samples[MODES[2]]=[.98]*ROUNDS
        self.assertEqual(summary(samples,setup)['preferred'],MODES[0])
        samples[MODES[1]]=[.9]*ROUNDS
        result=summary(samples,setup)
        self.assertEqual(result['preferred'],MODES[1]);self.assertEqual(result['unique_timed_tiles_per_mode'],ROUNDS*WINDOW)
        samples[MODES[2]]=[.8]*ROUNDS
        self.assertEqual(summary(samples,setup)['preferred'],MODES[2])
    def test_invalid_or_incomplete_samples_rejected(self):
        for values in ([1.]*(ROUNDS-1),[float('nan')]*ROUNDS,[0.]*ROUNDS):
            samples={m:[1.]*ROUNDS for m in MODES};samples[MODES[1]]=values
            with self.assertRaises(ValueError):summary(samples,{m:0. for m in MODES})
    def test_same_odd_tile_interval_and_exact_4096_step(self):
        class Search:
            def __init__(self):self.cursor=SimpleNamespace(next_tile=17);self.steps=[]
            def advance(self,amount):
                self.steps.append(amount);self.cursor.next_tile+=amount;return None,self.cursor
        for mode in MODES:
            search=Search();self.assertEqual(run_window(search,mode,4099),(17,4116));self.assertEqual(search.steps,[4096,3])


if __name__=='__main__':unittest.main()
