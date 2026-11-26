// Compare canonical consecutive MXFP4 rows with a shared resident Q8 activation.
#include <dlfcn.h>
#include <sched.h>
#include <time.h>

#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using Bytes = std::vector<unsigned char>;
using Dot = void (*)(int, float *, size_t, const void *, size_t, const void *, size_t, int);
using Four = void (*)(int, int, float *, const void *, size_t, const void *const *);
using Quant = void (*)(const float *, void *, int64_t);
using Activations = std::array<const void *, 4>;
enum class Mode { reference, control, separate, shared };
constexpr unsigned width = 2880, row_count = 8 * width;
constexpr size_t weight_stride = width / 32 * 17, activation_bytes = width / 32 * 34;
constexpr std::array<Mode, 3> candidates{Mode::control, Mode::separate, Mode::shared};

void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

void *open_library(const char *path, int flags) {
    void *handle = dlopen(path, RTLD_NOW | flags);
    if (!handle) throw std::runtime_error(dlerror());
    return handle;
}

template<class T> T symbol(void *handle, const char *name, const fs::path &owner) {
    void *address = dlsym(handle, name);
    Dl_info info{};
    require(address && dladdr(address, &info) && info.dli_fname && fs::equivalent(info.dli_fname, owner),
            std::string("unexpected symbol owner: ") + name);
    return reinterpret_cast<T>(address);
}

struct Family {
    Dot dot;
    Quant quant;
    std::array<Four, 3> kernels;

    explicit Family(char **argv) {
        void *ref = open_library(argv[1], RTLD_GLOBAL);
        symbol<void (*)()>(ref, "ggml_cpu_init", argv[1])();
        quant = symbol<Quant>(ref, "quantize_row_q8_0", argv[1]);
        dot = symbol<Dot>(ref, "ggml_vec_dot_mxfp4_q8_0", argv[1]);
        for (size_t i = 0; i < kernels.size(); ++i)
            kernels[i] = symbol<Four>(open_library(argv[i+2], RTLD_LOCAL), "tesy_four_rows", argv[i+2]);
        require(kernels[0] != kernels[1] && kernels[0] != kernels[2] && kernels[1] != kernels[2],
                "duplicate grouped kernel entry");
    }

    float reference(int n, const unsigned char *w, const void *y) const {
        float out = NAN;
        dot(n, &out, 0, w, 0, y, 0, 1);
        return out;
    }

    Four kernel(Mode mode) const { return kernels.at(static_cast<size_t>(mode) - 1); }
};

Bytes read_exact(const fs::path &path, size_t size) {
    require(fs::file_size(path) == size, "unexpected input size: " + path.filename().string());
    Bytes bytes(size);
    std::ifstream in(path, std::ios::binary);
    require(bool(in.read(reinterpret_cast<char *>(bytes.data()), size)), "short binary input");
    return bytes;
}

void save(const fs::path &path, const void *data, size_t size) {
    std::ofstream out(path, std::ios::binary);
    require(bool(out.write(static_cast<const char *>(data), size)), "short binary output");
}

void maps(const fs::path &root) {
    std::ifstream input("/proc/self/maps");
    std::ofstream output(root / "maps.tsv");
    for (std::string line; std::getline(input, line);)
        if (line.find('/') != std::string::npos) output << line << '\n';
    require(input.eof() && bool(output), "maps journal");
}

uint32_t bits(float x) {
    uint32_t v;
    std::memcpy(&v, &x, sizeof(v));
    return v;
}

void equal(float expected, float actual, Mode mode, size_t row, const char *phase) {
    if (std::isfinite(expected) && bits(expected) == bits(actual)) return;
    std::fprintf(stderr, "%s mode=%u row=%zu expected=%08x actual=%08x\n", phase,
                 static_cast<unsigned>(mode), row, bits(expected), bits(actual));
    throw std::runtime_error("nonfinite or unequal output");
}

struct SyntheticCounts {
    size_t shared_rows = 0;
    size_t distinct_rows = 0;
    size_t guarded_calls = 0;
    size_t distinguishing_rows = 0;
};

