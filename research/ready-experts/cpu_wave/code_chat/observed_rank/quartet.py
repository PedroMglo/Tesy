"""Measure first useful rows and drain of the same real four-reader CPU quartet."""

import argparse
import ctypes as ct
import json
import mmap
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
S = run_path(HERE / "stripe.py")
A, R, need, read, save = S["A"], S["RANK"], S["need"], S["A"]["receipt"], S["save"]
sha, file_sha = S["sha"], A["file_sha"]
PAIR = HERE.parents[3] / "qualification-retake/nvme_admission/io_pair"
N, ROWS, STRIDE = S["N"], S["ROWS"], S["STRIDE"]
ORDER = ["FLE"] * 4 + ["ELF"] * 3


def outcome(arms):
    need("".join(a["mode"] for a in arms) == "".join(ORDER), "mirrored groups")
    pairs = []
    for i in range(3, len(arms), 3):
        rows = {a["mode"]: a for a in arms[i : i + 3]}
        pairs.append(
            {
                ctl: {k: rows[ctl][k] - rows["E"][k] for k in ("all_ready_ns", "join_ns")}
                for ctl in ("F", "L")
            }
        )
    blocks = [
        {
            ctl: {k: median(p[ctl][k] for p in group) for k in ("all_ready_ns", "join_ns")}
            for ctl in ("F", "L")
        }
        for group in (pairs[:3], pairs[3:])
    ]
    ready = all(b[c]["all_ready_ns"] > 0 for b in blocks for c in ("F", "L"))
    drained = all(b[c]["join_ns"] > 0 for b in blocks for c in ("F", "L"))
    loss = all(b["F"]["join_ns"] < 0 for b in blocks)
    result = (
        "GO_SUCCESSOR_FIXTURE"
        if ready and drained
        else "NO_GO_ISOLATED_DRAIN"
        if ready and loss
        else "INCONCLUSIVE"
    )
    return dict(pairs=pairs, median_ns=blocks, decision=result)


def native(a, reference):
    need(
        file_sha(a.cpu) == reference["original_cpu_sha256"]
        and file_sha(a.base) == reference["base_sha256"],
        "C269 files",
    )
    base = ct.CDLL(str(a.base), mode=ct.RTLD_GLOBAL)
    cpu = ct.CDLL(str(a.cpu))
    bind, ptr = A["bind"], A["Ptr"]
    bind(cpu, "ggml_cpu_init", [])()
    quant = bind(cpu, "quantize_row_q8_0", [ptr, ptr, ct.c_int64])
    dot = bind(
        cpu,
        "ggml_vec_dot_mxfp4_q8_0",
        [ct.c_int, ptr, ct.c_size_t, ptr, ct.c_size_t, ptr, ct.c_size_t, ct.c_int],
    )
    traits = bind(cpu, "ggml_get_type_traits_cpu", [ct.c_int], ct.POINTER(A["Traits"]))
    need(
        base
        and traits(39).contents.vec_dot == ct.cast(dot, ptr).value
        and traits(39).contents.vec_dot_type == 8
        and traits(8).contents.from_float == ct.cast(quant, ptr).value,
        "registered operations",
    )
    src, _, _ = R["capture"](a.archive)
    qb = A["Bits"]()
    quant(S["Vec"].from_buffer_copy(src["gate"]), qb, N)
    return dot, qb


