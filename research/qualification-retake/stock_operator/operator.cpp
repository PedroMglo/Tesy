#include "ggml-cpp.h"
#include "ggml-cpu.h"
#include "ggml-cuda.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "sealed-planner.inc"

constexpr int E = 8, K = 256, M = 64, TOP = 4;
using IDs = std::vector<int32_t>;
using Bytes = std::vector<unsigned char>;
using Floats = std::vector<float>;

static void check(bool ok, const char *what) {
    if (!ok) throw std::runtime_error(what);
}

static ggml_context_ptr context() {
    return ggml_context_ptr(ggml_init({256 * 1024, nullptr, true}));
}

static ggml_tensor *bank(ggml_context *ctx) {
    return ggml_new_tensor_3d(ctx, GGML_TYPE_MXFP4, K, M, E);
}

static Bytes make_weights(int layer, size_t stride) {
    Bytes bytes(E * stride);
    Floats values(M * K);
    for (int e = 0; e < E; ++e) {
        for (int i = 0; i < M * K; ++i) {
            const int seed = (i % K) * (e + 1) + (i / K) * (layer + 3) + e * 13 + layer * 17;
            values[i] = float(seed % 61 - 30) / 16.0f;
        }
        check(ggml_quantize_chunk(GGML_TYPE_MXFP4, values.data(), bytes.data() + e * stride,
                                  0, M, K, nullptr) == stride, "quantized expert stride");
    }
    return bytes;
}

static IDs ids_for(int call, int layer) {
    IDs ids;
    for (int t = 0; t < (call == 0 ? 16 : 1); ++t) {
        for (int j = 0; j < TOP; ++j) {
            if (layer == 1) ids.push_back(2 * ((j + t) % TOP));
            else ids.push_back((j + t + (call == 2 ? 4 : 0)) % E);
        }
    }
    return ids;
}

static void check_weights(ggml_tensor *w, const Bytes &source, int e, int slot) {
    Bytes data(w->nb[2]);
    ggml_backend_tensor_get(w, data.data(), slot * data.size(), data.size());
    check(std::memcmp(data.data(), source.data() + e * data.size(), data.size()) == 0,
          "selected payload differs");
}

static void check_device_reserve(ggml_backend_t backend) {
    auto device = ggml_backend_get_device(backend);
    if (ggml_backend_dev_type(device) == GGML_BACKEND_DEVICE_TYPE_GPU) {
        size_t free_bytes = 0, total_bytes = 0;
        ggml_backend_dev_memory(device, &free_bytes, &total_bytes);
        check(free_bytes >= 512ULL * 1024 * 1024, "GPU reserve");
    }
}

static Floats project(ggml_backend_t backend, ggml_tensor *w, const IDs &ids,
                      const Floats &activation, const IDs *slot_map) {
    const int tokens = static_cast<int>(ids.size()) / TOP;
    auto ctx = context();
    auto *selection = ggml_new_tensor_2d(ctx.get(), GGML_TYPE_I32, TOP, tokens);
    auto *input = ggml_new_tensor_3d(ctx.get(), GGML_TYPE_F32, K, 1, tokens);
    auto *g = ggml_new_graph_custom(ctx.get(), 32, false);
    ggml_tensor *index = selection;
    ggml_tensor *map = nullptr;
    if (slot_map != nullptr) {
        map = ggml_new_tensor_2d(ctx.get(), GGML_TYPE_I32, 1, E);
        auto *flat = ggml_reshape_1d(ctx.get(), selection, ids.size());
        auto *found = ggml_get_rows(ctx.get(), map, flat);
        check(ggml_backend_supports_op(backend, found), "backend lacks I32 GET_ROWS");
        ggml_build_forward_expand(g, found);
        index = ggml_reshape_2d(ctx.get(), found, TOP, tokens);
    }
    auto *out = ggml_mul_mat_id(ctx.get(), w, input, index);
    check(ggml_backend_supports_op(backend, out), "backend lacks MXFP4 MUL_MAT_ID");
    ggml_build_forward_expand(g, out);
    ggml_backend_buffer_ptr buf(ggml_backend_alloc_ctx_tensors(ctx.get(), backend));
    check(buf != nullptr, "graph tensor allocation");
    ggml_backend_tensor_set(selection, ids.data(), 0, ggml_nbytes(selection));
    ggml_backend_tensor_set(input, activation.data(), 0, ggml_nbytes(input));
    if (map) ggml_backend_tensor_set(map, slot_map->data(), 0, ggml_nbytes(map));
    check(ggml_backend_graph_compute(backend, g) == GGML_STATUS_SUCCESS, "graph execution");
    ggml_backend_synchronize(backend);
    check_device_reserve(backend);
    IDs actual(ids.size());
    ggml_backend_tensor_get(index, actual.data(), 0, ggml_nbytes(index));
    for (size_t i = 0; i < ids.size(); ++i) {
        check(actual[i] == (slot_map ? slot_map->at(ids[i]) : ids[i]), "expert ID lookup");
    }
    Floats values(ggml_nelements(out));
    ggml_backend_tensor_get(out, values.data(), 0, ggml_nbytes(out));
    for (float v : values) check(std::isfinite(v), "non-finite projection");
    return values;
}

static void save(FILE *f, const Floats &v) {
    check(std::fwrite(v.data(), sizeof(float), v.size(), f) == v.size(), "write vectors");
}

