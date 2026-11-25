#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-moe-prefetch.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

namespace fs = std::filesystem;
constexpr int width = 128, hidden = 256, experts = 128;
constexpr int picks[2][4] = {{0, 1, 63, 127}, {2, 3, 61, 125}};
constexpr const char *roles[] = {"gate", "up", "down"};
static void require(bool ok, const char *msg) { if (!ok) throw std::runtime_error(msg); }
static std::string name(int l, int op) {
    return "blk." + std::to_string(l) + ".ffn_" + roles[op] + "_exps.weight";
}
static int code_for(int expert, int layer) {
    for (int r = 0; r < 4; ++r) if (picks[layer][r] == expert) return 1 + r;
    return 1 + expert % 4;
}
static void make_file(const fs::path &path) {
    require(!fs::exists(path), "fixture already exists");
    auto *ctx = ggml_init({16 * 1024 * 1024, nullptr, false});
    auto *file = gguf_init_empty();
    require(ctx && file, "writer allocation");
    for (int l = 0; l < 2; ++l) for (int role = 0; role < 3; ++role) {
        int nx = role == 2 ? hidden : width, ny = role == 2 ? width : hidden;
        auto *w = ggml_new_tensor_3d(ctx, GGML_TYPE_MXFP4, nx, ny, experts);
        ggml_set_name(w, name(l, role).c_str());
        for (int e = 0; e < experts; ++e) for (int y = 0; y < ny; ++y) {
            auto *row = static_cast<uint8_t *>(w->data) + e*w->nb[2] + y*w->nb[1];
            std::memset(row, 0, w->nb[1]);
            for (int t = 0; t < nx/32; ++t) row[17*t] = 127;
            const int k = y % nx, lane = k % 32;
            row[(k/32)*17 + 1 + lane%16] = code_for(e, l) << (lane >= 16 ? 4 : 0);
        }
        gguf_add_tensor(file, w);
    }
    gguf_write_to_file(file, path.c_str(), false);
    gguf_free(file);
    ggml_free(ctx);
}

