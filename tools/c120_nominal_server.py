#!/usr/bin/env python3
"""Prospective four-arm nominal153 server screen with per-arm start receipts."""

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c9_server_admission import MODEL
from c17_thermal_recovery import no_other_model
from host_resource_policy import GIB, validate_resource_protocol
from run_bounded import relevant_environment, sha256
import c112_nominal_session_base as base
import c117_operational_nominal_server as previous
from c118_start_inventory import collect, require_inventory

CAP = 18 * GIB
ORDER = (("c120-p1-control", "control", 1),
         ("c120-p1-candidate", "candidate", 1),
         ("c120-p2-candidate", "candidate", 2),
         ("c120-p2-control", "control", 2))
ROOT_NAME = "c120-nominal153-20260929T1331Z"
EPOCH_START_UTC = "2026-09-29T13:31:15+00:00"
EPOCH_WALL_S = 12 * 3600
EPOCH_PHYSICAL_S = 8 * 3600
CAMPAIGN_WRAPPER_FILE = None


def save_new(path, value):
    with Path(path).open("x") as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")


def budget(root, remaining):
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(EPOCH_START_UTC)
    wall = (start + timedelta(seconds=EPOCH_WALL_S) - now).total_seconds()
    # Count live units once, by their own receipts. The initial live host
    # inventory and model-free scope smoke have a separate reserved allowance.
    spent = 120.0
    prefix = ORDER[0][0].split("-p", 1)[0]
    for path in sorted((root / "raw").glob(f"{prefix}-p*-*.receipt.json")):
        if ".start-inventory." in path.name:
            continue
        row = strict_json(path.read_text())
        begin = datetime.fromisoformat(row["started_utc"])
        end = datetime.fromisoformat(row["ended_utc"])
        if end < begin:
            raise GateError("C120 physical receipt chronology invalid")
        spent += (end - begin).total_seconds()
    physical = EPOCH_PHYSICAL_S - spent
    reserve = remaining * (600 + 60) + 600
    if min(wall, physical) < reserve:
        raise GateError("C120 epoch cannot admit remaining arms and closure")
    return {"utc": now.isoformat(), "remaining_arms": remaining,
            "wall_remaining_s": wall, "physical_remaining_lower_bound_s": physical,
            "worst_case_s": reserve,
            "physical_spent_s": spent,
            "method": "initial live allowance plus unique arm receipt intervals"}


def screen_policy(root):
    return {"schema": "c120-screen-policy-v1", "status": "FROZEN_BEFORE_MODEL",
            "order": [run for run, _, _ in ORDER], "pairs": 2,
            "primary": "warm first_final_content_s",
            "protected": ["warm decode_s", "cold decode_s",
                          "cold first_final_content_s", "cold prefill_s",
                          "answer/prefix/resources/identity/inventory"],
            "gain_formula": "100*(control-candidate)/control per pair",
            "screen_go": "median primary >=5%; both pairs positive; all four protected timing medians >=-5%; all other gates PASS",
            "start": {"mode": "OPERATIONAL_WARM", "inventory_per_arm_s": 60,
                      "max_gap_s": 1.5, "max_launch_age_s": 3,
                      "narrow_thermal_match": False},
            "cap_bytes": CAP, "swap_max_bytes": 0,
            "input_sha256": sha256(root / "session-input.json"),
            "campaign_wrapper_sha256": sha256(CAMPAIGN_WRAPPER_FILE) if CAMPAIGN_WRAPPER_FILE else None,
            "historical_c117_effective_sha256": sha256(base.REPO / "results/c117-operational-nominal-server-20260929T1058Z/decision-effective.json"),
            "default_changed": False}


