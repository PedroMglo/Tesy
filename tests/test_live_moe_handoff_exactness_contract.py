from pathlib import Path


def test_mixed_tool_links_llama_for_live_handoff():
    root = Path(__file__).resolve().parents[1]
    cmake = (root / "native" / "CMakeLists.txt").read_text(
        encoding="utf-8"
    )
    native = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert '"${LLAMA_CPP_SOURCE_DIR}/include"' in cmake
    assert "target_link_libraries(tesy-mixed-residency PRIVATE llama ggml)" in cmake
    assert '#include "llama.h"' in native


def test_live_handoff_uses_stock_then_handoff_arms_with_rollbacks():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    start = text.index("live_handoff_result run_live_handoff_exactness(")
    end = text.index("live_timing_exactness_snapshot capture_live_timing_pair(", start)
    block = text[start:end]

    assert "live_handoff_arm::stock_reference" in block
    assert "live_handoff_arm::handoff" in block
    assert block.count("llama_memory_seq_rm(") == 2
    assert "stock_capture.stock_output" in block
    assert "handoff_capture.activation" in block
    assert "stock_capture.experts != handoff_capture.experts" in block
    assert "stock_capture.weights != handoff_capture.weights" in block


def test_handoff_callback_early_stops_before_stock_output():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    start = text.index("bool live_handoff_callback(")
    end = text.index("void validate_live_handoff_capture(", start)
    block = text[start:end]

    assert "ffn_moe_weights_softmax-0" in block
    assert "ffn_moe_out-0" in block
    assert "return state->arm != live_handoff_arm::handoff;" in block
    assert 'fail("live handoff arm reached stock MoE output")' in block


def test_live_handoff_reuses_existing_exactness_executor_without_timing():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    live_start = text.index("live_handoff_result run_live_handoff_exactness(")
    live_end = text.index(
        "live_timing_exactness_snapshot capture_live_timing_pair(",
        live_start,
    )
    live = text[live_start:live_end]

    routed_start = text.index("routed_exactness_result run_routed_exactness(")
    routed_end = text.index(
        "live_handoff_result run_live_handoff_exactness(",
        routed_start,
    )
    routed = text[routed_start:routed_end]

    assert "run_routed_exactness(" in live
    assert "measure(" not in live
    assert "measure_paired(" not in live
    assert "measure(" not in routed
    assert "measure_paired(" not in routed


def test_live_handoff_freezes_token_and_expert_identity():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "k_live_handoff_decode_token = 2167" in text
    assert "1, 13, 17, 21" in text
    assert "route differs from admitted experts" in text


def test_live_handoff_protocol_separates_numerical_from_bitwise_exactness():
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "research"
        / "LIVE-MOE-HANDOFF-EXACTNESS-PROTOCOL-20260924.md"
    ).read_text(encoding="utf-8")

    assert "activation_bitwise_equal" in text
    assert "Bitwise equality is diagnostic only" in text
    assert "relative max error <= 0.005" in text
    assert "cosine similarity >= 0.9999" in text


def test_live_handoff_protocol_does_not_authorize_timing_or_reinjection():
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "research"
        / "LIVE-MOE-HANDOFF-EXACTNESS-PROTOCOL-20260924.md"
    ).read_text(encoding="utf-8")

    assert "without timing it" in text
    assert "output reinjection correctness" in text
    assert "committed-token continuation" in text
    assert "do not time the handoff" in text


def test_live_handoff_runner_is_fail_closed_and_source_bound():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "scripts" / "run_live_moe_handoff_exactness.sh"
    ).read_text(encoding="utf-8")

    assert 'python_bin="$root/.venv/bin/python"' in text
    assert "refusing to replace output root" in text
    assert "capture_source_sha256" in text
    assert "mixed_source_sha256" in text
    assert "tesy.mixed_residency_provenance" in text
    assert "kill -STOP" in text
    assert "kill -CONT" in text
    assert "--live-handoff-exactness" in text
    assert "--threads 12" in text
    assert "--ctx 4096" in text
    assert "tesy.live_moe_handoff_exactness" in text
    assert '"PHYSICAL"' in text
    assert "peak_process_swap_bytes" in text


def test_live_handoff_output_contract_contains_no_timing_schema():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    start = text.index('tesy.live_moe_handoff_exactness.v1')
    end = text.index(
        'PASS_LIVE_MOE_HANDOFF_EXACTNESS',
        start,
    )
    block = text[start:end]

    assert "median_ms" not in block
    assert "p95_ms" not in block
    assert "samples_ms" not in block
    assert "speedup" not in block
