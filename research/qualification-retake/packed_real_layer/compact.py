"""Publish the numeric witnesses of a closed family without private tensor data."""

import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def compact(raw):
    receipt = json.loads((raw / "receipt.json").read_bytes())
    detail = json.loads((raw / "detail.json").read_bytes())
    check(
        receipt["status"] == detail["status"] == "PASS_C291_REAL_CPU_LAYER_FAMILY"
        and detail == receipt["detail"]
        and receipt["detail_sha256"] == digest(raw / "detail.json")
        and receipt["scope_exit"] == detail["child_processes_at_cleanup"] == 0,
        "incomplete family",
    )
    check(
        digest(raw / "raw/samples.jsonl") == detail["monitor_sha256"],
        "telemetry changed",
    )
    witness = []
    for mode, arm, expected_sets in zip(
        ("DENSE", "STAGED", "DIRECT"), detail["arms"], (15, 15, 0), strict=True
    ):
        folder = raw / mode
        native = json.loads((folder / "stdout").read_bytes())
        check(
            native["status"] == arm["status"] == "PASS_C291_CPU0_ROUTED_TILE"
            and native["arm"] == arm["arm"] == mode
            and digest(folder / "stdout") == arm["stdout_sha256"]
            and digest(folder / "stderr") == arm["stderr_sha256"]
            and arm == json.loads((folder / "receipt.json").read_bytes())
            and arm["child_rc"] == 0,
            "arm receipt mismatch",
        )
        check(
            arm["tile_sha256"]
            == detail["ffntile_gold_sha256"]
            == digest(folder / "native/tile.f32")
            and native["weight_sets"] == expected_sets
            and native["mmid_nodes_observed"] == 24,
            "tile output or copy count changed",
        )
        values = {key: val for key, val in native.items() if key != "providers"}
        values.update(tile_sha256=arm["tile_sha256"], native_receipt_sha256=arm["stdout_sha256"])
        witness.append(values)
    samples = [json.loads(s) for s in (raw / "raw/samples.jsonl").read_text().splitlines()]
    check(samples and all(not s["compute_pids"] for s in samples), "GPU compute")
    keys = (
        "status",
        "commit",
        "tree",
        "build_commit",
        "build_sha256",
        "source_sha256",
        "preparation_sha256",
        "c55_receipt_sha256",
        "pack_sha256",
        "capture_refs",
        "gguf_requested_bytes_in_preparation",
        "gguf_read_bytes_by_family",
        "prepared_files_bytes",
        "executables",
        "libraries",
        "peak_bytes",
        "swap_peak_bytes",
        "cgroup_max_bytes",
        "preventive_stop_bytes",
        "started_utc",
        "closed_utc",
        "io_stat",
        "monitor_sha256",
        "child_processes_at_cleanup",
    )
    result = {k: detail[k] for k in keys}
    result.update(
        family_raw_sha256=digest(raw / "receipt.json"),
        arms=witness,
        c118=detail["c118"],
        elapsed_with_inventory_s=receipt["elapsed_s"],
        events=detail["cgroup_final"]["events"],
        monitor_samples=len(samples),
        gpu_compute_processes_observed=0,
        cpu_tctl_max_c=max(s["thermal"]["cpu_tctl_c"] for s in samples),
        gpu_max_c=max(s["gpu"]["temperature_c"] for s in samples),
        nvme_max_c=max(max(s["thermal"]["nvme_composite_by_sensor"].values()) for s in samples),
        host_psi_full_avg10_max=max(
            s["resource_observation"]["host_psi_full_avg10"] for s in samples
        ),
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = compact(args.raw)
    args.new_output_dir.mkdir(exist_ok=False)
    with (args.new_output_dir / "receipt.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
