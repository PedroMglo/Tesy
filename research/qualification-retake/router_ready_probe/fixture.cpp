#include "tap.h"
#include "llama-moe-stream.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include <algorithm>
#include <cmath>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <set>
#include <stdexcept>
#include <vector>

static Probe *active;
static void need(bool ok, const char *what) {
    if (!ok) throw std::runtime_error(what);
}

static void remap_enter(ggml_tensor *dst, const ggml_tensor *compact, int ith) {
    if (ith != 0) return;
    if (active->mode) active->consumer = clock_now();
    ++active->remaps;
    active->remap_identity = dst == active->remap && compact == active->compact &&
        compact->op == GGML_OP_CONT && compact->src[0] == active->ids &&
        ggml_is_contiguous(compact) && compact->nb[1] == 16 &&
        compact->buffer && ggml_backend_buffer_is_host(compact->buffer);
}

static void forward_simple(ggml_tensor *dst, const ggml_tensor *a, int ith, int nth, void *ud) {
    remap_enter(dst, a, ith);
    llama_moe_stream_remap(dst, a, ith, nth, ud);
}
static void forward_wave(ggml_tensor *dst, int ith, int nth, void *ud) {
    remap_enter(dst, dst->src[0], ith);
    llama_moe_stream_wave_ids(dst, ith, nth, ud);
}

static int slot_for(int expert) { return (expert*7+3) % 40; }

