"""Select the independent one-query-per-warp kernel; same bounded queue ABI. ISC."""
from tools.wide_scan import WideCandidateScanner


class WarpCandidateScanner(WideCandidateScanner):
    def __init__(self):
        super().__init__()
        self.warp_enabled = True

    def kernel_launch(self, query_count):
        if self.warp_enabled:
            return b'warp_virtual_tile_scan', (query_count+7)//8
        return super().kernel_launch(query_count)
