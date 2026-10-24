"""Small CUDA Driver API lifecycle helper for offline checks. ISC license."""
import ctypes as C


class CudaDevice:
    def __init__(self):
        self.lib = C.CDLL('libcuda.so.1')
        self.context = C.c_void_p()
        self.module = C.c_void_p()
        self.allocations = []

    def api(self, name, types, *args):
        function = getattr(self.lib, name)
        function.argtypes = types
        function.restype = C.c_int
        result = function(*args)
        if result:
            raise RuntimeError(f'{name}: CUDA error {result}')

    def start(self, cubin):
        self.api('cuInit', [C.c_uint], 0)
        device = C.c_int()
        self.api('cuDeviceGet', [C.POINTER(C.c_int), C.c_int], C.byref(device), 0)
        attributes = []
        for attribute in (75, 76):
            value = C.c_int()
            self.api('cuDeviceGetAttribute', [C.POINTER(C.c_int), C.c_int, C.c_int],
                     C.byref(value), attribute, device)
            attributes.append(value.value)
        if attributes != [12, 0]:
            raise RuntimeError('this test requires sm_120')
        self.api('cuCtxCreate_v2', [C.POINTER(C.c_void_p), C.c_uint, C.c_int],
                 C.byref(self.context), 0, device)
        self.api('cuModuleLoad', [C.POINTER(C.c_void_p), C.c_char_p],
                 C.byref(self.module), str(cubin.resolve()).encode())
        print('GPU 0: sm_120', flush=True)

    def allocate(self, data):
        pointer = C.c_ulonglong()
        self.api('cuMemAlloc_v2', [C.POINTER(C.c_ulonglong), C.c_size_t],
                 C.byref(pointer), len(data))
        self.allocations.append(pointer)
        buffer = C.create_string_buffer(data, len(data))
        self.api('cuMemcpyHtoD_v2', [C.c_ulonglong, C.c_void_p, C.c_size_t],
                 pointer, buffer, len(data))
        return pointer

    def release(self, pointer):
        if not any(pointer is owned for owned in self.allocations):
            raise ValueError('allocation does not belong to this context')
        self.api('cuMemFree_v2', [C.c_ulonglong], pointer)
        self.allocations = [owned for owned in self.allocations if owned is not pointer]

    def close(self):
        # Always release only this test's own allocations/context.
        for pointer in self.allocations:
            self.lib.cuMemFree_v2(pointer)
        if self.module.value:
            self.lib.cuModuleUnload(self.module)
        if self.context.value:
            self.lib.cuCtxDestroy_v2(self.context)

