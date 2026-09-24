from pathlib import Path


def _native() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )


def test_live_timing_cli_freezes_campaign_shape():
    text = _native()

    assert "--live-handoff-timing" in text
    assert "live handoff timing gpu hits must be 2 or 3" in text
    assert "live handoff timing requires --warmup 6" in text
    assert "--samples 81 --inner 1" in text
    assert "live handoff timing requires --timing-start-gate" in text


def test_live_timing_callback_validates_before_ready_timestamps():
    text = _native()
    start = text.index("bool live_timing_callback(")
    end = text.index("void validate_live_timing_capture(", start)
    block = text[start:end]

    activation_check = block.index("compare_outputs(")
    activation_ready = block.index("state->activation_ready")
    weight_check = block.index("float_vectors_bitwise_equal(")
    route_ready = block.index("state->route_ready")

    assert activation_check < activation_ready
    assert weight_check < route_ready


def test_live_timing_uses_host_activation_for_cpu_and_gpu_inputs():
    text = _native()
    start = text.index("void set_live_routed_input(")
    end = text.index("void execute_live_routed_serial(", start)
    block = text[start:end]

    assert "ggml_backend_tensor_set(" in block
    assert "executor.cpu_graph->input" in block
    assert "executor.gpu_graph->input" in block
    assert "ggml_backend_tensor_copy(" not in block


def test_live_timing_candidate_endpoint_precedes_rollback():
    text = _native()
    start = text.index("std::pair<double, double> run_live_timing_trial(")
    end = text.index("live_handoff_timing_result run_live_handoff_timing(", start)
    block = text[start:end]

    endpoint = block.index("endpoint =")
    rollback = block.index("llama_memory_seq_rm(")

    assert endpoint < rollback
    assert "read_live_routed_output" not in block


def test_live_timing_has_all_six_triplet_permutations():
    text = _native()
    start = text.index(
        "const std::array<std::array<live_timing_mode, 3>, 6> orders"
    )
    end = text.index("auto run_mode", start)
    block = text[start:end]

    assert block.count("live_timing_mode::stock") == 6
    assert block.count("live_timing_mode::serial") == 6
    assert block.count("live_timing_mode::async") == 6


def test_live_timing_gate_opens_before_warmup_only():
    text = _native()
    start = text.index("live_handoff_timing_result run_live_handoff_timing(")
    end = text.index("void print_parity(", start)
    block = text[start:end]

    gate = block.index("std::filesystem::exists(opt.timing_start_gate)")
    warmup = block.index("round < opt.warmup")

    assert gate < warmup


def test_live_timing_raw_output_contains_no_native_decision():
    text = _native()
    start = text.index("tesy.live_moe_handoff_timing_raw.v1")
    end = text.index("PASS_LIVE_MOE_HANDOFF_TIMING_RAW", start)
    block = text[start:end]

    assert '\"decision\"' not in block
    assert "statistics and decision are recomputed independently" in block


def test_timing_protocol_freezes_budget_and_pivot_rules():
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "research"
        / "LIVE-MOE-HANDOFF-TIMING-PROTOCOL-20260924.md"
    ).read_text(encoding="utf-8")

    assert "stock_route_median_ms - async_route_median_ms" in text
    assert "async route median < stock route median" in text
    assert "async route p95 < stock route p95" in text
    assert "LIVE_MOE_HANDOFF_TIMING_GO" in text
    assert "LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT" in text
    assert "LIVE_MOE_HANDOFF_TIMING_NO_GO" in text


def test_timing_runner_proves_provenance_before_opening_gate():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "scripts" / "run_live_moe_handoff_timing.sh"
    ).read_text(encoding="utf-8")

    provenance = text.index("tesy.mixed_residency_provenance")
    gate = text.index(': >"$gate"')
    resume = text.index('kill -CONT "$active_pid"')

    assert provenance < gate < resume
    assert 'kill -STOP "$active_pid"' in text
    assert "--timing-start-gate" in text


def test_timing_runner_is_fail_closed_and_source_bound():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "scripts" / "run_live_moe_handoff_timing.sh"
    ).read_text(encoding="utf-8")

    assert 'python_bin="$root/.venv/bin/python"' in text
    assert "refusing to replace output root" in text
    assert "capture_source_sha256" in text
    assert "mixed_source_sha256" in text
    assert "run_h 2" in text
    assert "run_h 3" in text
    assert "tesy.live_moe_handoff_timing" in text
    assert '"PHYSICAL"' in text
    assert "peak_process_swap_bytes" in text
