// Geometry and queue conformance only. No GGUF is opened and no weight is touched.
#include "ggml.h"
#include "ggml-moe-prefetch.h"
#include "nlohmann/json.hpp"

#include <sys/mman.h>
#include <sys/syscall.h>
#include <dirent.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

using json = nlohmann::json;
using Bytes = uint64_t;

constexpr Bytes slab = 4406400, experts = 128, tensor_bytes = slab * experts;
constexpr Bytes chunk = 2 * 1024 * 1024;
constexpr std::array<const char *, 3> names{"gate", "up", "down"};
constexpr std::array<Bytes, 3> c283_offsets{1838905376, 2405874208, 1273411616};
constexpr std::array<int32_t, 4> ranks{0, 1, 63, 127};
constexpr std::array<int32_t, 4> small{3, 3, -1, 128};

static void require(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}

struct Mapping {
    uintptr_t base;
    Bytes size, file_page;
    ggml_tensor *weight;
};

enum Call { residency, populate, hint };
constexpr std::array<const char *, 3> call_names{"mincore", "populate", "willneed"};
// role, syscall kind, absolute byte offset in the original GGUF, length as issued
using Event = std::tuple<int, Call, Bytes, Bytes>;
using Events = std::vector<Event>;
static std::array<Mapping, 3> maps{};
static Bytes page;
static std::mutex log_mutex;
static Events journal;
static std::set<pid_t> readers;
static pid_t main_tid;
static bool probing = false;
static unsigned probes = 0;

static Bytes floor_page(Bytes n) { return n - n % page; }
static Bytes ceil_page(Bytes n) { return floor_page(n + page - 1); }

static std::set<pid_t> task_ids() {
    DIR *directory = opendir("/proc/self/task");
    require(directory != nullptr, "cannot enumerate native threads");
    std::set<pid_t> ids;
    while (const auto *entry = readdir(directory)) {
        char *end;
        long id = std::strtol(entry->d_name, &end, 10);
        if (id > 0 && *end == 0) ids.insert(static_cast<pid_t>(id));
    }
    closedir(directory);
    return ids;
}

static void record(void *address, size_t length, Call kind) {
    uintptr_t start = reinterpret_cast<uintptr_t>(address);
    pid_t tid = static_cast<pid_t>(syscall(SYS_gettid));
    if (!length || start % page ||
        (kind == hint ? tid != main_tid : readers.count(tid) != 1)) {
        std::fputs("invalid prefetch syscall thread or alignment\n", stderr);
        std::abort();
    }
    for (size_t i = 0; i < maps.size(); ++i) {
        const Mapping &m = maps[i];
        if (start < m.base || start - m.base >= m.size) continue;
        Bytes relative = start - m.base;
        if (length > m.size - relative) break;
        std::lock_guard<std::mutex> guard(log_mutex);
        journal.emplace_back(i, kind, m.file_page + relative, length);
        return;
    }
    std::fputs("syscall outside the fixture mapping\n", stderr);
    std::abort();
}

extern "C" int __real_madvise(void *, size_t, int);
extern "C" int __wrap_madvise(void *addr, size_t len, int advice) {
    // A genuine kernel capability probe on upstream's single anonymous page.
    if (probing && advice == MADV_POPULATE_READ && len == page &&
        syscall(SYS_gettid) == main_tid) {
        ++probes;
        return __real_madvise(addr, len, advice);
    }
    if (advice != MADV_POPULATE_READ && advice != MADV_WILLNEED) std::abort();
    record(addr, len, advice == MADV_POPULATE_READ ? populate : hint);
    return 0;
}

extern "C" int __wrap_mincore(void *addr, size_t len, unsigned char *vec) {
    record(addr, len, residency);
    std::memset(vec, 0, ceil_page(len) / page);  // explicitly cold synthetic response
    return 0;
}

enum class Coverage { none, selected, full, small_only };
using Runs = std::vector<std::pair<Bytes, Bytes>>;

// Independent oracle. These maximal runs are fixed by the two literal input
// vectors, independently of the fork's bitset, coalescer, ticket and queue.
static Runs expected_runs(Coverage coverage) {
    switch (coverage) {
        case Coverage::none: return {};
        case Coverage::selected: return {{0, 2}, {63, 1}, {127, 1}};
        case Coverage::full: return {{0, experts}};
        case Coverage::small_only: return {{3, 1}};
    }
    std::abort();
}

static Events expected(Coverage coverage, bool legacy, size_t n_roles) {
    Events result;
    for (size_t role = 0; role < n_roles; ++role) {
        for (auto [first, count] : expected_runs(coverage)) {
            Bytes start = c283_offsets[role] + first * slab;
            Bytes limit = start + count * slab;
            if (legacy) {
                result.emplace_back(role, hint, floor_page(start), limit - floor_page(start));
                continue;
            }
            for (Bytes cursor = start; cursor < limit; cursor += chunk) {
                Bytes end = std::min(limit, cursor + chunk);
                Bytes begin_page = floor_page(cursor);
                result.emplace_back(role, residency, begin_page, end - begin_page);
                result.emplace_back(role, populate, begin_page, ceil_page(end) - begin_page);
            }
        }
    }
    std::sort(result.begin(), result.end());
    return result;
}

