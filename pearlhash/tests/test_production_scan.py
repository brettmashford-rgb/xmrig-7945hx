"""Production-profile dispatch selection and strict unsupported-input rejection. ISC."""
from types import SimpleNamespace
import unittest

from tools.check_tile_scan_gpu import TileQuery
from tools.production_scan import ProductionCandidateScanner,require_production


class ProductionScanTests(unittest.TestCase):
    def test_only_exact_supported_shape_and_arithmetic_profile_is_selected(self):
        profile=SimpleNamespace(k=32768,rank=128,fill=64)
        good=TileQuery(tuple(range(10)),tuple(range(16)))
        require_production(profile,(good,))
        for changed in(SimpleNamespace(k=16384,rank=128,fill=64),
                       SimpleNamespace(k=32768,rank=32,fill=64),
                       SimpleNamespace(k=32768,rank=128,fill=-64)):
            with self.assertRaises(ValueError):require_production(changed,(good,))
        for q in(TileQuery(tuple(range(9)),tuple(range(16))),TileQuery(tuple(range(10)),tuple(range(15)))):
            with self.assertRaises(ValueError):require_production(profile,(q,))

    def test_kernel_comparison_modes_and_partial_grid(self):
        device=object.__new__(ProductionCandidateScanner)
        device.production_enabled=True;device.warp_enabled=True
        self.assertEqual(device.kernel_launch(67),(b'production_virtual_tile_scan',9))
        self.assertEqual(device.kernel_launch(4096),(b'production_virtual_tile_scan',512))
        device.production_enabled=False
        self.assertEqual(device.kernel_launch(67),(b'warp_virtual_tile_scan',9))
        device.warp_enabled=False
        self.assertEqual(device.kernel_launch(67),(b'virtual_tile_scan',67))

    def test_bad_profile_rejects_before_attempting_gpu_operations(self):
        device=object.__new__(ProductionCandidateScanner);device.production_enabled=True
        tables=SimpleNamespace(profile=SimpleNamespace(k=1024,rank=32,fill=64))
        q=TileQuery(tuple(range(10)),tuple(range(16)))
        with self.assertRaises(ValueError):device.scan_wide(tables,(q,),[0],0,0)


if __name__=='__main__':unittest.main()
