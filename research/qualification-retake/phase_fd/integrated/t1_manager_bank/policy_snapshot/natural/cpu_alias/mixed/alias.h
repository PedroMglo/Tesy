#include <fcntl.h>
#include <memory>
#include <unistd.h>
#include <sys/stat.h>

namespace fs = std::filesystem;
static void need(bool ok, const char *message) { check(ok, message); }
#include "mapped.inc"

// The wrapper has no ggml-owned allocation. The graph and wrapper die before this owner.
class AliasArena {
    size_t length;
    uint8_t *reservation;
    int fd;
    unsigned generation = 1;

    void bind(unsigned which) {
        void *slot = base() + (slots - 1) * stride;
        check(mmap(slot, stride, PROT_READ, MAP_SHARED | MAP_FIXED, fd,
                   static_cast<off_t>(which) * stride) == slot, "bind retained CPU window");
    }

    void prepare(int index, int tag) {
        void *p = mmap(nullptr, stride, PROT_READ | PROT_WRITE, MAP_SHARED, fd, index * stride);
        check(p != MAP_FAILED, "stage expert generation");
        for (int k = 0; k < 3; ++k) fill(static_cast<uint8_t *>(p) + k * slab, k, tag);
        check(munmap(p, stride) == 0, "release setup mapping");
    }

public:
    explicit AliasArena(size_t capacity) : length((capacity + page - 1) / page * page + 2 * page) {
        check(sysconf(_SC_PAGESIZE) == page, "native page size");
        reservation = static_cast<uint8_t *>(mmap(nullptr, length, PROT_NONE,
                                                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
        check(reservation != MAP_FAILED &&
              mprotect(base(), length - 2 * page, PROT_READ | PROT_WRITE) == 0,
              "own guarded 40-slot VA");
        fd = memfd_create("tesy-ggml-alias", MFD_CLOEXEC | MFD_ALLOW_SEALING);
        check(fd >= 0 && ftruncate(fd, 2 * stride) == 0, "backing for exactly two generations");
        prepare(0, 39);
        prepare(1, 38);
        int seals = F_SEAL_WRITE | F_SEAL_SHRINK | F_SEAL_GROW | F_SEAL_SEAL;
        check(fcntl(fd, F_ADD_SEALS, seals) == 0 && fcntl(fd, F_GET_SEALS) == seals,
              "seal both immutable generation payloads");
        bind(0);
    }

    ~AliasArena() {
        munmap(reservation, length);
        close(fd);
    }
    AliasArena(const AliasArena &) = delete;
    AliasArena &operator=(const AliasArena &) = delete;
    uint8_t *base() const { return reservation + page; }

    bool rebind(unsigned expected, unsigned next, unsigned backing) {
        if (expected != generation || next != generation + 1 || backing > 1) return false;
        bind(backing);
        generation = next;
        return true;
    }
};
