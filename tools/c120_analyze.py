#!/usr/bin/env python3
"""Analyze C120 only after all four strong inventory and launch gates pass."""

import argparse
from datetime import datetime
import json
from pathlib import Path
from statistics import median

from c2_gate import GateError, strict_json
from run_bounded import sha256
from c118_start_inventory import require_inventory
import c117_analyze as previous
from c120_nominal_server import ORDER, CAP, save_new


def screen_decision(pairs):
    medians = {key: median(pair["gain_percent"][key] for pair in pairs)
               for key in previous.METRICS}
    primary = "warm_first_final_s"
    protected = ("warm_decode_s", "cold_decode_s",
                 "cold_first_final_s", "cold_prefill_s")
    go = medians[primary] >= 5 and all(pair["gain_percent"][primary] > 0 for pair in pairs) and \
         all(medians[key] >= -5 for key in protected)
    return go, medians, primary, protected


def analyze(root):
    frozen = strict_json((root / "preflight.json").read_text())
    policy = strict_json((root / "confirm-policy.json").read_text())
    resource = strict_json((root / "resource-policy.json").read_text())
    if policy["order"] != [row[0] for row in ORDER] or \
       sha256(root / "confirm-policy.json") != frozen["confirm_policy_sha256"]:
        raise GateError("C120 frozen screen policy changed")
    power = {key: resource["power"][key] for key in ("source", "profile")}
    first = strict_json((root / "raw" / f"{ORDER[0][0]}.receipt.json").read_text())
    commit = first["measurement_commit"]
    if type(commit) is not str or len(commit) != 40:
        raise GateError("C120 measurement commit missing")
    rows = []
    prefix = ORDER[0][0].split("-p", 1)[0]
    for run_id, arm, pair in ORDER:
        receipt_path = root / "raw" / f"{run_id}.receipt.json"
        receipt = strict_json(receipt_path.read_text())
        inventory_path = root / "raw" / f"{run_id}.start-inventory.receipt.json"
        inventory = strict_json(inventory_path.read_text())
        launch_path = root / "raw" / f"{run_id}.launch.json"
        launch = strict_json(launch_path.read_text())
        if receipt.get("run_id") != run_id or receipt.get("measurement_commit") != commit or \
           receipt.get("status") != "PASS_SCREEN_ARM_TESTED_SCOPE" or \
           receipt.get("model_launch_observed") is not True or \
           receipt.get("start_inventory_receipt_sha256") != sha256(inventory_path) or \
           launch.get("run_id") != run_id or \
           launch.get("start_inventory", {}).get("receipt_sha256") != sha256(inventory_path):
            raise GateError("C120 receipt/launch/inventory identity incomplete: " + run_id)
        launch_at = datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
        require_inventory(root, run_id, inventory, policy=resource,
                          cap_bytes=CAP, expected_power=power, duration_s=60,
                          now=launch_at, max_age_s=3)
        # The frozen C117 per-request validator is reused only after the
        # stronger prospective inventory and launch chain has passed.
        rows.append(previous.run_row(root, pair, arm, commit, resource,
                                     run_prefix=prefix))
    pairs = []
    for pair in (1, 2):
        control = next(row for row in rows if row["pair"] == pair and row["arm"] == "control")
        candidate = next(row for row in rows if row["pair"] == pair and row["arm"] == "candidate")
        gains = {key: 100 * (control["metrics"][key] - candidate["metrics"][key]) /
                 control["metrics"][key] for key in previous.METRICS}
        pairs.append({"pair": pair, "control": control["run_id"],
                      "candidate": candidate["run_id"], "gain_percent": gains,
                      "start_delta_candidate_minus_control_c":
                      [b-a for a, b in zip(control["start_cpu_gpu_nvme_c"],
                                           candidate["start_cpu_gpu_nvme_c"])]})
    go, medians, primary, protected = screen_decision(pairs)
    timing = {"schema": "c120-timing-pairs-v1", "measurement_commit": commit,
              "runs": rows, "pairs": pairs, "median_paired_gain_percent": medians,
              "start_regime": "OPERATIONAL_WARM_NO_NARROW_THERMAL_MATCH"}
    decision = {"schema": "c120-decision-v1",
                "status": "SCREEN_GO_OPERATIONAL_NOMINAL153" if go else
                          "NO_GO_SCREEN_OPERATIONAL_NOMINAL153",
                "measurement_commit": commit,
                "primary": primary, "protected": list(protected),
                "pairs": pairs, "median_paired_gain_percent": medians,
                "old_failures_preserved": ["C100 NO_GO_CONFIRM",
                                           "C117 FAIL_RESOURCES_OR_EVIDENCE"],
                "M3": "C52B_TESTED_SCOPE_UNCHANGED", "M4": "NOT_DEMONSTRATED",
                "next_action": "directed warm153 decode trace under new protocol",
                "default_changed": False, "publication": "LOCAL_ONLY"}
    manifest = {"schema": "c120-manifest-v1", "measurement_commit": commit,
                "raw": {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
                        for path in sorted((root / "raw").iterdir()) if path.is_file()}}
    return timing, decision, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    timing, decision, manifest = analyze(root)
    for name, row in (("timing-pairs.json", timing),
                      ("decision.json", decision), ("manifest.json", manifest)):
        save_new(root / name, row)
    print(json.dumps({"status": decision["status"],
                      "median_paired_gain_percent": decision["median_paired_gain_percent"]}))


if __name__ == "__main__":
    main()
