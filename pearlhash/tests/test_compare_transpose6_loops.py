"""Stride six versus v57 paired timing keep controls, tile ranges and conservative selection. ISC."""
from collections import Counter
from types import SimpleNamespace
import unittest
from tools.compare_transpose6_loops import BASELINE,VARIANTS,ROUNDS,WINDOW,modes_for,summary,run_window


class Comparison(unittest.TestCase):
    def test_both_tests_alternate_twelve_rounds_each_order(self):
        for variant in VARIANTS:
            modes=modes_for(variant);orders=(modes,modes[::-1])
            for position in range(2):
                self.assertEqual(Counter(orders[r%2][position]for r in range(ROUNDS)),Counter({m:12 for m in modes}))
    def test_each_test_requires_margin_over_its_control(self):
        for variant in VARIANTS:
            modes=modes_for(variant);setup={m:.2 for m in modes};samples={m:[1.]*ROUNDS for m in modes}
            samples[modes[1]]=[.98]*ROUNDS
            self.assertEqual(summary(samples,setup,variant)['preferred'],BASELINE)
            samples[modes[1]]=[.9]*ROUNDS
            result=summary(samples,setup,variant)
            self.assertEqual(result['preferred'],modes[1]);self.assertEqual(result['unique_timed_tiles_per_mode'],ROUNDS*WINDOW)
    def test_invalid_or_incomplete_samples_rejected(self):
        for variant in VARIANTS:
            modes=modes_for(variant)
            for values in ([1.]*(ROUNDS-1),[float('nan')]*ROUNDS,[float('inf')]*ROUNDS,[0.]*ROUNDS):
                samples={m:[1.]*ROUNDS for m in modes};samples[modes[1]]=values
                with self.assertRaises(ValueError):summary(samples,{m:0. for m in modes},variant)
        with self.assertRaises(ValueError):modes_for('invalid')
    def test_same_odd_tile_interval_and_exact_4096_step(self):
        class Search:
            def __init__(self):self.cursor=SimpleNamespace(next_tile=17);self.steps=[]
            def advance(self,amount):
                self.steps.append(amount);self.cursor.next_tile+=amount;return None,self.cursor
        for mode in (BASELINE,*VARIANTS.values()):
            search=Search();self.assertEqual(run_window(search,mode,4099),(17,4116));self.assertEqual(search.steps,[4096,3])
    def test_unexpected_candidate_or_cursor_gap_rejected(self):
        for hit,position in ((object(),4096),(None,4095)):
            search=SimpleNamespace(cursor=SimpleNamespace(next_tile=0),advance=lambda amount:(hit,SimpleNamespace(next_tile=position)))
            with self.assertRaises(RuntimeError):run_window(search,BASELINE,4096)


if __name__=='__main__':unittest.main()
