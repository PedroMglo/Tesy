from pathlib import Path


def _runner_text() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "scripts" / "run_n_cpu_moe_timing_pilot.sh").read_text(
        encoding="utf-8"
    )


def test_pilot_uses_only_minimal_discriminating_placements():
    text = _runner_text()
    assert 'placements=("auto-fit-frozen" "n-cpu-moe-12" "n-cpu-moe-24")' in text
    assert '"n-cpu-moe-16"' not in text
    assert '"n-cpu-moe-20"' not in text


def test_pilot_rechecks_resources_and_capacity_before_each_server():
    text = _runner_text()
    preflight = text.index('snapshot_resources "$run_dir/pre-run-resources.json"')
    capacity = text.index('capacity_estimate \\')
    server = text.index('"${cmd[@]}" >"$run_dir/server.stdout.txt"')
    assert preflight < capacity < server


def test_pilot_auto_fit_is_frozen_then_replayed_with_fit_off():
    text = _runner_text()
    assert '--fit on \\\n  --fit-target "$gpu_target_mib"' in text
    assert '"${auto_fit_args[@]}" \\\n      --fit off' in text
    assert 'cmd+=("${auto_fit_args[@]}")' in text
    assert '--fit off' in text


def test_pilot_checks_runtime_provenance_before_request():
    text = _runner_text()
    provenance = text.index("python3 -m tesy.runtime_provenance")
    request = text.index("python3 -m tesy.server_client")
    assert provenance < request


def test_pilot_requires_exact_64_token_trajectory():
    text = _runner_text()
    assert "expected exactly 64 generated token IDs" in text
    assert "FAIL_TRAJECTORY_COMPARABILITY" in text
    assert '"required_token_count": 64' in text


def test_pilot_is_single_observation_diagnostic_not_full_ranking():
    text = _runner_text()
    assert '"observation_count": 1' in text
    assert "MEASURED_SINGLE_OBSERVATION_PILOT_DIAGNOSTIC" in text
    assert '"next_gate": "MANUAL_REVIEW_REQUIRED"' in text
    assert "not a stable throughput/latency ranking" in text


def test_pilot_enforces_runtime_resource_guards():
    text = _runner_text()
    assert 'summary["peak_process_swap_bytes"] != 0' in text
    assert 'summary["min_observed_gpu_free_bytes"] < gpu_target_bytes' in text
    assert 'summary["min_mem_available_bytes"] < host_guard_bytes' in text
    assert "GPU telemetry incomplete" in text
