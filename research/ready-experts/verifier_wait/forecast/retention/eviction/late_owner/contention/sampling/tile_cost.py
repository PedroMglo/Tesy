"""Compare serial and overlapped tiles at identical expert, link and four-reader prices."""

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(HERE / "sampled.py")
D, need, sha, save = (S[k] for k in ("D", "need", "sha", "save"))
X = D["replay"]()
V, F = X["V"], X["F"]
T = V["T"]
R, K, P = T["R"], T["K"], T["P"]
METHOD = "860df9435b6e54dac16f0d8749d44cfcfbc71cff330d4aef0cee978e7d5ed54e"
RATES = "0b5fcad908e04ab944539036a74f9fc79dba0533221eb09198ceaaddb4a6e5b1"
PPM = D["PPM"]


def exposure(jobs, hits):
    weights = defaultdict(Counter)
    outside = Counter()

    def count(live, q, k, width):
        if not 0 < k < q:
            return
        # Competing intervals are usable only inside the same original consumer region.
        shape = f"{q}/{k}"
        peers = live - hits
        if len({tuple(jobs[i - 1][1][:3]) for i in live}) > 1:
            outside[shape] += width * len(peers)
        else:
            for i in peers:
                weights[i][shape] += width

    totals, _ = X["split"](jobs, hits, on_interval=count)
    need(
        sum(v.total() for v in weights.values()) + outside.total()
        == sum(totals["simultaneous"].values()),
        "peer-time conservation",
    )
    return weights, outside


def paid_job(read, setters, potential, hit, adjacent, direct):
    need(not (hit and adjacent) and 0 <= potential <= read, "overlapping read credits")
    if hit or adjacent:
        return (0 if hit and direct else setters), 0
    return read - potential + setters, potential


def tile_clocks(stages, link_ns, workers_ns):
    # Both schedules get the same free inter-stage handoff and the same aggregate resources.
    serial = sum(a + b for a, b in stages)
    schedule = P["pipeline"](stages)
    pipeline = schedule[-1][-1]
    need(pipeline <= serial, "invalid overlap")
    return max(serial, link_ns, workers_ns), max(pipeline, link_ns, workers_ns)


