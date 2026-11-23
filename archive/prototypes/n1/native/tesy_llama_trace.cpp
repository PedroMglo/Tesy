#include "llama.h"
#include "ggml.h"
#include "ggml-backend.h"

#include <algorithm>
#include <charconv>
#include <clocale>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <string_view>
#include <vector>

namespace {

struct trace_state {
    std::ofstream out;
    bool enabled = false;
    int64_t step = -1;
    llama_token input_token = LLAMA_TOKEN_NULL;
};

bool parse_layer(const char * name, int & layer) {
    constexpr std::string_view prefix = "ffn_moe_topk-";
    if (name == nullptr) {
        return false;
    }
    std::string_view value{name};
    if (value.size() <= prefix.size() || value.substr(0, prefix.size()) != prefix) {
        return false;
    }
    value.remove_prefix(prefix.size());
    int parsed = -1;
    const auto result = std::from_chars(value.data(), value.data() + value.size(), parsed);
    if (result.ec != std::errc{} || result.ptr != value.data() + value.size() || parsed < 0) {
        return false;
    }
    layer = parsed;
    return true;
}

bool trace_eval_callback(ggml_tensor * tensor, bool ask, void * user_data) {
    auto * state = static_cast<trace_state *>(user_data);
    int layer = -1;
    const bool wanted =
        state != nullptr && state->enabled && parse_layer(tensor->name, layer);

    if (ask) {
        return wanted;
    }
    if (!wanted) {
        return true;
    }

    if (tensor->type != GGML_TYPE_I32) {
        std::fprintf(
            stderr,
            "unexpected ffn_moe_topk type for layer %d: %s\n",
            layer,
            ggml_type_name(tensor->type)
        );
        return false;
    }
    if (tensor->ne[1] != 1 || state->step < 0 || state->input_token == LLAMA_TOKEN_NULL) {
        std::fprintf(
            stderr,
            "trace callback requires decode batch=1; layer=%d ne=[%lld,%lld]\n",
            layer,
            static_cast<long long>(tensor->ne[0]),
            static_cast<long long>(tensor->ne[1])
        );
        return false;
    }

    const size_t count = static_cast<size_t>(tensor->ne[0]);
    std::vector<int32_t> ids(count);
    ggml_backend_tensor_get(tensor, ids.data(), 0, count * sizeof(int32_t));

    state->out << "{\"step\":" << state->step
               << ",\"input_token_id\":" << state->input_token
               << ",\"layer\":" << layer
               << ",\"phase\":\"decode\",\"experts\":[";
    for (size_t i = 0; i < ids.size(); ++i) {
        if (i != 0) {
            state->out << ',';
        }
        state->out << ids[i];
    }
    state->out << "]}\n";

    if (!state->out.good()) {
        std::fprintf(stderr, "failed writing routing trace\n");
        return false;
    }
    return true;
}

void usage(const char * argv0) {
    std::fprintf(
        stderr,
        "usage: %s -m MODEL -o TRACE.jsonl [-n TOKENS] [-ngl N] [--cpu-moe] PROMPT\n",
        argv0
    );
}

} // namespace

