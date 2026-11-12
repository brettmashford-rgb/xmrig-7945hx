"""Reject misleading counter exports; exercise installed split-package imports. ISC."""
import csv,io,json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from tools.ncu_profile import parse_csv,compact,bounded
from tools.install_v085 import check_install_imports
ROOT=Path(__file__).resolve().parents[1]

class Counters(unittest.TestCase):
    def raw(self,*,kernel='a_pair_direct_scan',count=3,missing=False,duplicate=False):
        out=io.StringIO();writer=csv.writer(out)
        out.write('==PROF== disconnected\n')
        writer.writerow(['ID','Kernel Name','Metric Name','Metric Unit','Metric Value'])
        for i in range(count):
            for name in ('gpu__time_duration.sum','sm__throughput.avg.pct_of_peak_sustained_elapsed',
                         'dram__throughput.avg.pct_of_peak_sustained_elapsed'):
                if missing and i==2 and name.startswith('dram'):continue
                writer.writerow([i,kernel,name,'cycle' if name.startswith('gpu') else '%','1,234' if name.startswith('gpu') else str(10+i)])
            writer.writerow([i,kernel,'smsp__warp_issue_stalled_barrier_per_warp_active.pct','%',20+i])
            writer.writerow([i,kernel,'smsp__warp_issue_stalled_wait_per_warp_active.pct','%',5+i])
            writer.writerow([i,kernel,'unsupported.metric','%','n/a'])
        if duplicate:writer.writerow([0,kernel,'gpu__time_duration.sum','cycle','1234'])
        return out.getvalue()
    def test_counter_units_values_replicates_and_stall_order(self):
        metrics=parse_csv(self.raw())
        self.assertEqual(metrics['gpu__time_duration.sum']['mean'],1234)
        self.assertEqual(metrics['sm__throughput.avg.pct_of_peak_sustained_elapsed']['mean'],11)
        result=compact(metrics);self.assertEqual(result['top_warp_stalls'][0]['value'],21)
        self.assertEqual(result['counters']['dram__throughput.avg.pct_of_peak_sustained_elapsed']['unit'],'%')
        self.assertNotIn('unsupported.metric',metrics)
    def test_incomplete_wrong_kernel_duplicate_and_empty_exports_rejected(self):
        for raw in (self.raw(kernel='other_kernel'),self.raw(count=2),self.raw(missing=True),self.raw(duplicate=True),''):
            with self.subTest(raw=raw[:50]),self.assertRaises(ValueError):parse_csv(raw)
    def test_profiler_failure_and_timeout_cannot_be_success(self):
        code,out=bounded([sys.executable,'-c','raise SystemExit(7)'],timeout=2)
        self.assertEqual(code,7)
        with self.assertRaisesRegex(RuntimeError,'timed out'):
            bounded([sys.executable,'-c','import time;time.sleep(10)'],timeout=.1)
    def test_installed_entrypoint_with_old_regular_reference_package(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);current=base/'new';old=base/'old';current.mkdir();old.mkdir()
            for name in ('reference','pool'):
                (old/name).symlink_to(ROOT/name,target_is_directory=True)
            (old/'tools').symlink_to(ROOT/'tools',target_is_directory=True)
            for name in ('profile_pair.py','ncu_profile.py'):
                target=current/'tools'/name;target.parent.mkdir(exist_ok=True)
                shutil.copyfile(ROOT/'tools'/name,target)
            env=dict(os.environ,PYTHONPATH=os.pathsep.join(map(str,(current,old))))
            check_install_imports(current,env)
            result=subprocess.run([sys.executable,'-S','-c',
                'from tools.ncu_profile import SIZE;assert SIZE==322492696'],env=env,cwd=base,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
