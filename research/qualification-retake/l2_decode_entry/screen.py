"""Finite warm L2 at I with the original four workers and measured C295 service."""

import argparse
import hashlib
import json
import math
import resource
import signal
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(UNIT))
from l2_decode_entry import solver  # noqa: E402
from l2_warm_critical import screen as warm  # noqa: E402

cold, p, require = warm.cold, warm.p, warm.require
CAPS = (0, 243, 378)
WARM_SHA = "7c51a5606505c8353971adec1beda99450215d4fab69b6dd9566523d09c7157e"


def claim_index(rows, jobs):
    """Match every lookup ordinal to its original physical generation at both cuts."""
    out = {}
    for seq, row in enumerate(rows):
        if row["kind"] == 5:
            key = tuple(row[k] for k in ("layer", "expert", "slot", "gen"))
            out[seq] = key, row["call"]
    require(len(out) == sum(map(len, jobs.values())), "P5 lookup cardinality")
    for phase in ("increment", "decode"):
        for start, end, key in jobs[phase]:
            native, owner = out[start]
            pub = rows[end]
            require(
                pub["kind"] == 10
                and tuple(pub[k] for k in ("layer", "expert", "slot", "gen")) == native
                and pub["call"] == owner
                and (owner == 0) == (phase == "increment")
                and native[:2] == key,
                "P5/P10 identity or phase",
            )
    return {seq: native for seq, (native, owner) in out.items() if owner > 0}


def reserved_keys(initial):
    rows = sorted(initial["layers"], key=lambda layer: layer["layer"])
    require([r["layer"] for r in rows] == list(range(36)), "reservation layers")
    keys = set()
    for row in rows:
        flags = row["seen"]
        require(
            len(flags) == 128 and all(type(v) is int and v in (0, 1) for v in flags),
            "reservation bitmap",
        )
        keys.update((row["layer"], expert) for expert, flag in enumerate(flags) if flag)
    return keys


def timed(data, claims, witness, baselines, historical):
    ids = witness["hit_claims"]
    require(len(set(ids)) == len(ids) and set(ids) <= claims.keys(), "invalid hit witnesses")
    hits = {claims[i] for i in ids}
    require(len(hits) == len(ids), "duplicate hit generation")
    fixed, stats, tiers = cold.maxima(data, hits)
    service = stats["new_max_us"]
    require(service == witness["group_max_sum_us"], "four-worker maximum disagrees with solver")
    change = {w: {**j, "read": 0.0 if w in hits else j["read"]} for w, j in data[0].items()}
    spans = []
    for base, earlier in zip(baselines, historical, strict=True):
        scale = base["scale"]
        elapsed = cold.c295.simulate((change, *data[1:]), None, scale, cold.ARENA)["decode_us"]
        require(
            math.isclose(elapsed, fixed + scale * service, rel_tol=0, abs_tol=1e-4)
            and earlier["scale"] == scale
            and elapsed >= earlier["warm_L2_us"] - 1e-4
            and elapsed <= base["baseline"]["decode_us"] + 1e-4,
            "simulator disagrees or exceeds the preceding relaxed bound",
        )
        spans.append(
            {
                "scale": scale,
                "baseline_us": base["baseline"]["decode_us"],
                "warm_P_bound_us": earlier["warm_L2_us"],
                "decode_us": elapsed,
                "steps_per_s": 32e6 / elapsed,
                "signed_slack_us": cold.BUDGET_US - elapsed,
                "reaches_6": elapsed <= cold.BUDGET_US,
            }
        )
    return {**witness, "scales": spans, "service_by_tier_at_scale1": tiers}


