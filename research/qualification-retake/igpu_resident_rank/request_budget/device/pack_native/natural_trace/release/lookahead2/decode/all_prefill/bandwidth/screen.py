"""Find the minimum joint payload rate on the two fixed, fully priced T2 traces."""

import argparse
from collections import Counter, defaultdict
from functools import cache
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(str(HERE.parent / "screen.py"))
C, D, L, Q, REL = (A[k] for k in ("C", "D", "L", "Q", "REL"))
NS, SIZE, PHASES = (A[k] for k in ("NS", "size", "PHASES"))
check, canonical = A["check"], A["canonical"]
CODE = "8c7de037b3242e7e8951bcced7a04375aca491ff7a9782923758305493c43370"
RULES = "36c8a1e791f06d28974db27111baff2020daef2a33b002797dcf42fd1ed4c674"
PRIOR = "ed035fcfa6a98e12ec7bbef29343256caa7c857f942d3ffa689e4bb562974147"
COMPACT = "f92af73e0cf14d4aaeceaf8559c96948818991d0b2459671186f52cbe5883a75"
MB = 1_000_000
LINE = 16 * NS * 4 * 128 // (130 * 8)
PAYLOAD_LINE = 16 * NS * 4 * 128 * SIZE // (130 * 8 * REL["WINDOW"])


def threshold(feasible, low=1, high=8000):
    """On the fixed MB/s grid return (largest observed fail, next successful price)."""
    if feasible(low):
        return None, low
    if not feasible(high):
        return high, None
    while high - low > 1:
        mid = (low + high) // 2
        if feasible(mid):
            high = mid
        else:
            low = mid
    return low, high


def certificate(measure):
    def point(bps):
        first, decode = measure(bps)
        return {"payload_Bps": bps, "first_margin_ns": first, "decode_margin_ns": decode}

    thresholds = {}
    for label, indices in (("first", (0,)), ("decode", (1,)), ("joint", (0, 1))):
        pair = threshold(lambda mb, indices=indices: min(measure(mb * MB)[i] for i in indices) >= 0)
        thresholds[label] = [None if mb is None else point(mb * MB) for mb in pair]
    return {
        "thresholds": thresholds,
        "anchors": [point(bps) for bps in (4500 * MB, PAYLOAD_LINE, LINE, 8000 * MB)],
    }


def occupancy(spans):
    changes = Counter()
    for worker, group in spans.items():
        check(worker in range(4), "invalid worker ID")
        prior = 0
        for start, end in sorted(group):
            check(prior <= start < end, "duplicate worker time or reversed read")
            prior = end
            changes[start] += 1
            changes[end] -= 1
    counts = Counter()
    ordered = sorted(changes)
    check(bool(ordered), "empty sampled phase")
    active = 0
    last = ordered[0]
    for now in ordered:
        counts[active] += now - last
        active += changes[now]
        check(0 <= active <= 4, "invalid read concurrency")
        last = now
    check(active == 0, "incomplete span")
    return {n: counts[n] for n in range(5)}


def observed(rows, host):
    phases = defaultdict(list)
    for r in rows:
        if r.kind != 30:
            continue
        entry = host["calls"][r.call - 1]
        check(
            entry["enter_ns"] <= r.begin < r.ns <= entry["return_ns"]
            and r.b == REL["WINDOW"]
            and SIZE <= r.c <= r.b
            and not r.error,
            "read not in originating call",
        )
        phases[C["phase"](r.call)].append(r)
    out = {}
    for phase in PHASES:
        records = phases[phase]
        group = defaultdict(list)
        for r in records:
            group[r.worker].append((r.begin, r.ns))
        occ = occupancy(group)
        union = sum(occ[n] for n in range(1, 5))
        worker_sum = sum(n * t for n, t in occ.items())
        wall = sum(occ.values())
        check(
            union == C["NATIVE"]["union_ns"]([(r.begin, r.ns) for r in records])
            and worker_sum == sum(r.ns - r.begin for r in records)
            and wall == max(r.ns for r in records) - min(r.begin for r in records),
            "distinct resource denominators",
        )
        payload = len(records) * SIZE
        out[phase] = {
            "reads": len(records),
            "distinct_workers": len(group),
            "payload_bytes": payload,
            "requested_bytes": sum(r.b for r in records),
            "returned_bytes": sum(r.c for r in records),
            "occupancy_ns": occ,
            "worker_ns": worker_sum,
            "union_ns": union,
            "span_ns": wall,
            "payload_per_union_Bps": payload * NS // union,
            "payload_per_span_Bps": payload * NS // wall,
        }
    check([out[p]["reads"] for p in PHASES] == [1263, 1067, 24], "conserved jobs")
    return out


