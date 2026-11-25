// C305 manager integration driver. All waits imposed on I/O are outside its mutex.
#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include "c305-cpu-stage.h"
#include "fixture_observer.h"

#include <sys/syscall.h>
#include <zlib.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using json = nlohmann::json;
using Stage = c305_cpu_stage;
using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;

namespace {

constexpr size_t region = ((128 * Stage::slab + 4095) / 4096) * 4096;
using Time = Clock::time_point;

struct Job {
    int expert = -1;
    int slot = -1;
    uint64_t generation = 0;
    uint64_t ticket = 0;
};

struct Event {
    const char *kind;
    long tid;
    int worker;
    int component;
    Time time;
    Job job;
};

struct Gate {
    Time arrival{};
    Time deadline{};
    Time opened{};
};

thread_local int ordinal = -1;
thread_local Job service;
std::array<Event, 256> journal;
size_t written = 0;
std::mutex journal_mutex;
std::atomic<bool> active{false};

int primary_fd = -1;
int stage_fd = -1;
size_t stage_align = 0;
std::mutex gate_mutex;
std::condition_variable gate_changed;
std::array<Gate, 5> gates;
std::array<std::array<int, 3>, 5> issued{}, delivered{};
std::string schedule;
Time t0{};
bool release_fault_read = false;

void check(bool ok, const char *why) {
    if (!ok) {
        std::cerr << "FAIL: " << why << std::endl;
        std::_Exit(1);
    }
}

int64_t ns(Time time) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(time.time_since_epoch()).count();
}

Time record(const char *kind, Job job = {}, int component = -1) {
    std::lock_guard<std::mutex> lock(journal_mutex);
    check(written < journal.size(), "observer overflow");
    const auto time = Clock::now();
    journal[written++] = {kind, syscall(SYS_gettid), ordinal, component, time, job};
    return time;
}

bool fault_case() { return schedule == "fault" || schedule == "stale"; }

void wait_arrival(int expert) {
    std::unique_lock<std::mutex> lock(gate_mutex);
    check(gate_changed.wait_for(lock, 10s, [&] { return gates.at(expert).arrival != Time{}; }),
          "reader did not reach first component");
}

void start_clock() {
    std::lock_guard<std::mutex> lock(gate_mutex);
    check(t0 == Time{}, "duplicate t0");
    t0 = record("t0");
    gate_changed.notify_all();
}

void first_read_gate(int expert, std::unique_lock<std::mutex> &lock) {
    auto &gate = gates.at(expert);
    gate.arrival = Clock::now();
    gate_changed.notify_all();
    if (fault_case()) {
        check(gate_changed.wait_for(lock, 10s, [] { return release_fault_read; }),
              "fault read was never released");
    } else {
        check(gate_changed.wait_for(lock, 10s, [] { return t0 != Time{}; }), "missing remap t0");
        switch (expert) {
            case 1: gate.deadline = t0 + 450ms; break;
            case 2: gate.deadline = t0 + 250ms; break;
            case 3: gate.deadline = t0 + (schedule == "early" ? 350ms : 1400ms); break;
            case 4: gate.deadline = gate.arrival + 650ms; break;
            default: check(false, "invalid gate");
        }
        // Sleep in the I/O worker without holding either manager or gate mutex.
        lock.unlock();
        std::this_thread::sleep_until(gate.deadline);
        lock.lock();
    }
    gate.opened = Clock::now();
}

template<class Predicate>
void await_manager(llama_moe_stream &mgr, Predicate predicate, const char *why) {
    const Time deadline = Clock::now() + 10s;
    std::unique_lock<std::mutex> lock(mgr.mtx);
    while (!predicate()) {
        check(Clock::now() < deadline, why);
        mgr.cv_done.wait_until(lock, std::min(deadline, Clock::now() + 10ms));
    }
}

bool direct(int fd) {
    const int flags = fcntl(fd, F_GETFL);
    return flags >= 0 && (flags & O_DIRECT);
}