static void run(ggml_backend_t backend, FILE *file) {
    auto ctx = context();
    std::array<ggml_tensor *, 2> canonical = {bank(ctx.get()), bank(ctx.get())};
    auto *reuse = bank(ctx.get());
    auto *recopy = bank(ctx.get());
    ggml_backend_buffer_ptr buf(ggml_backend_alloc_ctx_tensors(ctx.get(), backend));
    check(buf != nullptr, "weights allocation");
    ggml_backend_buffer_clear(buf.get(), 0);
    const size_t stride = reuse->nb[2];
    std::array<Bytes, 2> data = {make_weights(0, stride), make_weights(1, stride)};
    for (int layer = 0; layer < 2; ++layer) {
        ggml_backend_tensor_set(canonical[layer], data[layer].data(), 0, data[layer].size());
    }
    std::array<IDs, 2> maps = {IDs(E, E), IDs(E, E)};
    moe_cache_lru planner;
    planner.init(2, E, E);
    for (int layer = 0; layer < 2; ++layer) planner.slot_map[layer] = maps[layer].data();
    std::set<int> seen;
    size_t total_hits = 0, total_evicted = 0, total_reloaded = 0;
    for (int call = 0; call < 3; ++call) {
        for (int layer = 0; layer < 2; ++layer) {
            const IDs ids = ids_for(call, layer);
            const int tokens = static_cast<int>(ids.size()) / TOP;
            const std::set<int> selected(ids.begin(), ids.end());
            const IDs previous = planner.key_of;
            std::vector<moe_cache_lru::fill> fills, cpu;
            size_t hits = 0, evictions = 0, reloads = 0;
            check(planner.plan(layer, ids.data(), ids.size(), tokens, TOP, 0,
                               [](size_t) { return size_t(0); }, fills, cpu, hits), "plan");
            check(cpu.empty() && hits + fills.size() == selected.size(), "plan conservation");
            for (const auto &f : fills) {
                check(f.slot == maps[layer].at(f.expert), "fill publication");
                ggml_backend_tensor_set_async(backend, reuse, data[layer].data() + f.expert * stride,
                                              f.slot * stride, stride);
                evictions += previous.at(f.slot) >= 0;
                reloads += !seen.insert(layer * E + f.expert).second;
            }
            for (int e : selected) {
                ggml_backend_tensor_set_async(backend, recopy, data[layer].data() + e * stride,
                                              maps[layer].at(e) * stride, stride);
            }
            ggml_backend_synchronize(backend);
            for (int e : selected) {
                const int slot = maps[layer].at(e);
                check(slot >= 0 && slot < E && planner.key_of.at(slot) == layer * E + e, "map");
                check_weights(reuse, data[layer], e, slot);
                check_weights(recopy, data[layer], e, slot);
                check_weights(canonical[layer], data[layer], e, e);
            }
            Floats x(K * tokens);
            for (size_t i = 0; i < x.size(); ++i) {
                x[i] = float(int((i * 17 + call * 7 + layer) % 43) - 21) / 32.0f;
            }
            const auto ref = project(backend, canonical[layer], ids, x, nullptr);
            const auto control = project(backend, recopy, ids, x, &maps[layer]);
            const auto cached = project(backend, reuse, ids, x, &maps[layer]);
            for (const auto *v : {&ref, &control, &cached}) save(file, *v);
            check(std::memcmp(ref.data(), control.data(), ref.size() * sizeof(float)) == 0,
                  "canonical vs recopy projection differs");
            check(std::memcmp(control.data(), cached.data(), ref.size() * sizeof(float)) == 0,
                  "recopy vs reuse projection differs");
            if (call == 2 && layer == 1) {
                IDs fault = ids;
                std::swap(fault[0], fault[1]);
                const auto wrong = project(backend, canonical[layer], fault, x, nullptr);
                save(file, wrong);
                check(std::memcmp(ref.data(), wrong.data(), ref.size() * sizeof(float)) != 0,
                      "wrong-ID control undetected");
            }
            std::printf("PLAN %d %d %d %zu %zu %zu %zu %zu %zu %zu\n", call, layer, tokens,
                        selected.size(), hits, fills.size(), evictions, reloads, stride, ref.size());
            total_hits += hits;
            total_evicted += evictions;
            total_reloaded += reloads;
        }
    }
    check(total_hits && total_evicted && total_reloaded, "missing hit/eviction/reload");
}

int main(int argc, char **argv) {
    try {
        check(argc == 3, "usage: operator CPU|CUDA new-vectors");
        const std::string dev(argv[1]);
        check(dev == "CPU" || dev == "CUDA", "invalid device");
        ggml_backend_ptr backend(dev == "CPU" ? ggml_backend_cpu_init() : ggml_backend_cuda_init(0));
        check(backend != nullptr, "backend init");
        if (dev == "CPU") ggml_backend_cpu_set_n_threads(backend.get(), 1);
        std::printf("DEVICE %s\n", ggml_backend_name(backend.get()));
        FILE *out = std::fopen(argv[2], "wbx");
        check(out != nullptr, "exclusive new vectors");
        try { run(backend.get(), out); } catch (...) { std::fclose(out); throw; }
        check(std::fclose(out) == 0, "flush vectors");
        return 0;
    } catch (const std::exception &e) {
        std::fprintf(stderr, "FAIL %s\n", e.what());
        return 1;
    }
}
