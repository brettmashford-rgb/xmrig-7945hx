import importlib.util
from pathlib import Path
import shlex
import unittest
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
if __name__=='__main__':unittest.main()
