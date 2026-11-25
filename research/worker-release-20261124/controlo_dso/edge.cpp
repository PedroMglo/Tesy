// Execute the pinned decode routing edge in the original C305 DSO on one CPU layer.
#include "llama-moe-stream.h"
#include "c305-cpu-stage.h"
#include "c291-expert-store.h"
#include "ggml-cpu.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <pthread.h>
#include <set>
#include <sys/stat.h>
#include <thread>
#include <zlib.h>

namespace fs = std::filesystem;
using json = nlohmann::json;
constexpr size_t slab = c305_cpu_stage::slab;
constexpr size_t region = (128 * slab + 4095) / 4096 * 4096;

void check(bool ok, const char *why) {
    if (!ok) throw std::runtime_error(why);
}

std::array<float, 128> read_scores(const fs::path &path) {
    std::array<float, 128> values{};
    std::ifstream input(path, std::ios::binary);
    input.read(reinterpret_cast<char *>(values.data()), sizeof(values));
    check(input.gcount() == sizeof(values) && input.peek() == std::char_traits<char>::eof(),
          "score row size");
    check(std::all_of(values.begin(), values.end(), [](float f) { return std::isfinite(f); }),
          "nonfinite score");
    return values;
}

std::set<std::string> mapped_libraries() {
    std::set<std::string> libraries;
    std::ifstream maps("/proc/self/maps");
    check(bool(maps), "cannot read mappings");
    for (std::string line; std::getline(maps, line); ) {
        const auto i = line.find('/');
        if (i == std::string::npos) continue;
        fs::path path(line.substr(i));
        const auto name = path.filename().string();
        if (name.find(".so") != std::string::npos) {
            check(fs::is_regular_file(path), "mapping no longer names a regular file");
            libraries.insert(fs::canonical(path).string());
        }
    }
    return libraries;
}

std::string write_component(const fs::path &root, const llama_moe_stream_weight &weight,
                            int rank, int slot, int k, std::vector<uint8_t> &buffer) {
    check(weight.nb_expert == buffer.size(), "wrong expert slab");
    ggml_backend_tensor_get(weight.cache, buffer.data(), size_t(slot) * weight.nb_expert,
                            buffer.size());
    const auto name = "rank" + std::to_string(rank) + "-component" + std::to_string(k) + ".bin.gz";
    const auto path = root / name;
    gzFile output = gzopen(path.c_str(), "wb1x");
    check(output != nullptr, "cannot create destination");
    const int wrote = gzwrite(output, buffer.data(), static_cast<unsigned>(buffer.size()));
    const auto closed = gzclose(output);
    check(wrote == static_cast<int>(buffer.size()) && closed == Z_OK, "destination write failed");
    return name;
}

