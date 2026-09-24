#include "ggml-backend.h"
#include "ggml.h"
#include "llama.h"

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {

constexpr int64_t k_embd = 2880;
constexpr int64_t k_top_k = 4;
constexpr int k_generated_tokens = 2;

[[noreturn]] void fail(const std::string & message) {
    std::fprintf(stderr, "%s\n", message.c_str());
    std::exit(2);
}

struct options {
    std::string model;
    std::string prompt_file;
    std::string tokens_out;
    std::string capture_dir;
    int n_gpu_layers = 0;
    uint32_t n_ctx = 4096;
};

int parse_int(const char * value, const char * flag, int minimum) {
    char * end = nullptr;
    errno = 0;
    const long parsed = std::strtol(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0' ||
        parsed < minimum || parsed > INT32_MAX) {
        fail(std::string("invalid ") + flag + ": " + value);
    }
    return static_cast<int>(parsed);
}

[[noreturn]] void usage(const char * argv0, int code) {
    std::fprintf(
        code == 0 ? stdout : stderr,
        "usage: %s --model MODEL.gguf --prompt-file PROMPT "
        "--tokens-out TOKENS.json [--capture-dir DIR] "
        "[--ngl N] [--ctx N]\n",
        argv0);
    std::exit(code);
}

options parse_options(int argc, char ** argv) {
    options out;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto value = [&](const char * flag) -> const char * {
            if (i + 1 >= argc) {
                fail(std::string("missing value for ") + flag);
            }
            return argv[++i];
        };

        if (arg == "--model") {
            out.model = value("--model");
        } else if (arg == "--prompt-file") {
            out.prompt_file = value("--prompt-file");
        } else if (arg == "--tokens-out") {
            out.tokens_out = value("--tokens-out");
        } else if (arg == "--capture-dir") {
            out.capture_dir = value("--capture-dir");
        } else if (arg == "--ngl") {
            out.n_gpu_layers = parse_int(value("--ngl"), "--ngl", 0);
        } else if (arg == "--ctx") {
            out.n_ctx = static_cast<uint32_t>(
                parse_int(value("--ctx"), "--ctx", 16));
        } else if (arg == "--help" || arg == "-h") {
            usage(argv[0], 0);
        } else {
            fail("unknown argument: " + arg);
        }
    }

    if (out.model.empty() || out.prompt_file.empty() || out.tokens_out.empty()) {
        usage(argv[0], 2);
    }
    return out;
}

std::string read_text_file(const std::string & path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        fail("cannot open prompt file: " + path);
    }
    return std::string(
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>());
}

std::vector<llama_token> tokenize(
        const llama_vocab * vocab,
        const std::string & text) {
    const int32_t required =
        -llama_tokenize(
            vocab,
            text.c_str(),
            static_cast<int32_t>(text.size()),
            nullptr,
            0,
            true,
            true);
    if (required <= 0) {
        fail("tokenization sizing failed");
    }

    std::vector<llama_token> tokens(static_cast<size_t>(required));
    const int32_t written =
        llama_tokenize(
            vocab,
            text.c_str(),
            static_cast<int32_t>(text.size()),
            tokens.data(),
            static_cast<int32_t>(tokens.size()),
            true,
            true);
    if (written <= 0 || written > required) {
        fail("tokenization failed");
    }
    tokens.resize(static_cast<size_t>(written));
    return tokens;
}

bool exact_name(const ggml_tensor * tensor, const char * expected) {
    return std::strcmp(tensor->name, expected) == 0;
}

template <typename T>
std::vector<T> read_contiguous_tensor(
        ggml_tensor * tensor,
        ggml_type expected_type,
        size_t expected_elements,
        const char * label) {
    if (tensor->type != expected_type) {
        fail(std::string(label) + " has unexpected tensor type");
    }
    if (!ggml_is_contiguous(tensor)) {
        fail(std::string(label) + " must be contiguous");
    }
    const size_t elements = static_cast<size_t>(ggml_nelements(tensor));
    if (elements != expected_elements) {
        fail(
            std::string(label) + " element count mismatch: " +
            std::to_string(elements));
    }
    if (ggml_nbytes(tensor) != elements * sizeof(T)) {
        fail(std::string(label) + " byte count mismatch");
    }

    std::vector<T> out(elements);
    ggml_backend_tensor_get(
        tensor,
        out.data(),
        0,
        out.size() * sizeof(T));
    return out;
}

