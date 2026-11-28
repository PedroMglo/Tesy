"""Verify every worker interval and compare the complete consumer across paired submissions."""

from itertools import product
from pathlib import Path
from runpy import run_path
from statistics import median

C = run_path(Path(__file__).with_name("cases.py"))
need, CASES, TAGS = (C[k] for k in ("need", "CASES", "JOURNALS"))
REGIMES = ("HANDOFF", "BANK")
WINDOW, PAYLOAD = 13221888, 13219200


def verify(native, scenario, tag, case, regime, phase):
    need(
        [native[k] for k in ("journal", "case", "regime", "phase")] == [tag, case, regime, phase],
        "native scope",
    )
    jobs = scenario["jobs"]
    roles = C["role_names"](case, regime, scenario)
    last = 52 if case == "decode4" else 63
    initial_keys = {j["old"] for j in jobs} | {k[3] for k in scenario["entry"]}
    initial_keys.update(j["expert"] for j in jobs if j["hit"] or regime == "HANDOFF")
    need(
        native["bootstrap_records"] == len(initial_keys)
        and native["arena_B"] == 1252 * WINDOW
        and native["staging_B"] == 4 * WINDOW,
        "memory and initial physical reads",
    )
    want = [(0, 0, r) for r in roles]
    if phase == "exact":
        want.append((0, 0, "MUTANT"))
    else:
        for p, d in product(range(1, 8), range(2)):
            want.extend((p, d, r) for r in (roles[::-1] if d else roles))
    records = native["rows"]
    need([(r["block"], r["direction"], r["role"]) for r in records] == want, "registered order")
    stats = []
    for row in records:
        role = row["role"]
        pub, late, waiting, reads, sets = [], [], {}, 0, 0
        for j, (reserve, dispatch, ready, publish, nread, nset) in zip(
            jobs, row["events"], strict=True
        ):
            direct = j["hit"] and (role in ("ALL", "MUTANT") or role == "ONE_" + str(j["expert"]))
            need(
                nread == int(regime == "BANK" and (not j["hit"] or role == "DISK"))
                and nset == (0 if direct else 3),
                "source or number of SETs",
            )
            need(
                j["reserve_ns"] <= reserve <= dispatch
                and j["dispatch_ns"] <= dispatch <= ready <= publish <= row["consumer_ns"]
                and (regime != "HANDOFF" or j["ready_ns"] <= ready)
                and waiting.get(j["worker"], 0) <= dispatch,
                "worker execution or publication",
            )
            pub.append(publish)
            late.append(dispatch - j["dispatch_ns"])
            waiting[j["worker"]] = publish
            reads += nread
            sets += nset
        need(
            len(waiting) == 4
            and all(
                [e[k] for e in row["events"]] == sorted(e[k] for e in row["events"]) for k in (0, 1)
            )
            and scenario["barrier_ns"]
            <= row["arrival_ns"]
            <= row["consumer_ns"]
            <= row["drain_ns"],
            "FIFO, consumer, or drain",
        )
        if phase == "exact":
            witness = row["exact"]
            live = [
                (e, slot)
                for v, r in zip(scenario["view"], scenario["logical"], strict=True)
                for slot, e in zip(v, r, strict=True)
                if slot >= 0
            ]
            corrupt = sum(e == last for e, _ in live) if role == "MUTANT" else 0
            need(
                witness
                == dict(
                    active=len(live),
                    parked=4 * len(scenario["view"]) - len(live),
                    wrong_ranks=corrupt,
                    wrong_experts=[last] if corrupt else [],
                    matrix_hashes=3 * len(scenario["demands"]),
                )
                and (corrupt > 0) == (role == "MUTANT"),
                "authoritative rank view or fault",
            )
        else:
            need("exact" not in row, "numerical observer inside price")
        stats.append(
            dict(
                block=row["block"],
                direction=row["direction"],
                role=role,
                consumer=row["consumer_ns"],
                drain=row["drain_ns"],
                last=max(pub),
                wait=row["consumer_ns"] - row["arrival_ns"],
                release_to_consumer=row["consumer_ns"] - max(pub),
                max_dispatch_late=max(late),
                reads=reads,
                sets=sets,
            )
        )
    return stats


