"""Charge 32 causal decode steps and the final membership repair after the sealed prefix replay."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from itertools import groupby
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(UNIT))
import cache_boundary  # noqa: E402
from prefill_causal import plan as prefix  # noqa: E402
from warm_route_family.grade import state  # noqa: E402
from warm_route_reference.verify import check_witness, witness_rows  # noqa: E402

require = prefix.require
PRIOR_COMMIT = "1909d5cda24e5521d84c20ede1d51de3405fbf5f"
PRIOR_SOURCE = "7d67491c6289c478476f26292ee876d82d278a8b6a0333440434cc999ec9d6de"
PRIOR_FILE = UNIT / "prefill_causal" / "evidence" / "receipt.json"
PRIOR_SHA = "5e0aebdcb3fb3b5e2de22fefd145954b3aa5defc1b5ccdfc535e0fb86c4e9c87"
PHASES = ("prefix", "increment", "decode")


def history(rows, rule, previous, target_f):
    pools = [prefix.Pool(rule) for _ in range(36)]
    stats = {phase: {tier: Counter() for tier in prefix.TIERS} for phase in PHASES}
    cuts = {}
    for (call, _, layer), entries in groupby(rows, key=lambda row: row[:3]):
        if call in (9, 10) and call not in cuts:
            key = "P_membership_sha256" if call == 9 else "I_membership_sha256"
            cuts[call] = prefix.membership_digest(pools)
            require(cuts[call] == previous[key], "replayed membership differs at " + key[0])
        phase = "prefix" if call <= 8 else ("increment" if call == 9 else "decode")
        tier = prefix.TIERS[int(layer >= 25)]
        ranks = [entry[-1] for entry in entries]
        for group in prefix.waves(ranks):
            stats[phase][tier].update(pools[layer].serve(group))
    require(set(cuts) == {9, 10}, "incomplete cuts")
    for phase in PHASES:
        for tier, count in stats[phase].items():
            require(
                count["misses"] + count["hits"] == count["distinct_demands"], "miss and hit count"
            )
            count["logical_load_bytes"] = count["misses"] * prefix.EXPERT_BYTES
            if phase != "decode":
                require(dict(count) == previous["phases"][phase][tier], "prefill counters differ")
    require(
        sum(s["rank_uses"] for p in stats.values() for s in p.values())
        == sum(p.clock for p in pools)
        and sum(s["misses"] - s["evictions"] for p in stats.values() for s in p.values())
        == sum(len(p.resident) for p in pools),
        "rank or occupancy conservation",
    )
    return {
        "P_membership_sha256": cuts[9],
        "I_membership_sha256": cuts[10],
        "F_membership_sha256": prefix.membership_digest(pools),
        "phases": stats,
        "restore_F_identity_floor": prefix.project_i(pools, target_f),
    }


def count_loads(sim):
    counts = {phase: sum(x["misses"] for x in sim["phases"][phase].values()) for phase in PHASES}
    counts["restored_total"] = sum(counts.values()) + sum(
        v["loads"] for v in sim["restore_F_identity_floor"].values()
    )
    return counts


def compare(candidate, control):
    delta = {key: candidate[key] - control[key] for key in candidate}
    combined_c = candidate["increment"] + candidate["decode"]
    combined_r = control["increment"] + control["decode"]
    delta["increment_plus_decode"] = combined_c - combined_r
    raw_total_delta = sum(delta[p] for p in PHASES)
    checks = {
        "increment_plus_decode_at_least_10pct_lower": 10 * combined_c <= 9 * combined_r,
        **{
            key + "_no_more": delta[key] <= 0
            for key in ("prefix", "increment", "decode", "restored_total")
        },
    }
    return {
        "pass": all(checks.values()),
        "gates": checks,
        "scenario_free_F_only": {
            "delta_total_loads": raw_total_delta,
            "delta_total_payload_bytes": raw_total_delta * prefix.EXPERT_BYTES,
            "all_other_gates_and_unrestored_total_nonincreasing": raw_total_delta <= 0
            and all(passed for k, passed in checks.items() if k != "restored_total_no_more"),
        },
        "delta_loads": delta,
        "delta_payload_bytes": {k: v * prefix.EXPERT_BYTES for k, v in delta.items()},
    }


def historical_arm(hist, case, name, old, source_pair, i_fingerprint):
    root = hist / cache_boundary.CAMPAIGN / "raw"
    _, audit = cache_boundary.audit_arm(root, name)
    native = root / (name + ".native")
    hashes = audit["source_sha256"]
    require(
        hashes == old["source_sha256"] and audit["boundary_slot_vector_sha256"] == i_fingerprint,
        "historical input changed",
    )
    result = json.loads(prefix.read_pinned(native / "result.json", hashes["result.json"]))
    require(
        state(result["initial"]) == old["boundary_p_sha256"] == source_pair["P"]
        and state(result["final"]) == source_pair["F"],
        "R0 P or F differs",
    )
    ordered = check_witness(case, witness_rows(native / "events.tsv", case, hashes["events.tsv"]))
    final = cache_boundary.slots(result["final"])
    tiers = {}
    for i, tier in enumerate(prefix.TIERS):
        selected = final[25:] if i else final[:25]
        published = sum(gen for layer in selected for _, gen, _, _ in layer)
        phases = old["tiers"][tier]
        decode = published - phases["total_loads"]
        require(decode >= 0, "R0 generations went backwards")
        tiers[tier] = {
            "prefix": phases["prefix_loads"],
            "increment": phases["increment_loads"],
            "decode": decode,
        }
    counts = {phase: sum(t[phase] for t in tiers.values()) for phase in PHASES}
    require(
        counts["decode"] == audit["counts"]["decode_publications"]
        and audit["counts"]["decode_hit"] + audit["counts"]["decode_miss"] == 4608,
        "R0 decoding conservation",
    )
    counts["restored_total"] = sum(counts.values())
    return [{e for e, _, s, _ in pool if s == 2} for pool in final], {
        "source_sha256": hashes,
        "F_sha256": source_pair["F"],
        "decode_ranks_sha256": ordered,
        "tiers_loads": tiers,
        "tiers_payload_bytes": {
            tier: {p: n * prefix.EXPERT_BYTES for p, n in values.items()}
            for tier, values in tiers.items()
        },
        "counts": counts,
        "decode_hits": audit["counts"]["decode_hit"],
    }


def evaluate(family, hist):
    prefix.read_pinned(Path(prefix.__file__), PRIOR_SOURCE)
    old = json.loads(prefix.read_pinned(PRIOR_FILE, PRIOR_SHA))
    require(
        old["measurement_checkout"]["commit"] == PRIOR_COMMIT
        and old["status"] == "NO_GO"
        and old["family_sha256"] == prefix.FAMILY_SHA,
        "unqualified prefill reference",
    )
    prefix.check_source(hist)
    arms = prefix.family_inputs(family, prefix.FAMILY_SHA)
    cases = {}
    for case in prefix.PROMPT:
        prior = old["cases"][case]
        _, fp = prefix.case_inputs(family, case, arms)
        pair = [a for a in arms if a["case"] == case]
        for a in pair:
            sealed = prior["source_pair"][a["mode"]]
            require(
                sealed
                == {
                    "inputs": a["native_sha256"],
                    "run_id": a["run_id"],
                    "P": a["P_sha256"],
                    "I": fp,
                    "F": a["F_sha256"],
                },
                "WRT arm changed",
            )
        off = next(a for a in pair if a["mode"] == "OFF")
        graphs, rows = prefix.read(
            prefix.read_pinned(
                family / off["native_dir"] / "routed-witness.bin",
                off["native_sha256"]["routed-witness.bin"],
            )
        )
        prefix.check_geometry(graphs, case)
        require(
            set(prior["historical"]) == {f"c294-{case}-{n}-on" for n in (2, 3)},
            "missing paired R0 control",
        )
        historical, target = {}, None
        for name, ctrl in prior["historical"].items():
            final, entry = historical_arm(hist, case, name, ctrl, prior["source_pair"]["OFF"], fp)
            require(target is None or final == target, "R0 repetitions disagree at F")
            historical[name], target = entry, final
        policies = {r: history(rows, r, prior["simulated"][r], target) for r in prefix.RULES}
        for out in policies.values():
            for i, tier in enumerate(prefix.TIERS):
                counts = out["phases"]["decode"][tier]
                expected = 32 * (11 if i else 25)
                require(
                    counts["waves"] == expected
                    and counts["distinct_demands"] == 4 * expected == counts["rank_uses"]
                    and counts["parking_only_waves"] == 0,
                    "decode workload differs",
                )
        candidate = count_loads(policies["votes"])
        contrasts = {"lru": compare(candidate, count_loads(policies["lru"]))}
        contrasts.update(
            {name: compare(candidate, ctrl["counts"]) for name, ctrl in historical.items()}
        )
        cases[case] = {
            "simulated": policies,
            "historical": historical,
            "contrasts": contrasts,
            "source_pair": prior["source_pair"],
            "pass": all(c["pass"] for c in contrasts.values()),
        }
    return {
        "status": "GO_FIXTURE_ONLY" if all(v["pass"] for v in cases.values()) else "NO_GO",
        "scope": "TRACE_DERIVED_LOGICAL_PAYLOAD_ONLY",
        "family_sha256": prefix.FAMILY_SHA,
        "previous_receipt_sha256": PRIOR_SHA,
        "cases": cases,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", required=True, type=Path)
    p.add_argument("--historical-results", required=True, type=Path)
    p.add_argument("--new-output-dir", required=True, type=Path)
    a = p.parse_args()
    commit = prefix.git(HERE, "rev-parse", "HEAD")
    tree = prefix.git(HERE, "rev-parse", "HEAD^{tree}")
    clean = not prefix.git(HERE, "status", "--porcelain=v1", "--untracked-files=normal")
    a.new_output_dir.mkdir(mode=0o700)
    try:
        require(clean, "dirty measurement checkout")
        receipt = evaluate(a.family, a.historical_results)
    except (OSError, TypeError, ValueError, IndexError, KeyError) as e:
        receipt = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(e, FileNotFoundError)
            else "FAIL_PRESERVED",
            "error": str(e),
        }
    receipt["measurement_checkout"] = {"commit": commit, "tree": tree, "clean_before_output": clean}
    receipt["code_sha256"] = {
        path.relative_to(UNIT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__).resolve(), HERE / "protocol.md", Path(prefix.__file__))
    }
    tmp = a.new_output_dir / ".pending"
    with tmp.open("x") as f:
        f.write(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(receipt["status"])
    return int("cases" not in receipt)


if __name__ == "__main__":
    sys.exit(main())