struct capture_state {
    bool enabled = false;

    std::vector<float> activation;
    std::vector<int32_t> experts;
    std::vector<float> weights_softmax;
    std::vector<float> weights_scaled;
    std::vector<float> stock_output;

    bool saw_activation = false;
    bool saw_experts = false;
    bool saw_weights_softmax = false;
    bool saw_weights_scaled = false;
    bool saw_stock_output = false;
};

bool routed_capture_callback(
        ggml_tensor * tensor,
        bool ask,
        void * user_data) {
    auto * state = static_cast<capture_state *>(user_data);
    if (!state || !state->enabled) {
        return false;
    }

    const bool wanted =
        exact_name(tensor, "attn_post_norm-0") ||
        exact_name(tensor, "ffn_moe_topk-0") ||
        exact_name(tensor, "ffn_moe_weights_softmax-0") ||
        exact_name(tensor, "ffn_moe_weights_scaled-0") ||
        exact_name(tensor, "ffn_moe_out-0");

    if (ask) {
        return wanted;
    }
    if (!wanted) {
        return false;
    }

    if (exact_name(tensor, "attn_post_norm-0")) {
        if (state->saw_activation) {
            fail("duplicate attn_post_norm-0 capture");
        }
        state->activation = read_contiguous_tensor<float>(
            tensor,
            GGML_TYPE_F32,
            static_cast<size_t>(k_embd),
            "attn_post_norm-0");
        state->saw_activation = true;
        return true;
    }

    if (exact_name(tensor, "ffn_moe_topk-0")) {
        if (state->saw_experts) {
            fail("duplicate ffn_moe_topk-0 capture");
        }
        state->experts = read_contiguous_tensor<int32_t>(
            tensor,
            GGML_TYPE_I32,
            static_cast<size_t>(k_top_k),
            "ffn_moe_topk-0");
        state->saw_experts = true;
        return true;
    }

    if (exact_name(tensor, "ffn_moe_weights_softmax-0")) {
        if (state->saw_weights_softmax) {
            fail("duplicate ffn_moe_weights_softmax-0 capture");
        }
        state->weights_softmax = read_contiguous_tensor<float>(
            tensor,
            GGML_TYPE_F32,
            static_cast<size_t>(k_top_k),
            "ffn_moe_weights_softmax-0");
        state->saw_weights_softmax = true;
        return true;
    }

    if (exact_name(tensor, "ffn_moe_weights_scaled-0")) {
        if (state->saw_weights_scaled) {
            fail("duplicate ffn_moe_weights_scaled-0 capture");
        }
        state->weights_scaled = read_contiguous_tensor<float>(
            tensor,
            GGML_TYPE_F32,
            static_cast<size_t>(k_top_k),
            "ffn_moe_weights_scaled-0");
        state->saw_weights_scaled = true;
        return true;
    }

    if (exact_name(tensor, "ffn_moe_out-0")) {
        if (state->saw_stock_output) {
            fail("duplicate ffn_moe_out-0 capture");
        }
        state->stock_output = read_contiguous_tensor<float>(
            tensor,
            GGML_TYPE_F32,
            static_cast<size_t>(k_embd),
            "ffn_moe_out-0");
        state->saw_stock_output = true;
        return true;
    }

    return false;
}

