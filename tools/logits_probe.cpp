// Fixed-prefix diagnostic for numerical comparison within one llama.cpp SHA.
// The prefix uses GPT-OSS Harmony control tokens; no sampling or free generation.
#include "llama.h"

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char ** argv) {
    if (argc < 5 || argc > 8) {
        std::cerr << "usage: logits_probe MODEL stream|plain N_GPU_LAYERS OUTPUT.f32 [no-repack [N_UBATCH [direct-loader]]]\n";
        return 2;
    }
    const bool streaming = std::strcmp(argv[2], "stream") == 0;
    if (!streaming && std::strcmp(argv[2], "plain") != 0) return 2;
    const bool no_repack = argc >= 6 && std::strcmp(argv[5], "no-repack") == 0;
    if (argc >= 6 && !no_repack) return 2;
    const int n_ubatch = argc == 7 ? std::atoi(argv[6]) : 1;
    const bool direct_loader = argc == 8 && std::strcmp(argv[7], "direct-loader") == 0;
    if (argc == 8 && !direct_loader) return 2;
    const int n_ubatch_value = argc == 8 ? std::atoi(argv[6]) : n_ubatch;
    if (n_ubatch_value < 1 || n_ubatch_value > 64) return 2;
#ifndef STREAMING_BACKEND
    if (streaming) {
        std::cerr << "stock binary has no streaming mode\n";
        return 2;
    }
#endif
    const int gpu_layers = std::atoi(argv[3]);
    const char * prefix = "<|start|>user<|message|>What is 7 plus 5?<|end|><|start|>assistant<|channel|>final<|message|>";
    const char * prefix_limit_env = std::getenv("TESY_LOGITS_PREFIX_TOKENS");
    const char * mmap_plain_env = std::getenv("TESY_LOGITS_PLAIN_MMAP");
    llama_backend_init();
    auto mp = llama_model_default_params();
    mp.n_gpu_layers = gpu_layers;
#ifdef STREAMING_BACKEND
    mp.use_mmap = !streaming && mmap_plain_env != nullptr; // bounded target reference may use mmap
    mp.use_direct_io = direct_loader;
    mp.use_extra_bufts = !no_repack;
    mp.moe_stream = streaming;
    mp.moe_stream_slots = 16;
    mp.moe_stream_io_threads = 4;
    mp.moe_stream_direct = streaming;
#endif
    llama_model * model = llama_model_load_from_file(argv[1], mp);
    if (!model) return 3;
    const llama_vocab * vocab = llama_model_get_vocab(model);
    std::vector<llama_token> tokens(128);
    int n = llama_tokenize(vocab, prefix, std::strlen(prefix), tokens.data(), tokens.size(), true, true);
    if (n <= 0 || n > static_cast<int>(tokens.size())) return 4;
    if (prefix_limit_env) {
        const int limit = std::atoi(prefix_limit_env);
        if (limit < 1 || limit > n) return 4;
        n = limit;
    }
    tokens.resize(n);
    auto cp = llama_context_default_params();
    cp.n_ctx = 4096;
    cp.n_batch = 64;
    cp.n_ubatch = n_ubatch_value;
    cp.n_seq_max = 1;
    cp.n_threads = 8;
    cp.n_threads_batch = 8;
    cp.op_offload = false; // streamed host cache forces this; match the plain reference
    llama_context * ctx = llama_init_from_model(model, cp);
    if (!ctx) return 5;
    llama_batch batch = llama_batch_get_one(tokens.data(), tokens.size());
    if (llama_decode(ctx, batch) != 0) return 6;
    float * logits = llama_get_logits_ith(ctx, -1);
    if (!logits) return 7;
    const int vocab_size = llama_vocab_n_tokens(vocab);
    for (int i = 0; i < vocab_size; ++i) {
        if (!std::isfinite(logits[i])) return 8;
    }
    std::ofstream out(argv[4], std::ios::binary | std::ios::trunc);
    out.write(reinterpret_cast<const char *>(logits), static_cast<std::streamsize>(vocab_size) * sizeof(float));
    out.close();
    if (!out) return 9;
    std::cout << "{\"n_prefix_tokens\":" << tokens.size() << ",\"vocab_size\":" << vocab_size << ",\"token_ids\":[";
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (i) std::cout << ',';
        std::cout << tokens[i];
    }
    std::cout << "]}\n";
#ifdef STREAMING_BACKEND
    if (streaming) llama_moe_stream_print_stats(model);
#endif
    llama_free(ctx);
    llama_model_free(model);
    llama_backend_free();
    return 0;
}
