#include "ggml-backend.h"
#include "ggml.h"
#include "llama.h"

#include <algorithm>
#include <cerrno>
#include <cinttypes>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

namespace {

struct trace_file {
    explicit trace_file(const char * path) {
        file = std::fopen(path, "wx");
        if (!file) {
            std::fprintf(stderr, "cannot create trace %s: %s\n", path, std::strerror(errno));
            std::exit(2);
        }
    }

    ~trace_file() {
        if (file) {
            std::fclose(file);
        }
    }

    FILE * file = nullptr;
    uint64_t graph_seq = 0;
    int last_layer = -1;
    bool seen_layer = false;
    std::vector<unsigned char> scratch;
};

bool parse_layer(const char * name, int * layer) {
    constexpr const char prefix[] = "ffn_moe_topk-";
    constexpr size_t prefix_len = sizeof(prefix) - 1;
    if (std::strncmp(name, prefix, prefix_len) != 0) {
        return false;
    }

    char * end = nullptr;
    errno = 0;
    const long parsed = std::strtol(name + prefix_len, &end, 10);
    if (errno != 0 || end == name + prefix_len || *end != '\0' ||
        parsed < 0 || parsed > INT_MAX) {
        return false;
    }

    *layer = static_cast<int>(parsed);
    return true;
}

bool trace_callback(ggml_tensor * tensor, bool ask, void * user_data) {
    int layer = -1;
    if (!parse_layer(tensor->name, &layer)) {
        return false;
    }

    if (ask) {
        return true;
    }

    auto * state = static_cast<trace_file *>(user_data);
    if (!state || !state->file) {
        return false;
    }

    if (tensor->type != GGML_TYPE_I32 || tensor->ne[0] <= 0 || tensor->ne[1] <= 0) {
        std::fprintf(stderr, "unexpected ffn_moe_topk tensor type/shape at layer %d\n", layer);
        return false;
    }

    if (state->seen_layer && layer <= state->last_layer) {
        ++state->graph_seq;
    }
    state->seen_layer = true;
    state->last_layer = layer;

    const size_t nbytes = ggml_nbytes(tensor);
    state->scratch.resize(nbytes);
    ggml_backend_tensor_get(tensor, state->scratch.data(), 0, nbytes);

    std::fprintf(
        state->file,
        "{\"schema\":\"tesy.llama_moe_topk.v1\","
        "\"graph_seq\":%" PRIu64 ",\"layer\":%d,"
        "\"n_tokens\":%" PRId64 ",\"n_expert_used\":%" PRId64 ","
        "\"experts\":[",
        state->graph_seq,
        layer,
        tensor->ne[1],
        tensor->ne[0]);

    for (int64_t token = 0; token < tensor->ne[1]; ++token) {
        if (token != 0) {
            std::fputc(',', state->file);
        }
        std::fputc('[', state->file);

        for (int64_t slot = 0; slot < tensor->ne[0]; ++slot) {
            if (slot != 0) {
                std::fputc(',', state->file);
            }
            const size_t offset =
                static_cast<size_t>(token) * tensor->nb[1] +
                static_cast<size_t>(slot) * tensor->nb[0];
            if (offset + sizeof(int32_t) > state->scratch.size()) {
                std::fprintf(stderr, "invalid ffn_moe_topk tensor stride at layer %d\n", layer);
                return false;
            }
            int32_t expert = -1;
            std::memcpy(&expert, state->scratch.data() + offset, sizeof(expert));
            std::fprintf(state->file, "%" PRId32, expert);
        }
        std::fputc(']', state->file);
    }

    std::fputs("]}\n", state->file);
    std::fflush(state->file);
    return true;
}

struct options {
    std::string model;
    std::string prompt = "Explain why sparse Mixture-of-Experts models can be memory bound.";
    std::string trace;
    std::string tokens_out;
    int n_predict = 32;
    int n_gpu_layers = 99;
    uint32_t n_ctx = 4096;
    bool chat = true;
};

[[noreturn]] void usage(const char * argv0, int code) {
    std::fprintf(
        code == 0 ? stdout : stderr,
        "usage: %s --model MODEL.gguf --trace TRACE.jsonl "
        "[--prompt TEXT] [--n-predict N] [--ngl N] [--ctx N] [--raw-prompt]\n",
        argv0);
    std::exit(code);
}

int parse_int(const char * value, const char * flag, int minimum) {
    char * end = nullptr;
    errno = 0;
    const long parsed = std::strtol(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0' ||
        parsed < minimum || parsed > INT_MAX) {
        std::fprintf(stderr, "invalid %s value: %s\n", flag, value);
        std::exit(2);
    }
    return static_cast<int>(parsed);
}

options parse_options(int argc, char ** argv) {
    options out;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto require_value = [&](const char * flag) -> const char * {
            if (i + 1 >= argc) {
                std::fprintf(stderr, "missing value for %s\n", flag);
                usage(argv[0], 2);
            }
            return argv[++i];
        };

        if (arg == "--model") {
            out.model = require_value("--model");
        } else if (arg == "--trace") {
            out.trace = require_value("--trace");
        } else if (arg == "--tokens-out") {
            out.tokens_out = require_value("--tokens-out");
        } else if (arg == "--prompt") {
            out.prompt = require_value("--prompt");
        } else if (arg == "--n-predict") {
            out.n_predict = parse_int(require_value("--n-predict"), "--n-predict", 1);
        } else if (arg == "--ngl") {
            out.n_gpu_layers = parse_int(require_value("--ngl"), "--ngl", 0);
        } else if (arg == "--ctx") {
            out.n_ctx = static_cast<uint32_t>(
                parse_int(require_value("--ctx"), "--ctx", 16));
        } else if (arg == "--raw-prompt") {
            out.chat = false;
        } else if (arg == "--help" || arg == "-h") {
            usage(argv[0], 0);
        } else {
            std::fprintf(stderr, "unknown argument: %s\n", arg.c_str());
            usage(argv[0], 2);
        }
    }

