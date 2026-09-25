#include "ggml-backend.h"
#include "llama.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

[[noreturn]] void fail(const std::string & message) {
    throw std::runtime_error(message);
}

struct args {
    std::string model;
    std::string prompt;
    std::string output_dir;
    int ngl = -1;
    int common_token = -1;
};

args parse(int argc, char ** argv) {
    args result;
    for (int i = 1; i < argc; ++i) {
        const std::string key(argv[i]);
        if (i + 1 >= argc) fail("missing value for " + key);
        const std::string value(argv[++i]);
        if (key == "--model") result.model = value;
        else if (key == "--prompt-file") result.prompt = value;
        else if (key == "--output-dir") result.output_dir = value;
        else if (key == "--ngl") result.ngl = std::stoi(value);
        else if (key == "--common-token") result.common_token = std::stoi(value);
        else fail("unknown argument: " + key);
    }
    if (result.model.empty() || result.prompt.empty() ||
        result.output_dir.empty() ||
        (result.ngl != 0 && result.ngl != 12) ||
        result.common_token < -1) {
        fail("requires --model, --prompt-file, --output-dir, --ngl 0|12; "
             "optional --common-token ID");
    }
    if (result.common_token == -1 && result.ngl != 0) {
        fail("only B0 may define the common token");
    }
    return result;
}

std::vector<llama_token> tokenize(const llama_vocab * vocab,
                                  const std::string & prompt) {
    const auto size = -llama_tokenize(vocab, prompt.data(),
        static_cast<int32_t>(prompt.size()), nullptr, 0, true, true);
    if (size <= 0) fail("invalid tokenization size");
    std::vector<llama_token> tokens(static_cast<size_t>(size));
    if (llama_tokenize(vocab, prompt.data(), static_cast<int32_t>(prompt.size()),
                       tokens.data(), size, true, true) != size) {
        fail("tokenization changed between sizing and fill");
    }
    return tokens;
}

std::vector<float> logits(llama_context * ctx, size_t count) {
    const float * values = llama_get_logits(ctx);
    if (!values) fail("logits unavailable");
    std::vector<float> result(values, values + count);
    if (!std::all_of(result.begin(), result.end(),
                     [](float x) { return std::isfinite(x); })) {
        fail("non-finite logits");
    }
    return result;
}

void write_f32(const std::filesystem::path & path,
               const std::vector<float> & values) {
    FILE * file = std::fopen(path.c_str(), "wbx");
    if (!file) fail("cannot create " + path.string());
    const bool wrote = std::fwrite(values.data(), sizeof(float), values.size(), file)
                       == values.size();
    const int closed = std::fclose(file);
    if (!wrote || closed != 0) fail("cannot write " + path.string());
}

void write_meta(const std::filesystem::path & path,
                const std::vector<llama_token> & prompt_tokens,
                int ngl, int common, int greedy_p, int greedy_d,
                size_t n_vocab) {
    FILE * file = std::fopen(path.c_str(), "wx");
    if (!file) fail("cannot create metadata");
    std::fprintf(file,
        "{\"schema\":\"tesy.stock_prefix_logits_raw.v1\","
        "\"n_gpu_layers\":%d,\"n_ctx\":4096,\"n_threads\":12,"
        "\"n_batch\":%zu,\"n_ubatch\":%zu,\"n_vocab\":%zu,"
        "\"tokenization\":{\"add_special\":true,\"parse_special\":true},"
        "\"prompt_tokens\":[",
        ngl, prompt_tokens.size(), prompt_tokens.size(), n_vocab);
    for (size_t i = 0; i < prompt_tokens.size(); ++i) {
        if (i) std::fputc(',', file);
        std::fprintf(file, "%d", prompt_tokens[i]);
    }
    std::fprintf(file,
        "],\"common_token\":%d,\"greedy_p\":%d,\"greedy_d\":%d,"
        "\"checkpoint_p_file\":\"P.f32\",\"checkpoint_d_file\":\"D.f32\"}\n",
        common, greedy_p, greedy_d);
    if (std::fclose(file) != 0) fail("cannot close metadata");
}

int run(const args & opt) {
    ggml_backend_load_all();
    llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = opt.ngl;
    llama_model * model = llama_model_load_from_file(opt.model.c_str(), mp);
    if (!model) fail("model load failed");
    const llama_vocab * vocab = llama_model_get_vocab(model);
    std::ifstream in(opt.prompt, std::ios::binary);
    if (!in) fail("cannot read prompt");
    const std::string prompt((std::istreambuf_iterator<char>(in)),
                             std::istreambuf_iterator<char>());
    const auto prompt_tokens = tokenize(vocab, prompt);
    if (prompt_tokens.size() + 1 > 4096) fail("prompt exceeds context");
    const auto n_vocab = static_cast<size_t>(llama_vocab_n_tokens(vocab));
    if (n_vocab != 201088) fail("unexpected vocabulary size");
    llama_context_params cp = llama_context_default_params();
    cp.n_ctx = 4096;
    cp.n_batch = static_cast<uint32_t>(prompt_tokens.size());
    cp.n_ubatch = static_cast<uint32_t>(prompt_tokens.size());
    cp.n_threads = 12;
    cp.n_threads_batch = 12;
    cp.no_perf = true;
    llama_context * ctx = llama_init_from_model(model, cp);
    if (!ctx) fail("context init failed");
    llama_sampler_chain_params sp = llama_sampler_chain_default_params();
    sp.no_perf = true;
    llama_sampler * sampler = llama_sampler_chain_init(sp);
    llama_sampler_chain_add(sampler, llama_sampler_init_greedy());
    auto batch = llama_batch_get_one(
        const_cast<llama_token *>(prompt_tokens.data()),
        static_cast<int32_t>(prompt_tokens.size()));
    if (llama_decode(ctx, batch) != 0) fail("prefill failed");
    const auto p = logits(ctx, n_vocab);
    const int greedy_p = llama_sampler_sample(sampler, ctx, -1);
    const int common = opt.common_token == -1 ? greedy_p : opt.common_token;
    if (common < 0 || static_cast<size_t>(common) >= n_vocab) {
        fail("common token outside vocabulary");
    }
    llama_token common_input = common;
    batch = llama_batch_get_one(&common_input, 1);
    if (llama_decode(ctx, batch) != 0) fail("common-token decode failed");
    const auto d = logits(ctx, n_vocab);
    const int greedy_d = llama_sampler_sample(sampler, ctx, -1);
    const auto root = std::filesystem::path(opt.output_dir);
    write_f32(root / "P.f32", p);
    write_f32(root / "D.f32", d);
    write_meta(root / "raw.json", prompt_tokens, opt.ngl,
               common, greedy_p, greedy_d, n_vocab);
    llama_sampler_free(sampler);
    llama_free(ctx);
    llama_model_free(model);
    return 0;
}

}  // namespace

int main(int argc, char ** argv) {
    try {
        return run(parse(argc, argv));
    } catch (const std::exception & e) {
        std::fprintf(stderr, "stock prefix logits: %s\n", e.what());
        return 1;
    }
}
