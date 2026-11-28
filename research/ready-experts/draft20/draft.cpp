// CPU-only greedy draft with independent teacher forcing on the confirmed prefix.
#include "llama.h"
#include "ggml-backend.h"
#include <openssl/sha.h>

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using Clock = std::chrono::steady_clock;
using Tokens = std::vector<llama_token>;
using Digest = std::array<unsigned char, SHA256_DIGEST_LENGTH>;
using Model = std::unique_ptr<llama_model, decltype(&llama_model_free)>;
using Context = std::unique_ptr<llama_context, decltype(&llama_free)>;
using Path = std::filesystem::path;
constexpr int vocab_size = 201088;

void check(bool ok, const std::string & reason) {
    if (!ok) throw std::runtime_error(reason);
}
int64_t elapsed(Clock::time_point start) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
}
Tokens read_ids(const Path & path) {
    const auto bytes = std::filesystem::file_size(path);
    check(bytes && bytes % 4 == 0 && bytes < 8192 * 4, "invalid ID file");
    Tokens out(bytes / 4);
    std::ifstream file(path, std::ios::binary);
    check(bool(file.read(reinterpret_cast<char *>(out.data()), bytes)), "short ID file");
    for (auto id : out) check(id >= 0 && id < vocab_size, "invalid ID");
    return out;
}
std::string piece(const llama_vocab * v, int id, bool special) {
    std::string out(256, '\0');
    int n = llama_token_to_piece(v, id, out.data(), out.size(), 0, special);
    if (n < 0) {
        out.resize(-n);
        n = llama_token_to_piece(v, id, out.data(), out.size(), 0, special);
    }
    check(n >= 0 && size_t(n) <= out.size(), "vocab piece length");
    out.resize(n);
    return out;
}
Model open_model(const char * path, bool vocab_only) {
    auto p = llama_model_default_params();
    static ggml_backend_dev_t devices[] = {nullptr};
    p.devices = devices;
    p.n_gpu_layers = 0;
    p.load_mode = LLAMA_LOAD_MODE_MMAP;
    p.lazy_mode = LLAMA_LAZY_MODE_OFF;
    p.use_extra_bufts = false;
    p.vocab_only = vocab_only;
    Model m(llama_model_load_from_file(path, p), llama_model_free);
    check(bool(m), "model load");
    return m;
}
void vocab_contract(const llama_vocab * a, const llama_vocab * b) {
    check(llama_vocab_n_tokens(a) == vocab_size && llama_vocab_n_tokens(b) == vocab_size, "vocabulary size");
    for (int id = 0; id < vocab_size; ++id) {
        check(std::strcmp(llama_vocab_get_text(a, id), llama_vocab_get_text(b, id)) == 0 &&
              llama_vocab_get_attr(a, id) == llama_vocab_get_attr(b, id) &&
              llama_vocab_is_eog(a, id) == llama_vocab_is_eog(b, id) &&
              piece(a, id, true) == piece(b, id, true) && piece(a, id, false) == piece(b, id, false),
              "different vocabulary ID " + std::to_string(id));
    }
}
struct Row {
    llama_token top;
    Digest hash;
    int64_t ns;
};
Row logits(llama_context * ctx, int64_t ns) {
    const float * data = llama_get_logits_ith(ctx, -1);
    check(data != nullptr, "missing row");
    int best = 0;
    for (int i = 0; i < vocab_size; ++i) {
        if (!std::isfinite(data[i])) throw std::runtime_error("nonfinite draft logits");
        if (data[i] > data[best]) best = i;
    }
    Row row{best, {}, ns};
    SHA256(reinterpret_cast<const unsigned char *>(data), vocab_size * sizeof(float), row.hash.data());
    return row;
}
Row advance(llama_context * ctx, llama_token token) {
    auto start = Clock::now();
    check(llama_decode(ctx, llama_batch_get_one(&token, 1)) == 0, "single ID decode");
    llama_synchronize(ctx);
    check(llama_get_logits_ith(ctx, -1) != nullptr, "draft logits unavailable");
    return logits(ctx, elapsed(start));
}
Context prompt(llama_model * model, Tokens & ids, const char * pass) {
    auto p = llama_context_default_params();
    p.n_ctx = 8192;
    p.n_batch = p.n_ubatch = 32;
    p.n_threads = p.n_threads_batch = 8;
    p.offload_kqv = p.op_offload = false;
    p.swa_full = true;
    p.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;
    Context ctx(llama_init_from_model(model, p), llama_free);
    check(bool(ctx) && llama_n_ctx(ctx.get()) == 8192, "draft context");
    auto start = Clock::now();
    for (size_t at = 0; at < ids.size(); at += 32) {
        auto n = std::min<size_t>(32, ids.size() - at);
        check(llama_decode(ctx.get(), llama_batch_get_one(ids.data() + at, n)) == 0, "draft prefill");
    }
    llama_synchronize(ctx.get());
    std::cout << "prefill " << pass << ' ' << elapsed(start) << '\n';
    return ctx;
}
void match(const Row & a, const Row & b) {
    check(a.top == b.top && a.hash == b.hash, "confirmed draft prefix differs from reference");
}
void session(llama_model * model, const Path & root, const std::string & name) {
    auto inputs = read_ids(root / (name + "-prompt.i32"));
    auto target = read_ids(root / (name + "-target.i32"));
    const auto * vocab = llama_model_get_vocab(model);
    check(llama_vocab_is_eog(vocab, target.back()), "missing terminal EOG");
    for (size_t i = 0; i + 1 < target.size(); ++i) check(!llama_vocab_is_eog(vocab, target[i]), "early EOG");
    std::cout << "case " << name << '\n';
    std::vector<Row> reference;
    Row ref_prompt{};
    {
        auto ctx = prompt(model, inputs, "serial");
        ref_prompt = logits(ctx.get(), 0);
        for (size_t i = 0; i + 1 < target.size(); ++i) {
            reference.push_back(advance(ctx.get(), target[i]));
            std::cout << "serial " << i << ' ' << reference.back().top << ' ' << reference.back().ns << '\n';
        }
    }
    auto ctx = prompt(model, inputs, "blocks");
    match(ref_prompt, logits(ctx.get(), 0));
    size_t at = 1;
    while (at + 2 < target.size()) {
        const Row first = advance(ctx.get(), target[at - 1]);
        match(first, reference.at(at - 1));
        const Row second = advance(ctx.get(), first.top);
        int accepted = 0;
        int64_t rollback = 0, align = 0;
        if (first.top != target[at]) {
            const auto start = Clock::now();
            check(llama_memory_seq_rm(llama_get_memory(ctx.get()), 0, inputs.size() + at, -1), "draft KV rollback");
            llama_synchronize(ctx.get());
            rollback = elapsed(start);
        } else {
            match(second, reference.at(at));
            accepted = 1;
            if (second.top == target[at + 1]) {
                const Row extra = advance(ctx.get(), second.top);
                match(extra, reference.at(at + 1));
                align = extra.ns;
                accepted = 2;
            }
        }
        std::cout << "block " << at << ' ' << first.top << ' ' << second.top << ' ' << accepted << ' '
                  << first.ns << ' ' << second.ns << ' ' << rollback << ' ' << align << '\n';
        at += 1 + accepted;
    }
    while (at < target.size()) {
        const Row last = advance(ctx.get(), target[at - 1]);
        match(last, reference.at(at - 1));
        std::cout << "tail " << at << ' ' << last.ns << '\n';
        ++at;
    }
    std::cout << "end " << name << '\n' << std::flush;
}
void terminal_code(llama_model * model, const Path & root) {
    auto inputs = read_ids(root / "code-prompt.i32");
    const auto target = read_ids(root / "code-target.i32");
    check(target.size() == 256 && llama_vocab_is_eog(llama_model_get_vocab(model), target.back()), "code end");
    auto ctx = prompt(model, inputs, "serial");
    for (size_t i = 0; i + 1 < target.size(); ++i) {
        check(!llama_vocab_is_eog(llama_model_get_vocab(model), target[i]), "early end");
        const Row first = advance(ctx.get(), target[i]);
        std::cout << "reference " << i << ' ' << first.top << '\n';
        if (i + 2 == target.size()) {
            const Row second = advance(ctx.get(), first.top);
            std::cout << "terminal " << first.top << ' ' << second.top << ' ' << first.ns << ' ' << second.ns << '\n';
        }
    }
}
int main(int argc, char ** argv) try {
    static_assert(sizeof(llama_token) == 4 && std::endian::native == std::endian::little);
    const bool terminal = argc == 5 && std::string(argv[4]) == "--terminal-code";
    check(argc == 4 || terminal, "draft20 TARGET_GGUF DRAFT_GGUF INPUTS [--terminal-code]");
    llama_backend_init();
    std::cout << std::unitbuf;
    ggml_backend_load_all();
    auto target_vocab = open_model(argv[1], true);
    auto draft = open_model(argv[2], false);
    vocab_contract(llama_model_get_vocab(target_vocab.get()), llama_model_get_vocab(draft.get()));
    target_vocab.reset();
    std::cout << "vocabulary " << vocab_size << '\n';
    if (terminal) {
        terminal_code(draft.get(), argv[3]);
    } else {
        session(draft.get(), argv[3], "nominal");
        session(draft.get(), argv[3], "code");
    }
    draft.reset();
    llama_backend_free();
    std::cout << "done\n";
    return 0;
} catch (const std::exception & e) {
    std::cerr << "draft20: " << e.what() << '\n';
    return 1;
}
