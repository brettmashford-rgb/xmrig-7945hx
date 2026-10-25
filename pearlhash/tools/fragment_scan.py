"""Immutable K-major 16-byte fragments in first-use row order. ISC."""
from tools.cached_scan import RowCache,row_plan


class FragmentCache(RowCache):
    materialize_kernel=b'materialize_fragment_rows'
    scan_kernel=b'fragment_cached_tile_scan'

    @staticmethod
    def plan_rows(profile,queries):
        _,_,size=row_plan(profile,queries)
        # Keep a tile's ordered rows adjacent where they have not appeared yet;
        # mapping still handles arbitrary overlaps, duplicates and reversals.
        return (tuple(dict.fromkeys(r for q in queries for r in q.rows)),
                tuple(dict.fromkeys(c for q in queries for c in q.cols)),size)
