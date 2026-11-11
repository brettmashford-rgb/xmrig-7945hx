"""Rig-reported v073 CLI exclusion and real collector limit regressions. ISC."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.check_experiments import argument_parser
from tools.experiments_scan import MODES
ROOT=Path(__file__).resolve().parents[1]

class Regressions(unittest.TestCase):
    def test_every_installer_mode_is_accepted_by_actual_parser(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                args=argument_parser().parse_args(['--module','m','--commitment-module','c','--oracle','o','--output-dir','d','--mode',mode])
                self.assertEqual(args.mode,mode)
    def test_real_collector_gate_accepts_large_windows_and_rejects_invalid_limits(self):
        source=(ROOT/'gpu/experiments_scan.cu').read_text()
        body=source.rsplit('extern "C" __global__ void resident_guard_snapshot(',1)[1]
        self.assertIn('if(!experiment_snapshot_valid(blockDim.x,guards,count))return;',body)
        self.assertIn('pearl_snapshot_byte(addresses,status,generation,first,count,i)',body)
        with tempfile.TemporaryDirectory()as folder:
            code=Path(folder)/'gate.cpp';binary=Path(folder)/'gate'
            code.write_text('''#include "experiment_axes.h"
#include <cassert>
int main(){
 for(unsigned guards: {28U,30U,64U})
  for(unsigned count: {1U,4096U,4097U,16384U})assert(experiment_snapshot_valid(128,guards,count));
 assert(!experiment_snapshot_valid(128,28,0));
 assert(!experiment_snapshot_valid(128,28,16385));
 assert(!experiment_snapshot_valid(128,0,16384));
 assert(!experiment_snapshot_valid(128,65,16384));
 assert(!experiment_snapshot_valid(256,28,16384));
}'''.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>'))
            subprocess.run(['g++','-std=c++17','-fsanitize=undefined','-I'+str(ROOT/'gpu'),str(code),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)
    def test_compiled_collector_exposes_same_ABI_and_new_limit(self):
        raw=(ROOT/'releases/pearlhash-dev-v0.0.74-scan-sm120.ptx').read_text()
        body=raw.split('.visible .entry resident_guard_snapshot(',1)[1].split('.visible .entry ',1)[0]
        self.assertEqual(body.split(')')[0].count('.param '),7)
        self.assertRegex(body,r'\b16384\b|\b16385\b|\b16383\b')
        self.assertIn('.visible .entry resident_guard_snapshot_legacy4096(',raw)

if __name__=='__main__':unittest.main()
