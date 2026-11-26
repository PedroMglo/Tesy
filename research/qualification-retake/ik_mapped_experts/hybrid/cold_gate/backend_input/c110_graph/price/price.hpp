#pragma once

#include <algorithm>
#include <array>
#include <chrono>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace input_price {
using Clock = std::chrono::steady_clock;

struct Transfer {
    int phase, layer;
    unsigned generation;
    int64_t file;
    size_t dest, bytes;
    std::array<char,GGML_MAX_NAME> name;
};
struct Site {
    int phase;
    size_t count;
    std::array<int32_t,64> ranks;
};
static std::array<Transfer,4096> transfers{};
static std::array<Site,72> sites{};
static size_t n_transfers{}, n_sites{};
static std::array<int64_t,2> forward_ns{};
static int64_t cleanup_ns{};

static int64_t ns_since(Clock::time_point start) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count();
}
static void record_set(int phase, unsigned generation, int layer, const char *name,
                       int64_t file, size_t dest, size_t bytes) {
    must(n_transfers < transfers.size() && generation == n_sites, "unexpected C110 SET");
    auto &t = transfers[n_transfers++];
    const auto len = std::strlen(name);
    must(len < t.name.size(), "destination name");
    t.phase = phase;
    t.generation = generation;
    t.layer = layer;
    t.file = file;
    t.dest = dest;
    t.bytes = bytes;
    std::memcpy(t.name.data(),name,len+1);
}
static void record_ranks(int phase, const int32_t *ids, size_t count) {
    must(n_sites < sites.size() && count <= sites.front().ranks.size(), "C110 ID capacity");
    auto &s = sites[n_sites++];
    s.phase = phase;
    s.count = count;
    std::copy_n(ids,count,s.ranks.begin());
}
static void cold_file(int fd, size_t bytes) {
    const auto page = sysconf(_SC_PAGESIZE);
    struct stat s{};
    must(page == 4096 && fstat(fd,&s) == 0 && uint64_t(s.st_size) == bytes &&
         s.st_dev == file_id.st_dev && s.st_ino == file_id.st_ino, "cold GGUF identity");
    must(posix_fadvise(fd,0,0,POSIX_FADV_DONTNEED) == 0, "evict GGUF");
    void *map = mmap(nullptr,bytes,PROT_READ,MAP_SHARED,fd,0);
    must(map != MAP_FAILED, "residency map");
    std::vector<unsigned char> state((bytes+page-1)/page);
    const int inspected = mincore(map,bytes,state.data());
    const int released = munmap(map,bytes);
    must(inspected == 0 && released == 0, "residency observation");
    size_t resident = 0, first = state.size();
    for (size_t i=0; i<state.size(); ++i) {
        if (state[i]&1) {
            if (!resident) first=i;
            ++resident;
        }
    }
    std::printf("COLD_GGUF %zu %zu %zu\n",state.size(),resident,first);
    std::fflush(stdout);
    must(resident == 0, "nonempty GGUF page cache before load");
}
static void save(const fs::path &dir) {
    must(n_transfers > 0 && n_sites == sites.size() && forward_ns[0] > 0 &&
         forward_ns[1] > 0 && cleanup_ns > 0, "missing cost boundary");
    std::ofstream out(dir/"service.tsv");
    for (size_t i=0; i<n_transfers; ++i) {
        const auto &t = transfers[i];
        out << "SET " << t.phase << ' ' << t.generation << ' ' << t.layer << ' ' << t.name.data()
            << ' ' << t.file << ' ' << t.dest << ' ' << t.bytes << '\n';
    }
    for (size_t i=0; i<n_sites; ++i) {
        const auto &s = sites[i];
        out << "IDS " << s.phase << ' ' << i+1;
        for (size_t j=0; j<s.count; ++j) out << ' ' << s.ranks[j];
        out << '\n';
    }
    out.close();
    must(bool(out), "write after timed phases");
    std::printf("GRAPH_NS %lld %lld %lld\n", (long long)forward_ns[0],
                (long long)forward_ns[1],(long long)cleanup_ns);
}
} // namespace input_price
