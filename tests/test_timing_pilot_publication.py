import json
import subprocess
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_valid_campaign(tmp_path: Path) -> tuple[Path, list[tuple[str, str, int | None, float]]]:
    campaign = tmp_path / "n-cpu-moe-timing-pilot-test"
    runs = campaign / "runs"
    capacity = campaign / "capacity"
    runs.mkdir(parents=True)
    capacity.mkdir()

    for name in ("model.json", "doctor.json", "backend.json"):
        _write_json(campaign / name, {})

    _write_json(
        campaign / "build-provenance.json",
        {"schema": "tesy.llama_build_provenance.v1", "status": "PASS"},
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
        ("auto-fit-frozen", "01-auto-fit-frozen", None, 100.0),
        ("n-cpu-moe-12", "02-n-cpu-moe-12", 12, 90.0),
        ("n-cpu-moe-24", "03-n-cpu-moe-24", 24, 60.0),
    ]
    token_hash = "a" * 64
    summary_rows = []

    for placement, run_name, n_cpu_moe, decode_tps in placements:
        run = runs / run_name
        run.mkdir()

        _write_json(run / "pre-run-resources.json", {"schema": "test"})
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
        (run / "server.stderr.txt").write_text("", encoding="utf-8")
        (run / "resources.jsonl").write_text("{}\n", encoding="utf-8")
        _write_json(run / "health.json", {"status": "ok"})
        _write_json(
            run / "runtime-provenance.json",
            {"schema": "tesy.runtime_backend_provenance.v1", "status": "PASS"},
        )
        _write_json(
            run / "server-ready.json",
            {
                "schema": "tesy.stock_server_ready.v1",
                "placement_id": placement,
                "server_ready_ms": 1000.0,
            },
        )
        request = {
            "schema": "tesy.stock_server_request.v1",
            "generated_token_count": 64,
            "ttft_ms": 10.0,
            "request_wall_ms": 100.0,
            "timings": {
                "prompt_per_second": 200.0,
                "predicted_per_second": decode_tps,
            },
        }
        _write_json(run / "request.json", request)
        (run / "token-sha256.txt").write_text(token_hash + "\n", encoding="utf-8")
        resources = {
            "schema": "tesy.stock_placement_pilot_resources.v1",
            "peak_gpu_memory_used_bytes": 4 * 1024**3,
            "min_observed_gpu_free_bytes": 3 * 1024**3,
            "peak_process_rss_bytes": 8 * 1024**3,
            "peak_process_swap_bytes": 0,
            "gpu_failed_samples": 0,
        }
        _write_json(run / "resource-summary.json", resources)
        (run / "placement.txt").write_text("CUDA0 model buffer\n", encoding="utf-8")

        _write_json(
            capacity / f"{placement}.json",
            {
                "schema": "tesy.placement_capacity_estimate.v1",
                "placement_id": placement,
                "admitted": True,
                "gpu_required_mib": 7000,
                "host_required_mib": 10000,
            },
        )
        (capacity / f"{placement}.stdout.txt").write_text(
            "CUDA0 1 1 1 \nHost 1 0 1 \n", encoding="utf-8"
        )
        (capacity / f"{placement}.stderr.txt").write_text("", encoding="utf-8")

        summary_rows.append(
            {
                "placement_id": placement,
                "n_cpu_moe": n_cpu_moe,
                "observation_count": 1,
                "ttft_ms": request["ttft_ms"],
                "request_wall_ms": request["request_wall_ms"],
                "prompt_tps": request["timings"]["prompt_per_second"],
                "decode_tps": request["timings"]["predicted_per_second"],
                "server_ready_ms": 1000.0,
                "peak_gpu_memory_used_bytes": resources["peak_gpu_memory_used_bytes"],
                "min_observed_gpu_free_bytes": resources["min_observed_gpu_free_bytes"],
                "peak_process_rss_bytes": resources["peak_process_rss_bytes"],
                "peak_process_swap_bytes": resources["peak_process_swap_bytes"],
                "max_gpu_temperature_c": 60.0,
                "max_gpu_power_w": 50.0,
                "capacity_gpu_required_mib": 7000,
                "capacity_host_required_mib": 10000,
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
                "unique_token_trajectory_hashes": [token_hash],
            },
            "next_gate": "MANUAL_REVIEW_REQUIRED",
        },
    )
    return campaign, placements


def _run_publisher(root: Path, campaign: Path, publish: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
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


def test_timing_pilot_publication_validates_and_copies_independent_artifacts(tmp_path):
    root = Path(__file__).resolve().parents[1]
    campaign, placements = _make_valid_campaign(tmp_path)
    publish = tmp_path / "published"

    completed = _run_publisher(root, campaign, publish)

    assert completed.returncode == 0, completed.stderr
    assert "PASS_TIMING_PILOT_PUBLICATION_PREPARED" in completed.stdout

    manifest = json.loads(
        (publish / "publication-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["classification"] == "MEASURED_SINGLE_OBSERVATION_PILOT_DIAGNOSTIC"
    assert manifest["placements"] == [item[0] for item in placements]
    assert manifest["trajectory_status"] == "PASS"
    assert manifest["next_gate"] == "MANUAL_REVIEW_REQUIRED"

    result = (publish / "RESULT.md").read_text(encoding="utf-8")
    assert "not a stable throughput/latency ranking" in result

    attributes = (publish / ".gitattributes").read_text(encoding="utf-8")
    assert "capacity/*.stdout.txt -whitespace" in attributes
    assert "runs/*/server.stderr.txt -whitespace" in attributes


def test_timing_pilot_publication_rejects_summary_artifact_mismatch(tmp_path):
    root = Path(__file__).resolve().parents[1]
    campaign, _ = _make_valid_campaign(tmp_path)
    summary_path = campaign / "pilot-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["placements"][1]["decode_tps"] = 9999.0
    _write_json(summary_path, summary)

    completed = _run_publisher(root, campaign, tmp_path / "published")

    assert completed.returncode != 0
    assert "pilot summary mismatch for n-cpu-moe-12 decode_tps" in completed.stderr