int main(int argc, char ** argv) {
    std::setlocale(LC_NUMERIC, "C");

    std::string model_path;
    std::string output_path;
    std::string prompt;
    int n_predict = 16;
    int ngl = 0;
    bool cpu_moe = false;

    int i = 1;
    try {
        for (; i < argc; ++i) {
            const std::string_view arg{argv[i]};
            if (arg == "-m" && i + 1 < argc) {
                model_path = argv[++i];
            } else if (arg == "-o" && i + 1 < argc) {
                output_path = argv[++i];
            } else if (arg == "-n" && i + 1 < argc) {
                n_predict = std::stoi(argv[++i]);
            } else if (arg == "-ngl" && i + 1 < argc) {
                ngl = std::stoi(argv[++i]);
            } else if (arg == "--cpu-moe") {
                cpu_moe = true;
            } else {
                break;
            }
        }
    } catch (...) {
        usage(argv[0]);
        return 2;
    }

    for (; i < argc; ++i) {
        if (!prompt.empty()) {
            prompt.push_back(' ');
        }
        prompt += argv[i];
    }

    if (model_path.empty() || output_path.empty() || prompt.empty() || n_predict < 2 || ngl < 0) {
        usage(argv[0]);
        return 2;
    }
    if (std::filesystem::exists(output_path)) {
        std::fprintf(stderr, "refusing to replace existing trace output: %s\n", output_path.c_str());
        return 2;
    }

    ggml_backend_load_all();

    llama_model_params mparams = llama_model_default_params();
    mparams.n_gpu_layers = ngl;

    static const char * moe_pattern = "\\.ffn_(up|down|gate|gate_up)_(ch|)exps";
    llama_model_tensor_buft_override cpu_moe_overrides[] = {
        {moe_pattern, ggml_backend_cpu_buffer_type()},
        {nullptr, nullptr},
    };
    if (cpu_moe) {
        mparams.tensor_buft_overrides = cpu_moe_overrides;
    }

    llama_model * model = llama_model_load_from_file(model_path.c_str(), mparams);
    if (model == nullptr) {
        std::fprintf(stderr, "failed to load model\n");
        return 2;
    }

    const llama_vocab * vocab = llama_model_get_vocab(model);
    const int needed = -llama_tokenize(
        vocab, prompt.c_str(), prompt.size(), nullptr, 0, true, true
    );
    if (needed <= 0) {
        std::fprintf(stderr, "failed to size tokenized prompt\n");
        llama_model_free(model);
        return 2;
    }
    std::vector<llama_token> prompt_tokens(static_cast<size_t>(needed));
    if (llama_tokenize(
            vocab,
            prompt.c_str(),
            prompt.size(),
            prompt_tokens.data(),
            prompt_tokens.size(),
            true,
            true
        ) < 0) {
        std::fprintf(stderr, "failed to tokenize prompt\n");
        llama_model_free(model);
        return 2;
    }

    trace_state trace;
    trace.out.open(output_path, std::ios::out | std::ios::app);
    if (!trace.out.is_open()) {
        std::fprintf(stderr, "failed to open trace output\n");
        llama_model_free(model);
        return 2;
    }

    llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx = static_cast<uint32_t>(std::max<int>(4096, needed + n_predict + 8));
    cparams.n_batch = static_cast<uint32_t>(prompt_tokens.size());
    cparams.n_ubatch = cparams.n_batch;
    cparams.no_perf = false;
    cparams.cb_eval = trace_eval_callback;
    cparams.cb_eval_user_data = &trace;

    llama_context * ctx = llama_init_from_model(model, cparams);
    if (ctx == nullptr) {
        std::fprintf(stderr, "failed to initialize context\n");
        llama_model_free(model);
        return 2;
    }

    auto sparams = llama_sampler_chain_default_params();
    sparams.no_perf = false;
    llama_sampler * sampler = llama_sampler_chain_init(sparams);
    llama_sampler_chain_add(sampler, llama_sampler_init_greedy());

    trace.enabled = false;
    llama_batch batch = llama_batch_get_one(prompt_tokens.data(), prompt_tokens.size());
    if (llama_decode(ctx, batch) != 0) {
        std::fprintf(stderr, "prefill failed\n");
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        return 2;
    }

    llama_token token = llama_sampler_sample(sampler, ctx, -1);
    int generated = 1;
    int routed_steps = 0;

    while (generated < n_predict && !llama_vocab_is_eog(vocab, token)) {
        trace.enabled = true;
        trace.step = routed_steps;
        trace.input_token = token;

        batch = llama_batch_get_one(&token, 1);
        if (llama_decode(ctx, batch) != 0) {
            std::fprintf(stderr, "decode failed\n");
            llama_sampler_free(sampler);
            llama_free(ctx);
            llama_model_free(model);
            return 2;
        }

        ++routed_steps;
        token = llama_sampler_sample(sampler, ctx, -1);
        ++generated;
    }

    trace.enabled = false;
    trace.out.flush();

    std::fprintf(
        stderr,
        "trace complete: generated=%d routed_decode_steps=%d output=%s\n",
        generated,
        routed_steps,
        output_path.c_str()
    );
    llama_perf_sampler_print(sampler);
    llama_perf_context_print(ctx);

    const bool output_ok = trace.out.good();
    llama_sampler_free(sampler);
    llama_free(ctx);
    llama_model_free(model);
    return output_ok ? 0 : 2;
}
