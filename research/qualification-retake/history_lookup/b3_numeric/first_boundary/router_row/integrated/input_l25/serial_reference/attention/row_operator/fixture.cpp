#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cuda.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace fs = std::filesystem;
constexpr int dim = 64, heads = 64, kv_heads = 8, cells = 256, capacity = 8192;
constexpr int kv_words = dim * kv_heads, q_words = dim * heads;
static size_t admission_free = 0;

static void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

static void check_memory() {
    size_t free = 0, total = 0;
    ggml_backend_cuda_get_device_memory(0, &free, &total);
    require(free > 0 && total >= free && free + (size_t{1}<<30) >= admission_free, "VRAM budget");
    std::printf("device_memory %zu %zu\n",free,total);
}

template <typename T>
static std::vector<T> read_words(const fs::path &path, size_t count) {
    require(fs::file_size(path) == count * sizeof(T), "input size " + path.string());
    std::vector<T> data(count);
    std::ifstream input(path, std::ios::binary);
    require(bool(input.read(reinterpret_cast<char *>(data.data()), count * sizeof(T))), "input read");
    return data;
}

static void write_bytes(const fs::path &path, const void *bytes, size_t count) {
    FILE *f = std::fopen(path.c_str(), "wbx");
    require(f != nullptr, "exclusive output " + path.string());
    const bool ok = std::fwrite(bytes, 1, count, f) == count;
    require(std::fclose(f) == 0 && ok, "write");
}

struct Inputs {
    std::vector<float> q, sinks;
    std::vector<uint16_t> k, v, mask;
    explicit Inputs(const fs::path &p)
        : q(read_words<float>(p/"q.f32", 3*q_words)),
          sinks(read_words<float>(p/"sinks.f32", heads)),
          k(read_words<uint16_t>(p/"k.f16", 192*kv_words)),
          v(read_words<uint16_t>(p/"v.f16", 192*kv_words)),
          mask(read_words<uint16_t>(p/"mask.f16", 3*cells)) {}
};

struct Graph {
    ggml_context *ctx;
    ggml_backend_buffer_t buf = nullptr;
    Graph() : ctx(ggml_init({2 << 20, nullptr, true})) { require(ctx, "context"); }
    ~Graph() {
        if (buf) ggml_backend_buffer_free(buf);
        ggml_free(ctx);
    }
    ggml_tensor *cache(ggml_tensor *base) const {
        auto *view = ggml_view_4d(ctx, base, dim, kv_heads, cells, 1,
                                  dim*2, kv_words*2, capacity*kv_words*2, 0);
        return ggml_permute(ctx, view, 0, 2, 1, 3);
    }
};

