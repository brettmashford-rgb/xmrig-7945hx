"""Scripted preparation launches for host lifetime tests; no GPU math emulation. ISC."""
from test_job_b_tables import Device as BaseDevice

class Device(BaseDevice):
    def __init__(self):super().__init__();self.fail_projection=None
    def launch(self,name,args,blocks,threads):
        if name in(b'projection_b_coeff',b'projection_b_sums',b'projection_prepare_a'):
            if name==self.fail_projection:raise RuntimeError('injected projection preparation failure')
            self.calls.append(name.decode());return
        super().launch(name,args,blocks,threads)
