"""C269 GGML destinations, with the loaded GGML and CUDA providers bound to the reference."""

import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
authority = run_path(str(HERE.parents[2] / "nvme_r0_gate/qualified_profile/authority.py"))
need = authority["need"]
MAP_SHA = "7e9d0efb4c9bac6ef88d0de0003e8643fc14f4f9942c72a8101e2c166b8b1729"
MXFP4 = 39
SHAPE = (2880, 2880, 40, 1)
SLAB = 4_406_400
STRIDES = (17, 1530, SLAB, SLAB * 40)
NATIVE = (
    "libcuda.so.1",
    "libnvidia-ptxjitcompiler.so.1",
    "libnvidia-nvvm70.so.4",
    "libnvidia-gpucomp.so.620.70.06",
    "libcudart.so.13",
    "libcublasLt.so.13",
    "libcublas.so.13",
    "libggml-base.so.0",
    "libggml-cpu.so.0",
    "libggml-cuda.so.0",
)


class InitParams(ct.Structure):
    _fields_ = [("mem_size", ct.c_size_t), ("mem_buffer", ct.c_void_p), ("no_alloc", ct.c_bool)]


class TensorHeader(ct.Structure):
    # Prefix of ggml_tensor at the C269 pin; the rest is owned by GGML.
    _fields_ = [
        ("type", ct.c_int),
        ("buffer", ct.c_void_p),
        ("ne", ct.c_int64 * 4),
        ("nb", ct.c_size_t * 4),
    ]


def mapping_rows():
    rows = []
    for line in Path("/proc/self/maps").read_text().splitlines():
        cols = line.split(maxsplit=5)
        if len(cols) == 6 and cols[5].startswith("/") and ".so" in Path(cols[5]).name:
            rows.append((cols[5], authority["mapping_key"](cols)))
    return set(rows)


def relevant(path):
    return Path(path).name.startswith(("libggml", "libcuda", "libcublas", "libnvidia", "libllama"))


class Providers:
    def __init__(self, map_path):
        raw = Path(map_path).read_bytes()
        need(hashlib.sha256(raw).hexdigest() == MAP_SHA, "C269 static map")
        manifest = json.loads(raw)
        need(
            Path("/sys/module/nvidia/version").read_text().strip() == "620.70.06", "driver release"
        )
        need(
            not os.environ.get("LD_PRELOAD") and not os.environ.get("LD_AUDIT"),
            "foreign loader hook",
        )
        self.files = manifest["files"]
        links = manifest["arms"]["C270"]["links"]
        self.paths = {k: v[1] for k, v in links.items()} | manifest["driver_aliases"]
        self.allowed = set(self.paths.values())
        self.check_files()
        self.vma = {p: authority["reference_key"](p, self.files[p]) for p in self.allowed}
        self.before = mapping_rows()
        self.handles = {}
        self.check_maps()
        for name in NATIVE:
            self.handles[name] = ct.CDLL(self.paths[name], mode=os.RTLD_NOW | os.RTLD_LOCAL)
        self.check_maps()

    def check_files(self):
        for p in self.allowed:
            now = authority["identity"](p)
            need(
                all(self.files[p][k] == v for k, v in now.items()), "replaced ELF: " + Path(p).name
            )

    def check_maps(self):
        rows = mapping_rows()
        for p, key in rows:
            if relevant(p) or (p, key) not in self.before or p in self.allowed:
                need(p in self.allowed and self.vma[p] == key, "unqualified ELF: " + p)
        mapped = {p for p, _ in rows}
        need(all(self.paths[name] in mapped for name in self.handles), "absent selected DSO")
        return {Path(p).name: self.files[p]["sha256"] for p in sorted(mapped & self.allowed)}


def bind(library, name, result, *args):
    call = getattr(library, name)
    call.restype = result
    call.argtypes = list(args)
    return call


