"""Capacity admission for vertical integration; never a throughput forecast."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

GIB = 1024**3
HOST_RESERVE = 6 * GIB
STAGING_AND_IO = 1 * GIB
VRAM_RESERVE = 1 * GIB


def classify_bytes(encoded_bytes: int | None, ram_bytes: int) -> str:
    if encoded_bytes is None:
        return "ARTIFACT_BYTES_UNKNOWN"
    if encoded_bytes <= 0 or ram_bytes <= 0:
        raise ValueError("capacity bytes must be positive")
    if encoded_bytes > ram_bytes:
        return "WEIGHTS_EXCEED_RAM"
    if encoded_bytes + HOST_RESERVE + STAGING_AND_IO > ram_bytes:
        return "WORKING_SET_NEAR_HOST_BUDGET"
    return "ENCODED_WEIGHTS_RAM_ADMISSIBLE_ONLY"


def _validated_process_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    valid = [
        row
        for row in rows
        if set(row.get("process", {})) == {"VmRSS_bytes", "VmSwap_bytes"}
    ]
    if not valid or any(row.get("gpu", {}).get("status") != "OK" for row in rows):
        raise ValueError("missing process samples or incomplete GPU telemetry")
    if any(row["process"]["VmSwap_bytes"] != 0 for row in valid):
        raise ValueError("process swap invalidates observed capacity")
    return valid


def build_report(
    models: dict,
    doctor: dict,
    resources: list[dict],
    observed_gpu_buffer_bytes: int,
) -> dict:
    if models.get("schema") != "tesy.models.lock.v1":
        raise ValueError("unexpected model lock schema")
    snapshot = doctor["snapshot"]
    if doctor["reference_check"]["status"] != "PASS" or (
        snapshot["virtualization"]["status"] != "PHYSICAL"
    ):
        raise ValueError("physical reference host not admitted")
    ram = snapshot["memory"]["total_bytes"]
    vram = snapshot["gpu"]["gpus"][0]["memory_total_bytes"]
    if not isinstance(ram, int) or not isinstance(vram, int):
        raise ValueError("missing host/device capacities")
    if observed_gpu_buffer_bytes <= 0 or observed_gpu_buffer_bytes > vram:
        raise ValueError("invalid observed Tesy GPU buffer allocation")
    if not resources or any(row["process"]["VmSwap_bytes"] != 0 for row in resources):
        raise ValueError("missing valid swap-free process telemetry")

    by_id = {model["id"]: model for model in models["models"]}
    installed = by_id["gpt-oss-20b-mxfp4-gguf"]
    exact_bytes = installed["artifact"]["bytes"]
    peak_rss = max(row["process"]["VmRSS_bytes"] for row in resources)
    peak_gpu = max(row["gpu"]["memory_used_bytes"] for row in resources)
    if exact_bytes <= 0 or peak_rss <= 0:
        raise ValueError("invalid installed-model inventory")

    candidates = []
    for model in models["models"]:
        artifact = model["artifact"]
        exact = artifact.get("bytes")
        source_size = artifact.get("source_reported_size")
        if exact is not None and (not isinstance(exact, int) or exact <= 0):
            raise ValueError("invalid exact artifact size")
        if exact is not None:
            classification = classify_bytes(exact, ram)
            basis = "EXACT_LOCKED_ARTIFACT_BYTES"
        elif model["id"] == "gpt-oss-120b-mxfp4":
            checkpoint = model["upstream"].get("source_reported_checkpoint_size")
            classification = "CHECKPOINT_REPORTED_OVER_RAM_GGUF_ARTIFACT_UNKNOWN"
            basis = f"SOURCE_REPORTED_CHECKPOINT_{checkpoint}"
        elif source_size:
            classification = "ARTIFACT_BYTES_UNKNOWN_SOURCE_SIZE_ONLY"
            basis = f"SOURCE_REPORTED_{source_size}"
        else:
            classification = "ARTIFACT_BYTES_UNKNOWN"
            basis = "NO_SIZE"
        candidates.append({
            "model_id": model["id"],
            "classification": classification,
            "basis": basis,
            "exact_artifact_bytes": exact,
            "missing_for_admission": [
                key for key in ("revision", "bytes", "sha256")
                if artifact.get(key) is None
            ],
        })

    transfer_scenarios = []
    for required_bytes in (GIB, 4 * GIB, 16 * GIB):
        transfer_scenarios.append({
            "required_bytes": required_bytes,
            "floor_seconds_by_sustained_bandwidth": {
                f"{gbps}_GBps": required_bytes / (gbps * 10**9)
                for gbps in (1, 3, 5)
            },
        })
    for scenario in transfer_scenarios:
        if not all(math.isfinite(value) and value > 0 for value in
                   scenario["floor_seconds_by_sustained_bandwidth"].values()):
            raise ValueError("non-finite transfer floor")

    return {
        "schema": "tesy.vertical_capacity_report.v1",
        "classification": "MEASURED_INSTALLED_ESTIMATED_CANDIDATES",
        "ram_total_bytes": ram,
        "vram_total_bytes": vram,
        "host_reserve_bytes": HOST_RESERVE,
        "staging_and_io_reserve_bytes": STAGING_AND_IO,
        "vram_reserve_bytes": VRAM_RESERVE,
        "installed_model": {
            "id": installed["id"],
            "encoded_artifact_bytes": exact_bytes,
            "observed_peak_process_rss_bytes": peak_rss,
            "observed_peak_gpu_used_bytes": peak_gpu,
            "observed_tesy_gpu_buffer_bytes_one_layer_four_residents":
                observed_gpu_buffer_bytes,
            "rss_minus_artifact_bytes_not_repacking_only": peak_rss - exact_bytes,
            "mmap_is_not_resident_dram_proof": True,
            "classification": classify_bytes(exact_bytes, ram),
        },
        "candidates": candidates,
        "loader": {
            "full_model_tensor_namespace_required_before_decode": True,
            "full_physical_weight_materialization": "UNKNOWN_MMAP_AND_BACKEND_DEPENDENT",
            "validated_over_ram_support": False,
            "comment": (
                "Current stock model load and Tesy borrowed tensors require the whole "
                "model tensor namespace. mmap does not establish physical residency "
                "or a correct >RAM runtime."
            ),
        },
        "nvme_transfer_floors_parameterized_not_tok_s": transfer_scenarios,
        "claim_boundary": (
            "Installed-model RSS/VRAM are observed health data; candidate sizes "
            "and NVMe transfer floors are estimates/scenarios. No physical I/O "
            "or larger-model inference has been measured."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-lock", required=True, type=Path)
    parser.add_argument("--doctor", required=True, type=Path)
    parser.add_argument("--resources", required=True, type=Path)
    parser.add_argument("--gpu-buffer-bytes", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = build_report(
        json.loads(args.models_lock.read_text()),
        json.loads(args.doctor.read_text()),
        _validated_process_rows(args.resources),
        args.gpu_buffer_bytes,
    )
    with args.output.open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
