"""Compare all three projection rows of the first captured CPU rank with two external GEMVs."""

import argparse
import ctypes as ct
import json
import math
import os
import resource
import struct
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(HERE.parent / "activation/run.py")
OPERANDS = run_path(HERE.parents[2] / "operands/check.py")
need, sha, receipt, save = (A[k] for k in ("require", "sha", "receipt", "save"))
N, STRIDE, Vec, Bits, Ptr, bind = (A[k] for k in ("N", "STRIDE", "Vec", "Bits", "Ptr", "bind"))
PROJECTIONS = ("gate", "up", "down")


def capture(archive):
    observed, anchor = (OPERANDS["Archive"](archive, k) for k in (110, 86))

    def boundary(name):
        return observed.read(f"{OPERANDS['BOUNDARY']}/189.{name}-0.bin")

    def row(name):
        return anchor.read(f"{OPERANDS['RANK']}/{name}")

    ranks = json.loads(row("rank.json"))
    ids = struct.unpack("<4i", boundary("ffn_moe_topk"))
    need(
        list(ids) == ranks["logical"] == [28, 24, 8, 16]
        and ranks["physical"] == [3, 14, 6, 35]
        and ranks["generations"] == [6, 6, 5, 4]
        and ranks["status"] == "PASS_CPU0_RANK_STAGES_CAPTURE"
        and ranks["shape"] == [N, 4, 1, 1],
        "observed rank",
    )
    x = boundary("attn_post_norm")
    hidden = boundary("ffn_moe_swiglu_oai")
    need(
        len(x) == 4 * N and len(hidden) == 4 * 4 * N and row("swiglu.f32") == hidden,
        "separate target inputs",
    )
    gold = {}
    for k in PROJECTIONS:
        data = row(k + ".f32")
        need(
            len(data) == N * 4 * 4 and sha(data) == ranks["files_sha256"][k + ".f32"],
            "capture " + k,
        )
        gold[k] = Vec.from_buffer_copy(data[: 4 * N])
    return {"gate": x, "up": x, "down": hidden[: 4 * N]}, gold, row("down-rank0.q8")


