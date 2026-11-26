// Included by the private client after the shared observer and the model census.
#include "ids_expected.hpp"
#include <charconv>
#include <string_view>

static int numbered_layer(std::string_view name, std::string_view prefix) {
    if (name.substr(0, prefix.size()) != prefix) return -1;
    auto digits = name.substr(prefix.size());
    if (digits.empty() || (digits.size() > 1 && digits.front() == '0')) return -1;
    int layer = -1;
    auto parsed = std::from_chars(digits.data(), digits.data() + digits.size(), layer);
    return parsed.ec == std::errc{} && parsed.ptr == digits.data() + digits.size() &&
           layer >= 0 && layer < 36 ? layer : -1;
}

static bool real_router(const char *name) {
    return numbered_layer(name, "ffn_moe_topk-") >= 0;
}

static int rank_width(const char *name) {
    const std::string_view value(name);
    const auto dash = value.rfind('-');
    must(dash != std::string_view::npos, "unnumbered routed operation");
    const int layer = numbered_layer(value, value.substr(0, dash + 1));
    must(layer >= 0 && (observe::phase == 3 || observe::phase == 4), "invalid routed operation");
    return observe::phase == 3 && layer < 35 ? 16 : 1;
}

static void compare_bias(const ggml_tensor *node, const ggml_tensor *operand, const std::string &ranks) {
    std::string name = node->name;
    const auto suffix = name.find("_biased-");
    must(name.rfind("ffn_moe_", 0) == 0 && suffix != std::string::npos, "bias node name");
    auto role = name.substr(8, suffix - 8);
    const auto layer = numbered_layer(name, name.substr(0, suffix + 8));
    must(layer >= 0 && (role == "gate" || role == "up" || role == "down"), "bias site");
    auto key = "blk." + std::to_string(layer) + ".ffn_" + role + "_exps.bias";
    const auto *ref = host_biases.at(key);
    constexpr size_t width = 2880 * sizeof(float);
    must(operand->type == GGML_TYPE_F32 && operand->ne[0] == 2880 && operand->ne[1] == 128 &&
         operand->ne[2] == 1 && operand->ne[3] == 1 && operand->nb[0] == 4 &&
         operand->nb[1] == width && ref->nb[1] == width, "logical bias layout");
    const auto offset = observe::file_offset(ref->data, ggml_nbytes(ref));
    must(offset >= 0, "missing bias file view");
    std::array<bool,128> seen{};
    std::array<float,2880> values{};
    std::istringstream stream(ranks);
    std::string value;
    int verified = 0;
    while (std::getline(stream, value, ',')) {
        const int e = std::stoi(value);
        must(e >= 0 && e < 128, "invalid bias expert");
        if (seen[e]) continue;
        seen[e] = true;
        ggml_backend_tensor_get(operand, values.data(), size_t(e)*width, width);
        const char *gold = static_cast<const char *>(ref->data) + size_t(e)*width;
        must(std::memcmp(values.data(), gold, width) == 0, "effective logical bias bits differ");
        ++verified;
    }
    std::printf("BIAS_READ %d %s %s %zu %zu %lld %d %zu\n", observe::phase, node->name, key.c_str(),
                uintptr_t(operand->data), uintptr_t(ref->data), (long long)offset, verified, verified * width);
}

static std::array<llama_token, 17> read_input(const char *path) {
    static_assert(sizeof(llama_token) == 4 && sizeof(float) == 4);
    static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);
    std::array<llama_token, 17> ids{};
    std::ifstream f(path, std::ios::binary);
    must(bool(f.read(reinterpret_cast<char *>(ids.data()), sizeof(ids))) &&
         f.peek() == std::ifstream::traits_type::eof() && !f.bad(), "expected 17 supplied IDs");
    must(ids == expected_ids && ids.back() == 976, "sealed C110 input mismatch");
    return ids;
}

static int save_cut(llama_context *ctx, const fs::path &dir, int pos, int expected) {
    constexpr int vocab = 201088;
    auto logits = llama_get_logits_ith(ctx, -1);
    must(logits != nullptr, "last full row missing");
    std::ofstream out(dir / ("pos" + std::to_string(pos) + ".f32"), std::ios::binary);
    out.write(reinterpret_cast<const char *>(logits), vocab * sizeof(float));
    out.close();
    must(bool(out), "failed to preserve row");
    int best = 0, ties = 0;
    for (int i = 0; i < vocab; ++i) {
        if (!std::isfinite(logits[i])) return 45;
        if (logits[i] > logits[best]) { best = i; ties = 1; }
        else if (logits[i] == logits[best]) ++ties;
    }
    std::printf("ROW %d %d %d %d\n", pos, vocab, best, ties);
    return ties == 1 && expected == best ? 0 : (pos == 15 ? 42 : 43);
}

static int supplied_cuts(llama_context *ctx, const fs::path &dir, std::array<llama_token,17> &ids) {
    must(llama_n_threads(ctx) == 8 && llama_n_threads_batch(ctx) == 8, "GGML team");
    for (int pos : {15,16}) {
        const bool prefill = pos == 15;
        observe::phase = prefill ? 3 : 4;
        auto batch = prefill ? llama_batch_get_one(ids.data(), 16, 0, 0)
                             : llama_batch_get_one(&ids[16], 1, 16, 0);
        must(llama_decode(ctx, batch) == 0, "supplied decode");
        llama_synchronize(ctx);
        const int cells = llama_get_kv_cache_used_cells(ctx);
        std::printf("KV %d %d\n", pos, cells);
        must(cells == pos + 1, "used KV cells");
        int rc = save_cut(ctx, dir, pos, prefill ? 3659 : 3992);
        if (rc) return rc;
        if (prefill) maps_at(dir, "prefill.maps"); else maps_at(dir, "teacher.maps");
        handoff(false, prefill ? 'P' : 'T');
    }
    return 0;
}
