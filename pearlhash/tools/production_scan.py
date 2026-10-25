"""Strict production-profile selector; shared-cache kernel or validated warp baseline. ISC."""
from tools.warp_scan import WarpCandidateScanner


def require_production(profile, queries):
    if (profile.k,profile.rank,profile.fill)!=(32768,128,64):
        raise ValueError('production kernel requires K32768/rank128/fill64')
    if any(len(q.rows)!=10 or len(q.cols)!=16 for q in queries):
        raise ValueError('production kernel requires 10x16 queries')


class ProductionCandidateScanner(WarpCandidateScanner):
    def __init__(self):
        super().__init__()
        self.production_enabled=True

    def kernel_launch(self, query_count):
        if self.production_enabled:
            return b'production_virtual_tile_scan',(query_count+7)//8
        return super().kernel_launch(query_count)

    def scan_wide(self,tables,queries,bounds,capacity,generation,*,audit=False):
        if self.production_enabled:require_production(tables.profile,queries)
        return super().scan_wide(tables,queries,bounds,capacity,generation,audit=audit)
