"""Exercise a seven-reservation prefill queue with the real NVMe pack and C269 CPU slot SETs."""

import argparse
import ctypes as ct
import hashlib
import importlib.util
import json
import mmap
import os
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(HERE / "selection.py")
P, SRC, need, W, SLAB = (S[k] for k in ("P", "SRC", "need", "W", "SLAB"))
save, sha = P["save"], P["sha"]
CAP, STOP = 1 << 30, 896 << 20
CPU = "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313"
BASE = "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539"


class Params(ct.Structure):
    _fields_ = [("size", ct.c_size_t), ("buffer", ct.c_void_p), ("no_alloc", ct.c_bool)]


def bind(provider, name, args, ret):
    function = getattr(provider, name)
    function.argtypes, function.restype = args, ret
    return function


class Store:
    def __init__(self, libs, life):
        bp, cp = (libs / name for name in ("libggml-base.so.0.15.3", "libggml-cpu.so.0.15.3"))
        need(sha(bp) == BASE and sha(cp) == CPU, "C269 active providers")
        base, cpu_lib = ct.CDLL(str(bp), mode=ct.RTLD_GLOBAL), ct.CDLL(str(cp))
        ptr, sz = ct.c_void_p, ct.c_size_t
        need(
            bind(base, "ggml_type_name", [ct.c_int], ct.c_char_p)(39) == b"mxfp4", "GGML MXFP4 type"
        )
        ctx = bind(base, "ggml_init", [Params], ptr)(Params(1 << 20, None, True))
        need(ctx, "GGML metadata")
        life.callback(bind(base, "ggml_free", [ptr], None), ctx)
        cpu = bind(cpu_lib, "ggml_backend_cpu_init", [], ptr)()
        need(cpu, "GGML CPU")
        life.callback(bind(base, "ggml_backend_free", [ptr], None), cpu)
        new = bind(
            base, "ggml_new_tensor_3d", [ptr, ct.c_int, ct.c_int64, ct.c_int64, ct.c_int64], ptr
        )
        self.ts = [new(ctx, 39, 2880, 2880, 40) for _ in range(3)]
        mem = bind(base, "ggml_backend_alloc_ctx_tensors", [ptr, ptr], ptr)(ctx, cpu)
        need(mem, "40-slot allocation")
        life.callback(bind(base, "ggml_backend_buffer_free", [ptr], None), mem)
        size = bind(base, "ggml_nbytes", [ptr], sz)
        self.storage_bytes = bind(base, "ggml_backend_buffer_get_size", [ptr], sz)(mem)
        need(
            all(size(t) == 40 * SLAB for t in self.ts) and self.storage_bytes >= 120 * SLAB,
            "native extent",
        )
        data = bind(base, "ggml_get_data", [ptr], ptr)
        self.bases = [data(t) for t in self.ts]
        need(all(self.bases), "tensor buffers")
        self.set = bind(base, "ggml_backend_tensor_set", [ptr, ptr, sz, sz], None)

    def copy(self, source, record):
        spans = []
        for i, t in enumerate(self.ts):
            start = time.monotonic_ns()
            self.set(t, source + i * SLAB, record["slot"] * SLAB, SLAB)
            spans.append([start, time.monotonic_ns()])
        return spans

    def poison(self, records):
        for r in records:
            for base in self.bases:
                ct.memset(base + r["slot"] * SLAB, 0, SLAB)

    def verify(self, records):
        for r in records.values():
            for base, wanted in zip(self.bases, r["matrices"], strict=True):
                data = (ct.c_ubyte * SLAB).from_address(base + r["slot"] * SLAB)
                need(
                    hashlib.sha256(data).hexdigest() == wanted, "original matrix in final CPU slot"
                )


def remap(pins, states, routes):
    phys = {}
    for _, slot, gen, expert in pins:
        need(states[slot] == (expert, gen, True), "pin generation not ready")
        phys[expert] = slot
    return [[phys.get(e, -1) for e in rank] for rank in routes]


