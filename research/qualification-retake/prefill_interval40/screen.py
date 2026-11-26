"""Offline fixed-P cache floor for the C294 increment, 32 decode steps and final membership."""

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
import cache_boundary as boundary  # noqa: E402
from cache_bound import minimum  # noqa: E402
from prefill_causal import plan as p  # noqa: E402
from warm_route_family.grade import state  # noqa: E402

SEALED = "ef9234d7d5b811ec3897e1eb3e62a6d727984f07d98a54bdede74042f132b8f8"
require = p.require


def layer_floor(groups, start, final, capacity=40):
    union = set().union(*groups)
    floor = minimum(groups, capacity, initial=start)
    with_final = minimum([*groups, sorted(final)], capacity, initial=start)
    cardinality = len(union - start)
    cardinality_f = len((union | final) - start)
    require(cardinality <= floor <= with_final and cardinality_f <= with_final, "floor ordering")
    return Counter(
        cardinality=cardinality,
        cardinality_with_F=cardinality_f,
        joint=floor,
        joint_with_F=with_final,
    )


def groups_for(rows):
    layers = [[] for _ in range(36)]
    votes = Counter()
    for (call, _, layer), entries in groupby(rows, key=lambda r: r[:3]):
        if call < 9:
            continue
        phase = "increment" if call == 9 else "decode"
        for wave in p.waves([r[-1] for r in entries]):
            if wave:
                layers[layer].append(tuple(dict.fromkeys(wave)))
                votes[phase, layer] += len(wave)
    for layer in range(36):
        require(
            votes["decode", layer] == 4 * 32
            and votes["increment", layer] == 4 * (153 if layer < 35 else 1),
            "wave coverage",
        )
    return layers


def members(snap):
    return [{e for e, _, s, _ in pool if s == 2} for pool in boundary.slots(snap)]


def passes(optimum, reference):
    return 10 * optimum <= 9 * reference


def evaluate(family, hist):
    old = json.loads(p.read_pinned(UNIT / "prefill_causal_continue/evidence/receipt.json", SEALED))
    require(
        old["family_sha256"] == p.FAMILY_SHA and old["status"] in {"NO_GO", "GO_FIXTURE_ONLY"},
        "continuation receipt not qualified",
    )
    p.check_source(hist)
    arms = p.family_inputs(family, p.FAMILY_SHA)
    cases = {}
    for case in p.PROMPT:
        p.case_inputs(family, case, arms)
        off = next(a for a in arms if a["case"] == case and a["mode"] == "OFF")
        prev = old["cases"][case]
        require(
            all(
                a["native_sha256"] == prev["source_pair"][a["mode"]]["inputs"]
                for a in arms
                if a["case"] == case
            ),
            "WRT inputs changed",
        )
        graphs, rows = p.read(
            p.read_pinned(
                family / off["native_dir"] / "routed-witness.bin",
                off["native_sha256"]["routed-witness.bin"],
            )
        )
        p.check_geometry(graphs, case)
        groups = groups_for(rows)
        results = {}
        require(set(prev["historical"]) == {f"c294-{case}-{n}-on" for n in (2, 3)}, "pair")
        for name, ctrl in prev["historical"].items():
            src = hist / boundary.CAMPAIGN / "raw" / (name + ".native")
            hashes = ctrl["source_sha256"]
            initial = json.loads(p.read_pinned(src / "initial.json", hashes["initial.json"]))
            native = json.loads(p.read_pinned(src / "result.json", hashes["result.json"]))
            require(
                native["initial"] == initial
                and state(initial) == off["P_sha256"]
                and state(native["final"]) == off["F_sha256"],
                "historical P/F anchor",
            )
            start, final = members(initial), members(native["final"])
            tiers = {tier: Counter() for tier in p.TIERS}
            for layer, stream in enumerate(groups):
                tiers[p.TIERS[int(layer >= 25)]].update(
                    layer_floor(stream, start[layer], final[layer])
                )
            for tier, counts in tiers.items():
                ref = ctrl["tiers_loads"][tier]
                counts["R0_increment_plus_decode"] = ref["increment"] + ref["decode"]
                require(
                    counts["joint_with_F"] <= counts["R0_increment_plus_decode"],
                    "R0 feasible cost below optimum",
                )
            total = sum(tiers.values(), Counter())
            results[name] = {
                "loads_by_tier": tiers,
                "loads": total,
                "payload_bytes": {k: v * p.EXPERT_BYTES for k, v in total.items()},
                "input_sha256": hashes,
                "headroom_screen_pass": passes(
                    total["joint_with_F"], total["R0_increment_plus_decode"]
                ),
            }
        cases[case] = {
            "historical": results,
            "witness_pair": prev["source_pair"],
            "pass": all(r["headroom_screen_pass"] for r in results.values()),
        }
    return {
        "status": "GO_EXPLORE_VICTIMS_ONLY" if all(c["pass"] for c in cases.values()) else "NO_GO",
        "scope": "TRACE_DERIVED_FIXED_P_FREE_PARKING_EXACT_WAVE_JOINT_LOAD_FLOOR",
        "prior_sha256": SEALED,
        "family_sha256": p.FAMILY_SHA,
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", type=Path, required=True)
    parser.add_argument("--historical-results", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    a = parser.parse_args()
    commit = p.git(HERE, "rev-parse", "HEAD")
    tree = p.git(HERE, "rev-parse", "HEAD^{tree}")
    clean = not p.git(HERE, "status", "--porcelain=v1", "--untracked-files=normal")
    a.new_output_dir.mkdir(mode=0o700)
    try:
        require(clean, "dirty measurement checkout")
        out = evaluate(a.family, a.historical_results)
    except (OSError, TypeError, ValueError, IndexError, KeyError) as e:
        out = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(e, FileNotFoundError)
            else "FAIL_PRESERVED",
            "error": str(e),
        }
    out.update(
        commit=commit,
        tree=tree,
        clean=clean,
        code_sha256={
            path.relative_to(UNIT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__).resolve(),
                HERE / "protocol.md",
                Path(p.__file__),
                UNIT / "cache_bound.py",
            )
        },
    )
    tmp = a.new_output_dir / ".pending"
    with tmp.open("x") as f:
        f.write(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(out["status"])
    return int("cases" not in out)


if __name__ == "__main__":
    sys.exit(main())