def make(root, spec):
    run_id, arm, pair = spec
    protocol, config = base.make(root, arm)
    config["suite"] = "c120nominal"
    protocol["schema_version"] = "c120-protocol-v1"
    protocol["protocol_id"] = run_id + "-v1"
    protocol["identity"]["config_sha256"] = server.digest(config)
    old = protocol.pop("c97")
    protocol["c120"] = {"run_id": run_id, "arm": arm, "pair": pair,
                        "order_index": ORDER.index(spec) + 1,
                        "model_stat": old["model_stat"],
                        "backend_tree": old["backend_tree"],
                        "runner_sha256": sha256(__file__),
                        "campaign_wrapper_sha256": sha256(CAMPAIGN_WRAPPER_FILE) if CAMPAIGN_WRAPPER_FILE else None,
                        "screen_policy_sha256": sha256(root / "confirm-policy.json")}
    protocol["start_inventory"] = {"schema": "c120-start-inventory-v1",
                                    "duration_s": 60, "max_age_s": 3,
                                    "policy_sha256": sha256(root / "resource-policy.json")}
    validate_resource_protocol(protocol)
    return protocol, config


def freeze(root):
    if root.name != ROOT_NAME or not (root / "raw").is_dir() or \
       not (root / "protocols").is_dir():
        raise GateError("C120 new root/raw/protocols required")
    admission = budget(root, len(ORDER))
    save_new(root / "epoch.json", {"schema": "c120-epoch-v1",
        "epoch_start_utc": EPOCH_START_UTC, "wall_limit_s": EPOCH_WALL_S,
        "physical_limit_s": EPOCH_PHYSICAL_S, "raw_limit_bytes": 20 * GIB,
        "authorization": "owner order after C119", "old_epoch": "C55-C119 CLOSED"})
    save_new(root / "confirm-policy.json", screen_policy(root))
    save_new(root / "budget-admission.json", admission)
    for spec in ORDER:
        p, c = make(root, spec)
        save_new(root / "protocols" / f"{spec[0]}.json", p)
        save_new(root / f"{spec[0]}-config.json", c)
    save_new(root / "preflight.json", {"schema": "c120-freeze-v1",
        "utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_sha256": sha256(root / "snapshot.json"),
        "resource_policy_sha256": sha256(root / "resource-policy.json"),
        "input_sha256": sha256(root / "session-input.json"),
        "confirm_policy_sha256": sha256(root / "confirm-policy.json"),
        "protocol_sha256": {s[0]: sha256(root / "protocols" / f"{s[0]}.json") for s in ORDER},
        "config_sha256": {s[0]: sha256(root / f"{s[0]}-config.json") for s in ORDER},
        "status": "FROZEN_NOT_MEASURED"})


def frozen(root, spec):
    run_id = spec[0]
    p, c = make(root, spec)
    pre = strict_json((root / "preflight.json").read_text())
    files = [(root / "snapshot.json", pre["snapshot_sha256"]),
             (root / "resource-policy.json", pre["resource_policy_sha256"]),
             (root / "session-input.json", pre["input_sha256"]),
             (root / "confirm-policy.json", pre["confirm_policy_sha256"]),
             (root / "protocols" / f"{run_id}.json", pre["protocol_sha256"][run_id]),
             (root / f"{run_id}-config.json", pre["config_sha256"][run_id])]
    if any(sha256(path) != expected for path, expected in files) or \
       p != strict_json(files[-2][0].read_text()) or \
       c != strict_json(files[-1][0].read_text()) or \
       screen_policy(root) != strict_json((root / "confirm-policy.json").read_text()):
        raise GateError("C120 frozen source/protocol/config/input changed")
    return p, c


