// Time the pinned MXFP4 row dot on resident data. Every implementation takes
// the same external call and writes each result to the same destination layout.
#include <dlfcn.h>
#include <sched.h>
#include <time.h>

#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using bytes = std::vector<unsigned char>;
using Dot = void (*)(int, float *, size_t, const void *, size_t, const void *, size_t, int);
using Quant = void (*)(const float *, void *, int64_t);
constexpr size_t width = 2880, blocks = width / 32;
constexpr size_t weight_stride = blocks * 17, activation_stride = blocks * 34;
constexpr size_t rows = 8 * width;

void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

bytes read_exact(const fs::path &path, size_t size) {
    require(fs::file_size(path) == size, "input size: " + path.string());
    bytes content(size);
    std::ifstream f(path, std::ios::binary);
    require(bool(f.read(reinterpret_cast<char *>(content.data()), size)), "short input");
    return content;
}

void save(const fs::path &path, const void *data, size_t size) {
    std::ofstream f(path, std::ios::binary);
    require(bool(f.write(static_cast<const char *>(data), size)), "write failed");
}

void *open_library(const fs::path &path, int flags) {
    void *handle = dlopen(path.c_str(), RTLD_NOW | flags);
    if (!handle) throw std::runtime_error(dlerror());
    return handle;
}

template<class T> T symbol(void *handle, const char *name, const fs::path &owner) {
    auto address = dlsym(handle, name);
    Dl_info info{};
    require(address && dladdr(address, &info) && info.dli_fname &&
                fs::equivalent(info.dli_fname, owner), std::string("unexpected symbol: ") + name);
    return reinterpret_cast<T>(address);
}

struct Family {
    std::array<Dot, 4> dot;
    Quant quant;
};

Family load(char **argv) {
    Family family{};
    void *ref = open_library(argv[1], RTLD_GLOBAL);
    symbol<void (*)()>(ref, "ggml_cpu_init", argv[1])();
    family.quant = symbol<Quant>(ref, "quantize_row_q8_0", argv[1]);
    for (int i = 0; i < 4; ++i) {
        void *handle = i == 0 ? ref : open_library(argv[i + 1], RTLD_LOCAL);
        family.dot[i] = symbol<Dot>(handle, "ggml_vec_dot_mxfp4_q8_0", argv[i + 1]);
    }
    return family;
}

void compare(float gold, float produced, int implementation, size_t row) {
    if (std::isfinite(gold) && !std::memcmp(&gold, &produced, sizeof(float))) return;
    unsigned int a = 0, b = 0;
    std::memcpy(&a, &gold, sizeof(a));
    std::memcpy(&b, &produced, sizeof(b));
    std::fprintf(stderr, "row=%zu implementation=%d expected=%08x actual=%08x\n", row,
                 implementation, a, b);
    throw std::runtime_error("nonfinite or parity mismatch");
}

float one(Dot dot, int n, const unsigned char *weight, const unsigned char *q8) {
    float result = NAN;
    dot(n, &result, 0, weight, 0, q8, 0, 1);
    return result;
}

size_t synthetic(const Family &f) {
    size_t verified = 0;
    for (int nblocks : {1, 2, 3, 5, 90}) {
        bytes w(size_t(nblocks) * 17), y(size_t(nblocks) * 34);
        for (unsigned pattern = 0; pattern < 32; ++pattern) {
            for (int block = 0; block < nblocks; ++block) {
                const uint16_t half = (block & 1) ? 0x3800 : 0x3c00;
                std::memcpy(&y[34 * block], &half, 2);
                w[17 * block] = static_cast<unsigned char>(119 + (block + pattern) % 11);
                for (int i = 0; i < 16; ++i) {
                    const unsigned low = (pattern + i + block) % 16;
                    const unsigned high = (3 * pattern + 15 - i + block) % 16;
                    w[17 * block + 1 + i] = static_cast<unsigned char>(low | (high << 4));
                }
                constexpr int signs[] = {-127, -100, -7, -1, 0, 1, 6, 89, 127};
                for (unsigned i = 0; i < 32; ++i) {
                    y[34 * block + 2 + i] = static_cast<unsigned char>(
                        signs[(i + block + pattern) % std::size(signs)]);
                }
            }
            const float gold = one(f.dot[0], 32 * nblocks, w.data(), y.data());
            for (int i = 1; i < 4; ++i) {
                compare(gold, one(f.dot[i], 32 * nblocks, w.data(), y.data()), i, verified);
            }
            ++verified;
        }
    }
    return verified;
}