SyntheticCounts synthetic(const Family &f) {
    SyntheticCounts checked;
    constexpr std::array<unsigned, 4> slots{2, 0, 3, 1}, destinations{1, 3, 0, 2};
    constexpr std::array<unsigned, 4> inputs{3, 0, 1, 2};
    constexpr std::array<int, 9> q8_codes{-127, -100, -7, -1, 0, 1, 6, 89, 127};
    constexpr float canary = -1234567.5f;
    for (const int blocks : {1, 2, 3, 5, 90}) {
        const size_t stride = size_t(blocks) * 17 + 11; // padding between weight rows
        const size_t sy = size_t(blocks) * 34 + 6;
        for (unsigned pattern = 0; pattern < 8; ++pattern) {
            Bytes w(16 * stride, 0x55), y(4 * sy, 0xaa);
            for (unsigned b = 0; b < unsigned(blocks); ++b) {
                for (unsigned r = 0; r < 16; ++r) {
                    auto *block = w.data() + r * stride + b * 17;
                    block[0] = static_cast<unsigned char>(119 + (b + pattern + r) % 11);
                    for (unsigned i = 0; i < 16; ++i) {
                        unsigned low = (pattern + i + b + 7 * r) % 16;
                        unsigned high = (3 * pattern + 15 - i + b + r) % 16;
                        block[1+i] = static_cast<unsigned char>(low | (high << 4));
                    }
                }
                for (unsigned q = 0; q < 4; ++q) {
                    auto *block = y.data() + q * sy + b * 34;
                    const uint16_t d = 0x3600 + 0x100 * ((q + b + pattern) % 9);
                    std::memcpy(block, &d, sizeof(d));
                    for (unsigned i = 0; i < 32; ++i)
                        block[2+i] = static_cast<unsigned char>(q8_codes[(i+b+pattern+q) % q8_codes.size()]);
                }
            }
            const Bytes before_w = w, before_y = y;
            for (int nr = 1; nr <= 4; ++nr) {
                for (size_t job = 0; job < 4; ++job) {
                    const auto *weights = w.data() + 4 * slots[job] * stride;
                    const unsigned offset = 1 + 7 * destinations[job];
                    for (bool distinct : {false, true}) {
                        Activations operands{};
                        std::array<float, 4> independent{}, common{};
                        for (unsigned r = 0; r < 4; ++r) {
                            const size_t index = (inputs[job] + (distinct ? r : 0)) % 4;
                            operands[r] = y.data() + sy * index;
                            if (r < unsigned(nr)) {
                                common[r] = f.reference(blocks * 32, weights + stride * r, operands[0]);
                                independent[r] = f.reference(blocks * 32, weights + stride * r, operands[r]);
                                if (distinct && nr == 4 && bits(common[r]) != bits(independent[r]))
                                    ++checked.distinguishing_rows;
                            }
                        }
                        (distinct ? checked.distinct_rows : checked.shared_rows) += nr;
                        for (Mode mode : candidates) {
                            std::array<float, 28> output;
                            output.fill(canary);
                            f.kernel(mode)(blocks * 32, nr, output.data() + offset, weights,
                                           stride, operands.data());
                            const auto &gold = mode == Mode::shared ? common : independent;
                            for (unsigned i = 0; i < output.size(); ++i) {
                                const bool produced = i >= offset && i < offset + unsigned(nr);
                                equal(produced ? gold[i-offset] : canary, output[i], mode, i, "synthetic");
                            }
                            ++checked.guarded_calls;
                        }
                    }
                }
            }
            require(before_w == w && before_y == y, "synthetic input or padding overwritten");
        }
    }
    require(checked.distinguishing_rows > 0, "distinct activations did not discriminate");
    return checked;
}

// Cancellation in the last (scalar) block distinguishes a fused multiply-add
// from adding a separately rounded odd-block result, even when the rank agrees.
void odd_block_witness(const Family &f) {
    constexpr size_t stride = 3 * 17;
    Bytes weights(4 * stride, 0), y(3 * 34, 0);
    for (unsigned r = 0; r < 4; ++r) {
        auto *base = weights.data() + r * stride;
        for (unsigned b = 0; b < 3; ++b) base[b * 17] = 128;
        std::fill(base + 1, base + 17, 0x77);
        std::fill(base + 35, base + 51, 0x77);
        base[50] = 0x17; // high nibble for element 31
    }
    const std::array<uint16_t, 3> scales{0x4000, 0x3c00, 0x3fff};
    for (unsigned b = 0; b < 3; ++b) std::memcpy(y.data()+34*b, &scales[b], 2);
    std::fill(y.begin()+2, y.begin()+34, static_cast<unsigned char>(-123));
    std::fill(y.begin()+70, y.end(), 127);
    y.back() = 1;
    const Activations ys{y.data(), y.data(), y.data(), y.data()};
    constexpr float exact = -20.1376953125f;
    equal(exact, f.reference(96, weights.data(), y.data()), Mode::reference, 0, "odd-fma-oracle");
    for (Mode mode : candidates) {
        std::array<float, 4> result{NAN, NAN, NAN, NAN};
        f.kernel(mode)(96, 4, result.data(), weights.data(), stride, ys.data());
        for (unsigned r = 0; r < 4; ++r) equal(exact, result[r], mode, r, "odd-fma");
    }
}

void pass(const Family &f, Mode mode, const Bytes &weights, const Activations &ys,
          size_t count, float *dst) {
    if (mode == Mode::reference) {
        for (size_t r = 0; r < count; ++r)
            f.dot(width, dst+r, 0, weights.data() + r*weight_stride, 0, ys[0], 0, 1);
        return;
    }
    Four kernel = f.kernel(mode);
    for (size_t r = 0; r < count; r += 4)
        kernel(width, static_cast<int>(std::min<size_t>(4, count-r)), dst+r,
               weights.data() + r*weight_stride, weight_stride, ys.data());
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
    require(sched_setaffinity(0, sizeof(mask), &mask) == 0 && sched_getcpu() == cpu, "affinity");
}

