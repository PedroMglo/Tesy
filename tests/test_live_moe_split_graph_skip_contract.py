"""Contratos model-free da seam experimental e do protocolo congelado."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/llama-cpp-4e416ee73-tesy-split-graph-hook.patch"
NATIVE = ROOT / "native/tesy_mixed_residency.cpp"


def test_patch_is_internal_and_null_path_uses_stock_scheduler() -> None:
    patch = PATCH.read_text(encoding="utf-8")
    assert "diff --git a/src/llama-context.cpp b/src/llama-context.cpp" in patch
    assert "diff --git a/src/llama-context.h b/src/llama-context.h" in patch
    assert "diff --git a/include/llama.h" not in patch
    assert "+        : ggml_backend_sched_graph_compute_async(sched.get(), gf);" in patch
    assert "ggml_backend_sched_alloc_graph" not in patch


def test_split_uses_allocated_graph_views_without_scheduler_reset() -> None:
    source = NATIVE.read_text(encoding="utf-8")
    start = source.index("ggml_status split_graph_compute_hook(")
    end = source.index("struct split_graph_arm_result", start)
    hook = source[start:end]
    assert "ggml_graph_view(graph, 0, state->weights_idx + 1)" in hook
    assert "ggml_graph_view(graph, state->weights_idx + 1," in hook
    assert "ggml_graph_view(graph, state->moe_out_idx + 1," in hook
    assert "ggml_backend_graph_compute(backend_cpu, view)" in hook
    assert "ggml_backend_sched_graph_compute" not in hook
    assert "ggml_backend_sched_reset" not in hook
    assert "state->middle_compute_count" in hook
    assert "state->injected_output_count" in hook


def test_model_free_killer_is_wired_into_ci() -> None:
    cmake = (ROOT / "native/CMakeLists.txt").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "add_executable(tesy-split-graph-model-free" in cmake
    assert "build/native-ci/tesy-split-graph-model-free" in workflow
