"""Ordered cache packing and compatibility with the validated row-major control. ISC."""
from types import SimpleNamespace
import unittest
from tools.fragment_scan import FragmentCache
from tools.cached_scan import RowCache,row_plan
from tools.check_production_gpu import cases
from tools.check_tile_scan_gpu import TileQuery


class FragmentTests(unittest.TestCase):
    def test_first_use_order_gives_contiguous_local_rows(self):
        _,profile,queries,_=list(cases())[0]
        query=TileQuery(tuple(reversed(queries[0].rows)),tuple(reversed(queries[0].cols)))
        a,b,size=FragmentCache.plan_rows(profile,(query,queries[1],query))
        self.assertEqual(a[:10],query.rows);self.assertEqual(b[:16],query.cols)
        self.assertEqual((len(a),len(b),size),(11,17,28*32768))
        cache=object.__new__(FragmentCache);cache.closed=False
        cache.tables=SimpleNamespace(profile=profile)
        cache.maps=({r:i for i,r in enumerate(a)},{c:i for i,c in enumerate(b)})
        remapped=cache.remap((query,query))
        self.assertEqual(remapped[0].rows,tuple(range(10)))
        self.assertEqual(remapped[0].cols,tuple(range(16)))
        self.assertEqual(remapped[0],remapped[1])

    def test_control_layout_and_kernels_remain_separate(self):
        _,profile,queries,_=list(cases())[0]
        self.assertEqual(RowCache.plan_rows(profile,queries),row_plan(profile,queries))
        self.assertEqual(RowCache.materialize_kernel,b'materialize_selected_rows')
        self.assertEqual(RowCache.scan_kernel,b'cached_tile_scan')
        self.assertEqual(FragmentCache.materialize_kernel,b'materialize_fragment_rows')
        self.assertEqual(FragmentCache.scan_kernel,b'fragment_cached_tile_scan')
        with self.assertRaises(ValueError):FragmentCache.plan_rows(profile,())


if __name__=='__main__':unittest.main()
