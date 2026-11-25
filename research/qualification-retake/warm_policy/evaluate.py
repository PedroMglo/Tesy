"""Screen a completed four-arm witness family against the original C294 decode."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UNIT))
import cache_boundary as boundary  # noqa: E402
from scores import describe, freeze_tables  # noqa: E402
from warm_policy_controls.replay import EXPERT_BYTES, replay  # noqa: E402
from warm_route_reference.verify import PROMPT, check_witness, witness_rows  # noqa: E402
from warm_routes40.witness import compare_tpr  # noqa: E402

C286_RECEIPT = "1288f59b44a1ddd69eecd52778f4f9b56e354d60973fdbf48c25175fe43796f4"
ARM_ORDER = [("nominal153", "OFF"), ("nominal153", "ON"), ("code153", "ON"), ("code153", "OFF")]


def read_pinned(path, digest):
    data = path.read_bytes()
    boundary.require(hashlib.sha256(data).hexdigest() == digest, "digest mismatch for " + path.name)
    return data


def evaluate(family, family_sha, historical):
    receipt = json.loads(read_pinned(family / "receipt.json", family_sha))
    arms = receipt["arms"]
    boundary.require(
        receipt["status"] == "PASS_WARM_ROUTE_FAMILY"
        and [(r["case"], r["mode"]) for r in arms] == ARM_ORDER,
        "four validated arms required",
    )
    cross = json.loads(read_pinned(UNIT / "cross_prefix_evidence/receipt.json", C286_RECEIPT))
    cases = {}
    for case, length in PROMPT.items():
        files = {}
        hashes = {}
        for arm in (a for a in arms if a["case"] == case):
            mode = arm["mode"]
            native = Path(arm["native_dir"])
            boundary.require(
                native.parts == ("raw", arm["run_id"] + ".native"), "unexpected native path"
            )
            hashes[mode] = arm["native_sha256"]
            files[mode] = family / native
        wrt = read_pinned(files["ON"] / "routed-witness.bin", hashes["ON"]["routed-witness.bin"])
        boundary.require(
            wrt
            == read_pinned(
                files["OFF"] / "routed-witness.bin", hashes["OFF"]["routed-witness.bin"]
            ),
            "contemporary routed witnesses differ",
        )
        raw = read_pinned(files["ON"] / "prefix-routes.bin", hashes["ON"]["prefix-routes.bin"])
        compare_tpr(wrt, raw)
        tables = freeze_tables(raw, 8, length - 153, 153, 32)
        stats = {phase: describe(table) for phase, table in tables.items()}
        stats["changed_top40_memberships"] = sum(
            len(set(x["top40_by_score_then_id"]) - set(y["top40_by_score_then_id"]))
            for x, y in zip(stats["I"]["layers"], stats["P"]["layers"], strict=True)
        )
        c286 = cross["arms"][f"c294-{case}-2-on.native"]
        snap = json.loads(
            read_pinned(
                historical
                / "c286-logical-route-policy-cost-20261006/raw"
                / c286["source"]
                / "initial.json",
                c286["source_initial_sha256"],
            )
        )
        tables["C286"] = [layer["route_hotness"] for layer in snap["layers"]]
        summaries = []
        for rep in (2, 3):
            name = f"c294-{case}-{rep}-on"
            root = historical / boundary.CAMPAIGN / "raw"
            pools, facts = boundary.audit_arm(root, name)
            native = root / (name + ".native")
            historical_result = json.loads(
                read_pinned(native / "result.json", facts["source_sha256"]["result.json"])
            )
            groups = witness_rows(native / "events.tsv", case, facts["source_sha256"]["events.tsv"])
            check_witness(case, groups)
            observed = facts["counts"]["decode_publications"]
            reference_end = [
                {e for e, _, state, _ in pool if state == 2}
                for pool in boundary.slots(historical_result["final"])
            ]
            tiers = [layer["native_cache_buffer"] for layer in historical_result["final"]["layers"]]
            boundary.require(tiers == ["CPU"] * 25 + ["CUDA0"] * 11, "changed R0 tier placement")
            policies = {}
            for label, table in tables.items():
                end, layer_stats = replay(pools, groups, scores=table)
                misses = sum(row["misses"] for row in layer_stats)
                cpu = sum(row["misses"] for row in layer_stats[:25])
                restore = sum(len(r - e) for r, e in zip(reference_end, end, strict=True))
                policies[label] = {
                    "misses": misses,
                    "hits": sum(row["hits"] for row in layer_stats),
                    "evictions": sum(row["evictions"] for row in layer_stats),
                    "logical_load_bytes": misses * EXPERT_BYTES,
                    "logical_cuda_destination_bytes": (misses - cpu) * EXPERT_BYTES,
                    "R0_final_identities_missing": restore,
                    "restore_identity_floor_bytes": restore * EXPERT_BYTES,
                    "count_margin_before_10pct_threshold": (9 * observed) // 10 - misses,
                }
                boundary.require(misses + policies[label]["hits"] == 4608, "decode conservation")
            winner = policies["I"]["misses"]
            summaries.append(
                {
                    "arm": name,
                    "R0_publications": observed,
                    "policies": policies,
                    "screen_pass": 10 * winner <= 9 * observed
                    and all(winner < policies[key]["misses"] for key in ("P", "C286")),
                }
            )
        cases[case] = {"rankings": stats, "arms": summaries}
    n_pass = sum(all(a["screen_pass"] for a in c["arms"]) for c in cases.values())
    return {
        "status": ("NO_GO", "INCONCLUSIVE", "GO_FIXTURE_ONLY")[n_pass],
        "scope": "TRACE_DERIVED_DECODE_LOADS_ONLY",
        "family_sha256": family_sha,
        "cases": cases,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", required=True, type=Path)
    p.add_argument("--family-receipt-sha256", required=True)
    p.add_argument("--historical-results", required=True, type=Path)
    p.add_argument("--new-output-dir", required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        out = evaluate(a.family, a.family_receipt_sha256, a.historical_results)
    except (ValueError, KeyError, OSError) as exc:
        out = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            "reason": str(exc),
        }
    tmp = a.new_output_dir / ".pending"
    with tmp.open("x") as stream:
        json.dump(out, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(out["status"])
    raise SystemExit(int("cases" not in out))
