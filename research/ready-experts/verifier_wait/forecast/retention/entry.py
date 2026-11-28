"""Separate first compulsory prefill reads from weights already owned at external call entry."""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
R = run_path(HERE / "replay.py")
F, T, S, need, sha, save, verified = (
    R[k] for k in ("F", "T", "S", "need", "sha", "save", "verified")
)
PROTO = "738255a0cbd6159f2db0ba2b03cfb9a7aee7466c2c43e848506500beec93a5f6"
PRIOR = "4606ac9a6ea424537f85df4037b58ac73054580b6289f72719d7e8d987ba4e61"
KINDS = ("first_absent", "supplied_only", "entry_only", "both")


def entry_state(primary, pools):
    sources = {}
    for (layer, _), (expert, _) in primary.items():
        key = layer, expert
        need(key not in sources, "two primary slots with same owner")
        sources[key] = "primary_back" if T["stage"](layer) else "primary_front"
    for stage, pool in enumerate(pools):
        for key in pool.held:
            need(key not in sources and T["stage"](key[0]) == stage, "secondary ownership")
            sources[key] = "bank_back_RAM" if stage else "bank_front_RAM"
    return sources


def classify(entry, supplied, key):
    return KINDS[2 * int(key in entry) + int(key in supplied)]


def inventory(tx):
    freq = Counter({(layer, expert): n for layer, expert, n in tx["counts"]})
    caps = T["quotas"](freq)
    seed = list(map(tuple, tx["seed"]))
    primary = {(layer, slot): (expert, gen) for layer, slot, expert, gen in tx["initial"]}
    present = {(layer, e) for (layer, _), (e, _) in primary.items()}
    pools = [
        T["Pool"](cap, [k for k in seed if k not in present and T["stage"](k[0]) == i], freq)
        for i, cap in enumerate(caps)
    ]
    effects, reference = T["run_order"](tx["reservations"], tx["initial"], seed, freq, caps, True)
    witness = F["Inventory"](tx)
    original, early, all_hits = (defaultdict(set) for _ in range(3))
    quadrants = defaultdict(Counter)
    entry_keys = defaultdict(set)
    mandatory_keys = defaultdict(set)
    entry_counts = {}
    last_call = None
    for row, effect in zip(tx["reservations"], effects, strict=True):
        call, tile, layer, slot, gen, e, old = row
        key, site = (layer, e), (call, tile, layer)
        group = T["stage"](layer)
        if call <= 2 and call != last_call:
            entry = entry_state(primary, pools)
            entry_counts[str(call)] = dict(Counter(entry.values()))
            supplied = set()
            last_call = call
        elif call == 3 and last_call != 3:
            need(
                primary == witness.primary
                and all(a.held == b.held for a, b in zip(pools, witness.pools, strict=True)),
                "first decode owner mismatch",
            )
            last_call = 3
        need(primary[layer, slot] == (old, gen - 1) and group == effect[0], "reservation identity")
        src, dst = pools[group].reserve(key, (layer, old))
        primary[layer, slot] = e, gen
        need([group, src, dst] == effect, "secondary source or victim changed")
        if src is not None:
            for table in (original, early, all_hits):
                table[site].add(e)
        elif call <= 2:
            where = classify(entry, supplied, key)
            stage = "back" if group else "front"
            quadrants[call, stage][where] += 1
            if key in supplied:
                early[site].add(e)
            if where != "first_absent":
                all_hits[site].add(e)
            else:
                need(key not in mandatory_keys[call], "repeated first acquisition")
                mandatory_keys[call].add(key)
            if where == "entry_only":
                entry_keys[call, entry[key]].add(key)
        if call <= 2:
            supplied.add(key)
    final = [sorted((layer, e, slot) for (layer, e), slot in p.held.items()) for p in pools]
    need(
        hashlib.sha256(json.dumps(final).encode()).hexdigest() == reference["final_sha256"],
        "terminal secondary ownership",
    )
    counts = {
        str(call): {
            stage: {k: quadrants[call, stage][k] for k in KINDS} for stage in ("front", "back")
        }
        for call in (1, 2)
    }
    result = dict(
        quadrants=counts,
        snapshots=entry_counts,
        final_secondary=reference["final_sha256"],
        entry_only_distinct_by_call_and_tier={
            str(c): {
                label: len(keys) for (call, label), keys in sorted(entry_keys.items()) if c == call
            }
            for c in (1, 2)
        },
        compulsory_distinct_by_call=[len(mandatory_keys[c]) for c in (1, 2)],
    )
    return original, early, all_hits, result


