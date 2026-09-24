from pathlib import Path


def test_reinjection_callback_overwrites_post_compute_and_continues():
    root = Path(__file__).resolve().parents[1]
    native = (root / "native" / "tesy_mixed_residency.cpp").read_text()
    start = native.index("bool reinjection_callback(")
    end = native.index("struct reinjection_arm_result", start)
    callback = native[start:end]
    assert '"ffn_moe_out-0"' in callback
    assert "ggml_backend_tensor_set(tensor" in callback
    assert "state->injection_count++" in callback
    write = callback.index("ggml_backend_tensor_set(tensor")
    assert write < callback.index("return true;", write)


def test_committed_decode_has_no_rollback_and_normal_next_decode():
    root = Path(__file__).resolve().parents[1]
    native = (root / "native" / "tesy_mixed_residency.cpp").read_text()
    start = native.index("llama_batch committed_batch =")
    end = native.index("llama_sampler_free(sampler);", start)
    block = native[start:end]
    assert "llama_memory_seq_rm" not in block
    assert "state.phase = reinjection_phase::disabled;" in block
    assert "llama_decode(ctx, continuation_batch)" in block
    assert "execute_live_routed_async" not in block
