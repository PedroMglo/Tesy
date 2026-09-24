from pathlib import Path


def test_capacity_runner_uses_cli_for_backend_feature_probe():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    assert 'cli="${TESY_LLAMA_CLI:-$build_dir/bin/llama-cli}"' in text
    assert (
        'python3 -m tesy backend probe \\\n'
        '  --binary "$cli" \\\n'
        '  --source-dir "$source_dir" >"$out/backend.json"'
    ) in text
    assert (
        'python3 -m tesy backend probe \\\n'
        '  --binary "$server"'
    ) not in text


def test_capacity_only_exits_before_timed_server_order():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    capacity_exit = text.index("PASS_SOURCE_BACKED_N_CPU_MOE_CAPACITY_ESTIMATION")
    timed_order = text.index('order=("auto")')
    timed_server = text.index('"${cmd[@]}" >"$run_dir/server.stdout.txt"')

    assert capacity_exit < timed_order < timed_server


def test_manual_capacity_estimation_is_explicit_all_gpu_plus_cpu_moe():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    assert "--gpu-layers all" in text
    assert '--n-cpu-moe "$n"' in text
    assert "--fit-print on" in text


def test_timing_pilot_is_bound_to_published_capacity_evidence():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    assert '--timing-pilot' in text
    assert (
        'capacity_evidence_commit="5a8bbf08eb95069b1847f724e5d1be98c6392678"'
        in text
    )
    assert 'cp "$capacity_evidence_dir/auto-fit.json" "$out/auto-fit.json"' in text
    assert 'git -C "$root" merge-base --is-ancestor "$capacity_evidence_commit" HEAD' in text


def test_timing_pilot_rechecks_exactly_three_selected_placements():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    assert 'candidates=(12 24)' in text
    assert '--placement-id "auto-fit-frozen"' in text
    assert 'order=("auto" "n12" "n24")' in text
    assert '"schema": "tesy.timing_pilot_capacity_gate.v1"' in text


def test_timing_pilot_has_separate_non_pareto_summary_and_exit():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    pilot_summary = text.index('"$out/pilot-summary.json"')
    pilot_pass = text.index("PASS_DIAGNOSTIC_STOCK_PLACEMENT_TIMING_PILOT")
    sweep_summary = text.index('"$out/sweep-summary.json"')

    assert pilot_summary < pilot_pass < sweep_summary
    assert '"schema": "tesy.stock_placement_timing_pilot.v1"' in text
    assert "no confirmatory performance winner or Pareto frontier follows" in text


def test_timing_pilot_rechecks_fresh_resources_before_each_server():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    snapshot = text.index('snapshot_pre_run_resources "$run_dir/pre-run-resources.json"')
    admission = text.index('pre_run_capacity_check \\')
    server = text.index('"${cmd[@]}" >"$run_dir/server.stdout.txt"')

    assert snapshot < admission < server


def test_runtime_summary_rejects_any_gpu_telemetry_failure():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    assert 'if summary["gpu_failed_samples"] != 0:' in text
    assert "GPU telemetry incomplete" in text


def test_timing_pilot_gates_request_on_quantitative_placement_telemetry():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    telemetry = text.index("python3 -m tesy.placement_telemetry")
    request = text.index("python3 -m tesy.server_client")
    assert telemetry < request
    assert '--fit-print "$capacity_input"' in text
    assert '--placement-id "$placement_id"' in text
    assert '--tolerance-mib 2.0' in text
    assert '--output "$run_dir/placement-telemetry.json"' in text


def test_timing_pilot_enables_backend_placement_logs_before_server_start():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    verbosity = text.index('cmd+=(--verbosity 4)')
    server = text.index('"${cmd[@]}" >"$run_dir/server.stdout.txt"')
    assert (
        'if (( timing_pilot == 1 )); then\n'
        '    # Pinned llama.cpp maps backend INFO placement rows to verbosity 4.\n'
        '    cmd+=(--verbosity 4)'
    ) in text
    assert verbosity < server


def test_timing_pilot_binds_live_process_to_frozen_server_argv():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    argv_text = text.index('>"$run_dir/server-command.txt"')
    argv_json = text.index('"$run_dir/server-argv.json"')
    server = text.index('"${cmd[@]}" >"$run_dir/server.stdout.txt"')
    runtime = text.index("python3 -m tesy.runtime_provenance")
    request = text.index("python3 -m tesy.server_client")

    assert argv_text < argv_json < server < runtime < request
    assert '--expected-argv "$run_dir/server-argv.json"' in text
    assert 'runtime.get("argv", {}).get("status") != "PASS"' in text


def test_timing_pilot_does_not_compare_host_mmap_span_to_fit_host_bytes():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    assert (
        '"host_comparability_status": '
        'placement_telemetry["host_comparability"]["status"]'
    ) in text
    assert '"observed_host_mmap_span_mib"' in text
    assert '"projected_host_logical_model_mib"' in text
    assert '"observed_host_model_mib"' not in text


def test_timing_pilot_stops_on_monitor_failure_or_nonfinite_resources():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_n_cpu_moe_capacity_pareto.sh").read_text(
        encoding="utf-8"
    )

    assert '  wait "$monitor_pid"\n  monitor_pid=""' in text
    assert 'raise SystemExit("non-finite resource telemetry")' in text
