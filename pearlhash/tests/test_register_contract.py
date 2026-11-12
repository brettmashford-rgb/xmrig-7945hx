"""v077 compiled ABI and preservation of the winning arithmetic and traversal. ISC."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from tools.check_register import argument_parser
from tools.register_scan import MODES,THREADS,ENTRIES,canonical,inverse,DISPATCHES
from tools.combo_scan import canonical as baseline
ROOT=Path(__file__).resolve().parents[1]
class Contract(unittest.TestCase):
    def test_actual_installer_modes_parse(self):
        for mode in MODES:
            args=argument_parser().parse_args(['--module','m','--commitment-module','c','--oracle','o','--output-dir','d','--mode',mode])
            self.assertEqual(args.mode,mode);self.assertEqual(THREADS[mode],256)
            self.assertEqual(DISPATCHES[mode].kernel_entry,ENTRIES[mode])
    def test_candidates_call_unchanged_control_body_with_only_launch_bounds(self):
        source=(ROOT/'gpu/register_scan.cu').read_text()
        for blocks in (3,4):
            self.assertIn(f'__launch_bounds__(256,{blocks}) void wide_resident{blocks}_scan',source)
        self.assertIn('register_body<8,3>(',source)
        self.assertIn('register_body<8,4>(',source)
        reference=(ROOT/'gpu/cta_b_scan.cu').read_text().split('template<unsigned Steps>',1)[1].split('extern \"C\" __global__ void cta_b8_scan',1)[0]
        candidate=source.split('template<unsigned Steps,unsigned Residency>',1)[1].split('extern \"C\" __global__ __launch_bounds__',1)[0]
        self.assertEqual(candidate.replace('register_body','cta_b_body'),reference)
        self.assertIn('#include "experiments_scan.cu"',source)
    def test_unaligned_and_partial_groups_preserve_baseline_mapping(self):
        for rows in (4,8,16,32,64,512):
            plan=SimpleNamespace(rows=range(rows),cols=range(7),count=rows*7)
            for mode in MODES:
                for ordinal in range(plan.count):
                    tile=canonical(plan,mode,ordinal)
                    self.assertEqual(tile,baseline(plan,'wide16k',ordinal))
                    self.assertEqual(inverse(plan,mode,tile),ordinal)
    def test_compiled_ABI_MMA_and_snapshot(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.77-scan-sm120.ptx').read_text()
        old=(ROOT/'releases/pearlhash-dev-v0.0.75-scan-sm120.ptx').read_text()
        def entry(ptx,name):return ptx.split('.visible .entry '+name+'(',1)[1].split('.visible .entry ',1)[0].split('\n\t// .globl',1)[0]
        for name,mma in [('cta_b8_scan',6),('wide_resident3_scan',6),('wide_resident4_scan',6)]:
            body=entry(raw,name)
            self.assertEqual(body.split(')')[0].count('.param '),24)
            self.assertEqual(body.count('mma.sync'),mma)
            self.assertGreaterEqual(body.count('bar.sync'),3)
        for blocks in (3,4):
            body=entry(raw,f'wide_resident{blocks}_scan')
            self.assertIn('.maxntid 256, 1, 1',body)
            self.assertIn(f'.minnctapersm {blocks}',body)
        # Registers/labels are generated identically for the unchanged control entry.
        self.assertEqual(entry(raw,'cta_b8_scan'),entry(old,'cta_b8_scan'))
        self.assertEqual(entry(raw,'resident_guard_snapshot'),entry(old,'resident_guard_snapshot'))
if __name__=='__main__':unittest.main()
