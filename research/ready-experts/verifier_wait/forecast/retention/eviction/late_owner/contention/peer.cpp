// Price the three unchanged reads while the fourth lane remains occupied.
#include <array>
#include <barrier>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <openssl/sha.h>
#include <set>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <time.h>
#include <unistd.h>
#include <vector>

constexpr size_t slab = 4406400, stride = 13221888;
using Tick = int64_t;
using Identity = std::array<int64_t, 5>;

void require(bool ok, const char *what) {
    if (!ok) {
        std::fprintf(stderr, "%s\n", what);
        std::_Exit(2);
    }
}

Tick ns(timespec t) { return static_cast<Tick>(t.tv_sec) * 1000000000 + t.tv_nsec; }
Tick now() {
    timespec t{};
    require(clock_gettime(CLOCK_MONOTONIC_RAW, &t) == 0, "clock");
    return ns(t);
}

Identity identity(int fd) {
    struct stat s{};
    require(fstat(fd, &s) == 0 && S_ISREG(s.st_mode), "pack fd");
    return {static_cast<int64_t>(s.st_dev), static_cast<int64_t>(s.st_ino),
            s.st_size, ns(s.st_mtim), ns(s.st_ctim)};
}

struct Buffer {
    unsigned char *data = nullptr;
    Buffer() {
        void *p = nullptr;
        require(posix_memalign(&p, 4096, stride) == 0, "aligned buffer");
        data = static_cast<unsigned char *>(p);
        std::memset(data, 0, stride);
    }
    Buffer(const Buffer &) = delete;
    ~Buffer() { std::free(data); }
};

struct Record { off_t offset{}; std::array<std::string, 3> digests; };
void fetch(int fd, const Record &record, Buffer &buf) {
    require(pread(fd, buf.data, stride, record.offset) == static_cast<ssize_t>(stride),
            "short direct read");
}
void verify(const Record &record, const Buffer &buf) {
    for (size_t k = 0; k < 3; ++k) {
        unsigned char hash[SHA256_DIGEST_LENGTH];
        require(SHA256(buf.data + k * slab, slab, hash) != nullptr, "matrix digest");
        std::string hex;
        constexpr char digits[] = "0123456789abcdef";
        for (unsigned char b : hash) {
            hex += digits[b >> 4];
            hex += digits[b & 15];
        }
        require(hex == record.digests[k], "target matrix mismatch");
    }
}

struct Trial {
    int group, stage, order, pair, hit, trace;
    Tick start{}, peers{}, reads{}, drain{};
    std::array<Tick, 4> begin{}, end{};
};

void pair(std::vector<Trial> &v, int group, int stage, int order, int num) {
    for (int leg = 0; leg < 2; ++leg) {
        const int alter = (order == 1) != leg;
        v.push_back(Trial{group, stage, order, num, stage * alter, (1 - stage) * alter});
    }
}

int main(int argc, char **argv) {
    require(argc == 3, "usage: peer PACK PLAN");
    int fd = open(argv[1], O_RDONLY | O_DIRECT | O_CLOEXEC | O_NOFOLLOW);
    require(fd >= 0, "open direct pack");
    Identity expected{};
    int n = 0;
    std::ifstream file(argv[2]);
    for (auto &v : expected) require(bool(file >> v), "missing plan fd");
    require(identity(fd) == expected && bool(file >> n) && (n == 1 || n == 2), "pack identity or groups");
    std::vector<std::array<Record, 4>> groups(n);
    for (auto &group : groups) {
        std::set<off_t> offsets;
        for (auto &record : group) {
            require(bool(file >> record.offset) && record.offset >= 0 && record.offset % 4096 == 0
                    && record.offset <= expected[2] - static_cast<off_t>(stride)
                    && offsets.insert(record.offset).second, "pack range or repeated worker");
            for (auto &h : record.digests) require(bool(file >> h) && h.size() == 64, "hash plan");
        }
    }
    std::string extra;
    require(!(file >> extra) && file.eof(), "unexpected plan entry");
    std::vector<Trial> trials;
    for (int g = 0; g < n; ++g) {
        for (int stage = 0; stage < 2; ++stage) {
            pair(trials, g, stage, -1, 0);
            for (int order = 0; order < 2; ++order)
                for (int p = 1; p <= 7; ++p) pair(trials, g, stage, order, p);
        }
    }

    std::array<Buffer, 4> staging, destination;
    Buffer retained;
    std::array<unsigned, 4> requested{}, checked{};
    size_t ix = 0;
    std::barrier parity(4);
    std::barrier start(4, [&]() noexcept { trials[ix].start = now(); });
    std::barrier peers(3, [&]() noexcept { trials[ix].peers = now(); });
    std::barrier reads(4, [&]() noexcept { trials[ix].reads = now(); });
    std::barrier drain(4, [&]() noexcept { trials[ix].drain = now(); });
    std::barrier next(4, [&]() noexcept { ++ix; });
    std::array<std::thread, 4> workers;
    for (int w = 0; w < 4; ++w) {
        workers[w] = std::thread([&, w] {
            int previous = -1;
            for (auto &trial : trials) {
                const Record &record = groups[trial.group][w];
                if (trial.group != previous) {
                    Buffer &initial = w == 3 ? retained : staging[w];
                    fetch(fd, record, initial);
                    ++requested[w];
                    verify(record, initial);
                    checked[w] += 3;
                    parity.arrive_and_wait();
                    previous = trial.group;
                }
                const bool keep = trial.hit && w == 3;
                const Buffer &source = keep ? retained : staging[w];
                start.arrive_and_wait();
                if (trial.trace) trial.begin[w] = now();
                if (!keep) {
                    fetch(fd, record, staging[w]);
                    ++requested[w];
                }
                if (trial.trace) trial.end[w] = now();
                if (w != 3) peers.arrive_and_wait();
                reads.arrive_and_wait();
                for (size_t k = 0; k < 3; ++k)
                    std::memcpy(destination[w].data + k * slab, source.data + k * slab, slab);
                drain.arrive_and_wait();
                verify(record, destination[w]);
                checked[w] += 3;
                next.arrive_and_wait();
            }
        });
    }
    for (auto &w : workers) w.join();
    require(ix == trials.size() && identity(fd) == expected && close(fd) == 0, "incomplete drain or changed pack");
    std::cout << "fd";
    for (auto v : expected) std::cout << ' ' << v;
    std::cout << '\n';
    for (const auto &r : trials) {
        std::cout << "row " << r.group << ' ' << r.stage << ' ' << r.order << ' ' << r.pair
                  << ' ' << r.hit << ' ' << r.trace << ' ' << r.peers-r.start
                  << ' ' << r.reads-r.start << ' ' << r.drain-r.start;
        for (int w = 0; w < 4; ++w)
            std::cout << ' ' << (r.trace ? r.begin[w]-r.start : 0)
                      << ' ' << (r.trace ? r.end[w]-r.start : 0);
        std::cout << '\n';
    }
    std::cout << "drained";
    for (auto v : requested) std::cout << ' ' << v;
    for (auto v : checked) std::cout << ' ' << v;
    std::cout << '\n';
}
