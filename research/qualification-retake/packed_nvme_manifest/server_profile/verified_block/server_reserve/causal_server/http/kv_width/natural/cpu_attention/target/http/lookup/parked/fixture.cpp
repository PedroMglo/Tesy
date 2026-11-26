// Independent native GGML reference for a completely parked CPU down projection.
#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include <nlohmann/json.hpp>
#include <openssl/sha.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <vector>

using json = nlohmann::json;
namespace fs = std::filesystem;
constexpr int width = 2880, ranks = 4, tokens = 32, experts = 128;
constexpr int rows = ranks * tokens, values = width * rows;

static void require(bool ok, const char *reason) {
    if (!ok) throw std::runtime_error(reason);
}

template<class T>
static std::vector<T> read(const fs::path &p, size_t count) {
    require(fs::file_size(p) == count * sizeof(T), "input length");
    std::vector<T> data(count);
    std::ifstream f(p, std::ios::binary);
    require(bool(f.read(reinterpret_cast<char *>(data.data()), count * sizeof(T))), "input read");
    return data;
}

static std::string digest(const std::vector<float> &v) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    require(SHA256(reinterpret_cast<const unsigned char *>(v.data()), v.size()*sizeof(float), hash), "SHA-256");
    const char hex[] = "0123456789abcdef";
    std::string result;
    for (unsigned char c : hash) { result += hex[c >> 4]; result += hex[c & 15]; }
    return result;
}

template<class T>
static void put(ggml_tensor *t, const std::vector<T> &v) {
    require(ggml_nbytes(t) == v.size() * sizeof(T), "tensor shape");
    ggml_backend_tensor_set(t, v.data(), 0, ggml_nbytes(t));
}

static bool parked(const std::vector<int32_t> &physical, const std::vector<int32_t> &logical,
                   const std::vector<float> &mask) {
    for (int r = 0; r < rows; ++r) {
        if (physical[r] != -1 || logical[r] < 0 || logical[r] >= experts ||
            std::bit_cast<uint32_t>(mask[r]) != 0) return false;
    }
    return true;
}

static void finite(const std::vector<float> &v) {
    require(std::all_of(v.begin(), v.end(), [](float x){ return std::isfinite(x); }), "nonfinite input or output");
}

static float empty_add(float previous, float bias) {
    if (std::isnormal(previous)) return previous;
    volatile float zero = 0.0f;
    const float projected = zero + bias;
    return previous + projected * zero;
}

static json run(const fs::path &input) {
    require(std::fegetround() == FE_TONEAREST && sizeof(float) == 4, "host arithmetic");
    const auto raw = read<int32_t>(input / "ffn_moe_topk-0.bin", 153 * ranks);
    std::vector<int32_t> logical(raw.begin()+32*ranks, raw.begin()+64*ranks);
    std::vector<int32_t> physical(rows, -1);
    std::vector<float> mask(rows, 0.0f);
    const auto real = read<float>(input / "down.bias", width*experts);
    require(std::set<int32_t>(logical.begin(), logical.end()) == std::set<int32_t>({45,49,57,60,98}), "captured routes");
    require(parked(physical, logical, mask), "entire wave parked");
    auto bad_physical = physical;
    bad_physical.back() = 3;
    auto bad_logical = logical;
    bad_logical.back() = experts;
    auto bad_mask = mask;
    bad_mask.back() = -0.0f;
    require(!parked(bad_physical, logical, mask) && !parked(physical, bad_logical, mask)
            && !parked(physical, logical, bad_mask), "mixed or invalid wave");
    bool rejected = false;
    try { finite({std::numeric_limits<float>::quiet_NaN()}); }
    catch (const std::runtime_error &) { rejected = true; }
    require(rejected, "nonfinite control");

    const std::array<uint32_t, 12> bits = {0, 0x80000000, 0x3f800000, 0xbf800000, 0x7f7fffff,
        0xff7fffff, 0x00800000, 0x80800000, 1, 0x80000001, 0x007fffff, 0x807fffff};
    std::vector<float> previous(values), artificial(width*experts);
    for (int k = 0; k < values; ++k) previous[k] = std::bit_cast<float>(bits[k % bits.size()]);
    for (size_t k = 0; k < artificial.size(); ++k)
        artificial[k] = std::bit_cast<float>(bits[(k / bits.size() + 5*(k % bits.size())) % bits.size()]);

    ggml_context *ctx = ggml_init({16ULL << 20, nullptr, true});
    ggml_backend_t cpu = ggml_backend_cpu_init();
    require(ctx && cpu, "CPU backend");
    ggml_backend_cpu_set_n_threads(cpu, 8);
    auto *w = ggml_new_tensor_3d(ctx, GGML_TYPE_MXFP4, width, width, 40);
    auto *rhs = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, width, ranks, tokens);
    auto *slots = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, ranks, tokens);
    auto *ids = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, ranks, tokens);
    auto *bias = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, width, experts);
    auto *m = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 1, ranks, tokens);
    auto *acc = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, width, ranks, tokens);
    auto *down = ggml_mul_mat_id(ctx, w, rhs, slots);
    auto *biased = ggml_add_id(ctx, down, bias, ids);
    auto *masked = ggml_mul(ctx, biased, m);
    auto *out = ggml_add(ctx, acc, masked);
    auto *graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(graph, out);
    ggml_backend_buffer_t memory = ggml_backend_alloc_ctx_tensors(ctx, cpu);
    require(memory && ggml_graph_n_nodes(graph) == 4, "native reference graph");
    ggml_backend_buffer_clear(memory, 0);
    put(slots, physical); put(ids, logical); put(m, mask); put(acc, previous);
    json tests = json::object();
    for (bool synthetic : {false, true}) {
        const auto &b = synthetic ? artificial : real;
        finite(b); finite(previous);
        put(bias, b);
        require(ggml_backend_graph_compute(cpu, graph) == GGML_STATUS_SUCCESS, "native graph");
        ggml_backend_synchronize(cpu);
        std::vector<float> ref(values), prod(values), candidate(values);
        ggml_backend_tensor_get(down, prod.data(), 0, ggml_nbytes(down));
        require(std::all_of(prod.begin(), prod.end(), [](float x){ return std::bit_cast<uint32_t>(x)==0; }), "parked down output");
        ggml_backend_tensor_get(out, ref.data(), 0, ggml_nbytes(out));
        finite(ref);
        int mismatches = 0, changed = 0;
        for (int row = 0; row < rows; ++row) {
            for (int col = 0; col < width; ++col) {
                const int i = row*width+col;
                candidate[i] = empty_add(previous[i], b[logical[row]*width+col]);
                const uint32_t expected = std::bit_cast<uint32_t>(ref[i]);
                mismatches += std::bit_cast<uint32_t>(candidate[i]) != expected;
                changed += std::bit_cast<uint32_t>(previous[i]) != expected;
            }
        }
        finite(candidate);
        tests[synthetic ? "adversarial_bias" : "C266_bias"] = {
            {"values",values},{"parked_positive_zeros",values},{"copy_differences",changed},
            {"candidate_differences",mismatches},{"reference_sha256",digest(ref)},{"candidate_sha256",digest(candidate)}
        };
        if (mismatches) break;
    }
    ggml_backend_buffer_free(memory);
    ggml_backend_free(cpu);
    ggml_free(ctx);
    return tests;
}

int main(int argc, char **argv) {
    try {
        require(argc == 2, "usage: fixture INPUT_DIRECTORY");
        std::cout << run(argv[1]).dump() << '\n';
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
