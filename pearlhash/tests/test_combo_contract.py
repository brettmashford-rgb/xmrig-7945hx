"""Compiled v075 ABI, exact arithmetic source preservation and actual parser. ISC."""
from pathlib import Path
import unittest
from tools.check_combo import argument_parser
from tools.combo_scan import MODES
ROOT=Path(__file__).resolve().parents[1]
class Contract(unittest.TestCase):
    def test_installer_modes_parse(self):
        for mode in MODES:
            args=argument_parser().parse_args(['--module','m','--commitment-module','c','--oracle','o','--output-dir','d','--mode',mode]);self.assertEqual(args.mode,mode)
    def test_scheduling_only_changes_unroll_directive(self):
        reference=(ROOT/'gpu/experiments_scan.cu').read_text().split('template<unsigned Steps>',1)[1].split('extern "C" __global__ void small4_scan',1)[0]
        candidate=(ROOT/'gpu/combo_scan.cu').read_text().split('template<unsigned Steps,unsigned Unroll>',1)[1].split('extern "C" __global__ void small4_schedule4_scan',1)[0]
        self.assertEqual(candidate.replace('combo_schedule_body','small_body').replace('#pragma unroll Unroll','#pragma unroll 1'),reference)
    def test_PTX_ABI_MMA_and_extended_snapshot(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.75-scan-sm120.ptx').read_text()
        for name,mma in [('cta_b8_scan',6),('small4_scan',6),('small4_schedule4_scan',24)]:
            body=raw.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0]
            self.assertEqual(body.split(')')[0].count('.param '),24);self.assertEqual(body.count('mma.sync'),mma)
        body=raw.split('.visible .entry resident_guard_snapshot(',1)[1].split('.visible .entry ',1)[0]
        self.assertRegex(body,r'\b16384\b|\b16385\b|\b16383\b')
if __name__=='__main__':unittest.main()