json destinations(const std::string &root, const llama_moe_stream_layer &layer, const ggml_tensor *out) {
    json result = json::array();
    std::vector<uint8_t> slab(Stage::slab);
    for (int rank = 0; rank < 4; ++rank) {
        const int slot = static_cast<const int32_t *>(out->data)[rank];
        check(layer.slot_state.at(slot) == LLAMA_MOE_STREAM_SLOT_RESIDENT, "unpublished slot");
        json files = json::array();
        for (int k = 0; k < 3; ++k) {
            const auto &w = layer.weights.at(k);
            check(w.nb_expert == slab.size(), "encoding/size");
            ggml_backend_tensor_get(w.cache, slab.data(), size_t(slot) * w.nb_expert, w.nb_expert);
            const std::string name = "rank" + std::to_string(rank) + "-component" +
                                     std::to_string(k) + ".bin.gz";
            gzFile gzip = gzopen((root + "/" + name).c_str(), "wb1");
            check(gzip, "compressed output");
            const int bytes = gzwrite(gzip, slab.data(), slab.size());
            const int closed = gzclose(gzip);
            check(bytes == int(slab.size()) && closed == Z_OK, "write destination");
            files.push_back(name);
        }
        result.push_back({{"expert", layer.slot_expert.at(slot)}, {"slot", slot},
                          {"generation", layer.slot_gen.at(slot)}, {"files", files}});
    }
    return result;
}

json exercise_fault(llama_moe_stream &mgr, llama_moe_stream_layer &layer) {
    // A failed native remap intentionally calls GGML_ABORT. Submit through its
    // real reserve/enqueue primitives so the manager's terminal state is observable.
    int slot;
    uint64_t original_gen;
    {
        std::lock_guard<std::mutex> lock(mgr.mtx);
        slot = mgr.pick_victim_locked(layer, nullptr);
        check(slot >= 0, "fault slot");
        mgr.reserve_slot_locked(layer, 1, slot);
        original_gen = layer.slot_gen.at(slot);
        mgr.enqueue_locked(&layer, 1, slot, original_gen);
        mgr.cv_work.notify_all();
    }
    await_manager(mgr, [&] { return mgr.continuation_count_locked() == 1; }, "no attached work");
    if (schedule == "stale") {
        std::lock_guard<std::mutex> lock(mgr.mtx);
        check(layer.slot_claimed.at(slot) && layer.slot_gen.at(slot) == original_gen,
              "old generation missing its claim");
        // Model a newer owner of the same expert/slot via a new generation. The
        // older completion must never clear the claim or publish to this owner.
        ++layer.slot_gen.at(slot);
        ob::note("new_generation", 1, slot, layer.slot_gen.at(slot));
    }
    {
        std::lock_guard<std::mutex> lock(gate_mutex);
        release_fault_read = true;
        gate_changed.notify_all();
    }
    // Sticky load_failed is published under mtx after rejection of this one job.
    await_manager(mgr, [&] { return mgr.load_failed; }, "fault failed to terminate");
    bool threw = false;
    std::string message;
    ob::note("finish_entry");
    try {
        mgr.prediction_finish();
    } catch (const std::runtime_error &error) {
        threw = true;
        message = error.what();
    }
    ob::note(threw ? "finish_throw" : "finish_return");
    bool restart_rejected = false;
    try {
        mgr.prediction_begin(true);
    } catch (const std::runtime_error &) {
        restart_rejected = true;
    }
    std::lock_guard<std::mutex> lock(mgr.mtx);
    const auto state = layer.slot_state.at(slot);
    const char *state_name = state == LLAMA_MOE_STREAM_SLOT_LOADING ? "LOADING" :
                             state == LLAMA_MOE_STREAM_SLOT_RESIDENT ? "RESIDENT" : "EMPTY";
    return {{"slot", slot}, {"original_generation", original_gen},
            {"observed_generation", layer.slot_gen.at(slot)}, {"observed_expert", layer.slot_expert.at(slot)},
            {"claimed", int(layer.slot_claimed.at(slot))}, {"state", state_name},
            {"injected_errno", schedule == "fault" ? EIO : 0}, {"finish_threw", threw}, {"message", message},
            {"restart_rejected", restart_rejected}};
}

} // namespace

