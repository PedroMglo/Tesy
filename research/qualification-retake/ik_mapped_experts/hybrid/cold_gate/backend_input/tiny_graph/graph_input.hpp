#pragma once

#include "../bank_input.hpp"
#include <memory>

namespace graph_input {

using Fence = decltype(&ggml_backend_synchronize);
inline Fence original_fence() {
    static auto real = next_fn<Fence>("ggml_backend_synchronize");
    return real;
}

// A single-context diagnostic. Only libllama's ID read and its following
// barrier release this site's host ranges. Other synchronizations pass through.
inline uintptr_t llama_site(void *pc) {
    Dl_info info{};
    if (!dladdr(pc, &info) || fs::path(info.dli_fname).filename() != "libllama.so") return 0;
    return uintptr_t(pc) - uintptr_t(info.dli_fbase);
}

struct Matrix {
    std::string suffix;
    uintptr_t address;
    size_t bytes, stride;
    int64_t offset;
    int layer;
};

class Session;
inline thread_local Session *active = nullptr;

struct Layout {
    unsigned layers = 2;
    size_t capacity = 1u << 20;
    unsigned prefill_width = 32;
    bool output_only_last_layer = false;
    bool compare_host_bytes = true;

    size_t selected_bytes(int phase, unsigned layer) const {
        const bool full = phase == 3 && !(output_only_last_layer && layer + 1 == layers);
        return (full ? prefill_width : 1) * 4 * sizeof(int32_t);
    }
};

class Session {
    std::vector<Matrix> matrices;
    ggml_backend_t backend{};
    std::unique_ptr<tesy::BankInput> input;
    tesy::Source source;
    const Layout layout;
    int fd = -1;
    unsigned generation = 0, fills = 0;
    const int32_t *ids = nullptr;
    size_t id_count = 0;

public:
    explicit Session(const char *path, const std::string &mode, Layout geometry = {})
        : source(mode == "DIRECT" ? tesy::Source::mapped : tesy::Source::ranges), layout(geometry) {
        must(!active && layout.layers > 0 && (mode == "DIRECT" || mode == "PREAD_RANDOM"),
             "single bank context/mode");
        fd = open(path, O_RDONLY | O_CLOEXEC);
        struct stat s{};
        if (fd < 0 || fstat(fd, &s) || s.st_dev != file_id.st_dev || s.st_ino != file_id.st_ino ||
            s.st_size != file_id.st_size) {
            if (fd >= 0) close(fd);
            throw std::runtime_error("original model descriptor");
        }
        active = this;
    }
    Session(const Session &) = delete;
    ~Session() {
        input.reset(); // drain before losing the context on an incomplete submission
        active = nullptr;
        close(fd);
    }

    void add(int layer, const char *role, const char *kind, const ggml_tensor *w) {
        if (std::strcmp(kind, "weight") != 0) return;
        must(w && w->data && w->buffer, "missing original weight");
        auto off = observe::file_offset(w->data, ggml_nbytes(w));
        must(off >= 0 && w->nb[2] && w->type == GGML_TYPE_MXFP4, "original mapped matrix");
        matrices.push_back({std::string(".ffn_") + role + "_exps.weight", uintptr_t(w->data),
                            ggml_nbytes(w), w->nb[2], off, layer});
    }
    void got_ids(ggml_backend_t b, const ggml_tensor *t, void *buf, size_t off, size_t n,
                 uintptr_t caller) {
        if (!caller || t->type != GGML_TYPE_I32) return;
        must(!ids && off == 0 && n == ggml_nbytes(t) &&
             n == layout.selected_bytes(observe::phase, generation % layout.layers),
             "unexpected libllama rank read");
        if (!backend) {
            must(std::string(ggml_backend_name(b)) == "CUDA0", "ID backend");
            backend = b;
            input = std::make_unique<tesy::BankInput>(fd, layout.capacity, source,
                                                      [this]() { original_fence()(backend); });
        }
        must(backend == b, "changed ID backend");
        ids = static_cast<int32_t *>(buf);
        id_count = n / sizeof(*ids);
        std::printf("BANK_GET %d %u %zu %zu %zu\n", observe::phase, generation+1,
                    uintptr_t(b), caller, n);
    }
    bool fence(ggml_backend_t b, uintptr_t caller) {
        if (!caller || !ids || b != backend) return false;
        input->synchronize_ids();
        std::printf("BANK_FENCE %d %u %zu %zu %u ", observe::phase, ++generation,
                    uintptr_t(b), caller, fills);
        for (size_t i = 0; i < id_count; ++i) std::printf(i ? ",%d" : "%d", ids[i]);
        std::putchar('\n');
        ids = nullptr;
        fills = 0;
        return true;
    }
    template<class Submit>
    bool send(ggml_backend_t b, ggml_tensor *t, const void *src, size_t off, size_t n, Submit real) {
        const std::string name(t->name);
        if (name.rfind("moe_cache.", 0) != 0 || name.find("_exps.weight") == name.npos) return false;
        must(backend && backend == b && !ids && generation && matrices.size() == 3 * layout.layers,
             "bank context");
        auto ptr = uintptr_t(src);
        const Matrix *selected = nullptr;
        for (const auto &m : matrices) {
            if (ptr < m.address || ptr - m.address >= m.bytes || n > m.bytes - (ptr-m.address)) continue;
            must(!selected && name.size() >= m.suffix.size() &&
                 name.compare(name.size()-m.suffix.size(), m.suffix.size(), m.suffix) == 0,
                 "ambiguous or different role");
            selected = &m;
        }
        must(selected && n && !(n % selected->stride) && !(off % selected->stride) &&
             !((ptr-selected->address) % selected->stride) &&
             off <= ggml_nbytes(t) && n <= ggml_nbytes(t)-off, "bank source/destination geometry");
        auto file = observe::file_offset(src,n);
        must(file >= 0 && uint64_t(file-selected->offset) == ptr-selected->address, "GGUF interval");
        input->send(file, src, n, [&](const void *effective, size_t bytes) {
            must(bytes == n && (!layout.compare_host_bytes || std::memcmp(src, effective, bytes) == 0),
                 "source bytes differ");
            std::printf("BANK_SOURCE %d %lu %u %zu %d %zu %lld %zu %lld %zu\n",
                        observe::phase, observe::owner, generation, uintptr_t(b), selected->layer,
                        ptr, (long long)file, uintptr_t(effective),
                        (long long)observe::file_offset(effective,n), n);
            real(b,t,effective,off,n);
        });
        ++fills;
        return true;
    }
    void finish() {
        must(input && generation == 2 * layout.layers && !ids, "incomplete bank graph");
        input.reset();
        std::printf("BANK_END %u %u\n", generation, fills);
        active = nullptr;
    }
};
} // namespace graph_input

extern "C" void ggml_backend_tensor_get_async(ggml_backend_t b, const ggml_tensor *t,
                                               void *buf, size_t off, size_t n) {
    static auto real = next_fn<decltype(&ggml_backend_tensor_get_async)>("ggml_backend_tensor_get_async");
    real(b,t,buf,off,n);
    if (graph_input::active && (observe::phase == 3 || observe::phase == 4))
        graph_input::active->got_ids(b,t,buf,off,n,graph_input::llama_site(__builtin_return_address(0)));
}
extern "C" void ggml_backend_synchronize(ggml_backend_t b) {
    if (graph_input::active && graph_input::active->fence(b,graph_input::llama_site(__builtin_return_address(0)))) return;
    graph_input::original_fence()(b);
}
