"""Replay two causal replacement policies from the original C294 physical prefix slots."""

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
from prefill_interval40 import screen as interval  # noqa: E402
from srrip40 import policy  # noqa: E402

p = interval.p
require = p.require
ORACLE = "d2f0912118512131cc6c5719947bb44b1bc1d651e21a7b5d0199eac84026b0cf"
RULES = ("srrip", "lru")
PHASES = ("increment", "decode")


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def compare(candidate, control):
    delta = {k: candidate[k] - control[k] for k in ("increment", "decode", "repair_F", "total")}
    allowed = (9 * control["total"]) // 10
    gates = {
        "increment_no_more": delta["increment"] <= 0,
        "decode_no_more": delta["decode"] <= 0,
        "restored_total_10pct_lower": candidate["total"] <= allowed,
    }
    return {
        "pass": all(gates.values()),
        "gates": gates,
        "allowed_total": allowed,
        "additional_loads_to_remove_for_10pct": max(0, candidate["total"] - allowed),
        "delta_loads": delta,
        "delta_logical_bytes": {k: d * p.EXPERT_BYTES for k, d in delta.items()},
    }


def counts(increment, decode, repair):
    return {
        "increment": increment,
        "decode": decode,
        "repair_F": repair,
        "total": increment + decode + repair,
    }


def replay(start, target, stream):
    pools = {rule: [policy.Pool(slots.copy(), rule) for slots in start] for rule in RULES}
    phases = {rule: {phase: {t: Counter() for t in p.TIERS} for phase in PHASES} for rule in RULES}
    diagnostics = {phase: {t: Counter() for t in p.TIERS} for phase in PHASES}
    for phase, layer, ranks in stream:
        tier = p.TIERS[int(layer >= 25)]
        pins = set(ranks)
        misses = {}
        for rule in RULES:
            pool = pools[rule][layer]
            misses[rule] = pins.difference(pool.slots)
            record = pool.serve(ranks)
            require(
                record["misses"] == len(misses[rule])
                and record["hits"] == len(pins) - len(misses[rule])
                and record["rank_uses"] == len(ranks)
                and record["distinct_demands"] == len(pins)
                and record["waves"] == int(bool(ranks))
                and record["parking_only_waves"] == int(not ranks)
                and pins.issubset(pool.slots),
                "wave accounting or pin",
            )
            phases[rule][phase][tier].update(record)
        d = diagnostics[phase][tier]
        sr, lr = misses["srrip"], misses["lru"]
        d.update(
            compared_waves=int(bool(ranks)),
            different_miss_sets=int(sr != lr),
            excess_srrip_misses=len(sr - lr),
            excess_lru_misses=len(lr - sr),
        )
    simulated = {}
    for rule in RULES:
        final_slots = [list(pool.slots) for pool in pools[rule]]
        final_members = [set(slots) - {-1} for slots in final_slots]
        repair = [sorted(wanted - have) for wanted, have in zip(target, final_members, strict=True)]
        tiers = {}
        for tier, first, last in (("CPU", 0, 25), ("CUDA0", 25, 36)):
            increment, decode = (phases[rule][phase][tier] for phase in PHASES)
            for r in (increment, decode):
                r["logical_load_bytes"] = r["misses"] * p.EXPERT_BYTES
            tiers[tier] = counts(
                increment["misses"], decode["misses"], sum(map(len, repair[first:last]))
            )
            original = sum(sum(e >= 0 for e in pool) for pool in start[first:last])
            require(
                original
                + increment["misses"]
                + decode["misses"]
                - increment["evictions"]
                - decode["evictions"]
                == sum(map(len, final_members[first:last])),
                "tier occupancy conservation",
            )
        total = dict(sum((Counter(row) for row in tiers.values()), Counter()))
        # Counter addition drops zero-valued fields, including a legitimate zero repair.
        total = counts(*(total.get(phase, 0) for phase in (*PHASES, "repair_F")))
        simulated[rule] = {
            "phases": phases[rule],
            "loads_by_tier": tiers,
            "loads": total,
            "payload_bytes": {k: v * p.EXPERT_BYTES for k, v in total.items()},
            "F_slots": final_slots,
            "F_membership_sha256": digest([sorted(ids) for ids in final_members]),
            "missing_R0_F_by_layer": repair,
        }
    return simulated, diagnostics