def arm(raw, name, routed, off, prior, sensitivity):
    jobs, proof = cold.admission.service_arm(raw, name)
    hashes = proof["source_sha256"]
    require(
        hashes == prior["raw_sha256"]
        and off["I_sha256"] == prior["I_sha256"] == proof["primary_I_sha256"]
        and (off["P_sha256"], off["F_sha256"], off["decode_sha256"])
        == (prior["P_sha256"], prior["F_sha256"], prior["decode_ranks_sha256"])
        and off["native_sha256"]["routed-witness.bin"] == prior["WRT_sha256"],
        "different historical trace, service, routes or P/I/F",
    )
    directory = raw / (name + ".native")
    init = json.loads(p.read_pinned(directory / "initial.json", hashes["initial.json"]))
    res = reserved_keys(init)
    rows = cold.c295.events(directory / "events.tsv", True)
    claims = claim_index(rows, jobs)
    data = cold.c295.extract(rows)
    require(
        len(claims) == prior["decode_claims"]
        and set(claims.values()) == {w for w, j in data[0].items() if j["owner"] > 0}
        and [(g["call"], g["layer"]) for g in data[1]]
        == [(i, layer) for i in range(1, 33) for layer in range(36)],
        "C295 service or group mismatch",
    )
    require(
        [h["scale"] for h in sensitivity] == [0.8, 1.0, 1.2]
        and all(
            cold.c295.simulate(data, None, h["scale"], cold.ARENA) == h["baseline"]
            for h in sensitivity
        ),
        "historical C295 without L2",
    )
    groups = []
    for g in data[1]:
        entries = []
        for w in g["need"]:
            j = data[0][w]
            require(all(int(j[k]) == j[k] >= 0 for k in ("read", "copy")), "service units")
            entries.append((w[:2], int(j["read"]), int(j["copy"])))
        groups.append(entries)
    increment = {key for _, _, key in jobs["increment"]}
    all_keys = {(layer, expert) for layer in range(36) for expert in range(128)}
    result = {}
    for label, allowed in (("prefix_routed", routed), ("prefix_reserved", res), ("any", all_keys)):
        options = solver.solve(jobs, groups, allowed, CAPS)
        require(set(options) == set(CAPS), "missing capacity")
        # The published warm-P screen has no reserved-only variant; 'any' contains it.
        relaxed = prior["eligibility"]["any" if label == "prefix_reserved" else label]
        cases = {}
        for k, choice in options.items():
            keys = {tuple(key) for key in choice["chosen"]}
            require(
                len(keys) == len(choice["chosen"]) <= k and keys <= allowed | increment,
                "unavailable I-entry materialization",
            )
            item = dict(choice)
            for mode in ("optimistic", "feasible"):
                prev = relaxed["by_capacity"][str(k)]["scales"]
                # Warm-P K=0 retains all incremental completions thereafter for free.
                # At I, even the optimistic K=0 starts empty, then keeps decode repeats.
                item[mode] = timed(data, claims, choice[mode], sensitivity, prev)
            require(
                item["feasible"]["peak_slots"] <= k
                and item["feasible"]["fits"]
                and item["optimistic"]["group_max_sum_us"] <= item["feasible"]["group_max_sum_us"]
                and (k or not item["feasible"]["hit_claims"]),
                "capacity/relaxation violated",
            )
            cases[k] = item
        result[label] = {"prefix_universe": len(allowed), "by_capacity": cases}
    for k in CAPS:
        lower = result["any"]["by_capacity"][k]["optimistic"]["group_max_sum_us"]
        require(
            all(
                v["by_capacity"][k]["optimistic"]["group_max_sum_us"] >= lower
                for v in result.values()
            ),
            "eligibility superset",
        )
    return {
        "raw_sha256": hashes,
        "P_sha256": off["P_sha256"],
        "I_sha256": off["I_sha256"],
        "F_sha256": off["F_sha256"],
        "decode_ranks_sha256": off["decode_sha256"],
        "WRT_sha256": prior["WRT_sha256"],
        "increment_publications": len(jobs["increment"]),
        "increment_unique": len(increment),
        "decode_claims": len(claims),
        "eligibility": result,
    }


