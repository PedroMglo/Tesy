// Complete fixed-B native verifier diagnostic. No head and no server tokens.
// Build with TESY_BLOCK_CAPTURE pointing to block_prepare_capture.py's output.
#define main tesy_original_capture_main
#include TESY_BLOCK_CAPTURE
#undef main

#include "json.hpp"
#include <chrono>

namespace {
using json = nlohmann::ordered_json;

struct observer {
    capture_state capture;
    int rows = 0;
    int vocab_rows = 0;
    int ffn_rows = 0;
};

bool block_callback(ggml_tensor * tensor, bool ask, void * opaque) {
    auto & state = *static_cast<observer *>(opaque);
    const std::string name = ggml_get_name(tensor);
    if (state.rows > 0 && name == "result_output") {
        check(tensor->ne[0] == 201088 && tensor->ne[1] == state.rows,
              "vocabulary projection omitted block rows");
        state.vocab_rows = static_cast<int>(tensor->ne[1]);
    }
    if (state.rows > 0 && name == "ffn_moe_out-35") {
        check(tensor->ne[1] == state.rows, "last FFN omitted block rows");
        state.ffn_rows = static_cast<int>(tensor->ne[1]);
    }
    return capture(tensor, ask, &state.capture);
}

void persist(const capture_state & state) {
    // Atomic replacement of the live index, never of immutable tensor payloads.
    for (const auto & item : std::array<std::pair<const char *, const std::string *>, 3>{{
        {"index.tsv", &state.index}, {"byte_checks.tsv", &state.checked},
        {"route_prestate.tsv", &state.route_prestate}}}) {
        const auto temp = state.root / (std::string(item.first) + ".partial");
        write_new(temp, item.second->data(), item.second->size());
        std::filesystem::rename(temp, state.root / item.first);
    }
}

llama_token argmax(const float * data, int vocab) {
    check(data != nullptr, "missing native logits");
    int selected = 0;
    for (int i = 0; i < vocab; ++i) {
        check(std::isfinite(data[i]), "non-finite native logit");
        if (data[i] > data[selected]) selected = i;
    }
    return selected;
}

std::vector<float> evaluate(llama_context * ctx, observer & state,
        const std::vector<llama_token> & ids, int position,
        const std::string & phase, bool observed) {
    check(!ids.empty() && ids.size() <= 32, "invalid fixed block size");
    state.rows = static_cast<int>(ids.size());
    state.ffn_rows = state.vocab_rows = 0;
    state.capture.enabled = observed;
    state.capture.prefill = false;
    state.capture.block_tokens = state.rows;
    state.capture.decode_step = position - 189;
    state.capture.phase = phase;
    llama_batch batch = llama_batch_init(state.rows, 0, 1);
    batch.n_tokens = state.rows;
    for (int i = 0; i < state.rows; ++i) {
        batch.token[i] = ids[static_cast<size_t>(i)];
        batch.pos[i] = position + i;
        batch.n_seq_id[i] = 1;
        batch.seq_id[i][0] = 0;
        batch.logits[i] = 1;
    }
    const int rc = llama_decode(ctx, batch);
    llama_batch_free(batch);
    check(rc == 0, "block llama_decode failed");
    llama_synchronize(ctx);
    check(state.ffn_rows == state.rows && state.vocab_rows == state.rows,
          "complete block output graph not witnessed");
    std::vector<float> result(static_cast<size_t>(state.rows)*201088);
    for (int i = 0; i < state.rows; ++i) {
        const float * data = llama_get_logits_ith(ctx, i);
        argmax(data, 201088);
        std::memcpy(result.data()+static_cast<size_t>(i)*201088, data, 201088*sizeof(float));
    }
    if (observed) {
        write_new(state.capture.root / (phase + ".logits.f32"), result.data(), result.size()*sizeof(float));
        persist(state.capture);
    }
    std::cout << "BLOCK_ROWS phase=" << phase << " first_abs=" << position
              << " input=" << state.rows << " last_ffn=" << state.ffn_rows
              << " vocab=" << state.vocab_rows << "\n" << std::flush;
    return result;
}

void trim(llama_context * ctx, int position) {
    llama_synchronize(ctx);
    check(llama_memory_seq_rm(llama_get_memory(ctx), 0, position, -1),
          "KV rollback rejected");
}

void append_record(const std::filesystem::path & root, const json & record) {
    std::ofstream stream(root / "observations.jsonl", std::ios::app);
    check(bool(stream), "cannot persist observations");
    stream << record.dump() << '\n'; stream.flush();
    check(bool(stream), "observation persistence failed");
}
} // namespace

