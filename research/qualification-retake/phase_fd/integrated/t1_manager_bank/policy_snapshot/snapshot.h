// Included only by the private two-TU PFJ1 build. The manager and PFJ1 ABI stay unchanged.
#pragma once

#include "llama-moe-stream.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <fcntl.h>
#include <memory>
#include <stdexcept>
#include <unistd.h>

namespace pfj __attribute__((visibility("hidden"))) {
namespace policy {
constexpr int layers = 36, slots = 40, experts = 128;
enum Status : int64_t { missing, complete, pending, duplicate, invalid };

struct Header {
    char magic[8] = {'T', 'P', 'O', 'L', 'I', 'C', 'Y', '1'};
    int64_t status = missing, matches = 0, call = 0, n = 0, first = 0, last = 0;
    int64_t calls = 0, interval = 0, workers = 0, n_layers = 0, n_slots = 0, n_experts = 0;
    int64_t queued = 0, claimed = 0, loading = 0;
};
struct Layer {
    int64_t clock = 0;
    std::array<int64_t, slots> age{};
    std::array<int64_t, experts> heat{};
};
static_assert(sizeof(Header) == 128 && sizeof(Layer) == 169 * 8);
static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);

struct Capture {
    int fd = -1;
    Header header;
    std::array<Layer, layers> data;
    ~Capture() {
        if (fd >= 0) ::close(fd);
    }
};
inline std::unique_ptr<Capture> observation;

inline void install() {
    const char *path = std::getenv("TESY_PFJ_POLICY_SNAPSHOT");
    if (!path) return;
    if (*path != '/' || observation) throw std::runtime_error("invalid policy snapshot profile");
    auto c = std::make_unique<Capture>();
    c->fd = ::open(path, O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC | O_WRONLY, 0600);
    if (c->fd < 0) throw std::runtime_error("new policy snapshot required");
    observation = std::move(c);
}

// Called immediately after the target ENTER while the native manager holds its mutex.
inline void capture_locked(const llama_moe_stream &mgr, int call, int n, int first, int last) {
    if (!observation || n != 5 || first != 2044 || last != 2048) return;
    auto &h = observation->header;
    if (++h.matches != 1) {
        h.status = duplicate;
        return;
    }
    h.call = call;
    h.n = n;
    h.first = first;
    h.last = last;
    h.calls = mgr.stats.n_calls;
    h.interval = mgr.hot_decay_interval;
    h.workers = mgr.n_io_threads;
    h.n_layers = mgr.layers.size();
    h.n_slots = mgr.n_slots;
    h.n_experts = experts;
    h.queued = mgr.q_demand.size();
    h.status = invalid;
    if (h.n_layers != layers || h.n_slots != slots || h.workers != 4 || h.calls < 0 ||
        h.interval < 0 || mgr.load_failed || mgr.shutting_down) return;
    for (int i = 0; i < layers; ++i) {
        const auto *sl = mgr.layer(i);
        if (!sl || sl->il != i || sl->n_expert != experts || sl->n_slots != slots ||
            sl->slot_last_use.size() != slots || sl->slot_state.size() != slots ||
            sl->slot_claimed.size() != slots || sl->route_hotness.size() != experts ||
            sl->use_counter < 0) return;
        for (int s = 0; s < slots; ++s) {
            if (sl->slot_claimed[s] > 1 || sl->slot_state[s] > LLAMA_MOE_STREAM_SLOT_RESIDENT ||
                (sl->slot_claimed[s] && sl->slot_state[s] != LLAMA_MOE_STREAM_SLOT_LOADING) ||
                sl->slot_last_use[s] < 0 || sl->slot_last_use[s] > sl->use_counter) return;
            h.claimed += sl->slot_claimed[s];
            h.loading += sl->slot_state[s] == LLAMA_MOE_STREAM_SLOT_LOADING;
        }
        auto &out = observation->data[i];
        out.clock = sl->use_counter;
        std::copy(sl->slot_last_use.begin(), sl->slot_last_use.end(), out.age.begin());
        std::copy(sl->route_hotness.begin(), sl->route_hotness.end(), out.heat.begin());
    }
    h.status = h.queued || h.claimed || h.loading ? pending : complete;
}

inline void write_all(int fd, const void *src, size_t count) {
    const auto *p = static_cast<const uint8_t *>(src);
    while (count) {
        const auto n = ::write(fd, p, count);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) throw std::runtime_error("policy snapshot write");
        count -= n;
        p += n;
    }
}
inline void finish() {
    if (!observation) return;
    auto c = std::move(observation);
    write_all(c->fd, &c->header, sizeof(c->header));
    if (c->header.status == complete) write_all(c->fd, c->data.data(), sizeof(c->data));
    if (::fdatasync(c->fd) != 0) throw std::runtime_error("policy snapshot flush");
    const int fd = c->fd;
    c->fd = -1;
    if (::close(fd) != 0) throw std::runtime_error("policy snapshot close");
}
} // namespace policy
} // namespace pfj
