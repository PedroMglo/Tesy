#!/usr/bin/python3 -I
"""Serve the same cold, authenticated mmap ranges to the same CUDA slots in both orders."""

import ctypes as ct
import hashlib
import json
import mmap
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

clock = time.monotonic_ns
Pointer, Size, CInt = ct.c_void_p, ct.c_size_t, ct.c_int
PAGE = 4096
BLOCK = Path("/sys/class/block/nvme0n1")


def require(ok, why):
    if not ok:
        raise ValueError(why)


def bind(lib, name, args, returns):
    fn = getattr(lib, name)
    fn.argtypes = args
    fn.restype = returns
    return fn


libc = ct.CDLL(None, use_errno=True)
file_map = bind(libc, "mmap", [Pointer, Size, CInt, CInt, CInt, ct.c_long], Pointer)
unmap = bind(libc, "munmap", [Pointer, Size], CInt)
mincore = bind(libc, "mincore", [Pointer, Size, Pointer], CInt)
copy = bind(libc, "memcpy", [Pointer, Pointer, Size], Pointer)


class Cuda:
    def __init__(self, path):
        self.lib = ct.CDLL(path)
        for name, args in {
            "cudaSetDevice": [CInt],
            "cudaMalloc": [ct.POINTER(Pointer), Size],
            "cudaFree": [Pointer],
            "cudaStreamCreateWithFlags": [ct.POINTER(Pointer), ct.c_uint],
            "cudaStreamDestroy": [Pointer],
            "cudaStreamSynchronize": [Pointer],
            "cudaMemsetAsync": [Pointer, CInt, Size, Pointer],
            "cudaMemcpyAsync": [Pointer, Pointer, Size, CInt, Pointer],
            "cudaMemcpy": [Pointer, Pointer, Size, CInt],
            "cudaDeviceReset": [],
        }.items():
            bind(self.lib, name, args, CInt)

    def __call__(self, name, *args):
        rc = getattr(self.lib, name)(*args)
        require(rc == 0, f"{name} returned {rc}")


def handoff(marker):
    require(os.write(int(os.environ["TESY_TEST_TX"]), marker) == 1, "handoff send")
    require(os.read(int(os.environ["TESY_TEST_RX"]), 1) == marker, "handoff ack")


def model_id(fd):
    st = os.fstat(fd)
    require(st.st_uid == os.getuid(), "source ownership")
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


