"""Selected offline winner flows into bounded live mining only after validation. ISC."""
from contextlib import redirect_stdout
import io,json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import install_v077 as install
class Gate(unittest.TestCase):
    def exercise(self,selected='wide16k',gain=1.,bad=None):
        with tempfile.TemporaryDirectory()as temp:
            folder=Path(temp);home=folder/'home';login=home/'pearlhash-dev/captures/independent-login-test.json'
            login.parent.mkdir(parents=True)
            login.write_text(json.dumps(dict(schema='pearlhash-login-probe-1',error=None,records=[dict(direction='out',json=dict(method='login',params=['fake-wallet','worker','agent']))])))
            report=dict(comparison=dict(preferred=selected,speedup_over_wide16k={selected:gain}))
            def run(args,**kwargs):
                self.assertEqual(args[args.index('--register-mode')+1],selected)
                self.assertEqual(args[args.index('--seconds')+1],'300')
                self.assertIn('--cache-a',args);self.assertIn('--commitment-module',args)
                self.assertEqual(args[args.index('--login-file')+1],str(login))
                live=dict(complete=True,error=None,scan_backend='register-16k-one-stream-v077',scan_mode=selected,
                    worker=dict(joined=True),job_b_lifecycle=[dict(closed=True)],geometry_lifecycle=[dict(closed=True)],
                    work=dict(tiles=16384),submitted_shares=0,pool_accepted_shares=0,connection={})
                if bad=='process':return SimpleNamespace(returncode=1)
                if bad=='mode':live['scan_mode']='wrong'
                if bad=='worker':live['worker']['joined']=False
                if bad=='owner':live['geometry_lifecycle'][0]['closed']=False
                if bad=='missing-owner':live['geometry_lifecycle']=[]
                (folder/'mining-result.json').write_text(json.dumps(live))
                return SimpleNamespace(returncode=0)
            with patch.object(install.subprocess,'run',side_effect=run)as call,redirect_stdout(io.StringIO()):
                if bad or selected=='unknown' or(selected!='wide16k'and gain<=1/.97):
                    with self.assertRaises(ValueError):install.run_live(folder,home,Path('module'),Path('commitment'),{},report)
                else:install.run_live(folder,home,Path('module'),Path('commitment'),{},report)
                if selected=='unknown'or(selected!='wide16k'and gain<=1/.97):call.assert_not_called()
                else:call.assert_called_once()
    def test_live_control_is_valid_when_no_candidate_promoted(self):self.exercise()
    def test_each_promoted_candidate_selected_without_reverting_to_old_scanner(self):
        for mode in ('wide16k-resident3','wide16k-resident4'):self.exercise(mode,1.1)
    def test_under_threshold_and_unknown_candidates_never_connect(self):
        self.exercise('wide16k-resident3',1.01);self.exercise('unknown',1.1)
    def test_bad_live_completion_fails(self):
        for bad in ('process','mode','worker','owner','missing-owner'):self.exercise(bad=bad)
    def test_missing_saved_login_never_connects(self):
        with tempfile.TemporaryDirectory()as temp,patch.object(install.subprocess,'run')as run:
            with self.assertRaises(ValueError):install.run_live(Path(temp),Path(temp),Path('m'),Path('c'),{},dict(comparison=dict(preferred='wide16k')))
            run.assert_not_called()
if __name__=='__main__':unittest.main()