class NativeSinks:
    """Three original-format weights per tier, each with forty independently addressed slots."""

    def __init__(self, stack, map_path):
        self.providers = Providers(map_path)
        libs = self.providers.handles
        base = libs["libggml-base.so.0"]
        pointer, size, integer = ct.c_void_p, ct.c_size_t, ct.c_int
        ctx_init = bind(base, "ggml_init", pointer, InitParams)
        ctx_free = bind(base, "ggml_free", None, pointer)
        backend_free = bind(base, "ggml_backend_free", None, pointer)
        buffer_free = bind(base, "ggml_backend_buffer_free", None, pointer)
        new_tensor = bind(
            base, "ggml_new_tensor_3d", pointer, pointer, integer, *([ct.c_int64] * 3)
        )
        allocate = bind(base, "ggml_backend_alloc_ctx_tensors", pointer, pointer, pointer)
        set_usage = bind(base, "ggml_backend_buffer_set_usage", None, pointer, integer)
        usage = bind(base, "ggml_backend_buffer_get_usage", integer, pointer)
        name = bind(base, "ggml_backend_buffer_name", ct.c_char_p, pointer)
        is_host = bind(base, "ggml_backend_buffer_is_host", ct.c_bool, pointer)
        buf_size = bind(base, "ggml_backend_buffer_get_size", size, pointer)
        buf_base = bind(base, "ggml_backend_buffer_get_base", pointer, pointer)
        type_name = bind(base, "ggml_type_name", ct.c_char_p, integer)
        contiguous = bind(base, "ggml_is_contiguous", ct.c_bool, pointer)
        nbytes = bind(base, "ggml_nbytes", size, pointer)
        data = bind(base, "ggml_get_data", pointer, pointer)
        self.write = bind(base, "ggml_backend_tensor_set", None, pointer, pointer, size, size)
        self.read = bind(base, "ggml_backend_tensor_get", None, pointer, pointer, size, size)
        self.synchronize = bind(base, "ggml_backend_synchronize", None, pointer)
        need(type_name(MXFP4) == b"mxfp4", "C269 quantization type")
        self.backends, self.tensors = {}, {}
        self.receipt = {"map_sha256": MAP_SHA, "pools": {}}
        for tier, expected_name in (("cpu", "CPU"), ("cuda", "CUDA0")):
            if tier == "cpu":
                init = bind(libs["libggml-cpu.so.0"], "ggml_backend_cpu_init", pointer)
                backend = init()
            else:
                init = bind(libs["libggml-cuda.so.0"], "ggml_backend_cuda_init", pointer, integer)
                backend = init(0)
            need(backend, "backend creation: " + tier)
            stack.callback(backend_free, backend)
            ctx = ctx_init(InitParams(64 * 1024, None, True))
            need(ctx, "tensor metadata: " + tier)
            stack.callback(ctx_free, ctx)
            tensors = tuple(new_tensor(ctx, MXFP4, *SHAPE[:3]) for _ in range(3))
            need(all(tensors), "tensor creation: " + tier)
            buffer = allocate(ctx, backend)
            need(buffer, "weight buffer: " + tier)
            stack.callback(buffer_free, buffer)
            set_usage(buffer, 1)
            length, address = buf_size(buffer), buf_base(buffer)
            need(
                name(buffer).decode() == expected_name
                and is_host(buffer) == (tier == "cpu")
                and usage(buffer) == 1
                and address,
                "weight buffer type: " + tier,
            )
            ranges = []
            for tensor in tensors:
                h = TensorHeader.from_address(tensor)
                need(
                    h.type == MXFP4
                    and h.buffer == buffer
                    and tuple(h.ne) == SHAPE
                    and tuple(h.nb) == STRIDES
                    and contiguous(tensor)
                    and nbytes(tensor) == 40 * SLAB,
                    "physical MXFP4 layout",
                )
                start = data(tensor)
                ranges.append((start - address, start - address + nbytes(tensor)))
            spans = sorted(ranges)
            need(
                0 <= spans[0][0]
                and spans[-1][1] <= length
                and all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False)),
                "tensor ownership",
            )
            self.backends[tier], self.tensors[tier] = backend, tensors
            self.receipt["pools"][tier] = dict(
                buffer=expected_name,
                bytes=length,
                weights=True,
                shape=SHAPE,
                strides=STRIDES,
                tensor_ranges=ranges,
            )
        self.end_check()

    def transfer(self, role, slot, address):
        need(
            type(role) is int
            and 0 <= role < 3
            and type(slot) is int
            and 0 <= slot < 40
            and type(address) is int
            and address > 0,
            "component, slot or staging address",
        )

    def put(self, tier, role, slot, address):
        self.transfer(role, slot, address)
        self.write(self.tensors[tier][role], address, slot * SLAB, SLAB)

    def get(self, tier, role, slot, address):
        self.transfer(role, slot, address)
        self.read(self.tensors[tier][role], address, slot * SLAB, SLAB)

    def sync(self, tier):
        self.synchronize(self.backends[tier])

    def end_check(self):
        self.providers.check_files()
        self.receipt["loaded_sha256"] = self.providers.check_maps()
        return self.receipt