def trial(fd, pool, buffers, gap, extra, store, selection, records, mode):
    order = [k[3] for k in selection["fifo"]]
    promoted = [order[0], order[3], *order[1:3], *order[4:]]
    ids = order if mode == "F" else promoted
    jobs = deque(
        [(i,) for i in ids] if mode in "FP" else [tuple(ids[:2]), *((i,) for i in ids[2:])]
    )
    states = {r["slot"]: (e, r["generation"], e not in order) for e, r in records.items()}
    store.poison(records[i] for i in order)
    cv = threading.Condition()
    start = []
    launch = threading.Barrier(5, action=lambda: start.append(time.monotonic_ns()), timeout=8)
    accepted, reads, publications, errors = [], [], {}, []

    def direct(worker, group, destinations):
        begin = time.monotonic_ns()
        n = os.preadv(fd, destinations, records[group[0]]["offset"])
        end = time.monotonic_ns()
        need(n == sum(map(len, destinations)), "short O_DIRECT read")
        with cv:
            reads.append(dict(worker=worker, ids=group, begin=begin, end=end, bytes=n))

    def publish(worker, expert, buf):
        source = ct.addressof(ct.c_char.from_buffer(buf))
        record = records[expert]
        copies = store.copy(source, record)
        with cv:
            slot, gen = record["slot"], record["generation"]
            need(
                states[slot] == (expert, gen, False) and expert not in publications,
                "publication epoch",
            )
            states[slot] = (expert, gen, True)
            publications[expert] = dict(
                worker=worker, slot=slot, gen=gen, sets=copies, at=time.monotonic_ns()
            )
            cv.notify_all()

    def worker(i):
        try:
            launch.wait()
            while True:
                with cv:
                    if errors or not jobs:
                        break
                    group = jobs.popleft()
                    accepted.append(dict(worker=i, ids=group, at=time.monotonic_ns()))
                if mode == "M" and len(group) == 2:
                    direct(i, group, [buffers[i], gap, extra])
                    publish(i, group[0], buffers[i])
                    publish(i, group[1], extra)
                else:
                    for e in group:
                        direct(i, (e,), [buffers[i]])
                        publish(i, e, buffers[i])
            return time.monotonic_ns()
        except BaseException as exc:
            with cv:
                errors.append(repr(exc))
                cv.notify_all()
            raise

    futures = [pool.submit(worker, i) for i in range(4)]
    launch.wait()
    with cv:
        need(
            cv.wait_for(lambda: len(publications) == len(order) or errors, timeout=12),
            "barrier timeout",
        )
        need(not errors, "worker failure " + str(errors))
        resumed = time.monotonic_ns()
        resolved = remap(selection["pins"], states, selection["ranks"])
    returned = time.monotonic_ns()
    worker_ends = [f.result(timeout=8) for f in futures]
    drained = time.monotonic_ns()
    need(resolved == selection["remap"], "target logical/physical mapping")
    store.verify(records)
    return dict(
        mode=mode,
        start=start[0],
        accepted=accepted,
        reads=reads,
        published=publications,
        resumed=resumed,
        returned=returned,
        drained=drained,
        worker_ends=worker_ends,
        checked_matrix_hashes=48,
        remap_values=sum(map(len, resolved)),
    )


