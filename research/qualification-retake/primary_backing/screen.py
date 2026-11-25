"""Bound demand-only primary backing from the exact historical decode entry."""

import argparse
import hashlib
import json
import math
import resource
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(UNIT))
import cache_boundary as boundary  # noqa: E402
from component_ready_bound.screen import Inconclusive, causal  # noqa: E402
from l2_critical import screen as critical  # noqa: E402
from warm_route_reference.verify import PROMPT, check_witness  # noqa: E402

require = boundary.require
c295 = critical.c295
PINS = {
    "cache-paid-evidence/receipt.json": (
        "80b22417608677f3d7316396068a319ac199056e15cdd0cae4e7447bd627c059"
    ),
    "l2_critical/evidence/receipt.json": (
        "b5640a5fd78cc28c6b1b708a7cf532526fe1190d5222c6ec64a678315bef1ca3"
    ),
    "component_ready_bound/evidence/receipt.json": (
        "3473a9506fbb4d4e2e5051b243e9cbce04c76ecb96707a5c0fd3e1628d11eebe"
    ),
}
PROTOCOL = "5dfcf683dca4e2f94cd28d8735dcf0b6ac22e9e16d469696d581b3e890ae19a4"


def pinned(path, fingerprint):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == fingerprint, "digest: " + path.name)
    return data


def union(intervals):
    covered = 0
    last = 0
    for start, end in sorted(intervals):
        causal(0 <= start <= end, "invalid interval")
        covered += max(0, end - max(start, last))
        last = max(last, end)
    return covered


def contribution(seen, demands, reads, wait):
    """One routed group. Each reads[e] holds its three serial component intervals."""
    causal(len(demands) == len(set(demands)) == 4 and set(reads) <= set(demands), "route")
    required = set(demands) - seen
    causal(required <= set(reads), "compulsory miss has no source generation")
    outside = []
    floor = original = 0
    for e, spans in reads.items():
        causal(len(spans) == 3, "incomplete READ chain")
        cursor = 0
        cost = 0
        for lo, hi in spans:
            causal(cursor <= lo <= hi, "nonserial service")
            cursor = hi
            cost += max(0, hi - lo - 1)
            if e in required:
                if wait is None:
                    outside.append((lo, hi))
                else:
                    wl, wr = wait
                    if lo < wl:
                        outside.append((lo, min(hi, wl)))
                    if hi > wr:
                        outside.append((max(lo, wr), hi))
        original = max(original, cost)
        if e in required:
            floor = max(floor, cost)
    seen.update(demands)
    return {
        "required": len(required),
        "required_groups": int(bool(required)),
        "r0_loads": len(reads),
        "all_read_floor_us": original,
        "required_read_floor_us": floor,
        "union_outside_wait_us": union(outside),
    }


def markers(rows):
    clocks = defaultdict(dict)
    demands = defaultdict(list)
    components = defaultdict(dict)
    for r in rows:
        if r["call"] == 0:
            continue
        cl = r["call"], r["layer"]
        kind = r["kind"]
        if kind in (2, 11, 12, 14):
            causal(kind not in clocks[cl], "repeated group boundary")
            clocks[cl][kind] = r["us"]
        elif kind == 3:
            demands[cl].append((r["expert"], r["bytes"]))
        elif kind in (6, 7):
            w = (r["layer"], r["expert"], r["slot"], r["gen"])
            k = r["component"], kind
            causal(k not in components[w], "duplicated READ")
            components[w][k] = r["us"]
    return clocks, demands, components


def score(us, fixed, n, d):
    amount = fixed * d + us * n
    over = 3 * amount - 16_000_000 * d
    return dict(seconds=amount / (d * 1e6), excess_seconds=over / (d * 3e6), excludes=over > 0)


