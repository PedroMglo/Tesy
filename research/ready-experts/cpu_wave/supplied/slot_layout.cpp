// Test three physical expert projections with the original CPU scheduler and MXFP4 kernels.
#include "ggml-cpp.h"
#include "ggml-cpu.h"
#include "c291-direct-reader.h"
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <future>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

constexpr size_t width = 2880, slots = 40, ranks = 4, slab = 4406400;
constexpr size_t stride = (3 * slab + 4095) / 4096 * 4096;
constexpr std::array<int32_t, ranks> slot_ids = {0, 13, 27, 39};
using Bytes = unsigned char;
using Matrix = std::array<ggml_tensor *, 3>;
struct CloseFile { void operator()(FILE *stream) const { std::fclose(stream); } };

void check(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }

struct Mapping {
    size_t size;
    Bytes *data;
    explicit Mapping(size_t n) : size(n), data(static_cast<Bytes *>(
        mmap(nullptr, n, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0))) {
        check(data != MAP_FAILED, "anonymous aligned pool");
    }
    Mapping(const Mapping &) = delete;
    ~Mapping() { munmap(data, size); }
};

void pattern(Bytes *dst, int record) {
    for (size_t part = 0; part < 3; ++part) {
        unsigned state = 7919 * (record + 1) + 271 * (part + 1);
        for (size_t at = 0; at < slab; at += 17) {
            *dst++ = 123 + (state & 3);
            for (size_t j = 1; j < 17; ++j) {
                state = state * 1664525u + 1013904223u;
                *dst++ = state >> 24;
            }
        }
    }
    std::memset(dst, 0xa5, stride - 3 * slab);
}

void make_input(const char *path) {
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    check(fd >= 0, "exclusive fixture input");
    Mapping data(stride);
    for (int i = 0; i < 5; ++i) {
        pattern(data.data, i);
        check(write(fd, data.data, stride) == ssize_t(stride), "fixture write");
    }
    check(fsync(fd) == 0 && close(fd) == 0, "fixture flush");
}

void calculate(const Matrix &w, ggml_backend_t cpu, int n, bool mutant, FILE *output) {
    ggml_context_ptr ctx(ggml_init({4u << 20, nullptr, true}));
    check(bool(ctx), "graph metadata");
    auto *c = ctx.get();
    auto *g = ggml_new_graph_custom(c, 128, false);
    auto *x = ggml_new_tensor_3d(c, GGML_TYPE_F32, width, 1, n);
    auto *ids = ggml_new_tensor_2d(c, GGML_TYPE_I32, ranks, n);
    ggml_set_input(x);
    ggml_set_input(ids);
    Matrix projections;
    for (size_t k = 0; k < 3; ++k) {
        projections[k] = ggml_mul_mat_id(c, w[mutant ? (k + 1) % 3 : k], x, ids);
        ggml_set_output(projections[k]);
        ggml_build_forward_expand(g, projections[k]);
    }
    ggml_backend_sched_ptr sched(ggml_backend_sched_new(&cpu, nullptr, 1, 128, false, false));
    check(sched && ggml_backend_sched_alloc_graph(sched.get(), g), "CPU scheduler allocation");
    std::vector<float> values(width * n);
    std::vector<int32_t> routing(ranks * n);
    for (size_t i = 0; i < values.size(); ++i) values[i] = (int((53*i+i/width)%97) - 48)/32.0f;
    for (size_t i = 0; i < routing.size(); ++i) routing[i] = slot_ids[(i + i/ranks) % ranks];
    ggml_backend_tensor_set(x, values.data(), 0, sizeof(float) * values.size());
    ggml_backend_tensor_set(ids, routing.data(), 0, sizeof(int32_t) * routing.size());
    check(ggml_backend_sched_graph_compute(sched.get(), g) == GGML_STATUS_SUCCESS, "CPU graphs");
    ggml_backend_sched_synchronize(sched.get());
    values.resize(width * ranks * n);
    for (auto *p : projections) {
        ggml_backend_tensor_get(p, values.data(), 0, values.size() * sizeof(float));
        for (float v : values) check(std::isfinite(v), "non-finite operator output");
        check(fwrite(values.data(), sizeof(float), values.size(), output) == values.size(), "output");
    }
}

