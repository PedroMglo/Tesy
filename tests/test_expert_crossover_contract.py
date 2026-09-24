from pathlib import Path


def test_crossover_native_source_freezes_real_expert_contract():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_expert_crossover.cpp").read_text(
        encoding="utf-8"
    )

    assert "constexpr int64_t k_embd = 2880;" in text
    assert "constexpr int64_t k_expert_count = 32;" in text
    assert "constexpr size_t k_encoded_bytes_per_expert = 13253760;" in text
    assert "GGML_TYPE_MXFP4" in text
    assert "GGML_TYPE_F32" in text
    assert "ggml_mul_mat_id" in text
    assert "ggml_add_id" in text
    assert "ggml_swiglu_oai" in text
    assert "tensor->nb[n_dims - 1] != per_expert_bytes" in text


def test_crossover_runner_keeps_requested_bytes_separate_from_physical_pcie():
    root = Path(__file__).resolve().parents[1]
    native = (root / "native" / "tesy_expert_crossover.cpp").read_text(
        encoding="utf-8"
    )
    protocol = (root / "research" / "EXPERT-CROSSOVER-PROTOCOL-20260924.md")

    assert "not physical PCIe traffic" in native
    if protocol.exists():
        text = protocol.read_text(encoding="utf-8")
        assert "requested" in text
        assert "physical PCIe" in text


def test_crossover_runner_requires_live_cuda_provenance_before_completion():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "run_expert_crossover.sh").read_text(
        encoding="utf-8"
    )

    provenance = text.index("python3 -m tesy.crossover_provenance")
    completion = text.index('stage="benchmark_completion"')
    validation = text.index("python3 -m tesy.expert_crossover")
    assert provenance < completion < validation
