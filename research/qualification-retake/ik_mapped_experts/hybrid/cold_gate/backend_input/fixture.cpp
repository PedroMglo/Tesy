#include "bank_input.hpp"
#include <array>
#include <cstdio>
#include <iostream>
#include <string_view>
#include <tuple>
#include <vector>

static void require(bool ok, const char *why) {
    if (!ok) throw std::runtime_error(why);
}

static uint8_t expected(size_t i) { return uint8_t((19 * i + i / 37 + 7) % 251); }

struct Deferred {
    std::vector<std::tuple<const uint8_t *, size_t, size_t>> queue;
    size_t fences = 0, checks = 0, verified = 0;

    void enqueue(const void *src, size_t n, size_t offset) {
        require(uintptr_t(src) % tesy::BankInput::page == offset % tesy::BankInput::page,
                "page displacement changed");
        queue.emplace_back(static_cast<const uint8_t *>(src), n, offset);
    }

    void complete() {
        ++fences;
        for (auto [p, n, at] : queue) {
            for (size_t i = 0; i < n; ++i) require(p[i] == expected(at + i), "source reused early");
            ++checks;
            verified += n;
        }
        queue.clear();
    }
};

template<class Error, class F> static void rejects(F f) {
    try {
        f();
    } catch (const Error &) {
        return;
    }
    throw std::runtime_error("expected rejection");
}

static void run(const char *label, tesy::Source source, int fd, const uint8_t *map, size_t size) {
    constexpr size_t page = tesy::BankInput::page;
    Deferred stream, other, idle;
    std::array<const void *, 2> starts{};
    {
        tesy::BankInput a(fd, 2 * page, source, [&]{stream.complete();});
        a.synchronize_ids();
        auto send = [&](size_t at, size_t bytes, size_t record) {
            a.send(at, map + at, bytes, [&](const void *src, size_t n){
                starts[record] = src;
                stream.enqueue(src, n, at);
            });
        };
        send(103, 900, 0);
        send(4800, 1300, 1);
        rejects<std::length_error>([&]{ send(16, 32, 1); });
        rejects<std::invalid_argument>([&]{ a.send(size - 1, map, 2, [](auto,auto){}); });
        rejects<std::invalid_argument>([&]{ a.send(-1, map, 1, [](auto,auto){}); });
        rejects<std::invalid_argument>([&]{ a.send(0, map, 0, [](auto,auto){}); });
        const void *initial = starts[0];
        {
            tesy::BankInput b(fd, page, source, [&]{other.complete();});
            b.synchronize_ids();
            b.send(17, map + 17, 51, [&](const void *p,size_t n){other.enqueue(p,n,17);});
        }
        require(other.fences == 2 && other.checks == 1 && stream.checks == 0, "shared stream owner");
        a.synchronize_ids();
        require(stream.checks == 2 && stream.fences == 2, "two checks at next ID barrier");
        send(103, 1099, 0);
        require(starts[0] == initial, "region not reusable after the ID fence");
        rejects<std::runtime_error>([&]{
            a.send(8821, map + 8821, 257, [&](const void *p,size_t n){
                stream.enqueue(p,n,8821);
                throw std::runtime_error("failure after enqueue");
            });
        });
        rejects<std::invalid_argument>([&]{ send(65, 16, 0); });
    }
    {
        tesy::BankInput b(fd, page, source, [&]{idle.complete();});
        b.synchronize_ids();
    }
    require(stream.fences == 3 && stream.checks == 4 && stream.verified == 3556 &&
            other.verified == 51 && idle.fences == 1, "teardown conservation");
    std::cout << label << " 3 4 3556 2 1 51 1\n";
}

int main() {
    constexpr size_t size = 4 * tesy::BankInput::page;
    FILE *f = std::tmpfile();
    if (!f) return 1;
    int fd = fileno(f);
    std::array<uint8_t,size> bytes{};
    for (size_t i = 0; i < size; ++i) bytes[i]=expected(i);
    if (pwrite(fd,bytes.data(),size,0) != ssize_t(size)) return 2;
    void *raw = mmap(nullptr,size,PROT_READ,MAP_SHARED,fd,0);
    if (raw == MAP_FAILED) return 3;
    auto map = static_cast<const uint8_t *>(raw);
    try {
        run("DIRECT", tesy::Source::mapped, fd, map, size);
        run("PREAD_RANDOM", tesy::Source::ranges, fd, map, size);
        Deferred pending;
        {
            tesy::BankInput a(fd,2*tesy::BankInput::page,tesy::Source::ranges,[&]{pending.complete();});
            a.synchronize_ids();
            a.send(81,map+81,64,[&](const void *p,size_t n){pending.enqueue(p,n,81);});
            require(ftruncate(fd,4096) == 0, "fixture truncation");
            rejects<std::runtime_error>([&]{a.send(8192,nullptr,64,[](auto,auto){});});
        }
        require(pending.fences==2 && pending.verified==64, "short read lost pending transfer");
        std::cout << "SHORT_READ 2 1 64\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 4;
    }
    return munmap(raw,size) || std::fclose(f);
}