def run(root, spec, commit):
    run_id = spec[0]
    failure = None
    inv_receipt = None
    raw = None
    maxima = None
    launched = False
    started = datetime.now(timezone.utc)
    try:
        budget(root, len(ORDER) - ORDER.index(spec))
        actual = base.git("rev-parse", "HEAD")
        if actual != commit:
            raise GateError(f"measurement SHA mismatch: supplied {commit}, HEAD {actual}")
        if base.git("status", "--porcelain") or relevant_environment(os.environ):
            raise GateError("measurement worktree/environment changed")
        scope = server.cgroup_state()
        if not scope or scope["memory_max"] != CAP or scope["swap_max"] != 0:
            raise GateError("C120 parent scope cap/swap invalid")
        protocol, config = frozen(root, spec)
        for prior in ORDER[:ORDER.index(spec)]:
            receipt = strict_json((root / "raw" / f"{prior[0]}.receipt.json").read_text())
            if receipt["status"] != "PASS_SCREEN_ARM_TESTED_SCOPE":
                raise GateError("C120 earlier arm failed; family closed")
        no_other_model()
        policy = strict_json((root / "resource-policy.json").read_text())
        power = {key: policy["power"][key] for key in ("source", "profile")}
        inv_receipt = collect(root, run_id, policy=policy, cap_bytes=CAP,
                              expected_power=power, duration_s=60)
        save_new(root / "raw" / f"{run_id}.start-inventory.receipt.json", inv_receipt)
        require_inventory(root, run_id, inv_receipt, policy=policy, cap_bytes=CAP,
                          expected_power=power, duration_s=60)
        args = SimpleNamespace(run_id=run_id, protocol=root / "protocols" / f"{run_id}.json",
                               suite="c120nominal", model="target120b")
        code = server.run(args, protocol, config, base.tasks(root), MODEL)
        launched = (root / "raw" / f"{run_id}.launch.json").is_file()
        raw = strict_json((root / "raw" / f"{run_id}.json").read_text())
        maxima = previous.validate_run(root, spec, protocol, config, raw)
        if code != 0:
            raise GateError("C120 server runner exit failure")
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        launched = (root / "raw" / f"{run_id}.launch.json").is_file()
    receipt = {"schema": "c120-arm-receipt-v1", "run_id": run_id,
               "arm": spec[1], "pair": spec[2], "measurement_commit": commit,
               "started_utc": started.isoformat(),
               "ended_utc": datetime.now(timezone.utc).isoformat(),
               "status": "PASS_SCREEN_ARM_TESTED_SCOPE" if failure is None else
                         ("FAIL_RESOURCES_OR_EVIDENCE" if launched else "FAIL_HARNESS_PREMODEL"),
               "reason": failure, "model_launch_observed": launched,
               "stop_reasons": raw.get("stop_reasons") if raw else None,
               "completed_requests": len(raw["results"]) if raw else 0,
               "start_inventory_receipt_sha256": sha256(root / "raw" / f"{run_id}.start-inventory.receipt.json") if inv_receipt else None,
               "raw_sha256": sha256(root / "raw" / f"{run_id}.json") if raw else None,
               "maxima": maxima, "default_changed": False}
    if inv_receipt:
        last = strict_json((root / "raw" / f"{run_id}.start-inventory.jsonl").read_text().splitlines()[-1])
        sensor = strict_json((root / "resource-policy.json").read_text())["nvme"][0]["sensor"]
        obs = last["observation"]
        receipt["matched_start"] = {"status": "OPERATIONAL_WARM_START_OBSERVED",
            "temperature_c": [obs["thermal"]["cpu_tctl_c"],
                              obs["gpu"]["temperature_c"],
                              obs["thermal"]["nvme_composite_by_sensor"][sensor]],
            "power": obs["power"], "inventory_sha256": inv_receipt["sha256"]}
    save_new(root / "raw" / f"{run_id}.receipt.json", receipt)
    print(json.dumps(receipt, allow_nan=False))
    return 0 if failure is None else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "run"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--run-id", choices=[row[0] for row in ORDER])
    parser.add_argument("--measurement-commit")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == "freeze":
        freeze(root)
    else:
        if not args.run_id or not args.measurement_commit:
            parser.error("run requires run ID and measurement commit")
        raise SystemExit(run(root, next(row for row in ORDER if row[0] == args.run_id),
                             args.measurement_commit))


if __name__ == "__main__":
    main()
