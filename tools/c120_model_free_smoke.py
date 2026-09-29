#!/usr/bin/env python3
"""Real sensors, real E18 scope, real Popen; no model weights or inference."""

import json
from pathlib import Path
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, strict_json
from c118_start_inventory import collect
from host_resource_policy import digest
from run_bounded import sha256


def run(campaign_root):
    root = campaign_root / "model-free-smoke"
    root.mkdir()
    (root / "raw").mkdir()
    policy = strict_json((campaign_root / "resource-policy.json").read_text())
    (root / "resource-policy.json").write_text(
        json.dumps(policy, indent=2, sort_keys=True, allow_nan=False) + "\n")
    cap = 18 * 2**30
    cg = server.cgroup_state()
    if not cg or cg["memory_max"] != cap or cg["swap_max"] != 0 or cg["swap_current"] != 0:
        raise GateError("model-free smoke scope E18/swap invalid")
    run_id = "c120-smoke01"
    power = {key: policy["power"][key] for key in ("source", "profile")}
    inventory = collect(root, run_id, policy=policy, cap_bytes=cap,
                        expected_power=power, duration_s=60)
    receipt_path = root / "raw" / f"{run_id}.start-inventory.receipt.json"
    receipt_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    dummy = root / "dummy-model.bin"
    dummy.write_bytes(b"model-free-smoke")
    backend_root = root / "empty-backend"
    backend_root.mkdir()
    config = {"output_root": str((root / "raw").resolve()),
              "server_command": ["python3", "tools/c120_smoke_server.py"],
              "backend_root": str(backend_root), "explicit_env": {},
              "request_policy": {"max_tokens": 1}, "total_timeout_s": 15}
    old = strict_json((campaign_root / "protocols/c120-p1-control.json").read_text())
    protocol = {"schema_version": "c120-model-free-smoke-v1",
                "campaign_id": root.name, "protocol_id": run_id,
                "resources": old["resources"], "limits": old["limits"],
                "expected_request_ids": [],
                "identity": {"model_sha256": sha256(dummy),
                             "library_sha256": {},
                             "config_sha256": digest(config)},
                "start_inventory": {"schema": "c120-start-inventory-v1",
                    "duration_s": 60, "max_age_s": 3,
                    "policy_sha256": sha256(root / "resource-policy.json")}}
    protocol_path = root / "protocol.json"
    protocol_path.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    args = SimpleNamespace(run_id=run_id, protocol=protocol_path,
                           suite="c120smoke", model="target120b")
    try:
        code = server.run(args, protocol, config, [], dummy)
        launch = strict_json((root / "raw" / f"{run_id}.launch.json").read_text())
        raw = strict_json((root / "raw" / f"{run_id}.json").read_text())
        status = "PASS_MODEL_FREE_ENTRYPOINT" if code == 0 and \
                 launch["start_inventory"]["receipt_sha256"] == sha256(receipt_path) and \
                 raw["stop_reasons"] == [] else "FAIL_MODEL_FREE_ENTRYPOINT"
        row = {"schema": "c120-model-free-smoke-result-v1", "status": status,
               "model_weights_loaded": False, "scope": cg,
               "inventory_receipt_sha256": sha256(receipt_path),
               "launch_sha256": sha256(root / "raw" / f"{run_id}.launch.json"),
               "raw_sha256": sha256(root / "raw" / f"{run_id}.json"),
               "returncode": raw["returncode"], "stop_reasons": raw["stop_reasons"]}
    except Exception as exc:
        row = {"schema": "c120-model-free-smoke-result-v1",
               "status": "FAIL_MODEL_FREE_ENTRYPOINT", "error": str(exc),
               "model_weights_loaded": False, "scope": cg,
               "inventory_receipt_sha256": sha256(receipt_path)}
    (root / "result.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": row["status"], "root": str(root)}))
    return 0 if row["status"] == "PASS_MODEL_FREE_ENTRYPOINT" else 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.root.resolve()))
