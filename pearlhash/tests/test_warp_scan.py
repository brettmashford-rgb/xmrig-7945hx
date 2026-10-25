"""Warp launch coverage and host ABI/audit allocation contract. ISC."""
import ctypes as C
from types import SimpleNamespace
import unittest

from tools.check_range_scan_gpu import ConstantProfile
from tools.check_tile_scan_gpu import TileQuery
from tools.warp_scan import WarpCandidateScanner


class WarpScanTests(unittest.TestCase):
    def test_launch_covers_partial_and_full_grids_without_missing_queries(self):
        device=object.__new__(WarpCandidateScanner);device.warp_enabled=True
        for count in(1,7,8,9,67,4096):
            kernel,blocks=device.kernel_launch(count)
            self.assertEqual(kernel,b'warp_virtual_tile_scan')
            actual=[block*8+warp for block in range(blocks)for warp in range(8)if block*8+warp<count]
            self.assertEqual(actual,list(range(count)))
        device.warp_enabled=False
        self.assertEqual(device.kernel_launch(67),(b'virtual_tile_scan',67))

    def test_audit_buffers_and_kernel_abi_keep_query_count_not_block_count(self):
        class Device(WarpCandidateScanner):
            def __init__(self):
                self.warp_enabled=True;self.allocations=[];self.sizes=[];self.launches=[]
                self.dispatches=self.wide_dispatches=self.unique_cpu_checks=self.verified_tiles=0
            def allocate(self,data):
                pointer=SimpleNamespace(value=len(self.sizes)+100)
                self.sizes.append(len(data));self.allocations.append(pointer);return pointer
            def guarded(self,size):
                raw=self.allocate(bytes(size+32));return raw,C.c_ulonglong(raw.value+16)
            def api(self,*args):pass
            def launch(self,kernel,args,blocks,threads):self.launches.append((kernel,args,blocks,threads))
            def checked_download(self,pointer,size):return bytes(size)
            def release(self,pointer):self.allocations=[p for p in self.allocations if p is not pointer]
        device=Device();profile=ConstantProfile(3,7,1024,32,64,bytes(16),bytes(32),bytes(32))
        tables=SimpleNamespace(device=device,closed=False,profile=profile,key_a=C.c_ulonglong(0),
                               inputs=lambda:(C.c_ulonglong(0),)*5,check_guards=lambda:None)
        queries=(TileQuery((0,),(0,)),)*67
        result=device.scan_wide(tables,queries,[0]*67,0,19,audit=True)
        self.assertEqual(result.total,0);self.assertEqual(device.allocations,[])
        kernel,args,blocks,threads=device.launches[0]
        self.assertEqual((kernel,blocks,threads),(b'warp_virtual_tile_scan',9,256))
        self.assertEqual((len(args),args[11].value,args[13].value),(20,1,67))
        self.assertIn(67*64+32,device.sizes)
        self.assertEqual(device.last_transcripts,((0,)*16,)*67)
        self.assertEqual(device.unique_cpu_checks,0)


if __name__=='__main__':unittest.main()