void measure(const Family &f, const Bytes &weights, const Activations &ys,
             const std::vector<float> &gold, const fs::path &root) {
    std::vector<float> dst(row_count);
    std::ofstream out(root / "arms.tsv");
    out << "cpu regime arm variant rows repeats duration_ns\n";
    constexpr std::array<Mode, 8> order{Mode::reference, Mode::control, Mode::separate, Mode::shared,
                                        Mode::shared, Mode::separate, Mode::control, Mode::reference};
    for (int cpu : {0, 4}) {
        pin(cpu);
        for (bool stream : {false, true}) {
            const size_t count = stream ? row_count : 64, repeats = stream ? 12 : 4096;
            for (size_t arm = 0; arm < order.size(); ++arm) {
                Mode mode = order[arm];
                pass(f, mode, weights, ys, count, dst.data());
                const auto start = now_ns();
                for (size_t i = 0; i < repeats; ++i) pass(f, mode, weights, ys, count, dst.data());
                const auto elapsed = now_ns() - start;
                require(sched_getcpu() == cpu && elapsed > 0, "migration or clock");
                require(std::memcmp(dst.data(), gold.data(), count*sizeof(float)) == 0, "timed parity");
                out << cpu << ' ' << (stream ? "stream" : "hot") << ' ' << arm+1 << ' '
                    << "RACB"[static_cast<unsigned>(mode)] << ' ' << count << ' ' << repeats
                    << ' ' << elapsed << std::endl;
                require(bool(out), "arm journal write");
            }
        }
    }
}

int main(int argc, char **argv) {
    try {
        const bool synthetic_only = argc == 7 && std::string(argv[5]) == "--synthetic";
        require(synthetic_only || argc == 8,
                "usage: clockbench4 R.so control.so separate.so shared.so {weights.bin activation.f32 | --synthetic} OUT");
        const fs::path root(argv[argc-1]);
        require(fs::is_directory(root) && fs::is_empty(root), "output must be an empty directory");
        require(__builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma"), "AVX2/FMA");
        require(std::fesetround(FE_TONEAREST) == 0, "rounding");
        const Family family(argv);
        maps(root);
        const auto tested = synthetic(family);
        odd_block_witness(family);
        std::ofstream parity(root / "parity.tsv");
        parity << "real_rows shared_rows distinct_rows guarded_calls distinguishing_rows odd_fma_rows quant_bytes\n";
        if (synthetic_only) {
            parity << 0 << ' ' << tested.shared_rows << ' ' << tested.distinct_rows << ' '
                   << tested.guarded_calls << ' ' << tested.distinguishing_rows << " 4 0" << std::endl;
            require(bool(parity), "synthetic receipt");
            return 0;
        }
        const auto weights = read_exact(argv[5], row_count * weight_stride);
        const auto input = read_exact(argv[6], width * sizeof(float));
        std::vector<float> activation(width);
        std::memcpy(activation.data(), input.data(), input.size());
        Bytes q8(activation_bytes);
        family.quant(activation.data(), q8.data(), width);
        const Activations ys{q8.data(), q8.data(), q8.data(), q8.data()};
        std::vector<float> gold(row_count), actual(row_count);
        pass(family, Mode::reference, weights, ys, row_count, gold.data());
        require(std::any_of(gold.begin(), gold.end(), [](float x){ return x != 0; }), "zero reference");
        for (Mode mode : candidates) {
            std::fill(actual.begin(), actual.end(), NAN);
            pass(family, mode, weights, ys, row_count, actual.data());
            for (size_t r = 0; r < row_count; ++r) equal(gold[r], actual[r], mode, r, "target");
        }
        const char *historical_dir = std::getenv("TESY_FOUR_REFERENCE_NATIVE");
        require(historical_dir && fs::path(historical_dir).is_absolute(), "historical reference directory");
        const auto historical = fs::path(historical_dir);
        const auto prior_outputs = read_exact(historical / "gold.f32", row_count * sizeof(float));
        const auto prior_q8 = read_exact(historical / "activation.q8", activation_bytes);
        require(q8 == prior_q8, "historical Q8 activation mismatch");
        require(std::memcmp(gold.data(), prior_outputs.data(), prior_outputs.size()) == 0,
                "historical R0 row mismatch");
        save(root / "gold.f32", gold.data(), gold.size() * sizeof(float));
        save(root / "activation.q8", q8.data(), q8.size());
        parity << row_count << ' ' << tested.shared_rows << ' ' << tested.distinct_rows << ' '
               << tested.guarded_calls << ' ' << tested.distinguishing_rows << " 4 " << q8.size()
               << std::endl;
        require(bool(parity), "parity receipt");
        measure(family, weights, ys, gold, root);
        return 0;
    } catch (const std::exception &e) {
        std::fprintf(stderr, "FAIL %s\n", e.what());
        return 1;
    }
}