def paired(values):
    return dict(ns=values, median_ns=median(values), positive=sum(v > 0 for v in values))


def summarize(native, scenario, tag, case, regime):
    exact = native["exact"]
    proof = verify(exact, scenario, tag, case, regime, "exact")
    timed = verify(native["price"], scenario, tag, case, regime, "price")
    roles = C["role_names"](case, regime, scenario)
    singles = [r for r in roles if r.startswith("ONE_")]
    indexed = {(r["block"], r["direction"], r["role"]): r for r in timed}
    results = []
    for d in range(2):
        arms = {}
        for name in roles:
            group = [indexed[p, d, name] for p in range(1, 8)]
            arms[name] = {
                k: median(r[k] for r in group)
                for k in (
                    "consumer",
                    "drain",
                    "last",
                    "wait",
                    "release_to_consumer",
                    "max_dispatch_late",
                    "reads",
                    "sets",
                )
            }
        pairs = {}
        winners = []
        for label in ("COPY", "best_ONE", *(["DISK"] if regime == "BANK" else [])):
            vals = []
            for p in range(1, 8):
                if label == "best_ONE":
                    control = min(singles, key=lambda name: indexed[p, d, name]["consumer"])
                    winners.append(control)
                else:
                    control = label
                vals.append(indexed[p, d, control]["consumer"] - indexed[p, d, "ALL"]["consumer"])
            pairs[label + "_minus_ALL"] = paired(vals)
        if regime == "BANK":
            pairs["DISK_minus_COPY"] = paired(
                [
                    indexed[p, d, "DISK"]["consumer"] - indexed[p, d, "COPY"]["consumer"]
                    for p in range(1, 8)
                ]
            )
        results.append(
            dict(
                direction=d,
                medians_ns_or_counts=arms,
                comparisons=pairs,
                best_single_per_block=winners,
            )
        )
    return dict(
        journal=scenario["journal"],
        site=scenario["site"],
        positions=len(scenario["view"]),
        consumers=len(scenario["demands"]),
        jobs=len(scenario["jobs"]),
        hits=sum(j["hit"] for j in scenario["jobs"]),
        exact_arms=len(proof),
        exact=exact["rows"][0]["exact"],
        mutant=exact["rows"][-1]["exact"],
        price_submissions=len(timed),
        graded_submissions=14 * len(roles),
        directions=results,
        timed_service_records=sum(row["reads"] for row in timed if row["block"]),
        exact_warm_price_pack_B=WINDOW
        * (
            sum(row["reads"] for row in proof + timed)
            + exact["bootstrap_records"]
            + native["price"]["bootstrap_records"]
        ),
    )


def grade(scenarios, all_native):
    arms = {}
    for tag, case, regime in product(TAGS, CASES, REGIMES):
        key = "-".join((tag, case, regime))
        arms[key] = summarize(all_native[key], scenarios[tag][case], tag, case, regime)
    prim = [r["comparisons"] for t in TAGS for r in arms[t + "-decode4-BANK"]["directions"]]
    if all(
        min(r[k]["median_ns"] for k in ("COPY_minus_ALL", "best_ONE_minus_ALL")) > 0 for r in prim
    ):
        verdict = "GO_MEASURED_GROUP_DELIVERY"
    elif all(r["COPY_minus_ALL"]["median_ns"] < 0 for r in prim):
        verdict = "NO_GO_LOCAL_GROUP_DELIVERY"
    else:
        verdict = "INCONCLUSIVE_GROUP_DELIVERY"
    total_bytes = sum(a["exact_warm_price_pack_B"] for a in arms.values())
    need(total_bytes <= 40 << 30, "pack transfer cap")
    return dict(
        status=verdict,
        evidence="MEASURED_COMPONENT_LAPTOP",
        arms=arms,
        pack_requested_B=total_bytes,
        graded_submissions=sum(a["graded_submissions"] for a in arms.values()),
        exact_submissions=sum(a["exact_arms"] for a in arms.values()),
        M3="PARTIAL",
        M4="NOT_MET",
        HTTP_requests=0,
        full_model_forwards=0,
        gpu_compute=False,
    )
