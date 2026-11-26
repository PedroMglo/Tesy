// No tensor reads: use only VMA metadata, including logical offsets beyond 4 GiB.
#include "inspect.hpp"
#include <sys/sysmacros.h>
#include <functional>
#include <iostream>

using ik_vma::Inspect;
namespace fs = std::filesystem;

static void need(bool ok, const char *label) {
    if (!ok) throw std::runtime_error(label);
}

static void rejects(const std::function<void()> &test, const std::string &reason) {
    try {
        test();
    } catch (const std::runtime_error &e) {
        if (std::string(e.what()).find(reason) != std::string::npos) return;
        throw;
    }
    throw std::runtime_error("accepted negative " + reason);
}

int main(int argc, char **argv) try {
    need(argc == 2 || argc == 3, "new fixture directory [existing non-model regular file]");
    const fs::path root(argv[1]);
    need(fs::create_directory(root), "output exists");
    const auto p = root / "sparse weights with spaces", alias = root / "alias";
    int fd = open(p.c_str(), O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
    const size_t page = sysconf(_SC_PAGESIZE);
    const uint64_t high = UINT64_C(1) << 32, len = high + 8 * page;
    need(fd >= 0 && ftruncate(fd, len) == 0, "sparse file");
    fs::create_symlink(p.filename(), alias);
    struct stat id{};
    need(fstat(fd, &id) == 0 && id.st_blocks == 0, "sparse identity");
    void *map = mmap(nullptr, len, PROT_READ, MAP_SHARED, fd, 0);
    need(map != MAP_FAILED, "file mmap");
    const auto base = reinterpret_cast<uintptr_t>(map);
    const auto start = base + high + 47, mid = base + high + page;
    const size_t bytes = 2 * page;
    const auto offset = [&](const Inspect &obs) { return obs.offset("gate", base, len, start, bytes); };
    const auto check = [&]() { return Inspect::capture(alias.c_str(), id); };
    need(offset(check()) == high + 47, "large file offset");
    need(madvise(reinterpret_cast<void *>(mid), page, MADV_DONTNEED) == 0, "DONTNEED");
    need(offset(check()) == high + 47, "following DONTNEED");
    // RANDOM creates a VMA split on Linux without changing read permissions or file offset.
    need(madvise(reinterpret_cast<void *>(mid), page, MADV_RANDOM) == 0, "RANDOM");
    auto split = check();
    need(ik_vma::cover(split.maps,start).end == mid && offset(split) == high+47, "contiguous split");

    const auto other = root / "another inode";
    int foreign = open(other.c_str(), O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
    need(foreign >= 0 && ftruncate(foreign, len) == 0, "foreign file");
    rejects([&]() { Inspect::capture(other.c_str(), id); }, "FD identity");
    auto bad = split;
    ++bad.key.minor;
    rejects([&]() { offset(bad); }, "map device");
    bad = split;
    bad.key.path += ".changed";
    rejects([&]() { offset(bad); }, "map pathname");

    auto replace = [&](int src, off_t off, int prot, int flags) {
        auto *where = reinterpret_cast<void *>(mid);
        need(mmap(where, page, prot, flags | MAP_FIXED, src, off) == where, "owned interval remap");
    };
    replace(foreign, high+page, PROT_READ, MAP_SHARED);
    rejects([&]() { offset(check()); }, "map inode");
    replace(fd, high+page, PROT_READ | PROT_WRITE, MAP_SHARED);
    rejects([&]() { offset(check()); }, "permissions");
    replace(-1, 0, PROT_READ, MAP_ANONYMOUS | MAP_PRIVATE);
    rejects([&]() { offset(check()); }, "permissions");
    replace(fd, high+2*page, PROT_READ, MAP_SHARED);
    rejects([&]() { offset(check()); }, "file offset");
    need(munmap(reinterpret_cast<void *>(mid), page) == 0, "punch gap");
    rejects([&]() { offset(check()); }, "gap");
    need(munmap(map, len) == 0 && close(foreign) == 0 && close(fd) == 0, "cleanup");
    fs::remove(other); fs::remove(alias); fs::remove(p);
    std::cout << "PASS_SPARSE_VMA large_offset=" << high+47 << " negative_cases=8\n";

    if (argc == 3) {
        struct stat live{};
        need(stat(argv[2], &live) == 0, "non-model witness stat");
        auto obs = Inspect::capture(argv[2], live);
        bool remains = false;
        for (auto &v: ik_vma::read_maps())
            if (v.path == obs.key.path && v.begin == obs.key.begin) remains = true;
        need(!remains, "passive witness survived capture");
        std::cout << "PASS_NON_MODEL_FD map_dev=" << obs.key.major << ":" << obs.key.minor
                  << " inode_equal=" << (obs.key.inode == live.st_ino)
                  << " stat_dev=" << major(live.st_dev) << ":" << minor(live.st_dev) << "\n";
    }
    return 0;
} catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
}