static std::vector<float> compute(ggml_backend_t cuda, const Inputs &data, int row, int width,
                                  bool sliced, bool alt_tail, bool masked) {
    Graph g;
    auto *q = ggml_new_tensor_3d(g.ctx, GGML_TYPE_F32, dim, heads, width);
    auto *m = ggml_new_tensor_2d(g.ctx, GGML_TYPE_F16, cells, width);
    auto *sink = ggml_new_tensor_1d(g.ctx, GGML_TYPE_F32, heads);
    auto *kb = ggml_new_tensor_2d(g.ctx, GGML_TYPE_F16, kv_words, capacity);
    auto *vb = ggml_new_tensor_2d(g.ctx, GGML_TYPE_F16, kv_words, capacity);
    auto *k = g.cache(kb), *v = g.cache(vb);
    auto attention = [&](ggml_tensor *query, ggml_tensor *mask) {
        auto *perm = ggml_permute(g.ctx, query, 0, 2, 1, 3);
        auto *out = ggml_flash_attn_ext(g.ctx, perm, k, v, mask, 0.125f, 0.0f, 0.0f);
        ggml_flash_attn_ext_add_sinks(out, sink);
        ggml_flash_attn_ext_set_prec(out, GGML_PREC_F32);
        require(ggml_backend_supports_op(cuda, out), "unsupported attention");
        return out;
    };
    ggml_tensor *value = nullptr;
    if (sliced) {
        require(width == 3 && row == 0, "three block views");
        for (int i = 0; i < width; ++i) {
            auto *qi = ggml_view_3d(g.ctx, q, dim, heads, 1, q->nb[1], q->nb[2], i*q->nb[2]);
            auto *mi = ggml_view_2d(g.ctx, m, cells, 1, m->nb[1], i*m->nb[1]);
            auto *out = attention(qi, mi);
            value = value ? ggml_concat(g.ctx, value, out, 2) : out;
        }
    } else {
        value = attention(q, m);
    }
    auto *graph = ggml_new_graph_custom(g.ctx, 64, false);
    ggml_build_forward_expand(graph, value);
    g.buf = ggml_backend_alloc_ctx_tensors(g.ctx, cuda);
    require(g.buf && ggml_nbytes(value) == width*q_words*sizeof(float), "device output shape");
    check_memory();
    auto set = [](ggml_tensor *t, const void *ptr, size_t bytes) {
        ggml_backend_tensor_set(t, ptr, 0, bytes);
    };
    set(q, data.q.data()+row*q_words, width*q_words*sizeof(float));
    set(sink, data.sinks.data(), heads*sizeof(float));
    std::vector<uint16_t> mask(data.mask.begin()+row*cells, data.mask.begin()+(row+width)*cells);
    if (masked) std::fill(mask.begin(),mask.end(),uint16_t{0xfc00});
    set(m, mask.data(), mask.size()*2);
    const int populated = width == 1 ? 190 + row : 192;
    auto fill_cache = [&](ggml_tensor *t, const std::vector<uint16_t> &values, uint16_t pad) {
        std::vector<uint16_t> active(cells*kv_words, alt_tail ? pad : 0);
        std::copy_n(values.begin(), populated*kv_words, active.begin());
        set(t, active.data(), active.size()*2);
    };
    fill_cache(kb, data.k, 0x3400);
    fill_cache(vb, data.v, 0xb800);
    require(ggml_backend_graph_compute(cuda, graph) == GGML_STATUS_SUCCESS, "graph compute");
    ggml_backend_synchronize(cuda);
    check_memory();
    std::vector<float> result(width*q_words);
    ggml_backend_tensor_get(value, result.data(), 0, result.size()*sizeof(float));
    return result;
}

static void checkpoint(const fs::path &dir, const std::string &name) {
    write_bytes(dir/(name+".ready"), name.data(), name.size());
    for (int i=0; i<500 && !fs::exists(dir/(name+".ack")); ++i)
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    require(fs::exists(dir/(name+".ack")), "telemetry handshake " + name);
}

int main(int argc, char **argv) try {
    require(argc == 3, "fixture INPUTS NEW-OUTPUT");
    const Inputs data(argv[1]);
    const fs::path out(argv[2]);
    require(fs::create_directory(out), "exclusive device result");
    require(ggml_backend_cuda_get_device_count() == 1, "one device");
    size_t total = 0;
    ggml_backend_cuda_get_device_memory(0, &admission_free, &total);
    char name[256]{};
    ggml_backend_cuda_get_device_description(0, name, sizeof(name));
    require(std::string(name).find("RTX 4060 Laptop GPU") != std::string::npos, "target SKU");
    auto cuda = ggml_backend_cuda_init(0);
    require(cuda && ggml_backend_is_cuda(cuda), "CUDA backend");
    checkpoint(out,"before");
    std::vector<float> serial;
    for (int row=0; row<3; ++row) {
        auto part=compute(cuda, data, row, 1, false, false, false);
        serial.insert(serial.end(),part.begin(),part.end());
    }
    write_bytes(out/"A.f32", serial.data(), serial.size()*sizeof(float));
    for (const std::string tag : {"B","S","B-alt","S-alt","mutant"}) {
        const bool split = tag[0]=='S';
        auto result=compute(cuda,data,0,3,split,tag.find("-alt")!=std::string::npos,tag=="mutant");
        write_bytes(out/(tag+".f32"),result.data(),result.size()*sizeof(float));
    }
    checkpoint(out,"after");
    ggml_backend_free(cuda);
    return 0;
} catch (const std::exception &e) {
    std::fprintf(stderr,"%s\n",e.what());
    return 1;
}
