from pathlib import Path


def test_async_candidate_orders_gpu_enqueue_before_cpu_and_gpu_wait():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    block = text.split("auto execute_async_overlap = [&]() {", 1)[1].split(
        "execute_serial();", 1
    )[0]
    enqueue = block.index("compute_async_start(gpu_backend, *gpu_graph);")
    cpu = block.index("compute(cpu_backend, *cpu_graph);")
    gpu_wait = block.index("ggml_backend_synchronize(gpu_backend);", enqueue)

    assert enqueue < cpu < gpu_wait
    assert "std::thread" not in block


def test_async_candidate_requires_gpu_async_capability():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "ggml_backend_dev_get_props(gpu_dev, &gpu_props)" in text
    assert "opt.async_overlap || opt.live_handoff_timing" in text
    assert "&& !gpu_props.caps.async" in text
    assert "GPU backend does not advertise async capability" in text


def test_async_candidate_uses_paired_alternating_measurement():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "measure_paired(" in text
    assert "if ((sample % 2) == 0)" in text
    assert "serial_ms.push_back(measure_one(serial_fn))" in text
    assert "async_ms.push_back(measure_one(async_fn))" in text


def test_async_protocol_freezes_same_ten_percent_gate():
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "research"
        / "MIXED-RESIDENCY-ASYNC-OVERLAP-PROTOCOL-20260924.md"
    ).read_text(encoding="utf-8")

    assert "weighted_async <= 0.90 * weighted_serial" in text
    assert "ASYNC_OVERLAP_MEASURED_GO" in text
    assert "ASYNC_OVERLAP_COMPLEXITY_NO_GO" in text
    assert "prefetch" in text.lower()


def test_async_runner_requires_project_venv_and_new_output_root():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "scripts" / "run_mixed_residency_async_overlap.sh"
    ).read_text(encoding="utf-8")

    assert ".venv/bin/python" in text
    assert "--async-overlap" in text
    assert "refusing to replace output root" in text
    assert "tesy.mixed_residency_async_overlap validate" in text
    assert "tesy.mixed_residency_async_overlap weight" in text
    assert (
        "ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab"
        in text
    )


def test_async_build_is_bound_to_current_source_head():
    root = Path(__file__).resolve().parents[1]
    bootstrap = (
        root / "scripts" / "bootstrap_mixed_residency.sh"
    ).read_text(encoding="utf-8")
    runner = (
        root / "scripts" / "run_mixed_residency_async_overlap.sh"
    ).read_text(encoding="utf-8")

    assert "tesy.mixed_residency_native_build.v1" in bootstrap
    assert "native_source_sha256" in bootstrap
    assert "cmake_lists_sha256" in bootstrap
    assert "tool_sha256" in bootstrap
    assert "tesy_head" in bootstrap
    assert "llama_head" in bootstrap
    assert "tesy-mixed-residency-build-provenance.json" in runner
    assert "native build provenance mismatch" in runner


def test_async_raw_records_schedule_identity():
    root = Path(__file__).resolve().parents[1]
    text = (root / "native" / "tesy_mixed_residency.cpp").read_text(
        encoding="utf-8"
    )

    assert "post_d2h_gpu_enqueue_cpu_sync_gpu_wait" in text
    assert "even_serial_async_odd_async_serial" in text