def wave_stream(rows):
    for (call, _, layer), entries in groupby(rows, key=lambda row: row[:3]):
        if call >= 9:
            for ranks in p.waves([row[-1] for row in entries]):
                yield "increment" if call == 9 else "decode", layer, ranks


def evaluate(family, hist):
    old = json.loads(
        p.read_pinned(UNIT / "prefill_causal_continue/evidence/receipt.json", interval.SEALED)
    )
    oracle = json.loads(p.read_pinned(UNIT / "prefill_interval40/evidence/receipt.json", ORACLE))
    require(
        oracle["status"] == "GO_EXPLORE_VICTIMS_ONLY"
        and oracle["prior_sha256"] == interval.SEALED
        and oracle["family_sha256"] == old["family_sha256"] == p.FAMILY_SHA,
        "oracle provenance",
    )
    p.check_source(hist)
    arms = p.family_inputs(family, p.FAMILY_SHA)
    cases = {}
    for case in p.PROMPT:
        p.case_inputs(family, case, arms)
        prior, reference = old["cases"][case], oracle["cases"][case]
        require(prior["source_pair"] == reference["witness_pair"], "sealed WRT pair")
        for arm in (arm for arm in arms if arm["case"] == case):
            anchor = prior["source_pair"][arm["mode"]]
            require(
                arm["native_sha256"] == anchor["inputs"]
                and arm["run_id"] == anchor["run_id"]
                and arm["I_sha256"] == anchor["I"]
                and arm["P_sha256"] == anchor["P"]
                and arm["F_sha256"] == anchor["F"],
                "WRT P/F or inputs",
            )
        off = next(a for a in arms if a["case"] == case and a["mode"] == "OFF")
        graphs, rows = p.read(
            p.read_pinned(
                family / off["native_dir"] / "routed-witness.bin",
                off["native_sha256"]["routed-witness.bin"],
            )
        )
        p.check_geometry(graphs, case)
        work = list(wave_stream(rows))
        results = {}
        require(
            set(prior["historical"])
            == set(reference["historical"])
            == {f"c294-{case}-{i}-on" for i in (2, 3)},
            "two historical controls",
        )
        for name, ctrl in prior["historical"].items():
            root = hist / interval.boundary.CAMPAIGN / "raw" / (name + ".native")
            hashes = ctrl["source_sha256"]
            opt = reference["historical"][name]
            require(
                hashes == opt["input_sha256"]
                and ctrl["decode_ranks_sha256"] == off["decode_sha256"]
                and ctrl["decode_hits"] + ctrl["counts"]["decode"] == 4608,
                "R0 inputs, ranked decode or accounting",
            )
            # Include the journal in the fresh input checks even though its P10 counts are sealed.
            p.read_pinned(root / "events.tsv", hashes["events.tsv"])
            initial = json.loads(p.read_pinned(root / "initial.json", hashes["initial.json"]))
            native = json.loads(p.read_pinned(root / "result.json", hashes["result.json"]))
            require(
                native["initial"] == initial
                and interval.state(initial) == off["P_sha256"]
                and interval.state(native["final"]) == off["F_sha256"],
                "physical P/F",
            )
            start = [[e for e, _, _, _ in slots] for slots in interval.boundary.slots(initial)]
            final = interval.members(native["final"])
            policies, diag = replay(start, final, work)
            controls = {
                tier: counts(r["increment"], r["decode"], 0)
                for tier, r in ctrl["tiers_loads"].items()
            }
            r0 = counts(ctrl["counts"]["increment"], ctrl["counts"]["decode"], 0)
            for tier, width in zip(p.TIERS, (25, 11), strict=True):
                lower = opt["loads_by_tier"][tier]
                require(controls[tier]["total"] == lower["R0_increment_plus_decode"], "R0 cost")
                for data in policies.values():
                    costs = data["loads_by_tier"][tier]
                    require(
                        costs["total"] >= lower["joint_with_F"]
                        and costs["increment"] + costs["decode"] >= lower["joint"],
                        "below oracle",
                    )
                    inc, dec = (data["phases"][phase][tier] for phase in PHASES)
                    require(
                        dec["rank_uses"] == dec["distinct_demands"] == 32 * 4 * width
                        and dec["waves"] == 32 * width
                        and dec["parking_only_waves"] == 0
                        and inc["rank_uses"] == 4 * (width * 153 - (152 if tier == "CUDA0" else 0)),
                        "supplied workload",
                    )
            proposal = policies["srrip"]
            contrasts = {
                k: compare(proposal["loads"], v)
                for k, v in (("R0", r0), ("lru", policies["lru"]["loads"]))
            }
            for contrast, other in (("R0", controls), ("lru", policies["lru"]["loads_by_tier"])):
                contrasts[contrast]["tier_delta_loads"] = {
                    t: {k: proposal["loads_by_tier"][t][k] - v for k, v in other[t].items()}
                    for t in p.TIERS
                }
            results[name] = {
                "P_sha256": off["P_sha256"],
                "R0_F_sha256": off["F_sha256"],
                "input_sha256": hashes,
                "policies": policies,
                "R0": controls,
                "R0_total": r0,
                "R0_decode_hits": ctrl["decode_hits"],
                "decode_ranks_sha256": ctrl["decode_ranks_sha256"],
                "oracle": opt["loads_by_tier"],
                "contrasts": contrasts,
                "diagnostic_wave_disagreements": diag,
                "pass": all(c["pass"] for c in contrasts.values()),
            }
        cases[case] = {
            "historical": results,
            "pass": all(a["pass"] for a in results.values()),
            "witness_pair": prior["source_pair"],
        }
    return {
        "status": "GO_FIXTURE_ONLY" if all(a["pass"] for a in cases.values()) else "NO_GO",
        "scope": "TRACE_DERIVED_CAUSAL_REPLACEMENT_FIXED_PHYSICAL_P_FREE_PARKING",
        "historical_receipt_sha256": interval.SEALED,
        "oracle_receipt_sha256": ORACLE,
        "family_sha256": p.FAMILY_SHA,
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", type=Path, required=True)
    parser.add_argument("--historical-results", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    a = parser.parse_args()
    commit, tree = (p.git(HERE, "rev-parse", ref) for ref in ("HEAD", "HEAD^{tree}"))
    clean = not p.git(HERE, "status", "--porcelain=v1", "--untracked-files=normal")
    a.new_output_dir.mkdir(mode=0o700)
    try:
        require(clean, "dirty measurement checkout")
        out = evaluate(a.family, a.historical_results)
    except (OSError, TypeError, ValueError, KeyError, IndexError) as error:
        out = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(error, FileNotFoundError)
            else "FAIL_PRESERVED",
            "error": str(error),
        }
    out.update(
        commit=commit,
        tree=tree,
        clean=clean,
        code_sha256={
            f.relative_to(UNIT).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in (
                Path(__file__).resolve(),
                Path(policy.__file__),
                Path(interval.__file__),
                Path(p.__file__),
                HERE / "protocol.md",
            )
        },
    )
    tmp = a.new_output_dir / ".pending"
    with tmp.open("x") as dest:
        dest.write(json.dumps(out, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(out["status"])
    return int("cases" not in out)


if __name__ == "__main__":
    sys.exit(main())
