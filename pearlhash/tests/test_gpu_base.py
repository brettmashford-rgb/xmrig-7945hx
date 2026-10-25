"""Temporary GPU commitment context ownership and current-job gates. ISC."""
import unittest
from unittest.mock import patch
from tools.gpu_base import prepare_gpu_base
from tools.check_prepared_job import synthetic_session
from pool.search import StaleWork


class BaseTests(unittest.TestCase):
    def test_new_base_and_cleanup_before_return(self):
        session,job,message=synthetic_session(bytes(32));events=[];opening=object()
        class Device:
            def start(self,module):events.append(('start',module))
            def opening(self,key,fill,total,rows,width,*,current):
                current();events.append((fill,total,rows,width));return opening
            def close(self):events.append('close')
        with patch('tools.gpu_base.ConstantMerkleGpu',Device):base=prepare_gpu_base(job,session.is_current,'module')
        self.assertIs(base.opening,opening)
        self.assertEqual((base.job_key,base.n,base.k),(job.job_key,192,32768))
        self.assertEqual(events,[('start','module'),(64,6144,[0],32768),'close'])
        session.close()

    def test_replacement_cannot_return_base_and_still_closes_context(self):
        session,job,message=synthetic_session(bytes(32));events=[]
        class Device:
            def start(self,module):pass
            def opening(self,*args,**kwargs):session.consume(message);kwargs['current']()
            def close(self):events.append('closed')
        with patch('tools.gpu_base.ConstantMerkleGpu',Device):
            with self.assertRaises(StaleWork):prepare_gpu_base(job,session.is_current,'module')
        self.assertEqual(events,['closed']);session.close()

    def test_stale_job_does_not_create_gpu_context(self):
        session,job,message=synthetic_session(bytes(32));session.close()
        with patch('tools.gpu_base.ConstantMerkleGpu')as device:
            with self.assertRaises(StaleWork):prepare_gpu_base(job,session.is_current,'module')
            device.assert_not_called()


if __name__=='__main__':unittest.main()
