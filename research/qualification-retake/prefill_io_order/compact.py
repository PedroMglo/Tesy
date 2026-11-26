"""Validate local arm records and export timing and hashes without host identifiers."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import measure


def read(path):
    return json.loads(path.read_text())


def compact(raw, new):
    new.mkdir(exist_ok=False)
    receipt = read(raw / "receipt.json")
    files = [p for p in raw.rglob("*") if p.is_file()]
    hashes = {
        p.relative_to(raw).as_posix(): {"sha256": measure.io.sha256(p), "bytes": p.stat().st_size}
        for p in sorted(files)
    }
    if receipt["decision"] == "FAIL":
        value = {"decision": "FAIL", "receipt": receipt, "raw_manifest": hashes}
    else:
        frozen = read(raw / "freeze.json")
        measure.require(frozen["schedule_sha256"] == measure.PLAN_SHA, "plan")
        plan = read(measure.HERE / "schedule.json")
        arms = [read(raw / f"arm-{n}-{mode}.json") for n, mode in enumerate(measure.ORDER, 1)]
        verdict, pairs = measure.decision(arms)
        measure.require(
            verdict == receipt["decision"] and pairs == receipt["pairs"], "pair reproduction"
        )
        gold = arms[0]["payload_sha256"]
        groups = []
        for arm in arms:
            measure.require(gold == arm["payload_sha256"] and len(gold) == 96, "all hashes")
            one = []
            for row, g in zip(arm["groups"], plan["groups"], strict=True):
                measure.require(
                    row["order_indices"] == measure.ordered_indices(g["jobs"], arm["mode"]),
                    "dispatch",
                )
                calls = [s for j in row["jobs"] for s in j["read_spans_ns"]]
                measure.require(
                    len(calls) == 3 * len(g["jobs"])
                    and sum(b - a for a, b in calls) == row["read_worker_ns"],
                    "worker µs",
                )
                measure.require(
                    row["demand_ns"]
                    == max(j["finish_ns"] for j in row["jobs"] if j["role"] == "demand"),
                    "demand",
                )
                one.append(
                    {
                        k: row[k]
                        for k in (
                            "layer",
                            "demand_ns",
                            "drain_ns",
                            "read_worker_ns",
                            "read_union_ns",
                            "release_cost_ns",
                            "disk_delta",
                        )
                    }
                )
            groups.append(one)
        inventory = read(raw / "inventory-receipt.json")
        value = {
            **receipt,
            "raw_manifest": hashes,
            "protocol_sha256": frozen["protocol_sha256"],
            "commit": frozen["commit"],
            "tree": frozen["tree"],
            "policy_sha256": frozen["policy_sha256"],
            "placement_sha256": frozen["placement_sha256"],
            "schedule_sha256": measure.PLAN_SHA,
            "start_inventory_samples": inventory["sample_count"],
            "start_inventory_duration_s": inventory["duration_s"],
            "per_arm_groups": groups,
            "scope": "two original prefill read cohorts on NVMe; no inference",
        }
        obs = [o for arm in arms for o in arm["samples"]]
        value["min_mem_available_bytes"] = min(o["mem_available_bytes"] for o in obs)
        value["max_cpu_tctl_c"] = max(o["thermal"]["cpu_tctl_c"] for o in obs)
        value["max_gpu_temp_c"] = max(o["gpu"]["temperature_c"] for o in obs)
        value["max_nvme_composite_c"] = max(
            t for o in obs for t in o["thermal"]["nvme_composite_by_sensor"].values()
        )
        measure.require(
            all(
                math.isfinite(value[k])
                for k in ("max_cpu_tctl_c", "max_gpu_temp_c", "max_nvme_composite_c")
            ),
            "finite sensors",
        )
        measure.require(
            hashlib.sha256(json.dumps(gold, sort_keys=True).encode()).hexdigest()
            == receipt["payload_manifest_sha256"],
            "manifest",
        )
    measure.io.save(new / "receipt.json", value)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--raw-dir", type=Path, required=True)
    cli.add_argument("--new-output-dir", type=Path, required=True)
    args = cli.parse_args()
    compact(args.raw_dir, args.new_output_dir)