def run(family, raw):
    saved = json.loads(p.read_pinned(UNIT / "l2_warm_critical/evidence/receipt.json", WARM_SHA))
    require(saved["status"] == "PASS_CONDITIONAL_WARM_P_BOUNDS", "unqualified preceding envelope")
    p.read_pinned(Path(cold.__file__), warm.BASE_CODE)
    p.read_pinned(Path(cold.c295.__file__), cold.C295)
    scenario = json.loads(
        p.read_pinned(
            cold.ROOT / "results/c295-activation-byte-optimistic-scenario-20261006/scenario.json",
            cold.SCENARIO,
        )
    )
    members = p.family_inputs(family, p.FAMILY_SHA)
    arms = {}
    for case in p.PROMPT:
        routed, off = warm.wrt(family, case, members)
        for row in scenario["cases"][case]:
            name = row["run"]
            arms[name] = arm(
                raw, name, routed, off, saved["arms"][name], row["service_sensitivity"]
            )
    require(set(arms) == set(cold.admission.boundary.NAMES), "four original arms")
    return {
        "status": "PASS_CONDITIONAL_DECODE_ENTRY_BOUNDS",
        "arms": arms,
        "family_sha256": p.FAMILY_SHA,
        "warm_P_sha256": WARM_SHA,
        "C295_program_sha256": cold.C295,
        "C295_scenario_sha256": cold.SCENARIO,
        "budget_us": cold.BUDGET_US,
        "expert_bytes": warm.EXPERT,
    }


def classify(arms, k, index):
    def passes(case, eligible, mode):
        return all(
            arms[f"c294-{case}-{n}-on"]["eligibility"][eligible]["by_capacity"][k][mode]["scales"][
                index
            ]["reaches_6"]
            for n in (2, 3)
        )

    decisions = {}
    for case in p.PROMPT:
        arbitrary = passes(case, "any", "optimistic")
        feasible = passes(case, "prefix_routed", "feasible")
        decisions[case] = (
            "NO_GO_CAPACITY_BOTH_REPEATS_REQUIRED"
            if not arbitrary
            else "GO_CAUSAL_SELECTION_FIXTURE_ONLY"
            if feasible
            else "INCONCLUSIVE"
        )
    return decisions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    dest = args.new_output_dir.resolve()
    require(
        all(not dest.is_relative_to(x.resolve()) for x in (args.family, args.raw_dir)),
        "output overlaps inputs",
    )
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = 768 << 20
    resource.setrlimit(resource.RLIMIT_AS, (min(hard, cap) if hard >= 0 else cap, hard))

    def timeout(*_):
        raise TimeoutError("120 s budget")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    dest.mkdir(mode=0o700)
    meta = {}
    try:
        meta = {
            key: p.git(HERE, "rev-parse", rev)
            for key, rev in (("commit", "HEAD"), ("tree", "HEAD^{tree}"))
        }
        meta["clean"] = not p.git(
            HERE,
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "status",
            "--porcelain=v1",
            "--untracked-files=normal",
        )
        require(meta["clean"], "dirty measurement checkout")
        meta["sources_sha256"] = {
            src.relative_to(UNIT).as_posix(): hashlib.sha256(src.read_bytes()).hexdigest()
            for src in (
                Path(__file__).resolve(),
                Path(solver.__file__),
                Path(warm.__file__),
                Path(warm.optimizer.__file__),
                HERE / "protocol.md",
            )
        }
        result = run(args.family, args.raw_dir)
        result["decisions"] = {
            k: {
                str(scale): classify(result["arms"], k, i)
                for i, scale in enumerate((0.8, 1.0, 1.2))
            }
            for k in CAPS
        }
        payload = (
            json.dumps({**meta, **result}, sort_keys=True, allow_nan=False, separators=(",", ":"))
            + "\n"
        )
        require(len(payload.encode()) <= 8 << 20, "8 MiB receipt budget")
    except (OSError, ValueError, KeyError, IndexError, TypeError, MemoryError) as exc:
        result = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            "error": str(exc),
        }
        payload = json.dumps({**meta, **result}, sort_keys=True) + "\n"
    pending = dest / ".pending"
    with pending.open("x") as handle:
        handle.write(payload)
    pending.rename(dest / "receipt.json")
    print(result["status"])
    return int("arms" not in result)


if __name__ == "__main__":
    sys.exit(main())
