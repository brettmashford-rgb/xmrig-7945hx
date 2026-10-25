"""Explicit 2-A by 8-B query blocks over immutable fragment inputs. ISC."""
from tools.fragment_scan import FragmentCache
from tools.check_tile_scan_gpu import TileQuery


def validate_cooperative(queries):
    if not queries or len(queries)>4096 or len(queries)%16:
        raise ValueError('cooperative batches require a positive multiple of 16 queries, up to 4096')
    for start in range(0,len(queries),16):
        block=queries[start:start+16]
        for a in range(2):
            rows=block[a*8].rows
            for b in range(8):
                query=block[a*8+b]
                if query.rows!=rows or query.cols!=block[b].cols:
                    raise ValueError('cooperative batch is not an ordered 2 by 8 cross-product')


def cooperative_queries(rows,cols):
    if not rows or not cols or len(rows)%2 or len(cols)%8:
        raise ValueError('even A groups and a multiple of eight B groups required')
    return tuple(TileQuery(rows[a+i],cols[b+j])for a in range(0,len(rows),2)
                 for b in range(0,len(cols),8)for i in range(2)for j in range(8))


class CooperativeCache(FragmentCache):
    scan_kernel=b'cooperative_tile_scan'