def run():
    need(sha(HERE / "entry.md") == PROTO, "entry protocol")
    prior = verified(HERE / "evidence-20261128-r01/receipt.json", PRIOR)
    inputs = prior["sources"]
    tx = verified(S["PATHS"]["transactions"], inputs["transactions"])
    service = verified(S["PATHS"]["service"], inputs["service"])
    tier = verified(S["PATHS"]["bank"], inputs["bank"])
    cfg = {k: verified(T["E"] / (k + ".json"), h) for k, h in prior["geometry"].items()}
    original, early, all_hits, result = inventory(tx)
    blocks = [v for stages in result["quadrants"].values() for v in stages.values()]
    total = {k: sum(row[k] for row in blocks) for k in KINDS}
    need(sum(total.values()) == 892 and total["both"] + total["supplied_only"] == 41, "cold census")
    need(total["first_absent"] == sum(result["compulsory_distinct_by_call"]), "mandatory set")
    order = cfg["plan"]["order"]
    source = prior["arms"]["unlimited_envelope"]
    arms = []
    for tag, raw in service["journals"].items():
        relaxed = R["grant_original_pairs"](raw, original, order)

        old, new = (
            T["priced"](tag, table, relaxed, order, cfg["layout"], cfg["pipeline"])["copied"]
            for table in (early, all_hits)
        )
        old_ns = old["limits_by_Bps"][R["RATE"]]["prefill_ns"]
        new_ns = new["limits_by_Bps"][R["RATE"]]["prefill_ns"]
        need(
            new_ns <= old_ns and new["counts"]["prefill"]["cold"] == total["first_absent"],
            "monotonicity or volumes",
        )
        for a in source:
            if a["tag"] != tag:
                continue
            need(a["prefill_ns"] == old_ns, "41-read control")
            first = [n + new_ns - old_ns for n in a["first_ns"]]
            arms.append(
                dict(
                    tag=tag,
                    W=a["W"],
                    repeat=a["repeat"],
                    first_ns=first,
                    decode_ns=a["decode_ns"],
                    prefill_ns=new_ns,
                    additional_prefill_saved_ns=old_ns - new_ns,
                    extra_budget_ns=min(10**10 - first[1], 47 * 10**9 // 6 - a["decode_ns"]),
                )
            )
    need(
        len(arms) == 8 and tier["result"]["partition"]["final_sha256"] == result["final_secondary"],
        "frozen control",
    )
    any_fit = any(v["first_ns"][0] <= 10**10 and v["decode_ns"] <= 47 * 10**9 // 6 for v in arms)
    status = (
        "GO_FINITE_SCHEDULE_ONLY"
        if all(v["extra_budget_ns"] >= 0 for v in arms)
        else "INCONCLUSIVE"
        if any_fit
        else "NO_GO"
    )
    distinct = sum(sum(v.values()) for v in result["entry_only_distinct_by_call_and_tier"].values())
    return result | dict(
        total=total,
        entry_only_distinct_per_return_total=distinct,
        distinct_entry_payload_B=distinct * T["PAYLOAD"],
        mandatory_aligned_B=total["first_absent"] * S["ALIGNED"],
        arms=arms,
        status=status,
        protocol=PROTO,
        program=sha(Path(__file__)),
        prior=PRIOR,
        evidence="TRACE_DERIVED_UNLIMITED_FREE_ENTRY_AND_REUSE",
        model_forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--new-output-dir", type=Path)
    g.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        report = run()
        if a.check:
            need(report == F["load"](a.check), "changed entry proof")
        else:
            save(a.new_output_dir / "receipt.json", report)
        print(report["status"], report["total"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
