from pathlib import Path


def test_overlap_bound_native_source_measures_components_without_async():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "tesy.mixed_residency_overlap_bound_raw.v1" in text
    assert "MEASURED_MIXED_RESIDENCY_COMPONENT_DIAGNOSTIC" in text
    assert "activation_d2h" in text
    assert "cpu_compute" in text
    assert "gpu_compute" in text
    assert "cpu_partial_h2d" in text
    assert "gpu_aggregation" in text
    assert "post_d2h_overlap_bound_median_ms" in text
    assert "ggml_backend_graph_compute_async" not in text
    assert "std::thread" not in text


def test_overlap_bound_formula_uses_max_compute_branch():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "std::max(" in text
    assert "result.cpu_compute.median_ms" in text
    assert "result.gpu_compute.median_ms" in text
    assert "result.activation_d2h.median_ms" in text
    assert "result.cpu_partial_h2d.median_ms" in text
    assert "result.gpu_aggregation.median_ms" in text


def test_overlap_bound_runner_uses_admitted_histogram_and_validator():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_mixed_residency_overlap_bound.sh").read_text(
        encoding="utf-8"
    )

    assert (
        "ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab"
        in text
    )
    assert "tesy.mixed_residency_overlap_bound validate" in text
    assert "tesy.mixed_residency_overlap_bound weight" in text
    assert "PASS_MIXED_RESIDENCY_OVERLAP_BOUND" in text


def test_overlap_bound_protocol_freezes_ten_percent_go_gate():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "research" / "MIXED-RESIDENCY-OVERLAP-BOUND-PROTOCOL-20260924.md"
    ).read_text(encoding="utf-8")

    assert "weighted_bound <= 0.90 * weighted_direct" in text
    assert "OVERLAP_IMPLEMENTATION_GO" in text
    assert "OVERLAP_COMPLEXITY_NO_GO" in text


def test_overlap_bound_aggregation_uses_leaf_partials():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "result->gpu_partial =" in text
    assert "result->cpu_partial =" in text
    assert "ggml_add(ctx, result->gpu_partial, result->cpu_partial)" in text
    assert "aggregate = make_sum_graph(gpu_backend);" in text
    assert "gpu_graph->output, aggregate->gpu_partial" in text
