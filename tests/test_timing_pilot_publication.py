import json
import subprocess
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fake_pilot(root: Path) -> Path:
    campaign = root / "n-cpu-moe-timing-pilot-test"
    capacity_dir = campaign / "capacity"
    runs_dir = campaign / "runs"
    capacity_dir.mkdir(parents=True)
    runs_dir.mkdir()

    for name in ("model.json", "doctor.json", "backend.json"):
        _write_json(campaign / name, {})

    _write_json(
        campaign / "build-provenance.json",
        {
            "schema": "tesy.llama_build_provenance.v1",
            "status": "PASS",
        },
    )
    _write_json(
        campaign / "auto-fit.json",
        {
            "schema": "tesy.llama_fit_args.v1",
            "ctx_size": 4096,
            "argv": ["-c", "4096", "-ngl", "25"],
        },
    )

    for name in (
        "tesy-head.txt",
        "llama-head.txt",
        "server-sha256.txt",
        "fit-tool-sha256.txt",
        "prompt-sha256.txt",
        "auto-fit.stdout.txt",
        "auto-fit.stderr.txt",
    ):
        (campaign / name).write_text("x\n", encoding="utf-8")
    (campaign / "tesy-status.txt").write_text("", encoding="utf-8")
    (campaign / "llama-status.txt").write_text("", encoding="utf-8")

    placements = [
        ("auto-fit-frozen", "01-auto-fit-frozen", None),
        ("n-cpu-moe-12", "02-n-cpu-moe-12", 12),
        ("n-cpu-moe-24", "03-n-cpu-moe-24", 24),
    ]
    summary_rows = []

    for index, (placement, dirname, n_cpu_moe) in enumerate(placements, start=1):
        run = runs_dir / dirname
        run.mkdir()
        token_hash = "abc123"

        _write_json(run / "pre-run-resources.json", {})
        _write_json(
            run / "run-metadata.json",
            {
                "schema": "tesy.stock_placement_pilot_run.v1",
                "placement_id": placement,
                "n_cpu_moe": n_cpu_moe,
                "observation_index": 1,
            },
        )
        (run / "server-command.txt").write_text("server\n", encoding="utf-8")
        (run / "server.stdout.txt").write_text("", encoding="utf-8")
        (run / "server.stderr.txt").write_text("CUDA0\n", encoding="utf-8")
        (run / "resources.jsonl").write_text("{}\n", encoding="utf-8")
        _write_json(run / "health.json", {})
        _write_json(
            run / "runtime-provenance.json",
            {
                "schema": "tesy.runtime_backend_provenance.v1",
                "status": "PASS",
            },
        )
        _write_json(
            run / "server-ready.json",
            {
                "schema": "tesy.stock_server_ready.v1",
                "placement_id": placement,
                "server_ready_ms": 1000.0 + index,
            },
        )

        ttft = 10.0 + index
        wall = 20.0 + index
        prompt_tps = 3.0 + index
        decode_tps = 4.0 + index
        _write_json(
            run / "request.json",
            {
                "schema": "tesy.stock_server_request.v1",
                "generated_token_count": 64,
                "ttft_ms": ttft,
                "request_wall_ms": wall,
                "timings": {
                    "prompt_per_second": prompt_tps,
                    "predicted_per_second": decode_tps,
                },
            },
        )
        (run / "token-sha256.txt").write_text(token_hash + "\n", encoding="utf-8")

        peak_gpu = 1000 + index
        min_gpu_free = 2000 + index
        peak_rss = 3000 + index
        _write_json(
            run / "resource-summary.json",
            {
                "schema": "tesy.stock_placement_pilot_resources.v1",
                "peak_process_swap_bytes": 0,
                "gpu_failed_samples": 0,
                "peak_gpu_memory_used_bytes": peak_gpu,
                "min_observed_gpu_free_bytes": min_gpu_free,
                "peak_process_rss_bytes": peak_rss,
            },
        )
        (run / "placement.txt").write_text("CUDA0\n", encoding="utf-8")

        _write_json(
            capacity_dir / f"{placement}.json",
            {
                "schema": "tesy.placement_capacity_estimate.v1",
                "placement_id": placement,
                "admitted": True,
            },
        )
        (capacity_dir / f"{placement}.stdout.txt").write_text("", encoding="utf-8")
        (capacity_dir / f"{placement}.stderr.txt").write_text("", encoding="utf-8")

        summary_rows.append(
            {
                "placement_id": placement,
                "n_cpu_moe": n_cpu_moe,
                "observation_count": 1,
                "ttft_ms": ttft,
                "request_wall_ms": wall,
                "prompt_tps": prompt_tps,
                "decode_tps": decode_tps,
                "server_ready_ms": 1000.0 + index,
                "peak_gpu_memory_used_bytes": peak_gpu,
                "min_observed_gpu_free_bytes": min_gpu_free,
                "peak_process_rss_bytes": peak_rss,
                "peak_process_swap_bytes": 0,
                "max_gpu_temperature_c": 50.0,
                "max_gpu_power_w": 20.0,
                "capacity_gpu_required_mib": 100,
                "capacity_host_required_mib": 200,
                "token_sha256": token_hash,
            }
        )

    _write_json(
        campaign / "pilot-summary.json",
        {
            "schema": "tesy.stock_placement_timing_pilot.v1",
            "classification": "MEASURED_SINGLE_OBSERVATION_PILOT_DIAGNOSTIC",
            "placements": summary_rows,
            "trajectory_comparability": {
                "status": "PASS",
                "required_token_count": 64,
                "unique_token_trajectory_hashes": ["abc123"],
            },
            "next_gate": "MANUAL_REVIEW_REQUIRED",
        },
    )
    return campaign


def test_timing_pilot_publication_validates_and_copies(tmp_path):
    root = Path(__file__).resolve().parents[1]
    campaign = _fake_pilot(tmp_path)
    publish = tmp_path / "published"

    completed = subprocess.run(
        [
            "bash",
            str(root / "scripts" / "publish_n_cpu_moe_timing_pilot_result.sh"),
            str(campaign),
            str(publish),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PASS_TIMING_PILOT_PUBLICATION_PREPARED" in completed.stdout

    manifest = json.loads(
        (publish / "publication-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["classification"] == "MEASURED_SINGLE_OBSERVATION_PILOT_DIAGNOSTIC"
    assert manifest["trajectory_status"] == "PASS"
    assert manifest["placements"] == [
        "auto-fit-frozen",
        "n-cpu-moe-12",
        "n-cpu-moe-24",
    ]

    result = (publish / "RESULT.md").read_text(encoding="utf-8")
    assert "not a stable throughput/latency ranking" in result

    attributes = (publish / ".gitattributes").read_text(encoding="utf-8")
    assert "capacity/*.stdout.txt -whitespace" in attributes
    assert "runs/*/server.stderr.txt -whitespace" in attributes


def test_timing_pilot_publication_rejects_summary_artifact_mismatch(tmp_path):
    root = Path(__file__).resolve().parents[1]
    campaign = _fake_pilot(tmp_path)
    summary_path = campaign / "pilot-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["placements"][1]["decode_tps"] += 1.0
    _write_json(summary_path, summary)

    completed = subprocess.run(
        [
            "bash",
            str(root / "scripts" / "publish_n_cpu_moe_timing_pilot_result.sh"),
            str(campaign),
            str(tmp_path / "published"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "pilot summary mismatch" in completed.stderr
