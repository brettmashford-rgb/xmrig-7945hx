import importlib.util
from pathlib import Path
import shlex
import unittest
from unittest.mock import patch
import tempfile, hashlib, io, subprocess, types
from contextlib import ExitStack
spec=importlib.util.spec_from_file_location('switch_pool',Path(__file__).with_name('switch-pool.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
WALLET='4'+'1'*94
class PoolSwitchTests(unittest.TestCase):
 def startup(self,binary='/root/xmrig-miner',extra=''):
  return '#!/bin/sh\ncp /media/usb/xmrig-miner /root/xmrig-miner\nchmod +x /root/xmrig-miner\ntmux new-session -d -s xmrig "'+binary+' -o old.example:9200 -a rx/0 -u OLDADDRESS.5900x-2 -p x --nicehash '+extra+'"\n'
 def test_keep_cpu_settings_and_worker(self):
  original=self.startup(extra='--threads=24 --cpu-affinity 0xffff --asm=ryzen')
  _,_,inner,_=m.parse_start(original);kept,worker=m.pool_args(inner);self.assertEqual(worker,'5900x-2')
  new,session=m.rewrite(original,WALLET,worker);self.assertEqual(session,'xmrig')
  _,_,args,_=m.parse_start(new)
  self.assertNotIn('--nicehash',args)
  for arg in ['--threads=24','--cpu-affinity','0xffff','--asm=ryzen','--tls',WALLET,worker,m.POOL]:self.assertIn(arg,args)
  self.assertEqual(new.splitlines()[:3],original.splitlines()[:3]);self.assertEqual(args[0],'/root/xmrig-miner')
 def test_alternate_binary(self):
  new,_=m.rewrite(self.startup(binary='/root/xmrig'),WALLET,'3900x')
  self.assertEqual(m.parse_start(new)[2][0],'/root/xmrig')
 def test_equal_options(self):
  inner=shlex.split('/root/xmrig --url=old:443 --user=OLD.7900 --pass=old --nicehash --tls --tls-fingerprint=OLD --coin=monero --threads=32')
  kept,worker=m.pool_args(inner);self.assertEqual(worker,'7900');self.assertEqual(kept,['/root/xmrig','--threads=32'])
 def test_repeat_rewrite(self):
  a,_=m.rewrite(self.startup(),WALLET,'5900x-2');b,_=m.rewrite(a,WALLET,'5900x-2');self.assertEqual(a,b)
 def test_ambiguous_refused(self):
  with self.assertRaises(ValueError):m.parse_start(self.startup()+self.startup())
 def test_command_chain_refused(self):
  with self.assertRaises(ValueError):m.parse_start(self.startup(extra='&& echo bad'))
 def test_missing_value_refused(self):
  with self.assertRaises(ValueError):m.pool_args(['/root/xmrig','-u'])
 def test_safe_worker_names(self):
  for name in ['3900x','5900x-2','7945hx']:self.assertTrue(m.valid_worker(name))
  for name in ['','bad name','x;reboot']:self.assertFalse(m.valid_worker(name))
 def test_supportxmr_worker_preserved(self):
  _, worker=m.pool_args(['/root/xmrig','-o',m.POOL,'-u',WALLET,'-p','7900','--tls'])
  self.assertEqual(worker,'7900')
 def test_download_bad_hash_preserves_binary(self):
  with tempfile.TemporaryDirectory() as d:
   dest=Path(d)/'xmrig';dest.write_bytes(b'OLD')
   with patch.object(m.urllib.request,'urlopen',return_value=io.BytesIO(b'NEW')):
    with self.assertRaises(ValueError):m.stage_miner('http://example/miner','0'*64,dest)
   self.assertEqual(dest.read_bytes(),b'OLD');self.assertEqual(list(Path(d).iterdir()),[dest])
 def test_download_version_before_install(self):
  blob=b'#!/bin/sh\necho XMRig-test\n'
  with tempfile.TemporaryDirectory() as d:
   dest=Path(d)/'xmrig';dest.write_bytes(b'OLD')
   with patch.object(m.urllib.request,'urlopen',return_value=io.BytesIO(blob)):
    staged=m.stage_miner('http://example/miner',hashlib.sha256(blob).hexdigest(),dest)
   self.assertEqual(dest.read_bytes(),b'OLD');self.assertEqual(staged.read_bytes(),blob)
 def test_upgrade_transaction_and_rollback(self):
  for fail_commit in [False,True]:
   with self.subTest(fail_commit=fail_commit), tempfile.TemporaryDirectory() as d, ExitStack() as stack:
    root=Path(d);usb=root/'usb';etc=root/'etc';usb.mkdir();etc.mkdir()
    original=self.startup();start=etc/'xmrig.start';start.write_text(original);start.chmod(0o755)
    binary=usb/'xmrig-miner';binary.write_bytes(b'OLD');staged=usb/'staged';staged.write_bytes(b'NEW');staged.chmod(0o755)
    def path_map(value):
     text=str(value)
     if text=='/etc/local.d':return etc
     if text.startswith('/media/usb'):return usb/text[len('/media/usb'):].lstrip('/')
     return Path(value)
    calls=[];commits=[]
    def run(argv,**kwargs):
     calls.append(argv)
     if argv[:2]==['tmux','has-session']:return subprocess.CompletedProcess(argv,1)
     if argv==['lbu','commit']:
      commits.append(argv)
      if fail_commit and len(commits)==1:raise subprocess.CalledProcessError(1,argv)
     return subprocess.CompletedProcess(argv,0)
    stack.enter_context(patch.object(m,'Path',side_effect=path_map))
    stack.enter_context(patch.object(m.sys,'argv',['switch-pool.py','--wallet',WALLET,'--miner-url','http://example/miner','--miner-sha256','0'*64]))
    stack.enter_context(patch.object(m.os,'geteuid',return_value=0))
    stack.enter_context(patch.object(m.os.path,'ismount',return_value=True))
    stack.enter_context(patch.object(m.os,'statvfs',return_value=types.SimpleNamespace(f_flag=0)))
    stack.enter_context(patch.object(m.os,'sync'))
    stack.enter_context(patch.object(m.shutil,'which',return_value='/bin/sh'))
    stack.enter_context(patch.object(m,'stage_miner',return_value=staged))
    stack.enter_context(patch.object(m,'miners_running',return_value=[]))
    stack.enter_context(patch.object(m,'stop_direct_miner',return_value=False))
    stack.enter_context(patch.object(m.subprocess,'run',side_effect=run))
    stack.enter_context(patch.object(m.time,'sleep'))
    if fail_commit:
     with self.assertRaises(subprocess.CalledProcessError):m.main()
     self.assertEqual(binary.read_bytes(),b'OLD');self.assertEqual(start.read_text(),original)
    else:
     m.main();self.assertEqual(binary.read_bytes(),b'NEW');self.assertIn(m.POOL,start.read_text())
    self.assertTrue(any(x.name.startswith('xmrig-miner.before-upgrade-') for x in usb.iterdir()))
 def test_background_startup(self):
  original='#!/bin/sh\ncp /media/usb/xmrig-miner /root/xmrig-miner\nchmod +x /root/xmrig-miner\n/root/xmrig-miner -o old:9200 -a rx/0 -u OLD.3900x -p x --nicehash --threads=24 > /var/log/xmrig.log 2>&1 &\n'
  new,session=m.rewrite(original,WALLET,'3900x')
  self.assertEqual(session,'xmrig');self.assertEqual(new.splitlines()[:3],original.splitlines()[:3])
  _,outer,inner,_=m.parse_start(new);self.assertEqual(outer[:2],['tmux','new-session']);self.assertIn('--threads=24',inner);self.assertNotIn('--nicehash',inner);self.assertNotIn('>',new)
 def test_unsafe_background_refused(self):
  with self.assertRaises(ValueError):m.parse_start('/root/xmrig -u OLD & reboot\n')
 def test_terminal_input_uses_tty(self):
  from unittest.mock import mock_open
  with patch('builtins.open',mock_open(read_data='5900x-2\n')) as opened:
   self.assertEqual(m.terminal_input('Worker: '),'5900x-2')
   opened.assert_called_once_with('/dev/tty','r+')
 def test_background_log_redirect_variants(self):
  for suffix in [' > /var/log/xmrig.log 2>&1 &', ' >> /var/log/xmrig.log 2>&1 &', '>/var/log/xmrig.log 2>&1&', ' 1>>/var/log/xmrig.log 2 >& 1 &', ' 2>/var/log/miner.err &', ' &']:
   with self.subTest(suffix=suffix):
    line='/root/xmrig-miner -o old:9200 -u OLD.3900x -p x --nicehash'+suffix+'\n'
    new,_=m.rewrite(line,WALLET,'3900x')
    _,_,inner,_=m.parse_start(new)
    self.assertEqual(inner[0],'/root/xmrig-miner');self.assertIn(m.POOL,inner);self.assertNotIn('>',new)
 def test_dangerous_redirect_refused(self):
  for suffix in [' > /etc/passwd &',' | sh',' ; reboot',' > /var/log/a 2>&3 &']:
   with self.subTest(suffix=suffix), self.assertRaises(ValueError):m.parse_start('/root/xmrig-miner -u OLD'+suffix)
if __name__=='__main__':unittest.main()