def work(a, proof, pack):
    index = a.derived / "integral-index.json"
    need(file_sha(index) == pack["index_sha256"], "index")
    entries = [e for e in read(index)["experts"] if e["layer"] == 0]
    anchor = R["OPERANDS"]["Archive"](a.archive, 86)
    root = R["OPERANDS"]["RANK"] + "/"
    ranks = json.loads(anchor.read(root + "rank.json"))
    route = ranks["logical"]
    need(
        route == [28, 24, 8, 16]
        and ranks["physical"] == [3, 14, 6, 35]
        and ranks["generations"] == [6, 6, 5, 4],
        "routed quartet",
    )
    gold = {}
    for k in ("gate", "up"):
        data = anchor.read(root + k + ".f32")
        need(
            sha(data) == ranks["files_sha256"][k + ".f32"] and len(data) == 4 * N * 4,
            "recorded projection",
        )
        gold[k] = [data[4 * i * N : 4 * (i * N + ROWS)] for i in range(4)]
    jobs = []
    for r, e in enumerate(route):
        (entry,) = [v for v in entries if v["expert"] == e]
        comp = {
            k: next(c for c in entry["components"] if c["name"] == f"blk.0.ffn_{k}_exps.weight")
            for k in ("gate", "down", "up")
        }
        need(
            all(
                comp[k]["packed_relative_offset"] == i * N * STRIDE
                and comp[k]["size_bytes"] == N * STRIDE
                for i, k in enumerate(comp)
            )
            and entry["pack_offset"] % S["PAGE"] == 0,
            "actual geometry",
        )
        jobs.append((entry["pack_offset"], comp, {k: gold[k][r] for k in gold}))
    need(
        proof["arms"]["partial"]["spans"]
        == [[0, 49152], [8810496, 8863744], [49152, 8810496], [8863744, 13221888]],
        "verified partial plan",
    )
    return jobs


def trial(pool, fd, buffers, jobs, qb, dot, mode, plan):
    begin = []
    barrier = threading.Barrier(5, action=lambda: begin.append(time.monotonic_ns()), timeout=5)

    def worker(i):
        base, comp, _ = jobs[i]
        buf = buffers[i]
        spans = plan["complete" if mode == "F" else "partial"]["spans"]
        first = 2 if mode == "E" else len(spans)
        values = [(ct.c_float * ROWS)() for _ in range(2)]
        stamps = []
        barrier.wait()
        for n, (lo, hi) in enumerate(spans, 1):
            with memoryview(buf)[lo:hi] as part:
                need(os.preadv(fd, [part], base + lo) == hi - lo, "short direct read")
            if n == first:
                for v, k in zip(values, ("gate", "up"), strict=True):
                    off = comp[k]["packed_relative_offset"]
                    for j in range(ROWS):
                        w = ct.c_ubyte.from_buffer(buf, off + j * STRIDE)
                        dot(N, ct.byref(v, 4 * j), 0, ct.byref(w), 0, qb, 0, 1)
                        del w
                stamps.append(time.monotonic_ns())
        return stamps[0], time.monotonic_ns(), [bytes(v) for v in values]

    futures = [pool.submit(worker, i) for i in range(4)]
    barrier.wait()
    result = [f.result(timeout=10) for f in futures]
    joined = time.monotonic_ns()
    for i, (_, _, vs) in enumerate(result):
        _, comp, gold = jobs[i]
        need(vs == [gold["gate"], gold["up"]], "complete rank outputs")
        for c in comp.values():
            off = c["packed_relative_offset"]
            with memoryview(buffers[i])[off : off + c["size_bytes"]] as payload:
                need(sha(payload) == c["sha256"], "full matrix at drain")
    ready = [t - begin[0] for t, _, _ in result]
    done = [t - begin[0] for _, t, _ in result]
    join = joined - begin[0]
    need(all(0 < x <= y <= join for x, y in zip(ready, done, strict=True)), "worker clocks")
    return dict(
        mode=mode,
        ready_ns=ready,
        done_ns=done,
        first_ready_ns=min(ready),
        all_ready_ns=max(ready),
        join_ns=join,
    )