json run(const fs::path &score_file, const fs::path &sparse_file, const fs::path &root) {
    check(fs::is_directory(root) && fs::is_empty(root), "output must be an existing empty directory");
    const auto scores = read_scores(score_file);
    struct stat st{};
    check(::stat(sparse_file.c_str(), &st) == 0 && S_ISREG(st.st_mode) &&
          st.st_size == static_cast<off_t>(3 * region + 4096) &&
          static_cast<uint64_t>(st.st_blocks) * 512 < 200ull * 1024 * 1024,
          "wrong sparse source");
    // The original implementation is compiled in libllama, not in this executable.
    Dl_info symbol{};
    check(dladdr(reinterpret_cast<void *>(&llama_moe_stream_remap), &symbol) && symbol.dli_fname,
          "cannot identify remap definition");
    const auto definition = fs::canonical(symbol.dli_fname);
    check(definition.filename().string().rfind("libllama.so", 0) == 0,
          "remap is not owned by libllama");
    ggml_context_ptr meta(ggml_init({1024*1024, nullptr, true}));
    ggml_context_ptr ctx(ggml_init({2*1024*1024, nullptr, true}));
    ggml_backend_ptr cpu(ggml_backend_cpu_init());
    check(meta && ctx && cpu, "CPU/graph context");
    ggml_backend_cpu_set_n_threads(cpu.get(), 1);
    ggml_backend_t device = cpu.get();
    ggml_backend_sched_ptr scheduler(ggml_backend_sched_new(&device, nullptr, 1, 128, false, false));
    check(bool(scheduler), "scheduler");
    json result;
    std::set<pid_t> tids;
    {
        llama_moe_stream manager(36, 40, 4, true);
        for (int k = 0; k < 3; ++k) {
            auto *tensor = ggml_new_tensor_3d(meta.get(), GGML_TYPE_MXFP4, 2880, 2880, 128);
            manager.create_cache_tensor(4, ggml_backend_cpu_buffer_type(), tensor, 0, k * region);
        }
        manager.alloc_bufs(false);
        manager.open_files({sparse_file.string()});
        check(manager.use_direct_io && manager.files.size() == 1 && manager.files[0]->has_direct_io()
              && !manager.prediction_stage && !manager.expert_store, "wrong byte service");
        auto *layer = manager.layer(4);
        check(layer && layer->weights.size() == 3 && layer->n_slots == 40 &&
              layer->n_expert == 128 && layer->expert_slot.empty(), "wrong initial pool");

        auto *input = ggml_new_tensor_2d(ctx.get(), GGML_TYPE_F32, 128, 1);
        ggml_set_input(input);
        auto *selected = ggml_argsort_top_k(ctx.get(), input, 4);
        auto *ids = ggml_cont(ctx.get(), selected);
        auto *mapped = ggml_map_custom1(ctx.get(), ids, llama_moe_stream_remap, 1, layer);
        check(selected->op == GGML_OP_VIEW && selected->src[0]->op == GGML_OP_ARGSORT &&
              ids->op == GGML_OP_CONT && ids->src[0] == selected && mapped->op == GGML_OP_MAP_CUSTOM1 &&
              mapped->src[0] == ids && ids->ne[0] == 4 && ids->ne[1] == 1 && ids->type == GGML_TYPE_I32,
              "GGML decode edge changed");
        ggml_set_output(ids);
        ggml_set_output(mapped);
        auto *graph = ggml_new_graph_custom(ctx.get(), 128, false);
        ggml_build_forward_expand(graph, mapped);
        check(ggml_backend_sched_alloc_graph(scheduler.get(), graph), "scheduler allocation");
        ggml_backend_tensor_set(input, scores.data(), 0, sizeof(scores));
        manager.window.call.store(1);
        check(ggml_backend_sched_graph_compute(scheduler.get(), graph) == GGML_STATUS_SUCCESS,
              "CPU graph execution");
        ggml_backend_sched_synchronize(scheduler.get());
        std::array<int32_t, 4> ranks{}, slots{};
        ggml_backend_tensor_get(ids, ranks.data(), 0, sizeof(ranks));
        ggml_backend_tensor_get(mapped, slots.data(), 0, sizeof(slots));
        check(ggml_backend_sched_get_tensor_backend(scheduler.get(), mapped) == device &&
              ggml_backend_buffer_is_host(mapped->buffer) && ggml_backend_buffer_is_host(ids->buffer) &&
              ggml_backend_buffer_is_host(input->buffer), "unexpected backend placement");
        result["scheduler"] = {{"backend",ggml_backend_name(device)}, {"ops",{"ARGSORT","VIEW","CONT","MAP_CUSTOM1"}},
                               {"top_k",4},{"score_shape",{128,1}},{"id_shape",{4,1}},{"remap_tasks",1}};
        result["ranks"] = ranks;
        result["slots"] = slots;
        result["destinations"] = json::array();
        std::vector<uint8_t> buffer(slab);
        {
            std::lock_guard<std::mutex> guard(manager.mtx);
            check(manager.stats.n_calls == 1 && manager.stats.n_miss == 4 &&
                  manager.stats.n_hit == 0 && layer->expert_slot.size() == 4, "native remap counts");
            check(manager.q_demand.empty() && !manager.load_failed && manager.workers.size()==4 &&
                  std::all_of(layer->slot_claimed.begin(),layer->slot_claimed.end(),
                              [](auto x){return x==0;}), "incomplete service");
            for (auto &worker : manager.workers) {
                const auto tid = pthread_gettid_np(worker.native_handle());
                check(worker.joinable() && tid > 0 && tids.insert(tid).second, "worker identity");
            }
        }
        for (int i = 0; i < 4; ++i) {
            const auto slot = slots[i];
            check(slot >= 0 && slot < 40 && ranks[i] >= 0 && ranks[i] < 128 &&
                  layer->slot_expert.at(slot) == ranks[i] && layer->slot_gen.at(slot) == 1 &&
                  layer->slot_state.at(slot) == LLAMA_MOE_STREAM_SLOT_RESIDENT, "wrong publication");
            json files = json::array();
            for (int k = 0; k < 3; ++k) {
                files.push_back(write_component(root, layer->weights[k], i, slot, k, buffer));
            }
            result["destinations"].push_back({{"expert",ranks[i]},{"slot",slot},
                {"generation",layer->slot_gen.at(slot)},{"files",files}});
        }
        result["n_calls"] = manager.stats.n_calls;
        result["n_miss"] = manager.stats.n_miss;
        result["n_hit"] = manager.stats.n_hit;
        result["terminal"] = {{"workers",manager.workers.size()},{"queue",manager.q_demand.size()},
                              {"claimed",0},{"load_failed",manager.load_failed},{"direct_primary",manager.use_direct_io}};
        result["mapped_dsos"] = mapped_libraries();
        result["remap_symbol_dso"] = definition.string();
    }
    // The destructor joins these exact workers. Confirm all four TIDs disappeared
    // while the rest of the scheduler and this process are still alive.
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    for (pid_t tid : tids) {
        const fs::path task = fs::path("/proc/self/task") / std::to_string(tid);
        while (fs::exists(task) && std::chrono::steady_clock::now() < deadline)
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        check(!fs::exists(task), "worker survived manager destruction");
    }
    result["terminal"]["joins"] = tids.size();
    return result;
}

int main(int argc, char **argv) {
    try {
        check(argc == 4, "usage: edge SCORES_F32 SPARSE_INPUT EMPTY_OUTPUT_DIR");
        const auto result = run(argv[1],argv[2],argv[3]);
        std::ofstream out(fs::path(argv[3]) / "raw.json");
        out << result.dump(2) << '\n';
        out.close();
        check(bool(out), "raw JSON write failed");
    } catch (const std::exception &e) {
        std::cerr << "EDGE_FAIL " << e.what() << '\n';
        return 1;
    }
}