namespace ob {

void note(const char *kind, int expert, int slot, uint64_t generation, uint64_t ticket, int component) {
    if (active.load() || std::strcmp(kind, "worker_enter") == 0) {
        record(kind, {expert, slot, generation, ticket}, component);
    }
}

void worker(int identity) {
    ordinal = identity;
    note("worker_enter");
}

void stage(int expert, uint64_t ticket) {
    service = {expert, -1, 0, ticket};
    note("stage_start", expert, -1, 0, ticket);
}

void primary(int kind, int expert, int slot, uint64_t generation, int component) {
    if (kind == 5) service = {expert, slot, generation, 0};
    const char *label = nullptr;
    switch (kind) {
        case 5: label = "primary_accept"; break;
        case 8: label = "copy_begin"; break;
        case 9: label = "copy_end"; break;
        case 10: label = "primary_publish"; break;
        case 11: label = "barrier_begin"; break;
        case 12: label = "barrier_end"; break;
        default: return;
    }
    note(label, expert, slot, generation, 0, component);
}

} // namespace ob

extern "C" ssize_t __real_pread(int, void *, size_t, off_t);

extern "C" ssize_t __wrap_pread(int fd, void *dst, size_t bytes, off_t offset) {
    if (!active.load() || (fd != primary_fd && fd != stage_fd)) {
        return __real_pread(fd, dst, bytes, offset);
    }
    const bool staged = fd == stage_fd;
    const int k = static_cast<int>(size_t(offset) / region);
    const int expert = service.expert;
    check(k >= 0 && k < 3 && ((staged && expert >= 1 && expert <= 3) || (!staged && expert == 4)),
          "unexpected read identity");
    const size_t align = staged ? stage_align : 4096;
    const size_t logical = size_t(k) * region + size_t(expert) * Stage::slab;
    const size_t head = logical % align;
    check(offset >= 0 && size_t(offset) == logical - head &&
          bytes == (head + Stage::slab + align - 1) / align * align, "unexpected aligned range");
    record(staged ? "stage_read_begin" : "direct_read_begin", service, k);
    {
        std::unique_lock<std::mutex> lock(gate_mutex);
        check(++issued.at(expert).at(k) == 1, "duplicate read");
        if (k == 0) first_read_gate(expert, lock);
    }
    if (schedule == "fault" && staged && expert == 1 && k == 0) {
        record("stage_read_error", service, k);
        errno = EIO;
        return -1;
    }
    const auto result = __real_pread(fd, dst, bytes, offset);
    check(result == ssize_t(bytes), "short/error synthetic positional read");
    {
        std::lock_guard<std::mutex> lock(gate_mutex);
        ++delivered.at(expert).at(k);
    }
    record(staged ? "stage_read_end" : "direct_read_end", service, k);
    return result;
}

