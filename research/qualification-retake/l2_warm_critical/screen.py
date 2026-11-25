"""Warm-at-P upper envelopes in the historical C295 fixed-service decode."""

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
from l2_critical import screen as cold  # noqa: E402
from l2_warm_critical import optimizer  # noqa: E402
from warm_route_family.grade import state  # noqa: E402
from warm_route_reference.verify import check_witness, witness_rows  # noqa: E402

p = cold.prefix
require = cold.require
LIMITS = (0, 243, 378)
EXPERT = cold.admission.EXPERT
BASE_SHA = "b5640a5fd78cc28c6b1b708a7cf532526fe1190d5222c6ec64a678315bef1ca3"
BASE_CODE = "2e45383585d5dd3b0da3dfa1d44433100793994b06246fa94fb791c8bf43cc07"


def mark_groups(data, hits, allowed):
    jobs, groups, *_ = data
    records, available = [], {}
    for g in groups:
        records.append([])
        for w in g["need"]:
            layer, expert, *_ = w
            key = layer, expert
            read, copy = jobs[w]["read"], jobs[w]["copy"]
            require(int(read) == read >= 0 and int(copy) == copy >= 0, "component service")
            if w in hits:
                status = "free"
            else:
                require(key not in available, "multiple first decode claims of a key")
                available[key] = w
                status = "eligible" if allowed is None or key in allowed else "cold"
            records[-1].append((key, int(read), int(copy), status))
    return records, available


def verify_witness(data, hits, first, allowed, k, solution, sealed):
    chosen = [tuple(key) for key in solution["chosen"]]
    keys = set(chosen)
    require(
        len(chosen) == len(keys) <= k
        and keys <= first.keys()
        and (allowed is None or keys <= allowed),
        "ineligible or oversized warm witness",
    )
    warm = hits | {first[key] for key in keys}
    require(len(warm) == len(hits) + len(keys), "warm double credit")
    fixed, stats, tiers = cold.maxima(data, warm)
    service = stats["new_max_us"]
    require(
        service == solution["group_max_sum_us"]
        and sealed["service_at_scale_1"]["new_max_us"] - service == solution["gain_us"],
        "witness does not attain optimizer score",
    )
    cheaper = {w: {**j, "read": 0.0 if w in warm else j["read"]} for w, j in data[0].items()}
    scales = []
    for base in sealed["scales"]:
        scale, orig = base["scale"], base["baseline_us"]
        ideal = cold.c295.simulate((cheaper, *data[1:]), None, scale, cold.ARENA)["decode_us"]
        require(
            math.isclose(ideal, fixed + scale * service, rel_tol=0, abs_tol=1e-4), "C295/DP timing"
        )
        if not keys:
            require(ideal == base["ideal_us"], "cold replay changed")
        slack = cold.BUDGET_US - ideal
        scales.append(
            {
                "scale": scale,
                "baseline_us": orig,
                "cold_L2_us": base["ideal_us"],
                "warm_L2_us": ideal,
                "warm_gain_over_cold_us": base["ideal_us"] - ideal,
                "gain_over_baseline_fraction": (orig - ideal) / orig,
                "steps_per_s": 32e6 / ideal,
                "reaches_6": slack >= 0,
                "max_additional_decode_overhead_us": max(0.0, slack),
                "still_missing_us": max(0.0, -slack),
            }
        )
    ncpu = sum(layer < 25 for layer, _ in chosen)
    ingress = {"CPU": ncpu * EXPERT, "CUDA0": (len(chosen) - ncpu) * EXPERT}
    return {
        "capacity_at_P": k,
        "identities_chosen": len(keys),
        "chosen_layer_expert": sorted(keys),
        "charged_ingress_bytes_by_original_tier": ingress,
        "charged_ingress_bytes": len(keys) * EXPERT,
        "decode_hits": len(warm),
        "fixed_nonservice_us": fixed,
        "group_max_sum_us": service,
        "extra_wall_us_scale1": solution["gain_us"],
        "service_by_tier_at_scale1": tiers,
        "scales": scales,
    }