static json stats(const Events &events, int role) {
    json output;
    for (int kind = residency; kind <= hint; ++kind) {
        Runs ranges;
        Bytes requested = 0, page_sum = 0;
        for (auto [event_role, method, start, length] : events) {
            if (method != kind || (role >= 0 && role != event_role)) continue;
            requested += length;
            ranges.emplace_back(start, ceil_page(start + length));
            page_sum += ranges.back().second - start;
        }
        std::sort(ranges.begin(), ranges.end());
        Bytes end = 0, joined = 0;
        for (auto [start, stop] : ranges) {
            if (stop > end) joined += stop - std::max(start, end);
            end = std::max(end, stop);
        }
        output[call_names[kind]] = {{"calls", ranges.size()}, {"requested_bytes", requested},
                                    {"page_sum_bytes", page_sum}, {"page_union_bytes", joined}};
    }
    return output;
}

static json finish(const char *mode, int width, Coverage coverage, bool legacy = false,
                   size_t n_roles = 3) {
    for (const auto &m : maps) ggml_moe_prefetch_wait(m.weight);
    Events actual;
    {
        std::lock_guard<std::mutex> guard(log_mutex);
        actual.swap(journal);
    }
    std::sort(actual.begin(), actual.end());
    const Events oracle = expected(coverage, legacy, n_roles);
    if (actual != oracle) {
        size_t i = 0;
        while (i < actual.size() && i < oracle.size() && actual[i] == oracle[i]) ++i;
        auto mismatch = [i](const Events &log) -> json {
            return i < log.size() ? json(log[i]) : json(nullptr);
        };
        throw std::runtime_error(std::string(mode) + " width=" + std::to_string(width) +
            " observed=" + mismatch(actual).dump() + " expected=" + mismatch(oracle).dump());
    }
    json roles;
    for (size_t i = 0; i < maps.size(); ++i) roles[names[i]] = stats(actual, i);
    return {{"mode", mode}, {"width", width}, {"rank_elements", 4 * width},
            {"roles", roles}, {"total", stats(actual, -1)}};
}

static void registrations(bool enabled) {
    for (const auto &m : maps) {
        void *base = reinterpret_cast<void *>(m.base);
        if (enabled) ggml_moe_prefetch_register_mapping(base, m.size);
        else ggml_moe_prefetch_unregister_mapping(base);
    }
}

struct Nodes {
    std::vector<int32_t> values;
    ggml_tensor *ids;
    ggml_tensor *fused;
    std::array<ggml_tensor *, 3> separate;
    Nodes(ggml_context *ctx, int width) : values(4 * width) {
        ids = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, 4, width);
        require(ggml_nbytes(ids) == values.size() * sizeof(int32_t), "ID strides");
        ids->data = values.data();
        auto *x = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 2880, 1, width);
        auto *activated = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 2880, 4, width);
        for (size_t i = 0; i < maps.size(); ++i) {
            separate[i] = ggml_mul_mat_id(ctx, maps[i].weight, i == 2 ? activated : x, ids);
            require(separate[i]->op == GGML_OP_MUL_MAT_ID, "unexpected ordinary operation");
        }
        auto *up_bias = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, 2880, 128);
        auto *gate_bias = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, 2880, 128);
        fused = ggml_moe_up_gate_ext(ctx, maps[1].weight, maps[0].weight, x, ids,
                                     up_bias, gate_bias, GGML_UNARY_OP_SWIGLU_OAI);
        require(fused->op == GGML_OP_MOE_FUSED_UP_GATE &&
                fused->src[0] == maps[1].weight && fused->src[1] == maps[0].weight &&
                fused->src[3] == ids && fused->src[4] == up_bias && fused->src[5] == gate_bias,
                "fused operation topology");
        fill(ranks);
    }
    void fill(const std::array<int32_t, 4> &pattern) {
        for (size_t i = 0; i < values.size(); ++i) values[i] = pattern[i % 4];
    }
    void kernel(int ith) const {
        for (auto *node : separate) ggml_moe_prefetch_kernel_hook(node, ith);
    }
    void selective() const {
        for (auto *node : separate) ggml_moe_prefetch_node(node);
    }
    void full() const {
        for (const auto &m : maps) ggml_moe_prefetch_tensor(m.weight);
    }
};

static void start_pool() {
    const auto before = task_ids();
    probing = true;
    ggml_moe_prefetch_set_n_threads(4);
    probing = false;
    require(ggml_moe_prefetch_enabled() && probes == 1, "anonymous populate capability or wrap");
    const auto after = task_ids();
    std::set_difference(after.begin(), after.end(), before.begin(), before.end(),
                        std::inserter(readers, readers.end()));
    require(readers.size() == 4, "four distinct upstream worker tasks required");
}

