import json
from pathlib import Path

from tesy.publish_timing_pilot import publish_timing_pilot


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_publish_timing_pilot_keeps_only_derived_artifacts(tmp_path):
    campaign = tmp_path / "timing-pilot-test"
    campaign.mkdir()

    _write_json(
        campaign / "pilot-summary.json",
        {
            "schema": "tesy.stock_placement_timing_pilot.v1",
            "classification": "MEASURED_STOCK_PLACEMENT_PILOT_DIAGNOSTIC",
            "capacity_evidence_commit": "5a8bbf08eb95069b1847f724e5d1be98c6392678",
            "order": ["auto-fit-frozen", "n-cpu-moe-12", "n-cpu-moe-24"],
            "observations": [
                {
                    "placement_id": placement,
                    "predicted_n": 64,
                    "runtime_provenance_status": "PASS",
                    "peak_process_swap_bytes": 0,
                    "placement_log_lines": ["placement"],
                    "ttft_ms": 100.0 + index,
                    "prompt_tps": 200.0 + index,
                    "decode_tps": 30.0 + index,
                    "peak_gpu_memory_bytes": 2 * 1024 * 1024,
                    "peak_process_rss_bytes": 3 * 1024**3,
                    "max_gpu_temperature_c": 55.0,
                }
                for index, placement in enumerate(
                    ["auto-fit-frozen", "n-cpu-moe-12", "n-cpu-moe-24"]
                )
            ],
            "trajectory_comparability": {
                "status": "PASS",
                "unique_token_trajectory_hashes": ["a" * 64],
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
    _write_json(
        campaign / "build-provenance.json",
        {"status": "PASS"},
    )
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

    raw_dir = campaign / "01-auto-fit"
    raw_dir.mkdir()
    (raw_dir / "resources.jsonl").write_text('{"raw":true}\n', encoding="utf-8")
    (raw_dir / "server.stderr.txt").write_text("raw log\n", encoding="utf-8")

    destination = tmp_path / "published"
    manifest = publish_timing_pilot(campaign, destination)

    assert manifest["observation_count"] == 3
    assert manifest["trajectory_status"] == "PASS"
    assert manifest["next_gate"] == "MANUAL_REVIEW_REQUIRED"
    assert "01-auto-fit/resources.jsonl" in manifest["raw_artifacts"]
    assert not (destination / "01-auto-fit").exists()
    assert (destination / "pilot-summary.json").exists()
    assert (destination / "host-summary.json").exists()
    assert (destination / "RESULT.md").exists()
    assert (destination / "publication-manifest.json").exists()
