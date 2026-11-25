// Built against either the unchanged C269 source or its private counting overlay.
#include "llama-moe-stream.h"
#include "ggml-cpu.h"
#include "observe.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <sys/mman.h>
#include <sys/stat.h>
#include <vector>

namespace {
void check(bool ok, const char *msg) { if (!ok) throw std::runtime_error(msg); }
constexpr size_t PAGE = 4096, SLAB = 128;
constexpr std::array<size_t, 3> bases = {32, PAGE+64, 2*PAGE+96};
constexpr auto timeout = std::chrono::seconds(4);

struct Ledger {
    std::mutex mu;
    std::condition_variable cv;
    int fd = -1;
    bool first_tail_started = false, release_tail = false;
    uint64_t calls = 0, requests = 0, results = 0, foreign = 0;
} kernel;

bool idle(const llama_moe_stream &m, const llama_moe_stream_layer &sl) {
    return m.q_demand.empty() && std::count(sl.slot_claimed.begin(), sl.slot_claimed.end(), 1) == 0;
}

void submit(llama_moe_stream &m, llama_moe_stream_layer *sl, int expert, int slot) {
    m.reserve_slot_locked(*sl, expert, slot);
    const auto gen = sl->slot_gen[slot];
    phase_fd::records[expert] = {sl->il, expert, slot, gen, kernel.fd};
    if (!expert) m.q_demand.push_back({sl, expert, slot, gen-1}); // obsolete reservation
    m.q_demand.push_back({sl, expert, slot, gen});
    if (!expert) m.q_demand.push_back({sl, expert, slot, gen}); // duplicate claim
    m.cv_work.notify_all();
}
} // namespace

// Independent syscall witness and deterministic barrier; no elapsed-time endpoint.
extern "C" ssize_t __real_pread(int,void *,size_t,off_t);
extern "C" ssize_t __wrap_pread(int fd, void *buf, size_t requested, off_t off) {
    if (fd != kernel.fd) {
        std::lock_guard<std::mutex> lock(kernel.mu);
        ++kernel.foreign;
        return __real_pread(fd,buf,requested,off);
    }
    {
        std::unique_lock<std::mutex> lock(kernel.mu);
        if (off == 2*PAGE && !kernel.first_tail_started) {
            kernel.first_tail_started = true;
            kernel.cv.notify_all();
            if (!kernel.cv.wait_for(lock,timeout,[]{return kernel.release_tail;})) std::abort();
        }
    }
    const auto r = __real_pread(fd,buf,requested,off);
    const int saved = errno;
    {
        std::lock_guard<std::mutex> lock(kernel.mu);
        ++kernel.calls;
        kernel.requests += requested;
        if (r>0) kernel.results += static_cast<uint64_t>(r);
    }
    errno = saved;
    return r;
}

