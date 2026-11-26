// Private qualification overlay. Callers seal the lifetime/identity of each descriptor.
#pragma once
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <unistd.h>

namespace phase_fd {
struct Record {
    int layer, expert, slot;
    uint64_t gen;
    int fd;
    uint64_t attempts = 0, requested = 0, returned = 0, interrupted = 0, failed = 0;
    uint64_t payload = 0, components = 0, starts = 0, publications = 0, load_errors = 0;
};
inline std::array<Record, 2> records{};
inline thread_local Record *active = nullptr;

// Begin/finish are inside the same manager mutex as the native claim/publication.
// The fixture prebinds the reservation identities to its two different source calls.
inline void begin(int layer, int expert, int slot, uint64_t gen) {
    if (active) std::abort();
    for (auto &r : records) {
        if (r.layer == layer && r.expert == expert && r.slot == slot && r.gen == gen) {
            if (++r.starts != 1) std::abort();
            active = &r;
            return;
        }
    }
    std::abort();
}

inline ssize_t read(int fd, void *p, size_t bytes, off_t offset) {
    auto result = ::pread(fd, p, bytes, offset);
    const int saved = errno;
    if (active && fd == active->fd) {
        ++active->attempts;
        active->requested += bytes;
        if (result > 0) active->returned += static_cast<uint64_t>(result);
        if (result < 0 && saved == EINTR) ++active->interrupted;
        if (result < 0 && saved != EINTR) ++active->failed;
    }
    errno = saved;
    return result;
}

inline void set_return(size_t payload) {
    if (!active) std::abort();
    active->payload += payload;
    ++active->components;
}

inline void finish(bool ok) {
    if (!active) std::abort();
    if (ok) ++active->publications;
    else ++active->load_errors;
    active = nullptr;
}
} // namespace phase_fd