struct event { char tag; int role; int64_t off; size_t len; long tid; };
static std::mutex event_mutex;
static std::vector<event> events;
static uintptr_t base;
static size_t extent;
static std::array<ggml_tensor *, 6> weights{};
static thread_local bool kernel_call;
static void api(char tag, const ggml_tensor *w) {
    auto it = std::find(weights.begin(), weights.end(), w);
    require(it != weights.end(), "unknown observer tensor");
    std::lock_guard<std::mutex> lock(event_mutex);
    events.push_back({tag, int(it-weights.begin()), 0, 0, 0});
}
template<class F> static F upstream(const char *symbol) {
    auto p = reinterpret_cast<F>(dlsym(RTLD_NEXT, symbol));
    require(p, "original symbol absent");
    return p;
}
extern "C" void ggml_moe_prefetch_tensor(const ggml_tensor *w) {
    static auto fn = upstream<decltype(&ggml_moe_prefetch_tensor)>("ggml_moe_prefetch_tensor");
    api('F', w);
    fn(w);
}
extern "C" void ggml_moe_prefetch_node(const ggml_tensor *node) {
    static auto fn = upstream<decltype(&ggml_moe_prefetch_node)>("ggml_moe_prefetch_node");
    api(kernel_call ? 'K' : 'S', node->src[0]);
    fn(node);
}
extern "C" void ggml_moe_prefetch_kernel_hook(const ggml_tensor *node, int ith) {
    static auto fn = upstream<decltype(&ggml_moe_prefetch_kernel_hook)>("ggml_moe_prefetch_kernel_hook");
    if (ith == 0) api('H', node->src[0]);
    kernel_call = true;
    fn(node, ith);
    kernel_call = false;
}
extern "C" int mincore(void *addr, size_t len, unsigned char *vec) noexcept {
    auto a = reinterpret_cast<uintptr_t>(addr);
    int ret = static_cast<int>(syscall(SYS_mincore, addr, len, vec));
    if (base && a >= base && a-base < extent) {
        std::lock_guard<std::mutex> lock(event_mutex);
        events.push_back({ret == 0 ? 'M' : '!', -1, static_cast<int64_t>(a-base), len, syscall(SYS_gettid)});
    }
    return ret;
}
static std::set<long> threads() {
    std::set<long> result;
    for (auto &e : fs::directory_iterator("/proc/self/task")) result.insert(std::stol(e.path().filename()));
    return result;
}
static void save(std::ofstream &raw, const void *p, size_t size) {
    raw.write(static_cast<const char *>(p), size);
    require(raw.good(), "output write");
}
static void run_case(const fs::path &dir, int layout, int pos, bool permuted, ggml_backend_t cpu,
                     const std::set<long> &workers) {
    int layers = layout == 0 ? 1 : 2;
    std::string key = std::to_string(layout) + "-" + std::to_string(pos) + (permuted ? "-perm" : "");
    auto *ctx = ggml_init({2 * 1024 * 1024, nullptr, true});
    auto *gf = ggml_new_graph_custom(ctx, 128, false);
    auto *sched = ggml_backend_sched_new(&cpu, nullptr, 1, 128, false);
    auto *input = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, width, 1, pos);
    ggml_set_input(input);
    auto *x = input;
    ggml_tensor *scores[2]{}, *top[2]{}, *down[2]{};
    std::vector<ggml_tensor *> actual_ops;
    for (int l = 0; l < layers; ++l) {
        scores[l] = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, experts, pos);
        ggml_set_input(scores[l]);
        top[l] = ggml_top_k(ctx, scores[l], 4);
        if (l == 1 && layout == 2) top[l]->src[0]->op_params[GGML_MAX_OP_PARAMS/sizeof(int32_t)-1] = 0xff;
        ggml_set_output(top[l]->src[0]);
        ggml_build_forward_expand(gf, top[l]);
        auto *gate = ggml_mul_mat_id(ctx, weights[3*l], x, top[l]);
        auto *up = ggml_mul_mat_id(ctx, weights[3*l+1], x, top[l]);
        auto *product = ggml_mul(ctx, gate, up);
        down[l] = ggml_mul_mat_id(ctx, weights[3*l+2], product, top[l]);
        actual_ops.insert(actual_ops.end(), {top[l]->src[0], gate, up, down[l]});
        ggml_set_output(down[l]);
        ggml_build_forward_expand(gf, down[l]);
        if (l+1 < layers) x = ggml_cont(ctx, ggml_view_3d(ctx, down[l], width, 1, pos,
                                             down[l]->nb[1], down[l]->nb[2], 0));
    }
    require(ggml_backend_sched_alloc_graph(sched, gf), "scheduler allocation");
    int splits = ggml_backend_sched_get_n_splits(sched);
    for (auto *t : actual_ops) require(ggml_backend_sched_get_tensor_backend(sched, t) == cpu, "backend");
    std::vector<float> input_data(width*pos);
    for (int t = 0; t < pos; ++t) for (int k = 0; k < width; ++k)
        input_data[t*width+k] = 1.0f + float((t+k)%7)*0.125f;
    ggml_backend_tensor_set(input, input_data.data(), 0, ggml_nbytes(input));
    for (int l = 0; l < layers; ++l) {
        std::vector<float> vals(experts*pos);
        for (int t = 0; t < pos; ++t) {
            for (int e = 0; e < experts; ++e) vals[t*experts+e] = -float(e+1);
            for (int r = 0; r < 4; ++r) vals[t*experts+picks[l][r]] = 10 - (permuted ? r^1 : r);
        }
        ggml_backend_tensor_set(scores[l], vals.data(), 0, ggml_nbytes(scores[l]));
    }
    { std::lock_guard<std::mutex> lock(event_mutex); events.clear(); }
    require(ggml_backend_sched_graph_compute(sched, gf) == GGML_STATUS_SUCCESS, "compute failed");
    ggml_backend_sched_synchronize(sched);
    for (int j = 0; j < 3*layers; ++j) ggml_moe_prefetch_wait(weights[j]);
    std::ofstream f(dir/(key+".bin"), std::ios::binary);
    for (int l = 0; l < layers; ++l) {
        for (int t = 0; t < pos; ++t) {
            int32_t ids[4];
            ggml_backend_tensor_get(top[l], ids, t*top[l]->nb[1], sizeof(ids));
            for (int r = 0; r < 4; ++r) require(ids[r] == picks[l][permuted ? r^1 : r], "top-k");
            save(f, ids, sizeof(ids));
        }
        std::vector<float> output(width*4*pos);
        ggml_backend_tensor_get(down[l], output.data(), 0, ggml_nbytes(down[l]));
        require(std::all_of(output.begin(), output.end(), [](float v){ return std::isfinite(v); }), "non-finite");
        save(f, output.data(), output.size()*sizeof(float));
    }
    std::cout << "case " << key << " " << splits << "\n";
    {
        std::lock_guard<std::mutex> lock(event_mutex);
        for (const auto &e : events) {
            if (e.tag == 'M') require(workers.count(e.tid), "mincore outside pool");
            std::cout << e.tag << " " << e.role << " " << e.off << " " << e.len << "\n";
        }
    }
    ggml_backend_sched_free(sched);
    ggml_free(ctx);
}
static void run(const fs::path &file, const fs::path &dir, bool enabled) {
    int fd = open(file.c_str(), O_RDONLY|O_CLOEXEC);
    struct stat st{};
    require(fd >= 0 && fstat(fd, &st) == 0 && S_ISREG(st.st_mode), "synthetic FD");
    auto *mapped = mmap(nullptr, st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    require(mapped != MAP_FAILED, "read-only mmap");
    extent = st.st_size;
    base = reinterpret_cast<uintptr_t>(mapped);
    ggml_context *meta = nullptr;
    auto *gguf = gguf_init_from_file(file.c_str(), {true, &meta});
    require(gguf && gguf_get_version(gguf) == 3 && gguf_get_alignment(gguf) == 32 &&
            gguf_get_n_tensors(gguf) == 6 && sysconf(_SC_PAGESIZE)==4096, "GGUF header");
    struct stat st2{};
    require(stat(file.c_str(), &st2)==0 && st2.st_dev==st.st_dev && st2.st_ino==st.st_ino &&
            st2.st_size==st.st_size, "mapping identity");
    auto *buf = ggml_backend_cpu_buffer_from_ptr(mapped, extent);
    ggml_backend_buffer_set_usage(buf, GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
    for (int j = 0; j < 6; ++j) {
        auto n = name(j/3, j%3);
        auto *w = ggml_get_tensor(meta, n.c_str());
        int id = gguf_find_tensor(gguf, n.c_str());
        require(w && id==j && w->type==GGML_TYPE_MXFP4 && w->ne[2]==experts && w->nb[2]==17408 &&
                w->ne[0]==(j%3==2?hidden:width) && w->ne[1]==(j%3==2?width:hidden), "weight geometry");
        size_t off = gguf_get_data_offset(gguf)+gguf_get_tensor_offset(gguf, id);
        require(off+ggml_nbytes(w)<=extent, "weight extent");
        ggml_backend_tensor_alloc(buf, w, reinterpret_cast<void *>(base+off));
        weights[j] = w;
        std::cout << "weight " << j << " " << off << " " << w->nb[2] << "\n";
    }
    auto *cpu = ggml_backend_cpu_init();
    ggml_backend_cpu_set_n_threads(cpu, 1);
    auto before = threads();
    if (enabled) require(ggml_backend_prefetch_init(4), "worker support");
    ggml_backend_cpu_set_moe_expert_prefetch(cpu, enabled);
    ggml_backend_prefetch_register_mapping(mapped, extent);
    auto after = threads();
    std::set<long> workers;
    for (auto t : after) if (!before.count(t)) workers.insert(t);
    require(workers.size()==(enabled ? 4u : 0u), "pool size");
    for (int layout : {0,1,2}) for (int pos : {1,5,20,32}) run_case(dir, layout, pos, false, cpu, workers);
    run_case(dir, 0, 5, true, cpu, workers);
    ggml_moe_prefetch_set_n_threads(0);
    for (auto t : workers) {
        for (int i = 0; i < 250 && threads().count(t); ++i) usleep(1000);
        require(!threads().count(t), "thread survived join");
    }
    ggml_backend_prefetch_unregister_mapping(mapped);
    std::cout << "workers " << workers.size() << "\n";
    ggml_backend_free(cpu);
    ggml_backend_buffer_free(buf);
    gguf_free(gguf);
    ggml_free(meta);
    base = 0;
    require(munmap(mapped, extent)==0 && close(fd)==0, "mapping cleanup");
}
int main(int argc, char **argv) {
    try {
        if (argc == 3 && std::string(argv[1])=="make") make_file(argv[2]);
        else {
            require(argc==4 && (std::string(argv[1])=="off" || std::string(argv[1])=="on"), "arguments");
            run(argv[2], argv[3], std::string(argv[1])=="on");
        }
        struct rusage usage{};
        require(getrusage(RUSAGE_SELF, &usage)==0 && usage.ru_maxrss<=256*1024, "child RSS cap");
        std::cout << "rss_kib " << usage.ru_maxrss << "\n";
        return 0;
    } catch (const std::exception &err) {
        std::cerr << err.what() << "\n";
        return 1;
    }
}