void validate_capture(capture_state & state) {
    if (!state.saw_activation ||
        !state.saw_experts ||
        !state.saw_weights_softmax ||
        !state.saw_stock_output) {
        fail("incomplete routed-layer capture");
    }

    std::vector<int32_t> sorted = state.experts;
    std::sort(sorted.begin(), sorted.end());
    if (std::adjacent_find(sorted.begin(), sorted.end()) != sorted.end()) {
        fail("router returned duplicate experts");
    }
    for (const int32_t expert : state.experts) {
        if (expert < 0 || expert >= 32) {
            fail("router expert id outside 0..31");
        }
    }

    const std::vector<float> & final_weights =
        state.saw_weights_scaled
            ? state.weights_scaled
            : state.weights_softmax;
    for (float value : final_weights) {
        if (!std::isfinite(value) || value < 0.0f) {
            fail("routing weight must be finite and non-negative");
        }
    }
    for (float value : state.activation) {
        if (!std::isfinite(value)) {
            fail("captured activation contains non-finite value");
        }
    }
    for (float value : state.stock_output) {
        if (!std::isfinite(value)) {
            fail("captured stock output contains non-finite value");
        }
    }
}

void write_binary_f32(
        const std::filesystem::path & path,
        const std::vector<float> & values) {
    FILE * file = std::fopen(path.c_str(), "wbx");
    if (!file) {
        fail(
            "cannot create " + path.string() + ": " +
            std::strerror(errno));
    }
    const size_t written =
        std::fwrite(
            values.data(),
            sizeof(float),
            values.size(),
            file);
    if (written != values.size() || std::fclose(file) != 0) {
        fail("failed writing " + path.string());
    }
}

void write_tokens(
        const std::string & path,
        const std::vector<llama_token> & tokens) {
    FILE * file = std::fopen(path.c_str(), "wx");
    if (!file) {
        fail(
            "cannot create token output " + path + ": " +
            std::strerror(errno));
    }
    std::fputs(
        "{\"schema\":\"tesy.routed_layer_capture_tokens.v1\","
        "\"classification\":\"MEASURED_GREEDY_TOKEN_IDS\","
        "\"tokens\":[",
        file);
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (i != 0) {
            std::fputc(',', file);
        }
        std::fprintf(file, "%" PRId32, tokens[i]);
    }
    std::fputs("]}\n", file);
    if (std::fclose(file) != 0) {
        fail("failed closing token output");
    }
}

void write_capture(
        const std::string & root_path,
        capture_state & state,
        llama_token decode_input_token,
        llama_token decode_output_token) {
    validate_capture(state);

    const std::filesystem::path root(root_path);
    std::error_code error;
    if (!std::filesystem::create_directory(root, error)) {
        fail(
            "refusing or unable to create capture directory: " +
            root.string());
    }

    write_binary_f32(root / "activation.f32", state.activation);
    write_binary_f32(root / "stock-output.f32", state.stock_output);

    const std::vector<float> & final_weights =
        state.saw_weights_scaled
            ? state.weights_scaled
            : state.weights_softmax;
    const char * weight_stage =
        state.saw_weights_scaled
            ? "ffn_moe_weights_scaled-0"
            : "ffn_moe_weights_softmax-0";

    const std::filesystem::path metadata = root / "metadata.json";
    FILE * file = std::fopen(metadata.c_str(), "wx");
    if (!file) {
        fail(
            "cannot create metadata " + metadata.string() + ": " +
            std::strerror(errno));
    }

    std::fprintf(
        file,
        "{\"schema\":\"tesy.routed_layer_capture.v1\","
        "\"classification\":\"MEASURED_STOCK_ROUTED_LAYER_CAPTURE\","
        "\"layer\":0,\"phase\":\"decode\","
        "\"n_embd\":%" PRId64 ",\"n_expert_used\":%" PRId64 ","
        "\"decode_input_token\":%" PRId32 ","
        "\"decode_output_token\":%" PRId32 ","
        "\"activation_tensor\":\"attn_post_norm-0\","
        "\"topk_tensor\":\"ffn_moe_topk-0\","
        "\"routing_weight_tensor\":\"%s\","
        "\"stock_output_tensor\":\"ffn_moe_out-0\","
        "\"selected_experts\":[",
        k_embd,
        k_top_k,
        decode_input_token,
        decode_output_token,
        weight_stage);

    for (size_t i = 0; i < state.experts.size(); ++i) {
        if (i != 0) {
            std::fputc(',', file);
        }
        std::fprintf(file, "%" PRId32, state.experts[i]);
    }

    std::fputs("],\"routing_weights\":[", file);
    for (size_t i = 0; i < final_weights.size(); ++i) {
        if (i != 0) {
            std::fputc(',', file);
        }
        std::fprintf(file, "%.9g", final_weights[i]);
    }

    std::fputs(
        "],\"activation_file\":\"activation.f32\","
        "\"stock_output_file\":\"stock-output.f32\","
        "\"claim_boundary\":"
        "\"Exact stock llama.cpp layer-0 decode activation, router top-k, "
        "final routing weights and MoE output captured via cb_eval. "
        "The capture is diagnostic and does not replace routing or expert "
        "execution in the stock decode.\"}\n",
        file);

    if (std::fclose(file) != 0) {
        fail("failed closing routed capture metadata");
    }
}

}  // namespace

