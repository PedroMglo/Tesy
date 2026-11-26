"""Price fixed cross-matrix coding on the same causal CPU cache trajectory."""

import argparse
import json
import os
import resource
import signal
import subprocess
from collections import Counter
from fractions import Fraction
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
cost = run_path(HERE.parent / "prices.py")
LRU_DIR = cost["NAT"] / "global_residency/causal"
lru = run_path(LRU_DIR / "screen.py")
base = lru["base"]
need, pinned, sha = lru["check"], lru["pinned"], lru["sha"]
W = cost["WINDOW"]
CODEC = "58703cbf3ea6ee5807f39fae8d1d54b50b73810c5e16779743d32505afd292ca"
LRU = "ba87a65b92fa4f16e9b1ec44d4b4321a74f8eb070789a42b7d16e445607a173b"
NS = 10**9


def decode_callbacks(groups, events, marks, plan):
    callbacks = []
    for group, (miss, _), (reads, common_set), g in zip(groups, events, marks, plan, strict=True):
        layer = group["site"][2]
        if layer < 25:
            # Missing duration is kept distinct from a known zero-cost read.
            jobs = [(k, reads.get(k), 0) for k in miss]
        else:
            jobs = []
            for j in g["jobs"]:
                key = 128 * layer + j["expert"]
                need((key in reads) == (j["source"] == "disk"), "CUDA read source")
                jobs.append((key, reads.get(key, 0), j["r0_same_site_set_ns"] or 0))
            need(max((r + s for _, r, s in jobs), default=0) == common_set, "CUDA SET chains")
        callbacks.append(jobs)
    return callbacks


def service(callbacks, sizes):
    total = cost["OUTSIDE"] * W
    uncertain_groups = []
    unknown = 0
    for jobs in callbacks:
        charged = max((r * sizes(k) + s * W for k, r, s in jobs if r is not None), default=0)
        total += charged
        missing = sum(r is None for _, r, _ in jobs)
        if missing:
            unknown += missing
            uncertain_groups.append(charged)
    return total, uncertain_groups, unknown


def crossed(prefill, decode, uncertain, gap):
    joint_limit = (cost["BUDGET"] - gap) * W - prefill
    six_limit = Fraction(47 * NS * W, 6)
    budget = lru["unknown_budget"](uncertain, decode, int(min(joint_limit, six_limit)))
    threshold = budget["max_uniform_ns"]  # The solver operated in ns times W.
    return dict(
        joint_margin_ns_floor=(joint_limit - decode) // W,
        six_margin_ns_floor=(six_limit - decode) // W,
        new_read_uniform_effective_ns_max=None if threshold is None else threshold // W,
        status=budget["status"],
    )


def analyse(archive):
    codec = pinned(HERE.parent / "evidence/receipt.json", CODEC)
    experts = pinned(HERE.parent / "evidence/experts.json", codec["experts_sha256"])
    sample = {128 * e["layer"] + e["expert"]: e["aligned_bytes_floor"] for e in experts}
    best = min(sample.values())
    need(len(sample) == 64 and best == codec["sample"]["best_aligned_bytes"], "sample population")
    ref = pinned(LRU_DIR / "evidence/receipt.json", LRU)["arms"]["U1262"]
    pri, bank, ages, now, _ = lru["start_clock"](archive)
    groups, p, b, _, physical, _, joint, fixed, _ = base["inputs"](archive)
    need(pri == p and bank == b, "initial backing")
    events, states = lru["simulate"](groups, pri, bank, ages, now, "U1262")
    need(states == ref["states"] and base["summarize"](groups, events) == ref["phase_work"], "LRU")
    plan = pinned(
        archive / "part-65/tesy-decode-transport-prepare-20261125-r01/plan.json", cost["DECODE"]
    )["groups"]
    split = len(groups) - len(plan)
    population = {"prefill": Counter(), "decode": Counter()}
    for g, (miss, _) in zip(groups, events, strict=True):
        population["decode" if g["phase"] == "decode" else "prefill"].update(
            miss if g["site"][2] < 25 else g["logical_disk"]
        )
    need([c.total() for c in population.values()] == [1048, 918], "transport population")
    cases = {}
    for order, marks in physical.items():
        callbacks = decode_callbacks(groups[split:], events[split:], marks, plan)
        for mode, sizes in (
            ("raw", lambda k: W),
            ("sample_only", lambda k: sample.get(k, W)),
            ("uniform_best", lambda k: best),
        ):
            decode, uncertain, unknown = service(callbacks, sizes)
            need(len(uncertain) == 222 and unknown == 254, "unpriced CPU sites")
            size_sum = sum(n * sizes(k) for k, n in population["prefill"].items())
            for pre_order, arm in joint["arms"].items():
                tag = pre_order + "_" + order
                prefill = Fraction(arm["P"]["service_ns"] * size_sum, 1058)
                out = cases.setdefault(mode, {}).setdefault(tag, {})
                for label, gap in (
                    ("serial", fixed["gaps"]["total_ns"]),
                    ("pipeline", fixed["gaps"]["protected_ns"]),
                    ("zero", 0),
                ):
                    out[label] = crossed(prefill, decode, uncertain, gap)
                    if mode == "raw":
                        need(
                            decode == ref["decode_prices"][order]["decode_witness_ns"] * W
                            and abs(
                                ref["conditional"][tag][label]["margin_ns"]
                                - out[label]["joint_margin_ns_floor"]
                            )
                            < 1,
                            "uncompressed causal reference",
                        )
    return dict(
        status="REPRODUCED_COMBINED_PRICE",
        cases=cases,
        sources={"codec": CODEC, "lru": LRU},
        coverage={
            phase: {
                "jobs": counts.total(),
                "sample_jobs": sum(counts[k] for k in sample),
                "keys": len(counts),
                "sample_keys": len(sample.keys() & counts.keys()),
            }
            for phase, counts in population.items()
        },
        cpu_unknown_jobs=unknown,
        cpu_unknown_callbacks=len(uncertain),
        best_size=best,
        model_forwards=0,
        weight_bytes_read=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
    signal.alarm(120)
    git = ["git", "-C", str(HERE), "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
    try:
        need(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty checkout")
        result = analyse(a.archive)
        result.update(
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            protocol_sha256=sha(HERE / "protocol.md"),
            program_sha256=sha(Path(__file__)),
        )
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
