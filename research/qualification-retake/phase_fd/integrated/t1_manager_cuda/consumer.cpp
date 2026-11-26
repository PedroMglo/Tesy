// Same R0 ordering operand on a small CPU FFN. No CUDA backend is linked here.
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpp.h"
#include "ggml-cpu.h"
#include "ggml.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
constexpr int width = 32, ranks = 4, roles = 3;
constexpr int slab = width * 17;
using Bytes = std::array<uint8_t, slab>;
using Triplet = std::array<Bytes, roles>;

void need(bool value, const char *reason) {
    if (!value) throw std::runtime_error(reason);
}

enum class Arm { old_gold, new_gold, original, event, broken };

struct Schedule {
    Arm arm;
    std::mutex lock;
    std::condition_variable changed;
    bool captured = false, observed = false, graph_done = false, overwritten = false;
    bool reader_released = false;
    std::vector<std::string> sequence;
    float token = 0.0f;

    explicit Schedule(Arm arm) : arm(arm) {}
    bool gold() const { return arm == Arm::old_gold || arm == Arm::new_gold; }
    void mark(bool &flag, const char *name) {
        std::lock_guard guard(lock);
        flag = true;
        sequence.emplace_back(name);
        changed.notify_all();
    }
    void await(const bool &flag, const char *name) {
        std::unique_lock guard(lock);
        if (!changed.wait_for(guard, std::chrono::seconds(3), [&] { return flag; })) {
            std::cerr << "bounded handshake expired at " << name << std::endl;
            std::_Exit(3);  // callback can be running on a backend thread
        }
    }
};

Bytes payload(int generation, int role, int slot) {
    Bytes b{};
    // One MXFP4 block per row. Nibble 2 decodes to +1 before power-of-two scaling.
    for (int y = 0; y < width; ++y) {
        b[17*y] = 118 + generation + role + (slot ? 1 : 0);
        std::fill_n(b.begin() + 17*y + 1, 16, 0x22);
    }
    return b;
}

void allow_reader(ggml_tensor *dst, const ggml_tensor *src, int ith, int, void *ud) {
    if (ith) return;
    auto &s = *static_cast<Schedule *>(ud);
    if (!s.gold()) {
        s.await(s.arm == Arm::broken ? s.overwritten : s.captured, "consumer input");
    }
    s.mark(s.reader_released, "READER_RELEASED");
    std::memcpy(dst->data, src->data, ggml_nbytes(src));
}

void observe(ggml_tensor *dst, int ith, int, void *ud) {
    if (ith) return;
    auto &s = *static_cast<Schedule *>(ud);
    if (dst->src[1]) std::memcpy(&s.token, dst->src[1]->data, sizeof(float));
    std::memcpy(dst->data, dst->src[0]->data, ggml_nbytes(dst->src[0]));
    s.mark(s.observed, "OBSERVER");
}

void save(const fs::path &p, const void *data, size_t size) {
    std::ofstream f(p, std::ios::binary);
    need(bool(f.write(static_cast<const char *>(data), size)), "write witness");
}

