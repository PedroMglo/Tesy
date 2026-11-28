"""Measure concurrent, serial and coalesced O_DIRECT service of two real adjacent experts."""

import argparse
import hashlib
import json
import mmap
import os
import subprocess
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
B = run_path(HERE / "batch.py")
SRC, need = B["SRC"], B["need"]
PAIR = HERE.parents[2] / "qualification-retake/nvme_admission/io_pair"
PACK = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
WINDOW, SLAB = 13221888, 4406400
PHASES = ("prefill", "decode")
ORDER = ("DSM", "MSD")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def save(path, data):
    with path.open("x") as f:
        json.dump(data, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def select(waves):
    demand = defaultdict(set)
    for w in waves:
        demand[w.site[:3]].update(w.demands)
    chosen = {}
    for w in waves:
        call = w.site[0]
        if not 2 <= call <= 46:
            continue
        phase = PHASES[int(call > 2)]
        ids = {k[3]: k for k in w.reserved & demand[w.site[:3]]}
        adjacent = sorted(i for i in ids if i + 1 in ids)
        if phase not in chosen and adjacent:
            n = adjacent[0]
            chosen[phase] = dict(site=list(w.site), keys=[list(ids[n]), list(ids[n + 1])])
    need(set(chosen) == set(PHASES), "both phases contain a jointly offered adjacent pair")
    return chosen


def plan(a):
    screen = B["SCREEN"]
    old = SRC["pinned"](
        screen["NATURAL"] / "prefill_retention/request_cost/receipt.json", screen["PRIOR"]
    )
    chosen = None
    sources = {}
    for label in ("P97", "P106"):
        _, auth = screen["read_arm"](a.archive, label, old[label])
        name, h, _ = SRC["SOURCES"][label]
        folder = a.archive / ("part-" + label[1:]) / name
        if label == "P97":
            rows, _ = SRC["T"]["PFJ"]["read_journal"](folder / "ON/raw/events.pfj")
        else:
            _, rows, _, _ = SRC["Q"]["read_new"](folder, h)
        waves, _ = SRC["timeline"](rows)
        selection = select(waves)
        need(chosen is None or chosen == selection, "capture selection or generations differ")
        chosen = selection
        sources[label] = auth["journal_sha256"]
        del rows, waves
    pack = SRC["pinned"](a.derived / "receipt.json", PACK)
    idx = SRC["pinned"](a.derived / "integral-index.json", pack["index_sha256"])
    need(idx["weight_window"] == WINDOW, "window")
    mapping = {(e["layer"], e["expert"]): e for e in idx["experts"]}
    for case in chosen.values():
        records = []
        for layer, _, _, expert in case["keys"]:
            record = mapping[layer, expert]
            parts = {c["name"]: c for c in record["components"]}
            matrices = []
            for i, k in enumerate(("gate", "down", "up")):
                c = parts[f"blk.{layer}.ffn_{k}_exps.weight"]
                need(
                    c["packed_relative_offset"] == i * SLAB and c["size_bytes"] == SLAB,
                    "matrix extent",
                )
                matrices.append(c["sha256"])
            records.append(dict(offset=record["pack_offset"], matrices=matrices))
        gap = records[1]["offset"] - records[0]["offset"] - WINDOW
        need(
            gap == 36864 and all(r["offset"] % 4096 == 0 for r in records),
            "adjacent packed records",
        )
        case.update(records=records, gap=gap)
    return chosen, sources, pack


def trial(fd, pool, bufs, gap, case, mode):
    stamps = []
    barrier = threading.Barrier(5, action=lambda: stamps.append(time.monotonic_ns()), timeout=5)
    offsets = [r["offset"] for r in case["records"]]

    def direct(parts, at):
        begin = time.monotonic_ns()
        need(os.preadv(fd, parts, at) == sum(map(len, parts)), "short direct read")
        return begin, time.monotonic_ns()

    def worker(i):
        barrier.wait()
        if mode == "D" and i < 2:
            return [direct([bufs[i]], offsets[i])]
        if mode == "S" and i == 0:
            return [direct([bufs[k]], at) for k, at in enumerate(offsets)]
        if mode == "M" and i == 0:
            return [direct([bufs[0], gap, bufs[1]], offsets[0])]
        return []

    # Poison one byte of every matrix outside the clock. Every arm must restore both records.
    for buf in bufs:
        for k in range(3):
            buf[k * SLAB] ^= 255
    futures = [pool.submit(worker, i) for i in range(4)]
    barrier.wait()
    clocks = [span for f in futures for span in f.result(timeout=10)]
    joined = time.monotonic_ns()
    for buf, r in zip(bufs, case["records"], strict=True):
        for i, wanted in enumerate(r["matrices"]):
            with memoryview(buf)[i * SLAB : (i + 1) * SLAB] as data:
                need(hashlib.sha256(data).hexdigest() == wanted, "original matrix at destination")
    start = stamps[0]
    need(all(start <= a < b <= joined for a, b in clocks), "worker chronology")
    return dict(
        mode=mode,
        reads_ns=[[a - start, b - start] for a, b in clocks],
        join_ns=joined - start,
        requested_bytes=2 * WINDOW + (len(gap) if mode == "M" else 0),
        verified_matrices=6,
    )


def grade(arms):
    need(len(arms) == 42, "two cases and seven triples each")
    design = [(-1, -1, case, mode) for case in PHASES for mode in "DSM"] + [
        (b, rep, case, mode)
        for b in (0, 1)
        for rep in range(3)
        for case in (PHASES if b == 0 else tuple(reversed(PHASES)))
        for mode in ORDER[b]
    ]
    times = {}
    for r, key in zip(arms, design, strict=True):
        b, rep, phase, mode = key
        spans = r["reads_ns"]
        need(
            (r["block"], r["rep"], r["case"], r["mode"]) == key
            and len(spans) == (1 if mode == "M" else 2)
            and all(0 <= a < z <= r["join_ns"] for a, z in spans)
            and (mode != "S" or spans[0][1] <= spans[1][0])
            and r["verified_matrices"] == 6
            and r["requested_bytes"] == 2 * WINDOW + (36864 if mode == "M" else 0),
            "design or bytes",
        )
        times[key] = r["join_ns"]
    result = {}
    for phase, threshold in zip(PHASES, (6950087, 4467682), strict=True):
        blocks = []
        for b in (0, 1):
            pairs = {
                k: [times[b, i, phase, k] - times[b, i, phase, "M"] for i in range(3)] for k in "DS"
            }
            blocks.append(
                dict(paired_ns=pairs, median_gain_ns={k: median(v) for k, v in pairs.items()})
            )
        gains = [b["median_gain_ns"]["D"] for b in blocks]
        good = all(min(b["median_gain_ns"].values()) > 0 for b in blocks)
        result[phase] = dict(
            blocks=blocks,
            decision="GO_COMPONENT" if good else "NO_GO" if max(gains) < 0 else "INCONCLUSIVE",
            required_ns=threshold,
            passes_price_both_orders=min(gains) >= threshold,
        )
    return result


def identity(fd):
    st = os.fstat(fd)
    return dict(
        dev=st.st_dev,
        inode=st.st_ino,
        size_bytes=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


def measure(a):
    sys.path.insert(0, str(PAIR))
    gate = run_path(PAIR / "run.py")
    window = SRC["pinned"](a.c55 / "receipt.json", a.c55_sha256)
    policy = SRC["pinned"](a.c55 / "resource-policy.json", window["canonical_policy_sha256"])
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(
        window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and window["span_s"] >= 60
        and 0 <= age <= 3600
        and policy == gate["derive_policy"](snapshot=policy["snapshot"])
        and gate["operational_session_ready"](policy)[0],
        "C55 qualification",
    )
    need(not subprocess.check_output(["git", "status", "--porcelain"], cwd=HERE), "dirty source")
    commit, tree = (
        subprocess.check_output(["git", "rev-parse", "HEAD", "HEAD^{tree}"], cwd=HERE, text=True)
        .strip()
        .splitlines()
    )
    gate["scope"]()
    chosen, sources, pack = plan(a)
    proof = dict(
        commit=commit,
        tree=tree,
        sources=sources,
        selection=chosen,
        pack_sha256=pack["pack_sha256"],
        model_sha256=pack["model_sha256"],
        index_sha256=pack["index_sha256"],
        program_sha256=sha(HERE / "pair.py"),
        protocol_sha256=sha(HERE / "pair-protocol.md"),
        c55_sha256=a.c55_sha256,
        c55_age_s=age,
        host=os.uname().nodename,
        kernel=os.uname().release,
        cpu=window["cpu"],
        gpu=window["gpu_name"],
        driver=window["gpu_driver"],
        filesystem=window["model_fs"],
    )
    out = a.new_output_dir
    save(out / "provenance.json", proof)

    def sample():
        obs = gate["monitor"](policy)
        with (out / "samples.jsonl").open("a") as f:
            f.write(json.dumps(obs, allow_nan=False) + "\n")

    start = time.monotonic()
    sample()
    while time.monotonic() - start < 60:
        time.sleep(min(1, max(0, 60 - (time.monotonic() - start))))
        sample()
    arms = []
    device = gate["disk"](Path(pack["pack_path"]), "nvme")
    fd = os.open(pack["pack_path"], os.O_RDONLY | os.O_DIRECT | os.O_CLOEXEC)
    try:
        need(identity(fd) == pack["pack_stat"], "pack identity before")
        with ExitStack() as stack:
            bufs = [stack.enter_context(mmap.mmap(-1, WINDOW)) for _ in range(2)]
            gap = stack.enter_context(mmap.mmap(-1, 36864))
            for buf in [*bufs, gap]:
                for i in range(0, len(buf), 4096):
                    buf[i] = 0
            pool = stack.enter_context(ThreadPoolExecutor(max_workers=4))
            before = gate["diskstats"](device)
            orders = [(-1, -1, PHASES, "DSM")] + [
                (b, i, PHASES if b == 0 else tuple(reversed(PHASES)), ORDER[b])
                for b in (0, 1)
                for i in range(3)
            ]
            for b, rep, phases, order in orders:
                sample()
                for phase in phases:
                    for m in order:
                        row = trial(fd, pool, bufs, gap, chosen[phase], m)
                        row.update(block=b, rep=rep, case=phase)
                        arms.append(row)
                        with (out / "arms.jsonl").open("a") as f:
                            f.write(json.dumps(row) + "\n")
            after = gate["diskstats"](device)
        need(identity(fd) == pack["pack_stat"], "pack identity after drain")
    finally:
        os.close(fd)
    sample()
    total = sum(r["requested_bytes"] for r in arms)
    need(total < 5 * (1 << 28) and time.monotonic() - start < 170, "I/O or time budget")
    return dict(
        **proof,
        status="MEASURED",
        arms=arms,
        cases=grade(arms),
        logical_bytes=total,
        elapsed_s=time.monotonic() - start,
        peak_cgroup_bytes=gate["scope"](),
        device_delta={k: after[k] - before[k] for k in after},
        model_forwards=0,
        gpu_compute=0,
        swap_bytes=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("archive", "derived", "c55", "new-output-dir"):
        p.add_argument("--" + n, required=True, type=Path)
    p.add_argument("--c55-sha256", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = measure(a)
    except Exception as exc:
        save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
    save(a.new_output_dir / "receipt.json", result)
    print({k: r["decision"] for k, r in result["cases"].items()})
