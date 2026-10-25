"""Cache size limits and global-to-local binding validation before GPU work. ISC."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from tools.cached_scan import row_plan,RowCache,CACHE_CAP
from tools.check_production_gpu import cases
from tools.check_tile_scan_gpu import TileQuery


class CacheTests(unittest.TestCase):
    def test_deduplicates_rows_and_preserves_query_order_and_duplicates(self):
        _,profile,queries,_=list(cases())[0]
        a,b,size=row_plan(profile,queries+queries)
        self.assertEqual((len(a),len(b),size),(11,17,28*32768))
        cache=object.__new__(RowCache);cache.closed=False
        cache.tables=SimpleNamespace(profile=profile)
        cache.maps=({r:i for i,r in enumerate(a)},{c:i for i,c in enumerate(b)})
        reversed_query=TileQuery(tuple(reversed(queries[0].rows)),tuple(reversed(queries[0].cols)))
        mapped=cache.remap((reversed_query,queries[0],queries[0]))
        self.assertEqual(mapped[0].rows,tuple(reversed(range(10))))
        self.assertEqual(mapped[1],mapped[2])
        with self.assertRaises(ValueError):cache.remap((replace(queries[0],rows=(True,)+queries[0].rows[1:]),))
        cache.closed=True
        with self.assertRaises(ValueError):cache.remap(queries)

    def test_cap_and_profile_rejected_before_any_allocation(self):
        _,profile,_,_=list(cases())[1]
        queries=tuple(TileQuery(tuple(range(10)),tuple(range(16*i,16*i+16)))for i in range(300))
        class Device:
            def allocate(self,*args):raise AssertionError('invalid cache allocated GPU memory')
        tables=SimpleNamespace(profile=profile,device=Device(),closed=False)
        with self.assertRaisesRegex(ValueError,'128 MiB'):RowCache(tables,queries)
        with self.assertRaises(ValueError):row_plan(replace(profile,k=4096),queries[:1])
        with self.assertRaises(ValueError):row_plan(profile,())
        self.assertEqual(CACHE_CAP,128*1024*1024)

    def test_missing_global_row_cannot_alias_a_local_row(self):
        _,profile,queries,_=list(cases())[1]
        a,b,_=row_plan(profile,queries[:1]);cache=object.__new__(RowCache)
        cache.closed=False;cache.tables=SimpleNamespace(profile=profile)
        cache.maps=({r:i for i,r in enumerate(a)},{c:i for i,c in enumerate(b)})
        with self.assertRaisesRegex(ValueError,'absent'):cache.remap(queries[1:])


if __name__=='__main__':unittest.main()
