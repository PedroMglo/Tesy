#include "llama-moe-stream.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <sys/syscall.h>
#include <unistd.h>

static std::atomic<int> held_fd{-1};
static std::atomic<bool> entered{false};
static std::atomic<bool> released{false};

extern "C" ssize_t pread(int fd, void * data, size_t count, off_t offset) {
    if (fd == held_fd.load() && !entered.exchange(true)) {
        while (!released.load()) std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    return syscall(SYS_pread64,fd,data,count,offset);
}

static void require(bool ok, const char * message) {
    if (!ok) throw std::runtime_error(message);
}

int main() {
    char path[] = "/tmp/tesy-c3-inflight-XXXXXX";
    const int fixture_fd = mkstemp(path);
    if (fixture_fd < 0) return 2;
    try {
        std::vector<uint8_t> payload(128*4096);
        for (int expert=0; expert<128; ++expert)
            std::memset(payload.data()+expert*4096,expert+17,4096);
        require(write(fixture_fd,payload.data(),payload.size()) ==
                static_cast<ssize_t>(payload.size()),"fixture write short");
        close(fixture_fd);
        ggml_init_params params{1024*1024,nullptr,true};
        ggml_context * ctx = ggml_init(params);
        require(ctx != nullptr,"ggml context failed");
        ggml_tensor * cache = ggml_new_tensor_3d(ctx,GGML_TYPE_F32,1024,1,12);
        ggml_backend_t cpu = ggml_backend_cpu_init();
        require(cpu != nullptr,"CPU backend failed");
        ggml_backend_buffer_t buffer = ggml_backend_alloc_ctx_tensors(ctx,cpu);
        require(buffer != nullptr,"cache allocation failed");
        {
            llama_moe_stream mgr(1,12,1,false);
            mgr.layers[0] = std::make_unique<llama_moe_stream_layer>();
            auto & sl = *mgr.layers[0];
            sl.mgr = &mgr; sl.il = 0; sl.n_slots = 12; sl.n_expert = 128;
            sl.slot_expert.assign(12,-1);
            sl.slot_state.assign(12,LLAMA_MOE_STREAM_SLOT_EMPTY);
            sl.slot_claimed.assign(12,0);
            sl.slot_gen.assign(12,0);
            sl.slot_last_use.assign(12,0);
            sl.route_hotness.assign(128,0);
            sl.seen.assign(128,0);
            mgr.files.emplace_back(new llama_file(path,"rb",false));
            mgr.max_nb_expert = 4096;
            sl.weights.push_back({cache,0,0,4096});
            held_fd.store(mgr.files.front()->file_id());
            std::unique_lock<std::mutex> lock(mgr.mtx);
            mgr.reserve_slot_locked(sl,7,0);
            mgr.q_demand.push_back({&sl,7,0,sl.slot_gen[0]});
            mgr.start_workers_locked();
            mgr.cv_work.notify_all();
            lock.unlock();
            const auto deadline = std::chrono::steady_clock::now()+std::chrono::seconds(2);
            while (!entered.load() && std::chrono::steady_clock::now()<deadline)
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            require(entered.load(),"worker did not enter held pread");
            lock.lock();
            require(sl.slot_state[0] == LLAMA_MOE_STREAM_SLOT_LOADING &&
                    sl.slot_claimed[0] && sl.slot_expert[0] == 7,
                    "in-flight read slot lost its claim");
            for (int slot=1; slot<12; ++slot) {
                sl.slot_expert[slot] = slot+7;
                sl.slot_state[slot] = LLAMA_MOE_STREAM_SLOT_RESIDENT;
            }
            const int victim = mgr.pick_victim_locked(sl,nullptr);
            require(victim >= 1 && victim < 12,"in-flight slot was evictable");
            released.store(true);
            const bool ready = mgr.cv_done.wait_for(lock,std::chrono::seconds(2),[&] {
                return sl.slot_state[0] == LLAMA_MOE_STREAM_SLOT_RESIDENT;
            });
            require(ready && !sl.slot_claimed[0] && sl.slot_gen[0] == 1,
                    "completed read was not published at the same generation");
            lock.unlock();
            std::vector<uint8_t> observed(4096);
            ggml_backend_tensor_get(cache,observed.data(),0,observed.size());
            require(std::all_of(observed.begin(),observed.end(),[](uint8_t x){return x==24;}),
                    "resident slot bytes differ from fixture expert");
            held_fd.store(-1);
        }
        ggml_backend_buffer_free(buffer);
        ggml_backend_free(cpu);
        ggml_free(ctx);
        unlink(path);
        std::cout << "{\"schema\":\"c3-inflight-read-test-v1\","
                  << "\"held_read_observed\":true,"
                  << "\"claimed_loading_slot_excluded\":true,"
                  << "\"correct_bytes_published\":true,"
                  << "\"gpu_upload_tested\":false}\n";
        return 0;
    } catch (const std::exception & error) {
        released.store(true);
        unlink(path);
        std::cerr << "C3_INFLIGHT_FAIL: " << error.what() << '\n';
        return 1;
    }
}