def measure(a, out):
    sys.path.insert(0, str(PAIR))
    g = run_path(PAIR / "run.py")
    need(file_sha(a.c55 / "receipt.json") == a.c55_sha256, "C55 seal")
    window = read(a.c55 / "receipt.json")
    policyfile = a.c55 / "resource-policy.json"
    policy = read(policyfile)
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(
        window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and window["span_s"] >= 60
        and 0 <= age <= 3600
        and file_sha(policyfile) == window["canonical_policy_sha256"]
        and policy == g["derive_policy"](snapshot=policy["snapshot"])
        and g["operational_session_ready"](policy)[0],
        "active C55 hardware window",
    )
    head, tree = [
        subprocess.check_output(["git", "rev-parse", k], cwd=HERE, text=True).strip()
        for k in ("HEAD", "HEAD^{tree}")
    ]
    need(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=HERE),
        "clean physical source",
    )
    need(
        file_sha(HERE / "stripe-result.json")
        == "2607984a2c4f0663206930227af3caea6c483cd7be368f071ec570c3e1dd5ee3"
        and file_sha(a.derived / "receipt.json") == A["OLD"]["C291"],
        "preceding gate and pack",
    )
    proof = read(HERE / "stripe-result.json")
    pack = read(a.derived / "receipt.json")
    args = dict(
        commit=head,
        tree=tree,
        host=os.uname().nodename,
        kernel=os.uname().release,
        protocol_sha256=file_sha(HERE / "quartet-protocol.md"),
        program_sha256=file_sha(HERE / "quartet.py"),
        c55_sha256=a.c55_sha256,
        c55_age_s=age,
        model_sha256=pack["model_sha256"],
        pack_sha256=pack["pack_sha256"],
        index_sha256=pack["index_sha256"],
        profile=dict(
            cpu=window["cpu"],
            gpu=window["gpu_name"],
            driver=window["gpu_driver"],
            total_vram_mib=window["gpu_total_mib"],
            power=window["power"]["source"],
            filesystem=window["model_fs"],
        ),
    )
    save(out / "provenance.json", args)
    dot, qb = native(a, read(HERE.parent / "activation/result.json"))
    jobs = work(a, proof, pack)
    plan = proof["arms"]
    size = plan["complete"]["total_requested_bytes"]
    start = time.monotonic()
    arms = []

    def guard():
        sample = g["monitor"](policy)
        with (out / "samples.jsonl").open("a") as f:
            f.write(json.dumps(sample, allow_nan=False) + "\n")
        need(time.monotonic() - start < 160, "family deadline")

    guard()
    device = g["disk"](Path(pack["pack_path"]), "nvme")
    fd = os.open(pack["pack_path"], os.O_RDONLY | os.O_DIRECT | os.O_CLOEXEC)
    try:
        need(S["identity"](fd) == pack["pack_stat"], "NVMe descriptor")
        with ExitStack() as stack:
            bufs = [stack.enter_context(mmap.mmap(-1, size)) for _ in range(4)]
            for buf in bufs:
                for i in range(0, size, S["PAGE"]):
                    buf[i] = 0
            pool = stack.enter_context(ThreadPoolExecutor(max_workers=4))
            initial = g["diskstats"](device)
            for order in ORDER:
                guard()
                for m in order:
                    row = trial(pool, fd, bufs, jobs, qb, dot, m, plan)
                    arms.append(row)
                    with (out / "arms.jsonl").open("a") as f:
                        f.write(json.dumps(row) + "\n")
            final = g["diskstats"](device)
        need(S["identity"](fd) == pack["pack_stat"], "same pack after drain")
    finally:
        os.close(fd)
    guard()
    return dict(
        **args,
        **outcome(arms),
        status="MEASURED_QUARTET_PREFIX_SERVICE",
        arms=arms,
        requested_bytes=4 * len(arms) * size,
        checked_full_slabs=4 * 3 * len(arms),
        matched_prefix_f32=4 * 2 * ROWS * len(arms),
        elapsed_s=time.monotonic() - start,
        peak_cgroup_bytes=g["scope"](),
        swap_bytes=0,
        model_forwards=0,
        gpu_compute=0,
        whole_device_delta={k: final[k] - initial[k] for k in final},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("derived", "archive", "base", "cpu", "c55", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--c55-sha256", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = measure(a, a.new_output_dir)
        save(a.new_output_dir / "receipt.json", result)
    except Exception as exc:
        save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    print(result["decision"], result["median_ns"])