def scenarios(
    data,
    jobs,
    hits,
    weights,
    paths,
    rates,
    direct,
    markers,
    previous,
    tag,
    *,
    on_stages=None,
    site_floor=None,
    free_hit_layers=None,
):
    lookup = {(*row[1][:3], row[0][3]): i for i, row in enumerate(jobs, 1)}
    need(len(lookup) == len(jobs) == 2354, "distinct source per site and generation")
    clocks = defaultdict(list)
    discarded, applied, cold, work, census = (Counter() for _ in range(5))
    removed = defaultdict(list)
    seen = set()
    tile_jobs = []
    for c, tile, layer, lo, start, end, hi, group in data["groups"]:
        ordinals = {e: lookup[c, tile, layer, e] for e, _, _ in group}
        sources = {e for e, i in ordinals.items() if i in hits}
        local, adjacent, _, _ = K["sources"](group, paths[layer], sources)
        need(local == sources and not local & adjacent, "exclusive sources")
        durations = []
        bypass = direct and (free_hit_layers is None or layer in free_hit_layers)
        for e, read, setters in group:
            i = ordinals[e]
            row = jobs[i - 1]
            need(
                i not in seen
                and row[6] - row[5] == read
                and sum(row[j + 1] - row[j] for j in (7, 9, 11)) == setters,
                "mismatched read, generation or component clocks",
            )
            seen.add(i)
            potential = sum(v * rates[s] for s, v in weights.get(i, {}).items()) // PPM
            cost, discount = paid_job(read, setters, potential, e in local, e in adjacent, bypass)
            durations.append(cost)
            applied[c] += discount
            discarded[c] += potential - discount
        if not (local or adjacent):
            need(not any(i in weights for i in ordinals.values()), "credit with no local source")
        else:
            removed[c].append((lo, hi))
            floor = max(max(durations), P["ceil_div"](sum(durations), 4))
            if site_floor is not None:
                tighter = site_floor(c, tile, layer, durations)
                need(tighter >= floor, "local bound weaker than control")
                floor = tighter
            need(floor <= end - start, "service exceeds observed window")
            clocks[c].append((start, end, floor))
        work[c] += sum(durations)
        if on_stages is not None and c == 2 and group:
            tile_jobs.append(
                (tile, layer, start, end, list(zip(ordinals.values(), durations, strict=True)))
            )
        cold[c] += len(group) - len(local)
        census.update(
            hits=len(local),
            adjacent=len(adjacent),
            isolated=len(group) - len(local) - len(adjacent),
        )
    need(
        len(seen) == 2354 and census.total() == len(seen) and census["hits"] == len(hits),
        "incomplete generation accounting",
    )
    total_credit = sum(sum(v * rates[s] for s, v in mix.items()) // PPM for mix in weights.values())
    need(
        applied.total() + discarded.total() == total_credit, "isolated/adjacent credit conservation"
    )

    def region(c, lo, hi):
        value = P["kept"](lo, hi, removed[c])
        for start, end, cost in clocks[c]:
            if max(lo, start) < min(hi, end):
                need(lo <= start <= end <= hi, "service crosses stage boundary")
                value += cost
        need(0 <= value <= hi - lo, "stage duration")
        return value

    calls = {c: region(c, lo, hi) for c, (lo, hi) in enumerate(data["calls"], 1)}
    stages = [[region(2, a, b), region(2, f, g)] for _, a, b, f, g, _ in markers["tiles"]]
    need(len(stages) == 5 and len(calls) == 48, "external returns or geometry")
    if on_stages is not None:
        on_stages(tile_jobs, stages, markers["tiles"], region)
    result, legacy = {}, {}
    credit = F["C"]["CC"]["CREDIT"] if tag == "P106" else 0
    ext = previous["outside_calls_ns"]

    def metrics(prices):
        phase = dict(
            call5=prices[1],
            call148=prices[2],
            decode_to_first=sum(prices[c] for c in range(3, 47)),
            tail=prices[47] + prices[48],
        )
        first = ext["first_final"] + phase["call5"] + phase["call148"] + phase["decode_to_first"]
        decode = ext["decode"] + phase["decode_to_first"] + phase["tail"]
        return dict(
            first_final_ns=first,
            decode_ns=decode,
            credited_first_ns=first - credit,
            margin_ns=min(10**10 - first, 47 * 10**9 // 6 - decode),
            credited_margin_ns=min(10**10 - first + credit, 47 * 10**9 // 6 - decode),
            phases_ns=phase,
        )

    worker = {c: P["ceil_div"](v, 4) for c, v in work.items()}
    for speed in P["SPEEDS"]:
        link = {c: P["ceil_div"](n * K["PAYLOAD"] * 10**9, speed) for c, n in cold.items()}
        serial, pipeline = tile_clocks(stages, link[2], worker[2])
        legacy_calls = {c: max(cost, link[c]) for c, cost in calls.items()}
        legacy_calls[2] = max(P["pipeline"](stages)[-1][-1], link[2])
        old = metrics(legacy_calls)
        legacy[str(speed)] = dict(first_final=old["first_final_ns"], decode=old["decode_ns"])
        prices = {c: max(legacy_calls[c], worker[c]) for c in calls}
        result[str(speed)] = dict(
            serial=metrics(prices | {2: serial}),
            pipeline=metrics(prices | {2: pipeline}),
            overlap_saved_ns=serial - pipeline,
            call148_worker_floor_ns=worker[2],
            call148_link_floor_ns=link[2],
        )
    return dict(
        counts=census,
        stages_ns=stages,
        discarded_adjacent_worker_ns=discarded.total(),
        applied_isolated_worker_ns=applied.total(),
        speeds=result,
    ), legacy


def decision(arms):
    speed = "8000000000"
    for row in arms.values():
        best = row["trained"]["high"]["direct"]["speeds"][speed]["pipeline"]
        if best["credited_margin_ns"] < 0:
            return "NO_GO_AT_TRANSPORTED_RATES"
    floor = [row["trained"]["low"]["copied"]["speeds"][speed] for row in arms.values()]
    if all(v["pipeline"]["margin_ns"] >= 0 for v in floor):
        return (
            "SERIAL_INTEGRATION_FIRST"
            if all(v["serial"]["margin_ns"] >= 0 for v in floor)
            else "GO_TWO_TILE_FIXTURE"
        )
    return "INCONCLUSIVE"


def evaluate():
    need(sha(HERE / "pipeline-protocol.md") == METHOD, "protocol identity")
    sample = S["M"]["verified"](HERE / "evidence-three-20261128-r01/projection.json", RATES)
    need(sample["status"] == "NO_GO_AT_CALIBRATED_RATES", "parent decision")
    rates = sample["models"]["envelope"]["rates_ppm"]
    legacy = S["M"]["verified"](V["TIER"] / "evidence-tier-20261128-r01/receipt.json", V["OLD"])
    tx, effect = V["sources"]()
    hits = {i for i, r in enumerate(effect, 1) if r[1] is not None}
    e = T["E"]
    manifest = R["get"](e / "provenance.json")["artifacts_sha256"]
    for name in ("pipeline.json", "layout.json", "service.json.gz", "plan.json"):
        need(sha(e / name) == manifest[name], "pipeline input " + name)
    pipeline, layout, trained = (
        R["get"](e / name) for name in ("pipeline.json", "layout.json", "plan.json")
    )
    bank_service = R["unpack"]("service.json.gz")["journals"]
    peers = X["ORIGINAL"] / "service.json.gz"
    need(sha(peers) == V["SERVICE"], "peer journal input")
    current = F["unpack"](peers)
    basis, _, _ = F["freeze"]()
    results, cross = {}, {}
    for tag, data in bank_service.items():
        jobs = current[tag]["jobs"]
        F["verify_jobs"](jobs, basis["arms"][tag])
        need(
            layout["arms"][tag]["journal_sha256"] == basis["arms"][tag]["journal_sha256"],
            "different client process",
        )
        for row, (call, tile, layer, slot, gen, expert, _) in zip(jobs, tx, strict=True):
            need(
                row[0] == [layer, slot, gen, expert] and row[1][:3] == [call, tile, layer],
                "wrong generation",
            )
        w, cross[tag] = exposure(jobs, hits)
        result = {}
        for name, paths in (("numeric", [list(range(128))] * 36), ("trained", trained["order"])):
            result[name] = {}
            for end, values in (
                ("zero", dict.fromkeys(rates, 0)),
                ("low", {s: v[0] for s, v in rates.items()}),
                ("high", {s: v[1] for s, v in rates.items()}),
            ):
                modes = {}
                for mode, direct in (("copied", False), ("direct", True)):
                    row, control = scenarios(
                        data,
                        jobs,
                        hits,
                        w,
                        paths,
                        values,
                        direct,
                        pipeline["arms"][tag]["markers"],
                        layout["arms"][tag],
                        tag,
                    )
                    if end == "zero":
                        prior = legacy["result"]["arms"][tag][name][mode]["limits_by_Bps"]
                        need(
                            all(c == prior[k]["floors_ns"] for k, c in control.items()),
                            "historical costs",
                        )
                    modes[mode] = row
                result[name][end] = modes
        results[tag] = result
    need(set(results) == {"P97", "P106"} and len(hits) == 674, "complete clients and bank")
    return dict(
        status=decision(results),
        method=METHOD,
        prior_rates=RATES,
        prior_bank=V["OLD"],
        evidence="TRACE_DERIVED_CONDITIONAL",
        rates_ppm=rates,
        excluded_cross_site_worker_ns_by_shape=cross,
        arms=results,
        http_requests=0,
        forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    out = p.add_mutually_exclusive_group(required=True)
    out.add_argument("--new-output-dir", type=Path)
    out.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        result = evaluate()
        if a.check:
            need(result == json.loads(a.check.read_bytes()), "published comparison")
        else:
            save(a.new_output_dir / "pipeline.json", result)
        print(result["status"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
