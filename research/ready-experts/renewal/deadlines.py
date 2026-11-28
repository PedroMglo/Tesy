"""Price prefetched generations whose first consumer cannot leave the same tile/layer."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CO = run_path(HERE / "composition.py")
IV, RE, SRC, B, CC, need, CAP = (CO[k] for k in ("INTERVAL", "RE", "SRC", "B", "CC", "need", "CAP"))
METHOD = "213ec38c0dcd8b551a378eea7d09969129b0147e0cb005a912001bd9b0a49455"
PARENT = "df1ad53c531351498de7837fe9a16bd8e8282c8cddad94b949d3d838bd3a0776"
PPM = 1_000_000


def consumers(waves, stamps):
    first = {}
    for wave in waves:
        for k in wave.demands:
            first.setdefault(k, wave)
    result = {}
    for producer in waves:
        for k in producer.reserved:
            reserve, publish = stamps[k]
            need(
                k not in result
                and producer.start <= reserve <= producer.end
                and reserve <= publish,
                "reserve outside its origin",
            )
            w = first.get(k)
            if w is None:
                tag = "no_consumer"
            else:
                need(producer.start <= w.start and publish <= w.end, "unpublished or stale demand")
                if w.site == producer.site:
                    tag = "same_wave"
                elif w.site[:3] == producer.site[:3]:
                    tag = "later_wave_same_tile_layer"
                else:
                    tag = "later_region"
            result[k] = tag
    need(set(stamps) == result.keys(), "unclassified generation")
    return result


def deadline_arm(rows, tx, old):
    by_key = {r.generation: i for i, r in enumerate(tx, 1)}
    origins, published, read, sets = {}, {}, {}, defaultdict(list)
    for e in rows:
        k = SRC["key"](e)
        if e.kind == 11:
            origins[k] = e.ns
        elif e.kind == 30:
            read[k] = e.ns - e.begin
        elif e.kind == 16:
            sets[k].append(e.ns - e.begin)
        elif e.kind == 17:
            published[k] = e.ns
    need(
        by_key.keys() == origins.keys() == published.keys() == read.keys() == sets.keys(),
        "service population",
    )
    waves, sites = SRC["timeline"](rows)
    tags = consumers(waves, {k: (ts, published[k]) for k, ts in origins.items()})
    groups, histogram, prices = defaultdict(lambda: defaultdict(list)), defaultdict(Counter), {}
    for k, tag in tags.items():
        i = by_key[k]
        call, tile, layer, _ = sites[k]
        histogram[B["phase"](call)][tag] += 1
        amount = sum(sets[k])
        need(len(sets[k]) == 3 and (tag == "same_wave") == (i in old), "legacy equivalence")
        if tag in ("same_wave", "later_wave_same_tile_layer"):
            prices[i] = read[k] + amount
            groups[call][tile, layer].append(RE["Job"](i, read[k], amount))
            if i in old:
                need(prices[i] == old[i], "changed original service price")
    regs = list(IV["C"]["partition"](SRC["NATIVE"]["host_trace"](rows)["calls"], waves, groups))
    return regs, histogram, prices


def fits(clocks):
    return all(B["joint"](c) >= 0 for c in clocks["with_full_client_cost_ns"].values())


def read_limit(data, chosen):
    def assess(scale):
        args = {}
        for label, (regs, exterior) in data.items():
            result = []
            for num, groups, edges in regs:
                scaled = []
                for g in groups:
                    jobs = [RE["Job"](j.expert, j.read_ns * scale // PPM, j.set_ns) for j in g.jobs]
                    scaled.append(RE["Region"](g.site, g.internal, jobs))
                result.append((num, scaled, edges))
            args[label] = result, exterior
        return CC["assess"](args, chosen, False)

    if not fits(assess(0)):
        return {"status": "NO_GO_EVEN_FREE_READ"}
    lo, hi = 0, PPM + 1
    while hi - lo > 1:
        middle = (hi + lo) // 2
        if fits(assess(middle)):
            lo = middle
        else:
            hi = middle
    inside = assess(lo)
    outside = assess(hi) if hi <= PPM else None
    need(fits(inside) and (outside is None or not fits(outside)), "break-even bracket")
    return {
        "max_read_ppm": lo,
        "min_reduction_ppm": PPM - lo,
        "at_limit_ns": inside["with_full_client_cost_ns"],
        "at_one_ppm_more_ns": None if outside is None else outside["with_full_client_cost_ns"],
    }


def run(a):
    need(SRC["digest"](HERE / "deadlines.md") == METHOD, "method")
    previous = SRC["pinned"](a.composition / "receipt.json", PARENT)
    intervals = SRC["pinned"](a.intervals / "receipt.json", CO["PARENT"])
    assignment = a.intervals / "schedule.json.gz"
    need(SRC["digest"](assignment) == intervals["schedule_sha256"], "assignment digest")
    old_witness = SRC["pinned"](a.composition / "witness.json", previous["witness_sha256"])
    proof = json.loads(gzip.decompress(assignment.read_bytes()))
    policies = {k: {i for _, i, _ in proof[k]} for k in ("recent", "frequency")}
    policies["prior_oracle"] = {i for _, i, _ in old_witness["intervals"]}
    prior = SRC["pinned"](B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"])
    gaps = SRC["pinned"](CO["LOOKUP"] / "empty-result.json", CO["EMPTY_RESULT"])
    local = CO["placements"](a.placement)
    root = a.archive / "part-106" / SRC["SOURCES"]["P106"][0]
    seal, rows106, _, _ = SRC["Q"]["read_new"](root, SRC["SOURCES"]["P106"][1])
    seed = list(map(tuple, seal["banks"]["lru"]["ordered_keys"]))
    data, old_data, credits, prices = {}, {}, {}, Counter()
    common = None
    for label in ("P106", "P97"):
        rows = rows106
        if label == "P97":
            path = a.archive / "part-97" / SRC["SOURCES"][label][0] / "ON/raw/events.pfj"
            rows, _ = SRC["T"]["PFJ"]["read_journal"](path)
        old_data[label], tx, primary, old, _, lineage = IV["load_arm"](
            a.archive, label, rows, seed, prior[label]
        )
        need(
            list(lineage) == intervals["routing_and_reservations"],
            "different routing or generation",
        )
        regs, population, added = deadline_arm(rows, tx, old)
        identity = tx, primary, population, added.keys()
        need(common is None or common == identity, "different consumer class")
        common = identity
        data[label] = regs, old_data[label][1]
        c, audit = CO["graph_credits"](rows, local, gaps["journals"][label])
        need(audit == previous["empty_graph"][label], "changed graph")
        credits[label] = c["placed"]
        prices.update(added)
    seed = [k for k in seed if k not in primary]
    starts = IV["opportunities"](tx, seed)
    eligible = {i: start for i, start in starts.items() if i in prices}
    for policy, ids in policies.items():
        wanted = "critical_oracle" if policy == "prior_oracle" else policy
        for mode in ("copied", "direct"):
            need(
                CC["assess"](old_data, ids, mode == "direct")
                == previous["results"][wanted]["unchanged"][mode],
                "previous full client and decode",
            )
    base = IV["expensive_first"](eligible, prices, CAP)
    if a.verify:
        witness = json.loads(a.verify.read_bytes())
        chosen, swaps = base.copy(), witness["exchanges"]
        need(len(swaps) <= 24, "exchange extent")
        for drop, add, delta in swaps:
            need(drop in chosen and add not in chosen and add in eligible and delta < 0, "bad swap")
            chosen.remove(drop)
            chosen.add(add)
    else:
        chosen, swaps = CO["search"](data["P106"][0], eligible, base, CAP)
    slots, peak = IV["assign"](eligible, chosen, CAP)
    tier = IV["audit"](tx, seed, eligible, slots, CAP)
    candidate = {
        "exchanges": swaps,
        "intervals": [[starts[i], i, slots[i]] for i in sorted(chosen)],
    }
    if a.verify:
        need(witness == candidate, "slot identity")
    w = a.new_output_dir / "witness.json"
    w.write_text(json.dumps(candidate, separators=(",", ":")) + "\n")
    policies.update(new_oracle=chosen, unlimited=set(eligible))
    graphs = {"unchanged": data, "placed": CO["discount"](data, credits)}
    results = {
        p: {
            g: {m: CC["assess"](args, ids, m == "direct") for m in ("copied", "direct")}
            for g, args in graphs.items()
        }
        for p, ids in policies.items()
    }
    now = results["new_oracle"]["unchanged"]["copied"]["with_full_client_cost_ns"]["P106"][
        "first_final"
    ]
    before = CC["assess"](data, base, False)["with_full_client_cost_ns"]["P106"]["first_final"]
    need(before + sum(d for _, _, d in swaps) == now, "incorrect repricing")
    for g in graphs:
        lower = results["unlimited"][g]["direct"]["with_full_client_cost_ns"]
        for r in results.values():
            full = r[g]["direct"]["with_full_client_cost_ns"]
            need(all(lower[a][k] <= full[a][k] for a in lower for k in lower[a]), "unlimited bound")
    thresholds = {
        p: {g: read_limit(args, policies[p]) for g, args in graphs.items()}
        for p in ("recent", "frequency")
        if not fits(results[p]["placed"]["copied"])
    }
    return {
        "schema": "tesy.ready_bank_deadlines.v1",
        "status": "TRACE_DERIVED",
        "method_sha256": METHOD,
        "source_sha256": SRC["digest"](Path(__file__)),
        "composition_sha256": PARENT,
        "population": population,
        "mandatory": len(prices),
        "eligible": len(eligible),
        "peak": peak,
        "exchanges": len(swaps),
        "oracle_hits": len(chosen),
        "oracle_counts_by_tier": tier,
        "witness_sha256": SRC["digest"](w),
        "results": results,
        "read_service": thresholds,
        "decisions": {
            g: {
                "all_selections_full_client": "NO_GO"
                if not fits(results["unlimited"][g]["direct"])
                else "HEADROOM_ONLY"
                if fits(results["new_oracle"][g]["copied"])
                else "INCONCLUSIVE",
                "all_selections_with_grant": "NO_GO"
                if not results["unlimited"][g]["direct"]["fits_with_grant"]
                else "HEADROOM_ONLY"
                if results["new_oracle"][g]["direct"]["fits_with_grant"]
                else "INCONCLUSIVE",
                "causal_even_with_grant": {
                    p: "HEADROOM_ONLY" if results[p][g]["direct"]["fits_with_grant"] else "NO_GO"
                    for p in ("recent", "frequency")
                },
            }
            for g in graphs
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("archive", "intervals", "composition", "placement", "new-output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--verify", type=Path)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(a)
    except FileNotFoundError as exc:
        path = Path(exc.filename).resolve()
        raw = path.is_relative_to(a.archive.resolve()) or path.is_relative_to(a.placement.resolve())
        report = {"status": "NOT_RUN_RAW_REQUIRED" if raw else "FAIL", "missing": path.name}
    except (KeyError, ValueError, AssertionError, OSError, TypeError) as exc:
        report = {"status": "FAIL", "reason": str(exc)}
    tmp = a.new_output_dir / ".pending"
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(report["status"], report.get("decisions", report.get("reason", "")))
    raise SystemExit(report["status"] != "TRACE_DERIVED")