def host(a):
    sys.path.insert(0, str(P["PAIR"]))
    spec = importlib.util.spec_from_file_location("tesy_queue_guard", P["PAIR"] / "run.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    g.CAP, g.STOPS = CAP, STOP
    w = SRC["pinned"](a.c55 / "receipt.json", a.c55_sha256)
    policy = SRC["pinned"](a.c55 / "resource-policy.json", w["canonical_policy_sha256"])
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(
        w["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not w["reason"]
        and 0 <= age <= 3600
        and w["span_s"] >= 60
        and g.derive_policy(snapshot=policy["snapshot"]) == policy
        and g.operational_session_ready(policy)[0],
        "C55",
    )
    g.scope()
    return g, w, policy, age


def measure(a):
    need(not subprocess.check_output(["git", "status", "--porcelain"], cwd=HERE), "dirty source")
    commit, tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD", "HEAD^{tree}"], cwd=HERE, text=True
    ).split()
    g, w, policy, age = host(a)
    selection, journals, records, pack = S["plan"](a.archive, a.derived)
    proof = dict(
        commit=commit,
        tree=tree,
        protocol_sha256=sha(HERE / "protocol.md"),
        programs={name: sha(HERE / name) for name in ("run.py", "selection.py", "grade.py")},
        providers=dict(cpu=CPU, base=BASE),
        model_sha256=pack["model_sha256"],
        pack_sha256=pack["pack_sha256"],
        index_sha256=pack["index_sha256"],
        c55_sha256=a.c55_sha256,
        c55_age_s=age,
        host=os.uname().nodename,
        kernel=os.uname().release,
        cpu=w["cpu"],
        gpu=w["gpu_name"],
        driver=w["gpu_driver"],
        filesystem=w["model_fs"],
        selection=selection,
        journals=journals,
        records=records,
    )
    save(a.new_output_dir / "provenance.json", proof)
    start = time.monotonic()

    def guard():
        obs = g.monitor(policy)
        with (a.new_output_dir / "samples.jsonl").open("a") as f:
            f.write(json.dumps(obs, allow_nan=False) + "\n")
        need(time.monotonic() - start < 175, "time budget")

    guard()
    while time.monotonic() - start < 60:
        time.sleep(min(1, max(0, 60 - (time.monotonic() - start))))
        guard()
    device = g.disk(Path(pack["pack_path"]), "nvme")
    with ExitStack() as life:
        fd = os.open(pack["pack_path"], os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECT)
        life.callback(os.close, fd)
        need(P["identity"](fd) == pack["pack_stat"], "internal pack inode")
        store = Store(a.libs, life)

        def buffer(size):
            buf = life.enter_context(mmap.mmap(-1, size))
            for i in range(0, size, 4096):
                buf[i] = 0
            return buf

        bufs = [buffer(W) for _ in range(4)]
        extra, gap = buffer(W), buffer(36864)
        initial = g.diskstats(device)
        cold = {k[3] for k in selection["fifo"]}
        for expert, r in records.items():
            if expert not in cold:
                need(os.preadv(fd, [bufs[0]], r["offset"]) == W, "resident setup")
                store.copy(ct.addressof(ct.c_char.from_buffer(bufs[0])), r)
        states = {r["slot"]: (e, r["generation"], True) for e, r in records.items()}
        wrong = dict(states)
        _, slot, gen, e = selection["fifo"][0]
        wrong[slot] = (e, gen - 1, True)
        try:
            remap(selection["pins"], wrong, selection["ranks"])
        except ValueError as exc:
            need(str(exc) == "pin generation not ready", "wrong negative control")
        else:
            raise ValueError("stale generation survived")
        before = g.diskstats(device)
        pool = life.enter_context(ThreadPoolExecutor(max_workers=4))
        arms = []
        design = [(-1, -1, "FPSM")] + [
            (b, i, "FPSM" if b == 0 else "MSPF") for b in (0, 1) for i in range(5)
        ]
        for b, rep, order in design:
            guard()
            for mode in order:
                row = trial(fd, pool, bufs, gap, extra, store, selection, records, mode)
                row.update(block=b, rep=rep)
                arms.append(row)
                with (a.new_output_dir / "arms.jsonl").open("a") as f:
                    f.write(json.dumps(row, allow_nan=False) + "\n")
        after = g.diskstats(device)
        need(P["identity"](fd) == pack["pack_stat"], "final inode")
    guard()
    # JSON keys are strings on disk; apply the independent reviewer to the actual serialization.
    stored = [
        json.loads(line) for line in (a.new_output_dir / "arms.jsonl").read_bytes().splitlines()
    ]
    graded = run_path(HERE / "grade.py")["grade"](stored, selection)
    total = (len(records) - len(cold)) * W + graded["requested_bytes"]
    need(total <= 9 * (1 << 29), "logical read cap")
    return dict(
        **proof,
        status="MEASURED",
        result=graded,
        requested_with_setup=total,
        elapsed_s=time.monotonic() - start,
        peak_bytes=g.scope(),
        swap_bytes=0,
        storage_bytes=store.storage_bytes,
        model_forwards=0,
        gpu_compute=0,
        device_delta_setup={k: before[k] - initial[k] for k in initial},
        device_delta_arms={k: after[k] - before[k] for k in before},
        mutant_rejected=True,
        arms_sha256=sha(a.new_output_dir / "arms.jsonl"),
        samples_sha256=sha(a.new_output_dir / "samples.jsonl"),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for n in ("archive", "derived", "libs", "c55", "new-output-dir"):
        ap.add_argument("--" + n, type=Path, required=True)
    ap.add_argument("--c55-sha256", required=True)
    args = ap.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    try:
        result = measure(args)
    except Exception as exc:
        save(args.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
    save(args.new_output_dir / "receipt.json", result)
    print(result["result"]["merged"], result["result"]["promotion"])