def session_prices(task, total, work, source, cbs):
    @cache
    def measure(rate):
        by_phase = Counter()
        for c in range(1, 49):
            both = D["resources"](total[c], task[c], rate, work[c])[2]
            by_phase[C["phase"](c)] += both
        score = D["budget"](
            source["baseline_first_ns"],
            source["baseline_decode_ns"],
            cbs,
            [by_phase[p] for p in PHASES],
        )
        return [score["first_margin_ns"], score["decode_margin_ns"]]

    return measure


def analyse(rows, tiers, bank, old, source):
    host = C["NATIVE"]["host_trace"](rows)
    jobs, pop, seal = A["jobs"](rows, host, tiers, bank)
    check(
        pop == old["population"] and seal == old["reservation_first_use_sha256"],
        "different generations or first use",
    )
    choice, residency = A["staging"](rows, jobs, bank, tiers, "transient")
    frozen = old["modes"]["transient"]
    check(all(frozen[k] == v for k, v in residency.items()), "different residency")
    marks = (L["markers"](rows, host), D["decode_markers"](rows, host))
    clocks = [L["contracted"](m[-1]) for m in marks]
    cbs = [source["callback_ns"][p] for p in PHASES]
    result = {}
    for release in ("earliest_outer", "ranks_observed"):
        task, total, work = A["analyse_placements"](jobs, choice, marks, clocks, release, 4)

        measure = session_prices(task, total, work, source, cbs)
        for rate in L["RATES"]:
            check(
                measure(rate)
                == frozen["scenarios"][f"{release}/4/{rate}"]["priced_set_margins_ns"],
                "does not reproduce the frozen two-resource rate",
            )
        result[release] = certificate(measure)
    return {
        "windows": result,
        "observed": observed(rows, host),
        "reservation_first_use_sha256": seal,
    }


def run(archive, backend):
    check(
        L["digest"](HERE / "protocol.md") == RULES
        and L["digest"](HERE.parent / "screen.py") == CODE,
        "frozen method",
    )
    prior = A["run"](archive, backend)
    check(D["sha"](canonical(prior)) == PRIOR, "full prior receipt")
    compact = L["pinned"](HERE.parent / "receipt.json", COMPACT)
    check(compact["full_receipt_sha256"] == PRIOR, "published compact")
    old = L["pinned"](HERE.parents[1] / "receipt.json", A["PREVIOUS"])
    refs = C["SOURCES"]
    roots = {k: archive / ("part-" + k[1:]) / v[0] for k, v in refs.items()}
    seal, rows, tiers, _ = Q["read_new"](roots["P106"], refs["P106"][1])
    bank = set(map(tuple, seal["banks"]["prefill"]["ordered_keys"]))
    p106 = analyse(rows, tiers, bank, prior["P106"], old["P106"])
    del rows
    _, _, _, audit = C["CHAIN"]["chain"](roots["P97"], refs["P97"][1])
    rows, header = L["T"]["PFJ"]["read_journal"](roots["P97"] / "ON/raw/events.pfj")
    check(header == audit["header"], "sealed P97")
    p97 = analyse(rows, tiers, bank, prior["P97"], old["P97"])
    return {
        "status": "REPRODUCED_CONDITIONAL_MINIMUM_PAYLOAD_RATE",
        "code_sha256": L["digest"](Path(__file__)),
        "protocol_sha256": RULES,
        "source_sha256": CODE,
        "parent_receipt_sha256": PRIOR,
        "grid_Bps": MB,
        "line_after_encoding_Bps": LINE,
        "line_after_full_window_Bps": PAYLOAD_LINE,
        "payload_bytes_per_returned_full_window": [SIZE, REL["WINDOW"]],
        "P97": p97,
        "P106": p106,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("archive", "backend", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        row = run(args.archive, args.backend)
    except (ValueError, KeyError, OSError, StopIteration) as e:
        row = {"status": "FAIL_PRESERVED", "error": type(e).__name__, "reason": str(e)}
    (args.new_output_dir / "receipt.json").write_bytes(canonical(row))
    print(row["status"])
    raise SystemExit(int(row["status"] != "REPRODUCED_CONDITIONAL_MINIMUM_PAYLOAD_RATE"))
