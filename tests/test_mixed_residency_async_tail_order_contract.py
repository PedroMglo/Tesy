from pathlib import Path


def test_tail_order_runner_freezes_81_samples_and_analysis():
    root = Path(__file__).resolve().parents[1]
    base = (
        root / "scripts" / "run_mixed_residency_async_overlap.sh"
    ).read_text(encoding="utf-8")
    wrapper = (
        root / "scripts" / "run_mixed_residency_async_tail_order.sh"
    ).read_text(encoding="utf-8")

    assert 'TESY_ASYNC_SAMPLES:-21' in base
    assert 'TESY_ASYNC_TAIL_ORDER:-0' in base
    assert 'tail-order diagnostic requires TESY_ASYNC_SAMPLES=81' in base
    assert "tesy.mixed_residency_async_tail_order" in base

    assert "TESY_ASYNC_SAMPLES=81" in wrapper
    assert "TESY_ASYNC_TAIL_ORDER=1" in wrapper
    assert "run_mixed_residency_async_overlap.sh" in wrapper


def test_tail_order_analyzer_freezes_condition_slices():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "src" / "tesy" / "mixed_residency_async_tail_order.py"
    ).read_text(encoding="utf-8")

    assert "async_values[0::2]" in text
    assert "async_values[1::2]" in text
    assert "serial[1::2]" in text
    assert "serial[2::2]" in text
    assert "_EXPECTED_SAMPLES = 81" in text


def test_tail_order_protocol_freezes_median_and_p95_gates():
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "research"
        / "MIXED-RESIDENCY-ASYNC-TAIL-ORDER-PROTOCOL-20260924.md"
    ).read_text(encoding="utf-8")

    assert "AA_median <= 0.90 * SS_median" in text
    assert "AA_p95 <= 1.10 * SS_p95" in text
    assert "ASYNC_STEADY_TAIL_GO" in text
    assert "ASYNC_STEADY_TAIL_NO_GO" in text


def test_tail_order_does_not_change_native_async_schedule():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "post_d2h_gpu_enqueue_cpu_sync_gpu_wait" in text
    assert "even_serial_async_odd_async_serial" in text
    assert "std::thread" not in text