def arm(raw, name, paid, previous, component):
    seen, facts = boundary.audit_arm(raw, name)
    require(facts["boundary_slot_vector_sha256"] == component["entry_slot_sha256"], "I")
    require(
        facts["source_sha256"] == component["raw_sha256"] == previous["source_sha256"], "sources"
    )
    path = raw / (name + ".native") / "events.tsv"
    rows = c295.events(path, True)
    pinned(path, facts["source_sha256"]["events.tsv"])
    data = c295.extract(rows)
    jobs, groups, tail, native, initial, late, start = data
    causal(not initial and not late, "entry has undrained work")
    case = name.split("-")[1]
    clocks, ranks, components = markers(rows)
    totals = {tier: Counter() for tier in ("CPU", "CUDA")}
    witness = []
    handled = set()
    prior = start
    for i, g in enumerate(groups):
        call, layer = cl = g["call"], g["layer"]
        causal((call - 1, layer) == divmod(i, 36), "group order")
        rd = ranks.pop(cl)
        ids = [e for e, _ in rd]
        witness.append((call, layer, PROMPT[case] + call - 1, ids))
        z = clocks.pop(cl)
        causal(set(z) in ({2, 14}, {2, 11, 12, 14}), "unpaired wait")
        wait = (z[11], z[12]) if 11 in z else None
        causal(prior <= z[2] <= z[14] == g["original_ready"], "remap scope")
        if wait is not None:
            causal(z[2] <= wait[0] <= wait[1] <= z[14], "wait scope")
        duration = wait[1] - wait[0] if wait else 0
        nonwait = g["pre"] + g["attention"] + g["after"]
        causal(
            duration == g["wait"] and duration + nonwait == z[14] - prior, "fixed time partition"
        )
        reads = {}
        for w in g["need"]:
            e = w[1]
            job = jobs[w]
            causal(w not in handled and w[0] == layer and e not in reads, "reused generation")
            causal(
                job["owner"] == call and z[2] <= job["begin"] <= job["end"] <= z[14],
                "foreign generation",
            )
            handled.add(w)
            pairs = components.pop(w)
            causal(set(pairs) == {(c, k) for c in range(3) for k in (6, 7)}, "READ coverage")
            spans = [(pairs[c, 6], pairs[c, 7]) for c in range(3)]
            causal(job["begin"] <= spans[0][0] and spans[-1][1] <= job["end"], "job span")
            causal(sum(hi - lo for lo, hi in spans) == job["read"], "C295 READ identity")
            reads[e] = spans
        causal(
            all(s in (0, 2) for _, s in rd) and set(reads) == {e for e, s in rd if s == 0}, "P3/P5"
        )
        v = contribution(seen[layer], ids, reads, wait)
        causal(v["union_outside_wait_us"] <= nonwait, "unexplained overlapping READ")
        totals["CPU" if layer < 25 else "CUDA"].update(v, groups=1, observed_nonwait_us=nonwait)
        prior = z[14]
    causal(len(groups) == 1152 and not ranks and not components and not clocks, "group coverage")
    causal(handled == {w for w, j in jobs.items() if j["owner"] > 0}, "unowned generation")
    require(
        check_witness(case, witness) == component["ordered_rank_sha256"], "ordered official ranks"
    )
    total = sum(totals.values(), Counter())
    for tier, v in totals.items():
        require(
            v["all_read_floor_us"] == component["tiers"][tier]["read_floor_us"], "all READ control"
        )
    require(
        total["required"] == paid["distinct_absent_at_entry"]
        and total["r0_loads"] == paid["observed_loads"],
        "entry count",
    )
    fixed = total["observed_nonwait_us"] + tail
    require(
        fixed == previous["fixed_nonservice_us"]
        and fixed + sum(g["wait"] for g in groups) == native,
        "C295 partition",
    )
    for ref in previous["scales"]:
        calc = c295.simulate(data, None, ref["scale"], critical.ARENA)["decode_us"]
        require(math.isclose(calc, ref["baseline_us"], rel_tol=0, abs_tol=1e-4), "C295 baseline")
    charged = fixed - total["union_outside_wait_us"]
    floor = total["required_read_floor_us"]
    return dict(
        anchor_sha256=facts["boundary_slot_vector_sha256"],
        raw_sha256=facts["source_sha256"],
        ranks_sha256=component["ordered_rank_sha256"],
        tiers=totals,
        total=total,
        tail_us=tail,
        original_fixed_us=fixed,
        charged_fixed_us=charged,
        native_us=native,
        scale={
            label: dict(read=score(floor, 0, n, d), with_fixed=score(floor, charged, n, d))
            for label, n, d in [("1", 1, 1), ("0.8", 4, 5)]
        },
    )


def classify(arms):
    for metric, label in (
        ("read", "NO_GO_PRIMARY_BACKING_FIXED_READ"),
        ("with_fixed", "NO_GO_CONDITIONAL_FIXED_REMAINDER"),
    ):
        if all(s[metric]["excludes"] for a in arms.values() for s in a["scale"].values()):
            return label
    return "INCONCLUSIVE"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    require(not a.new_output_dir.resolve().is_relative_to(a.raw_dir.resolve()), "protect raw")
    a.new_output_dir.mkdir(mode=0o700)
    report = {"status": "FAIL_PRESERVED", "arms": {}}
    try:
        for key, cap in (
            (resource.RLIMIT_CPU, 120),
            (resource.RLIMIT_AS, 512 << 20),
            (resource.RLIMIT_FSIZE, 2 << 20),
        ):
            soft, hard = resource.getrlimit(key)
            resource.setrlimit(key, (min(x for x in (soft, hard, cap) if x >= 0), hard))
        require(
            not critical.prefix.git(
                HERE,
                "-c",
                "core.preloadIndex=false",
                "-c",
                "index.threads=1",
                "status",
                "--porcelain",
            ),
            "dirty tree",
        )
        report.update(
            commit=critical.prefix.git(HERE, "rev-parse", "HEAD"),
            tree=critical.prefix.git(HERE, "rev-parse", "HEAD^{tree}"),
            protocol_sha256=PROTOCOL,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            control_sha256=PINS,
        )
        pinned(HERE / "protocol.md", PROTOCOL)
        pinned(Path(c295.__file__), critical.C295)
        paid, fixed, all_reads = [
            json.loads(pinned(UNIT / path, sha))["arms"] for path, sha in PINS.items()
        ]
        for name in boundary.NAMES:
            report["arms"][name] = arm(
                a.raw_dir, name, paid[name + ".native"], fixed[name], all_reads[name]
            )
        report["status"] = classify(report["arms"])
    except FileNotFoundError as exc:
        report.update(status="NOT_RUN_RAW_REQUIRED", error=Path(exc.filename).name)
    except Inconclusive as exc:
        report.update(status="INCONCLUSIVE", error=str(exc))
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        MemoryError,
        subprocess.CalledProcessError,
    ) as exc:
        report["error"] = str(exc) or type(exc).__name__
    tmp = a.new_output_dir / ".pending"
    with tmp.open("x") as f:
        json.dump(report, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(report["status"])
    return int("error" in report)


if __name__ == "__main__":
    raise SystemExit(main())
