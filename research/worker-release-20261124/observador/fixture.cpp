// Model-free observer fixture. The ticket machine is the C317-pinned C305 header.
#define TESY_C305_STAGE_TESTING
#include "c305-cpu-stage.h"

#include <condition_variable>
#include <deque>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sys/syscall.h>
#include <thread>
#include <vector>

using component = std::array<unsigned char, 64>;
using payload = std::array<component, 3>;
using clock_type = std::chrono::steady_clock;
static_assert(clock_type::is_steady);
constexpr int blocked = 3, direct = 4, controller = -1;

struct event {
    uint64_t sequence;
    int64_t ns;
    int worker;
    long tid;
    const char *kind;
    int job, component, slot, generation;
    uint64_t ticket;
};

struct observer {
    bool on, overflow = false;
    size_t capacity;
    const clock_type::time_point origin = clock_type::now();
    std::array<event, 256> events{};
    size_t count = 0;

    observer(bool enabled, size_t limit) : on(enabled), capacity(limit) {}
    void record(int worker, const char *kind, int job, int k, int slot, int gen, uint64_t ticket) {
        if (!on) return;
        if (count >= capacity) { overflow = true; return; }
        const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
            clock_type::now() - origin).count();
        static thread_local const long tid = syscall(SYS_gettid);
        events[count] = {count + 1, ns, worker, tid, kind, job, k, slot, gen, ticket};
        ++count;
    }
};

struct fixture {
    observer obs;
    c305_cpu_stage stage;
    std::mutex mutex;
    std::condition_variable cv;
    std::vector<std::thread> workers;
    std::deque<int> demands;
    std::array<uint64_t, 3> tickets{};
    std::array<int, 3> entries{};
    std::array<payload, 5> source{};
    std::array<payload, 3> staged_bytes{};
    std::array<payload, 2> destination{};
    std::array<bool, 5> allow{};
    std::array<bool, 2> published{};
    std::array<int, 5> read_components{}, copy_components{};
    bool stopping = false, waiting = false, direct_started = false;
    int started = 0, completed = 0;

    fixture(bool enabled, size_t capacity) : obs(enabled, capacity) {
        for (size_t job = 0; job < source.size(); ++job) {
            for (size_t k = 0; k < 3; ++k) {
                for (size_t b = 0; b < 64; ++b) {
                    source[job][k][b] = static_cast<unsigned char>(19 + 47*job + 13*k + 7*b);
                }
            }
        }
    }

    // Called only with mutex held. Primary jobs have fixed destination generations.
    void stamp(int worker, const char *kind, int job = -1, int k = -1) {
        const int slot = job == blocked ? 11 : job == direct ? 17 : -1;
        const int gen = job == blocked ? 2 : job == direct ? 3 : 0;
        const auto ticket = job == blocked ? tickets[0] : job >= 0 && job < 3 ? tickets[job] : 0;
        obs.record(worker, kind, job, k, slot, gen, ticket);
    }

    void transfer(std::unique_lock<std::mutex> &lock, int worker, int job, int k,
                  bool read, const component &from, component &to) {
        stamp(worker, read ? "read_begin" : "copy_begin", job, k);
        if (read && k == 0) {
            if (job == direct) { direct_started = true; cv.notify_all(); }
            cv.wait(lock, [&] { return allow[job]; });
        }
        lock.unlock();
        std::copy(from.begin(), from.end(), to.begin());
        lock.lock();
        (read ? read_components : copy_components)[job]++;
        stamp(worker, read ? "read_end" : "copy_end", job, k);
    }

    void producer(std::unique_lock<std::mutex> &lock, int worker, int index) {
        const int job = stage.entries.at(index).expert - 1;
        c305_cpu_stage::require(job >= 0 && job < 3, "forecast outside fixture");
        auto ticket = stage.start(index);
        stamp(worker, "dispatch", job);
        ++started;
        cv.notify_all();
        for (int k = 0; k < 3; ++k)
            transfer(lock, worker, job, k, true, source[job][k], staged_bytes[job][k]);
        stage.complete(index, ticket, true);
        stamp(worker, "producer_done", job);
        ++completed;
        cv.notify_all();
    }

