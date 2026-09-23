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