def run(a):
    proof = receipt(HERE.parent / "activation/result.json")
    need(
        proof["decision"] == "NO_GO_LAYOUT_ONLY_REGISTERED_CPU_DOT"
        and A["file_sha"](HERE.parent / "activation/result.json")
        == "f3c8486cfdb4d20de58dce467f7bc00ca1872f1e0e29cc91a6f0cb29a94ffd8e",
        "prior operator",
    )
    src, gold, downq = capture(a.archive)
    need(
        A["file_sha"](a.base) == proof["base_sha256"]
        and A["file_sha"](a.cpu) == proof["original_cpu_sha256"],
        "C269 DSOs",
    )
    base = ct.CDLL(str(a.base), mode=ct.RTLD_GLOBAL)
    cpu = ct.CDLL(str(a.cpu))
    bind(cpu, "ggml_cpu_init", [])()
    traits = bind(cpu, "ggml_get_type_traits_cpu", [ct.c_int], ct.POINTER(A["Traits"]))
    quant = bind(cpu, "quantize_row_q8_0", [Ptr, Ptr, ct.c_int64])
    dot = bind(
        cpu,
        "ggml_vec_dot_mxfp4_q8_0",
        [ct.c_int, Ptr, ct.c_size_t, Ptr, ct.c_size_t, Ptr, ct.c_size_t, ct.c_int],
    )
    deq = bind(base, "dequantize_row_q8_0", [Ptr, Ptr, ct.c_int64])
    need(
        traits(39).contents.vec_dot == ct.cast(dot, Ptr).value
        and traits(39).contents.vec_dot_type == 8
        and traits(8).contents.from_float == ct.cast(quant, Ptr).value,
        "registered functions",
    )
    need(A["file_sha"](a.derived / "receipt.json") == A["OLD"]["C291"], "C291 constructor")
    placement = receipt(a.derived / "receipt.json")
    index = a.derived / "integral-index.json"
    need(A["file_sha"](index) == placement["index_sha256"], "slab index")
    (expert,) = [e for e in receipt(index)["experts"] if (e["layer"], e["expert"]) == (0, 28)]
    components = {v["name"]: v for v in expert["components"]}
    libraries = {}
    for name, b in proof["builds"].items():
        path = a.binaries / (name + ".so")
        need(A["file_sha"](path) == b["elf_sha256"], "external " + name)
        libraries[name] = bind(
            ct.CDLL(str(path)), "gemv_mxfp4_f32_direct", [Ptr, Ptr, Ptr, ct.c_uint32, ct.c_uint32]
        )
    summaries = {}
    stages = {}

    def identity(fd):
        s = os.fstat(fd)
        return dict(
            dev=s.st_dev,
            inode=s.st_ino,
            size_bytes=s.st_size,
            mtime_ns=s.st_mtime_ns,
            ctime_ns=s.st_ctime_ns,
        )

    with Path(placement["model_path"]).open("rb", buffering=0) as gguf:
        need(identity(gguf.fileno()) == placement["model_stat"], "original descriptor")
        for stage in PROJECTIONS:
            c = components[f"blk.0.ffn_{stage}_exps.weight"]
            require_size = N * STRIDE
            need(c["type"] == "mxfp4" and c["size_bytes"] == require_size, "slab geometry")
            data = os.pread(gguf.fileno(), require_size, c["source_offset"])
            need(len(data) == require_size and sha(data) == c["sha256"], "complete slab " + stage)
            mat = (ct.c_uint8 * require_size).from_buffer_copy(data)
            x = Vec.from_buffer_copy(src[stage])
            need(all(math.isfinite(v) for v in x), "finite input " + stage)
            qb = Bits()
            quant(x, qb, N)
            need(
                bytes(qb) == OPERANDS["ARITH"]["quantize"](src[stage])
                and (stage != "down" or bytes(qb) == downq),
                "physical and mathematical Q8_0",
            )
            ref = Vec()
            for i in range(N):
                dot(N, ct.byref(ref, i * 4), 0, ct.byref(mat, i * STRIDE), 0, qb, 0, 1)
            need(
                bytes(ref) == bytes(gold[stage]),
                "independent recorded actual pre-bias row " + stage,
            )
            stages[stage] = (mat, x, qb)
            summaries[stage] = dict(
                activation_sha256=sha(src[stage]),
                q8_sha256=sha(bytes(qb)),
                weight_sha256=sha(data),
                captured_sha256=sha(bytes(ref)),
                rows=N,
                builds={},
            )
        need(identity(gguf.fileno()) == placement["model_stat"], "unchanged descriptor")
    # Authenticate every recorded projection before scoring the external engine.
    for stage, (mat, x, qb) in stages.items():
        qx = Vec()
        deq(qb, qx, N)
        for name, gemv in libraries.items():
            result = {}
            for label, vector in (("layout", x), ("layout_and_q8", qx)):
                output = Vec()
                gemv(mat, A["reorder"](vector), output, N, N)
                result[label] = A["difference"](gold[stage], output)
            summaries[stage]["builds"][name] = result
    mismatches = {
        variant: sum(
            rows["builds"][name][variant]["different_bits"]
            for rows in summaries.values()
            for name in libraries
        )
        for variant in ("layout", "layout_and_q8")
    }
    return dict(
        status="MEASURED_REAL_ROUTED_PROJECTIONS",
        decision={
            k: "NO_GO_EXACT_DROP_IN_AT_OBSERVED_RANK" if v else "GO_FULL_RANK_FIXTURE"
            for k, v in mismatches.items()
        },
        observed_position=189,
        layer=0,
        expert=28,
        slot=3,
        generation=6,
        stages=summaries,
        logical_gguf_bytes=3 * N * STRIDE,
        model_sha256=placement["model_sha256"],
        upstream=proof["external_commit"],
        manifests=OPERANDS["MANIFESTS"],
        program_sha256=A["file_sha"](HERE / "run.py"),
        protocol_sha256=A["file_sha"](HERE / "protocol.md"),
        gpu_forwards=0,
        model_forwards=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "derived", "binaries", "base", "cpu", "new-output-dir"):
        parser.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    start = time.monotonic()
    try:
        cg = A["scope"]()
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
        need(
            not subprocess.check_output(["git", "status", "--porcelain"], cwd=HERE),
            "clean rank source",
        )
        save(
            a.new_output_dir / "provenance.json",
            dict(commit=head, protocol_sha256=A["file_sha"](HERE / "protocol.md"), scope=cg.name),
        )
        out = run(a)
        events = dict(r.split() for r in (cg / "memory.events").read_text().splitlines())
        need(
            time.monotonic() - start <= 60
            and (cg / "memory.swap.current").read_text().strip() == "0"
            and int(events["oom"]) == int(events["oom_kill"]) == 0,
            "resource envelope",
        )
        save(
            a.new_output_dir / "resources.json",
            dict(
                elapsed_s=time.monotonic() - start,
                peak_bytes=int((cg / "memory.peak").read_text()),
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                cap_bytes=512 << 20,
                swap_bytes=0,
            ),
        )
    except Exception as exc:
        save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    save(a.new_output_dir / "decision.json", out)
    print(out["decision"])