void execute(Arm arm, const fs::path &dir) {
    Schedule s(arm);
    ggml_backend_ptr cpu(ggml_backend_cpu_init());
    need(bool(cpu), "CPU backend");
    ggml_backend_cpu_set_n_threads(cpu.get(), 1);
    ggml_context_ptr ctx(ggml_init({2u << 20, nullptr, true}));
    auto *c = ctx.get();
    need(c, "metadata");
    std::array<ggml_tensor *, roles> weights{};
    for (auto &w : weights) w = ggml_new_tensor_3d(c, GGML_TYPE_MXFP4, width, width, ranks);
    auto *ids = ggml_new_tensor_2d(c, GGML_TYPE_I32, ranks, 1);
    auto *x = ggml_new_tensor_3d(c, GGML_TYPE_F32, width, 1, 1);
    auto *mask = ggml_new_tensor_3d(c, GGML_TYPE_F32, 1, ranks, 1);
    auto *input = ggml_map_custom1(c, x, allow_reader, 1, &s);
    auto *up = ggml_mul_mat_id(c, weights[2], input, ids);
    auto *gate = ggml_mul_mat_id(c, weights[0], input, ids);
    auto *act = ggml_swiglu_oai(c, gate, up, 1.702f, 7.0f);
    auto *down = ggml_mul_mat_id(c, weights[1], act, ids);
    auto *pairs = ggml_mul(c, down, mask);
    auto *sum = ggml_view_1d(c, pairs, width, 0);
    for (int k = 1; k < ranks; ++k) {
        sum = ggml_add(c, sum, ggml_view_1d(c, pairs, width, k*pairs->nb[1]));
    }
    // R0 uses a scalar view of the masked per-rank accumulator before rank reduction.
    auto *view = ggml_view_1d(c, pairs, 1, 0);
    ggml_tensor *args[] = {ids, view};
    auto *observer = ggml_custom_4d(c, GGML_TYPE_I32, ranks, 1, 1, 1, args,
                                    arm == Arm::original ? 2 : 1, observe, 1, &s);
    auto *g = ggml_new_graph_custom(c, 64, false);
    if (!s.gold()) ggml_build_forward_expand(g, observer);
    ggml_build_forward_expand(g, sum);
    int projections = 0;
    for (int i = 0; i < ggml_graph_n_nodes(g); ++i) {
        auto *n = ggml_graph_node(g, i);
        if (n->op == GGML_OP_MUL_MAT_ID) {
            need(n->src[2] == ids &&
                 std::find(weights.begin(), weights.end(), n->src[0]) != weights.end(),
                 "projection slots");
            ++projections;
        }
    }
    need(projections == 3, "missing projection");
    ggml_backend_buffer_ptr buffer(ggml_backend_alloc_ctx_tensors(c, cpu.get()));
    need(bool(buffer), "operator allocation");
    for (int role = 0; role < roles; ++role) {
        need(weights[role]->nb[2] == slab, "weight stride");
        for (int slot = 0; slot < ranks; ++slot) {
            auto b = payload(arm == Arm::new_gold && slot == 0 ? 2 : 1, role, slot);
            ggml_backend_tensor_set(weights[role], b.data(), slot*slab, slab);
        }
    }
    std::array<float, width> input_data{};
    input_data.fill(0.25f);
    std::array<int32_t, ranks> indices = {0,1,2,3};
    std::array<float, ranks> kept = {1,0,0,0};
    ggml_backend_tensor_set(x,input_data.data(),0,sizeof(input_data));
    ggml_backend_tensor_set(ids,indices.data(),0,sizeof(indices));
    ggml_backend_tensor_set(mask,kept.data(),0,sizeof(kept));

    Triplet bank{};
    std::future<void> worker;
    if (!s.gold()) {
        worker = std::async(std::launch::async, [&] {
            for (int i=0; i<roles; ++i) ggml_backend_tensor_get(weights[i], bank[i].data(), 0, slab);
            s.mark(s.captured, "CAPTURED");
            if (arm == Arm::event) s.await(s.graph_done, "explicit event");
            else s.await(s.observed, "replacement observer");
            for (int i=0; i<roles; ++i) {
                auto b = payload(2, i, 0);
                ggml_backend_tensor_set(weights[i], b.data(), 0, slab);
            }
            s.mark(s.overwritten, "OVERWRITTEN");
        });
    }
    need(ggml_backend_graph_compute(cpu.get(), g) == GGML_STATUS_SUCCESS, "FFN compute");
    ggml_backend_synchronize(cpu.get());
    s.mark(s.graph_done, "GRAPH_DONE");
    if (worker.valid()) worker.get();
    std::array<float, width> result{};
    ggml_backend_tensor_get(sum, result.data(), 0, sizeof(result));
    save(dir/"out.f32", result.data(), sizeof(result));
    std::vector<uint8_t> primary(roles*ranks*slab);
    for (int role=0; role<roles; ++role) {
        ggml_backend_tensor_get(weights[role], primary.data()+role*ranks*slab, 0, ranks*slab);
    }
    save(dir/"slots.mxfp4", primary.data(), primary.size());
    if (!s.gold()) save(dir/"bank.mxfp4", bank.data(), sizeof(bank));
    if (arm == Arm::original) save(dir/"token.f32", &s.token, sizeof(s.token));
    for (const auto &step : s.sequence) std::cout << step << '\n';
    std::cout << "PROJECTIONS " << projections << '\n';
    for (const auto name : {"ggml_backend_cpu_init", "ggml_backend_tensor_set"}) {
        Dl_info info{};
        need(dladdr(dlsym(RTLD_DEFAULT, name), &info) != 0, "symbol provider");
        std::cout << "PROVIDER " << name << ' ' << fs::canonical(info.dli_fname).string() << '\n';
    }
    std::ifstream maps("/proc/self/maps");
    std::string line;
    need(bool(maps), "process mappings");
    while (std::getline(maps, line)) {
        need(line.find("/libcuda") == line.npos && line.find("/libggml-cuda") == line.npos,
             "CUDA DSO present in CPU-only process");
    }
}

int main(int argc, char **argv) {
    try {
        need(argc == 3, "usage: consumer old|new|original|event|broken NEW_DIR");
        const std::array<std::string,5> names = {"old","new","original","event","broken"};
        auto found = std::find(names.begin(),names.end(),argv[1]);
        need(found != names.end(), "arm");
        const fs::path dir(argv[2]);
        need(fs::create_directory(dir), "exclusive arm output");
        execute(static_cast<Arm>(found-names.begin()), dir);
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
