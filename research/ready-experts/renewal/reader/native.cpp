#include <liburing.h>
#include <openssl/sha.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using Clock = std::chrono::steady_clock;
constexpr size_t slab = 4406400, window = 13221888;
constexpr int lanes = 4;

void check(bool ok, const std::string &reason) {
    if (!ok) throw std::runtime_error(reason);
}

struct Window {
    off_t offset{};
    std::array<std::string, 3> expected;
};
using Group = std::vector<Window>;
using Work = std::array<Group, 4>;

Work plan(const char *filename) {
    Work groups;
    std::ifstream file(filename);
    int g;
    Window w;
    while (file >> g) {
        check(bool(file >> w.offset >> w.expected[0] >> w.expected[1] >> w.expected[2]),
              "incomplete plan");
        check(g >= 0 && g < 4 && w.offset >= 0 && w.offset % 4096 == 0, "invalid group");
        for (const auto &hash : w.expected) check(hash.size() == 64, "invalid digest");
        groups[g].push_back(w);
    }
    check(file.eof(), "invalid plan suffix");
    for (int i = 0; i < 4; ++i)
        check(groups[i].size() == (i < 2 ? 4u : 1u), "group size");
    return groups;
}

class Buffers {
public:
    std::array<unsigned char *, lanes> ptr{};
    Buffers() {
        for (auto &p : ptr) {
            void *mem = nullptr;
            check(posix_memalign(&mem, 4096, window) == 0, "aligned allocation");
            p = static_cast<unsigned char *>(mem);
            std::memset(p, 0, window);
        }
    }
    ~Buffers() { for (auto p : ptr) std::free(p); }

    void verify(const Group &group) const {
        static constexpr char digits[] = "0123456789abcdef";
        for (size_t i = 0; i < group.size(); ++i) {
            for (size_t j = 0; j < 3; ++j) {
                std::array<unsigned char, SHA256_DIGEST_LENGTH> sum;
                check(SHA256(ptr[i] + j * slab, slab, sum.data()) != nullptr, "hash error");
                std::string hex;
                for (const auto v : sum) {
                    hex.push_back(digits[v >> 4]);
                    hex.push_back(digits[v & 15]);
                }
                check(hex == group[i].expected[j], "incorrect expert component");
            }
        }
    }
};

class PreadWorkers {
    const int fd;
    Buffers &buffers;
    std::mutex mutex;
    std::condition_variable wake, done;
    const Group *group = nullptr;
    unsigned generation = 0, remaining = 0, ready = 0;
    bool stop = false;
    std::array<ssize_t, lanes> returns{};
    std::array<std::thread, lanes> threads;

    void worker(size_t lane) {
        std::unique_lock lock(mutex);
        auto seen = generation;
        ++ready;
        done.notify_one();
        while (true) {
            wake.wait(lock, [&] { return stop || generation != seen; });
            if (stop) return;
            seen = generation;
            if (lane >= group->size()) continue;
            const off_t offset = (*group)[lane].offset;
            lock.unlock();
            const auto rv = pread(fd, buffers.ptr[lane], window, offset);
            lock.lock();
            returns[lane] = rv;
            if (--remaining == 0) done.notify_one();
        }
    }
public:
    PreadWorkers(int f, Buffers &b) : fd(f), buffers(b) {
        for (int i = 0; i < lanes; ++i) threads[i] = std::thread([this, i] { worker(i); });
        std::unique_lock lock(mutex);
        done.wait(lock, [&] { return ready == lanes; });
    }
    ~PreadWorkers() {
        { std::lock_guard lock(mutex); stop = true; }
        wake.notify_all();
        for (auto &t : threads) t.join();
    }
    void read(const Group &g) {
        std::unique_lock lock(mutex);
        group = &g;
        remaining = g.size();
        ++generation;
        wake.notify_all();
        done.wait(lock, [&] { return remaining == 0; });
        for (size_t i = 0; i < g.size(); ++i) check(returns[i] == ssize_t(window), "short pread");
    }
};

class Ring {
    io_uring ring{};
public:
    Ring() {
        int ret = io_uring_queue_init(lanes, &ring, 0);
        check(ret == 0, "io_uring_queue_init errno=" + std::to_string(-ret));
    }
    ~Ring() { io_uring_queue_exit(&ring); }
    void read(int fd, const Group &group, Buffers &b) {
        for (size_t i = 0; i < group.size(); ++i) {
            io_uring_sqe *sqe = io_uring_get_sqe(&ring);
            check(sqe != nullptr, "missing SQE");
            io_uring_prep_read(sqe, fd, b.ptr[i], window, group[i].offset);
            io_uring_sqe_set_data64(sqe, i);
        }
        int n = static_cast<int>(group.size());
        check(io_uring_submit_and_wait(&ring, n) == n, "short submission");
        std::array<bool, lanes> used{};
        for (int j = 0; j < n; ++j) {
            io_uring_cqe *cqe = nullptr;
            check(io_uring_wait_cqe(&ring, &cqe) == 0 && cqe, "missing CQE");
            auto id = io_uring_cqe_get_data64(cqe);
            check(id < group.size() && !used[id] && cqe->res == int(window), "invalid or short CQE");
            used[id] = true;
            io_uring_cqe_seen(&ring, cqe);
        }
    }
};

int main(int argc, char **argv) {
    try {
        check(argc == 3, "usage: reader PACK PLAN");
        auto groups = plan(argv[2]);
        int fd = open(argv[1], O_RDONLY | O_DIRECT | O_CLOEXEC | O_NOFOLLOW);
        check(fd >= 0 && (fcntl(fd, F_GETFL) & O_DIRECT), "open direct read only");
        struct stat st{};
        check(fstat(fd, &st) == 0 && S_ISREG(st.st_mode), "invalid source");
        std::cout << "fd " << st.st_dev << ' ' << st.st_ino << ' ' << st.st_size << ' '
                  << (st.st_mtim.tv_sec * 1000000000LL + st.st_mtim.tv_nsec) << ' '
                  << (st.st_ctim.tv_sec * 1000000000LL + st.st_ctim.tv_nsec) << std::endl;
        {
            Buffers b;
            PreadWorkers pool(fd, b);
            Ring ring;
            for (int arm = 0; arm < 30; ++arm) {
                bool async = arm < 16 ? (arm % 2 == 1) : (arm % 2 == 0);
                for (size_t i = 0; i < groups.size(); ++i) {
                    auto begin = Clock::now();
                    if (async) ring.read(fd, groups[i], b);
                    else pool.read(groups[i]);
                    auto end = Clock::now();
                    b.verify(groups[i]);
                    auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count();
                    std::cout << arm << ' ' << (async ? "RING" : "PRE") << ' ' << i << ' '
                              << groups[i].size() << ' ' << ns << std::endl;
                }
            }
        }
        check(close(fd) == 0, "pack close");
        std::cout << "drained" << std::endl;
    } catch (const std::exception &e) {
        std::cerr << e.what() << std::endl;
        return 1;
    }
    return 0;
}
