"""Price complete dense payload transfers on CPU and on the RTX, outside ggml."""

import ctypes as ct
import hashlib
import random
import time
from collections import Counter
from dataclasses import dataclass

SLAB = 4_406_400
DRIVER = "/usr/lib64/libcuda.so.1"


class Cuda:
    def __init__(self):
        self.lib = ct.CDLL(DRIVER)
        u32, u64, ptr, size = ct.c_uint, ct.c_uint64, ct.c_void_p, ct.c_size_t
        for name, args in {
            "cuInit": [u32],
            "cuDeviceGet": [ct.POINTER(ct.c_int), ct.c_int],
            "cuDevicePrimaryCtxRetain": [ct.POINTER(ptr), ct.c_int],
            "cuCtxSetCurrent": [ptr],
            "cuDriverGetVersion": [ct.POINTER(ct.c_int)],
            "cuMemAlloc_v2": [ct.POINTER(u64), size],
            "cuMemFree_v2": [u64],
            "cuMemsetD8_v2": [u64, ct.c_ubyte, size],
            "cuMemcpyHtoD_v2": [u64, ptr, size],
            "cuMemcpyDtoD_v2": [u64, u64, size],
            "cuMemcpyDtoH_v2": [ptr, u64, size],
            "cuCtxSynchronize": [],
            "cuDevicePrimaryCtxRelease_v2": [ct.c_int],
        }.items():
            f = getattr(self.lib, name)
            f.argtypes, f.restype = args, ct.c_int
        self.allocations = []
        self.call("cuInit", 0)
        self.device, self.context, self.version = ct.c_int(), ptr(), ct.c_int()
        self.call("cuDeviceGet", ct.byref(self.device), 0)
        self.call("cuDevicePrimaryCtxRetain", ct.byref(self.context), self.device)
        self.call("cuCtxSetCurrent", self.context)
        self.call("cuDriverGetVersion", ct.byref(self.version))

    def call(self, name, *args):
        status = getattr(self.lib, name)(*args)
        if status:
            raise RuntimeError(f"{name} returned {status}")

    def allocate(self):
        addr = ct.c_uint64()
        self.call("cuMemAlloc_v2", ct.byref(addr), SLAB)
        self.allocations.append(addr.value)
        if len(self.allocations) * SLAB > 1 << 30:
            raise ValueError("explicit GPU allocation budget")
        return addr.value

    def sync(self):
        self.call("cuCtxSynchronize")

    def close(self):
        self.sync()
        for addr in self.allocations:
            self.call("cuMemFree_v2", addr)
        self.call("cuCtxSetCurrent", None)
        self.call("cuDevicePrimaryCtxRelease_v2", self.device)


@dataclass
class Component:
    stage: int
    source: int
    carrier: int
    target: int
    sha256: str


class Transfers:
    def __init__(self, schedule, gpu):
        self.gpu, self.host = gpu, []
        self.components, self.events = [], []
        for i, leg in enumerate(schedule):
            layer, _, _, expert = leg["source"]
            cuda = layer >= 25
            parts = []
            for c in range(3):
                parts.append(self.component(cuda, (128 * layer + expert) * 3 + c))
            self.components.append((cuda, parts))
            for phase, key in enumerate(("save", "load")):
                self.events.append((tuple(leg[key]), phase, i))
        self.events.sort()
        self.scratch = ct.create_string_buffer(SLAB)
        self.gpu.sync()

    def ram(self):
        buf = ct.create_string_buffer(SLAB)
        self.host.append(buf)
        return ct.addressof(buf)

    def component(self, cuda, seed):
        values = random.Random(seed).randbytes(SLAB)
        stage = self.ram()
        ct.memmove(stage, values, SLAB)
        allocate = self.gpu.allocate if cuda else self.ram
        source, carrier, target = (allocate() for _ in range(3))
        if cuda:
            self.gpu.call("cuMemcpyHtoD_v2", source, stage, SLAB)
        else:
            ct.memmove(source, stage, SLAB)
        return Component(stage, source, carrier, target, hashlib.sha256(values).hexdigest())

    def reset(self):
        for cuda, parts in self.components:
            for p in parts:
                for addr, poison in ((p.carrier, 0x6A), (p.target, 0x93)):
                    if cuda:
                        self.gpu.call("cuMemsetD8_v2", addr, poison, SLAB)
                    else:
                        ct.memset(addr, poison, SLAB)
        self.gpu.sync()

    def timed(self, mode):
        if mode not in ("A", "B"):
            raise ValueError("unknown arm")
        by_tier, start = Counter(), time.perf_counter_ns()
        for _, phase, i in self.events:
            cuda, parts = self.components[i]
            begin = time.perf_counter_ns()
            for p in parts:
                if mode == "A":
                    if phase == 1:
                        if cuda:
                            self.gpu.call("cuMemcpyHtoD_v2", p.target, p.stage, SLAB)
                        else:
                            ct.memmove(p.target, p.stage, SLAB)
                else:
                    src, dst = (p.source, p.carrier) if phase == 0 else (p.carrier, p.target)
                    if cuda:
                        self.gpu.call("cuMemcpyDtoD_v2", dst, src, SLAB)
                    else:
                        ct.memmove(dst, src, SLAB)
            if cuda:
                self.gpu.sync()
            by_tier["CUDA0" if cuda else "CPU"] += time.perf_counter_ns() - begin
        return dict(
            mode=mode, wall_ns=time.perf_counter_ns() - start, transfer_site_ns=dict(by_tier)
        )

    def different(self):
        differences = []
        for i, (cuda, parts) in enumerate(self.components):
            for c, p in enumerate(parts):
                if cuda:
                    self.gpu.call("cuMemcpyDtoH_v2", ct.addressof(self.scratch), p.target, SLAB)
                    data = self.scratch
                else:
                    data = (ct.c_ubyte * SLAB).from_address(p.target)
                if hashlib.sha256(data).hexdigest() != p.sha256:
                    differences.append((i, c))
        return differences

    def corrupt(self):
        i = len(self.components) - 1
        cuda, parts = self.components[i]
        p = parts[-1]
        byte = ct.c_ubyte()
        if cuda:
            self.gpu.call("cuMemcpyDtoH_v2", ct.byref(byte), p.target + SLAB - 1, 1)
            byte.value ^= 1
            self.gpu.call("cuMemcpyHtoD_v2", p.target + SLAB - 1, ct.byref(byte), 1)
            self.gpu.sync()
        else:
            ct.c_ubyte.from_address(p.target + SLAB - 1).value ^= 1
        return (i, len(parts) - 1)