def wrt(family, case, arms):
    _, frozen_i = p.case_inputs(family, case, arms)
    members = [a for a in arms if a["case"] == case]
    off = next(a for a in members if a["mode"] == "OFF")
    require(
        all((a["P_sha256"], a["F_sha256"]) == (off["P_sha256"], off["F_sha256"]) for a in members),
        "WRT P or F differs",
    )
    graphs, rows = p.read(
        p.read_pinned(
            family / off["native_dir"] / "routed-witness.bin",
            off["native_sha256"]["routed-witness.bin"],
        )
    )
    p.check_geometry(graphs, case)
    prefix_keys = {(layer, e) for call, _, layer, _, ranks in rows if call < 9 for e in ranks}
    require(
        prefix_keys and all(0 <= layer < 36 and 0 <= e < 128 for layer, e in prefix_keys),
        "prefix identities",
    )
    require(off["I_sha256"] == frozen_i, "prefix I differs between WRT modes")
    return prefix_keys, off


def trial(raw, name, case, prior, control, prefix_keys, off):
    # Reproduce all three published baselines, the cold receipt, source digests and cuts.
    record = cold.arm(raw, name, control)
    require(record == prior, "cold baseline or conservation changed")
    _, proof = cold.admission.boundary.audit_arm(raw, name)
    require(
        proof["boundary_slot_vector_sha256"] == off["I_sha256"], "historical I differs from WRT"
    )
    directory = raw / (name + ".native")
    hashes = record["source_sha256"]
    initial = json.loads(p.read_pinned(directory / "initial.json", hashes["initial.json"]))
    native = json.loads(p.read_pinned(directory / "result.json", hashes["result.json"]))
    require(
        initial == native["initial"]
        and state(initial) == off["P_sha256"]
        and state(native["final"]) == off["F_sha256"],
        "C294 physical P/F differs from WRT",
    )
    require(
        check_witness(case, witness_rows(directory / "events.tsv", case, hashes["events.tsv"]))
        == off["decode_sha256"],
        "decode ranks differ",
    )
    pools = cold.admission.boundary.slots(initial)
    resident = {(layer, e) for layer, pool in enumerate(pools) for e, _, s, _ in pool if s == 2}
    rows = cold.c295.events(directory / "events.tsv", True)
    hits, n = cold.eligible(rows)
    data = cold.c295.extract(rows)
    require(
        n == record["service_at_scale_1"]["claims"]
        and len(hits) == record["service_at_scale_1"]["hits"],
        "cold increment/decode boundary",
    )
    variants = {}
    for label, allowed in (("any", None), ("prefix_routed", prefix_keys), ("P_resident", resident)):
        groups, first = mark_groups(data, hits, allowed)
        require(len(groups) == 1152 and len(first) + len(hits) == n, "first-use partition")
        optimal = optimizer.resolve(groups, LIMITS)
        require(set(optimal) == set(LIMITS), "missing capacity")
        result = {
            k: verify_witness(data, hits, first, allowed, k, optimal[k], record) for k in LIMITS
        }
        require(
            all(
                result[a]["group_max_sum_us"] >= result[b]["group_max_sum_us"]
                for a, b in zip(LIMITS[:-1], LIMITS[1:], strict=True)
            ),
            "capacity monotonicity",
        )
        variants[label] = {
            "prefix_universe_keys": None if allowed is None else len(allowed),
            "eligible_first_decode_services": len(first)
            if allowed is None
            else len(first.keys() & allowed),
            "by_capacity": result,
        }
    for k in LIMITS:
        any_cost = variants["any"]["by_capacity"][k]["group_max_sum_us"]
        require(
            all(any_cost <= v["by_capacity"][k]["group_max_sum_us"] for v in variants.values()),
            "superset bound",
        )
    return {
        "P_sha256": off["P_sha256"],
        "I_sha256": off["I_sha256"],
        "F_sha256": off["F_sha256"],
        "decode_ranks_sha256": off["decode_sha256"],
        "raw_sha256": hashes,
        "WRT_sha256": off["native_sha256"]["routed-witness.bin"],
        "after_P_capacity": "unlimited",
        "decode_claims": n,
        "cold_start_decode_hits": len(hits),
        "eligibility": variants,
    }