    void demand(std::unique_lock<std::mutex> &lock, int worker, int job) {
        stamp(worker, "dispatch", job);
        if (job == blocked) {
            const int entry = stage.find(1, 2, 1);
            c305_cpu_stage::require(entry == entries[0] && stage.demand(entry, tickets[0]) &&
                                   stage.entries[entry].status == c305_cpu_stage::READING,
                                   "expected attached READING ticket");
            stamp(worker, "attach", job);
            ++stage.stats.waits;  // Owned by worker_loop in the original manager.
            waiting = true;
            cv.notify_all();
            stamp(worker, "demand_park", job);
            cv.wait(lock, [&] { return stage.entries[entry].status != c305_cpu_stage::READING; });
            stamp(worker, "demand_resume", job);
            stage.claim(entry, tickets[0]);
            stamp(worker, "claim", job);
            for (int k = 0; k < 3; ++k)
                transfer(lock, worker, job, k, false, staged_bytes[0][k], destination[0][k]);
            stage.release(entry, tickets[0]);
            stamp(worker, "release", job);
        } else {
            c305_cpu_stage::require(stage.find(1, 2, 4) < 0, "direct path unexpectedly staged");
            component scratch{};
            for (int k = 0; k < 3; ++k) {
                transfer(lock, worker, job, k, true, source[job][k], scratch);
                transfer(lock, worker, job, k, false, scratch, destination[1][k]);
            }
        }
        published[job - blocked] = true;
        stamp(worker, "publish", job);
        cv.notify_all();
    }

    void worker_loop(int id) {
        std::unique_lock<std::mutex> lock(mutex);
        stamp(id, "worker_enter");
        while (!stopping) {
            if (demands.empty() && stage.next() < 0) {
                stamp(id, "idle_wait");
                cv.wait(lock, [&] { return stopping || !demands.empty() || stage.next() >= 0; });
                stamp(id, "idle_resume");
            }
            if (stopping) break;
            if (demands.empty()) {
                producer(lock, id, stage.next());
            } else {
                const int job = demands.front();
                demands.pop_front();
                demand(lock, id, job);
            }
        }
        stamp(id, "worker_exit");
    }

    void open_service(int job) {
        stamp(controller, "gate_open", job, 0);
        allow[job] = true;
        cv.notify_all();
    }

    void run() {
        stage.begin(true);
        for (int id = 0; id < 4; ++id)
            workers.emplace_back([this, id] { worker_loop(id); });
        std::unique_lock<std::mutex> lock(mutex);
        for (int job = 0; job < 3; ++job) {
            entries[job] = stage.request(1, 2, job + 1);
            tickets[job] = stage.entries.at(entries[job]).ticket;
            stamp(controller, "enqueue", job);
        }
        cv.notify_all();
        cv.wait(lock, [&] { return started == 3; });
        const int32_t route[] = {1, 4, 8, 9};
        stage.expire(1, 2, route, 4);
        stamp(controller, "cancel", 1);
        stamp(controller, "cancel", 2);
        demands = {blocked, direct};
        stamp(controller, "enqueue", blocked);
        stamp(controller, "enqueue", direct);
        stamp(controller, "barrier_begin");
        cv.notify_all();
        cv.wait(lock, [&] { return waiting; });
        open_service(1);
        cv.wait(lock, [&] { return direct_started; });
        open_service(0);
        open_service(2);
        cv.wait(lock, [&] { return published[0] && completed == 3; });
        open_service(direct);
        cv.wait(lock, [&] { return published[1]; });
        stamp(controller, "barrier_end");
        stamp(controller, "drain_begin");
        stage.finish();
        c305_cpu_stage::require(stage.idle() && demands.empty(), "unfinished service");
        stopping = true;
        cv.notify_all();
        lock.unlock();
        for (auto &t : workers) t.join();
        lock.lock();
        stamp(controller, "drain_end");
    }

    void write() const {
        std::cout << "metrics " << obs.count << " " << obs.overflow << " " << stage.stats.issued
            << " " << stage.stats.completed_reads << " " << stage.stats.expired_running
            << " " << stage.stats.consumed << " " << stage.stats.waits << " " << stage.idle()
            << " " << stage.stats.errors << "\n";
        for (int i = 0; i < 5; ++i)
            std::cout << "work " << i << " " << read_components[i] << " " << copy_components[i] << "\n";
        for (int i = 0; i < 2; ++i) {
            std::cout << "dest " << (i ? 17 : 11) << " " << (i ? 3 : 2) << " ";
            for (const auto &c : destination[i])
                for (auto b : c) std::cout << std::hex << std::setw(2) << std::setfill('0') << +b;
            std::cout << std::dec << "\n";
        }
        for (size_t i = 0; i < obs.count; ++i) {
            const auto &e = obs.events[i];
            std::cout << "event " << e.sequence << " " << e.ns << " " << e.worker << " " << e.tid
                << " " << e.kind << " " << e.job << " " << e.component << " " << e.slot << " "
                << e.generation << " " << e.ticket << "\n";
        }
    }
};

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    const std::string mode = argv[1];
    if (mode != "on" && mode != "off" && mode != "overflow") return 2;
    auto harness = std::make_unique<fixture>(mode != "off", mode == "overflow" ? 1 : 256);
    harness->run();
    harness->write();
}
