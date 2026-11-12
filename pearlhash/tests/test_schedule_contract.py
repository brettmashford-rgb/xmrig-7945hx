"""v076 compiled ABI and preservation of the winning arithmetic and traversal. ISC."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from tools.check_schedule import argument_parser
from tools.schedule_scan import MODES,THREADS,ENTRIES,canonical,inverse,DISPATCHES
from tools.combo_scan import canonical as baseline
ROOT=Path(__file__).resolve().parents[1]
class Contract(unittest.TestCase):
    def test_actual_installer_modes_parse(self):
        for mode in MODES:
            args=argument_parser().parse_args(['--module','m','--commitment-module','c','--oracle','o','--output-dir','d','--mode',mode])
            self.assertEqual(args.mode,mode);self.assertEqual(THREADS[mode],256)
            self.assertEqual(DISPATCHES[mode].kernel_entry,ENTRIES[mode])
    def test_scheduling_changes_only_consumer_unroll(self):
        reference=(ROOT/'gpu/cta_b_scan.cu').read_text().split('template<unsigned Steps>',1)[1].split('extern "C" __global__ void cta_b8_scan',1)[0]
        candidate=(ROOT/'gpu/schedule_scan.cu').read_text().split('template<unsigned Steps,unsigned Unroll>',1)[1].split('extern "C" __global__ void wide_schedule4_scan',1)[0]
        self.assertEqual(candidate.replace('wide_schedule_body','cta_b_body').replace('#pragma unroll Unroll','#pragma unroll 1'),reference)
    def test_unaligned_and_partial_groups_preserve_baseline_mapping(self):
        for rows in (4,8,16,32,64,512):
            plan=SimpleNamespace(rows=range(rows),cols=range(7),count=rows*7)
            for mode in MODES:
                for ordinal in range(plan.count):
                    tile=canonical(plan,mode,ordinal)
                    self.assertEqual(tile,baseline(plan,'wide16k',ordinal))
                    self.assertEqual(inverse(plan,mode,tile),ordinal)
    def test_compiled_ABI_MMA_and_snapshot(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.76-scan-sm120.ptx').read_text()
        old=(ROOT/'releases/pearlhash-dev-v0.0.75-scan-sm120.ptx').read_text()
        def entry(ptx,name):return ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].split('\n\t// .globl',1)[0]
        for name,mma in [('cta_b8_scan',6),('wide_schedule4_scan',24),('wide_schedule8_scan',48)]:
            body=entry(raw,name)
            self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertEqual(body.count('mma.sync'),mma)
            self.assertGreaterEqual(body.count('bar.sync'),3)
        # Registers/labels are generated identically for the unchanged control entry.
        self.assertEqual(entry(raw,'cta_b8_scan'),entry(old,'cta_b8_scan'))
        self.assertEqual(entry(raw,'resident_guard_snapshot'),entry(old,'resident_guard_snapshot'))
if __name__=='__main__':unittest.main()