def run(family, raw):
    saved = json.loads(p.read_pinned(UNIT / "l2_critical/evidence/receipt.json", BASE_SHA))
    p.read_pinned(Path(cold.__file__), BASE_CODE)
    p.read_pinned(Path(cold.c295.__file__), cold.C295)
    scenario = json.loads(
        p.read_pinned(
            cold.ROOT / "results/c295-activation-byte-optimistic-scenario-20261006/scenario.json",
            cold.SCENARIO,
        )
    )
    require(
        saved["status"] == "PASS_CONDITIONAL_SCENARIO"
        and saved["scenario_sha256"] == cold.SCENARIO,
        "unqualified cold scenario",
    )
    arms = p.family_inputs(family, p.FAMILY_SHA)
    out = {}
    for case in p.PROMPT:
        prefix_keys, off = wrt(family, case, arms)
        for row in scenario["cases"][case]:
            name = row["run"]
            out[name] = trial(
                raw, name, case, saved["arms"][name], row["service_sensitivity"], prefix_keys, off
            )
    require(set(out) == set(cold.admission.boundary.NAMES), "missing R0 arm")
    return {
        "status": "PASS_CONDITIONAL_WARM_P_BOUNDS",
        "scope": "OFFLINE_FIXED_SERVICE_AFTER_P_INFINITE",
        "family_sha256": p.FAMILY_SHA,
        "cold_receipt_sha256": BASE_SHA,
        "C295_program_sha256": cold.C295,
        "C295_scenario_sha256": cold.SCENARIO,
        "budget_us": cold.BUDGET_US,
        "expert_bytes": EXPERT,
        "arms": out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--family", type=Path, required=True)
    ap.add_argument("--raw-dir", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    require(
        all(
            not a.new_output_dir.resolve().is_relative_to(x.resolve())
            for x in (a.family, a.raw_dir)
        ),
        "protect inputs",
    )
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = 768 * 2**20
    resource.setrlimit(resource.RLIMIT_AS, (min(hard, cap) if hard >= 0 else cap, hard))

    def timeout(*_):
        raise TimeoutError("120s envelope")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    commit, tree = (p.git(HERE, "rev-parse", rev) for rev in ("HEAD", "HEAD^{tree}"))
    clean = not p.git(
        HERE,
        "-c",
        "core.preloadIndex=false",
        "-c",
        "index.threads=1",
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
    )
    a.new_output_dir.mkdir(mode=0o700)
    try:
        require(clean, "dirty measurement checkout")
        out = run(a.family, a.raw_dir)
    except (OSError, ValueError, TypeError, IndexError, KeyError, MemoryError) as exc:
        out = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            "error": str(exc),
        }
    out.update(
        commit=commit,
        tree=tree,
        clean=clean,
        code_sha256={
            path.relative_to(UNIT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__).resolve(),
                Path(optimizer.__file__),
                Path(cold.__file__),
                HERE / "protocol.md",
            )
        },
    )
    pending = a.new_output_dir / ".pending"
    payload = json.dumps(out, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if len(payload.encode()) > 8 * 2**20:
        out = {
            "status": "FAIL_PRESERVED",
            "commit": commit,
            "tree": tree,
            "error": "8 MiB receipt limit",
        }
        payload = json.dumps(out) + "\n"
    with pending.open("x") as f:
        f.write(payload)
    pending.rename(a.new_output_dir / "receipt.json")
    print(out["status"])
    return int("arms" not in out)


if __name__ == "__main__":
    sys.exit(main())
