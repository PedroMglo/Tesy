#!/usr/bin/env python3
"""Fail-closed compact closure of the stopped C17 thermal recovery unit."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from c8_observer_runner import program_physical_consumed

RUNS = (
    ("c17-t0-p8-init", "PASS_QUALIFIED"),
    ("c17-t0-p12-init", "PASS_QUALIFIED"),
    ("c17-t1-p8-smoke78", "PASS_QUALIFIED"),
    ("c17-t1-p12-smoke78", "PASS_QUALIFIED"),
    ("c17-t2-p8-cold513", "FAIL_THERMAL_GUARD"),
    ("c17-t2-p12-cold513", "FAIL_THERMAL_GUARD"),
)
TOKEN_SHA = "e19cb14e4c38e8f1b153a58c1d3450ded2b402d82f5798961a1246285099d316"
OLD_FAILURES = ("c9-g3-prefix-on", "c10b-g3-short513",
                "c13-g1-prefix-on", "c14-g3-short513")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_x(path, data):
    with path.open("x") as out:
        json.dump(data, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    records = []
    for run_id, expected in RUNS:
        receipt = strict_json((root / (run_id + "-receipt.json")).read_text())
        idle = strict_json((root / (run_id + "-idle.json")).read_text())
        if receipt["status"] != expected or idle["status"] != "PASS" or \
                idle["qualifying_duration_s"] < 300 or idle["max_gap_qualifying_s"] > 1:
            raise GateError("run/admission status differs from frozen closure: " + run_id)
        raw = root / "raw" / (run_id + ".json")
        if sha(raw) != receipt["raw_sha256"]:
            raise GateError("raw SHA mismatch: " + run_id)
        failure = None
        if expected == "FAIL_THERMAL_GUARD":
            failure = strict_json((root / (run_id + "-failure-analysis.json")).read_text())
            if failure["classification"] != expected or failure["reasons"] or \
                    failure["input_token_ids_sha256"] != TOKEN_SHA or \
                    failure["completed_requests"] != 0 or \
                    failure["cgroup"]["swap_end"] != 0 or \
                    any(v for scope in failure["cgroup"]["event_delta"].values()
                        for v in scope.values()):
                raise GateError("thermal failure evidence invalid: " + run_id)
        records.append({"run_id": run_id, "arm": receipt["arm"], "phase": receipt["phase"],
                        "order": receipt["order"], "status": expected,
                        "measurement_commit": receipt["measurement_commit"],
                        "idle_duration_s": idle["duration_s"],
                        "idle_max_gap_qualifying_s": idle["max_gap_qualifying_s"],
                        "idle_start_temperatures_c": {"cpu": idle["end"]["cpu_c"],
                                                       "gpu": idle["end"]["gpu"]["temperature_c"],
                                                       "nvme": idle["end"]["nvme_c"]},
                        "returncode": receipt["returncode"],
                        "stop_reasons": receipt["stop_reasons"],
                        "server_elapsed_s": receipt["server_elapsed_s"],
                        "completed_requests": receipt["completed_requests"],
                        "raw_sha256": receipt["raw_sha256"],
                        "output_message_sha256": receipt.get("output_message_sha256"),
                        "prefill_s": receipt.get("prefill_s"),
                        "decode_s": receipt.get("decode_s"),
                        "maxima": failure["maxima"] if failure else receipt["maxima"],
                        "first_guard_exceed_elapsed_s": failure["first_guard_exceed_elapsed_s"] if failure else None,
                        "first_guard_exceed_utc": failure["first_guard_exceed_utc"] if failure else None,
                        "cgroup": failure["cgroup"] if failure else None})
    series = root / "thermal-series.jsonl"
    samples = series.read_text().splitlines()
    if len(samples) != sum(strict_json((root / (rid + "-idle.json")).read_text())["sample_count"]
                           for rid, _ in RUNS):
        raise GateError("aggregate idle series sample count mismatch")
    previous_idle = 394.4515725659985
    c17_idle = sum(row["idle_duration_s"] for row in records)
    raw_server = program_physical_consumed()
    used_s = raw_server + previous_idle + c17_idle
    timing = {"schema": "c17-thermal-timing-pairs-v1", "status": "NO_COMPLETED_513_PAIR",
              "primary_metric": "completion-fenced API request elapsed seconds",
              "gain_formula": "100*(P8-P12)/P8", "paired_gains_pct": [],
              "pair1": {"order": ["P8", "P12"], "control": "FAIL_THERMAL_GUARD",
                        "candidate": "FAIL_THERMAL_GUARD", "gain_pct": None},
              "pair2": {"order": ["P12", "P8"], "status": "NOT_RUN",
                        "reason": "both first-pair arms reached CPU95 guard"},
              "historical_c8_gain_pct": 16.593707538111605,
              "historical_c8_scope": "separate 496+32 teacher-forced preload probe; excluded from server pairs"}
    resources = {"schema": "c17-resource-summary-v1", "status": "COMPLETE_FOR_EXECUTED_ARMS",
                 "arms": records, "idle_series": {"path": "thermal-series.jsonl",
                                                  "sample_count": len(samples),
                                                  "sha256": sha(series),
                                                  "git_policy": "local raw, ignored"},
                 "gpu_compute_after": "none listed by nvidia-smi",
                 "port_18367_after": "free by ss"}
    decision = {"schema": "c17-thermal-recovery-decision-v1",
                "status": "THERMAL_LIMIT_REPRODUCED",
                "reason": "Both P8 and P12 fresh-process cold513 first-pair arms exceeded the unchanged CPU95 C guard before any completed request under the reported changed physical placement.",
                "cooling_condition": "changed_physical_placement (owner report)",
                "ambient_temperature": "UNKNOWN",
                "gates": {"historical_reaudit": "PASS_LIMITED_SCOPE_FOUR_OLD_FAILS_PRESERVED",
                          "model_free": "PASS_50_TESTS",
                          "host_and_scope_preflight": "PASS",
                          "T0_init": "PASS_BOTH_PROFILES",
                          "T1_smoke78": "PASS_BOTH_PROFILES",
                          "T2_cold513": "FAIL_THERMAL_GUARD_BOTH_PROFILES",
                          "T3_inverted": "NOT_RUN_STOP_RULE",
                          "same_profile_8k_full_logits": "NOT_RUN",
                          "M3": "NOT_RUN", "M4": "NOT_RUN",
                          "C15": "SOURCE_ONLY_NOT_COMPILED_NOT_MEASURED"},
                "executed_runs": records,
                "not_run_513_arms": ["c17-t3-p12-cold513", "c17-t3-p8-cold513"],
                "old_fails_preserved": list(OLD_FAILURES),
                "prior_c16_block_preserved": "THERMAL_PREFLIGHT_BLOCKED_IDLE_CADENCE_NO_MODEL",
                "claim_limits": ["No completed 513 pair, so no new paired speed gain",
                                 "The cooler placement was owner-reported; no ambient sensor or causal attribution",
                                 "Short 78-ID and init admissions do not establish 513-ID or sustained service",
                                 "No 8K same-profile full-logit, exact-prefix, functional-quality or sustained claim",
                                 "This is a limit of these P8/P12 ub32 preload-on 8K profiles, not of all 120B configurations"],
                "budget": {"physical_limit_s": 57600, "previous_raw_server_plus_c17_server_s": raw_server,
                           "c16_idle_s": previous_idle, "c17_idle_s": c17_idle,
                           "conservative_program_physical_used_s": used_s,
                           "remaining_s": 57600-used_s},
                "next_action": "Pivot model-free: analyze whether reducing CPU batch-thread concurrency in a new P12 profile could lower peak heat without losing the useful preload path; freeze numeric/reference and resource gates before any new cold513 run. Do not profile C15 waves under a guard-stopped workload.",
                "default_changed": False,
                "closed_utc": datetime.now(timezone.utc).isoformat()}
    write_x(root / "timing-pairs.json", timing)
    write_x(root / "resource-summary.json", resources)
    write_x(root / "decision.json", decision)
    print(json.dumps({"status": decision["status"], "used_s": used_s,
                      "executed": len(records), "513_pairs_completed": 0}, allow_nan=False))


if __name__ == "__main__":
    main()