int run(const std::string &role, const char *input, const char *path) {
    const bool planar = role == "A", direct = role == "C" || role == "MUTANT";
    check(planar || role == "B" || direct, "unknown layout");
    tesy_witness::direct_reader source;
    source.open_file(input);
    int fd = source.descriptor();
    check((fcntl(fd, F_GETFL) & O_DIRECT) && source.file_size() == 5 * stride &&
          4096 % source.memory_alignment() == 0 && 4096 % source.offset_alignment() == 0,
          "direct NVMe alignment and extent");
    Mapping pool(stride * slots);
    ggml_context_ptr ctx(ggml_init({2u << 20, nullptr, true}));
    ggml_backend_ptr cpu(ggml_backend_cpu_init());
    ggml_backend_buffer_ptr buffer(ggml_backend_cpu_buffer_from_ptr(pool.data, pool.size));
    check(ctx && cpu && buffer, "CPU backend or native pool");
    ggml_backend_cpu_set_n_threads(cpu.get(), 8);
    ggml_backend_buffer_set_usage(buffer.get(), GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
    Matrix w;
    for (size_t k = 0; k < 3; ++k) {
        auto *t = ggml_new_tensor_3d(ctx.get(), GGML_TYPE_MXFP4, width, width, slots);
        check(t->nb[2] == slab, "independent MXFP4 geometry");
        t->nb[2] = planar ? slab : stride;
        t->nb[3] = slots * t->nb[2];
        auto *base = pool.data + k * slab * (planar ? slots : 1);
        check(ggml_backend_tensor_alloc(buffer.get(), t, base) == GGML_STATUS_SUCCESS, "CPU destination");
        w[k] = t;
    }
    auto serve = [&](int record, int slot) {
        // Direct mode gives the slot itself to pread. Controls pass a private staging allocation.
        std::unique_ptr<Mapping> staging;
        Bytes *dst = pool.data + slot * stride;
        if (!direct) { staging = std::make_unique<Mapping>(stride); dst = staging->data; }
        check(pread(fd, dst, stride, off_t(record) * stride) == ssize_t(stride), "short direct READ");
        Mapping expected(stride);
        pattern(expected.data, record);
        for (size_t k = 0; k < 3; ++k) {
            auto *t = w[k];
            if (!direct) ggml_backend_tensor_set(t, dst + k * slab, slot * t->nb[2], slab);
            auto *live = static_cast<Bytes *>(t->data) + slot * t->nb[2];
            check(!std::memcmp(live, expected.data + k*slab, slab), "published weight payload");
        }
    };
    std::array<std::future<void>,ranks> workers;
    for (size_t r=0; r<ranks; ++r)
        workers[r] = std::async(std::launch::async, serve, int(r), slot_ids[r]);
    for (auto &worker: workers) worker.get();
    std::unique_ptr<FILE,CloseFile> out(fopen(path,"wbx"));
    check(bool(out), "exclusive output");
    for (int generation=0; generation<2; ++generation) {
        if (generation) serve(4, slot_ids[1]);
        for (int n : {1,20,32}) calculate(w, cpu.get(), n, role == "MUTANT", out.get());
    }
    check(fflush(out.get()) == 0, "drain");
    printf("%s %zu %zu %zu %zu 5 %d\n", role.c_str(), slab, stride, source.memory_alignment(),
           source.offset_alignment(), direct ? 0 : 15);
    return 0;
}

int main(int argc, char **argv) {
    try {
        if (argc == 3 && std::string(argv[1]) == "make") { make_input(argv[2]); return 0; }
        check(argc == 4, "usage: role input output");
        return run(argv[1],argv[2],argv[3]);
    } catch (const std::exception &e) { fprintf(stderr,"%s\n",e.what()); return 1; }
}