int main(int argc, char ** argv) {
    if (argc != 5) {
        std::cerr << "usage: block_causal_probe MODEL IDS OUTPUT_DIR B(2|4|8)\n";
        return 2;
    }
    llama_model * model = nullptr;
    llama_context * ctx = nullptr;
    try {
        const int B = std::stoi(argv[4]);
        check(B == 2 || B == 4 || B == 8, "unfrozen block shape");
        const auto prompt = ids_for(argv[2], "log_medium", false);
        check(prompt.size() == 189, "official anchor fixture changed");
        check(!std::getenv("GOMP_SPINCOUNT") && !std::getenv("LD_PRELOAD") &&
              !std::getenv("LLAMA_MOE_STREAM_NO_PRELOAD") &&
              !std::getenv("TESY_CPU_FA_PREFILL_VEC_COMPAT"), "profile environment changed");
        observer state;
        state.capture.root = argv[3];
        state.capture.chunk_by_layer.fill(-1);
        check(std::filesystem::create_directory(state.capture.root), "output root reused");
        prepare_canonical(state.capture, argv[1]);
        llama_backend_init();
        auto mp = llama_model_default_params();
        mp.n_gpu_layers = 12; mp.use_mmap = false;
        mp.use_direct_io = true; mp.use_extra_bufts = false;
        mp.moe_stream = true; mp.moe_stream_slots = 40;
        mp.moe_stream_io_threads = 4; mp.moe_stream_direct = true;
        model = llama_model_load_from_file(argv[1], mp);
        check(model != nullptr, "model load failed");
        auto cp = llama_context_default_params();
        cp.n_ctx = 8192; cp.n_batch = 256; cp.n_ubatch = 32;
        cp.n_seq_max = 1; cp.n_threads = 8; cp.n_threads_batch = 8;
        cp.op_offload = false; cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
        cp.type_k = GGML_TYPE_F16; cp.type_v = GGML_TYPE_F16;
        cp.swa_full = true; cp.offload_kqv = true; cp.kv_unified = true;
        cp.cb_eval = block_callback; cp.cb_eval_user_data = &state;
        ctx = llama_init_from_model(model, cp);
        check(ctx != nullptr, "context init failed");
        check(llama_vocab_n_tokens(llama_model_get_vocab(model)) == 201088, "vocabulary changed");
        std::cout << "C80_CONTEXT_READY block=" << B << " K=" << B-1 << " ngl=12 ctx=8192\n" << std::flush;
        // Historical native prefix plan, only its last logit requested.
        decode(ctx, prompt, 0, 0, 189);
        llama_synchronize(ctx);
        std::vector<llama_token> inputs{argmax(llama_get_logits_ith(ctx, -1), 201088)};
        std::vector<float> sequential;
        for (int i = 0; i < B; ++i) {
            const auto row = evaluate(ctx, state, {inputs.back()}, 189+i, "r0_"+std::to_string(i), true);
            sequential.insert(sequential.end(), row.begin(), row.end());
            inputs.push_back(argmax(row.data(), 201088));
        }
        inputs.resize(static_cast<size_t>(B));
        append_record(state.capture.root, {{"phase", "official_native_r0_inputs"}, {"prefix_ids", prompt},
            {"block_input_ids", inputs}, {"B", B}, {"K", B-1}, {"anchor_counted_as_output", false}});
        trim(ctx, 189);
        const auto baseline = evaluate(ctx, state, inputs, 189, "block_base", true);
        int equal_rows = 0, equal_argmax = 0;
        for (int i = 0; i < B; ++i) {
            const size_t offset = static_cast<size_t>(i)*201088;
            equal_rows += std::memcmp(baseline.data()+offset, sequential.data()+offset, 201088*sizeof(float)) == 0;
            equal_argmax += argmax(baseline.data()+offset, 201088) == argmax(sequential.data()+offset, 201088);
        }
        append_record(state.capture.root, {{"phase", "cross_shape_R0"}, {"rows", B},
            {"full_logit_rows_equal", equal_rows}, {"argmax_equal", equal_argmax},
            {"claim", "Observed comparison only; cross-shape bitwise equality is not required"}});
        for (int j = 1; j < B; ++j) {
            auto variant = inputs;
            const auto expected = argmax(baseline.data()+static_cast<size_t>(j-1)*201088, 201088);
            variant[static_cast<size_t>(j)] = (expected + 17) % 201088;
            trim(ctx, 189);
            const auto other = evaluate(ctx, state, variant, 189, "suffix_"+std::to_string(j), true);
            int equal = 0;
            for (int i = 0; i < j; ++i)
                equal += std::memcmp(baseline.data()+static_cast<size_t>(i)*201088,
                    other.data()+static_cast<size_t>(i)*201088, 201088*sizeof(float)) == 0;
            append_record(state.capture.root, {{"phase", "suffix_"+std::to_string(j)},
                {"mutated_input_position", 189+j}, {"official_input_ids", variant},
                {"required_equal_rows", j}, {"actual_equal_rows", equal},
                {"status", equal == j ? "PASS_FIXED_SHAPE_CAUSALITY" : "FAIL_FUTURE_DEPENDENCE"}});
            check(equal == j, "fixed-shape logits depend on a causally masked future input");
            // Clean full-grid resubmission after rejection: expert cache has changed.
            trim(ctx, 189);
            const auto clean = evaluate(ctx, state, inputs, 189, "rollback_"+std::to_string(j), true);
            const bool same = baseline.size() == clean.size() &&
                std::memcmp(baseline.data(), clean.data(), baseline.size()*sizeof(float)) == 0;
            append_record(state.capture.root, {{"phase", "rollback_"+std::to_string(j)},
                {"full_grid_resubmission", true}, {"status", same ? "PASS" : "FAIL_CACHE_OR_ROLLBACK_DEPENDENCE"}});
            check(same, "fixed-shape clean resubmission depends on changed residency or rollback");
        }
        append_record(state.capture.root, {{"status", "PASS_SELECTED_FIXED_SHAPE_CAUSALITY"},
            {"B", B}, {"captured_tensor_bytes", state.capture.bytes},
            {"consumer_byte_checks", state.capture.checked_slices},
            {"scope", "One native 189-token prefix; R1 construction/reference and block timing not yet qualified"}});
        llama_free(ctx); ctx = nullptr;
        llama_model_free(model); model = nullptr;
        llama_backend_free();
        return 0;
    } catch (const std::exception & exc) {
        std::cerr << "BLOCK_PROBE_FAIL: " << exc.what() << "\n";
        if (ctx) llama_free(ctx);
        if (model) llama_model_free(model);
        llama_backend_free();
        return 1;
    }
}