static json run(int argc, char **argv) {
    require(argc == 4, "usage: ik-mapped-experts GATE_ABS_OFFSET UP_ABS_OFFSET DOWN_ABS_OFFSET");
    main_tid = static_cast<pid_t>(syscall(SYS_gettid));
    page = sysconf(_SC_PAGESIZE);
    require(page == 4096, "fixture requires the qualified 4096-byte page");
    auto *ctx = ggml_init({2 * 1024 * 1024, nullptr, true});
    require(ctx != nullptr, "GGML metadata arena");
    json weights;
    require(GGML_TYPE_MXFP4 == 39 && ggml_blck_size(GGML_TYPE_MXFP4) == 32 &&
            ggml_type_size(GGML_TYPE_MXFP4) == 17, "native MXFP4 format");
    for (size_t role = 0; role < maps.size(); ++role) {
        const char *s = argv[role + 1], *end = s + std::strlen(s);
        Bytes offset = 0;
        auto parsed = std::from_chars(s, end, offset);
        require(parsed.ec == std::errc{} && parsed.ptr == end &&
                offset == c283_offsets[role], "GGUF role offset does not match C283");
        auto *w = ggml_new_tensor_3d(ctx, GGML_TYPE_MXFP4, 2880, 2880, 128);
        require(w->data == nullptr && w->nb[0] == 17 && w->nb[1] == 1530 &&
                w->nb[2] == slab && ggml_is_contiguous(w) && ggml_nbytes(w) == tensor_bytes,
                "GGML MXFP4 tensor layout");
        Bytes shift = offset - floor_page(offset), size = ceil_page(shift + tensor_bytes);
        void *base = mmap(nullptr, size, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE,
                          -1, 0);
        require(base != MAP_FAILED, "cannot reserve tensor virtual range");
        maps[role] = {reinterpret_cast<uintptr_t>(base), size, floor_page(offset), w};
        w->data = static_cast<char *>(base) + shift;
        weights[names[role]] = {{"offset", offset}, {"ggml_nbytes", ggml_nbytes(w)},
                                {"ggml_nb2", w->nb[2]}, {"mapped_virtual_bytes", size}};
    }

    json cases = json::array();
    require(!ggml_moe_prefetch_enabled(), "unexpected pre-existing pool");
    for (int width : {1, 5, 20, 32}) {
        Nodes n(ctx, width);
        n.selective();
        cases.push_back(finish("pool_off_node", width, Coverage::none));
        n.kernel(0);
        cases.push_back(finish("pool_off_kernel_legacy", width, Coverage::selected, true));
    }
    start_pool();
    // Each width uses the same pool and the same synthetic routings. A new epoch
    // separates independent calls; consecutive steps intentionally share one.
    for (int width : {1, 5, 20, 32}) {
        Nodes n(ctx, width);
        ggml_moe_prefetch_new_epoch();
        n.kernel(0);
        cases.push_back(finish("unregistered", width, Coverage::none));
        registrations(true);
        n.kernel(1);
        cases.push_back(finish("nonzero_lane", width, Coverage::none));
        n.selective();
        cases.push_back(finish("selective", width, Coverage::selected));
        n.kernel(0);
        cases.push_back(finish("same_epoch_repeat", width, Coverage::none));
        ggml_moe_prefetch_new_epoch();
        n.kernel(0);
        cases.push_back(finish("reissued_new_epoch", width, Coverage::selected));

        ggml_moe_prefetch_new_epoch();
        n.full();
        n.selective();
        cases.push_back(finish("full_then_selective", width, Coverage::full));
        ggml_moe_prefetch_new_epoch();
        n.selective();
        n.full();
        cases.push_back(finish("selective_then_full", width, Coverage::selected));

        ggml_moe_prefetch_new_epoch();
        ggml_moe_prefetch_node(n.fused);
        cases.push_back(finish("separate_weights_fused_op", width, Coverage::selected, false, 2));
        ggml_moe_prefetch_new_epoch();
        n.fill(small);
        n.selective();
        cases.push_back(finish("small_duplicate_sentinel", width, Coverage::small_only));
        registrations(false);
    }
    ggml_moe_prefetch_set_n_threads(0);
    require(!ggml_moe_prefetch_enabled(), "pool failed to stop");
    for (const auto &m : maps)
        require(munmap(reinterpret_cast<void *>(m.base), m.size) == 0, "mapping cleanup");
    ggml_free(ctx);
    return {{"status", "PASS_IK_MAPPED_EXPERTS"}, {"workers", readers.size()}, {"page_bytes", page},
            {"capability", "real_anonymous_MADV_POPULATE_READ"}, {"resident_response", "all_cold"},
            {"tensor_syscalls", "wrapped_no_io"}, {"weights", weights},
            {"ids", ranks}, {"small_ids", small}, {"cases", cases}};
}

int main(int argc, char **argv) {
    try {
        auto result = run(argc, argv);
        std::cout << result.dump() << '\n';
        return 0;
    } catch (const std::exception &error) {
        ggml_moe_prefetch_set_n_threads(0);
        std::cerr << error.what() << '\n';
        return 1;
    }
}
