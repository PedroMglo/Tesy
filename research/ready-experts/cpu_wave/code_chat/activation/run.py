"""Probe the registered R0 CPU dot and a layout-corrected independent expert on real weights."""

import argparse
import array
import ctypes as ct
import hashlib
import json
import math
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OLD = run_path(HERE.parent / "executor.py")
require = OLD["require"]
CPU = "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313"
N = 2880
STRIDE = N // 32 * 17
Float = ct.c_float
Vec = Float * N
BYTE = ct.c_uint8
Bits = BYTE * (N // 32 * 34)
Ptr = ct.c_void_p


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def receipt(path):
    return json.loads(path.read_bytes())


def save(path, data):
    with path.open("x") as file:
        json.dump(data, file, sort_keys=True, indent=2, allow_nan=False)
        file.write("\n")


def scope():
    root = Path("/sys/fs/cgroup") / Path(
        Path("/proc/self/cgroup").read_text().strip().split("::")[1]
    ).relative_to("/")
    require(
        root.name.startswith("tesy-code-collision-")
        and root.name.endswith(".scope")
        and (root / "memory.high").read_text().strip()
        == (root / "memory.max").read_text().strip()
        == str(512 << 20)
        and (root / "memory.swap.max").read_text().strip() == "0",
        "bounded CPU scope",
    )
    return root


def slab(folder):
    require(file_sha(folder / "receipt.json") == OLD["C291"], "C291 identity")
    r = receipt(folder / "receipt.json")
    idx = folder / "integral-index.json"
    require(file_sha(idx) == r["index_sha256"], "qualified index")
    e = receipt(idx)["experts"][0]
    c = e["components"][0]
    require(
        (e["layer"], e["expert"], c["name"], c["type"], c["size_bytes"])
        == (0, 0, "blk.0.ffn_gate_exps.weight", "mxfp4", N * STRIDE)
        and c["sha256"] == "8d9f8042b7cdee0e8813f5224382089fef3e30dc41646b63d2d5e6eb3569628f",
        "real gate",
    )

    def verify(fd):
        s = os.fstat(fd)
        require(
            dict(
                dev=s.st_dev,
                inode=s.st_ino,
                size_bytes=s.st_size,
                mtime_ns=s.st_mtime_ns,
                ctime_ns=s.st_ctime_ns,
            )
            == r["model_stat"],
            "GGUF descriptor",
        )

    with Path(r["model_path"]).open("rb", buffering=0) as f:
        verify(f.fileno())
        data = os.pread(f.fileno(), N * STRIDE, c["source_offset"])
        require(len(data) == N * STRIDE and sha(data) == c["sha256"], "complete gate payload")
        verify(f.fileno())
    return (BYTE * len(data)).from_buffer_copy(data), c, r["model_sha256"]


def bind(lib, name, args, ret=None):
    fun = getattr(lib, name)
    fun.argtypes = args
    fun.restype = ret
    return fun


class Traits(ct.Structure):
    _fields_ = [
        ("from_float", Ptr),
        ("vec_dot", Ptr),
        ("vec_dot_type", ct.c_int),
        ("nrows", ct.c_int64),
    ]


def inputs():
    control = Vec()
    control[0] = 127 / 64
    plus = Vec.from_buffer_copy(control)
    plus[1] = 1 / 256
    minus = Vec.from_buffer_copy(control)
    minus[1] = -1 / 256
    dense = Vec(
        *[(((73 * i + 19) % 257) - 128) / 127 + (((37 * i) % 31) - 15) / 8192 for i in range(N)]
    )
    return dict(control=control, positive=plus, negative=minus, dense=dense)


def reorder(vector):
    x = Vec()
    for i, v in enumerate(vector):
        x[i // 32 * 32 + 2 * (i % 16) + (i % 32) // 16] = v
    return x


def difference(target, other):
    require(all(math.isfinite(v) for row in (target, other) for v in row), "finite projection")
    left = array.array("I")
    right = array.array("I")
    left.frombytes(bytes(target))
    right.frombytes(bytes(other))
    require(len(left) == len(right) == N, "2880 F32 words")
    return dict(
        different_bits=sum(a != b for a, b in zip(left, right, strict=True)),
        different_values=sum(a != b for a, b in zip(target, other, strict=True)),
        max_abs=max(abs(a - b) for a, b in zip(target, other, strict=True)),
        result_sha256=sha(bytes(other)),
    )


def run(a):
    require(ct.sizeof(Float) == 4 and sys.byteorder == "little", "F32 platform")
    frozen = receipt(HERE.parent / "executor-result.json")
    require(
        frozen == receipt(a.binaries / "decision.json")
        and frozen["decision"] == "NO_GO_AS_SHIPPED_EXPERT_GEMV"
        and frozen["upstream_commit"] == OLD["UPSTREAM"]
        and frozen["source_sha256"] == OLD["SOURCES"],
        "external numerical authority",
    )
    require(file_sha(a.cpu) == CPU and file_sha(a.base) == OLD["REFERENCE"], "R0 CPU and base ELF")
    gg = ct.CDLL(str(a.base), mode=ct.RTLD_GLOBAL)
    cpu = ct.CDLL(str(a.cpu))
    mapped = {
        Path(line.split(maxsplit=5)[-1]).resolve()
        for line in Path("/proc/self/maps").read_text().splitlines()
        if "r-xp" in line and "libggml" in line
    }
    require(mapped == {a.base, a.cpu}, "loaded GGML implementation")
    bind(cpu, "ggml_cpu_init", [])()
    traits = bind(cpu, "ggml_get_type_traits_cpu", [ct.c_int], ct.POINTER(Traits))
    q = bind(cpu, "quantize_row_q8_0", [Ptr, Ptr, ct.c_int64])
    dot = bind(
        cpu,
        "ggml_vec_dot_mxfp4_q8_0",
        [ct.c_int, Ptr, ct.c_size_t, Ptr, ct.c_size_t, Ptr, ct.c_size_t, ct.c_int],
    )
    unpack = bind(gg, "dequantize_row_q8_0", [Ptr, Ptr, ct.c_int64])
    weights_to_fp = bind(gg, "dequantize_row_mxfp4", [Ptr, Ptr, ct.c_int64])
    mx, qt = traits(39).contents, traits(8).contents
    require(
        mx.vec_dot_type == 8
        and mx.nrows == 1
        and mx.vec_dot == ct.cast(dot, Ptr).value
        and qt.from_float == ct.cast(q, Ptr).value,
        "registered target operators",
    )
    mats, component, model = slab(a.derived)
    x = inputs()
    packed = {}
    ref = {}
    dq = {}
    analytic = {}
    refs = {}
    for name, src in x.items():
        qb = Bits()
        q(src, qb, N)
        packed[name] = bytes(qb)
        quantized = Vec()
        unpack(qb, quantized, N)
        dq[name] = quantized
        y = Vec()
        expected = Vec()
        for row in range(N):
            ptr = ct.byref(mats, row * STRIDE)
            dot(N, ct.byref(y, row * 4), 0, ptr, 0, qb, 0, 1)
            if name != "dense":
                line = (Float * 32)()
                weights_to_fp(ptr, line, 32)
                expected[row] = Float(line[0] * src[0] + line[1] * src[1]).value
        ref[name] = y
        analytic[name] = expected
        refs[name] = dict(
            input_sha256=sha(bytes(src)),
            activation_q8_sha256=sha(bytes(qb)),
            dequantized_f32_sha256=sha(bytes(quantized)),
            dot_sha256=sha(bytes(y)),
        )
    require(
        packed["control"] == packed["positive"] == packed["negative"]
        and bytes(ref["control"]) == bytes(ref["positive"]) == bytes(ref["negative"])
        and any(v != 0 for v in ref["control"])
        and bytes(dq["control"]) == bytes(x["control"])
        and difference(analytic["control"], ref["control"])["different_values"] == 0,
        "collision control",
    )
    builds = {}
    witness = []
    for name in ("scalar", "avx2"):
        path = a.binaries / (name + ".so")
        require(file_sha(path) == frozen["builds"][name]["binary_sha256"], "native " + name)
        lib = ct.CDLL(str(path))
        gemv = bind(lib, "gemv_mxfp4_f32_direct", [Ptr, Ptr, Ptr, ct.c_uint32, ct.c_uint32])
        outcomes = {}
        outputs = {}
        for case in x:
            outcomes[case] = {}
            for variant, vector in (("layout", x[case]), ("layout_and_q8", dq[case])):
                y = Vec()
                gemv(mats, reorder(vector), y, N, N)
                outcomes[case][variant] = difference(ref[case], y)
                if case != "dense":
                    oracle = analytic[case] if variant == "layout" else ref["control"]
                    require(
                        difference(oracle, y)["different_values"] == 0,
                        "two-coordinate independent oracle",
                    )
                if variant == "layout":
                    outputs[case] = y
        delta = difference(outputs["positive"], outputs["negative"])
        witness.append(delta["different_values"] > 0)
        builds[name] = dict(elf_sha256=file_sha(path), cases=outcomes, collision_pair=delta)
    require(set(witness) in ({True}, {False}), "builds disagree on witness")
    decision = "NO_GO_LAYOUT_ONLY_REGISTERED_CPU_DOT" if all(witness) else "INCONCLUSIVE"
    if not any(witness) and all(
        item["layout"]["different_bits"] == 0
        for v in builds.values()
        for item in v["cases"].values()
    ):
        decision = "GO_ROUTED_LAYER_ONLY"
    return dict(
        decision=decision,
        classification="MEDIDO_OPERADOR_CPU",
        protocol_sha256=file_sha(HERE / "protocol.md"),
        program_sha256=file_sha(Path(__file__)),
        model_sha256=model,
        gate_sha256=component["sha256"],
        logical_gguf_bytes=N * STRIDE,
        rows=N,
        inner=N,
        inputs=refs,
        builds=builds,
        original_cpu_sha256=CPU,
        base_sha256=OLD["REFERENCE"],
        external_commit=OLD["UPSTREAM"],
        gpu_forwards=0,
        model_forwards=0,
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for k in ("binaries", "derived", "cpu", "base", "new-output-dir"):
        cli.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    a = cli.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    started = time.monotonic()
    try:
        cg = scope()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
        require(
            not subprocess.check_output(["git", "status", "--porcelain"], cwd=HERE),
            "clean operator source",
        )
        save(
            a.new_output_dir / "provenance.json",
            dict(
                commit=commit,
                protocol_sha256=file_sha(HERE / "protocol.md"),
                program_sha256=file_sha(Path(__file__)),
                scope=cg.name,
            ),
        )
        out = run(a)
        events = dict(row.split() for row in (cg / "memory.events").read_text().splitlines())
        require(
            time.monotonic() - started <= 60
            and all(int(events[k]) == 0 for k in ("oom", "oom_kill"))
            and (cg / "memory.swap.current").read_text().strip() == "0",
            "operator resource gate",
        )
        save(
            a.new_output_dir / "resources.json",
            dict(
                elapsed_s=time.monotonic() - started,
                peak_bytes=int((cg / "memory.peak").read_text()),
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                cap_bytes=512 << 20,
                swap_bytes=0,
                oom=0,
            ),
        )
    except Exception as exc:
        save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    save(a.new_output_dir / "decision.json", out)
    print(out["decision"])
