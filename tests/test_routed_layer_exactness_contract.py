from pathlib import Path


def test_routed_capture_requests_stock_router_boundary_tensors():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_routed_layer_capture.cpp").read_text(
        encoding="utf-8"
    )

    for name in (
        "attn_post_norm-0",
        "ffn_moe_topk-0",
        "ffn_moe_weights_softmax-0",
        "ffn_moe_weights_scaled-0",
        "ffn_moe_out-0",
    ):
        assert name in text

    assert "ggml_backend_tensor_get" in text


def test_routed_capture_only_enables_callback_for_decode_event():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_routed_layer_capture.cpp").read_text(
        encoding="utf-8"
    )

    prefill = text.index('if (llama_decode(ctx, batch) != 0)')
    enable = text.index("capture.enabled = !opt.capture_dir.empty();")
    decode = text.index('if (llama_decode(ctx, batch) != 0)', prefill + 1)
    disable = text.index("capture.enabled = false;", enable)

    assert prefill < enable < decode < disable


def test_routed_replay_uses_exact_weights_and_stock_reference():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "--routed-exactness" in text
    assert "--routed-input-f32" in text
    assert "--routed-reference-f32" in text
    assert "--routed-experts" in text
    assert "--routed-weights" in text
    assert "TOPK_SLOT_PREFIX_GPU_REMAINDER_CPU" in text
    assert "compare_outputs(stock_reference, serial_output)" in text
    assert "compare_outputs(stock_reference, async_output)" in text
    assert "compare_outputs(serial_output, async_output)" in text


def test_routed_exactness_path_has_no_timing_or_prefetch_policy():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    block = text.split("if (opt.routed_exactness) {", 1)[1].split(
        "const std::vector<float> input = deterministic_input();",
        1,
    )[0]

    assert "measure(" not in block
    assert "measure_paired(" not in block
    assert "prefetch" not in block.lower()
    assert "cache" not in block.lower()


def test_routed_protocol_requires_token_and_stock_output_exactness():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "research" / "ROUTED-LAYER-EXACTNESS-PROTOCOL-20260924.md"
    ).read_text(encoding="utf-8")

    assert "ROUTED_LAYER_EXACTNESS_GO" in text
    assert "OFF" in text and "ON" in text
    assert "greedy token" in text.lower()
    assert "serial_vs_stock" in text
    assert "async_vs_stock" in text
    assert "No routed-layer timing is authorized" in text


def test_routed_runner_is_no_replace_and_uses_project_venv():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "scripts" / "run_routed_layer_exactness.sh"
    ).read_text(encoding="utf-8")

    assert ".venv/bin/python" in text
    assert "refusing to replace output root" in text
    assert "ROUTED_LAYER_EXACTNESS_GO" in text
    assert "benchmarks/prompts/b0-b1-diagnostic.txt" in text
    assert "--ngl 0" in text


def test_routed_build_binds_both_native_sources_and_tools():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "scripts" / "bootstrap_routed_layer_exactness.sh"
    ).read_text(encoding="utf-8")

    assert "tesy.routed_layer_native_build.v1" in text
    assert "mixed_source_sha256" in text
    assert "capture_source_sha256" in text
    assert "mixed_tool_sha256" in text
    assert "capture_tool_sha256" in text
    assert "tesy-routed-layer-capture" in text


def test_routed_runner_freezes_live_provenance_before_replay():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "scripts" / "run_routed_layer_exactness.sh"
    ).read_text(encoding="utf-8")

    assert "tesy.process_identity" in text
    assert "kill -STOP" in text
    assert "tesy.mixed_residency_provenance" in text
    assert "kill -CONT" in text
    assert "run_replay 2" in text
    assert "run_replay 3" in text
