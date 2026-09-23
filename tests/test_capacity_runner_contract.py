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
