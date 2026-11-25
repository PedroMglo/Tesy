"""Screen a completed four-arm witness family against the original C294 decode."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UNIT))
import cache_boundary as boundary  # noqa: E402
from scores import describe, freeze_tables  # noqa: E402
from warm_policy_controls.replay import EXPERT_BYTES, replay  # noqa: E402
from warm_route_reference.verify import PROMPT, check_witness, witness_rows  # noqa: E402
from warm_routes40.boundary import verify as verify_boundary  # noqa: E402
from warm_routes40.witness import compare_tpr  # noqa: E402
from warm_routes40.witness import read as read_witness  # noqa: E402

C286_RECEIPT = "1288f59b44a1ddd69eecd52778f4f9b56e354d60973fdbf48c25175fe43796f4"
ARM_ORDER = [("nominal153", "OFF"), ("nominal153", "ON"), ("code153", "ON"), ("code153", "OFF")]


def read_pinned(path, digest):
    data = path.read_bytes()
    boundary.require(hashlib.sha256(data).hexdigest() == digest, "digest mismatch for " + path.name)
    return data


def family_inputs(family, family_sha):
    receipt = json.loads(read_pinned(family / "receipt.json", family_sha))
    arms = receipt["arms"]
    boundary.require(
        receipt["status"] == "PASS_WARM_ROUTE_FAMILY"
        and receipt["not_run"] == []
        and receipt["model_launch_receipts"] == 4
        and [(arm["case"], arm["mode"]) for arm in arms] == ARM_ORDER
        and len({arm["run_id"] for arm in arms}) == 4,
        "four independent completed arms required",
    )
    plan = json.loads(read_pinned(family / "protocol.json", receipt["plan_sha256"]))
    boundary.require(
        plan["schema"] == "tesy-warm-route-family-v1"
        and plan["measurement_commit"] == receipt["measurement_commit"]
        and plan["order"] == [list(pair) for pair in ARM_ORDER],
        "family plan or commit mismatch",
    )
    raw = family / "raw"
    for number, arm in enumerate(arms, 1):
        mode, case, unit = arm["mode"], arm["case"], arm["run_id"]
        suffix = f"-{number}-{case}-{mode.lower()}"
        native = Path(arm["native_dir"])
        boundary.require(
            arm["status"] == "PASS_WARM_ROUTE_ARM"
            and arm["scope_returncode"] == 0
            and arm["monitor_stop"] is None
            and arm["process_and_scope_closed"] is True
            and unit == plan["unit_stem"] + suffix
            and native.parts == ("raw", unit + ".native"),
            "failed, unclosed or misplaced arm",
        )
        monitor = json.loads(read_pinned(raw / (unit + ".json"), arm["monitor_sha256"]))
        launch = json.loads(read_pinned(raw / (unit + ".launch.json"), arm["launch_sha256"]))
        read_pinned(raw / (unit + ".start-inventory.receipt.json"), arm["inventory_sha256"])
        locked = json.loads(
            read_pinned(family / (unit + ".json"), launch["resource_protocol_sha256"])
        )
        boundary.require(
            monitor["run_id"] == launch["run_id"] == unit
            and monitor["returncode"] == 0
            and monitor["stop_reason"] is None
            and monitor["process_identity"] == launch["process_identity"]
            and monitor["start_inventory"] == launch["start_inventory"]
            and arm["inventory_sha256"] == monitor["start_inventory"]["receipt_sha256"]
            and monitor["limits"]["resource_protocol_sha256"] == launch["resource_protocol_sha256"]
            and locked == dict(plan, execution_scope_unit=unit)
            and monitor["binary_sha256"] == launch["binary_sha256"] == plan["executable_sha256"],
            "inconsistent physical receipts",
        )
        gold = plan["independent_reference"][case]
        hashes = arm["native_sha256"]
        boundary.require(
            arm["P_sha256"] == gold["P"]
            and arm["F_sha256"] == gold["F"]
            and hashes["all33.logits.f32"] == gold["gold"],
            "unqualified numeric anchor",
        )
        native = family / native
        for name in ("all33.logits.f32", "initial.json", "result.json", "events.tsv"):
            with (native / name).open("rb") as stream:
                boundary.require(
                    hashlib.file_digest(stream, "sha256").hexdigest() == hashes[name],
                    "changed native " + name,
                )
        if mode == "OFF":
            boundary.require(
                "prefix-routes.bin" not in hashes and not (native / "prefix-routes.bin").exists(),
                "OFF emitted TPR1",
            )
    return arms


def case_inputs(family, case, arms):
    by_mode = {arm["mode"]: arm for arm in arms if arm["case"] == case}
    states, witnesses = {}, {}
    for mode, arm in by_mode.items():
        native = family / arm["native_dir"]
        hashes = arm["native_sha256"]
        boundary_file = native / "boundary-i.json"
        read_pinned(boundary_file, hashes["boundary-i.json"])
        states[mode] = verify_boundary(case, boundary_file)["slot_vector_sha256"]
        boundary.require(states[mode] == arm["I_sha256"], "arm I receipt differs from its snapshot")
        witnesses[mode] = read_pinned(native / "routed-witness.bin", hashes["routed-witness.bin"])
    boundary.require(states["OFF"] == states["ON"], "different contemporary slot vectors at I")
    boundary.require(witnesses["OFF"] == witnesses["ON"], "contemporary routed witnesses differ")
    wrt = witnesses["ON"]
    graphs, rows = read_witness(wrt)
    ordered = check_witness(
        case, ((call - 9, layer, pos, ids) for call, _, layer, pos, ids in rows if call >= 10)
    )
    boundary.require(
        all(
            arm["decode_sha256"] == ordered
            and arm["groups"] == len(rows)
            and arm["ubatches"] == len(graphs)
            for arm in by_mode.values()
        ),
        "contemporary rank or graph receipt differs",
    )
    del rows, graphs
    on = by_mode["ON"]
    raw = read_pinned(
        family / on["native_dir"] / "prefix-routes.bin", on["native_sha256"]["prefix-routes.bin"]
    )
    compare_tpr(wrt, raw)
    return raw, states["ON"]


def evaluate(family, family_sha, historical):
    arms = family_inputs(family, family_sha)
    cross = json.loads(read_pinned(UNIT / "cross_prefix_evidence/receipt.json", C286_RECEIPT))
    cases = {}
    for case, length in PROMPT.items():
        raw, state_i = case_inputs(family, case, arms)
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
            boundary.require(
                facts["boundary_slot_vector_sha256"] == state_i, "initial slots differ"
            )
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


def report_text(result):
    """Keep each ranked set of integer expert IDs visible on one line."""
    pretty = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    return re.sub(
        r'("top40_by_score_then_id": )(\[(?:\s*\d+\s*,?)+\])',
        lambda group: group[1] + json.dumps(json.loads(group[2])),
        pretty,
    ) + "\n"


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
    except (TypeError, IndexError, ValueError, KeyError, OSError) as exc:
        out = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            "reason": str(exc),
        }
    tmp = a.new_output_dir / ".pending"
    with tmp.open("x") as stream:
        stream.write(report_text(out))
    tmp.rename(a.new_output_dir / "receipt.json")
    print(out["status"])
    raise SystemExit(int("cases" not in out))