static void run(std::string mode, int rows, const char *payload, const char *provider) {
    const bool simple = rows == 5;
    need(simple || rows == 20 || rows == 32, "unexpected tile");
    const bool base = mode == "BASE";
    need(base || mode == "OFF" || mode == "ON" || mode == "WRONG", "mode");
    auto *cpu = ggml_backend_cpu_init();
    need(cpu != nullptr, "CPU init");
    ggml_backend_cpu_set_n_threads(cpu, 8);
    auto *sched = ggml_backend_sched_new(&cpu, nullptr, 1, 256, false, true);
    auto *ctx = ggml_init({2u << 20, nullptr, true});
    need(sched && ctx, "graph init");
    llama_moe_stream manager(1,40,4,true);
    auto *meta = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 1, 1, 128);
    manager.create_cache_tensor(0, ggml_backend_cpu_buffer_type(), meta, 0, 0);
    manager.alloc_bufs(false);
    auto *layer = manager.layer(0);
    for (int e=0; e<40; ++e) {
        int s = slot_for(e);
        layer->slot_expert[s] = e;
        layer->slot_gen[s] = 1;
        layer->slot_state[s] = LLAMA_MOE_STREAM_SLOT_RESIDENT;
        layer->expert_slot[e] = s;
    }

    auto *graph = ggml_new_graph_custom(ctx, 256, false);
    auto *logits = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, 128, rows);
    ggml_set_input(logits);
    auto *ids = ggml_argsort_top_k(ctx, logits, 4);
    auto *gather = ggml_get_rows(ctx, ggml_reshape_3d(ctx, logits, 1, 128, rows), ids);
    auto *weights = ggml_reshape_3d(ctx, ggml_soft_max(ctx,
        ggml_reshape_2d(ctx, gather, 4, rows)), 1, 4, rows);
    ggml_set_output(weights);
    ggml_build_forward_expand(graph, weights);
    auto *compact = ggml_cont(ctx, ids);
    ggml_set_output(compact); // preserve this validation output through endpoint
    auto *remap = simple ? ggml_map_custom1(ctx, compact, base ? llama_moe_stream_remap : forward_simple, 1, layer)
        : ggml_custom_4d(ctx, GGML_TYPE_I32, 4, rows, 1, 1, &compact, 1,
            base ? llama_moe_stream_wave_ids : forward_wave, 1, layer->wave_userdata(0,18));
    ggml_set_output(remap);
    ggml_build_forward_expand(graph, remap);
    need(ggml_backend_sched_alloc_graph(sched, graph), "graph allocation");
    for (auto *node: {ids->src[0], gather, compact, remap})
        need(ggml_backend_sched_get_tensor_backend(sched,node) == cpu, "node placement");
    int n_nodes = ggml_graph_n_nodes(graph), gathers = 0;
    std::string ops;
    for (int j=0;j<n_nodes;++j) {
        auto op = ggml_graph_node(graph,j)->op;
        if (op == GGML_OP_GET_ROWS) ++gathers;
        if (j) ops += ',';
        ops += ggml_op_name(op);
    }
    need(ggml_backend_sched_get_n_splits(sched) == 1 && gathers == 1, "split/gather");

    std::vector<int32_t> expected(4*rows), slots(4*rows), actual(4*rows);
    std::vector<float> data(128*rows), probs(4*rows);
    for (int t=0;t<rows;++t) {
        for (int e=0;e<128;++e) data[t*128+e] = float(-128-e);
        for (int r=0;r<4;++r) {
            int e = (t*5 + r*3) % 16;
            expected[t*4+r] = e;
            data[t*128+e] = float(4-r) + float(t)/64;
        }
    }
    ggml_backend_tensor_set(logits, data.data(), 0, data.size()*sizeof(float));
    Probe probe{};
    probe.target=gather; probe.ids=ids; probe.remap=remap; probe.compact=compact;
    probe.mode = mode == "ON" ? 1 : (mode == "WRONG" ? 2 : 0);
    auto arm = reinterpret_cast<void *(*)(Probe *)>(dlsym(RTLD_DEFAULT,"ready_probe_arm"));
    need((arm == nullptr) == base, "unexpected observer linkage");
    if (arm) {
        active = &probe;
        void *kernel = arm(&probe);
        Dl_info info{};
        need(kernel && dladdr(kernel,&info) && info.dli_fname &&
             std::filesystem::equivalent(info.dli_fname,provider), "original GET_ROWS provider");
    }
    timespec resolution{};
    need(clock_getres(CLOCK_MONOTONIC,&resolution)==0, "clock resolution");
    auto min_tick = std::numeric_limits<uint64_t>::max();
    auto previous = clock_now();
    for (int i=0;i<1024;++i) {
        auto t=clock_now();
        need(t>=previous, "monotonic clock");
        if (t>previous) min_tick=std::min(min_tick,t-previous);
        previous=t;
    }
    need(min_tick<std::numeric_limits<uint64_t>::max(), "no positive clock delta");
    need(ggml_backend_sched_graph_compute(sched,graph)==GGML_STATUS_SUCCESS, "compute");
    ggml_backend_sched_synchronize(sched);
    ggml_backend_tensor_get(compact,actual.data(),0,actual.size()*4);
    ggml_backend_tensor_get(remap,slots.data(),0,slots.size()*4);
    ggml_backend_tensor_get(weights,probs.data(),0,probs.size()*4);
    need(expected == actual, "compact ids vs oracle");
    for (size_t i=0;i<actual.size();++i) {
        need(slots[i]==slot_for(expected[i]), "slot vs oracle");
        need(std::isfinite(probs[i]) && probs[i]>0 && probs[i]<1, "softmax");
    }
    need(manager.stats.n_calls==1 && manager.stats.n_wave_calls==!simple &&
         manager.stats.n_miss==0 && manager.stats.n_preload_issued==0 &&
         manager.workers.size()==4 && size_t(manager.stats.n_hit)==std::set<int32_t>(expected.begin(),expected.end()).size() &&
         manager.q_demand.empty() && !manager.load_failed, "manager accounting");
    int different = 0;
    if (arm) {
        need(probe.kernel_identity && probe.remap_identity && probe.entries==1 &&
             probe.forwarded==1 && probe.remaps==1, "observer delivery");
        if (probe.mode) {
            need(probe.start && probe.ready>=probe.start && probe.consumer>=probe.ready, "clock order");
            for (size_t i=0;i<expected.size();++i) different += expected[i] != probe.snapshot[i];
            need((different>0)==(mode=="WRONG"), "strided observation vs oracle");
        } else need(!probe.start && !probe.ready && !probe.consumer, "OFF timestamps");
    }
    std::ofstream output(payload, std::ios::binary);
    need(output.good(),"open outputs");
    for (auto ptr : {static_cast<const void *>(actual.data()),static_cast<const void *>(slots.data()),
                     static_cast<const void *>(probs.data())})
        output.write(static_cast<const char *>(ptr), 4*actual.size());
    output.close(); need(output.good(), "write outputs");
    std::cout << "mode=" << mode << "\nrows=" << rows << "\ngraph=" << ops
              << "\nsplits=1\nentries=" << probe.entries << "\nforwarded=" << probe.forwarded
              << "\nremaps=" << probe.remaps << "\nthreads=" << probe.threads << "\ndifferent=" << different
              << "\nstart=" << probe.start << "\nready=" << probe.ready << "\nconsumer=" << probe.consumer
              << "\nresolution=" << nanos(resolution) << "\nmin_tick=" << min_tick
              << "\nhits=" << manager.stats.n_hit << "\n";
    ggml_backend_sched_free(sched);
    ggml_free(ctx);
    ggml_backend_free(cpu);
}

int main(int argc, char **argv) {
    try {
        need(argc==5,"usage: fixture MODE ROWS NEW_OUTPUT CPU_DSO");
        run(argv[1],std::stoi(argv[2]),argv[3],argv[4]);
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
