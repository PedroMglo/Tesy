import hashlib
import hashlib
import json
from pathlib import Path

import pytest

from tesy.publish_timing_pilot import (
    TimingPilotPublicationError,
    publish_timing_pilot,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fake_campaign(root: Path) -> Path:
    campaign = root / "timing-pilot-test"
    campaign.mkdir()

    placements = [
        ("auto-fit-frozen", "01-auto-fit", None),
        ("n-cpu-moe-12", "02-n12", 12),
        ("n-cpu-moe-24", "03-n24", 24),
    ]
    observations = []
    tokens = list(range(64))
    token_hash = hashlib.sha256(
        json.dumps(tokens, separators=(",", ":")).encode()
    ).hexdigest()

    for index, (placement, dirname, n_cpu_moe) in enumerate(placements):
        run = campaign / dirname
        run.mkdir()

        ttft = 100.0 + index
        wall = 200.0 + index
        prompt_n = 20
        prompt_ms = 50.0 + index
        prompt_tps = 300.0 + index
        predicted_n = 64
        predicted_ms = 1000.0 + index
        decode_tps = 40.0 + index
        pre_gpu_free = 8_000_000_000 - index
        pre_temp = 50.0 + index
        pre_mem = 20_000_000_000 - index
        gpu_required = 7000 - index
        host_required = 8000 + index
        peak_gpu = 6_000_000_000 - index
        min_gpu_free = 2_000_000_000 + index
        peak_rss = 10_000_000_000 + index
        min_mem = 12_000_000_000 - index
        min_swap = 16_000_000_000
        max_temp = 60.0 + index
        max_power = 80.0 + index
        ready_ms = 1000.0 + index
        command = f"llama-server --placement {placement}"
        placement_lines = [f"CUDA0 placement {placement}"]

        _write_json(
            run / "run-metadata.json",
            {
                "schema": "tesy.stock_placement_run.v1",
                "placement_id": placement,
                "n_cpu_moe": n_cpu_moe,
            },
        )
        _write_json(
            run / "request.json",
            {
                "schema": "tesy.stock_server_request.v1",
                "generated_token_ids": tokens,
                "generated_token_count": 64,
                "ttft_ms": ttft,
                "request_wall_ms": wall,
                "timings": {
                    "prompt_n": prompt_n,
                    "prompt_ms": prompt_ms,
                    "prompt_per_second": prompt_tps,
                    "predicted_n": predicted_n,
                    "predicted_ms": predicted_ms,
                    "predicted_per_second": decode_tps,
                },
            },
        )
        _write_json(
            run / "resource-summary.json",
            {
                "samples": 10,
                "gpu_valid_samples": 10,
                "gpu_failed_samples": 0,
                "peak_gpu_memory_used_bytes": peak_gpu,
                "min_observed_gpu_free_bytes": min_gpu_free,
                "peak_process_rss_bytes": peak_rss,
                "peak_process_swap_bytes": 0,
                "min_mem_available_bytes": min_mem,
                "min_swap_free_bytes": min_swap,
                "max_gpu_temperature_c": max_temp,
                "max_gpu_power_w": max_power,
            },
        )
        _write_json(
            run / "runtime-provenance.json",
            {
                "schema": "tesy.runtime_backend_provenance.v1",
                "status": "PASS",
            },
        )
        _write_json(
            run / "pre-run-resources.json",
            {
                "schema": "tesy.timing_pilot_pre_run_resources.v1",
                "gpu": {
                    "memory_free_bytes": pre_gpu_free,
                    "temperature_c": pre_temp,
                },
                "memory": {"available_bytes": pre_mem},
            },
        )
        _write_json(
            run / "pre-run-capacity.json",
            {
                "schema": "tesy.placement_capacity_estimate.v1",
                "placement_id": placement,
                "admitted": True,
                "gpu_required_mib": gpu_required,
                "host_required_mib": host_required,
            },
        )
        _write_json(
            run / "server-ready.json",
            {
                "placement_id": placement,
                "server_ready_ms": ready_ms,
            },
        )
        _write_json(run / "health.json", {"status": "ok"})
        _write_json(
            run / "server-ready.json",
            {
                "schema": "tesy.stock_server_ready.v1",
                "placement_id": placement,
                "server_ready_ms": 1000.0 + index,
            },
        )
        _write_json(run / "health.json", {"status": "ok"})
        (run / "server.stdout.txt").write_text("", encoding="utf-8")
        (run / "server-command.txt").write_text(command + "\n", encoding="utf-8")
        (run / "placement.txt").write_text(
            placement_lines[0] + "\n",
            encoding="utf-8",
        )
        (run / "token-sha256.txt").write_text(token_hash + "\n", encoding="utf-8")
        (run / "resources.jsonl").write_text('{"raw":true}\n', encoding="utf-8")
        (run / "server.stdout.txt").write_text("", encoding="utf-8")
        (run / "server.stderr.txt").write_text("raw log\n", encoding="utf-8")

        observations.append(
            {
                "run": dirname,
                "placement_id": placement,
                "n_cpu_moe": n_cpu_moe,
                "server_command": command,
                "pre_run_gpu_free_bytes": pre_gpu_free,
                "pre_run_gpu_temperature_c": pre_temp,
                "pre_run_mem_available_bytes": pre_mem,
                "pre_run_capacity_gpu_required_mib": gpu_required,
                "pre_run_capacity_host_required_mib": host_required,
                "server_ready_ms": ready_ms,
                "ttft_ms": ttft,
                "request_wall_ms": wall,
                "prompt_n": prompt_n,
                "prompt_ms": prompt_ms,
                "prompt_tps": prompt_tps,
                "predicted_n": predicted_n,
                "predicted_ms": predicted_ms,
                "decode_tps": decode_tps,
                "resource_samples": 10,
                "gpu_valid_samples": 10,
                "peak_gpu_memory_bytes": peak_gpu,
                "min_observed_gpu_free_bytes": min_gpu_free,
                "peak_process_rss_bytes": peak_rss,
                "peak_process_swap_bytes": 0,
                "min_mem_available_bytes": min_mem,
                "min_swap_free_bytes": min_swap,
                "max_gpu_temperature_c": max_temp,
                "max_gpu_power_w": max_power,
                "gpu_failed_samples": 0,
                "runtime_provenance_status": "PASS",
                "placement_log_lines": placement_lines,
                "token_sha256": token_hash,
            }
        )

    _write_json(
        campaign / "pilot-summary.json",
        {
            "schema": "tesy.stock_placement_timing_pilot.v1",
            "classification": "MEASURED_STOCK_PLACEMENT_PILOT_DIAGNOSTIC",
            "capacity_evidence_commit": (
                "5a8bbf08eb95069b1847f724e5d1be98c6392678"
            ),
            "order": [item[0] for item in placements],
            "observations": observations,
            "trajectory_comparability": {
                "status": "PASS",
                "required_token_count": 64,
                "unique_token_trajectory_hashes": [token_hash],
            },
            "next_gate": "MANUAL_REVIEW_REQUIRED",
        },
    )
    _write_json(
        campaign / "capacity-summary.json",
        {
            "schema": "tesy.timing_pilot_capacity_gate.v1",
            "status": "PASS",
        },
    )
    _write_json(
        campaign / "source-capacity.json",
        {
            "schema": "tesy.timing_pilot_source_capacity.v1",
            "admitted_n_cpu_moe": [12, 16, 20, 24],
        },
    )
    _write_json(
        campaign / "admission-context.json",
        {"campaign_mode": "timing-pilot"},
    )
    _write_json(campaign / "build-provenance.json", {"status": "PASS"})
    _write_json(campaign / "model.json", {"status": "PASS"})
    _write_json(campaign / "backend.json", {"status": "PASS"})
    _write_json(
        campaign / "doctor.json",
        {
            "reference_check": {
                "status": "PASS",
                "profile_id": "reference",
            },
            "snapshot": {
                "cpu": {"logical_cpus": 24},
                "gpu": {"gpus": [{"name": "GPU"}]},
                "memory": {"available_bytes": 1},
                "gpu_compute_processes": {"status": "OK", "stdout": ""},
            },
        },
    )

    for name in (
        "tesy-head.txt",
        "llama-head.txt",
        "server-sha256.txt",
        "fit-tool-sha256.txt",
        "prompt-sha256.txt",
    ):
        (campaign / name).write_text("x\n", encoding="utf-8")
    (campaign / "tesy-status.txt").write_text("", encoding="utf-8")
    (campaign / "llama-status.txt").write_text("", encoding="utf-8")
    return campaign


def test_publish_timing_pilot_keeps_only_derived_artifacts(tmp_path):
    campaign = _fake_campaign(tmp_path)
    destination = tmp_path / "published"

    manifest = publish_timing_pilot(campaign, destination)

    assert manifest["observation_count"] == 3
    assert manifest["trajectory_status"] == "PASS"
    assert manifest["next_gate"] == "MANUAL_REVIEW_REQUIRED"
    assert "01-auto-fit/resources.jsonl" in manifest["raw_artifacts"]
    assert not (destination / "01-auto-fit").exists()
    assert not (destination / "02-n12").exists()
    assert not (destination / "03-n24").exists()
    assert (destination / "pilot-summary.json").exists()
    assert (destination / "host-summary.json").exists()
    assert (destination / "RESULT.md").exists()
    assert (destination / "publication-manifest.json").exists()


def test_publish_timing_pilot_rejects_summary_raw_mismatch(tmp_path):
    campaign = _fake_campaign(tmp_path)
    summary_path = campaign / "pilot-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["observations"][1]["decode_tps"] += 1.0
    _write_json(summary_path, summary)

    with pytest.raises(TimingPilotPublicationError, match="summary/raw mismatch"):
        publish_timing_pilot(campaign, tmp_path / "published")


def test_publish_timing_pilot_rejects_token_hash_not_bound_to_ids(tmp_path):
    campaign = _fake_campaign(tmp_path)
    (campaign / "02-n12" / "token-sha256.txt").write_text(
        "0" * 64 + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        TimingPilotPublicationError,
        match="token hash does not match token IDs",
    ):
        publish_timing_pilot(campaign, tmp_path / "published")


def test_publish_timing_pilot_rejects_incomplete_gpu_telemetry(tmp_path):
    campaign = _fake_campaign(tmp_path)
    summary_path = campaign / "pilot-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["observations"][0]["gpu_failed_samples"] = 1
    _write_json(summary_path, summary)

    with pytest.raises(
        TimingPilotPublicationError,
        match="incomplete GPU telemetry",
    ):
        publish_timing_pilot(campaign, tmp_path / "published")