uint64_t now_ns() {
    timespec t{};
    require(clock_gettime(CLOCK_MONOTONIC_RAW, &t) == 0, "clock_gettime");
    return uint64_t(t.tv_sec) * 1000000000ULL + t.tv_nsec;
}

void pin(int cpu) {
    cpu_set_t mask;
    CPU_ZERO(&mask);
    CPU_SET(cpu, &mask);
    require(sched_setaffinity(0, sizeof(mask), &mask) == 0 && sched_getcpu() == cpu, "CPU affinity");
}

void pass(Dot dot, const bytes &weights, const bytes &q8, size_t count, std::vector<float> &dst) {
    for (size_t r = 0; r < count; ++r)
        dot(width, &dst[r], 0, &weights[r * weight_stride], 0, q8.data(), 0, 1);
}

void measure(const Family &f, const bytes &weights, const bytes &q8,
             const std::vector<float> &gold, const fs::path &root) {
    std::vector<float> dst(rows);
    std::ofstream out(root / "arms.tsv");
    require(bool(out), "arm journal");
    out << "cpu regime arm variant rows repeats duration_ns\n";
    constexpr std::array<int, 6> order{0, 1, 2, 2, 1, 0};
    for (const int cpu : {0, 4}) {
        pin(cpu);
        for (const bool streaming : {false, true}) {
            size_t count = streaming ? rows : 64, repeats = streaming ? 12 : 4096;
            for (size_t arm = 0; arm < order.size(); ++arm) {
                int impl = order[arm];
                pass(f.dot[impl], weights, q8, count, dst);
                const uint64_t start = now_ns();
                for (size_t k = 0; k < repeats; ++k) pass(f.dot[impl], weights, q8, count, dst);
                const auto elapsed = now_ns() - start;
                require(sched_getcpu() == cpu && elapsed > 0, "invalid clock or CPU migration");
                require(!std::memcmp(dst.data(), gold.data(), count * sizeof(float)), "timed output");
                out << cpu << ' ' << (streaming ? "stream" : "hot") << ' ' << (arm + 1)
                    << ' ' << "RAB"[impl] << ' ' << count << ' ' << repeats << ' ' << elapsed
                    << std::endl;
                require(bool(out), "arm journal write");
            }
        }
    }
}

int main(int argc, char **argv) {
    try {
        require(argc == 8, "usage: clockbench R.so A.so B.so F.so weights.bin activation.f32 OUT");
        const fs::path root(argv[7]);
        require(fs::is_directory(root) && fs::is_empty(root), "output must be an empty directory");
        require(__builtin_cpu_supports("avxvnni"), "AVX-VNNI unavailable on timing host");
        require(std::fesetround(FE_TONEAREST) == 0, "rounding");
        const auto f = load(argv);
        const auto weights = read_exact(argv[5], rows * weight_stride);
        const auto input = read_exact(argv[6], width * sizeof(float));
        std::vector<float> activation(width);
        std::memcpy(activation.data(), input.data(), input.size());
        bytes q8(activation_stride);
        f.quant(activation.data(), q8.data(), width);
        const size_t cases = synthetic(f);
        std::vector<float> gold(rows), actual(rows);
        pass(f.dot[0], weights, q8, rows, gold);
        require(std::any_of(gold.begin(), gold.end(), [](float x){ return x != 0.0f; }), "zero reference");
        for (int i = 1; i < 4; ++i) {
            pass(f.dot[i], weights, q8, rows, actual);
            for (size_t r = 0; r < rows; ++r) compare(gold[r], actual[r], i, r);
        }
        save(root / "gold.f32", gold.data(), gold.size() * sizeof(float));
        save(root / "activation.q8", q8.data(), q8.size());
        std::ofstream parity(root / "parity.tsv");
        parity << "real_rows synthetic_rows quant_bytes\n" << rows << ' ' << cases << ' '
               << q8.size() << std::endl;
        require(bool(parity), "parity receipt");
        std::ifstream maps("/proc/self/maps");
        std::ofstream mapped(root / "maps.tsv");
        for (std::string line; std::getline(maps, line);)
            if (line.find('/') != std::string::npos) mapped << line << '\n';
        require(maps.eof() && bool(mapped), "ELF mappings");
        measure(f, weights, q8, gold, root);
        return 0;
    } catch (const std::exception &e) {
        std::fprintf(stderr, "FAIL %s\n", e.what());
        return 1;
    }
}
