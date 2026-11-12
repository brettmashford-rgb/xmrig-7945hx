"""Read-only NVML telemetry, matched by PCI address to the active CUDA device. ISC."""
import ctypes as C
import math
import threading
import time

class TelemetryError(RuntimeError):pass
class Utilization(C.Structure):_fields_=[('gpu',C.c_uint),('memory',C.c_uint)]

class NvmlReader:
    def __init__(self,device):
        self.initialized=False;self.closed=False
        try:
            self.lib=C.CDLL('libnvidia-ml.so.1');self.call('nvmlInit_v2',[]);self.initialized=True
            ordinal=C.c_int();bus=C.create_string_buffer(32)
            device.api('cuCtxGetDevice',[C.POINTER(C.c_int)],C.byref(ordinal))
            device.api('cuDeviceGetPCIBusId',[C.c_void_p,C.c_int,C.c_int],bus,len(bus),ordinal)
            self.pci_bus_id=bus.value.decode('ascii');self.handle=C.c_void_p()
            self.call('nvmlDeviceGetHandleByPciBusId_v2',[C.c_char_p,C.POINTER(C.c_void_p)],bus.value,C.byref(self.handle))
        except (OSError,RuntimeError,AttributeError,UnicodeError)as error:
            self.close();raise TelemetryError(str(error))from error
    def call(self,name,types,*args):
        function=getattr(self.lib,name);function.argtypes=types;function.restype=C.c_int
        result=function(*args)
        if result:raise TelemetryError(name+': NVML error '+str(result))
    def scalar(self,name,*extra,wide=False):
        value=C.c_ulonglong()if wide else C.c_uint()
        try:
            self.call(name,[C.c_void_p]+[C.c_uint]*len(extra)+[C.POINTER(type(value))],self.handle,*extra,C.byref(value))
            return value.value
        except (TelemetryError,AttributeError):return None
    def read(self):
        if self.closed:raise TelemetryError('NVML reader closed')
        power=self.scalar('nvmlDeviceGetPowerUsage')
        if power is None or power<=0:raise TelemetryError('GPU board power reading unavailable')
        utilization=Utilization();gpu=memory=None
        try:
            self.call('nvmlDeviceGetUtilizationRates',[C.c_void_p,C.POINTER(Utilization)],self.handle,C.byref(utilization))
            gpu,memory=utilization.gpu,utilization.memory
        except (TelemetryError,AttributeError):pass
        limit=self.scalar('nvmlDeviceGetEnforcedPowerLimit')
        return dict(power_w=power/1000.,power_limit_w=None if limit is None else limit/1000.,gpu_activity_pct=gpu,
            memory_activity_pct=memory,sm_clock_mhz=self.scalar('nvmlDeviceGetClockInfo',1),
            memory_clock_mhz=self.scalar('nvmlDeviceGetClockInfo',2),temperature_c=self.scalar('nvmlDeviceGetTemperature',0),
            pstate=self.scalar('nvmlDeviceGetPerformanceState'),clock_event_bits=self.scalar('nvmlDeviceGetCurrentClocksThrottleReasons',wide=True))
    def close(self):
        if self.closed:return
        self.closed=True
        if self.initialized:
            self.initialized=False
            try:self.call('nvmlShutdown',[])
            except (TelemetryError,AttributeError):pass


def summarize(samples,tiles,errors=()):
    if type(tiles)is not int or tiles<=0:raise ValueError('positive measured tile count required')
    if len(samples)<2:return dict(available=False,error='insufficient telemetry samples',sampling_errors=list(errors))
    times=[s['monotonic_seconds']for s in samples];duration=times[-1]-times[0]
    if any(not math.isfinite(t)for t in times)or duration<=0 or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('telemetry timestamps not strictly increasing')
    gaps=[b-a for a,b in zip(times,times[1:])];max_gap=max(gaps)
    def integral(field,transform=lambda value:value):
        values=[s.get(field)for s in samples]
        if any(v is None or type(v)not in(int,float)or not math.isfinite(v)for v in values):return None
        return sum((transform(a)+transform(b))*.5*dt for a,b,dt in zip(values,values[1:],gaps))
    energy=integral('power_w');available=duration>=5 and max_gap<=1.0 and energy is not None and energy>0
    result=dict(available=available,error=None if available else 'energy window shorter than 5 seconds, sample gap over 1 second, or invalid power',
        measured_tiles=tiles,seconds=duration,samples=len(samples),max_sample_gap_seconds=max_gap,sampling_errors=list(errors),
        energy_joules=energy if available else None,tiles_per_joule=tiles/energy if available else None,
        average_power_w=energy/duration if energy is not None else None,tiles_per_second=tiles/duration)
    for field in ('gpu_activity_pct','memory_activity_pct','sm_clock_mhz','memory_clock_mhz','temperature_c','power_limit_w'):
        total=integral(field);result['average_'+field]=None if total is None else total/duration
    temps=[s.get('temperature_c')for s in samples];result['maximum_temperature_c']=max(temps)if all(t is not None for t in temps)else None
    result['pstates']=sorted({s['pstate']for s in samples if s.get('pstate')is not None})
    result['clock_limit_time_fraction']={label:(None if (v:=integral('clock_event_bits',lambda bits:float(bool(int(bits)&mask))))is None else v/duration)
        for label,mask in (('software_power_cap',4),('hardware_slowdown',8),('software_thermal_slowdown',32),('hardware_thermal_slowdown',64),('hardware_power_brake',128))}
    return result


class PowerSampler:
    def __init__(self,reader,interval=.2):
        self.reader=reader;self.interval=interval;self.samples=[];self.errors=[];self.stop_event=threading.Event();self.thread=None
    def sample(self):
        before=time.perf_counter();row=self.reader.read();after=time.perf_counter()
        row=dict(row,monotonic_seconds=(before+after)*.5,wall_time_seconds=time.time(),read_seconds=after-before)
        self.samples.append(row)
    def loop(self):
        while not self.stop_event.wait(self.interval):
            try:self.sample()
            except (TelemetryError,OSError)as error:self.errors.append(str(error))
    def start(self):
        self.sample();self.thread=threading.Thread(target=self.loop,name='gpu-power',daemon=True);self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread is not None:self.thread.join()
        self.sample()
    def measure(self,work,tiles):
        self.start()
        try:work()
        except BaseException:
            try:self.stop()
            except (TelemetryError,OSError):pass
            raise
        else:self.stop()
        result=summarize(self.samples,tiles,self.errors);result['raw_samples']=self.samples
        return result
