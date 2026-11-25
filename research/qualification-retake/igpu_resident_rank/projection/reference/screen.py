"""Independent CPU reconstruction and conditional attribution for C270 e28 gate."""

import argparse
import ctypes as C
import hashlib
import json
import math
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import arithmetic as a  # noqa: E402

INPUT = "c928ffcd17719deb9c7122ef7e05b7122e3f5eca199e7be2a75dc59254f52b6e"
SOURCES = {
    "ggml/src/ggml-cpu/arch/x86/quants.c": (
        "3c489fdc77e3ab484a5f188bff9c60c0e9483c951ed65c1a562a04c249d5628e"
    ),
    "ggml/src/ggml-impl.h": "2ed56e264202906d107e26d08eabb242d3107b026ebfb78096fa1e5f94bdbbb8",
    "ggml/src/ggml-common.h": "578a0cffc8284387191aceb7128cc39d92a3b3edc199fe0b79ed8627fefcc633",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def checked(path, digest):
    value = path.read_bytes()
    need(sha(value) == digest, f"digest of {path.name}")
    return value


def identity(st):
    return dict(
        dev=st.st_dev,
        ino=st.st_ino,
        size=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


def read_inputs(args):
    ref = json.loads(checked(HERE.parent / "input-receipt.json", INPUT))
    checked(args.bundle / "receipt.json", ref["reference_receipt_sha256"])
    checked(args.bundle / "plan.json", ref["plan_sha256"])
    x = checked(args.bundle / "attn_post_norm.bin", ref["verified_rows_sha256"]["attn_post_norm"])
    placement = json.loads(checked(args.placement, ref["placement_receipt_sha256"]))
    record = ref["e28_record"]
    component = record["components"][0]
    need(component["name"] == "blk.0.ffn_gate_exps.weight", "gate role")
    with open(placement["destination"], "rb", buffering=0) as pack:
        need(identity(os.fstat(pack.fileno())) == placement["destination_stat"], "pack fd identity")
        weights = os.pread(
            pack.fileno(), component["bytes"], record["offset"] + component["offset_in_record"]
        )
        need(identity(os.fstat(pack.fileno())) == placement["destination_stat"], "pack changed")
    need(len(weights) == a.K * a.WROW and sha(weights) == component["sha256"], "gate bytes")
    return ref, x, weights


class DlInfo(C.Structure):
    _fields_ = [
        ("name", C.c_char_p),
        ("base", C.c_void_p),
        ("symbol", C.c_char_p),
        ("address", C.c_void_p),
    ]


def provider(fn):
    dladdr = C.CDLL(None).dladdr
    dladdr.argtypes = [C.c_void_p, C.POINTER(DlInfo)]
    dladdr.restype = C.c_int
    info = DlInfo()
    need(dladdr(C.cast(fn, C.c_void_p), C.byref(info)) == 1, "unresolved symbol")
    return Path(os.fsdecode(info.name)).resolve(strict=True)


def original(backend, ref, x, weights):
    for path, digest in SOURCES.items():
        checked(backend / path, digest)
    libs = backend / "build-c269-cuda/bin"
    basefile = (libs / "libggml-base.so.0.15.3").resolve(strict=True)
    cpufile = (libs / "libggml-cpu.so.0.15.3").resolve(strict=True)
    for file in (basefile, cpufile):
        checked(file, ref["c269_dso_sha256"][file.name])
    base = C.CDLL(basefile, mode=os.RTLD_NOW | os.RTLD_GLOBAL)
    cpu = C.CDLL(cpufile, mode=os.RTLD_NOW | os.RTLD_LOCAL)
    need(
        provider(base.ggml_init) == basefile and provider(cpu.ggml_init) == basefile,
        "base provider",
    )
    quant, dot = cpu.quantize_row_q8_0, cpu.ggml_vec_dot_mxfp4_q8_0
    for func in (cpu.ggml_cpu_init, quant, dot):
        need(provider(func) == cpufile, "CPU provider")
    cpu.ggml_cpu_init.argtypes = []
    cpu.ggml_cpu_init.restype = None
    cpu.ggml_cpu_init()
    quant.argtypes = [C.c_void_p, C.c_void_p, C.c_int64]
    quant.restype = None
    dot.argtypes = [
        C.c_int,
        C.c_void_p,
        C.c_size_t,
        C.c_void_p,
        C.c_size_t,
        C.c_void_p,
        C.c_size_t,
        C.c_int,
    ]
    dot.restype = None
    buf = C.create_string_buffer(a.QROW)
    quant(x, buf, a.K)
    matrix = C.create_string_buffer(weights, len(weights))
    ys = (C.c_float * a.K)()
    for row in range(a.K):
        dot(a.K, C.byref(ys, row * 4), 0, C.byref(matrix, row * a.WROW), 0, buf, 0, 1)
    need(all(map(math.isfinite, ys)), "non-finite original dot")
    return bytes(buf), bytes(ys)


def prepare(args, out):
    ref, x, weights = read_inputs(args)
    canonical, native = original(args.backend, ref, x, weights)
    q8 = a.quantize(x)
    require_equal(q8, canonical, 34, "independent Q8_0")
    row = a.project(weights, q8)
    require_equal(row, native, 4, "independent AVX2 dot")
    (out / "activation.q8").write_bytes(q8)
    (out / "gate.f32").write_bytes(row)
    return {
        "status": "PASS_C269_GATE_ARITHMETIC",
        "inputs_receipt_sha256": INPUT,
        "activation_sha256": sha(x),
        "weights_sha256": sha(weights),
        "weight_bytes_read": len(weights),
        "cpu_dso_sha256": ref["c269_dso_sha256"],
        "cpu_sources": SOURCES,
        "q8_sha256": sha(q8),
        "gate_sha256": sha(row),
        "q8_blocks_equal": a.BLOCKS,
        "f32_rows_equal": a.K,
        "real_graph_compared": False,
    }


def delta(x, y, size):
    need(len(x) == len(y) and len(x) % size == 0, "comparison shape")
    differences = [i // size for i in range(0, len(x), size) if x[i : i + size] != y[i : i + size]]
    return {"different": len(differences), "first": differences[0] if differences else None}


def require_equal(x, y, size, name):
    change = delta(x, y, size)
    need(not change["different"], f"{name}: {change}")


def diagnose(args, out):
    ref, _, w = read_inputs(args)
    cpu = json.loads(checked(args.cpu_dir / "receipt.json", args.cpu_receipt_sha256))
    need(
        cpu["status"] == "PASS_C269_GATE_ARITHMETIC" and cpu["inputs_receipt_sha256"] == INPUT,
        "CPU receipt",
    )
    q = checked(args.cpu_dir / "activation.q8", cpu["q8_sha256"])
    gate = checked(args.cpu_dir / "gate.f32", cpu["gate_sha256"])
    require_equal(q, checked(args.graph_q8, args.graph_q8_sha256), 34, "graph Q8_0")
    require_equal(gate, checked(args.graph_gate, args.graph_gate_sha256), 4, "graph gate")
    cand = checked(args.candidate_gate, args.candidate_gate_sha256)
    need(
        len(cand) == a.K * 4 and all(map(math.isfinite, struct.unpack("<2880f", cand))),
        "candidate row",
    )
    disparity = delta(gate, cand, 4)
    summary = {
        "status": "DIAGNOSED_PROJECTION",
        "cpu_receipt_sha256": args.cpu_receipt_sha256,
        "graph_gate_sha256": sha(gate),
        "graph_q8_sha256": sha(q),
        "candidate_gate_sha256": sha(cand),
        "candidate_minus_reference": disparity,
        "candidate_rhs_inspected": False,
        "first_device_internal_divergence": None,
        "inputs_receipt_sha256": INPUT,
    }
    if args.candidate_x4 is None:
        need(args.candidate_x4_sha256 is None, "x4 hash without file")
        return summary
    x4 = checked(args.candidate_x4, args.candidate_x4_sha256)
    alt = a.from_x4(x4)
    alternative = a.project(w, alt) if alt != q else gate
    block_change = delta(q, alt, 34)
    scale_change = delta(
        b"".join(q[i : i + 2] for i in range(0, len(q), 34)),
        b"".join(alt[i : i + 2] for i in range(0, len(alt), 34)),
        2,
    )
    def codes(data):
        return b"".join(data[i + 2 : i + 34] for i in range(0, len(data), 34))
    summary.update(
        {
            "candidate_rhs_inspected": True,
            "candidate_x4_sha256": sha(x4),
            "dot_relevant_blocks": block_change,
            "scales": scale_change,
            "codes": delta(codes(q), codes(alt), 1),
            "candidate_rhs_cpu_reduction_sha256": sha(alternative),
            "rhs_only_minus_reference": delta(gate, alternative, 4),
            "candidate_minus_rhs_only": delta(alternative, cand, 4),
        }
    )
    first = disparity["first"]
    if first is not None:
        selected = w[first * a.WROW : (first + 1) * a.WROW]
        traces = {}
        for name, data in (("cpu", q), ("candidate_rhs", alt)):
            _, traces[name] = a.dot_row(selected, a.unpack_q8(data), trace=True)
        (out / "first-row-traces.json").write_text(json.dumps(traces) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--backend", required=True, type=Path)
    diag = commands.add_parser("diagnose")
    diag.add_argument("--cpu-dir", required=True, type=Path)
    diag.add_argument("--cpu-receipt-sha256", required=True)
    for flag in ("graph-q8", "graph-gate", "candidate-gate", "candidate-x4"):
        required = flag != "candidate-x4"
        diag.add_argument("--" + flag, required=required, type=Path)
        diag.add_argument("--" + flag + "-sha256", required=required)
    for command in (prep, diag):
        command.add_argument("--bundle", required=True, type=Path)
        command.add_argument("--placement", required=True, type=Path)
        command.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.new_output_dir
    out.mkdir(mode=0o700)
    try:
        result = prepare(args, out) if args.mode == "prepare" else diagnose(args, out)
    except Exception as exc:
        (out / "receipt.json").write_text(json.dumps({"status": "FAIL", "reason": str(exc)}) + "\n")
        raise
    result["program_sha256"] = {
        f: sha((HERE / f).read_bytes()) for f in ("screen.py", "arithmetic.py", "protocol.md")
    }
    (out / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"])


if __name__ == "__main__":
    main()