    if (out.model.empty()) {
        usage(argv[0], 2);
    }
    return out;
}

std::string apply_single_turn_chat(const llama_model * model, const std::string & prompt) {
    const char * tmpl = llama_model_chat_template(model, nullptr);
    if (!tmpl) {
        std::fprintf(stderr, "model has no default chat template\n");
        std::exit(2);
    }

    llama_chat_message message{"user", prompt.c_str()};
    int32_t size = llama_chat_apply_template(tmpl, &message, 1, true, nullptr, 0);
    if (size < 0) {
        std::fprintf(stderr, "chat template sizing failed\n");
        std::exit(2);
    }

    std::string formatted(static_cast<size_t>(size), '\0');
    const int32_t written = llama_chat_apply_template(
        tmpl, &message, 1, true, formatted.data(), formatted.size());
    if (written < 0 || written > size) {
        std::fprintf(stderr, "chat template rendering failed\n");
        std::exit(2);
    }
    formatted.resize(static_cast<size_t>(written));
    return formatted;
}

std::vector<llama_token> tokenize(
    const llama_vocab * vocab, const std::string & text) {
    const int32_t required =
        -llama_tokenize(vocab, text.c_str(), text.size(), nullptr, 0, true, true);
    if (required <= 0) {
        std::fprintf(stderr, "tokenization sizing failed\n");
        std::exit(2);
    }

    std::vector<llama_token> tokens(static_cast<size_t>(required));
    const int32_t written = llama_tokenize(
        vocab,
        text.c_str(),
        text.size(),
        tokens.data(),
        static_cast<int32_t>(tokens.size()),
        true,
        true);
    if (written < 0) {
        std::fprintf(stderr, "tokenization failed\n");
        std::exit(2);
    }
    tokens.resize(static_cast<size_t>(written));
    return tokens;
}

}  // namespace

