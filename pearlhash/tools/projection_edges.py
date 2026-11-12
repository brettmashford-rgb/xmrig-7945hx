"""GPU preparation edge cases: coefficient +128, sparse high bytes and nonce tail. ISC."""
import ctypes as C
import struct
from tools.projected_scan import guarded,check_buffer
from tools.virtual_scan import VirtualTables
from reference.projection import project,signed8


def check_edges(device):
    class Scratch:
        read=VirtualTables.read
        def __init__(self):self.device=device;self.owned=[];self.buffers=[]
        def buffer(self,size):
            b=guarded(self,size);self.buffers.append(b);return b
        def upload(self,pointer,data):
            raw=C.create_string_buffer(data,len(data));device.api('cuMemcpyHtoD_v2',[C.c_ulonglong,C.c_void_p,C.c_size_t],pointer,raw,len(data))
    s=Scratch()
    try:
        ub=s.buffer(16*128);pb=s.buffer(32768*4);coeff=s.buffer(256*128);special=s.buffer(256*2);bsum=s.buffer(16*256*2)
        uniforms=[[((r*17+k*7)%64)-32 for k in range(128)]for r in range(16)]
        s.upload(ub[1],bytes(v&255 for row in uniforms for v in row));s.upload(pb[1],struct.pack('<I',1<<16)*32768)
        device.launch(b'projection_b_coeff',(pb[1],coeff[1],special[1]),256,128)
        device.launch(b'projection_b_sums',(ub[1],coeff[1],special[1],bsum[1],C.c_uint(16)),8,128)
        device.api('cuCtxSynchronize',[])
        expected=bytes([128,128]+[0]*126)*256
        if s.read(coeff[1],0,coeff[2])!=expected or s.read(special[1],0,special[2])!=bytes(512):raise RuntimeError('B +128 coefficient correction differs')
        actual=struct.unpack('<4096h',s.read(bsum[1],0,bsum[2]))
        if actual!=tuple(128*(row[0]-row[1])for row in uniforms for q in range(256)):raise RuntimeError('B edge sums differ')
        a=s.buffer(32768);low=s.buffer(32768);asum=s.buffer(512);counts=s.buffer(1024);records=s.buffer(256*128*2)
        signal=bytes([64])*(32768-16)+bytes([129])*16;s.upload(a[1],signal)
        device.launch(b'projection_prepare_a',(a[1],pb[1],low[1],asum[1],counts[1],records[1],C.c_uint(1)),256,128)
        device.api('cuCtxSynchronize',[])
        expected_projection=project([64]*112+[-127]*16,[(0,1)]*128)
        expected_low=bytes(255*128)+bytes(v&255 for v in expected_projection[0])
        if s.read(low[1],0,low[2])!=expected_low:raise RuntimeError('A edge low bytes differ')
        if struct.unpack('<256h',s.read(asum[1],0,512))!=(0,)*255+(expected_projection[2],):raise RuntimeError('A edge residual sum differs')
        if struct.unpack('<256I',s.read(counts[1],0,1024))!=(0,)*255+(2,):raise RuntimeError('A edge exception counts differ')
        raw=struct.unpack('<2H',s.read(records[1],255*128*2,4))
        decoded={(v&127,signed8(v>>8))for v in raw}
        if decoded!=set(expected_projection[1]):raise RuntimeError('A edge sparse signed corrections differ')
        for buffer in s.buffers:check_buffer(s,buffer)
        return dict(preparation_edges_checked=True,b_positive128_checked=True,tail_high_corrections_checked=True)
    finally:
        device.api('cuCtxSynchronize',[])
        for pointer in reversed(s.owned):device.release(pointer)