int main(int argc, char **argv) {
    try {
        check(argc == 3, "syntax");
        const bool on = std::string(argv[1]) == "ON";
        const bool fail = std::string(argv[2]) == "SHORT_INVALID";
        check((on || std::string(argv[1])=="OFF") && (fail || std::string(argv[2])=="SHORT_OK"), "mode");
        uint64_t at_A = 0, at_B = 0;
        const size_t tail = fail ? (96+SLAB-1) : (96+2*SLAB);
        std::vector<uint8_t> input(2*PAGE+tail);
        for (size_t i=0; i<input.size(); ++i) input[i] = static_cast<uint8_t>(i*17 + i/19 + 11);
        FILE *file = fdopen(memfd_create("phase-fd",MFD_CLOEXEC),"w+b");
        check(file && fwrite(input.data(),1,input.size(),file)==input.size() && !fflush(file), "memfd");
        FILE *other = tmpfile();
        check(other && fputc(17,other)==17 && !fflush(other), "second FD");
        std::unique_ptr<FILE, decltype(&fclose)> close_other(other,fclose);
        // llama_file(FILE*) in the pin borrows FILE*; the owner outlives the manager.
        std::unique_ptr<FILE, decltype(&fclose)> close_input(file,fclose);
        auto meta = ggml_context_ptr(ggml_init({ggml_tensor_overhead()*4,nullptr,true}));
        check(meta!=nullptr,"tensor metadata");
        {
            llama_moe_stream manager(1,40,4,true);
            manager.files.emplace_back(new llama_file(file));
            kernel.fd = manager.files.front()->file_id();
            check(kernel.fd==fileno(file) && fileno(other)!=kernel.fd,"FD binding");
            for (auto base : bases) {
                auto *weight = ggml_new_tensor_3d(meta.get(),GGML_TYPE_I8,SLAB,1,64);
                manager.create_cache_tensor(0,ggml_backend_cpu_buffer_type(),weight,0,base);
            }
            manager.alloc_bufs(false);
            auto *sl=manager.layer(0);
            check(sl && sl->weights.size()==3,"layer");
            for(const auto &wt:sl->weights) {
                std::vector<uint8_t> sentinel(ggml_nbytes(wt.cache),0xcb);
                ggml_backend_tensor_set(wt.cache,sentinel.data(),0,sentinel.size());
            }
            {
                std::lock_guard<std::mutex> lock(manager.mtx);
                submit(manager,sl,0,3);
                manager.start_workers_locked();
            }
            {
                std::unique_lock<std::mutex> lock(kernel.mu);
                check(kernel.cv.wait_for(lock,timeout,[]{return kernel.first_tail_started;}), "A did not enter read");
                at_A=kernel.results;
                check(kernel.calls==2 && at_A==2*PAGE,"first return snapshot");
            }
            // A duplicate skipped by the native worker does not notify cv_done.
            // Wait separately for the dequeue before testing the last publication.
            const auto until=std::chrono::steady_clock::now()+timeout;
            for (;;) {
                {
                    std::lock_guard<std::mutex> lk(manager.mtx);
                    if (manager.q_demand.empty()) break;
                }
                check(std::chrono::steady_clock::now()<until,"duplicate still queued");
                std::this_thread::yield();
            }
            uint8_t byte=0;
            check(phase_fd::read(fileno(other),&byte,1,0)==1 && byte==17,"unrelated FD read");
            {
                std::unique_lock<std::mutex> lock(manager.mtx);
                check(manager.workers.size()==4 && !idle(manager,*sl) && sl->slot_claimed[3], "false drain");
                if (!fail) {
                    submit(manager,sl,1,9);
                    check(manager.cv_done.wait_for(lock,timeout,[&]{return sl->slot_state[9]==LLAMA_MOE_STREAM_SLOT_RESIDENT;}),"B publication");
                    check(!idle(manager,*sl) && sl->slot_state[3]==LLAMA_MOE_STREAM_SLOT_LOADING,"B falsely drained A");
                }
            }
            {
                std::lock_guard<std::mutex> lock(kernel.mu);
                at_B=kernel.results;
                check(at_B==at_A+(fail?0:2*PAGE+tail),"second boundary snapshot");
                kernel.release_tail=true;
            }
            kernel.cv.notify_all();
            {
                std::unique_lock<std::mutex> lock(manager.mtx);
                check(manager.cv_done.wait_for(lock,timeout,[&]{return idle(manager,*sl);}),"terminal pending work");
                check(manager.load_failed==fail &&
                      sl->slot_state[3]==(fail?LLAMA_MOE_STREAM_SLOT_LOADING:LLAMA_MOE_STREAM_SLOT_RESIDENT),"publication state");
            }
            for(int expert=0; expert<(fail?1:2); ++expert) {
                int slot=expert?9:3;
                for(size_t c=0;c<bases.size();++c){
                    std::array<uint8_t,SLAB> actual{};
                    ggml_backend_tensor_get(sl->weights[c].cache,actual.data(),slot*SLAB,SLAB);
                    if (fail && c==2) check(std::all_of(actual.begin(),actual.end(),[](uint8_t x){return x==0xcb;}),"rejected payload");
                    else check(std::equal(actual.begin(),actual.end(),input.begin()+bases[c]+expert*SLAB),"destination mismatch");
                }
                const auto &r=phase_fd::records[expert];
                check(r.starts==unsigned(on) && r.attempts==unsigned(on?3:0) &&
                      r.requested==(on?3*PAGE:0) && r.returned==(on?2*PAGE+tail:0) &&
                      r.components==unsigned(on?(fail?2:3):0) && r.payload==(on?(fail?2:3)*SLAB:0) &&
                      r.publications==unsigned(on&&!fail) && r.load_errors==unsigned(on&&fail) &&
                      r.failed==0 && r.interrupted==0,"per-generation observer reconciliation");
            }
        } // the native destructor joins all four workers
        const int jobs=fail?1:2;
        check(kernel.foreign==1 && kernel.calls==static_cast<uint64_t>(jobs*3) &&
              kernel.requests==jobs*3*PAGE && kernel.results==jobs*(2*PAGE+tail),"syscall conservation");
        std::printf("{\"status\":\"PASS\",\"workers_joined\":4,\"pending_at_A_return\":1,"
                    "\"A_first_return_bytes\":%llu,\"before_A_release_bytes\":%llu,"
                    "\"foreign_calls\":1,\"calls\":%llu,"
                    "\"requested_bytes\":%llu,\"returned_bytes\":%llu,\"set_payload_bytes\":%zu,"
                    "\"publications\":%d,\"read_protocol_errors\":%d,\"drained_terminal\":true}\n",
                    (unsigned long long)at_A,(unsigned long long)at_B,(unsigned long long)kernel.calls,(unsigned long long)kernel.requests,
                    (unsigned long long)kernel.results,(fail?2:6)*SLAB,fail?0:2,fail?1:0);
        return 0;
    } catch(const std::exception &e) {
        std::fprintf(stderr,"%s\n",e.what());
        return 1;
    }
}
