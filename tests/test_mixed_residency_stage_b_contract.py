from pathlib import Path


def test_mixed_residency_native_source_freezes_real_top4_contract():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "constexpr int64_t k_embd = 2880;" in text
    assert "constexpr int k_top_k = 4;" in text
    assert "constexpr size_t k_encoded_bytes_per_expert = 13253760;" in text
    assert "constexpr float k_mix_weight = 0.25f;" in text
    assert "GGML_TYPE_MXFP4" in text
    assert "GGML_TYPE_F32" in text
    assert "ggml_mul_mat_id" in text
    assert "ggml_add_id" in text
    assert "ggml_swiglu_oai" in text
    assert 'cpu_weight_name != "CPU"' not in text
    assert 'std::string(ggml_backend_buft_name(cpu_buft)) != "CPU"' in text


def test_mixed_residency_source_freezes_balanced_case_order():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "measurement_order = {0, 4, 1, 3, 2}" in text
    assert '\"measurement_order\":[0,4,1,3,2]' in text


def test_mixed_residency_runner_binds_admitted_grouped_replay():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_mixed_residency_stage_b.sh").read_text(
        encoding="utf-8"
    )

    assert (
        'expected_histogram_sha="'
        "ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab"
        '"'
    ) in text
    assert '"0": 39' in text
    assert '"1": 26' in text
    assert '"2": 62' in text
    assert '"3": 128' in text
    assert '"4": 105' in text
    assert "abs(float(p.get(\"hit_rate\")) - 0.6625" in text


def test_mixed_residency_runner_requires_live_provenance_before_result():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_mixed_residency_stage_b.sh").read_text(
        encoding="utf-8"
    )

    provenance = text.index("python3 -m tesy.mixed_residency_provenance")
    completion = text.index('stage="benchmark_completion"')
    validation = text.index("python3 -m tesy.mixed_residency_benchmark validate")
    weighting = text.index("python3 -m tesy.mixed_residency_benchmark weight")

    assert provenance < completion < validation < weighting


def test_mixed_residency_runner_does_not_time_weight_transfers():
    root = Path(__file__).resolve().parents[1]
    native = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "weight_h2d" not in native
    assert "Weights are already resident" in native
    assert "no expert-weight transfer" in native
