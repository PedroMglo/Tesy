// Linux /proc/self/maps and stat need not expose the same device for Btrfs.
#pragma once
#include <algorithm>
#include <cerrno>
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace ik_vma {

struct Region {
    uintptr_t begin{}, end{};
    uint64_t offset{}, inode{};
    unsigned major{}, minor{};
    std::string perms, path;
};

inline std::vector<Region> read_maps() {
    std::ifstream maps("/proc/self/maps");
    if (!maps) throw std::runtime_error("VMA maps unavailable");
    std::vector<Region> result;
    std::string line;
    while (std::getline(maps, line)) {
        Region v;
        char perms[5]{};
        int consumed = 0;
        if (std::sscanf(line.c_str(), "%" SCNxPTR "-%" SCNxPTR " %4s %" SCNx64
                        " %x:%x %" SCNu64 "%n", &v.begin, &v.end, perms, &v.offset,
                        &v.major, &v.minor, &v.inode, &consumed) != 7 || v.end <= v.begin)
            throw std::runtime_error("VMA malformed maps");
        v.perms = perms;
        const auto first = line.find_first_not_of(" \t", consumed);
        if (first != std::string::npos) v.path = line.substr(first);
        result.push_back(std::move(v));
    }
    if (!maps.eof()) throw std::runtime_error("VMA maps read failed");
    return result;
}

inline const Region &cover(const std::vector<Region> &maps, uintptr_t cursor) {
    auto it = std::lower_bound(maps.begin(), maps.end(), cursor,
                               [](const Region &v, uintptr_t at) { return v.end <= at; });
    if (it == maps.end() || it->begin > cursor) throw std::runtime_error("VMA gap");
    return *it;
}

struct Inspect {
    Region key;
    std::vector<Region> maps;

    static Inspect capture(const char *path, const struct stat &id) {
        const auto canonical = std::filesystem::canonical(path).string();
        const int fd = open(canonical.c_str(), O_RDONLY | O_CLOEXEC);
        if (fd < 0) throw std::runtime_error("VMA witness open");
        struct stat now{};
        const long page = sysconf(_SC_PAGESIZE);
        if (page <= 0 || fstat(fd, &now) || !S_ISREG(now.st_mode) || now.st_size < page ||
            now.st_dev != id.st_dev || now.st_ino != id.st_ino || now.st_size != id.st_size ||
            now.st_mtim.tv_sec != id.st_mtim.tv_sec || now.st_mtim.tv_nsec != id.st_mtim.tv_nsec ||
            now.st_ctim.tv_sec != id.st_ctim.tv_sec || now.st_ctim.tv_nsec != id.st_ctim.tv_nsec) {
            close(fd);
            throw std::runtime_error("VMA witness FD identity");
        }
        void *addr = mmap(nullptr, page, PROT_READ, MAP_SHARED, fd, 0);
        close(fd);
        if (addr == MAP_FAILED) throw std::runtime_error("VMA witness mmap");
        Inspect obs;
        try {
            uintptr_t start = reinterpret_cast<uintptr_t>(addr);
            obs.key = cover(read_maps(), start);
            const auto &v = obs.key;
            if (v.begin != start || v.end - start < static_cast<uintptr_t>(page) || v.offset != 0 ||
                v.perms != "r--s" || v.inode != id.st_ino || v.path != canonical)
                throw std::runtime_error("VMA witness identity, permissions or offset");
        } catch (...) {
            munmap(addr, page);
            throw;
        }
        if (munmap(addr, page)) throw std::runtime_error("VMA witness munmap");
        // A temporary map could occupy a hole in a damaged tensor. Check after release.
        obs.maps = read_maps();
        return obs;
    }

    uint64_t offset(const std::string &name, uintptr_t base, size_t size,
                    uintptr_t start, size_t bytes) const {
        const auto failure = [&](const char *why, const Region &v, uintptr_t cursor) {
            char details[400];
            std::snprintf(details, sizeof(details),
                          "VMA %s %s, tensor=%" PRIxPTR "+%zu cursor=%" PRIxPTR
                          " region=%" PRIxPTR "-%" PRIxPTR " %s off=%" PRIu64
                          " dev=%x:%x ino=%" PRIu64 " expected_dev=%x:%x ino=%" PRIu64,
                          name.c_str(), why, start, bytes, cursor, v.begin, v.end, v.perms.c_str(),
                          v.offset, v.major, v.minor, v.inode, key.major, key.minor, key.inode);
            return std::runtime_error(details);
        };
        if (!base || !bytes || start < base || start - base > size ||
            bytes > size - (start - base) || bytes > UINTPTR_MAX - start)
            throw std::runtime_error("VMA tensor outside intercepted model map: " + name);
        const uintptr_t stop = start + bytes;
        for (uintptr_t cursor = start; cursor < stop;) {
            const auto &v = cover(maps, cursor);
            if (v.perms != "r--s") throw failure("permissions", v, cursor);
            if (v.major != key.major || v.minor != key.minor) throw failure("map device", v, cursor);
            if (v.inode != key.inode) throw failure("map inode", v, cursor);
            if (v.path != key.path) throw failure("map pathname", v, cursor);
            const uint64_t expected = cursor - base;
            if (v.offset > expected || cursor - v.begin != expected - v.offset)
                throw failure("file offset", v, cursor);
            cursor = std::min(stop, v.end);
        }
        return start - base;
    }
};

} // namespace ik_vma
