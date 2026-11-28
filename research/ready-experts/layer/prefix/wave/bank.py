"""Join a fixed causal RAM bank, adjacent disk reads and two in-flight tiles by generation."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(HERE / "pipeline.py")
SRC, L, need, LIMIT, PAYLOAD, NS = (P[k] for k in ("SRC", "L", "need", "LIMIT", "PAYLOAD", "NS"))
PIPE = "5fc56d654b3c04e9f02acb7c5a05ab39d29ea5c2477bc962c23901b0f00230c5"


def service(rows, regions):
    """Authenticate one complete READ and three completed SETs at the recorded slot version."""
    starts, ends, jobs, prices, calls = {}, {}, {}, {}, {}
    for r in rows:
        site = (r.call, r.tile, r.layer)
        k = SRC["key"](r)
        if r.kind in (1, 2):
            calls[r.call, r.kind] = r.ns
        elif r.kind == 9:
            starts.setdefault(site, r.ns)
        elif r.kind == 23:
            ends[site] = r.ns
        elif r.kind == 11:
            need(k not in jobs, "duplicate reserve")
            jobs[k] = [site, r.ns, None, []]
        elif r.kind == 30:
            origin, start, read, sets = jobs[k]
            need(
                origin == site
                and read is None
                and not sets
                and start <= r.begin < r.ns
                and not r.error
                and r.b == r.c == 13221888,
                "bad read",
            )
            jobs[k][2] = r.begin, r.ns
        elif r.kind == 16:
            origin, _, read, sets = jobs[k]
            need(
                origin == site
                and read
                and r.component == len(sets) < 3
                and r.a * 3 == PAYLOAD
                and (sets[-1][1] if sets else read[1]) <= r.begin < r.ns,
                "bad set",
            )
            sets.append((r.begin, r.ns))
        elif r.kind == 17:
            origin, _, read, sets = jobs[k]
            need(
                origin == site and len(sets) == 3 and sets[-1][1] <= r.ns and k not in prices,
                "publication",
            )
            prices[k] = [read[1] - read[0], sum(b - a for a, b in sets), r.ns]
    need(jobs.keys() == prices.keys() and len(jobs) == 2354, "complete generations")
    by_site = defaultdict(dict)
    for k, (site, release, _, _) in jobs.items():
        rd, st, pub = prices[k]
        need(
            starts[site] <= release < pub <= ends[site] and k[3] not in by_site[site],
            "region boundary",
        )
        by_site[site][k[3]] = [rd, st]
    compact = []
    for c, t, layer, ids, lo, hi, _ in regions:
        site = c, t, layer
        work = by_site[site]
        need(sorted(work) == ids and lo <= starts[site] <= ends[site] <= hi, "bound selection")
        compact.append(
            [c, t, layer, lo, starts[site], ends[site], hi, [[e, *work[e]] for e in ids]]
        )
    return dict(calls=[[calls[c, 1], calls[c, 2]] for c in range(1, 49)], groups=compact)


def sources(rows, path, bank):
    positions = {e: i for i, e in enumerate(path)}
    need(len(rows) == len({r[0] for r in rows}), "duplicate source")
    ordered = sorted(rows, key=lambda r: positions[r[0]])
    hits = {e for e, _, _ in ordered if e in bank}
    cold = [e for e, _, _ in ordered if e not in hits]
    adjacent = [(a, b) for a, b in pairwise(cold) if positions[b] == positions[a] + 1]
    coupled = {e for pair in adjacent for e in pair}
    original = sum(positions[b[0]] == positions[a[0]] + 1 for a, b in pairwise(ordered))
    need(original >= len(adjacent) and not hits & coupled, "exclusive sources")
    return hits, coupled, len(adjacent), original


def calculate(data, previous, marks, order, selected, direct):
    bins = defaultdict(set)
    for layer, e in selected:
        bins[layer].add(e)
    free, floors, counts = defaultdict(list), defaultdict(list), defaultdict(Counter)
    for c, _, layer, lo, start, end, hi, work in data["groups"]:
        hits, coupled, edges, original = sources(work, order[layer], bins[layer])
        count = counts[c]
        count.update(
            jobs=len(work),
            bank_hits=len(hits),
            cold=len(work) - len(hits),
            edges_before=original,
            edges_after=edges,
            cold_participants=len(coupled),
        )
        if not (hits or coupled):
            continue
        free[c].append((lo, hi))
        worker = [
            (0 if e in hits or e in coupled else rd) + (0 if direct and e in hits else st)
            for e, rd, st in work
        ]
        floor = max(max(worker), P["ceil_div"](sum(worker), 4))
        need(floor <= end - start, "service not feasible with observed four workers")
        floors[c].append((start, end, floor))

    def residual(c, lo, hi):
        total = P["kept"](lo, hi, free[c])
        for start, end, cost in floors[c]:
            if max(lo, start) < min(hi, end):
                need(lo <= start <= end <= hi, "split service region")
                total += cost
        need(0 <= total <= hi - lo, "residual outside control")
        return total

    clock = previous["before_ns"]
    exterior = previous["outside_calls_ns"]
    cut = {}
    for speed in P["SPEEDS"]:
        costs = {}
        for c, (lo, hi) in enumerate(data["calls"], 1):
            v = residual(c, lo, hi)
            if c == 2:
                stages = [
                    (residual(c, a, b), residual(c, f, g)) for _, a, b, f, g, _ in marks["tiles"]
                ]
                v = P["pipeline"](stages)[-1][-1]
            costs[c] = max(v, P["ceil_div"](counts[c]["cold"] * PAYLOAD * NS, speed))
        metrics = {
            "first_final": exterior["first_final"] + sum(costs[c] for c in range(1, 47)),
            "decode": exterior["decode"] + sum(costs[c] for c in range(3, 49)),
        }
        # A physical rate sensitivity may also price a short group above its historical service.
        need(all(0 < metrics[k] and exterior[k] <= clock[k] for k in LIMIT), "external cut")
        cut[str(speed)] = dict(
            floors_ns=metrics,
            margin_ns={k: LIMIT[k] - v for k, v in metrics.items()},
            prefill_ns=costs[1] + costs[2],
            decision="NO_GO_FIXED_COST"
            if any(metrics[k] > LIMIT[k] for k in LIMIT)
            else "HEADROOM_ONLY",
        )
    population = {}
    for name, cs in (
        ("prefill", range(1, 3)),
        ("early_decode", range(3, 47)),
        ("tail", range(47, 49)),
    ):
        population[name] = dict(sum((counts[c] for c in cs), Counter()))
    return dict(counts=population, limits_by_Bps=cut)


def evaluate(inputs, previous, pipeline, plan, bank):
    need(len(bank) == len(set(map(tuple, bank))) == 353, "fixed causal set")
    budget = 353 * PAYLOAD
    report = {}
    for tag, raw in inputs.items():
        now = {}
        for choice, seed in (("empty", []), ("fixed", bank)):
            for layout, ords in (("numeric", [list(range(128))] * 36), ("trained", plan["order"])):
                outputs = {
                    m: calculate(
                        raw, previous["arms"][tag], pipeline["arms"][tag]["markers"], ords, seed, d
                    )
                    for m, d in (("copied", False), ("direct", True))
                }
                need(outputs["copied"]["counts"] == outputs["direct"]["counts"], "hit attribution")
                row = dict(population=outputs["copied"]["counts"])
                for m, v in outputs.items():
                    row[m] = v["limits_by_Bps"]
                now[choice + "_" + layout] = row
        report[tag] = now
    need(
        all(v["population"] == report["P106"][k]["population"] for k, v in report["P97"].items()),
        "cohorts",
    )
    return dict(resident_bytes=budget, arms=report)


def run(a):
    p = SRC["pinned"](a.pipeline, PIPE)
    previous = SRC["pinned"](a.layout_evidence / "receipt.json", P["SCORING"])
    plan = SRC["pinned"](a.trained_plan, P["PLAN"])
    packed = a.layout_evidence / "regions.json.gz"
    need(SRC["digest"](packed) == previous["regions_sha256"], "reservation census")
    groups = json.loads(gzip.decompress(packed.read_bytes()))
    all_data = {}
    for tag in ("P106", "P97"):
        name, h, _ = SRC["SOURCES"][tag]
        root = a.archive / ("part-" + tag[1:]) / name
        if tag == "P106":
            before, rows, _, proof = SRC["Q"]["read_new"](root, h)
            selected = before["banks"]["lru"]["ordered_keys"]
            seal = proof["selection_sha256"]
        else:
            f = root / "ON/raw/events.pfj"
            need(SRC["digest"](f) == previous["arms"][tag]["journal_sha256"], "P97 receipt")
            rows, _ = SRC["T"]["PFJ"]["read_journal"](f)
        all_data[tag] = service(rows, groups[tag])
    result = evaluate(all_data, previous, p, plan, selected)
    result.update(
        evidence="TRACE_DERIVED_CONDITIONAL",
        program_sha256=SRC["digest"](HERE / "bank.py"),
        protocol_sha256=SRC["digest"](HERE / "bank-protocol.md"),
        selection_sha256=seal,
        pipe_sha256=PIPE,
        layout_sha256=P["SCORING"],
        plan_sha256=P["PLAN"],
    )
    return result, dict(journals=all_data, selected=selected)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("archive", "layout-evidence", "trained-plan", "pipeline", "new-output-dir"):
        p.add_argument("--" + arg, type=Path, required=True)
    args = p.parse_args()
    out = args.new_output_dir
    out.mkdir(mode=0o700)
    try:
        result, witness = run(args)
        packed = out / "service.json.gz"
        packed.write_bytes(
            gzip.compress(json.dumps(witness, separators=(",", ":")).encode(), mtime=0)
        )
        result["service_sha256"] = SRC["digest"](packed)
        tmp = out / ".pending"
        tmp.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        tmp.rename(out / "receipt.json")
    except (ValueError, KeyError, AssertionError, OSError, TypeError) as exc:
        (out / "failure.json").write_text(
            json.dumps({"status": "FAIL_PRESERVED", "reason": repr(exc)}) + "\n"
        )
        raise
    print(SRC["digest"](out / "receipt.json"))
