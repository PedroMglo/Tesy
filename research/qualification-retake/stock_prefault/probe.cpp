#include "llama-mmap.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <unistd.h>

constexpr size_t length = 4 * 1024 * 1024;
constexpr size_t page = 4096;
struct Observation {
    int fd, mappings = 0, sequential = 0, willneed = 0, flags = 0;
    void *base = nullptr;
};
static Observation *observing = nullptr;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

extern "C" {
void *__real_mmap(void *, size_t, int, int, int, off_t);
int __real_posix_fadvise(int, off_t, off_t, int);
int __real_posix_madvise(void *, size_t, int);

void *__wrap_mmap(void *address, size_t size, int prot, int flags, int fd, off_t offset) {
    auto *result = __real_mmap(address, size, prot, flags, fd, offset);
    if (observing) {
        require(fd == observing->fd && offset == 0 && size == length && prot == PROT_READ,
                "unexpected mapping");
        observing->mappings++;
        observing->flags = flags;
        observing->base = result;
    }
    return result;
}

int __wrap_posix_fadvise(int fd, off_t from, off_t size, int advice) {
    auto result = __real_posix_fadvise(fd, from, size, advice);
    if (observing) {
        require(fd == observing->fd && from == 0 && size == 0 &&
                advice == POSIX_FADV_SEQUENTIAL && result == 0, "fd advice");
        observing->sequential++;
    }
    return result;
}

int __wrap_posix_madvise(void *address, size_t size, int advice) {
    auto result = __real_posix_madvise(address, size, advice);
    if (observing) {
        require(address == observing->base && size == length &&
                advice == POSIX_MADV_WILLNEED && result == 0, "VMA advice");
        observing->willneed++;
    }
    return result;
}
}

static size_t rss_kib(void *addr) {
    std::ifstream maps("/proc/self/smaps");
    std::string line;
    bool selected = false;
    const auto target = reinterpret_cast<uintptr_t>(addr);
    while (std::getline(maps, line)) {
        unsigned long lo, hi, kib;
        if (std::sscanf(line.c_str(), "%lx-%lx", &lo, &hi) == 2) {
            selected = lo == target && hi - lo == length;
        } else if (selected && std::sscanf(line.c_str(), "Rss: %lu kB", &kib) == 1) {
            return kib;
        }
    }
    throw std::runtime_error("fixture VMA missing");
}

static void arm(llama_file &file, bool prefetch, const std::vector<unsigned char> &expected) {
    Observation obs{file.file_id()};
    observing = &obs;
    llama_mmap view(&file, prefetch ? size_t(-1) : size_t(0), false, {});
    observing = nullptr;
    require(view.size() == length && obs.base == view.addr() && obs.mappings == 1,
            "mapping geometry");
    require(obs.flags == (MAP_SHARED | (prefetch ? MAP_POPULATE : 0)) &&
            obs.sequential == 1 && obs.willneed == static_cast<int>(prefetch), "native advice");
    std::array<unsigned char, length / page> pages{};
    require(mincore(view.addr(), length, pages.data()) == 0, "mincore failure");
    const auto resident = std::count_if(pages.begin(), pages.end(), [](int v) { return v & 1; });
    const auto before = rss_kib(view.addr());
    require(resident == length/page && before == (prefetch ? length/1024 : 0), "residency");
    require(std::memcmp(view.addr(), expected.data(), length) == 0, "mapped bytes differ");
    const auto after = rss_kib(view.addr());
    require(after == length/1024, "incomplete post-read residency");
    std::cout << "{\"prefetch\":" << (prefetch ? "true" : "false")
              << ",\"map_flags\":" << obs.flags << ",\"fadvise_sequential\":" << obs.sequential
              << ",\"madvise_willneed\":" << obs.willneed << ",\"resident_pages\":" << resident
              << ",\"vma_rss_before_kib\":" << before << ",\"vma_rss_after_kib\":" << after
              << ",\"bytes_compared_exact\":" << length << "}\n";
}

int main() {
    try {
        require(sysconf(_SC_PAGESIZE) == page, "page size differs");
        int fd = memfd_create("tesy-prefault-model-free", MFD_CLOEXEC);
        require(fd >= 0, "memfd failure");
        std::vector<unsigned char> expected(length);
        for (size_t i = 0; i < length; ++i) expected[i] = (i * 13 + i / page) % 251;
        FILE *stream = fdopen(fd, "w+b");
        require(stream && fwrite(expected.data(), 1, length, stream) == length &&
                fflush(stream) == 0, "fixture data");
        {
            llama_file file(stream);
            arm(file, true, expected);
            arm(file, false, expected);
        }
        require(fclose(stream) == 0, "close failure");
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << "\n";
        return 1;
    }
}