int main(int argc, char ** argv) {
    const options opt = parse_options(argc, argv);

    const std::string prompt = read_text_file(opt.prompt_file);
    ggml_backend_load_all();

    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = opt.n_gpu_layers;

    llama_model * model =
        llama_model_load_from_file(opt.model.c_str(), model_params);
    if (!model) {
        fail("failed to load model");
    }

    const llama_vocab * vocab = llama_model_get_vocab(model);
    std::vector<llama_token> prompt_tokens = tokenize(vocab, prompt);

    const uint64_t minimum_ctx =
        static_cast<uint64_t>(prompt_tokens.size()) +
        static_cast<uint64_t>(k_generated_tokens) + 8;
    if (minimum_ctx > opt.n_ctx) {
        llama_model_free(model);
        fail("configured context is too small");
    }

    capture_state capture;

    llama_context_params ctx_params = llama_context_default_params();
    ctx_params.n_ctx = opt.n_ctx;
    ctx_params.n_batch = static_cast<uint32_t>(prompt_tokens.size());
    ctx_params.n_ubatch = static_cast<uint32_t>(prompt_tokens.size());
    ctx_params.no_perf = false;
    if (!opt.capture_dir.empty()) {
        ctx_params.cb_eval = routed_capture_callback;
        ctx_params.cb_eval_user_data = &capture;
    }

    llama_context * ctx = llama_init_from_model(model, ctx_params);
    if (!ctx) {
        llama_model_free(model);
        fail("failed to create context");
    }

    llama_sampler_chain_params sampler_params =
        llama_sampler_chain_default_params();
    sampler_params.no_perf = false;
    llama_sampler * sampler = llama_sampler_chain_init(sampler_params);
    llama_sampler_chain_add(sampler, llama_sampler_init_greedy());

    llama_batch batch =
        llama_batch_get_one(
            prompt_tokens.data(),
            static_cast<int32_t>(prompt_tokens.size()));

    if (llama_decode(ctx, batch) != 0) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("prompt llama_decode failed");
    }

    std::vector<llama_token> generated;
    generated.reserve(k_generated_tokens);

    const llama_token first =
        llama_sampler_sample(sampler, ctx, -1);
    if (llama_vocab_is_eog(vocab, first)) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("first greedy token is EOG; cannot capture decode layer");
    }
    generated.push_back(first);

    batch = llama_batch_get_one(&first, 1);
    capture.enabled = !opt.capture_dir.empty();
    if (llama_decode(ctx, batch) != 0) {
        capture.enabled = false;
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("decode llama_decode failed");
    }
    capture.enabled = false;

    const llama_token second =
        llama_sampler_sample(sampler, ctx, -1);
    generated.push_back(second);

    write_tokens(opt.tokens_out, generated);

    if (!opt.capture_dir.empty()) {
        write_capture(
            opt.capture_dir,
            capture,
            first,
            second);
    }

    llama_sampler_free(sampler);
    llama_free(ctx);
    llama_model_free(model);

    std::printf("PASS_ROUTED_LAYER_CAPTURE\n");
    std::printf("tokens: %s\n", opt.tokens_out.c_str());
    if (!opt.capture_dir.empty()) {
        std::printf("capture: %s\n", opt.capture_dir.c_str());
    }
    return 0;
}
