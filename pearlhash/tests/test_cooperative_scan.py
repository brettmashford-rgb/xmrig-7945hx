"""Cross-product coverage and rejection before collective GPU barriers. ISC."""
from dataclasses import replace
import unittest
from tools.cooperative_scan import cooperative_queries,validate_cooperative
from tools.check_tile_scan_gpu import TileQuery


class CooperativeTests(unittest.TestCase):
    def test_exact_coverage_and_block_order(self):
        rows=tuple(tuple(range(a*10,a*10+10))for a in range(4))
        cols=tuple(tuple(range(b*16,b*16+16))for b in range(16))
        queries=cooperative_queries(rows,cols);validate_cooperative(queries)
        self.assertEqual(len(queries),64)
        self.assertEqual(set(queries),{TileQuery(a,b)for a in rows for b in cols})
        self.assertEqual(queries[:16],tuple(TileQuery(a,b)for a in rows[:2]for b in cols[:8]))
        self.assertEqual(queries[16:32],tuple(TileQuery(a,b)for a in rows[:2]for b in cols[8:]))

    def test_malformed_groups_and_partial_blocks_rejected(self):
        rows=(tuple(range(10)),tuple(range(10,20)))
        cols=tuple(tuple(range(i*16,i*16+16))for i in range(8))
        queries=cooperative_queries(rows,cols)
        for bad in (queries[:15],(),queries+(queries[0],),
                    (replace(queries[0],rows=rows[1]),)+queries[1:],
                    queries[:8]+(replace(queries[8],cols=cols[1]),)+queries[9:]):
            with self.assertRaises(ValueError):validate_cooperative(bad)
        with self.assertRaises(ValueError):cooperative_queries(rows[:1],cols)
        with self.assertRaises(ValueError):cooperative_queries(rows,cols[:7])


if __name__=='__main__':unittest.main()