int main(int argc, char **argv) {
    check(argc == 5, "expected MODE SCHEDULE SPARSE_INPUT ARM_DIR");
    const std::string mode = argv[1];
    schedule = argv[2];
    const std::string root = argv[4];
    check(mode == "A" || mode == "B", "mode");
    check(schedule == "early" || schedule == "late" || (mode == "B" && fault_case()), "schedule");

    ggml_context_ptr meta(ggml_init({1024 * 1024, nullptr, true}));
    ggml_context_ptr ids_ctx(ggml_init({1024 * 1024, nullptr, false}));
    check(meta && ids_ctx, "metadata contexts");
    auto *ids = ggml_new_tensor_2d(ids_ctx.get(), GGML_TYPE_I32, 4, 1);
    auto *out = ggml_dup_tensor(ids_ctx.get(), ids);
    std::array<std::array<uint64_t, 3>, 36> offsets{};
    for (auto &layer : offsets)
        for (int k = 0; k < 3; ++k) layer[k] = k * region;

    json result = {{"mode", mode}, {"schedule", schedule}, {"destinations", json::array()}};
    {
        llama_moe_stream mgr(36, 40, 4, true);
        mgr.continuations_enabled = mode == "B";
        for (int k = 0; k < 3; ++k) {
            auto *t = ggml_new_tensor_3d(meta.get(), GGML_TYPE_MXFP4, 2880, 2880, 128);
            mgr.create_cache_tensor(2, ggml_backend_cpu_buffer_type(), t, 0, offsets[2][k]);
        }
        mgr.alloc_bufs(false);
        mgr.files.emplace_back(new llama_file(argv[3], "rb", true));
        mgr.prediction_stage = std::make_unique<Stage>(argv[3], offsets);
        auto &stage = *mgr.prediction_stage;
        primary_fd = mgr.files[0]->file_id();
        stage_fd = stage.reader.descriptor();
        stage_align = stage.reader.offset_alignment();
        check(primary_fd != stage_fd && direct(primary_fd) && direct(stage_fd), "O_DIRECT admission");

        auto &layer = *mgr.layer(2);
        auto route = [&](std::array<int32_t, 4> experts) {
            std::memcpy(ids->data, experts.data(), sizeof(experts));
            llama_moe_stream_remap(out, ids, 0, 1, &layer);
        };
        route({8, 9, 10, 11});
        mgr.window.call.store(1);
        mgr.prediction_begin(true);
        active.store(true);
        if (fault_case()) {
            mgr.prediction_request(1, 2, {1, 8, 9, 10});
            wait_arrival(1);
            result["fault"] = exercise_fault(mgr, layer);
        } else {
            mgr.prediction_request(1, 2, {1, 2, 3, 8});
            for (int e : {1, 2, 3}) wait_arrival(e);
            start_clock();
            route({1, 4, 8, 9});
            ob::note("remap_return");
            ob::note("finish_entry");
            mgr.prediction_finish();
            ob::note("finish_return");
            check(mgr.stats.n_calls == 2 && mgr.stats.n_miss == 6 && mgr.stats.n_hit == 2,
                  "native touched populations");
            result["destinations"] = destinations(root, layer, out);
        }

        std::lock_guard<std::mutex> lock(mgr.mtx);
        const auto &s = stage.stats;
        result["counters"] = {{"issued", s.issued}, {"reads", s.reads},
            {"completed_reads", s.completed_reads}, {"expired_running", s.expired_running},
            {"waits", s.waits}, {"consumed", s.consumed}, {"errors", s.errors},
            {"peak_running_spec", s.peak_running_spec}};
        result["terminal"] = {{"idle", stage.idle()}, {"workers", mgr.workers.size()},
            {"queue", mgr.q_demand.size()}, {"pending_continuations", mgr.continuation_count_locked()},
            {"claimed", std::count(layer.slot_claimed.begin(), layer.slot_claimed.end(), 1)},
            {"shutting_down", mgr.shutting_down}, {"load_failed", mgr.load_failed},
            {"direct_primary", direct(primary_fd)}, {"direct_stage", direct(stage_fd)}};
    }
    // The manager destructor has joined every worker before we serialize its journal.
    result["gates"] = json::array();
    for (int e = 1; e <= 4; ++e) {
        const auto &gate = gates.at(e);
        if (gate.arrival == Time{}) continue;
        result["gates"].push_back({{"expert", e}, {"arrival_ns", ns(gate.arrival)},
                                   {"deadline_ns", ns(gate.deadline)}, {"opened_ns", ns(gate.opened)}});
    }
    result["issued_components"] = issued;
    result["delivered_components"] = delivered;
    result["events"] = json::array();
    for (size_t i = 0; i < written; ++i) {
        const auto &v = journal.at(i);
        result["events"].push_back({{"seq", i + 1}, {"ns", ns(v.time)}, {"tid", v.tid},
            {"worker", v.worker}, {"kind", v.kind}, {"component", v.component},
            {"expert", v.job.expert}, {"slot", v.job.slot}, {"generation", v.job.generation},
            {"ticket", v.job.ticket}});
    }
    std::ofstream raw(root + "/raw.json");
    raw << result.dump(2) << std::endl;
    raw.close();
    check(bool(raw), "write raw");
}
