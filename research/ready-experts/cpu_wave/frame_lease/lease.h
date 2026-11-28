// Four producers compete with one genuine GGML consumer for a recorded CPU generation.
#pragma once
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <thread>

using Clock = std::chrono::steady_clock;
static int64_t now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
}

struct FrameGeneration {
    int generation = 1;
    unsigned pins = 0;
    bool pending = false;
    bool pin(int g) {
        if (g != generation || pending) return false;
        ++pins;
        return true;
    }
    bool release(int g) {
        if (g != generation || !pins) return false;
        --pins;
        return true;
    }
    bool reserve(int g) {
        if (g != generation || pending) return false;
        pending = true;
        return true;
    }
    bool publish(int g) {
        if (g != generation || !pending || pins) return false;
        pending = false;
        ++generation;
        return true;
    }
};

static void check_generations() {
    FrameGeneration frame;
    need(frame.pin(1) && frame.pin(1) && frame.reserve(1), "pin and reserve");
    need(!frame.reserve(1) && !frame.pin(1) && !frame.release(2) && !frame.publish(1), "stale/pinned");
    need(frame.release(1) && !frame.publish(1) && frame.release(1) && !frame.release(1), "last reader");
    need(!frame.publish(2) && frame.publish(1) && !frame.pin(1) && frame.pin(2), "generation handoff");
}

struct Transfer {
    FrameGeneration frame;
    int64_t claim = 0, writable = 0, published = 0;
    bool blocked = false;
};

class Replacements {
public:
    Replacements(unsigned char *pool, size_t pitch, int victim, std::string arm, bool audit)
        : data(pool), stride(pitch), contested(victim), role(std::move(arm)), exact(audit) {
        for (int k = 0; k < 4; ++k) workers[k] = std::thread([this,k] { work(k); });
        std::unique_lock lock(mutex);
        change.wait(lock, [this] { return ready == 4; });
    }

    // Publish the IDs only once the consumer owns its generation.
    void launch() {
        std::lock_guard lock(mutex);
        need(!started, "duplicate wave launch");
        if (direct()) need(jobs[0].frame.pin(1), "consumer lease");
        started = true;
        change.notify_all();
    }

    bool direct() const { return role != "COPY40" && role != "COPY1252"; }

    void before_down() {
        std::unique_lock lock(mutex);
        if (exact) {
            change.wait(lock, [this] {
                return jobs[0].claim && jobs[1].published && jobs[2].published && jobs[3].published;
            });
            if (direct()) need(jobs[0].blocked && !jobs[0].published, "protected delayed consumer");
        }
        before = now_ns();
        if (role == "EARLY") {
            unlock_frame();
            change.wait(lock, [this] { return jobs[0].published != 0; });
        }
    }

    void after_down() {
        std::lock_guard lock(mutex);
        last = now_ns();
        if (role == "LAST") unlock_frame();
    }

    void drain_graph() {
        std::lock_guard lock(mutex);
        graph_done = now_ns();
        if (role == "DRAIN") unlock_frame();
    }

    json finish(int64_t origin) {
        for (auto &worker : workers) worker.join();
        const int64_t end = now_ns();
        json rows = json::array();
        for (auto &j : jobs) {
            need(j.frame.generation == 2 && !j.frame.pending && !j.frame.pins &&
                 origin <= j.claim && j.claim <= j.writable && j.writable <= j.published &&
                 j.published <= end, "worker drain/publication");
            rows.push_back({{"claim_ns",j.claim-origin},{"writable_ns",j.writable-origin},
                            {"published_ns",j.published-origin},{"blocked",j.blocked}});
        }
        need(origin <= before && before <= last && last <= graph_done && graph_done <= end,
             "native consumer clock");
        return {{"workers",rows},{"before_down_ns",before-origin},{"down_done_ns",last-origin},
                {"release_ns",released ? released-origin : 0},{"graph_ns",graph_done-origin},
                {"drained_ns",end-origin}};
    }

private:
    unsigned char *data;
    size_t stride;
    int contested;
    std::string role;
    bool exact, started = false;
    int ready = 0;
    int64_t before = 0, last = 0, graph_done = 0, released = 0;
    std::array<Transfer,4> jobs{};
    std::array<std::thread,4> workers;
    std::mutex mutex;
    std::condition_variable change;

    void unlock_frame() {
        need(jobs[0].frame.release(1) && !released, "release wrong reader generation");
        released = now_ns();
        change.notify_all();
    }

    void work(int k) {
        std::unique_lock lock(mutex);
        ++ready;
        change.notify_all();
        change.wait(lock, [this] { return started; });
        auto &j = jobs[k];
        need(j.frame.reserve(1), "incoming generation");
        j.claim = now_ns();
        j.blocked = j.frame.pins != 0;
        change.notify_all();
        change.wait(lock, [&j] { return j.frame.pins == 0; });
        j.writable = now_ns();
        lock.unlock();
        const int dest = k == 0 ? contested : 970 + k;
        std::memcpy(data + dest*stride, data + (980+k)*stride, stride);
        lock.lock();
        need(j.frame.publish(1), "duplicate or stale writer");
        j.published = now_ns();
        change.notify_all();
    }
};
