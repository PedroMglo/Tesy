from pathlib import Path


def test_cancel_bound_uses_only_authoritative_route_and_stock_output():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "native" / "tesy_routed_layer_capture.cpp"
    ).read_text(encoding="utf-8")

    assert "ffn_moe_topk-0" in text
    assert "ffn_moe_weights_softmax-0" in text
    assert "ffn_moe_out-0" in text
    assert "cancel-bound ffn_moe_topk-0" in text
    assert "cancel-bound ffn_moe_weights_softmax-0" in text


def test_cancel_bound_is_zero_tesy_work_and_aborts_both_arms():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "native" / "tesy_routed_layer_capture.cpp"
    ).read_text(encoding="utf-8")

    start = text.index("void run_cancel_bound(")
    end = text.index("void write_binary_f32(", start)
    block = text[start:end]

    assert "llama_decode(ctx, batch)" in block
    assert "rc != 2" in block
    assert "make_compute_graph" not in block
    assert "compute_async_start" not in block
    assert "tesy-mixed-residency" not in block
    assert "ggml_backend_tensor_copy" not in block


def test_cancel_callback_starts_after_routing_weights_and_stock_stops_at_output():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "native" / "tesy_routed_layer_capture.cpp"
    ).read_text(encoding="utf-8")

    callback = text.split("bool cancel_bound_callback(", 1)[1].split(
        "timing_summary summarize_timings",
        1,
    )[0]

    weights = callback.index(
        'exact_name(tensor, "ffn_moe_weights_softmax-0")'
    )
    start = callback.index(
        "state->start = std::chrono::steady_clock::now();"
    )
    output = callback.index('exact_name(tensor, "ffn_moe_out-0")')
    stock_end = callback.index(
        "state->stock_end = std::chrono::steady_clock::now();"
    )

    assert weights < start
    assert output < stock_end
    assert "return state->arm != cancel_bound_arm::cancel;" in callback
    assert "return false;" in callback


def test_cancel_bound_freezes_samples_order_and_route_identity():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "native" / "tesy_routed_layer_capture.cpp"
    ).read_text(encoding="utf-8")

    assert "cancel bound requires --samples 81" in text
    assert "cancel bound requires --warmup 6" in text
    assert "even_stock_cancel_odd_cancel_stock" in text
    assert "routed expert IDs changed across trials" in text
    assert "routing weights changed across trials" in text


def test_cancel_bound_suppresses_only_expected_abort_logging():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "native" / "tesy_routed_layer_capture.cpp"
    ).read_text(encoding="utf-8")

    branch = text.split(
        'if (!opt.cancel_bound_output.empty()) {',
        1,
    )[1].split(
        "batch = llama_batch_get_one(&first, 1);",
        1,
    )[0]

    assert "llama_log_get" in branch
    assert "llama_log_set(silent_log_callback, nullptr)" in branch
    assert "run_cancel_bound" in branch
    assert "llama_log_set(" in branch
    assert "previous_log" in branch


def test_cancel_bound_protocol_freezes_hard_no_go_inequalities():
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "research"
        / "CB-EVAL-INTERCEPT-BOUND-PROTOCOL-20260924.md"
    ).read_text(encoding="utf-8")

    assert "median(T_cancel) >= median(T_stock)" in text
    assert "p95(T_cancel) >= p95(T_stock)" in text
    assert "CB_EVAL_INTERCEPT_HARD_NO_GO" in text
    assert "CB_EVAL_INTERCEPT_BOUND_SURVIVES" in text
    assert "zero-Tesy-work" in text


def test_cancel_bound_runner_is_fail_closed_and_source_bound():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "scripts" / "run_cb_eval_intercept_bound.sh"
    ).read_text(encoding="utf-8")

    assert 'python_bin="$root/.venv/bin/python"' in text
    assert "refusing to replace output root" in text
    assert "tesy.routed_layer_native_build.v1" in text
    assert "capture_source_sha256" in text
    assert "tesy.process_identity" in text
    assert "tesy.cb_eval_intercept_bound" in text
    assert "--warmup 6" in text
    assert "--samples 81" in text
    assert '"PHYSICAL"' in text
    assert "peak_process_swap_bytes" in text
