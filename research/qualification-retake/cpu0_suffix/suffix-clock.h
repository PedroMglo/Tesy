#pragma once
#include <iomanip>
#include <sstream>
#include <time.h>

// One graph and one custom task in each process. graph_compute and synchronize
// join the worker writing these fields before the main thread consumes them.
struct WaveClock {
    int64_t end_ns = 0;
    unsigned calls = 0;
    bool correct_task = false;
    int graph_team_size = 0;
};
static WaveClock wave_clock;

static int64_t monotonic_ns() {
    timespec now{};
    need(clock_gettime(CLOCK_MONOTONIC, &now) == 0, "CLOCK_MONOTONIC");
    return static_cast<int64_t>(now.tv_sec) * 1000000000 + now.tv_nsec;
}

static void timed_wave_ids(ggml_tensor *dst, int ith, int nth, void *userdata) {
    if (ith != 0) {
        llama_moe_stream_wave_ids(dst, ith, nth, userdata);
        return;
    }
    llama_moe_stream_wave_ids(dst, ith, nth, userdata);
    const int64_t end = monotonic_ns();
    wave_clock.end_ns = end;
    ++wave_clock.calls;
    const auto *wave = static_cast<llama_moe_stream_wave *>(userdata);
    wave_clock.graph_team_size = nth;
    wave_clock.correct_task = (nth >= 1 && nth <= 8 && wave && wave->wave == 0);
}

static bool valid_boundary(bool marked, const WaveClock &clock, int64_t start, int64_t end) {
    if (start <= 0 || end <= start) return false;
    if (!marked) return clock.calls == 0 && clock.end_ns == 0 && !clock.correct_task;
    return clock.calls == 1 && clock.correct_task && start < clock.end_ns && clock.end_ns < end;
}

struct GraphInputs {
    llama_moe_stream_layer *layer = nullptr;
    std::array<ggml_tensor *, 3> weights{};
    std::map<ggml_tensor *, std::pair<int, int>> mmids;
};

// Equality across arms checks types, shapes, strides, view offsets, source
// ordering and weight identities. The one experimental function pointer is
// intentionally excluded, as are process addresses.
class Fingerprint {
    uint64_t value = UINT64_C(14695981039346656037);
public:
    void add(uint64_t v) {
        for (unsigned n=0; n<8; ++n) {
            value ^= (v >> (8*n)) & 255;
            value *= UINT64_C(1099511628211);
        }
    }
    std::string finish() const {
        std::ostringstream stream;
        stream << std::hex << std::setfill('0') << std::setw(16) << value;
        return stream.str();
    }
};

static std::string fingerprint(ggml_cgraph *graph, const GraphInputs &inputs) {
    std::map<const ggml_tensor *, size_t> keys;
    auto key = [&](const ggml_tensor *node) -> size_t {
        if (!node) return 0;
        return keys.emplace(node, keys.size()+1).first->second;
    };
    for (auto *weight : inputs.weights) key(weight);
    const int count = ggml_graph_n_nodes(graph);
    for (int i=0; i<count; ++i) key(ggml_graph_node(graph, i));
    Fingerprint signature;
    signature.add(count);
    for (int i=0; i<count; ++i) {
        const auto *node = ggml_graph_node(graph, i);
        signature.add(key(node));
        signature.add(node->op);
        signature.add(node->type);
        for (int d=0; d<GGML_MAX_DIMS; ++d) {
            signature.add(node->ne[d]);
            signature.add(node->nb[d]);
        }
        signature.add(key(node->view_src));
        signature.add(node->view_offs);
        for (auto *src : node->src) signature.add(key(src));
    }
    return signature.finish();
}

static void counterexamples() {
    need(valid_boundary(false, {}, 1, 5), "unmarked control");
    need(valid_boundary(true, {3, 1, true}, 1, 5), "positive marker");
    need(!valid_boundary(false, {3, 1, true}, 1, 5) &&
         !valid_boundary(true, {3, 2, true}, 1, 5) &&
         !valid_boundary(true, {3, 1, false}, 1, 5) &&
         !valid_boundary(true, {1, 1, true}, 1, 5) &&
         !valid_boundary(true, {5, 1, true}, 1, 5), "boundary negative controls");
    Fingerprint a, b;
    a.add(3); a.add(4); b.add(4); b.add(3);
    need(a.finish() != b.finish(), "edge order negative control");
}