@contextmanager
def cold_source(plan):
    with open(plan["model"], "rb", buffering=0) as f:
        fd = f.fileno()
        require(model_id(fd) == plan["model_stat"], "source identity")
        size = plan["model_stat"][2]
        start = plan["tensor_start"] // PAGE * PAGE
        stop = (plan["tensor_start"] + plan["tensor_bytes"] + PAGE - 1) // PAGE * PAGE
        os.posix_fadvise(fd, start, stop - start, os.POSIX_FADV_DONTNEED)
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_SEQUENTIAL)
        base = file_map(None, size, mmap.PROT_READ, mmap.MAP_SHARED, fd, 0)
        require(base not in (None, Pointer(-1).value), "read-only file mmap")
        try:
            vec = (ct.c_ubyte * ((stop - start) // PAGE))()

            def resident():
                require(mincore(base + start, stop - start, vec) == 0, "mincore")
                return sum(b & 1 for b in vec)

            yield base, resident, len(vec)
            require(model_id(fd) == plan["model_stat"], "source changed")
        finally:
            require(unmap(base, size) == 0, "munmap")


def counters(scope, dev):
    sectors = int((BLOCK / "stat").read_text().split()[2])
    lines = [
        v
        for line in (scope / "io.stat").read_text().splitlines()
        if (v := line.split()) and v[0] == dev
    ]
    require(len(lines) <= 1, "scope NVMe identity")
    scope_bytes = int(dict(k.split("=") for k in lines[0][1:])["rbytes"]) if lines else 0
    pid = dict(line.split(": ") for line in Path("/proc/self/io").read_text().splitlines())
    return dict(namespace_B=sectors * 512, scope_B=scope_bytes, pid_B=int(pid["read_bytes"]))


def sample(mode, plan, gpu, dst, stream, scratch, scope, dev):
    payload = plan["payload_B"]
    ct.memset(scratch, 0, plan["scratch_B"])
    gpu("cudaMemsetAsync", dst - PAGE, 0xA5, payload + 2 * PAGE, stream)
    gpu("cudaStreamSynchronize", stream)
    with cold_source(plan) as (base, resident, total):
        initial = resident()
        require(initial == 0, f"cold gate has {initial}/{total} resident pages")
        before = counters(scope, dev)
        events = []
        start = clock()
        for row in plan["sets"]:
            src = base + row["source"]
            t0 = clock()
            if mode == "STAGED":
                addr = scratch + row["scratch"]
                copy(addr, src, row["bytes"])
                src = addr
            t1 = clock()
            gpu("cudaMemcpyAsync", dst + row["dest"], src, row["bytes"], 1, stream)
            events.append([t0 - start, t1 - start, clock() - start])
        issued = clock()
        gpu("cudaStreamSynchronize", stream)
        end = clock()
        after = counters(scope, dev)
        final = resident()
    delta = {k: after[k] - v for k, v in before.items()}
    require(
        0 < delta["namespace_B"] <= 6 << 30 and delta["scope_B"] > 0 and delta["pid_B"] >= 0,
        "physical cold reads or CInt/O budget",
    )
    verify_start = clock()
    buf = ct.create_string_buffer(max(r["bytes"] for r in plan["sets"]))
    observed = []
    for row in plan["sets"]:
        n = row["bytes"]
        gpu("cudaMemcpy", buf, dst + row["dest"], n, 2)
        observed.append(hashlib.sha256(memoryview(buf)[:n]).hexdigest())
        require(observed[-1] == row["sha256"], "CUDA destination differs from independent pread")
    for addr in (dst - PAGE, dst + payload):
        gpu("cudaMemcpy", buf, addr, PAGE, 2)
        require(bytes(memoryview(buf)[:PAGE]) == b"\xa5" * PAGE, "GPU guard changed")
    return dict(
        mode=mode,
        total_ns=end - start,
        events_ns=events,
        issued_ns=issued - start,
        drain_ns=end - issued,
        before=before,
        after=after,
        delta=delta,
        resident_before=initial,
        resident_after=final,
        tensor_pages=total,
        check_ns=clock() - verify_start,
        verified=observed,
        guards_B=2 * PAGE,
    )


def main():
    order, p, out = sys.argv[1:]
    orders = {"DIRECT_FIRST": ("DIRECT", "STAGED"), "STAGED_FIRST": ("STAGED", "DIRECT")}
    modes = orders[order]
    out = Path(out)
    out.mkdir(mode=0o700)
    plan = json.loads(Path(p).read_bytes())
    require(plan["status"] == "SEALED_GATE_BYTES" and os.sysconf("SC_PAGE_SIZE") == PAGE, "plan")
    scope = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::")[
        1
    ].lstrip("/")
    dev = (BLOCK / "dev").read_text().strip()
    handoff(b"E")
    gpu = Cuda(os.environ["TESY_CUDART"])
    gpu("cudaSetDevice", 0)
    device = Pointer()
    stream = Pointer()
    gpu("cudaStreamCreateWithFlags", ct.byref(stream), 1)
    gpu("cudaMalloc", ct.byref(device), plan["payload_B"] + 2 * PAGE)
    with mmap.mmap(-1, plan["scratch_B"], flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS) as scratch:
        ptr = ct.addressof(ct.c_char.from_buffer(scratch))
        require(ptr % PAGE == 0, "scratch alignment")
        handoff(b"A")
        for mode in modes:
            r = sample(mode, plan, gpu, device.value + PAGE, stream, ptr, scope, dev)
            (out / (mode + ".json")).write_text(json.dumps(r, sort_keys=True) + "\n")
        (out / "maps").write_bytes(Path("/proc/self/maps").read_bytes())
        handoff(b"F")
    gpu("cudaStreamDestroy", stream)
    gpu("cudaFree", device)
    gpu("cudaDeviceReset")


if __name__ == "__main__":
    main()