int main(int argc, char ** argv) {
    const options opt = parse_options(argc, argv);
    std::unique_ptr<trace_file> trace;
    if (!opt.trace.empty()) {
        trace = std::make_unique<trace_file>(opt.trace.c_str());
    }

    ggml_backend_load_all();

    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = opt.n_gpu_layers;

    llama_model * model = llama_model_load_from_file(opt.model.c_str(), model_params);
    if (!model) {
        std::fprintf(stderr, "failed to load model\n");
        return 2;
    }

    const llama_vocab * vocab = llama_model_get_vocab(model);
    const std::string input = opt.chat ? apply_single_turn_chat(model, opt.prompt) : opt.prompt;
    std::vector<llama_token> prompt_tokens = tokenize(vocab, input);

    const uint64_t minimum_ctx =
        static_cast<uint64_t>(prompt_tokens.size()) +
        static_cast<uint64_t>(opt.n_predict) + 8;
    if (minimum_ctx > opt.n_ctx) {
        std::fprintf(
            stderr,
            "ctx too small: need at least %" PRIu64 ", configured %u\n",
            minimum_ctx,
            opt.n_ctx);
        llama_model_free(model);
        return 2;
    }

    llama_context_params ctx_params = llama_context_default_params();
    ctx_params.n_ctx = opt.n_ctx;
    ctx_params.n_batch = static_cast<uint32_t>(prompt_tokens.size());
    ctx_params.n_ubatch = static_cast<uint32_t>(prompt_tokens.size());
    ctx_params.no_perf = false;
    if (trace) {
        ctx_params.cb_eval = trace_callback;
        ctx_params.cb_eval_user_data = trace.get();
    }

    llama_context * ctx = llama_init_from_model(model, ctx_params);
    if (!ctx) {
        std::fprintf(stderr, "failed to create context\n");
        llama_model_free(model);
        return 2;
    }

    llama_sampler_chain_params sampler_params = llama_sampler_chain_default_params();
    sampler_params.no_perf = false;
    llama_sampler * sampler = llama_sampler_chain_init(sampler_params);
    llama_sampler_chain_add(sampler, llama_sampler_init_greedy());

    llama_batch batch =
        llama_batch_get_one(prompt_tokens.data(), static_cast<int32_t>(prompt_tokens.size()));

    int generated = 0;
    int position = 0;
    std::vector<llama_token> generated_tokens;
    generated_tokens.reserve(static_cast<size_t>(opt.n_predict));
    while (generated < opt.n_predict) {
        if (llama_decode(ctx, batch) != 0) {
            std::fprintf(stderr, "llama_decode failed\n");
            llama_sampler_free(sampler);
            llama_free(ctx);
            llama_model_free(model);
            return 2;
        }

        position += batch.n_tokens;
        llama_token token = llama_sampler_sample(sampler, ctx, -1);
        if (llama_vocab_is_eog(vocab, token)) {
            break;
        }

        char piece[512];
        const int32_t piece_bytes = llama_token_to_piece(
            vocab, token, piece, sizeof(piece), 0, true);
        if (piece_bytes < 0) {
            std::fprintf(stderr, "llama_token_to_piece failed\n");
            break;
        }
        std::fwrite(piece, 1, static_cast<size_t>(piece_bytes), stdout);
        std::fflush(stdout);

        generated_tokens.push_back(token);
        batch = llama_batch_get_one(&token, 1);
        ++generated;
    }

    std::fputc('\n', stdout);

    if (!opt.tokens_out.empty()) {
        FILE * token_file = std::fopen(opt.tokens_out.c_str(), "wx");
        if (!token_file) {
            std::fprintf(
                stderr,
                "cannot create token output %s: %s\n",
                opt.tokens_out.c_str(),
                std::strerror(errno));
            llama_sampler_free(sampler);
            llama_free(ctx);
            llama_model_free(model);
            return 2;
        }

        std::fputs("{\"schema\":\"tesy.generated_tokens.v1\",\"tokens\":[", token_file);
        for (size_t token_index = 0; token_index < generated_tokens.size(); ++token_index) {
            if (token_index != 0) {
                std::fputc(',', token_file);
            }
            std::fprintf(token_file, "%" PRId32, generated_tokens[token_index]);
        }
        std::fputs("]}\n", token_file);

        if (std::fclose(token_file) != 0) {
            std::fprintf(stderr, "failed closing token output %s\n", opt.tokens_out.c_str());
            llama_sampler_free(sampler);
            llama_free(ctx);
            llama_model_free(model);
            return 2;
        }
    }

    std::fprintf(stderr, "generated=%d final_position=%d trace=%s\n",
                 generated, position, opt.trace.c_str());

    llama_perf_sampler_print(sampler);
    llama_perf_context_print(ctx);

    llama_sampler_free(sampler);
    llama_free(ctx);
    llama_model_free(model);
    return 0;
}
