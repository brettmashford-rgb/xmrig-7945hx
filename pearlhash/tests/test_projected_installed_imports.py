"""Actual python -S entry points under split installed-package layout; no CUDA required."""
import json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from tools.install_v084_fix import check_install_imports
ROOT=Path(__file__).resolve().parents[1]

class Installed(unittest.TestCase):
    def test_split_layout_reproduces_old_failure_and_new_entry_points_import(self):
        with tempfile.TemporaryDirectory()as temp:
            base=Path(temp);current=base/'new';previous=base/'old';current.mkdir();previous.mkdir()
            # The older regular reference package wins over a new namespace directory.
            shutil.copytree(ROOT/'reference',previous/'reference',ignore=shutil.ignore_patterns('projection.py','__pycache__'))
            (previous/'tools').symlink_to(ROOT/'tools',target_is_directory=True)
            (previous/'pool').symlink_to(ROOT/'pool',target_is_directory=True)
            manifest=json.loads((ROOT/'releases/pearlhash-dev-v0.0.84.1-files.json').read_text())
            for entry in manifest['files']:
                if entry['path'].endswith('.py'):
                    target=current/entry['path'];target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(ROOT/entry['path'],target)
            (current/'reference').mkdir(exist_ok=True)
            shutil.copyfile(ROOT/'reference/projection.py',current/'reference/projection.py')
            env=dict(os.environ,PYTHONPATH=os.pathsep.join(map(str,(current,previous))),PYTHONNOUSERSITE='1')
            broken=subprocess.run([sys.executable,'-S','-c','import reference.projection'],env=env,cwd=base,capture_output=True,text=True)
            self.assertNotEqual(broken.returncode,0);self.assertIn("No module named 'reference.projection'",broken.stderr)
            check_install_imports(current,env)
            code='import reference,tools.projection_reference as p;from pathlib import Path;assert Path(reference.__file__).parent==Path('+repr(str(previous/'reference'))+');assert Path(p.__file__)==Path('+repr(str(current/'tools/projection_reference.py'))+');assert p.signed8(255)==-1'
            result=subprocess.run([sys.executable,'-S','-c',code],env=env,cwd=base,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
