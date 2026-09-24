#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"
#include "ggml-impl.h"
#include "gguf.h"
#include "llama.h"
#include "tesy_static_residency.h"
#include "tesy_sum_graph.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cinttypes>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <limits>
#include <memory>
#include <numeric>
#include <string>
#include <thread>
#include <unordered_set>
#include <utility>
#include <vector>

extern "C" void llama_tesy_set_graph_compute_hook(
    llama_context *, ggml_status (*)(ggml_cgraph *, ggml_backend_sched_t,
                                     ggml_backend_t, void *), void *)
    __attribute__((weak));

namespace {

constexpr int64_t k_embd = 2880;
constexpr int64_t k_expert_count = 32;
constexpr int k_top_k = 4;
constexpr size_t k_encoded_bytes_per_expert = 13253760;
constexpr float k_swiglu_alpha = 1.702f;
constexpr float k_swiglu_limit = 7.0f;
constexpr float k_mix_weight = 0.25f;
constexpr llama_token k_live_handoff_decode_token = 2167;

struct options {
    std::string model;
    std::string output;
    int layer = 0;
    int threads = 12;
    int warmup = 3;
    int samples = 21;
    int inner = 5;
    bool async_overlap = false;
    bool routed_exactness = false;
    bool live_handoff_exactness = false;
    bool live_handoff_timing = false;
    bool live_reinjection_exactness = false;
    bool split_graph_skip_exactness = false;
    bool vertical_live_exactness = false;
    int vertical_layers = 24;
    int vertical_tokens = 4;
    std::string split_arm;
    std::string prompt_file;
    std::string timing_start_gate;
    std::string routed_input_f32;
    std::string routed_reference_f32;
    std::string routed_experts_csv;
    std::string routed_weights_csv;
    int routed_gpu_hits = -1;
    uint32_t live_ctx = 4096;
};

struct context_buffer {
    ggml_context * ctx = nullptr;
    ggml_backend_buffer_t buffer = nullptr;

    context_buffer() = default;
    context_buffer(const context_buffer &) = delete;
    context_buffer & operator=(const context_buffer &) = delete;

    ~context_buffer() {
        if (buffer) {
            ggml_backend_buffer_free(buffer);
        }
        if (ctx) {
            ggml_free(ctx);
        }
    }
};

struct backend_handle {
    ggml_backend_t backend = nullptr;

    ~backend_handle() {
        if (backend) {
            ggml_backend_free(backend);
        }
    }
};

struct tensor_spec {
    std::string name;
    ggml_type type = GGML_TYPE_COUNT;
    size_t absolute_offset = 0;
    size_t per_expert_bytes = 0;
};

struct tensor_bytes {
    std::vector<uint8_t> gate_w;
    std::vector<uint8_t> up_w;
    std::vector<uint8_t> down_w;
    std::vector<uint8_t> gate_b;
    std::vector<uint8_t> up_b;
    std::vector<uint8_t> down_b;

    size_t total() const {
        return gate_w.size() + up_w.size() + down_w.size() +
               gate_b.size() + up_b.size() + down_b.size();
    }
};

struct tensor_set {
    context_buffer weights;
    context_buffer biases;
    ggml_tensor * gate_w = nullptr;
    ggml_tensor * up_w = nullptr;
    ggml_tensor * down_w = nullptr;
    ggml_tensor * gate_b = nullptr;
    ggml_tensor * up_b = nullptr;
    ggml_tensor * down_b = nullptr;
};

struct compute_graph {
    context_buffer storage;
    ggml_cgraph * graph = nullptr;
    ggml_tensor * input = nullptr;
    ggml_tensor * ids = nullptr;
    ggml_tensor * mix = nullptr;
    ggml_tensor * output = nullptr;
};

struct tensor_holder {
    context_buffer storage;
    ggml_tensor * tensor = nullptr;
};

struct sum_graph {
    context_buffer storage;
    ggml_cgraph * graph = nullptr;
    ggml_tensor * gpu_partial = nullptr;
    ggml_tensor * cpu_partial = nullptr;
    ggml_tensor * output = nullptr;
};

struct stats {
    std::vector<double> samples_ms;
    double median_ms = 0.0;
    double p95_ms = 0.0;
    double min_ms = 0.0;
    double max_ms = 0.0;
    double mean_ms = 0.0;
};

struct parity {
    double max_abs = 0.0;
    double max_abs_ref = 0.0;
    double relative_max = 0.0;
    double cosine = 0.0;
    bool pass = false;
};

struct routed_exactness_result {
    int gpu_hits = 0;
    int cpu_misses = 0;
    parity serial_vs_stock;
    parity async_vs_stock;
    parity async_vs_serial;
};

enum class live_handoff_arm {
    stock_reference,
    handoff,
};

struct live_handoff_capture {
    bool enabled = false;
    live_handoff_arm arm = live_handoff_arm::stock_reference;
    bool saw_activation = false;
    bool saw_experts = false;
    bool saw_weights = false;
    bool saw_stock_output = false;
    std::vector<float> activation;
    std::vector<int32_t> experts;
    std::vector<float> weights;
    std::vector<float> stock_output;
};

struct live_handoff_result {
    llama_token decode_input_token = -1;
    int stock_decode_return_code = -1;
    int handoff_decode_return_code = -1;
    bool stock_rollback = false;
    bool handoff_rollback = false;
    bool activation_bitwise_equal = false;
    parity activation_parity;
    std::vector<int> selected_experts;
    std::vector<float> routing_weights;
    std::vector<routed_exactness_result> cases;
};

enum class live_timing_mode {
    stock,
    serial,
    async,
};

struct live_timing_capture {
    bool enabled = false;
    live_timing_mode mode = live_timing_mode::stock;
    bool capture_stock_output = false;
    bool saw_activation = false;
    bool saw_experts = false;
    bool saw_weights = false;
    bool saw_stock_output = false;
    std::vector<float> activation;
    std::vector<int32_t> experts;
    std::vector<float> weights;
    std::vector<float> stock_output;
    const std::vector<float> * expected_activation = nullptr;
    const std::vector<int> * expected_experts = nullptr;
    const std::vector<float> * expected_weights = nullptr;
    std::chrono::steady_clock::time_point activation_ready;
    std::chrono::steady_clock::time_point route_ready;
    std::chrono::steady_clock::time_point stock_output_ready;
};

struct live_timing_samples {
    std::vector<double> activation_ms;
    std::vector<double> route_ms;
};

struct live_timing_exactness_snapshot {
    int stock_decode_return_code = -1;
    int handoff_decode_return_code = -1;
    bool stock_rollback = false;
    bool handoff_rollback = false;
    bool activation_bitwise_equal = false;
    parity activation_parity;
    parity activation_vs_reference;
    parity stock_output_vs_reference;
    parity serial_vs_stock;
    parity async_vs_stock;
    parity async_vs_serial;
};

struct live_timing_reference {
    std::vector<float> activation;
    std::vector<int> selected_experts;
    std::vector<float> routing_weights;
    std::vector<float> stock_output;
};

struct live_routed_executor {
    int gpu_hits = 0;
    int cpu_misses = 0;
    std::unique_ptr<tensor_set> cpu_set;
    std::unique_ptr<tensor_set> gpu_set;
    std::unique_ptr<compute_graph> cpu_graph;
    std::unique_ptr<compute_graph> gpu_graph;
    std::unique_ptr<sum_graph> aggregate;
};

struct live_handoff_timing_result {
    int gpu_hits = 0;
    int cpu_misses = 0;
    llama_token decode_input_token = -1;
    std::vector<int> selected_experts;
    std::vector<float> routing_weights;
    live_timing_exactness_snapshot pre_exactness;
    live_timing_exactness_snapshot post_exactness;
    live_timing_samples stock;
    live_timing_samples serial;
    live_timing_samples async;
    int completed_stock_trials = 0;
    int completed_serial_trials = 0;
    int completed_async_trials = 0;
    int successful_timing_trial_rollbacks = 0;
};

struct case_result {
    int gpu_hits = 0;
    int cpu_misses = 0;
    stats direct_wall;
    bool has_async_wall = false;
    stats async_wall;
    parity async_parity;
    bool has_activation_d2h = false;
    stats activation_d2h;
    bool has_cpu_compute = false;
    stats cpu_compute;
    bool has_gpu_compute = false;
    stats gpu_compute;
    bool has_cpu_partial_h2d = false;
    stats cpu_partial_h2d;
    bool has_gpu_aggregation = false;
    stats gpu_aggregation;
    double component_sum_median_ms = 0.0;
    double overlap_bound_median_ms = 0.0;
    parity output_parity;
};

[[noreturn]] void fail(const std::string & message) {
    std::fprintf(stderr, "%s\n", message.c_str());
    std::exit(2);
}

int parse_positive(const char * value, const char * flag, int minimum = 1) {
    char * end = nullptr;
    const long parsed = std::strtol(value, &end, 10);
    if (!end || end == value || *end != '\0' || parsed < minimum ||
        parsed > std::numeric_limits<int>::max()) {
        fail(std::string("invalid ") + flag + ": " + value);
    }
    return static_cast<int>(parsed);
}

[[noreturn]] void usage(const char * argv0, int code) {
    std::fprintf(
        code == 0 ? stdout : stderr,
        "usage: %s --model MODEL.gguf --output RESULT.json "
        "[--layer N] [--threads N] [--samples N] [--warmup N] [--inner N] "
        "[--async-overlap] [--routed-exactness "
        "--routed-input-f32 FILE --routed-reference-f32 FILE "
        "--routed-experts CSV --routed-weights CSV --routed-gpu-hits N] "
        "[--live-handoff-exactness --prompt-file FILE --ctx N] "
        "[--live-handoff-timing --prompt-file FILE --ctx N "
        "--routed-gpu-hits N --warmup 6 --samples 81 --inner 1 "
        "--timing-start-gate FILE] "
        "[--live-reinjection-exactness --prompt-file FILE --ctx 4096] "
        "[--split-graph-skip-exactness --split-arm ARM --prompt-file FILE --ctx 4096] "
        "[--vertical-live-exactness --vertical-layers 1..24 --vertical-tokens N "
        "--prompt-file FILE --ctx 4096]\n",
        argv0);
    std::exit(code);
}

options parse_options(int argc, char ** argv) {
    options out;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto value = [&](const char * flag) -> const char * {
            if (i + 1 >= argc) {
                fail(std::string("missing value for ") + flag);
            }
            return argv[++i];
        };
        if (arg == "--model") {
            out.model = value("--model");
        } else if (arg == "--output") {
            out.output = value("--output");
        } else if (arg == "--layer") {
            out.layer = parse_positive(value("--layer"), "--layer", 0);
        } else if (arg == "--threads") {
            out.threads = parse_positive(value("--threads"), "--threads");
        } else if (arg == "--samples") {
            out.samples = parse_positive(value("--samples"), "--samples");
        } else if (arg == "--warmup") {
            out.warmup = parse_positive(value("--warmup"), "--warmup", 0);
        } else if (arg == "--inner") {
            out.inner = parse_positive(value("--inner"), "--inner");
        } else if (arg == "--async-overlap") {
            out.async_overlap = true;
        } else if (arg == "--routed-exactness") {
            out.routed_exactness = true;
        } else if (arg == "--live-handoff-exactness") {
            out.live_handoff_exactness = true;
        } else if (arg == "--live-handoff-timing") {
            out.live_handoff_timing = true;
        } else if (arg == "--live-reinjection-exactness") {
            out.live_reinjection_exactness = true;
        } else if (arg == "--split-graph-skip-exactness") {
            out.split_graph_skip_exactness = true;
        } else if (arg == "--vertical-live-exactness") {
            out.vertical_live_exactness = true;
        } else if (arg == "--vertical-layers") {
            out.vertical_layers = parse_positive(value("--vertical-layers"), "--vertical-layers");
        } else if (arg == "--vertical-tokens") {
            out.vertical_tokens = parse_positive(value("--vertical-tokens"), "--vertical-tokens");
        } else if (arg == "--split-arm") {
            out.split_arm = value("--split-arm");
        } else if (arg == "--prompt-file") {
            out.prompt_file = value("--prompt-file");
        } else if (arg == "--timing-start-gate") {
            out.timing_start_gate = value("--timing-start-gate");
        } else if (arg == "--ctx") {
            out.live_ctx = static_cast<uint32_t>(
                parse_positive(value("--ctx"), "--ctx", 16));
        } else if (arg == "--routed-input-f32") {
            out.routed_input_f32 = value("--routed-input-f32");
        } else if (arg == "--routed-reference-f32") {
            out.routed_reference_f32 = value("--routed-reference-f32");
        } else if (arg == "--routed-experts") {
            out.routed_experts_csv = value("--routed-experts");
        } else if (arg == "--routed-weights") {
            out.routed_weights_csv = value("--routed-weights");
        } else if (arg == "--routed-gpu-hits") {
            out.routed_gpu_hits =
                parse_positive(
                    value("--routed-gpu-hits"),
                    "--routed-gpu-hits");
        } else if (arg == "-h" || arg == "--help") {
            usage(argv[0], 0);
        } else {
            fail("unknown argument: " + arg);
        }
    }
    if (out.model.empty() || out.output.empty()) {
        usage(argv[0], 2);
    }
    const int special_modes =
        static_cast<int>(out.routed_exactness)
        + static_cast<int>(out.live_handoff_exactness)
        + static_cast<int>(out.live_handoff_timing)
        + static_cast<int>(out.live_reinjection_exactness)
        + static_cast<int>(out.split_graph_skip_exactness)
        + static_cast<int>(out.vertical_live_exactness);
    if (special_modes > 1) {
        fail("routed/live exactness/timing modes are mutually exclusive");
    }
    if (out.routed_exactness) {
        if (!out.async_overlap) {
            fail("--routed-exactness requires --async-overlap");
        }
        if (out.layer != 0) {
            fail("routed exactness is frozen to layer 0");
        }
        if (
            out.routed_input_f32.empty()
            || out.routed_reference_f32.empty()
            || out.routed_experts_csv.empty()
            || out.routed_weights_csv.empty()
        ) {
            fail("routed exactness requires input/reference/experts/weights");
        }
        if (out.routed_gpu_hits != 2 && out.routed_gpu_hits != 3) {
            fail("routed exactness gpu hits must be 2 or 3");
        }
    }
    if (out.live_handoff_exactness) {
        if (out.layer != 0) {
            fail("live handoff exactness is frozen to layer 0");
        }
        if (out.prompt_file.empty()) {
            fail("live handoff exactness requires --prompt-file");
        }
        if (out.live_ctx != 4096) {
            fail("live handoff exactness is frozen to --ctx 4096");
        }
    }
    if (out.live_handoff_timing) {
        if (out.layer != 0) {
            fail("live handoff timing is frozen to layer 0");
        }
        if (out.prompt_file.empty()) {
            fail("live handoff timing requires --prompt-file");
        }
        if (out.live_ctx != 4096) {
            fail("live handoff timing is frozen to --ctx 4096");
        }
        if (out.routed_gpu_hits != 2 && out.routed_gpu_hits != 3) {
            fail("live handoff timing gpu hits must be 2 or 3");
        }
        if (out.warmup != 6 || out.samples != 81 || out.inner != 1) {
            fail(
                "live handoff timing requires --warmup 6 "
                "--samples 81 --inner 1");
        }
        if (out.timing_start_gate.empty()) {
            fail("live handoff timing requires --timing-start-gate");
        }
    }
    if (out.live_reinjection_exactness) {
        if (out.layer != 0 || out.live_ctx != 4096 || out.prompt_file.empty()) {
            fail("live reinjection requires layer 0, --ctx 4096 and --prompt-file");
        }
        if (out.async_overlap || out.routed_gpu_hits != -1 || !out.timing_start_gate.empty()) {
            fail("live reinjection forbids async, routed GPU hits and timing gate");
        }
    }
    if (out.split_graph_skip_exactness) {
        if (out.layer != 0 || out.live_ctx != 4096 || out.prompt_file.empty() ||
            out.async_overlap || out.routed_gpu_hits != -1 ||
            !out.timing_start_gate.empty()) {
            fail("split graph skip requires layer 0, --ctx 4096, prompt and no async/timing");
        }
        if (out.split_arm != "stock" && out.split_arm != "null" &&
            out.split_arm != "segmented" && out.split_arm != "skip-stock" &&
            out.split_arm != "h2" && out.split_arm != "h3") {
            fail("invalid --split-arm");
        }
    } else if (!out.split_arm.empty()) {
        fail("--split-arm requires --split-graph-skip-exactness");
    }
    if (out.vertical_live_exactness) {
        if (out.live_ctx != 4096 || out.prompt_file.empty() ||
            out.vertical_layers > 24 || out.vertical_tokens > 128 ||
            out.async_overlap || out.routed_gpu_hits != -1 ||
            !out.timing_start_gate.empty()) {
            fail("vertical live requires --ctx 4096, prompt, 1..24 layers, "
                 "1..128 tokens and no async/timing");
        }
    }
    return out;
}

ggml_context * make_context(size_t bytes = 16u * 1024u * 1024u) {
    ggml_init_params params = {
        /* .mem_size   = */ bytes,
        /* .mem_buffer = */ nullptr,
        /* .no_alloc   = */ true,
    };
    ggml_context * ctx = ggml_init(params);
    if (!ctx) {
        fail("ggml_init failed");
    }
    return ctx;
}

tensor_spec get_spec(
        gguf_context * gguf,
        ggml_context * meta,
        const std::string & name,
        ggml_type expected_type,
        const std::vector<int64_t> & expected_shape) {
    const int64_t id = gguf_find_tensor(gguf, name.c_str());
    if (id < 0) {
        fail("missing GGUF tensor: " + name);
    }
    ggml_tensor * tensor = ggml_get_tensor(meta, name.c_str());
    if (!tensor) {
        fail("missing GGML metadata tensor: " + name);
    }
    const ggml_type type = gguf_get_tensor_type(gguf, id);
    if (type != expected_type) {
        fail("unexpected tensor type for " + name + ": " + ggml_type_name(type));
    }
    const int n_dims = ggml_n_dims(tensor);
    if (n_dims != static_cast<int>(expected_shape.size())) {
        fail("unexpected tensor rank for " + name);
    }
    for (int i = 0; i < n_dims; ++i) {
        if (tensor->ne[i] != expected_shape[static_cast<size_t>(i)]) {
            fail("unexpected tensor shape for " + name);
        }
    }

    const size_t n_bytes = gguf_get_tensor_size(gguf, id);
    if (n_bytes == 0 || n_bytes % static_cast<size_t>(k_expert_count) != 0) {
        fail("tensor bytes do not divide by expert count for " + name);
    }
    const size_t per_expert =
        n_bytes / static_cast<size_t>(k_expert_count);
    if (
        tensor->ne[n_dims - 1] != k_expert_count
        || tensor->nb[n_dims - 1] != per_expert
    ) {
        fail("expert slices are not contiguous on final GGUF dimension for " + name);
    }

    const size_t base = gguf_get_data_offset(gguf);
    const size_t relative = gguf_get_tensor_offset(gguf, id);
    if (relative > std::numeric_limits<size_t>::max() - base) {
        fail("tensor offset overflow for " + name);
    }
    return tensor_spec{name, type, base + relative, per_expert};
}

std::vector<uint8_t> read_subset(
        std::ifstream & file,
        const tensor_spec & spec,
        const std::vector<int> & source_ids) {
    std::vector<uint8_t> out(
        spec.per_expert_bytes * source_ids.size());
    for (size_t local = 0; local < source_ids.size(); ++local) {
        const int source_id = source_ids[local];
        if (source_id < 0 || source_id >= k_expert_count) {
            fail("source expert id out of range");
        }
        const size_t offset =
            spec.absolute_offset +
            spec.per_expert_bytes * static_cast<size_t>(source_id);
        file.clear();
        file.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
        if (!file.good()) {
            fail("seek failed for " + spec.name);
        }
        file.read(
            reinterpret_cast<char *>(
                out.data() + local * spec.per_expert_bytes),
            static_cast<std::streamsize>(spec.per_expert_bytes));
        if (file.gcount() != static_cast<std::streamsize>(spec.per_expert_bytes)) {
            fail("short read for " + spec.name);
        }
    }
    return out;
}

tensor_bytes load_subset(
        const std::string & model,
        int layer,
        const std::vector<int> & source_ids) {
    if (source_ids.empty()) {
        fail("expert subset must not be empty");
    }

    ggml_context * meta = nullptr;
    gguf_init_params params = {
        /* .no_alloc = */ true,
        /* .ctx      = */ &meta,
    };
    gguf_context * gguf = gguf_init_from_file(model.c_str(), params);
    if (!gguf || !meta) {
        if (meta) {
            ggml_free(meta);
        }
        if (gguf) {
            gguf_free(gguf);
        }
        fail("failed to read GGUF metadata");
    }

    const std::string prefix = "blk." + std::to_string(layer) + ".";
    const std::vector<int64_t> weight_shape = {k_embd, k_embd, k_expert_count};
    const std::vector<int64_t> bias_shape = {k_embd, k_expert_count};

    const tensor_spec gate_w = get_spec(
        gguf, meta, prefix + "ffn_gate_exps.weight",
        GGML_TYPE_MXFP4, weight_shape);
    const tensor_spec up_w = get_spec(
        gguf, meta, prefix + "ffn_up_exps.weight",
        GGML_TYPE_MXFP4, weight_shape);
    const tensor_spec down_w = get_spec(
        gguf, meta, prefix + "ffn_down_exps.weight",
        GGML_TYPE_MXFP4, weight_shape);
    const tensor_spec gate_b = get_spec(
        gguf, meta, prefix + "ffn_gate_exps.bias",
        GGML_TYPE_F32, bias_shape);
    const tensor_spec up_b = get_spec(
        gguf, meta, prefix + "ffn_up_exps.bias",
        GGML_TYPE_F32, bias_shape);
    const tensor_spec down_b = get_spec(
        gguf, meta, prefix + "ffn_down_exps.bias",
        GGML_TYPE_F32, bias_shape);

    const size_t one_expert =
        gate_w.per_expert_bytes + up_w.per_expert_bytes +
        down_w.per_expert_bytes + gate_b.per_expert_bytes +
        up_b.per_expert_bytes + down_b.per_expert_bytes;
    if (one_expert != k_encoded_bytes_per_expert) {
        ggml_free(meta);
        gguf_free(gguf);
        fail("encoded expert bytes mismatch");
    }

    std::ifstream file(model, std::ios::binary);
    if (!file) {
        ggml_free(meta);
        gguf_free(gguf);
        fail("cannot open model");
    }

    tensor_bytes result;
    result.gate_w = read_subset(file, gate_w, source_ids);
    result.up_w = read_subset(file, up_w, source_ids);
    result.down_w = read_subset(file, down_w, source_ids);
    result.gate_b = read_subset(file, gate_b, source_ids);
    result.up_b = read_subset(file, up_b, source_ids);
    result.down_b = read_subset(file, down_b, source_ids);

    ggml_free(meta);
    gguf_free(gguf);

    const size_t expected =
        k_encoded_bytes_per_expert * source_ids.size();
    if (result.total() != expected) {
        fail("compact expert payload bytes mismatch");
    }
    return result;
}

bool supports_cpu_weight_buft(
        ggml_backend_dev_t cpu_dev,
        ggml_backend_buffer_type_t buft,
        int count) {
    ggml_context * ctx = make_context(1024u * 1024u);
    ggml_tensor * weight =
        ggml_new_tensor_3d(ctx, GGML_TYPE_MXFP4, k_embd, k_embd, count);
    ggml_tensor * input =
        ggml_new_tensor_3d(ctx, GGML_TYPE_F32, k_embd, 1, 1);
    ggml_tensor * ids =
        ggml_new_tensor_2d(ctx, GGML_TYPE_I32, count, 1);

    ggml_backend_buffer_t dummy =
        ggml_backend_buft_alloc_buffer(buft, 0);
    if (!dummy) {
        ggml_free(ctx);
        return false;
    }
    weight->buffer = dummy;
    ggml_tensor * op =
        ggml_mul_mat_id(ctx, weight, input, ids);
    const bool supported =
        ggml_backend_dev_supports_op(cpu_dev, op);
    weight->buffer = nullptr;
    ggml_backend_buffer_free(dummy);
    ggml_free(ctx);
    return supported;
}

ggml_backend_buffer_type_t select_cpu_compute_weight_buft(
        ggml_backend_dev_t cpu_dev) {
    std::vector<ggml_backend_buffer_type_t> candidates;

    auto * reg = ggml_backend_dev_backend_reg(cpu_dev);
    auto fn = reinterpret_cast<ggml_backend_dev_get_extra_bufts_t>(
        ggml_backend_reg_get_proc_address(
            reg, "ggml_backend_dev_get_extra_bufts"));
    if (fn) {
        ggml_backend_buffer_type_t * extra = fn(cpu_dev);
        while (extra && *extra) {
            candidates.push_back(*extra);
            ++extra;
        }
    }
    candidates.push_back(
        ggml_backend_dev_buffer_type(cpu_dev));

    for (ggml_backend_buffer_type_t buft : candidates) {
        if (!buft) {
            continue;
        }
        bool all_counts_supported = true;
        for (int count = 1; count <= k_top_k; ++count) {
            if (!supports_cpu_weight_buft(
                    cpu_dev, buft, count)) {
                all_counts_supported = false;
                break;
            }
        }
        if (all_counts_supported) {
            return buft;
        }
    }

    fail(
        "no CPU backend buffer type supports MXFP4 MUL_MAT_ID "
        "for compact expert counts 1..4");
}

std::unique_ptr<tensor_set> make_tensor_set(
        const tensor_bytes & data,
        int count,
        ggml_backend_buffer_type_t weight_buft,
        ggml_backend_buffer_type_t bias_buft) {
    if (count <= 0 || count > k_top_k) {
        fail("invalid compact expert count");
    }
    auto result = std::make_unique<tensor_set>();
    result->weights.ctx = make_context();
    result->biases.ctx = make_context();

    result->gate_w = ggml_new_tensor_3d(
        result->weights.ctx, GGML_TYPE_MXFP4, k_embd, k_embd, count);
    result->up_w = ggml_new_tensor_3d(
        result->weights.ctx, GGML_TYPE_MXFP4, k_embd, k_embd, count);
    result->down_w = ggml_new_tensor_3d(
        result->weights.ctx, GGML_TYPE_MXFP4, k_embd, k_embd, count);

    result->gate_b =
        ggml_new_tensor_2d(result->biases.ctx, GGML_TYPE_F32, k_embd, count);
    result->up_b =
        ggml_new_tensor_2d(result->biases.ctx, GGML_TYPE_F32, k_embd, count);
    result->down_b =
        ggml_new_tensor_2d(result->biases.ctx, GGML_TYPE_F32, k_embd, count);

    result->weights.buffer =
        ggml_backend_alloc_ctx_tensors_from_buft(result->weights.ctx, weight_buft);
    result->biases.buffer =
        ggml_backend_alloc_ctx_tensors_from_buft(result->biases.ctx, bias_buft);
    if (!result->weights.buffer || !result->biases.buffer) {
        fail("failed to allocate compact expert tensors");
    }

    const std::array<std::pair<ggml_tensor *, const std::vector<uint8_t> *>, 6> rows = {{
        {result->gate_w, &data.gate_w},
        {result->up_w, &data.up_w},
        {result->down_w, &data.down_w},
        {result->gate_b, &data.gate_b},
        {result->up_b, &data.up_b},
        {result->down_b, &data.down_b},
    }};
    for (const auto & row : rows) {
        if (ggml_nbytes(row.first) != row.second->size()) {
            fail("tensor bytes mismatch while populating compact expert set");
        }
        ggml_backend_tensor_set(
            row.first, row.second->data(), 0, row.second->size());
    }
    return result;
}

std::unique_ptr<compute_graph> make_compute_graph(
        tensor_set & tensors,
        ggml_backend_t backend,
        int count,
        const std::vector<float> & input_values,
        const std::vector<float> * mix_values = nullptr) {
    auto result = std::make_unique<compute_graph>();
    result->storage.ctx = make_context();
    ggml_context * ctx = result->storage.ctx;

    result->input =
        ggml_new_tensor_3d(ctx, GGML_TYPE_F32, k_embd, 1, 1);
    result->ids =
        ggml_new_tensor_2d(ctx, GGML_TYPE_I32, count, 1);
    result->mix =
        ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 1, count, 1);

    ggml_tensor * up =
        ggml_mul_mat_id(ctx, tensors.up_w, result->input, result->ids);
    up = ggml_add_id(ctx, up, tensors.up_b, result->ids);

    ggml_tensor * gate =
        ggml_mul_mat_id(ctx, tensors.gate_w, result->input, result->ids);
    gate = ggml_add_id(ctx, gate, tensors.gate_b, result->ids);

    ggml_tensor * act =
        ggml_swiglu_oai(ctx, gate, up, k_swiglu_alpha, k_swiglu_limit);

    ggml_tensor * down =
        ggml_mul_mat_id(ctx, tensors.down_w, act, result->ids);
    down = ggml_add_id(ctx, down, tensors.down_b, result->ids);
    down = ggml_mul(ctx, down, result->mix);

    ggml_tensor * sum = nullptr;
    for (int expert = 0; expert < count; ++expert) {
        ggml_tensor * view = ggml_view_2d(
            ctx,
            down,
            k_embd,
            1,
            down->nb[2],
            static_cast<size_t>(expert) * down->nb[1]);
        sum = sum ? ggml_add(ctx, sum, view) : view;
    }
    result->output = ggml_cont(ctx, sum);
    result->graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(result->graph, result->output);

    result->storage.buffer =
        ggml_backend_alloc_ctx_tensors(ctx, backend);
    if (!result->storage.buffer) {
        fail("failed to allocate compact expert graph");
    }

    ggml_backend_tensor_set(
        result->input,
        input_values.data(),
        0,
        input_values.size() * sizeof(float));

    std::vector<int32_t> ids(static_cast<size_t>(count));
    std::iota(ids.begin(), ids.end(), 0);
    ggml_backend_tensor_set(
        result->ids,
        ids.data(),
        0,
        ids.size() * sizeof(int32_t));

    std::vector<float> mix;
    if (mix_values) {
        mix = *mix_values;
        if (mix.size() != static_cast<size_t>(count)) {
            fail("routing weight count does not match compact expert count");
        }
        for (float value : mix) {
            if (!std::isfinite(value) || value < 0.0f) {
                fail("routing weights must be finite and non-negative");
            }
        }
    } else {
        mix.assign(static_cast<size_t>(count), k_mix_weight);
    }
    ggml_backend_tensor_set(
        result->mix,
        mix.data(),
        0,
        mix.size() * sizeof(float));

    ggml_backend_synchronize(backend);
    return result;
}

std::unique_ptr<tensor_holder> make_gpu_tensor(
        ggml_backend_t gpu_backend,
        const std::vector<float> * initial = nullptr) {
    auto result = std::make_unique<tensor_holder>();
    result->storage.ctx = make_context(1024u * 1024u);
    result->tensor =
        ggml_new_tensor_2d(result->storage.ctx, GGML_TYPE_F32, k_embd, 1);
    result->storage.buffer =
        ggml_backend_alloc_ctx_tensors(result->storage.ctx, gpu_backend);
    if (!result->storage.buffer) {
        fail("failed to allocate GPU tensor");
    }
    if (initial) {
        ggml_backend_tensor_set(
            result->tensor,
            initial->data(),
            0,
            initial->size() * sizeof(float));
        ggml_backend_synchronize(gpu_backend);
    }
    return result;
}

std::unique_ptr<sum_graph> make_sum_graph(
        ggml_backend_t gpu_backend) {
    auto result = std::make_unique<sum_graph>();
    result->storage.ctx = make_context(1024u * 1024u);
    ggml_context * ctx = result->storage.ctx;
    const auto nodes = tesy_make_leaf_sum_nodes(ctx, k_embd);
    result->gpu_partial = nodes.gpu_partial;
    result->cpu_partial = nodes.cpu_partial;
    result->output = nodes.output;
    result->graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(result->graph, result->output);
    result->storage.buffer =
        ggml_backend_alloc_ctx_tensors(ctx, gpu_backend);
    if (!result->storage.buffer) {
        fail("failed to allocate GPU aggregation graph");
    }
    return result;
}

void compute(ggml_backend_t backend, compute_graph & graph) {
    const ggml_status status =
        ggml_backend_graph_compute(backend, graph.graph);
    if (status != GGML_STATUS_SUCCESS) {
        fail("ggml_backend_graph_compute failed");
    }
    ggml_backend_synchronize(backend);
}

void compute_async_start(ggml_backend_t backend, compute_graph & graph) {
    const ggml_status status =
        ggml_backend_graph_compute_async(backend, graph.graph);
    if (status != GGML_STATUS_SUCCESS) {
        fail("ggml_backend_graph_compute_async failed");
    }
}

void compute_sum(ggml_backend_t backend, sum_graph & graph) {
    const ggml_status status =
        ggml_backend_graph_compute(backend, graph.graph);
    if (status != GGML_STATUS_SUCCESS) {
        fail("GPU aggregation graph compute failed");
    }
    ggml_backend_synchronize(backend);
}

std::vector<float> read_output(
        ggml_backend_t backend,
        ggml_tensor * tensor) {
    ggml_backend_synchronize(backend);
    std::vector<float> values(static_cast<size_t>(k_embd));
    ggml_backend_tensor_get(
        tensor, values.data(), 0, values.size() * sizeof(float));
    return values;
}

std::string read_prompt_file(const std::string & path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        fail("cannot open prompt file: " + path);
    }
    return std::string(
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>());
}

std::vector<llama_token> tokenize_prompt(
        const llama_vocab * vocab,
        const std::string & text) {
    const int32_t required =
        -llama_tokenize(
            vocab,
            text.c_str(),
            static_cast<int32_t>(text.size()),
            nullptr,
            0,
            true,
            true);
    if (required <= 0) {
        fail("live handoff tokenization sizing failed");
    }

    std::vector<llama_token> tokens(static_cast<size_t>(required));
    const int32_t written =
        llama_tokenize(
            vocab,
            text.c_str(),
            static_cast<int32_t>(text.size()),
            tokens.data(),
            static_cast<int32_t>(tokens.size()),
            true,
            true);
    if (written <= 0 || written > required) {
        fail("live handoff tokenization failed");
    }
    tokens.resize(static_cast<size_t>(written));
    return tokens;
}

template <typename T>
std::vector<T> read_live_tensor(
        ggml_tensor * tensor,
        ggml_type expected_type,
        size_t expected_elements,
        const char * label) {
    if (tensor->type != expected_type) {
        fail(std::string(label) + " has unexpected tensor type");
    }
    if (!ggml_is_contiguous(tensor)) {
        fail(std::string(label) + " must be contiguous");
    }
    const size_t elements =
        static_cast<size_t>(ggml_nelements(tensor));
    if (elements != expected_elements) {
        fail(
            std::string(label) + " element count mismatch: " +
            std::to_string(elements));
    }
    if (ggml_nbytes(tensor) != elements * sizeof(T)) {
        fail(std::string(label) + " byte count mismatch");
    }

    std::vector<T> out(elements);
    ggml_backend_tensor_get(
        tensor,
        out.data(),
        0,
        out.size() * sizeof(T));
    return out;
}

void reset_live_handoff_capture(
        live_handoff_capture & state,
        live_handoff_arm arm) {
    state.enabled = true;
    state.arm = arm;
    state.saw_activation = false;
    state.saw_experts = false;
    state.saw_weights = false;
    state.saw_stock_output = false;
    state.activation.clear();
    state.experts.clear();
    state.weights.clear();
    state.stock_output.clear();
}

bool live_handoff_callback(
        ggml_tensor * tensor,
        bool ask,
        void * user_data) {
    auto * state =
        static_cast<live_handoff_capture *>(user_data);
    if (!state || !state->enabled) {
        return false;
    }

    const bool activation =
        std::strcmp(tensor->name, "attn_post_norm-0") == 0;
    const bool experts =
        std::strcmp(tensor->name, "ffn_moe_topk-0") == 0;
    const bool weights =
        std::strcmp(
            tensor->name,
            "ffn_moe_weights_softmax-0") == 0;
    const bool stock_output =
        std::strcmp(tensor->name, "ffn_moe_out-0") == 0;
    const bool wanted =
        activation || experts || weights || stock_output;

    if (ask) {
        return wanted;
    }
    if (!wanted) {
        return true;
    }

    if (activation) {
        if (state->saw_activation) {
            fail("duplicate live handoff activation");
        }
        state->activation =
            read_live_tensor<float>(
                tensor,
                GGML_TYPE_F32,
                static_cast<size_t>(k_embd),
                "live handoff attn_post_norm-0");
        state->saw_activation = true;
        return true;
    }

    if (experts) {
        if (state->saw_experts) {
            fail("duplicate live handoff top-k");
        }
        state->experts =
            read_live_tensor<int32_t>(
                tensor,
                GGML_TYPE_I32,
                static_cast<size_t>(k_top_k),
                "live handoff ffn_moe_topk-0");
        state->saw_experts = true;
        return true;
    }

    if (weights) {
        if (state->saw_weights) {
            fail("duplicate live handoff routing weights");
        }
        state->weights =
            read_live_tensor<float>(
                tensor,
                GGML_TYPE_F32,
                static_cast<size_t>(k_top_k),
                "live handoff ffn_moe_weights_softmax-0");
        for (float value : state->weights) {
            if (!std::isfinite(value) || value < 0.0f) {
                fail("live handoff routing weight is invalid");
            }
        }
        state->saw_weights = true;
        return state->arm != live_handoff_arm::handoff;
    }

    if (stock_output) {
        if (state->arm != live_handoff_arm::stock_reference) {
            fail("live handoff arm reached stock MoE output");
        }
        if (state->saw_stock_output) {
            fail("duplicate live handoff stock output");
        }
        state->stock_output =
            read_live_tensor<float>(
                tensor,
                GGML_TYPE_F32,
                static_cast<size_t>(k_embd),
                "live handoff ffn_moe_out-0");
        state->saw_stock_output = true;
        return false;
    }

    return true;
}

void validate_live_handoff_capture(
        const live_handoff_capture & state,
        bool require_stock_output,
        const char * label) {
    if (
        !state.saw_activation
        || !state.saw_experts
        || !state.saw_weights
    ) {
        fail(std::string(label) + " capture is incomplete");
    }
    if (state.experts.size() != static_cast<size_t>(k_top_k)) {
        fail(std::string(label) + " expert count mismatch");
    }

    const std::vector<int32_t> expected = {
        1, 13, 17, 21,
    };
    if (state.experts != expected) {
        fail(std::string(label) + " route differs from admitted experts");
    }

    if (require_stock_output != state.saw_stock_output) {
        fail(std::string(label) + " stock-output presence mismatch");
    }
    for (float value : state.activation) {
        if (!std::isfinite(value)) {
            fail(std::string(label) + " activation is non-finite");
        }
    }
    if (require_stock_output) {
        for (float value : state.stock_output) {
            if (!std::isfinite(value)) {
                fail(std::string(label) + " stock output is non-finite");
            }
        }
    }
}

bool float_vectors_bitwise_equal(
        const std::vector<float> & a,
        const std::vector<float> & b);

parity compare_outputs(
        const std::vector<float> & reference,
        const std::vector<float> & observed);

void reset_live_timing_capture(
        live_timing_capture & state,
        live_timing_mode mode,
        bool capture_stock_output,
        const std::vector<float> * expected_activation = nullptr,
        const std::vector<int> * expected_experts = nullptr,
        const std::vector<float> * expected_weights = nullptr) {
    state.enabled = true;
    state.mode = mode;
    state.capture_stock_output = capture_stock_output;
    state.expected_activation = expected_activation;
    state.expected_experts = expected_experts;
    state.expected_weights = expected_weights;
    state.saw_activation = false;
    state.saw_experts = false;
    state.saw_weights = false;
    state.saw_stock_output = false;
    state.activation.clear();
    state.experts.clear();
    state.weights.clear();
    state.stock_output.clear();
}

bool live_timing_callback(
        ggml_tensor * tensor,
        bool ask,
        void * user_data) {
    auto * state =
        static_cast<live_timing_capture *>(user_data);
    if (!state || !state->enabled) {
        return false;
    }

    const bool activation =
        std::strcmp(tensor->name, "attn_post_norm-0") == 0;
    const bool experts =
        std::strcmp(tensor->name, "ffn_moe_topk-0") == 0;
    const bool weights =
        std::strcmp(
            tensor->name,
            "ffn_moe_weights_softmax-0") == 0;
    const bool stock_output =
        std::strcmp(tensor->name, "ffn_moe_out-0") == 0;
    const bool wanted =
        activation || experts || weights || stock_output;

    if (ask) {
        return wanted;
    }
    if (!wanted) {
        return true;
    }

    if (activation) {
        if (state->saw_activation) {
            fail("duplicate live timing activation");
        }
        state->activation =
            read_live_tensor<float>(
                tensor,
                GGML_TYPE_F32,
                static_cast<size_t>(k_embd),
                "live timing attn_post_norm-0");
        state->saw_activation = true;
        if (state->expected_activation) {
            const parity check =
                compare_outputs(
                    *state->expected_activation,
                    state->activation);
            if (!check.pass) {
                fail("live timing callback activation drifted");
            }
        }
        state->activation_ready =
            std::chrono::steady_clock::now();
        return true;
    }

    if (experts) {
        if (state->saw_experts) {
            fail("duplicate live timing top-k");
        }
        state->experts =
            read_live_tensor<int32_t>(
                tensor,
                GGML_TYPE_I32,
                static_cast<size_t>(k_top_k),
                "live timing ffn_moe_topk-0");
        state->saw_experts = true;
        if (state->expected_experts) {
            if (
                state->experts.size()
                != state->expected_experts->size()
            ) {
                fail("live timing callback expert count drifted");
            }
            for (size_t i = 0; i < state->experts.size(); ++i) {
                if (
                    state->experts[i]
                    != (*state->expected_experts)[i]
                ) {
                    fail("live timing callback expert IDs drifted");
                }
            }
        }
        return true;
    }

    if (weights) {
        if (state->saw_weights) {
            fail("duplicate live timing routing weights");
        }
        state->weights =
            read_live_tensor<float>(
                tensor,
                GGML_TYPE_F32,
                static_cast<size_t>(k_top_k),
                "live timing ffn_moe_weights_softmax-0");
        for (float value : state->weights) {
            if (!std::isfinite(value) || value < 0.0f) {
                fail("live timing routing weight is invalid");
            }
        }
        state->saw_weights = true;
        if (
            state->expected_weights
            && !float_vectors_bitwise_equal(
                state->weights,
                *state->expected_weights)
        ) {
            fail("live timing callback routing weights drifted");
        }
        state->route_ready =
            std::chrono::steady_clock::now();
        return state->mode == live_timing_mode::stock;
    }

    if (stock_output) {
        if (state->mode != live_timing_mode::stock) {
            fail("candidate timing arm reached stock MoE output");
        }
        if (state->saw_stock_output) {
            fail("duplicate live timing stock output");
        }
        state->stock_output_ready =
            std::chrono::steady_clock::now();
        state->saw_stock_output = true;
        if (state->capture_stock_output) {
            state->stock_output =
                read_live_tensor<float>(
                    tensor,
                    GGML_TYPE_F32,
                    static_cast<size_t>(k_embd),
                    "live timing ffn_moe_out-0");
        }
        return false;
    }

    return true;
}

void validate_live_timing_capture(
        const live_timing_capture & state,
        live_timing_mode mode,
        bool require_stock_bytes,
        const char * label) {
    if (
        !state.saw_activation
        || !state.saw_experts
        || !state.saw_weights
    ) {
        fail(std::string(label) + " live timing capture is incomplete");
    }

    const std::vector<int32_t> expected = {
        1, 13, 17, 21,
    };
    if (state.experts != expected) {
        fail(std::string(label) + " live timing route drift");
    }

    if (mode == live_timing_mode::stock) {
        if (!state.saw_stock_output) {
            fail(std::string(label) + " stock output event missing");
        }
        if (
            require_stock_bytes
            && state.stock_output.size() != static_cast<size_t>(k_embd)
        ) {
            fail(std::string(label) + " stock output bytes missing");
        }
    } else if (state.saw_stock_output) {
        fail(std::string(label) + " candidate reached stock output");
    }

    for (float value : state.activation) {
        if (!std::isfinite(value)) {
            fail(std::string(label) + " activation is non-finite");
        }
    }
}

bool float_vectors_bitwise_equal(
        const std::vector<float> & a,
        const std::vector<float> & b) {
    if (a.size() != b.size()) {
        return false;
    }
    if (a.empty()) {
        return true;
    }
    return std::memcmp(
        a.data(),
        b.data(),
        a.size() * sizeof(float)) == 0;
}

parity compare_outputs(
        const std::vector<float> & reference,
        const std::vector<float> & observed) {
    if (reference.size() != observed.size() || reference.empty()) {
        fail("output size mismatch");
    }
    parity out;
    double dot = 0.0;
    double norm_ref = 0.0;
    double norm_obs = 0.0;
    for (size_t i = 0; i < reference.size(); ++i) {
        const double a = reference[i];
        const double b = observed[i];
        if (!std::isfinite(a) || !std::isfinite(b)) {
            fail("non-finite mixed-residency output");
        }
        out.max_abs = std::max(out.max_abs, std::abs(a - b));
        out.max_abs_ref = std::max(out.max_abs_ref, std::abs(a));
        dot += a * b;
        norm_ref += a * a;
        norm_obs += b * b;
    }
    out.relative_max =
        out.max_abs / std::max(1.0, out.max_abs_ref);
    out.cosine =
        dot / std::max(1e-30, std::sqrt(norm_ref * norm_obs));
    out.pass = out.relative_max <= 0.005 && out.cosine >= 0.9999;
    return out;
}

std::unique_ptr<live_routed_executor> make_live_routed_executor(
        const options & opt,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        ggml_backend_buffer_type_t gpu_buft,
        const std::vector<float> & initial_input,
        const std::vector<int> & selected_experts,
        const std::vector<float> & routing_weights) {
    if (selected_experts.size() != static_cast<size_t>(k_top_k)) {
        fail("live timing requires exactly four selected experts");
    }
    if (routing_weights.size() != static_cast<size_t>(k_top_k)) {
        fail("live timing requires exactly four routing weights");
    }
    const int gpu_hits = opt.routed_gpu_hits;
    if (gpu_hits != 2 && gpu_hits != 3) {
        fail("live timing gpu hits must be 2 or 3");
    }
    const int cpu_misses = k_top_k - gpu_hits;

    std::vector<int> gpu_ids(
        selected_experts.begin(),
        selected_experts.begin() + gpu_hits);
    std::vector<int> cpu_ids(
        selected_experts.begin() + gpu_hits,
        selected_experts.end());
    std::vector<float> gpu_mix(
        routing_weights.begin(),
        routing_weights.begin() + gpu_hits);
    std::vector<float> cpu_mix(
        routing_weights.begin() + gpu_hits,
        routing_weights.end());

    const tensor_bytes cpu_data =
        load_subset(opt.model, opt.layer, cpu_ids);
    const tensor_bytes gpu_data =
        load_subset(opt.model, opt.layer, gpu_ids);

    auto result = std::make_unique<live_routed_executor>();
    result->gpu_hits = gpu_hits;
    result->cpu_misses = cpu_misses;
    result->cpu_set = make_tensor_set(
        cpu_data,
        cpu_misses,
        cpu_weight_buft,
        cpu_bias_buft);
    result->gpu_set = make_tensor_set(
        gpu_data,
        gpu_hits,
        gpu_buft,
        gpu_buft);
    result->cpu_graph = make_compute_graph(
        *result->cpu_set,
        cpu_backend,
        cpu_misses,
        initial_input,
        &cpu_mix);
    result->gpu_graph = make_compute_graph(
        *result->gpu_set,
        gpu_backend,
        gpu_hits,
        initial_input,
        &gpu_mix);
    result->aggregate = make_sum_graph(gpu_backend);
    return result;
}

void set_live_routed_input(
        live_routed_executor & executor,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        const std::vector<float> & activation) {
    if (activation.size() != static_cast<size_t>(k_embd)) {
        fail("live timing activation size mismatch");
    }

    ggml_backend_tensor_set(
        executor.cpu_graph->input,
        activation.data(),
        0,
        activation.size() * sizeof(float));
    ggml_backend_tensor_set(
        executor.gpu_graph->input,
        activation.data(),
        0,
        activation.size() * sizeof(float));
    ggml_backend_synchronize(cpu_backend);
    ggml_backend_synchronize(gpu_backend);
}

void execute_live_routed_serial(
        live_routed_executor & executor,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        const std::vector<float> & activation) {
    set_live_routed_input(
        executor,
        cpu_backend,
        gpu_backend,
        activation);

    compute(cpu_backend, *executor.cpu_graph);
    compute(gpu_backend, *executor.gpu_graph);

    ggml_backend_tensor_copy(
        executor.gpu_graph->output,
        executor.aggregate->gpu_partial);
    ggml_backend_tensor_copy(
        executor.cpu_graph->output,
        executor.aggregate->cpu_partial);
    ggml_backend_synchronize(cpu_backend);
    ggml_backend_synchronize(gpu_backend);
    compute_sum(gpu_backend, *executor.aggregate);
}

void execute_live_routed_async(
        live_routed_executor & executor,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        const std::vector<float> & activation) {
    set_live_routed_input(
        executor,
        cpu_backend,
        gpu_backend,
        activation);

    compute_async_start(
        gpu_backend,
        *executor.gpu_graph);
    compute(cpu_backend, *executor.cpu_graph);
    ggml_backend_synchronize(gpu_backend);

    ggml_backend_tensor_copy(
        executor.gpu_graph->output,
        executor.aggregate->gpu_partial);
    ggml_backend_tensor_copy(
        executor.cpu_graph->output,
        executor.aggregate->cpu_partial);
    ggml_backend_synchronize(cpu_backend);
    ggml_backend_synchronize(gpu_backend);
    compute_sum(gpu_backend, *executor.aggregate);
}

std::vector<float> read_live_routed_output(
        live_routed_executor & executor,
        ggml_backend_t gpu_backend) {
    return read_output(
        gpu_backend,
        executor.aggregate->output);
}

routed_exactness_result run_routed_exactness(
        const options & opt,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        ggml_backend_buffer_type_t gpu_buft,
        const std::vector<float> & input,
        const std::vector<float> & stock_reference,
        const std::vector<int> & selected_experts,
        const std::vector<float> & routing_weights) {
    if (selected_experts.size() != static_cast<size_t>(k_top_k)) {
        fail("routed exactness requires exactly four selected experts");
    }
    if (routing_weights.size() != static_cast<size_t>(k_top_k)) {
        fail("routed exactness requires exactly four routing weights");
    }

    std::vector<int> sorted = selected_experts;
    std::sort(sorted.begin(), sorted.end());
    if (std::adjacent_find(sorted.begin(), sorted.end()) != sorted.end()) {
        fail("routed exactness selected experts must be unique");
    }
    for (int expert : selected_experts) {
        if (expert < 0 || expert >= k_expert_count) {
            fail("routed exactness expert id outside 0..31");
        }
    }

    const int gpu_hits = opt.routed_gpu_hits;
    const int cpu_misses = k_top_k - gpu_hits;

    std::vector<int> gpu_ids(
        selected_experts.begin(),
        selected_experts.begin() + gpu_hits);
    std::vector<int> cpu_ids(
        selected_experts.begin() + gpu_hits,
        selected_experts.end());
    std::vector<float> gpu_mix(
        routing_weights.begin(),
        routing_weights.begin() + gpu_hits);
    std::vector<float> cpu_mix(
        routing_weights.begin() + gpu_hits,
        routing_weights.end());

    const tensor_bytes cpu_data =
        load_subset(opt.model, opt.layer, cpu_ids);
    const tensor_bytes gpu_data =
        load_subset(opt.model, opt.layer, gpu_ids);

    auto cpu_set = make_tensor_set(
        cpu_data,
        cpu_misses,
        cpu_weight_buft,
        cpu_bias_buft);
    auto gpu_set = make_tensor_set(
        gpu_data,
        gpu_hits,
        gpu_buft,
        gpu_buft);

    auto cpu_graph = make_compute_graph(
        *cpu_set,
        cpu_backend,
        cpu_misses,
        input,
        &cpu_mix);
    auto gpu_graph = make_compute_graph(
        *gpu_set,
        gpu_backend,
        gpu_hits,
        input,
        &gpu_mix);
    auto aggregate = make_sum_graph(gpu_backend);

    auto execute_serial = [&]() {
        ggml_backend_tensor_copy(
            gpu_graph->input,
            cpu_graph->input);
        ggml_backend_synchronize(gpu_backend);
        ggml_backend_synchronize(cpu_backend);

        compute(cpu_backend, *cpu_graph);
        compute(gpu_backend, *gpu_graph);

        ggml_backend_tensor_copy(
            gpu_graph->output, aggregate->gpu_partial);
        ggml_backend_tensor_copy(
            cpu_graph->output,
            aggregate->cpu_partial);
        ggml_backend_synchronize(cpu_backend);
        ggml_backend_synchronize(gpu_backend);
        compute_sum(gpu_backend, *aggregate);
    };

    auto execute_async = [&]() {
        ggml_backend_tensor_copy(
            gpu_graph->input,
            cpu_graph->input);
        ggml_backend_synchronize(gpu_backend);
        ggml_backend_synchronize(cpu_backend);

        compute_async_start(gpu_backend, *gpu_graph);
        compute(cpu_backend, *cpu_graph);
        ggml_backend_synchronize(gpu_backend);

        ggml_backend_tensor_copy(
            gpu_graph->output, aggregate->gpu_partial);
        ggml_backend_tensor_copy(
            cpu_graph->output,
            aggregate->cpu_partial);
        ggml_backend_synchronize(cpu_backend);
        ggml_backend_synchronize(gpu_backend);
        compute_sum(gpu_backend, *aggregate);
    };

    execute_serial();
    const std::vector<float> serial_output =
        read_output(gpu_backend, aggregate->output);

    execute_async();
    const std::vector<float> async_output =
        read_output(gpu_backend, aggregate->output);

    routed_exactness_result result;
    result.gpu_hits = gpu_hits;
    result.cpu_misses = cpu_misses;
    result.serial_vs_stock =
        compare_outputs(stock_reference, serial_output);
    result.async_vs_stock =
        compare_outputs(stock_reference, async_output);
    result.async_vs_serial =
        compare_outputs(serial_output, async_output);

    if (!result.serial_vs_stock.pass) {
        fail("routed serial replay failed stock numerical parity");
    }
    if (!result.async_vs_stock.pass) {
        fail("routed async replay failed stock numerical parity");
    }
    if (!result.async_vs_serial.pass) {
        fail("routed async replay failed serial numerical parity");
    }

    return result;
}

live_handoff_result run_live_handoff_exactness(
        const options & opt,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        ggml_backend_buffer_type_t gpu_buft) {
    const std::string prompt =
        read_prompt_file(opt.prompt_file);

    llama_model_params model_params =
        llama_model_default_params();
    model_params.n_gpu_layers = 0;

    llama_model * model =
        llama_model_load_from_file(
            opt.model.c_str(),
            model_params);
    if (!model) {
        fail("live handoff failed to load stock model");
    }

    const llama_vocab * vocab =
        llama_model_get_vocab(model);
    std::vector<llama_token> prompt_tokens =
        tokenize_prompt(vocab, prompt);

    const uint64_t minimum_ctx =
        static_cast<uint64_t>(prompt_tokens.size()) + 8;
    if (minimum_ctx > opt.live_ctx) {
        llama_model_free(model);
        fail("live handoff configured context is too small");
    }

    live_handoff_capture callback_state;

    llama_context_params ctx_params =
        llama_context_default_params();
    ctx_params.n_ctx = opt.live_ctx;
    ctx_params.n_batch =
        static_cast<uint32_t>(prompt_tokens.size());
    ctx_params.n_ubatch =
        static_cast<uint32_t>(prompt_tokens.size());
    ctx_params.n_threads = opt.threads;
    ctx_params.n_threads_batch = opt.threads;
    ctx_params.no_perf = true;
    ctx_params.cb_eval = live_handoff_callback;
    ctx_params.cb_eval_user_data = &callback_state;

    llama_context * ctx =
        llama_init_from_model(model, ctx_params);
    if (!ctx) {
        llama_model_free(model);
        fail("live handoff failed to create stock context");
    }

    llama_sampler_chain_params sampler_params =
        llama_sampler_chain_default_params();
    sampler_params.no_perf = true;
    llama_sampler * sampler =
        llama_sampler_chain_init(sampler_params);
    llama_sampler_chain_add(
        sampler,
        llama_sampler_init_greedy());

    llama_batch prompt_batch =
        llama_batch_get_one(
            prompt_tokens.data(),
            static_cast<int32_t>(prompt_tokens.size()));
    if (llama_decode(ctx, prompt_batch) != 0) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live handoff prompt decode failed");
    }

    llama_token decode_token =
        llama_sampler_sample(sampler, ctx, -1);
    if (decode_token != k_live_handoff_decode_token) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live handoff decode token differs from admitted token");
    }
    if (llama_vocab_is_eog(vocab, decode_token)) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live handoff admitted decode token is EOG");
    }

    const llama_pos decode_position =
        static_cast<llama_pos>(prompt_tokens.size());

    reset_live_handoff_capture(
        callback_state,
        live_handoff_arm::stock_reference);
    llama_batch stock_batch =
        llama_batch_get_one(&decode_token, 1);
    const int stock_rc =
        llama_decode(ctx, stock_batch);
    callback_state.enabled = false;
    if (stock_rc != 0) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail(
            "live stock-reference early stop must return 0, got " +
            std::to_string(stock_rc));
    }
    validate_live_handoff_capture(
        callback_state,
        true,
        "stock-reference");
    const live_handoff_capture stock_capture =
        callback_state;

    const bool stock_rollback =
        llama_memory_seq_rm(
            llama_get_memory(ctx),
            0,
            decode_position,
            -1);
    if (!stock_rollback) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live stock-reference rollback failed");
    }

    reset_live_handoff_capture(
        callback_state,
        live_handoff_arm::handoff);
    llama_batch handoff_batch =
        llama_batch_get_one(&decode_token, 1);
    const int handoff_rc =
        llama_decode(ctx, handoff_batch);
    callback_state.enabled = false;
    if (handoff_rc != 0) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail(
            "live handoff early stop must return 0, got " +
            std::to_string(handoff_rc));
    }
    validate_live_handoff_capture(
        callback_state,
        false,
        "handoff");
    const live_handoff_capture handoff_capture =
        callback_state;

    const bool handoff_rollback =
        llama_memory_seq_rm(
            llama_get_memory(ctx),
            0,
            decode_position,
            -1);
    if (!handoff_rollback) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live handoff rollback failed");
    }

    if (stock_capture.experts != handoff_capture.experts) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live handoff expert IDs differ from stock reference");
    }
    if (stock_capture.weights != handoff_capture.weights) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live handoff routing weights differ from stock reference");
    }

    const parity activation_parity =
        compare_outputs(
            stock_capture.activation,
            handoff_capture.activation);
    if (!activation_parity.pass) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live handoff activation parity failed");
    }

    std::vector<int> selected_experts;
    selected_experts.reserve(static_cast<size_t>(k_top_k));
    for (int32_t expert : handoff_capture.experts) {
        selected_experts.push_back(static_cast<int>(expert));
    }

    live_handoff_result result;
    result.decode_input_token = decode_token;
    result.stock_decode_return_code = stock_rc;
    result.handoff_decode_return_code = handoff_rc;
    result.stock_rollback = stock_rollback;
    result.handoff_rollback = handoff_rollback;
    result.activation_bitwise_equal =
        float_vectors_bitwise_equal(
            stock_capture.activation,
            handoff_capture.activation);
    result.activation_parity = activation_parity;
    result.selected_experts = selected_experts;
    result.routing_weights = handoff_capture.weights;

    for (int gpu_hits : {2, 3}) {
        options routed_opt = opt;
        routed_opt.routed_gpu_hits = gpu_hits;
        routed_opt.async_overlap = true;
        result.cases.push_back(
            run_routed_exactness(
                routed_opt,
                cpu_backend,
                gpu_backend,
                cpu_weight_buft,
                cpu_bias_buft,
                gpu_buft,
                handoff_capture.activation,
                stock_capture.stock_output,
                selected_experts,
                handoff_capture.weights));
    }

    llama_sampler_free(sampler);
    llama_free(ctx);
    llama_model_free(model);
    return result;
}

live_timing_exactness_snapshot capture_live_timing_pair(
        llama_context * ctx,
        llama_token decode_token,
        llama_pos decode_position,
        live_timing_capture & callback_state,
        live_timing_reference & current,
        const live_timing_reference * frozen_reference) {
    reset_live_timing_capture(
        callback_state,
        live_timing_mode::stock,
        true);
    llama_batch stock_batch =
        llama_batch_get_one(&decode_token, 1);
    const int stock_rc =
        llama_decode(ctx, stock_batch);
    callback_state.enabled = false;
    if (stock_rc != 0) {
        fail(
            "live timing stock-reference early stop must return 0, got " +
            std::to_string(stock_rc));
    }
    validate_live_timing_capture(
        callback_state,
        live_timing_mode::stock,
        true,
        "timing-stock-reference");
    const live_timing_capture stock_capture =
        callback_state;

    const bool stock_rollback =
        llama_memory_seq_rm(
            llama_get_memory(ctx),
            0,
            decode_position,
            -1);
    if (!stock_rollback) {
        fail("live timing stock-reference rollback failed");
    }

    reset_live_timing_capture(
        callback_state,
        live_timing_mode::serial,
        false);
    llama_batch handoff_batch =
        llama_batch_get_one(&decode_token, 1);
    const int handoff_rc =
        llama_decode(ctx, handoff_batch);
    callback_state.enabled = false;
    if (handoff_rc != 0) {
        fail(
            "live timing handoff early stop must return 0, got " +
            std::to_string(handoff_rc));
    }
    validate_live_timing_capture(
        callback_state,
        live_timing_mode::serial,
        false,
        "timing-handoff");
    const live_timing_capture handoff_capture =
        callback_state;

    const bool handoff_rollback =
        llama_memory_seq_rm(
            llama_get_memory(ctx),
            0,
            decode_position,
            -1);
    if (!handoff_rollback) {
        fail("live timing handoff rollback failed");
    }

    if (stock_capture.experts != handoff_capture.experts) {
        fail("live timing expert IDs differ between exactness arms");
    }
    if (!float_vectors_bitwise_equal(
            stock_capture.weights,
            handoff_capture.weights)) {
        fail("live timing routing weights differ between exactness arms");
    }

    live_timing_reference observed;
    observed.activation = handoff_capture.activation;
    observed.stock_output = stock_capture.stock_output;
    observed.routing_weights = handoff_capture.weights;
    observed.selected_experts.reserve(static_cast<size_t>(k_top_k));
    for (int32_t expert : handoff_capture.experts) {
        observed.selected_experts.push_back(static_cast<int>(expert));
    }

    if (frozen_reference) {
        if (observed.selected_experts != frozen_reference->selected_experts) {
            fail("live timing expert IDs drifted from pre-timing reference");
        }
        if (!float_vectors_bitwise_equal(
                observed.routing_weights,
                frozen_reference->routing_weights)) {
            fail("live timing routing weights drifted from pre-timing reference");
        }
    }

    live_timing_exactness_snapshot snapshot;
    snapshot.stock_decode_return_code = stock_rc;
    snapshot.handoff_decode_return_code = handoff_rc;
    snapshot.stock_rollback = stock_rollback;
    snapshot.handoff_rollback = handoff_rollback;
    snapshot.activation_bitwise_equal =
        float_vectors_bitwise_equal(
            stock_capture.activation,
            handoff_capture.activation);
    snapshot.activation_parity =
        compare_outputs(
            stock_capture.activation,
            handoff_capture.activation);
    if (!snapshot.activation_parity.pass) {
        fail("live timing exactness activation pair parity failed");
    }

    if (frozen_reference) {
        snapshot.activation_vs_reference =
            compare_outputs(
                frozen_reference->activation,
                observed.activation);
        snapshot.stock_output_vs_reference =
            compare_outputs(
                frozen_reference->stock_output,
                observed.stock_output);
    } else {
        snapshot.activation_vs_reference =
            compare_outputs(
                observed.activation,
                observed.activation);
        snapshot.stock_output_vs_reference =
            compare_outputs(
                observed.stock_output,
                observed.stock_output);
    }

    if (!snapshot.activation_vs_reference.pass) {
        fail("live timing activation drifted from pre-timing reference");
    }
    if (!snapshot.stock_output_vs_reference.pass) {
        fail("live timing stock output drifted from pre-timing reference");
    }

    current = std::move(observed);
    return snapshot;
}

void complete_live_timing_exactness(
        live_timing_exactness_snapshot & snapshot,
        live_routed_executor & executor,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        const live_timing_reference & current) {
    execute_live_routed_serial(
        executor,
        cpu_backend,
        gpu_backend,
        current.activation);
    const std::vector<float> serial_output =
        read_live_routed_output(
            executor,
            gpu_backend);

    execute_live_routed_async(
        executor,
        cpu_backend,
        gpu_backend,
        current.activation);
    const std::vector<float> async_output =
        read_live_routed_output(
            executor,
            gpu_backend);

    snapshot.serial_vs_stock =
        compare_outputs(
            current.stock_output,
            serial_output);
    snapshot.async_vs_stock =
        compare_outputs(
            current.stock_output,
            async_output);
    snapshot.async_vs_serial =
        compare_outputs(
            serial_output,
            async_output);

    if (!snapshot.serial_vs_stock.pass) {
        fail("live timing serial pre/post exactness failed stock parity");
    }
    if (!snapshot.async_vs_stock.pass) {
        fail("live timing async pre/post exactness failed stock parity");
    }
    if (!snapshot.async_vs_serial.pass) {
        fail("live timing async pre/post exactness failed serial parity");
    }
}

std::pair<double, double> run_live_timing_trial(
        llama_context * ctx,
        llama_token decode_token,
        llama_pos decode_position,
        live_timing_capture & callback_state,
        live_timing_mode mode,
        live_routed_executor & executor,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        const live_timing_reference & reference) {
    reset_live_timing_capture(
        callback_state,
        mode,
        false,
        &reference.activation,
        &reference.selected_experts,
        &reference.routing_weights);

    llama_batch batch =
        llama_batch_get_one(&decode_token, 1);
    const int rc =
        llama_decode(ctx, batch);
    callback_state.enabled = false;
    if (rc != 0) {
        fail(
            "live timing repeated decode must return 0, got " +
            std::to_string(rc));
    }

    std::chrono::steady_clock::time_point endpoint;
    if (mode == live_timing_mode::stock) {
        endpoint = callback_state.stock_output_ready;
    } else if (mode == live_timing_mode::serial) {
        execute_live_routed_serial(
            executor,
            cpu_backend,
            gpu_backend,
            callback_state.activation);
        endpoint =
            std::chrono::steady_clock::now();
    } else {
        execute_live_routed_async(
            executor,
            cpu_backend,
            gpu_backend,
            callback_state.activation);
        endpoint =
            std::chrono::steady_clock::now();
    }

    const double activation_ms =
        std::chrono::duration<double, std::milli>(
            endpoint - callback_state.activation_ready).count();
    const double route_ms =
        std::chrono::duration<double, std::milli>(
            endpoint - callback_state.route_ready).count();
    if (
        !std::isfinite(activation_ms)
        || !std::isfinite(route_ms)
        || activation_ms <= 0.0
        || route_ms <= 0.0
    ) {
        fail("live timing produced invalid latency");
    }

    validate_live_timing_capture(
        callback_state,
        mode,
        false,
        mode == live_timing_mode::stock
            ? "timing-stock"
            : (mode == live_timing_mode::serial
                ? "timing-serial"
                : "timing-async"));

    if (!llama_memory_seq_rm(
            llama_get_memory(ctx),
            0,
            decode_position,
            -1)) {
        fail("live timing repeated-token rollback failed");
    }

    return {activation_ms, route_ms};
}

live_handoff_timing_result run_live_handoff_timing(
        const options & opt,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        ggml_backend_buffer_type_t gpu_buft) {
    const std::string prompt =
        read_prompt_file(opt.prompt_file);

    llama_model_params model_params =
        llama_model_default_params();
    model_params.n_gpu_layers = 0;

    llama_model * model =
        llama_model_load_from_file(
            opt.model.c_str(),
            model_params);
    if (!model) {
        fail("live timing failed to load stock model");
    }

    const llama_vocab * vocab =
        llama_model_get_vocab(model);
    std::vector<llama_token> prompt_tokens =
        tokenize_prompt(vocab, prompt);

    const uint64_t minimum_ctx =
        static_cast<uint64_t>(prompt_tokens.size()) + 8;
    if (minimum_ctx > opt.live_ctx) {
        llama_model_free(model);
        fail("live timing configured context is too small");
    }

    live_timing_capture callback_state;

    llama_context_params ctx_params =
        llama_context_default_params();
    ctx_params.n_ctx = opt.live_ctx;
    ctx_params.n_batch =
        static_cast<uint32_t>(prompt_tokens.size());
    ctx_params.n_ubatch =
        static_cast<uint32_t>(prompt_tokens.size());
    ctx_params.n_threads = opt.threads;
    ctx_params.n_threads_batch = opt.threads;
    ctx_params.no_perf = true;
    ctx_params.cb_eval = live_timing_callback;
    ctx_params.cb_eval_user_data = &callback_state;

    llama_context * ctx =
        llama_init_from_model(model, ctx_params);
    if (!ctx) {
        llama_model_free(model);
        fail("live timing failed to create stock context");
    }

    llama_sampler_chain_params sampler_params =
        llama_sampler_chain_default_params();
    sampler_params.no_perf = true;
    llama_sampler * sampler =
        llama_sampler_chain_init(sampler_params);
    llama_sampler_chain_add(
        sampler,
        llama_sampler_init_greedy());

    llama_batch prompt_batch =
        llama_batch_get_one(
            prompt_tokens.data(),
            static_cast<int32_t>(prompt_tokens.size()));
    if (llama_decode(ctx, prompt_batch) != 0) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live timing prompt decode failed");
    }

    const llama_token decode_token =
        llama_sampler_sample(sampler, ctx, -1);
    if (decode_token != k_live_handoff_decode_token) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live timing decode token differs from admitted token");
    }
    if (llama_vocab_is_eog(vocab, decode_token)) {
        llama_sampler_free(sampler);
        llama_free(ctx);
        llama_model_free(model);
        fail("live timing admitted decode token is EOG");
    }

    const llama_pos decode_position =
        static_cast<llama_pos>(prompt_tokens.size());

    live_timing_reference pre_reference;
    live_timing_exactness_snapshot pre_snapshot =
        capture_live_timing_pair(
            ctx,
            decode_token,
            decode_position,
            callback_state,
            pre_reference,
            nullptr);

    auto executor =
        make_live_routed_executor(
            opt,
            cpu_backend,
            gpu_backend,
            cpu_weight_buft,
            cpu_bias_buft,
            gpu_buft,
            pre_reference.activation,
            pre_reference.selected_experts,
            pre_reference.routing_weights);

    complete_live_timing_exactness(
        pre_snapshot,
        *executor,
        cpu_backend,
        gpu_backend,
        pre_reference);

    bool gate_open = false;
    for (int attempt = 0; attempt < 60000; ++attempt) {
        if (std::filesystem::exists(opt.timing_start_gate)) {
            gate_open = true;
            break;
        }
        std::this_thread::sleep_for(
            std::chrono::milliseconds(1));
    }
    if (!gate_open) {
        fail("live handoff timing start gate timed out");
    }

    live_handoff_timing_result result;
    result.gpu_hits = opt.routed_gpu_hits;
    result.cpu_misses = k_top_k - opt.routed_gpu_hits;
    result.decode_input_token = decode_token;
    result.selected_experts = pre_reference.selected_experts;
    result.routing_weights = pre_reference.routing_weights;
    result.pre_exactness = pre_snapshot;
    result.stock.activation_ms.reserve(
        static_cast<size_t>(opt.samples));
    result.stock.route_ms.reserve(
        static_cast<size_t>(opt.samples));
    result.serial.activation_ms.reserve(
        static_cast<size_t>(opt.samples));
    result.serial.route_ms.reserve(
        static_cast<size_t>(opt.samples));
    result.async.activation_ms.reserve(
        static_cast<size_t>(opt.samples));
    result.async.route_ms.reserve(
        static_cast<size_t>(opt.samples));

    const std::array<std::array<live_timing_mode, 3>, 6> orders = {{
        {
            live_timing_mode::stock,
            live_timing_mode::serial,
            live_timing_mode::async,
        },
        {
            live_timing_mode::stock,
            live_timing_mode::async,
            live_timing_mode::serial,
        },
        {
            live_timing_mode::serial,
            live_timing_mode::stock,
            live_timing_mode::async,
        },
        {
            live_timing_mode::serial,
            live_timing_mode::async,
            live_timing_mode::stock,
        },
        {
            live_timing_mode::async,
            live_timing_mode::stock,
            live_timing_mode::serial,
        },
        {
            live_timing_mode::async,
            live_timing_mode::serial,
            live_timing_mode::stock,
        },
    }};

    auto run_mode = [&](live_timing_mode mode, bool record) {
        const auto sample =
            run_live_timing_trial(
                ctx,
                decode_token,
                decode_position,
                callback_state,
                mode,
                *executor,
                cpu_backend,
                gpu_backend,
                pre_reference);

        live_timing_samples * destination = nullptr;
        if (mode == live_timing_mode::stock) {
            destination = &result.stock;
            result.completed_stock_trials++;
        } else if (mode == live_timing_mode::serial) {
            destination = &result.serial;
            result.completed_serial_trials++;
        } else {
            destination = &result.async;
            result.completed_async_trials++;
        }
        result.successful_timing_trial_rollbacks++;

        if (record) {
            destination->activation_ms.push_back(sample.first);
            destination->route_ms.push_back(sample.second);
        }
    };

    for (int round = 0; round < opt.warmup; ++round) {
        for (live_timing_mode mode :
                orders[static_cast<size_t>(round) % orders.size()]) {
            run_mode(mode, false);
        }
    }

    constexpr int measured_full_cycles = 13;
    constexpr std::array<size_t, 3> measured_tail = {
        0, 3, 4,
    };
    static_assert(
        measured_full_cycles * 6
            + static_cast<int>(measured_tail.size())
            == 81);

    for (int round = 0; round < opt.samples; ++round) {
        size_t order_index = 0;
        const int cycle_samples =
            measured_full_cycles
            * static_cast<int>(orders.size());
        if (round < cycle_samples) {
            order_index =
                static_cast<size_t>(round) % orders.size();
        } else {
            const size_t tail_index =
                static_cast<size_t>(round - cycle_samples);
            if (tail_index >= measured_tail.size()) {
                fail("live timing measured order tail overflow");
            }
            order_index = measured_tail[tail_index];
        }

        for (live_timing_mode mode : orders[order_index]) {
            run_mode(mode, true);
        }
    }

    if (
        result.stock.activation_ms.size()
            != static_cast<size_t>(opt.samples)
        || result.stock.route_ms.size()
            != static_cast<size_t>(opt.samples)
        || result.serial.activation_ms.size()
            != static_cast<size_t>(opt.samples)
        || result.serial.route_ms.size()
            != static_cast<size_t>(opt.samples)
        || result.async.activation_ms.size()
            != static_cast<size_t>(opt.samples)
        || result.async.route_ms.size()
            != static_cast<size_t>(opt.samples)
    ) {
        fail("live timing sample count mismatch");
    }

    live_timing_reference post_reference;
    live_timing_exactness_snapshot post_snapshot =
        capture_live_timing_pair(
            ctx,
            decode_token,
            decode_position,
            callback_state,
            post_reference,
            &pre_reference);
    complete_live_timing_exactness(
        post_snapshot,
        *executor,
        cpu_backend,
        gpu_backend,
        post_reference);
    result.post_exactness = post_snapshot;

    llama_sampler_free(sampler);
    llama_free(ctx);
    llama_model_free(model);
    return result;
}

enum class reinjection_phase { disabled, capture, committed };

struct reinjection_callback_state {
    reinjection_phase phase = reinjection_phase::disabled;
    live_handoff_capture capture;
    const std::vector<float> * expected_activation = nullptr;
    const std::vector<int32_t> * expected_experts = nullptr;
    const std::vector<float> * expected_weights = nullptr;
    const std::vector<float> * expected_stock_output = nullptr;
    const std::vector<float> * injection = nullptr;
    bool saw_activation = false;
    bool saw_experts = false;
    bool saw_weights = false;
    int injection_count = 0;
    parity pre_overwrite_parity;
    bool pre_overwrite_bitwise = false;
    bool injected_bytes_verified = false;
};

bool reinjection_callback(ggml_tensor * tensor, bool ask, void * user_data) {
    auto * state = static_cast<reinjection_callback_state *>(user_data);
    if (!state) {
        fail("reinjection callback state missing");
    }
    if (state->phase == reinjection_phase::disabled) {
        return ask ? false : true;
    }
    if (state->phase == reinjection_phase::capture) {
        return live_handoff_callback(tensor, ask, &state->capture);
    }

    const bool activation = std::strcmp(tensor->name, "attn_post_norm-0") == 0;
    const bool experts = std::strcmp(tensor->name, "ffn_moe_topk-0") == 0;
    const bool weights = std::strcmp(tensor->name, "ffn_moe_weights_softmax-0") == 0;
    const bool output = std::strcmp(tensor->name, "ffn_moe_out-0") == 0;
    if (ask) {
        return activation || experts || weights || output;
    }
    if (activation) {
        if (state->saw_activation || !state->expected_activation) {
            fail("reinjection activation missing or duplicated");
        }
        const auto observed = read_live_tensor<float>(
            tensor, GGML_TYPE_F32, static_cast<size_t>(k_embd),
            "reinjection attn_post_norm-0");
        if (!compare_outputs(*state->expected_activation, observed).pass) {
            fail("reinjection live activation differs from frozen reference");
        }
        state->saw_activation = true;
    } else if (experts) {
        if (state->saw_experts || !state->expected_experts) {
            fail("reinjection experts missing or duplicated");
        }
        const auto observed = read_live_tensor<int32_t>(
            tensor, GGML_TYPE_I32, static_cast<size_t>(k_top_k),
            "reinjection ffn_moe_topk-0");
        if (observed != *state->expected_experts ||
            observed != std::vector<int32_t>{1, 13, 17, 21}) {
            fail("reinjection route differs from frozen target route");
        }
        state->saw_experts = true;
    } else if (weights) {
        if (state->saw_weights || !state->expected_weights) {
            fail("reinjection weights missing or duplicated");
        }
        const auto observed = read_live_tensor<float>(
            tensor, GGML_TYPE_F32, static_cast<size_t>(k_top_k),
            "reinjection ffn_moe_weights_softmax-0");
        if (!float_vectors_bitwise_equal(observed, *state->expected_weights)) {
            fail("reinjection routing weights differ bitwise");
        }
        state->saw_weights = true;
    } else if (output) {
        if (!state->saw_activation || !state->saw_experts ||
            !state->saw_weights || state->injection_count != 0 ||
            !state->expected_stock_output || !state->injection) {
            fail("reinjection output reached with incomplete route or duplicate injection");
        }
        const auto before = read_live_tensor<float>(
            tensor, GGML_TYPE_F32, static_cast<size_t>(k_embd),
            "reinjection ffn_moe_out-0");
        state->pre_overwrite_parity = compare_outputs(
            *state->expected_stock_output, before);
        state->pre_overwrite_bitwise = float_vectors_bitwise_equal(
            *state->expected_stock_output, before);
        if (!state->pre_overwrite_parity.pass ||
            state->injection->size() != static_cast<size_t>(k_embd)) {
            fail("reinjection pre-overwrite stock output mismatch");
        }
        for (float value : *state->injection) {
            if (!std::isfinite(value)) {
                fail("reinjection vector contains non-finite value");
            }
        }
        ggml_backend_tensor_set(tensor, state->injection->data(), 0,
                                state->injection->size() * sizeof(float));
        const auto after = read_live_tensor<float>(
            tensor, GGML_TYPE_F32, static_cast<size_t>(k_embd),
            "reinjection written ffn_moe_out-0");
        state->injected_bytes_verified = float_vectors_bitwise_equal(
            after, *state->injection);
        if (!state->injected_bytes_verified) {
            fail("reinjection tensor write did not persist");
        }
        state->injection_count++;
    }
    return true;
}

struct reinjection_arm_result {
    std::string name;
    int gpu_hits = 0;
    llama_token first_token = -1;
    llama_token second_token = -1;
    llama_token third_token = -1;
    int committed_decode_return_code = -1;
    int continuation_decode_return_code = -1;
    bool stock_capture_rollback = false;
    bool handoff_capture_rollback = false;
    bool activation_pair_bitwise = false;
    parity activation_pair_parity;
    parity ffn_parity;
    bool ffn_bitwise = false;
    parity pre_overwrite_parity;
    bool pre_overwrite_bitwise = false;
    bool injected_bytes_verified = false;
    int injection_count = 0;
    std::vector<int32_t> experts;
    std::vector<float> weights;
    std::vector<float> logits_a;
    std::vector<float> logits_b;
};

std::vector<float> copy_reinjection_logits(llama_context * ctx, size_t count) {
    const float * data = llama_get_logits(ctx);
    if (!data || count == 0) {
        fail("reinjection decode produced no logits");
    }
    std::vector<float> out(data, data + count);
    for (float value : out) {
        if (!std::isfinite(value)) {
            fail("reinjection logits contain non-finite value");
        }
    }
    return out;
}

reinjection_arm_result run_reinjection_arm(
        const options & opt, llama_model * model,
        const std::vector<llama_token> & prompt_tokens,
        const std::string & name, int gpu_hits,
        ggml_backend_t cpu_backend, ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        ggml_backend_buffer_type_t gpu_buft,
        const reinjection_arm_result * stock_authority,
        bool require_patch_null = false) {
    const bool baseline = name == "stock" || name == "null";
    reinjection_callback_state state;
    llama_context_params params = llama_context_default_params();
    params.n_ctx = opt.live_ctx;
    params.n_batch = static_cast<uint32_t>(prompt_tokens.size());
    params.n_ubatch = static_cast<uint32_t>(prompt_tokens.size());
    params.n_threads = opt.threads;
    params.n_threads_batch = opt.threads;
    params.no_perf = true;
    if (!baseline) {
        params.cb_eval = reinjection_callback;
        params.cb_eval_user_data = &state;
    }
    llama_context * ctx = llama_init_from_model(model, params);
    if (!ctx) {
        fail("reinjection failed to create fresh stock context");
    }
    if (require_patch_null) {
        if (!llama_tesy_set_graph_compute_hook) {
            fail("patched-null control lacks Tesy hook symbol");
        }
        llama_tesy_set_graph_compute_hook(ctx, nullptr, nullptr);
    }
    llama_sampler_chain_params sampler_params = llama_sampler_chain_default_params();
    sampler_params.no_perf = true;
    llama_sampler * sampler = llama_sampler_chain_init(sampler_params);
    llama_sampler_chain_add(sampler, llama_sampler_init_greedy());

    reinjection_arm_result out;
    out.name = name;
    out.gpu_hits = gpu_hits;
    llama_batch prompt_batch = llama_batch_get_one(
        const_cast<llama_token *>(prompt_tokens.data()),
        static_cast<int32_t>(prompt_tokens.size()));
    if (llama_decode(ctx, prompt_batch) != 0) {
        fail("reinjection prompt decode failed");
    }
    out.first_token = llama_sampler_sample(sampler, ctx, -1);
    if (out.first_token != k_live_handoff_decode_token) {
        fail("reinjection first greedy token is not 2167");
    }
    if (llama_vocab_is_eog(llama_model_get_vocab(model), out.first_token)) {
        fail("reinjection first token is EOG");
    }

    std::vector<float> injection;
    std::unique_ptr<live_routed_executor> executor;
    live_handoff_capture reference;
    live_handoff_capture handoff;
    if (!baseline) {
        const llama_pos position = static_cast<llama_pos>(prompt_tokens.size());
        state.phase = reinjection_phase::capture;
        reset_live_handoff_capture(state.capture, live_handoff_arm::stock_reference);
        llama_batch capture_batch = llama_batch_get_one(&out.first_token, 1);
        if (llama_decode(ctx, capture_batch) != 0) {
            fail("reinjection stock capture decode failed");
        }
        validate_live_handoff_capture(state.capture, true, "reinjection stock");
        reference = state.capture;
        out.stock_capture_rollback = llama_memory_seq_rm(
            llama_get_memory(ctx), 0, position, -1);
        if (!out.stock_capture_rollback) {
            fail("reinjection stock capture rollback failed");
        }
        if (gpu_hits > 0) {
            reset_live_handoff_capture(state.capture, live_handoff_arm::handoff);
            llama_batch handoff_batch = llama_batch_get_one(&out.first_token, 1);
            if (llama_decode(ctx, handoff_batch) != 0) {
                fail("reinjection handoff capture decode failed");
            }
            validate_live_handoff_capture(state.capture, false, "reinjection handoff");
            handoff = state.capture;
            out.handoff_capture_rollback = llama_memory_seq_rm(
                llama_get_memory(ctx), 0, position, -1);
            if (!out.handoff_capture_rollback) {
                fail("reinjection handoff capture rollback failed");
            }
            if (reference.experts != handoff.experts ||
                !float_vectors_bitwise_equal(reference.weights, handoff.weights)) {
                fail("reinjection stock/handoff route drift");
            }
            out.activation_pair_parity = compare_outputs(
                reference.activation, handoff.activation);
            out.activation_pair_bitwise = float_vectors_bitwise_equal(
                reference.activation, handoff.activation);
            if (!out.activation_pair_parity.pass) {
                fail("reinjection activation pair mismatch");
            }
            options routed = opt;
            routed.routed_gpu_hits = gpu_hits;
            std::vector<int> selected(reference.experts.begin(), reference.experts.end());
            executor = make_live_routed_executor(
                routed, cpu_backend, gpu_backend, cpu_weight_buft, cpu_bias_buft,
                gpu_buft, handoff.activation, selected, handoff.weights);
            execute_live_routed_serial(*executor, cpu_backend, gpu_backend,
                                       handoff.activation);
            injection = read_live_routed_output(*executor, gpu_backend);
        } else {
            injection = reference.stock_output;
            out.handoff_capture_rollback = true;
            out.activation_pair_parity = compare_outputs(
                reference.activation, reference.activation);
            out.activation_pair_bitwise = true;
        }
        out.ffn_parity = compare_outputs(reference.stock_output, injection);
        out.ffn_bitwise = float_vectors_bitwise_equal(
            reference.stock_output, injection);
        if (!out.ffn_parity.pass) {
            fail("reinjection serial FFN output differs from stock");
        }
        out.experts = reference.experts;
        out.weights = reference.weights;
        state.expected_activation = gpu_hits > 0 ? &handoff.activation : &reference.activation;
        state.expected_experts = &reference.experts;
        state.expected_weights = &reference.weights;
        state.expected_stock_output = &reference.stock_output;
        state.injection = &injection;
        state.phase = reinjection_phase::committed;
    }

    llama_batch committed_batch = llama_batch_get_one(&out.first_token, 1);
    out.committed_decode_return_code = llama_decode(ctx, committed_batch);
    if (out.committed_decode_return_code != 0) {
        fail("reinjection committed decode failed");
    }
    if (!baseline) {
        state.phase = reinjection_phase::disabled;
        if (state.injection_count != 1 || !state.saw_activation ||
            !state.saw_experts || !state.saw_weights ||
            !state.injected_bytes_verified) {
            fail("reinjection committed callback incomplete");
        }
        out.injection_count = state.injection_count;
        out.pre_overwrite_parity = state.pre_overwrite_parity;
        out.pre_overwrite_bitwise = state.pre_overwrite_bitwise;
        out.injected_bytes_verified = state.injected_bytes_verified;
    }
    const size_t n_vocab = static_cast<size_t>(
        llama_vocab_n_tokens(llama_model_get_vocab(model)));
    out.logits_a = copy_reinjection_logits(ctx, n_vocab);
    out.second_token = llama_sampler_sample(sampler, ctx, -1);
    if (out.second_token != 1309) {
        fail("reinjection second greedy token is not 1309");
    }
    if (stock_authority) {
        if (out.second_token != stock_authority->second_token ||
            !compare_outputs(stock_authority->logits_a, out.logits_a).pass) {
            fail("reinjection checkpoint A logits or token mismatch");
        }
    }
    llama_batch continuation_batch = llama_batch_get_one(&out.second_token, 1);
    out.continuation_decode_return_code = llama_decode(ctx, continuation_batch);
    if (out.continuation_decode_return_code != 0) {
        fail("reinjection committed continuation decode failed");
    }
    out.logits_b = copy_reinjection_logits(ctx, n_vocab);
    out.third_token = llama_sampler_sample(sampler, ctx, -1);
    if (stock_authority) {
        if (out.third_token != stock_authority->third_token ||
            !compare_outputs(stock_authority->logits_b, out.logits_b).pass) {
            fail("reinjection checkpoint B logits or token mismatch");
        }
    }
    llama_sampler_free(sampler);
    llama_free(ctx);
    return out;
}

void write_reinjection_logits(const std::string & path,
                              const std::vector<float> & values) {
    FILE * out = std::fopen(path.c_str(), "wx");
    if (!out) {
        fail("failed opening reinjection full logits: " + path);
    }
    const bool wrote = std::fwrite(
        values.data(), sizeof(float), values.size(), out) == values.size();
    const bool closed = std::fclose(out) == 0;
    if (!wrote || !closed) {
        fail("failed writing reinjection full logits: " + path);
    }
}

void print_reinjection_parity(FILE * out, const parity & value) {
    std::fprintf(out,
        "{\"max_abs\":%.9g,\"max_abs_ref\":%.9g,"
        "\"relative_max\":%.9g,\"cosine\":%.12f,\"status\":\"%s\"}",
        value.max_abs, value.max_abs_ref, value.relative_max, value.cosine,
        value.pass ? "PASS" : "FAIL");
}

void run_live_reinjection_exactness(
        const options & opt, ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        ggml_backend_buffer_type_t gpu_buft) {
    const std::string prompt = read_prompt_file(opt.prompt_file);
    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 0;
    llama_model * model = llama_model_load_from_file(opt.model.c_str(), model_params);
    if (!model) {
        fail("reinjection failed to load pinned stock model");
    }
    const auto prompt_tokens = tokenize_prompt(llama_model_get_vocab(model), prompt);
    if (prompt_tokens.size() + 8 > opt.live_ctx) {
        fail("reinjection configured context too small");
    }
    std::vector<reinjection_arm_result> arms;
    arms.push_back(run_reinjection_arm(
        opt, model, prompt_tokens, "stock", 0, cpu_backend, gpu_backend,
        cpu_weight_buft, cpu_bias_buft, gpu_buft, nullptr));
    arms.push_back(run_reinjection_arm(
        opt, model, prompt_tokens, "control", 0, cpu_backend, gpu_backend,
        cpu_weight_buft, cpu_bias_buft, gpu_buft, &arms[0]));
    arms.push_back(run_reinjection_arm(
        opt, model, prompt_tokens, "h2", 2, cpu_backend, gpu_backend,
        cpu_weight_buft, cpu_bias_buft, gpu_buft, &arms[0]));
    arms.push_back(run_reinjection_arm(
        opt, model, prompt_tokens, "h3", 3, cpu_backend, gpu_backend,
        cpu_weight_buft, cpu_bias_buft, gpu_buft, &arms[0]));
    llama_model_free(model);

    const auto root = std::filesystem::path(opt.output).parent_path();
    for (const auto & arm : arms) {
        write_reinjection_logits((root / (arm.name + "-a.f32")).string(), arm.logits_a);
        write_reinjection_logits((root / (arm.name + "-b.f32")).string(), arm.logits_b);
    }
    FILE * out = std::fopen(opt.output.c_str(), "wx");
    if (!out) {
        fail("refusing or unable to create reinjection raw output");
    }
    std::fprintf(out,
        "{\"schema\":\"tesy.live_moe_reinjection_continuation_exactness_raw.v1\","
        "\"classification\":\"MEASURED_LIVE_MOE_REINJECTION_CONTINUATION_EXACTNESS_RAW\","
        "\"layer\":0,\"ngl\":0,\"first_token\":2167,\"second_token\":1309,"
        "\"stock_third_token\":%" PRId32 ",\"logits_count\":%zu,"
        "\"arms\":{", arms[0].third_token, arms[0].logits_a.size());
    for (size_t i = 0; i < arms.size(); ++i) {
        const auto & arm = arms[i];
        if (i != 0) std::fputc(',', out);
        std::fprintf(out,
            "\"%s\":{\"gpu_hits\":%d,\"first_token\":%" PRId32
            ",\"second_token\":%" PRId32 ",\"third_token\":%" PRId32
            ",\"committed_decode_return_code\":%d,"
            "\"continuation_decode_return_code\":%d,"
            "\"stock_capture_rollback\":%s,\"handoff_capture_rollback\":%s,"
            "\"activation_pair_bitwise\":%s,\"ffn_bitwise\":%s,"
            "\"pre_overwrite_bitwise\":%s,\"injected_bytes_verified\":%s,"
            "\"injection_count\":%d,\"selected_experts\":[",
            arm.name.c_str(), arm.gpu_hits, arm.first_token, arm.second_token,
            arm.third_token, arm.committed_decode_return_code,
            arm.continuation_decode_return_code,
            arm.stock_capture_rollback ? "true" : "false",
            arm.handoff_capture_rollback ? "true" : "false",
            arm.activation_pair_bitwise ? "true" : "false",
            arm.ffn_bitwise ? "true" : "false",
            arm.pre_overwrite_bitwise ? "true" : "false",
            arm.injected_bytes_verified ? "true" : "false",
            arm.injection_count);
        for (size_t j = 0; j < arm.experts.size(); ++j) {
            if (j) std::fputc(',', out);
            std::fprintf(out, "%" PRId32, arm.experts[j]);
        }
        std::fputs("],\"routing_weights\":[", out);
        for (size_t j = 0; j < arm.weights.size(); ++j) {
            if (j) std::fputc(',', out);
            std::fprintf(out, "%.9g", arm.weights[j]);
        }
        std::fputs("],\"activation_pair_parity\":", out);
        print_reinjection_parity(out, arm.activation_pair_parity);
        std::fputs(",\"ffn_parity\":", out);
        print_reinjection_parity(out, arm.ffn_parity);
        std::fputs(",\"pre_overwrite_parity\":", out);
        print_reinjection_parity(out, arm.pre_overwrite_parity);
        std::fprintf(out,
            ",\"logits_a_file\":\"%s-a.f32\",\"logits_b_file\":\"%s-b.f32\"}",
            arm.name.c_str(), arm.name.c_str());
    }
    std::fputs("},\"claim_boundary\":\"Post-compute layer-0 tensor overwrite and committed continuation correctness only; stock MoE still computes. No timing, skipping, cache, prefetch or physical traffic claim.\"}\n", out);
    if (std::fclose(out) != 0) {
        fail("failed closing reinjection raw output");
    }
    std::printf("PASS_LIVE_MOE_REINJECTION_RAW\n");
}

struct split_graph_hook_state {
    const live_handoff_capture * reference = nullptr;
    const std::vector<float> * injection = nullptr;
    std::string inventory_path;
    bool skip_middle = false;
    bool invoked = false;
    int prefix_compute_count = 0;
    int middle_compute_count = 0;
    int suffix_compute_count = 0;
    int injected_output_count = 0;
    int total_nodes = 0;
    int activation_idx = -1;
    int topk_idx = -1;
    int weights_idx = -1;
    int moe_out_idx = -1;
    int mul_mat_id_count = 0;
    bool all_nodes_cpu = false;
    bool middle_contiguous = false;
    bool downstream_depends_on_moe_out = false;
    parity stock_output_parity;
    bool stock_output_bitwise = false;
    bool injected_bytes_verified = false;
    std::vector<float> observed_moe_output;
};

void collect_graph_ancestors(ggml_tensor * node,
                             std::unordered_set<ggml_tensor *> & seen) {
    if (!node || !seen.insert(node).second) return;
    for (ggml_tensor * src : node->src) {
        collect_graph_ancestors(src, seen);
    }
    collect_graph_ancestors(node->view_src, seen);
}

void write_split_graph_inventory(const split_graph_hook_state & state,
                                 const ggml_cgraph * graph,
                                 ggml_backend_sched_t sched) {
    FILE * out = std::fopen(state.inventory_path.c_str(), "wx");
    if (!out) fail("cannot create split graph inventory");
    std::fprintf(out,
        "{\"schema\":\"tesy.live_moe_split_graph_inventory.v1\","
        "\"total_nodes\":%d,\"activation_idx\":%d,\"topk_idx\":%d,"
        "\"weights_idx\":%d,\"moe_out_idx\":%d,"
        "\"prefix\":[0,%d],\"middle\":[%d,%d],\"suffix\":[%d,%d],"
        "\"all_nodes_cpu\":%s,\"middle_contiguous\":%s,"
        "\"downstream_depends_on_moe_out\":%s,\"mul_mat_id_count\":%d,"
        "\"prefix_compute_count\":%d,\"middle_compute_count\":%d,"
        "\"suffix_compute_count\":%d,\"injected_output_count\":%d,"
        "\"skipped_nodes\":[",
        state.total_nodes, state.activation_idx, state.topk_idx,
        state.weights_idx, state.moe_out_idx,
        state.weights_idx + 1, state.weights_idx + 1, state.moe_out_idx + 1,
        state.moe_out_idx + 1, state.total_nodes,
        state.all_nodes_cpu ? "true" : "false",
        state.middle_contiguous ? "true" : "false",
        state.downstream_depends_on_moe_out ? "true" : "false",
        state.mul_mat_id_count, state.prefix_compute_count,
        state.middle_compute_count, state.suffix_compute_count,
        state.injected_output_count);
    for (int i = state.weights_idx + 1; i <= state.moe_out_idx; ++i) {
        const auto * node = graph->nodes[i];
        if (i > state.weights_idx + 1) std::fputc(',', out);
        std::fprintf(out,
            "{\"index\":%d,\"name\":\"%s\",\"op\":\"%s\"}",
            i, node->name, ggml_op_name(node->op));
    }
    const auto * downstream = graph->nodes[state.moe_out_idx + 1];
    std::fprintf(out,
        "],\"downstream_first\":{\"name\":\"%s\",\"op\":\"%s\"},"
        "\"node_backends\":[",
        downstream->name, ggml_op_name(downstream->op));
    for (int i = 0; i < graph->n_nodes; ++i) {
        if (i) std::fputc(',', out);
        ggml_backend_t assigned = ggml_backend_sched_get_tensor_backend(
            sched, graph->nodes[i]);
        if (!assigned) fail("inventory node backend missing");
        std::fprintf(out, "\"%s\"", ggml_backend_name(assigned));
    }
    std::fputs("]}\n", out);
    if (std::fclose(out) != 0) fail("cannot close split graph inventory");
}

ggml_status split_graph_compute_hook(ggml_cgraph * graph,
                                     ggml_backend_sched_t sched,
                                     ggml_backend_t backend_cpu,
                                     void * user_data) {
    auto * state = static_cast<split_graph_hook_state *>(user_data);
    if (!state || state->invoked || !state->reference || !backend_cpu ||
        !graph || graph->n_nodes <= 0) {
        fail("invalid split graph hook invocation");
    }
    state->invoked = true;
    state->total_nodes = graph->n_nodes;
    auto find_anchor = [&](const char * name) {
        int index = -1;
        for (int i = 0; i < graph->n_nodes; ++i) {
            if (std::strcmp(graph->nodes[i]->name, name) == 0) {
                if (index != -1) fail(std::string("duplicate graph anchor: ") + name);
                index = i;
            }
        }
        if (index < 0) fail(std::string("missing graph anchor: ") + name);
        return index;
    };
    state->activation_idx = find_anchor("attn_post_norm-0");
    state->topk_idx = find_anchor("ffn_moe_topk-0");
    state->weights_idx = find_anchor("ffn_moe_weights_softmax-0");
    state->moe_out_idx = find_anchor("ffn_moe_out-0");
    if (!(state->activation_idx < state->topk_idx &&
          state->topk_idx < state->weights_idx &&
          state->weights_idx < state->moe_out_idx &&
          state->moe_out_idx + 1 < graph->n_nodes)) {
        fail("split graph anchors not unique and ordered");
    }
    state->all_nodes_cpu = true;
    for (int i = 0; i < graph->n_nodes; ++i) {
        ggml_tensor * node = graph->nodes[i];
        if (ggml_backend_sched_get_tensor_backend(sched, node) != backend_cpu ||
            !node->buffer || !node->data) {
            state->all_nodes_cpu = false;
            fail("STATIC_NO_GO_DIRECT_CPU_GRAPH_VIEWS_NOT_SINGLE_BACKEND");
        }
    }
    std::unordered_set<ggml_tensor *> middle_nodes;
    std::unordered_set<ggml_tensor *> moe_ancestors;
    collect_graph_ancestors(graph->nodes[state->moe_out_idx], moe_ancestors);
    for (int i = state->weights_idx + 1; i <= state->moe_out_idx; ++i) {
        ggml_tensor * node = graph->nodes[i];
        middle_nodes.insert(node);
        if (!moe_ancestors.count(node)) {
            fail("STATIC_NO_GO_SPLIT_MIDDLE_NOT_ANCESTOR_OF_MOE_OUTPUT");
        }
        if (node->op == GGML_OP_MUL_MAT_ID) ++state->mul_mat_id_count;
    }
    if (state->mul_mat_id_count == 0) {
        fail("STATIC_NO_GO_SPLIT_MIDDLE_HAS_NO_EXPERT_COMPUTE");
    }
    state->middle_contiguous = true;
    ggml_tensor * moe_out = graph->nodes[state->moe_out_idx];
    for (int i = state->moe_out_idx + 1; i < graph->n_nodes; ++i) {
        for (ggml_tensor * src : graph->nodes[i]->src) {
            if (src == moe_out) state->downstream_depends_on_moe_out = true;
            if (src != moe_out && middle_nodes.count(src)) {
                fail("STATIC_NO_GO_SUFFIX_HAS_SIDE_DEPENDENCY_ON_MIDDLE");
            }
        }
    }
    if (!state->downstream_depends_on_moe_out) {
        fail("STATIC_NO_GO_SUFFIX_DOES_NOT_CONSUME_MOE_OUTPUT");
    }

    auto prefix = ggml_graph_view(graph, 0, state->weights_idx + 1);
    auto middle = ggml_graph_view(graph, state->weights_idx + 1,
                                  state->moe_out_idx + 1);
    auto suffix = ggml_graph_view(graph, state->moe_out_idx + 1,
                                  graph->n_nodes);
    const auto compute = [&](ggml_cgraph * view, const char * label) {
        if (ggml_backend_graph_compute(backend_cpu, view) != GGML_STATUS_SUCCESS) {
            fail(std::string("direct CPU graph view failed: ") + label);
        }
    };
    compute(&prefix, "prefix");
    ++state->prefix_compute_count;
    const auto & ref = *state->reference;
    const auto activation = read_live_tensor<float>(
        graph->nodes[state->activation_idx], GGML_TYPE_F32,
        static_cast<size_t>(k_embd), "split activation");
    const auto experts = read_live_tensor<int32_t>(
        graph->nodes[state->topk_idx], GGML_TYPE_I32,
        static_cast<size_t>(k_top_k), "split experts");
    const auto weights = read_live_tensor<float>(
        graph->nodes[state->weights_idx], GGML_TYPE_F32,
        static_cast<size_t>(k_top_k), "split weights");
    if (!float_vectors_bitwise_equal(activation, ref.activation) ||
        experts != ref.experts || experts != std::vector<int32_t>{1, 13, 17, 21} ||
        !float_vectors_bitwise_equal(weights, ref.weights)) {
        fail("split graph live activation/route differs from frozen reference");
    }
    if (state->skip_middle) {
        if (!state->injection || state->injection->size() != static_cast<size_t>(k_embd)) {
            fail("split graph injection missing or wrong size");
        }
        for (float value : *state->injection) {
            if (!std::isfinite(value)) fail("split graph injection non-finite");
        }
        ggml_backend_tensor_set(moe_out, state->injection->data(), 0,
                                state->injection->size() * sizeof(float));
        const auto observed = read_live_tensor<float>(
            moe_out, GGML_TYPE_F32, static_cast<size_t>(k_embd),
            "split written moe output");
        state->injected_bytes_verified = float_vectors_bitwise_equal(
            observed, *state->injection);
        if (!state->injected_bytes_verified) fail("split graph injection did not persist");
        state->observed_moe_output = observed;
        ++state->injected_output_count;
    } else {
        compute(&middle, "middle");
        ++state->middle_compute_count;
        const auto observed = read_live_tensor<float>(
            moe_out, GGML_TYPE_F32, static_cast<size_t>(k_embd),
            "split computed moe output");
        state->stock_output_parity = compare_outputs(ref.stock_output, observed);
        state->stock_output_bitwise = float_vectors_bitwise_equal(
            ref.stock_output, observed);
        state->observed_moe_output = observed;
        if (!state->stock_output_parity.pass) {
            fail("segmented stock MoE differs from frozen reference");
        }
    }
    compute(&suffix, "suffix");
    ++state->suffix_compute_count;
    write_split_graph_inventory(*state, graph, sched);
    return GGML_STATUS_SUCCESS;
}

struct split_graph_arm_result {
    reinjection_arm_result base;
    split_graph_hook_state hook;
    std::vector<float> reference_ffn;
    std::vector<float> candidate_ffn;
};

split_graph_arm_result run_split_graph_arm(
        const options & opt, llama_model * model,
        const std::vector<llama_token> & prompt_tokens,
        ggml_backend_t cpu_backend, ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        ggml_backend_buffer_type_t gpu_buft) {
    if (!llama_tesy_set_graph_compute_hook) {
        fail("split arm requires patched llama hook symbol");
    }
    const int gpu_hits = opt.split_arm == "h2" ? 2 :
                         opt.split_arm == "h3" ? 3 : 0;
    live_handoff_capture capture;
    llama_context_params params = llama_context_default_params();
    params.n_ctx = opt.live_ctx;
    params.n_batch = static_cast<uint32_t>(prompt_tokens.size());
    params.n_ubatch = static_cast<uint32_t>(prompt_tokens.size());
    params.n_threads = opt.threads;
    params.n_threads_batch = opt.threads;
    params.no_perf = true;
    params.cb_eval = live_handoff_callback;
    params.cb_eval_user_data = &capture;
    llama_context * ctx = llama_init_from_model(model, params);
    if (!ctx) fail("split arm context creation failed");
    llama_sampler_chain_params sampler_params = llama_sampler_chain_default_params();
    sampler_params.no_perf = true;
    llama_sampler * sampler = llama_sampler_chain_init(sampler_params);
    llama_sampler_chain_add(sampler, llama_sampler_init_greedy());

    split_graph_arm_result result;
    result.base.name = opt.split_arm;
    result.base.gpu_hits = gpu_hits;
    llama_batch prompt_batch = llama_batch_get_one(
        const_cast<llama_token *>(prompt_tokens.data()),
        static_cast<int32_t>(prompt_tokens.size()));
    if (llama_decode(ctx, prompt_batch) != 0) fail("split prompt decode failed");
    result.base.first_token = llama_sampler_sample(sampler, ctx, -1);
    if (result.base.first_token != 2167) fail("split first greedy token is not 2167");

    const llama_pos position = static_cast<llama_pos>(prompt_tokens.size());
    reset_live_handoff_capture(capture, live_handoff_arm::stock_reference);
    llama_batch capture_batch = llama_batch_get_one(&result.base.first_token, 1);
    if (llama_decode(ctx, capture_batch) != 0) fail("split stock capture failed");
    validate_live_handoff_capture(capture, true, "split stock reference");
    const live_handoff_capture reference = capture;
    result.base.stock_capture_rollback = llama_memory_seq_rm(
        llama_get_memory(ctx), 0, position, -1);
    if (!result.base.stock_capture_rollback) fail("split stock capture rollback failed");

    std::vector<float> injection;
    std::unique_ptr<live_routed_executor> executor;
    if (gpu_hits > 0) {
        reset_live_handoff_capture(capture, live_handoff_arm::handoff);
        llama_batch handoff_batch = llama_batch_get_one(&result.base.first_token, 1);
        if (llama_decode(ctx, handoff_batch) != 0) fail("split handoff capture failed");
        validate_live_handoff_capture(capture, false, "split handoff");
        const live_handoff_capture handoff = capture;
        result.base.handoff_capture_rollback = llama_memory_seq_rm(
            llama_get_memory(ctx), 0, position, -1);
        if (!result.base.handoff_capture_rollback) fail("split handoff rollback failed");
        if (reference.experts != handoff.experts ||
            !float_vectors_bitwise_equal(reference.weights, handoff.weights)) {
            fail("split handoff route drift");
        }
        result.base.activation_pair_parity = compare_outputs(
            reference.activation, handoff.activation);
        result.base.activation_pair_bitwise = float_vectors_bitwise_equal(
            reference.activation, handoff.activation);
        if (!result.base.activation_pair_parity.pass ||
            !result.base.activation_pair_bitwise) fail("split handoff activation drift");
        options routed = opt;
        routed.routed_gpu_hits = gpu_hits;
        std::vector<int> selected(reference.experts.begin(), reference.experts.end());
        executor = make_live_routed_executor(
            routed, cpu_backend, gpu_backend, cpu_weight_buft, cpu_bias_buft,
            gpu_buft, handoff.activation, selected, handoff.weights);
        execute_live_routed_serial(*executor, cpu_backend, gpu_backend,
                                   handoff.activation);
        injection = read_live_routed_output(*executor, gpu_backend);
    } else {
        result.base.handoff_capture_rollback = true;
        result.base.activation_pair_bitwise = true;
        result.base.activation_pair_parity = compare_outputs(
            reference.activation, reference.activation);
        injection = reference.stock_output;
    }
    result.base.experts = reference.experts;
    result.base.weights = reference.weights;
    result.base.ffn_parity = compare_outputs(reference.stock_output, injection);
    result.base.ffn_bitwise = float_vectors_bitwise_equal(
        reference.stock_output, injection);
    if (!result.base.ffn_parity.pass) fail("split Tesy FFN parity failed");
    result.reference_ffn = reference.stock_output;
    capture.enabled = false;

    result.hook.reference = &reference;
    result.hook.skip_middle = opt.split_arm != "segmented";
    result.hook.injection = result.hook.skip_middle ? &injection : nullptr;
    result.hook.inventory_path =
        (std::filesystem::path(opt.output).parent_path() / "inventory.json").string();
    llama_tesy_set_graph_compute_hook(ctx, split_graph_compute_hook, &result.hook);
    llama_batch committed_batch = llama_batch_get_one(&result.base.first_token, 1);
    result.base.committed_decode_return_code = llama_decode(ctx, committed_batch);
    llama_tesy_set_graph_compute_hook(ctx, nullptr, nullptr);
    if (result.base.committed_decode_return_code != 0 || !result.hook.invoked ||
        result.hook.prefix_compute_count != 1 ||
        result.hook.suffix_compute_count != 1 ||
        result.hook.middle_compute_count != (result.hook.skip_middle ? 0 : 1) ||
        result.hook.injected_output_count != (result.hook.skip_middle ? 1 : 0)) {
        fail("split committed decode or view counts failed");
    }
    const size_t n_vocab = static_cast<size_t>(
        llama_vocab_n_tokens(llama_model_get_vocab(model)));
    result.base.logits_a = copy_reinjection_logits(ctx, n_vocab);
    result.base.second_token = llama_sampler_sample(sampler, ctx, -1);
    if (result.base.second_token != 1309) fail("split second token is not 1309");
    llama_batch continuation_batch = llama_batch_get_one(&result.base.second_token, 1);
    result.base.continuation_decode_return_code = llama_decode(ctx, continuation_batch);
    if (result.base.continuation_decode_return_code != 0) {
        fail("split committed continuation failed");
    }
    result.base.logits_b = copy_reinjection_logits(ctx, n_vocab);
    result.base.third_token = llama_sampler_sample(sampler, ctx, -1);
    if (result.base.third_token != 316) fail("split third token is not 316");
    result.candidate_ffn = result.hook.observed_moe_output;
    result.base.ffn_parity = compare_outputs(
        reference.stock_output, result.candidate_ffn);
    result.base.ffn_bitwise = float_vectors_bitwise_equal(
        reference.stock_output, result.candidate_ffn);
    if (!result.base.ffn_parity.pass) fail("split final FFN output parity failed");
    result.hook.reference = nullptr;
    result.hook.injection = nullptr;
    llama_sampler_free(sampler);
    llama_free(ctx);
    return result;
}

void run_split_graph_skip_exactness(
        const options & opt, ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        ggml_backend_buffer_type_t gpu_buft) {
    const std::string prompt = read_prompt_file(opt.prompt_file);
    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 0;
    llama_model * model = llama_model_load_from_file(opt.model.c_str(), model_params);
    if (!model) fail("split model load failed");
    const auto prompt_tokens = tokenize_prompt(llama_model_get_vocab(model), prompt);
    if (prompt_tokens.size() + 8 > opt.live_ctx) fail("split context too small");

    reinjection_arm_result base;
    split_graph_hook_state hook;
    if (opt.split_arm == "stock" || opt.split_arm == "null") {
        base = run_reinjection_arm(
            opt, model, prompt_tokens, opt.split_arm, 0,
            cpu_backend, gpu_backend, cpu_weight_buft, cpu_bias_buft,
            gpu_buft, nullptr, opt.split_arm == "null");
    } else {
        auto split = run_split_graph_arm(
            opt, model, prompt_tokens, cpu_backend, gpu_backend,
            cpu_weight_buft, cpu_bias_buft, gpu_buft);
        const auto root = std::filesystem::path(opt.output).parent_path();
        write_reinjection_logits((root / "ffn-reference.f32").string(),
                                 split.reference_ffn);
        write_reinjection_logits((root / "ffn-candidate.f32").string(),
                                 split.candidate_ffn);
        base = std::move(split.base);
        hook = std::move(split.hook);
    }
    llama_model_free(model);
    if (base.first_token != 2167 || base.second_token != 1309 ||
        base.third_token != 316 || base.logits_a.size() != 201088 ||
        base.logits_b.size() != 201088) {
        fail("split arm frozen token/logits count failed");
    }
    const auto root = std::filesystem::path(opt.output).parent_path();
    write_reinjection_logits((root / "logits-a.f32").string(), base.logits_a);
    write_reinjection_logits((root / "logits-b.f32").string(), base.logits_b);
    FILE * out = std::fopen(opt.output.c_str(), "wx");
    if (!out) fail("cannot create split raw output");
    std::fprintf(out,
        "{\"schema\":\"tesy.live_moe_split_graph_skip_exactness_raw.v1\","
        "\"classification\":\"MEASURED_LIVE_MOE_SPLIT_GRAPH_SKIP_EXACTNESS_RAW\","
        "\"arm\":\"%s\",\"layer\":0,\"ngl\":0,\"threads\":%d,"
        "\"first_token\":%" PRId32 ",\"second_token\":%" PRId32
        ",\"third_token\":%" PRId32 ",\"gpu_hits\":%d,"
        "\"committed_decode_return_code\":%d,"
        "\"continuation_decode_return_code\":%d,"
        "\"stock_capture_rollback\":%s,\"handoff_capture_rollback\":%s,"
        "\"activation_pair_bitwise\":%s,\"ffn_bitwise\":%s,"
        "\"prefix_compute_count\":%d,\"middle_compute_count\":%d,"
        "\"suffix_compute_count\":%d,\"injected_output_count\":%d,"
        "\"injected_bytes_verified\":%s,\"all_nodes_cpu\":%s,"
        "\"middle_contiguous\":%s,\"downstream_depends_on_moe_out\":%s,"
        "\"logits_a_file\":\"logits-a.f32\","
        "\"logits_b_file\":\"logits-b.f32\","
        "\"ffn_reference_file\":%s,\"ffn_candidate_file\":%s,"
        "\"selected_experts\":[",
        base.name.c_str(), opt.threads, base.first_token, base.second_token,
        base.third_token, base.gpu_hits, base.committed_decode_return_code,
        base.continuation_decode_return_code,
        base.stock_capture_rollback ? "true" : "false",
        base.handoff_capture_rollback ? "true" : "false",
        base.activation_pair_bitwise ? "true" : "false",
        base.ffn_bitwise ? "true" : "false",
        hook.prefix_compute_count, hook.middle_compute_count,
        hook.suffix_compute_count, hook.injected_output_count,
        hook.injected_bytes_verified ? "true" : "false",
        hook.all_nodes_cpu ? "true" : "false",
        hook.middle_contiguous ? "true" : "false",
        hook.downstream_depends_on_moe_out ? "true" : "false",
        hook.invoked ? "\"ffn-reference.f32\"" : "null",
        hook.invoked ? "\"ffn-candidate.f32\"" : "null");
    for (size_t i = 0; i < base.experts.size(); ++i) {
        if (i) std::fputc(',', out);
        std::fprintf(out, "%" PRId32, base.experts[i]);
    }
    std::fputs("],\"routing_weights\":[", out);
    for (size_t i = 0; i < base.weights.size(); ++i) {
        if (i) std::fputc(',', out);
        std::fprintf(out, "%.9g", base.weights[i]);
    }
    std::fputs("],\"ffn_parity\":", out);
    print_reinjection_parity(out, base.ffn_parity);
    std::fputs(",\"stock_output_parity\":", out);
    print_reinjection_parity(out, hook.stock_output_parity);
    std::fprintf(out,
        ",\"stock_output_bitwise\":%s,\"inventory_file\":%s,"
        "\"claim_boundary\":\"Layer-0 CPU graph split/skip correctness only; no timing, cache or prefetch.\"}\n",
        hook.stock_output_bitwise ? "true" : "false",
        hook.invoked ? "\"inventory.json\"" : "null");
    if (std::fclose(out) != 0) fail("cannot close split raw output");
    std::puts("PASS_SPLIT_GRAPH_RAW");
}

struct vertical_layer_runtime {
    tensor_set borrowed_cpu;
    std::unique_ptr<tensor_set> gpu_resident;
    std::array<std::unique_ptr<compute_graph>, 5> cpu_graphs;
    std::array<std::unique_ptr<compute_graph>, 5> gpu_graphs;
    std::unique_ptr<sum_graph> aggregate;
    std::array<ggml_tensor *, 6> stock_tensors{};
    bool initialized = false;
};

std::array<ggml_tensor *, 6> vertical_stock_tensors(
        ggml_cgraph * graph, int layer) {
    const std::array<const char *, 6> suffixes{
        "ffn_moe_gate-", "ffn_moe_up-", "ffn_moe_down-",
        "ffn_moe_gate_biased-", "ffn_moe_up_biased-",
        "ffn_moe_down_biased-"};
    std::array<ggml_tensor *, 6> result{};
    for (size_t kind = 0; kind < suffixes.size(); ++kind) {
        const std::string name = std::string(suffixes[kind]) + std::to_string(layer);
        ggml_tensor * operation = nullptr;
        for (int i = 0; i < graph->n_nodes; ++i) {
            if (name == graph->nodes[i]->name) {
                if (operation) fail("vertical graph has duplicate expert operation");
                operation = graph->nodes[i];
            }
        }
        if (!operation || operation->op !=
            (kind < 3 ? GGML_OP_MUL_MAT_ID : GGML_OP_ADD_ID)) {
            fail("vertical graph missing expected expert operation: " + name);
        }
        result[kind] = operation->src[kind < 3 ? 0 : 1];
        if (!result[kind] || !result[kind]->buffer) {
            fail("vertical stock expert tensor is not allocated");
        }
    }
    for (size_t kind = 0; kind < result.size(); ++kind) {
        auto * tensor = result[kind];
        const bool weight = kind < 3;
        if (tensor->type != (weight ? GGML_TYPE_MXFP4 : GGML_TYPE_F32) ||
            tensor->ne[0] != k_embd ||
            tensor->ne[1] != (weight ? k_embd : k_expert_count) ||
            tensor->ne[2] != (weight ? k_expert_count : 1) ||
            !ggml_is_contiguous(tensor)) {
            fail("vertical stock expert tensor shape/type mismatch");
        }
    }
    return result;
}

tensor_bytes vertical_resident_bytes(
        const std::array<ggml_tensor *, 6> & tensors,
        const std::vector<int32_t> & resident) {
    tensor_bytes result;
    const std::array<std::vector<uint8_t> *, 6> destinations{
        &result.gate_w, &result.up_w, &result.down_w,
        &result.gate_b, &result.up_b, &result.down_b};
    for (size_t kind = 0; kind < tensors.size(); ++kind) {
        auto * tensor = tensors[kind];
        const size_t per_expert = ggml_nbytes(tensor) /
            static_cast<size_t>(k_expert_count);
        const size_t stride = tensor->nb[kind < 3 ? 2 : 1];
        if (per_expert == 0 || stride != per_expert ||
            ggml_nbytes(tensor) != per_expert * k_expert_count) {
            fail("vertical stock expert tensor is not expert-contiguous");
        }
        auto & bytes = *destinations[kind];
        bytes.resize(per_expert * resident.size());
        for (size_t slot = 0; slot < resident.size(); ++slot) {
            ggml_backend_tensor_get(tensor, bytes.data() + slot * per_expert,
                static_cast<size_t>(resident[slot]) * per_expert, per_expert);
        }
    }
    if (result.total() != resident.size() * k_encoded_bytes_per_expert) {
        fail("vertical resident extraction encoded byte count mismatch");
    }
    return result;
}

void vertical_set_graph_inputs(compute_graph & graph,
                               const std::vector<float> & activation,
                               const std::vector<int32_t> & ids,
                               const std::vector<float> & weights) {
    if (activation.size() != static_cast<size_t>(k_embd) || ids.empty() ||
        ids.size() != weights.size() ||
        ggml_nelements(graph.ids) != static_cast<int64_t>(ids.size()) ||
        ggml_nelements(graph.mix) != static_cast<int64_t>(weights.size())) {
        fail("vertical graph input shape mismatch");
    }
    ggml_backend_tensor_set(graph.input, activation.data(), 0,
                            activation.size() * sizeof(float));
    ggml_backend_tensor_set(graph.ids, ids.data(), 0,
                            ids.size() * sizeof(int32_t));
    ggml_backend_tensor_set(graph.mix, weights.data(), 0,
                            weights.size() * sizeof(float));
}

std::vector<float> vertical_compute_route(
        vertical_layer_runtime & layer,
        ggml_backend_t cpu_backend, ggml_backend_t gpu_backend,
        const std::vector<float> & activation,
        const tesy_route_partition & route) {
    const size_t n_cpu = route.cpu_global_ids.size();
    const size_t n_gpu = route.gpu_global_ids.size();
    if (n_cpu + n_gpu != static_cast<size_t>(k_top_k)) {
        fail("vertical route lost selected experts");
    }
    compute_graph * cpu = nullptr;
    compute_graph * gpu = nullptr;
    if (n_cpu) {
        if (!layer.cpu_graphs[n_cpu]) {
            layer.cpu_graphs[n_cpu] = make_compute_graph(
                layer.borrowed_cpu, cpu_backend, static_cast<int>(n_cpu),
                activation);
        }
        cpu = layer.cpu_graphs[n_cpu].get();
        vertical_set_graph_inputs(*cpu, activation, route.cpu_global_ids,
                                  route.cpu_weights);
        compute(cpu_backend, *cpu);
    }
    if (n_gpu) {
        if (!layer.gpu_graphs[n_gpu]) {
            layer.gpu_graphs[n_gpu] = make_compute_graph(
                *layer.gpu_resident, gpu_backend, static_cast<int>(n_gpu),
                activation);
        }
        gpu = layer.gpu_graphs[n_gpu].get();
        vertical_set_graph_inputs(*gpu, activation, route.gpu_local_ids,
                                  route.gpu_weights);
        compute(gpu_backend, *gpu);
    }
    if (cpu && gpu) {
        if (!layer.aggregate) layer.aggregate = make_sum_graph(gpu_backend);
        ggml_backend_tensor_copy(gpu->output, layer.aggregate->gpu_partial);
        ggml_backend_tensor_copy(cpu->output, layer.aggregate->cpu_partial);
        ggml_backend_synchronize(cpu_backend);
        ggml_backend_synchronize(gpu_backend);
        compute_sum(gpu_backend, *layer.aggregate);
        return read_output(gpu_backend, layer.aggregate->output);
    }
    if (cpu) return read_output(cpu_backend, cpu->output);
    if (gpu) return read_output(gpu_backend, gpu->output);
    fail("vertical route has no executor");
}

size_t vertical_gpu_allocation_bytes(const vertical_layer_runtime & layer) {
    size_t result = 0;
    auto add = [&](ggml_backend_buffer_t buffer) {
        if (buffer) result += ggml_backend_buffer_get_size(buffer);
    };
    if (layer.gpu_resident) {
        add(layer.gpu_resident->weights.buffer);
        add(layer.gpu_resident->biases.buffer);
    }
    for (const auto & graph : layer.gpu_graphs) {
        if (graph) add(graph->storage.buffer);
    }
    if (layer.aggregate) add(layer.aggregate->storage.buffer);
    return result;
}

struct vertical_event {
    int token_ordinal = 0;
    int layer = 0;
    int gpu_hits = 0;
    std::vector<int32_t> experts;
    std::vector<float> weights;
    int prefix_compute_count = 1;
    int middle_compute_count = 0;
    int suffix_compute_count = 1;
    size_t gpu_allocated_bytes = 0;
};

struct vertical_reference_event {
    std::vector<float> activation;
    std::vector<int32_t> experts;
    std::vector<float> weights;
    std::vector<float> output;
};

struct vertical_reference_state {
    bool enabled = false;
    int token_ordinal = 0;
    std::vector<std::array<vertical_reference_event, 24>> events;
};

bool vertical_reference_callback(ggml_tensor * tensor, bool ask,
                                 void * user_data) {
    auto * state = static_cast<vertical_reference_state *>(user_data);
    if (!state) fail("vertical stock reference callback state missing");
    if (!state->enabled) return ask ? false : true;
    for (int layer = 0; layer < 24; ++layer) {
        const std::string suffix = std::to_string(layer);
        const std::array<std::string, 4> names{
            "attn_post_norm-" + suffix,
            "ffn_moe_topk-" + suffix,
            "ffn_moe_weights_softmax-" + suffix,
            "ffn_moe_out-" + suffix};
        for (size_t kind = 0; kind < names.size(); ++kind) {
            if (names[kind] != tensor->name) continue;
            if (ask) return true;
            auto & event = state->events.at(
                static_cast<size_t>(state->token_ordinal))[static_cast<size_t>(layer)];
            if (kind == 0) {
                if (!event.activation.empty()) fail("duplicate stock activation capture");
                event.activation = read_live_tensor<float>(
                    tensor, GGML_TYPE_F32, static_cast<size_t>(k_embd),
                    "vertical stock activation");
            } else if (kind == 1) {
                if (!event.experts.empty()) fail("duplicate stock route capture");
                event.experts = read_live_tensor<int32_t>(
                    tensor, GGML_TYPE_I32, static_cast<size_t>(k_top_k),
                    "vertical stock expert IDs");
            } else if (kind == 2) {
                if (!event.weights.empty()) fail("duplicate stock weights capture");
                event.weights = read_live_tensor<float>(
                    tensor, GGML_TYPE_F32, static_cast<size_t>(k_top_k),
                    "vertical stock routing weights");
            } else {
                if (!event.output.empty()) fail("duplicate stock FFN capture");
                event.output = read_live_tensor<float>(
                    tensor, GGML_TYPE_F32, static_cast<size_t>(k_embd),
                    "vertical stock FFN output");
            }
            return true;
        }
    }
    return ask ? false : true;
}

struct vertical_hook_state {
    ggml_backend_t cpu_backend = nullptr;
    ggml_backend_t gpu_backend = nullptr;
    ggml_backend_buffer_type_t gpu_buft = nullptr;
    int layers_to_replace = 0;
    int token_ordinal = 0;
    bool active = false;
    bool invoked = false;
    const vertical_reference_state * reference = nullptr;
    std::array<vertical_layer_runtime, 24> layers;
    std::vector<vertical_event> events;
};

int vertical_find_anchor(ggml_cgraph * graph, const std::string & name) {
    int result = -1;
    for (int i = 0; i < graph->n_nodes; ++i) {
        if (name == graph->nodes[i]->name) {
            if (result != -1) fail("vertical duplicate graph anchor: " + name);
            result = i;
        }
    }
    if (result < 0) fail("vertical missing graph anchor: " + name);
    return result;
}

ggml_status vertical_live_compute_hook(ggml_cgraph * graph,
                                       ggml_backend_sched_t sched,
                                       ggml_backend_t backend_cpu,
                                       void * user_data) {
    auto * state = static_cast<vertical_hook_state *>(user_data);
    if (!state || !state->active || state->invoked || !graph ||
        !sched || !backend_cpu || !state->cpu_backend ||
        !state->gpu_backend || !state->gpu_buft) {
        fail("vertical hook state invalid or invoked twice");
    }
    state->invoked = true;
    for (int i = 0; i < graph->n_nodes; ++i) {
        ggml_tensor * node = graph->nodes[i];
        if (ggml_backend_sched_get_tensor_backend(sched, node) != backend_cpu ||
            !node->buffer || !node->data) {
            fail("VERTICAL_BLOCKER_STOCK_GRAPH_NOT_SINGLE_CPU_BACKEND");
        }
    }
    int cursor = 0;
    const std::vector<int32_t> resident_ids{0, 1, 2, 3};
    for (int layer_index = 0; layer_index < state->layers_to_replace; ++layer_index) {
        auto name = [&](const char * prefix) {
            return std::string(prefix) + std::to_string(layer_index);
        };
        const int activation_index = vertical_find_anchor(
            graph, name("attn_post_norm-"));
        const int topk_index = vertical_find_anchor(graph, name("ffn_moe_topk-"));
        const int weights_index = vertical_find_anchor(
            graph, name("ffn_moe_weights_softmax-"));
        const int moe_out_index = vertical_find_anchor(graph, name("ffn_moe_out-"));
        if (!(cursor <= activation_index && activation_index < topk_index &&
              topk_index < weights_index && weights_index < moe_out_index &&
              moe_out_index + 1 < graph->n_nodes)) {
            fail("VERTICAL_BLOCKER_LAYER_BOUNDARIES_NOT_ORDERED");
        }
        std::unordered_set<ggml_tensor *> middle;
        std::unordered_set<ggml_tensor *> ancestors;
        collect_graph_ancestors(graph->nodes[moe_out_index], ancestors);
        int expert_matmuls = 0;
        for (int i = weights_index + 1; i <= moe_out_index; ++i) {
            auto * node = graph->nodes[i];
            if (!ancestors.count(node)) fail("VERTICAL_BLOCKER_MIDDLE_NOT_CONTIGUOUS");
            middle.insert(node);
            if (node->op == GGML_OP_MUL_MAT_ID) ++expert_matmuls;
        }
        if (expert_matmuls != 3) fail("vertical expert matmul count changed");
        bool consumed = false;
        for (int i = moe_out_index + 1; i < graph->n_nodes; ++i) {
            for (auto * src : graph->nodes[i]->src) {
                if (src == graph->nodes[moe_out_index]) consumed = true;
                if (src != graph->nodes[moe_out_index] && middle.count(src)) {
                    fail("VERTICAL_BLOCKER_SUFFIX_DEPENDS_ON_SKIPPED_MIDDLE");
                }
            }
        }
        if (!consumed) fail("VERTICAL_BLOCKER_SUFFIX_IGNORES_INJECTED_OUTPUT");
        auto prefix = ggml_graph_view(graph, cursor, weights_index + 1);
        if (ggml_backend_graph_compute(backend_cpu, &prefix) != GGML_STATUS_SUCCESS) {
            fail("vertical CPU prefix graph compute failed");
        }
        const auto activation = read_live_tensor<float>(
            graph->nodes[activation_index], GGML_TYPE_F32,
            static_cast<size_t>(k_embd), "vertical activation");
        const auto experts = read_live_tensor<int32_t>(
            graph->nodes[topk_index], GGML_TYPE_I32,
            static_cast<size_t>(k_top_k), "vertical expert IDs");
        const auto weights = read_live_tensor<float>(
            graph->nodes[weights_index], GGML_TYPE_F32,
            static_cast<size_t>(k_top_k), "vertical routing weights");
        if (state->reference) {
            const auto & ref = state->reference->events.at(
                static_cast<size_t>(state->token_ordinal))[
                static_cast<size_t>(layer_index)];
            if (experts != ref.experts ||
                !float_vectors_bitwise_equal(weights, ref.weights)) {
                fail("vertical live route drift vs separate stock reference at layer " +
                     std::to_string(layer_index));
            }
            if (!compare_outputs(ref.activation, activation).pass) {
                fail("vertical activation drift vs separate stock reference at layer " +
                     std::to_string(layer_index));
            }
        }
        const auto partition = tesy_partition_route(
            experts, weights, resident_ids, static_cast<int32_t>(k_expert_count));
        auto & layer = state->layers[static_cast<size_t>(layer_index)];
        const auto stock_tensors = vertical_stock_tensors(graph, layer_index);
        if (!layer.initialized) {
            layer.stock_tensors = stock_tensors;
            layer.borrowed_cpu.gate_w = stock_tensors[0];
            layer.borrowed_cpu.up_w = stock_tensors[1];
            layer.borrowed_cpu.down_w = stock_tensors[2];
            layer.borrowed_cpu.gate_b = stock_tensors[3];
            layer.borrowed_cpu.up_b = stock_tensors[4];
            layer.borrowed_cpu.down_b = stock_tensors[5];
            const tensor_bytes bytes = vertical_resident_bytes(
                stock_tensors, resident_ids);
            layer.gpu_resident = make_tensor_set(
                bytes, static_cast<int>(resident_ids.size()),
                state->gpu_buft, state->gpu_buft);
            layer.initialized = true;
        } else if (layer.stock_tensors != stock_tensors) {
            fail("vertical stock weight tensor identity changed across decodes");
        }
        const auto output = vertical_compute_route(
            layer, state->cpu_backend, state->gpu_backend,
            activation, partition);
        if (state->reference) {
            const auto & ref = state->reference->events.at(
                static_cast<size_t>(state->token_ordinal))[
                static_cast<size_t>(layer_index)];
            const parity p = compare_outputs(ref.output, output);
            if (!p.pass) {
                std::fprintf(stderr,
                    "vertical FFN failure token=%d layer=%d h=%zu "
                    "rel=%.9g cosine=%.12f max_abs=%.9g max_ref=%.9g\n",
                    state->token_ordinal, layer_index,
                    partition.gpu_global_ids.size(), p.relative_max,
                    p.cosine, p.max_abs, p.max_abs_ref);
                fail("vertical live FFN differs from separate stock reference");
            }
        }
        for (float value : output) {
            if (!std::isfinite(value)) fail("vertical FFN output is non-finite");
        }
        ggml_tensor * moe_out = graph->nodes[moe_out_index];
        if (moe_out->type != GGML_TYPE_F32 ||
            !ggml_is_contiguous(moe_out) ||
            ggml_nelements(moe_out) != k_embd) {
            fail("vertical MoE output tensor metadata changed");
        }
        ggml_backend_tensor_set(moe_out, output.data(), 0,
                                output.size() * sizeof(float));
        const auto observed = read_live_tensor<float>(
            moe_out, GGML_TYPE_F32, static_cast<size_t>(k_embd),
            "vertical injected output");
        if (!float_vectors_bitwise_equal(output, observed)) {
            fail("vertical injection bytes did not persist");
        }
        size_t allocated = 0;
        for (const auto & item : state->layers) {
            allocated += vertical_gpu_allocation_bytes(item);
        }
        size_t free_vram = 0;
        size_t total_vram = 0;
        ggml_backend_dev_memory(ggml_backend_get_device(state->gpu_backend),
                                &free_vram, &total_vram);
        if (allocated > 5ull * 1024 * 1024 * 1024 ||
            free_vram < 1024ull * 1024 * 1024 ||
            total_vram < 7ull * 1024 * 1024 * 1024) {
            fail("vertical GPU resident buffer or free VRAM guard failed");
        }
        state->events.push_back({
            state->token_ordinal, layer_index,
            static_cast<int>(partition.gpu_global_ids.size()),
            experts, weights, 1, 0, 1, allocated});
        cursor = moe_out_index + 1;
    }
    auto suffix = ggml_graph_view(graph, cursor, graph->n_nodes);
    if (ggml_backend_graph_compute(backend_cpu, &suffix) != GGML_STATUS_SUCCESS) {
        fail("vertical CPU suffix graph compute failed");
    }
    return GGML_STATUS_SUCCESS;
}

llama_context * vertical_make_context(llama_model * model,
                                      size_t prompt_count,
                                      const options & opt,
                                      vertical_reference_state * reference = nullptr) {
    llama_context_params params = llama_context_default_params();
    params.n_ctx = opt.live_ctx;
    params.n_batch = static_cast<uint32_t>(prompt_count);
    params.n_ubatch = static_cast<uint32_t>(prompt_count);
    params.n_threads = opt.threads;
    params.n_threads_batch = opt.threads;
    params.no_perf = true;
    if (reference) {
        params.cb_eval = vertical_reference_callback;
        params.cb_eval_user_data = reference;
    }
    llama_context * ctx = llama_init_from_model(model, params);
    if (!ctx) fail("vertical context creation failed");
    return ctx;
}

llama_sampler * vertical_make_greedy_sampler() {
    llama_sampler_chain_params params = llama_sampler_chain_default_params();
    params.no_perf = true;
    llama_sampler * sampler = llama_sampler_chain_init(params);
    llama_sampler_chain_add(sampler, llama_sampler_init_greedy());
    return sampler;
}

void run_vertical_live_exactness(
        const options & opt, ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t gpu_buft) {
    if (!llama_tesy_set_graph_compute_hook) {
        fail("vertical live requires patched llama compute hook");
    }
    const std::string prompt = read_prompt_file(opt.prompt_file);
    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 0;
    llama_model * model = llama_model_load_from_file(
        opt.model.c_str(), model_params);
    if (!model) fail("vertical model load failed");
    const llama_vocab * vocab = llama_model_get_vocab(model);
    const auto prompt_tokens = tokenize_prompt(vocab, prompt);
    if (prompt_tokens.size() + static_cast<size_t>(opt.vertical_tokens) + 1 >
        opt.live_ctx) {
        fail("vertical prompt and generation exceed context");
    }
    const size_t n_vocab = static_cast<size_t>(llama_vocab_n_tokens(vocab));
    if (n_vocab != 201088) fail("vertical vocabulary identity changed");

    std::vector<llama_token> stock_tokens;
    std::vector<std::vector<float>> stock_logits;
    {
        llama_context * ctx = vertical_make_context(model, prompt_tokens.size(), opt);
        llama_sampler * sampler = vertical_make_greedy_sampler();
        llama_batch prompt_batch = llama_batch_get_one(
            const_cast<llama_token *>(prompt_tokens.data()),
            static_cast<int32_t>(prompt_tokens.size()));
        if (llama_decode(ctx, prompt_batch) != 0) fail("vertical stock prefill failed");
        stock_tokens.push_back(llama_sampler_sample(sampler, ctx, -1));
        for (int ordinal = 0; ordinal < opt.vertical_tokens; ++ordinal) {
            if (llama_vocab_is_eog(vocab, stock_tokens.back())) break;
            llama_token input = stock_tokens.back();
            llama_batch batch = llama_batch_get_one(&input, 1);
            if (llama_decode(ctx, batch) != 0) fail("vertical stock committed decode failed");
            stock_logits.push_back(copy_reinjection_logits(ctx, n_vocab));
            stock_tokens.push_back(llama_sampler_sample(sampler, ctx, -1));
        }
        llama_sampler_free(sampler);
        llama_free(ctx);
    }
    if (stock_logits.empty()) fail("vertical stock produced no continuation");

    vertical_reference_state reference;
    reference.events.resize(stock_logits.size());
    {
        llama_context * ctx = vertical_make_context(
            model, prompt_tokens.size(), opt, &reference);
        llama_batch prompt_batch = llama_batch_get_one(
            const_cast<llama_token *>(prompt_tokens.data()),
            static_cast<int32_t>(prompt_tokens.size()));
        if (llama_decode(ctx, prompt_batch) != 0) {
            fail("vertical instrumented stock prefill failed");
        }
        for (size_t ordinal = 0; ordinal < stock_logits.size(); ++ordinal) {
            reference.token_ordinal = static_cast<int>(ordinal);
            reference.enabled = true;
            llama_token input = stock_tokens[ordinal];
            llama_batch batch = llama_batch_get_one(&input, 1);
            if (llama_decode(ctx, batch) != 0) {
                fail("vertical instrumented stock decode failed");
            }
            reference.enabled = false;
            const auto logits = copy_reinjection_logits(ctx, n_vocab);
            if (!compare_outputs(stock_logits[ordinal], logits).pass) {
                fail("vertical instrumented stock differs from uninterrupted stock");
            }
            for (int layer = 0; layer < opt.vertical_layers; ++layer) {
                const auto & event = reference.events[ordinal][
                    static_cast<size_t>(layer)];
                if (event.activation.size() != static_cast<size_t>(k_embd) ||
                    event.experts.size() != static_cast<size_t>(k_top_k) ||
                    event.weights.size() != static_cast<size_t>(k_top_k) ||
                    event.output.size() != static_cast<size_t>(k_embd)) {
                    fail("vertical stock layer reference incomplete");
                }
            }
        }
        llama_free(ctx);
    }

    vertical_hook_state state;
    state.cpu_backend = cpu_backend;
    state.gpu_backend = gpu_backend;
    state.gpu_buft = gpu_buft;
    state.layers_to_replace = opt.vertical_layers;
    state.reference = &reference;
    std::vector<llama_token> candidate_tokens;
    std::vector<parity> logits_parity;
    {
        llama_context * ctx = vertical_make_context(model, prompt_tokens.size(), opt);
        llama_sampler * sampler = vertical_make_greedy_sampler();
        llama_batch prompt_batch = llama_batch_get_one(
            const_cast<llama_token *>(prompt_tokens.data()),
            static_cast<int32_t>(prompt_tokens.size()));
        if (llama_decode(ctx, prompt_batch) != 0) fail("vertical candidate prefill failed");
        candidate_tokens.push_back(llama_sampler_sample(sampler, ctx, -1));
        if (candidate_tokens.back() != stock_tokens.front()) {
            fail("vertical candidate prefill greedy token diverged");
        }
        for (size_t ordinal = 0; ordinal < stock_logits.size(); ++ordinal) {
            state.token_ordinal = static_cast<int>(ordinal);
            state.active = true;
            state.invoked = false;
            llama_tesy_set_graph_compute_hook(ctx, vertical_live_compute_hook, &state);
            llama_token input = candidate_tokens.back();
            llama_batch batch = llama_batch_get_one(&input, 1);
            const int code = llama_decode(ctx, batch);
            llama_tesy_set_graph_compute_hook(ctx, nullptr, nullptr);
            state.active = false;
            if (code != 0 || !state.invoked) {
                fail("vertical candidate committed decode or hook failed");
            }
            const auto candidate_logits = copy_reinjection_logits(ctx, n_vocab);
            const parity p = compare_outputs(stock_logits[ordinal], candidate_logits);
            logits_parity.push_back(p);
            const auto root = std::filesystem::path(opt.output).parent_path();
            const std::string stem = "token-" + std::to_string(ordinal);
            write_reinjection_logits((root / (stem + "-stock-logits.f32")).string(),
                                     stock_logits[ordinal]);
            write_reinjection_logits((root / (stem + "-candidate-logits.f32")).string(),
                                     candidate_logits);
            if (!p.pass) {
                std::fprintf(stderr,
                    "vertical logits failure token=%zu rel=%.9g cosine=%.12f "
                    "max_abs=%.9g max_ref=%.9g events=%zu\n",
                    ordinal, p.relative_max, p.cosine, p.max_abs,
                    p.max_abs_ref, state.events.size());
                for (size_t i = 0; i < state.events.size(); ++i) {
                    const auto & event = state.events[i];
                    if (event.token_ordinal == static_cast<int>(ordinal)) {
                        std::fprintf(stderr,
                            "vertical event layer=%d h=%d ids=%d,%d,%d,%d\n",
                            event.layer, event.gpu_hits,
                            event.experts[0], event.experts[1],
                            event.experts[2], event.experts[3]);
                    }
                }
                fail("vertical candidate full logits parity failed");
            }
            candidate_tokens.push_back(llama_sampler_sample(sampler, ctx, -1));
            if (candidate_tokens.back() != stock_tokens[ordinal + 1]) {
                fail("vertical candidate committed greedy continuation diverged");
            }
        }
        llama_sampler_free(sampler);
        llama_free(ctx);
    }
    llama_model_free(model);
    if (state.events.size() != stock_logits.size() *
        static_cast<size_t>(opt.vertical_layers)) {
        fail("vertical event/layer coverage incomplete");
    }
    FILE * out = std::fopen(opt.output.c_str(), "wx");
    if (!out) fail("cannot create vertical live raw output");
    std::fprintf(out,
        "{\"schema\":\"tesy.vertical_live_exactness_raw.v1\","
        "\"classification\":\"MEASURED_VERTICAL_LIVE_CORRECTNESS\","
        "\"layers_replaced\":%d,\"prompt_tokens\":%zu,"
        "\"committed_decodes\":%zu,\"stock_tokens\":[",
        opt.vertical_layers, prompt_tokens.size(), stock_logits.size());
    for (size_t i = 0; i < stock_tokens.size(); ++i) {
        if (i) std::fputc(',', out);
        std::fprintf(out, "%" PRId32, stock_tokens[i]);
    }
    std::fputs("],\"candidate_tokens\":[", out);
    for (size_t i = 0; i < candidate_tokens.size(); ++i) {
        if (i) std::fputc(',', out);
        std::fprintf(out, "%" PRId32, candidate_tokens[i]);
    }
    std::fputs("],\"logits_parity\":[", out);
    for (size_t i = 0; i < logits_parity.size(); ++i) {
        if (i) std::fputc(',', out);
        print_reinjection_parity(out, logits_parity[i]);
    }
    std::fputs("],\"events\":[", out);
    for (size_t i = 0; i < state.events.size(); ++i) {
        if (i) std::fputc(',', out);
        const auto & event = state.events[i];
        std::fprintf(out,
            "{\"token_ordinal\":%d,\"layer\":%d,\"gpu_hits\":%d,"
            "\"prefix_compute_count\":%d,\"middle_compute_count\":%d,"
            "\"suffix_compute_count\":%d,\"gpu_allocated_bytes\":%zu,"
            "\"experts\":[",
            event.token_ordinal, event.layer, event.gpu_hits,
            event.prefix_compute_count, event.middle_compute_count,
            event.suffix_compute_count, event.gpu_allocated_bytes);
        for (size_t j = 0; j < event.experts.size(); ++j) {
            if (j) std::fputc(',', out);
            std::fprintf(out, "%" PRId32, event.experts[j]);
        }
        std::fputs("],\"weights\":[", out);
        for (size_t j = 0; j < event.weights.size(); ++j) {
            if (j) std::fputc(',', out);
            std::fprintf(out, "%.9g", event.weights[j]);
        }
        std::fputs("]}", out);
    }
    std::fputs("],\"claim_boundary\":\"Instrumented correctness only; no timing or performance claim.\"}\n", out);
    if (std::fclose(out) != 0) fail("cannot close vertical live raw output");
    std::puts("VERTICAL_LIVE_CORRECTNESS_RAW_PASS");
}

void print_parity(FILE * out, const parity & value) {
    std::fprintf(
        out,
        "{\"max_abs\":%.9g,\"max_abs_ref\":%.9g,"
        "\"relative_max\":%.9g,\"cosine\":%.12f,"
        "\"status\":\"%s\"}",
        value.max_abs,
        value.max_abs_ref,
        value.relative_max,
        value.cosine,
        value.pass ? "PASS" : "FAIL");
}

template <class Fn>
stats measure(Fn && fn, int warmup, int samples, int inner) {
    for (int i = 0; i < warmup; ++i) {
        fn();
    }

    stats out;
    out.samples_ms.reserve(static_cast<size_t>(samples));
    for (int sample = 0; sample < samples; ++sample) {
        const auto start = std::chrono::steady_clock::now();
        for (int i = 0; i < inner; ++i) {
            fn();
        }
        const auto stop = std::chrono::steady_clock::now();
        const double elapsed =
            std::chrono::duration<double, std::milli>(stop - start).count();
        out.samples_ms.push_back(elapsed / static_cast<double>(inner));
    }

    std::vector<double> ordered = out.samples_ms;
    std::sort(ordered.begin(), ordered.end());
    out.min_ms = ordered.front();
    out.max_ms = ordered.back();
    out.median_ms = ordered[ordered.size() / 2];
    const size_t p95_index = std::min(
        ordered.size() - 1,
        static_cast<size_t>(
            std::ceil(0.95 * static_cast<double>(ordered.size()))) - 1);
    out.p95_ms = ordered[p95_index];
    out.mean_ms =
        std::accumulate(ordered.begin(), ordered.end(), 0.0) /
        static_cast<double>(ordered.size());

    return out;
}

stats summarize_samples(const std::vector<double> & samples_ms) {
    if (samples_ms.empty()) {
        fail("cannot summarize empty timing samples");
    }
    stats out;
    out.samples_ms = samples_ms;
    std::vector<double> ordered = samples_ms;
    std::sort(ordered.begin(), ordered.end());
    out.min_ms = ordered.front();
    out.max_ms = ordered.back();
    out.median_ms = ordered[ordered.size() / 2];
    const size_t p95_index = std::min(
        ordered.size() - 1,
        static_cast<size_t>(
            std::ceil(0.95 * static_cast<double>(ordered.size()))) - 1);
    out.p95_ms = ordered[p95_index];
    out.mean_ms =
        std::accumulate(ordered.begin(), ordered.end(), 0.0) /
        static_cast<double>(ordered.size());
    return out;
}

template <class SerialFn, class AsyncFn>
std::pair<stats, stats> measure_paired(
        SerialFn && serial_fn,
        AsyncFn && async_fn,
        int warmup,
        int samples,
        int inner) {
    for (int i = 0; i < warmup; ++i) {
        serial_fn();
        async_fn();
    }

    std::vector<double> serial_ms;
    std::vector<double> async_ms;
    serial_ms.reserve(static_cast<size_t>(samples));
    async_ms.reserve(static_cast<size_t>(samples));

    auto measure_one = [inner](auto & fn) {
        const auto start = std::chrono::steady_clock::now();
        for (int i = 0; i < inner; ++i) {
            fn();
        }
        const auto stop = std::chrono::steady_clock::now();
        const double elapsed =
            std::chrono::duration<double, std::milli>(stop - start).count();
        return elapsed / static_cast<double>(inner);
    };

    for (int sample = 0; sample < samples; ++sample) {
        if ((sample % 2) == 0) {
            serial_ms.push_back(measure_one(serial_fn));
            async_ms.push_back(measure_one(async_fn));
        } else {
            async_ms.push_back(measure_one(async_fn));
            serial_ms.push_back(measure_one(serial_fn));
        }
    }

    return {
        summarize_samples(serial_ms),
        summarize_samples(async_ms),
    };
}

std::vector<float> read_exact_f32_file(
        const std::string & path,
        size_t expected_count) {
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        fail("cannot open F32 file: " + path);
    }
    file.seekg(0, std::ios::end);
    const std::streamoff bytes = file.tellg();
    const std::streamoff expected =
        static_cast<std::streamoff>(expected_count * sizeof(float));
    if (bytes != expected) {
        fail(
            "unexpected F32 file size for " + path + ": " +
            std::to_string(bytes));
    }
    file.seekg(0, std::ios::beg);
    std::vector<float> values(expected_count);
    file.read(
        reinterpret_cast<char *>(values.data()),
        static_cast<std::streamsize>(expected));
    if (!file.good() && !file.eof()) {
        fail("failed reading F32 file: " + path);
    }
    for (float value : values) {
        if (!std::isfinite(value)) {
            fail("non-finite value in F32 file: " + path);
        }
    }
    return values;
}

std::vector<int> parse_int_csv(
        const std::string & text,
        const char * label) {
    std::vector<int> values;
    size_t start = 0;
    while (start <= text.size()) {
        const size_t end = text.find(',', start);
        const std::string item =
            text.substr(
                start,
                end == std::string::npos
                    ? std::string::npos
                    : end - start);
        if (item.empty()) {
            fail(std::string(label) + " contains empty item");
        }
        char * tail = nullptr;
        errno = 0;
        const long parsed = std::strtol(item.c_str(), &tail, 10);
        if (
            errno != 0
            || !tail
            || *tail != '\0'
            || parsed < 0
            || parsed > std::numeric_limits<int>::max()
        ) {
            fail(std::string("invalid ") + label + " item: " + item);
        }
        values.push_back(static_cast<int>(parsed));
        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }
    return values;
}

std::vector<float> parse_float_csv(
        const std::string & text,
        const char * label) {
    std::vector<float> values;
    size_t start = 0;
    while (start <= text.size()) {
        const size_t end = text.find(',', start);
        const std::string item =
            text.substr(
                start,
                end == std::string::npos
                    ? std::string::npos
                    : end - start);
        if (item.empty()) {
            fail(std::string(label) + " contains empty item");
        }
        char * tail = nullptr;
        errno = 0;
        const float parsed = std::strtof(item.c_str(), &tail);
        if (
            errno != 0
            || !tail
            || *tail != '\0'
            || !std::isfinite(parsed)
            || parsed < 0.0f
        ) {
            fail(std::string("invalid ") + label + " item: " + item);
        }
        values.push_back(parsed);
        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }
    return values;
}

std::vector<float> deterministic_input() {
    std::vector<float> input(static_cast<size_t>(k_embd));
    for (int64_t i = 0; i < k_embd; ++i) {
        input[static_cast<size_t>(i)] =
            0.5f * std::sin(static_cast<float>(i) * 0.017f);
    }
    return input;
}

std::vector<float> make_all_cpu_reference(
        const options & opt,
        ggml_backend_t cpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        const std::vector<float> & input) {
    const std::vector<int> ids = {0, 1, 2, 3};
    const tensor_bytes data = load_subset(opt.model, opt.layer, ids);
    auto set = make_tensor_set(
        data, 4, cpu_weight_buft, cpu_bias_buft);
    auto graph = make_compute_graph(*set, cpu_backend, 4, input);
    compute(cpu_backend, *graph);
    return read_output(cpu_backend, graph->output);
}

case_result run_case(
        const options & opt,
        int gpu_hits,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend,
        ggml_backend_buffer_type_t cpu_weight_buft,
        ggml_backend_buffer_type_t cpu_bias_buft,
        ggml_backend_buffer_type_t gpu_buft,
        const std::vector<float> & input,
        const std::vector<float> & reference) {
    if (gpu_hits < 0 || gpu_hits > k_top_k) {
        fail("gpu_hits outside 0..4");
    }
    const int cpu_misses = k_top_k - gpu_hits;

    std::vector<int> gpu_ids;
    std::vector<int> cpu_ids;
    for (int id = 0; id < k_top_k; ++id) {
        (id < gpu_hits ? gpu_ids : cpu_ids).push_back(id);
    }

    std::unique_ptr<tensor_set> cpu_set;
    std::unique_ptr<tensor_set> gpu_set;
    std::unique_ptr<compute_graph> cpu_graph;
    std::unique_ptr<compute_graph> gpu_graph;

    if (cpu_misses > 0) {
        const tensor_bytes cpu_data =
            load_subset(opt.model, opt.layer, cpu_ids);
        cpu_set = make_tensor_set(
            cpu_data,
            cpu_misses,
            cpu_weight_buft,
            cpu_bias_buft);
        cpu_graph = make_compute_graph(
            *cpu_set, cpu_backend, cpu_misses, input);
    }
    if (gpu_hits > 0) {
        const tensor_bytes gpu_data =
            load_subset(opt.model, opt.layer, gpu_ids);
        gpu_set = make_tensor_set(
            gpu_data, gpu_hits, gpu_buft, gpu_buft);
        gpu_graph = make_compute_graph(
            *gpu_set, gpu_backend, gpu_hits, input);
    }

    std::unique_ptr<tensor_holder> standalone_gpu_input;
    ggml_tensor * gpu_input = nullptr;
    if (gpu_graph) {
        gpu_input = gpu_graph->input;
    } else {
        standalone_gpu_input =
            make_gpu_tensor(gpu_backend, &input);
        gpu_input = standalone_gpu_input->tensor;
    }

    std::unique_ptr<tensor_holder> final_gpu;
    std::unique_ptr<sum_graph> aggregate;
    if (gpu_hits == 0) {
        final_gpu = make_gpu_tensor(gpu_backend);
    } else if (cpu_misses > 0) {
        aggregate = make_sum_graph(gpu_backend);
    }

    auto execute_serial = [&]() {
        if (cpu_graph) {
            ggml_backend_tensor_copy(
                gpu_input, cpu_graph->input);
            ggml_backend_synchronize(gpu_backend);
            ggml_backend_synchronize(cpu_backend);
            compute(cpu_backend, *cpu_graph);
        }

        if (gpu_graph) {
            compute(gpu_backend, *gpu_graph);
        }

        if (cpu_graph && !gpu_graph) {
            ggml_backend_tensor_copy(
                cpu_graph->output, final_gpu->tensor);
            ggml_backend_synchronize(cpu_backend);
            ggml_backend_synchronize(gpu_backend);
        } else if (cpu_graph && gpu_graph) {
            ggml_backend_tensor_copy(
                gpu_graph->output, aggregate->gpu_partial);
            ggml_backend_tensor_copy(
                cpu_graph->output, aggregate->cpu_partial);
            ggml_backend_synchronize(cpu_backend);
            ggml_backend_synchronize(gpu_backend);
            compute_sum(gpu_backend, *aggregate);
        }
    };

    auto execute_async_overlap = [&]() {
        if (!cpu_graph || !gpu_graph || !aggregate) {
            fail("async overlap requires a mixed CPU/GPU case");
        }

        ggml_backend_tensor_copy(
            gpu_input, cpu_graph->input);
        ggml_backend_synchronize(gpu_backend);
        ggml_backend_synchronize(cpu_backend);

        compute_async_start(gpu_backend, *gpu_graph);
        compute(cpu_backend, *cpu_graph);
        ggml_backend_synchronize(gpu_backend);

        ggml_backend_tensor_copy(
            gpu_graph->output, aggregate->gpu_partial);
        ggml_backend_tensor_copy(
            cpu_graph->output, aggregate->cpu_partial);
        ggml_backend_synchronize(cpu_backend);
        ggml_backend_synchronize(gpu_backend);
        compute_sum(gpu_backend, *aggregate);
    };

    execute_serial();
    ggml_tensor * final_tensor = nullptr;
    if (aggregate) {
        final_tensor = aggregate->output;
    } else if (final_gpu) {
        final_tensor = final_gpu->tensor;
    } else {
        final_tensor = gpu_graph->output;
    }

    const std::vector<float> observed =
        read_output(gpu_backend, final_tensor);
    const parity check =
        compare_outputs(reference, observed);
    if (!check.pass) {
        fail(
            "mixed-residency parity failed for h=" +
            std::to_string(gpu_hits));
    }

    case_result result;
    result.gpu_hits = gpu_hits;
    result.cpu_misses = cpu_misses;
    result.output_parity = check;

    if (opt.async_overlap && cpu_graph && gpu_graph) {
        execute_async_overlap();
        const std::vector<float> async_observed =
            read_output(gpu_backend, aggregate->output);
        result.async_parity =
            compare_outputs(reference, async_observed);
        if (!result.async_parity.pass) {
            fail(
                "mixed-residency async parity failed for h=" +
                std::to_string(gpu_hits));
        }

        auto paired = measure_paired(
            execute_serial,
            execute_async_overlap,
            opt.warmup,
            opt.samples,
            opt.inner);
        result.direct_wall = std::move(paired.first);
        result.async_wall = std::move(paired.second);
        result.has_async_wall = true;
    } else {
        result.direct_wall =
            measure(
                execute_serial,
                opt.warmup,
                opt.samples,
                opt.inner);
    }

    if (cpu_graph) {
        auto copy_input_d2h = [&]() {
            ggml_backend_tensor_copy(
                gpu_input, cpu_graph->input);
            ggml_backend_synchronize(gpu_backend);
            ggml_backend_synchronize(cpu_backend);
        };
        result.activation_d2h =
            measure(
                copy_input_d2h,
                opt.warmup,
                opt.samples,
                opt.inner);
        result.has_activation_d2h = true;

        copy_input_d2h();
        result.cpu_compute =
            measure(
                [&]() { compute(cpu_backend, *cpu_graph); },
                opt.warmup,
                opt.samples,
                opt.inner);
        result.has_cpu_compute = true;
    }

    if (gpu_graph) {
        result.gpu_compute =
            measure(
                [&]() { compute(gpu_backend, *gpu_graph); },
                opt.warmup,
                opt.samples,
                opt.inner);
        result.has_gpu_compute = true;
    }

    if (cpu_graph && !gpu_graph) {
        compute(cpu_backend, *cpu_graph);
        result.cpu_partial_h2d =
            measure(
                [&]() {
                    ggml_backend_tensor_copy(
                        cpu_graph->output, final_gpu->tensor);
                    ggml_backend_synchronize(cpu_backend);
                    ggml_backend_synchronize(gpu_backend);
                },
                opt.warmup,
                opt.samples,
                opt.inner);
        result.has_cpu_partial_h2d = true;
    } else if (cpu_graph && gpu_graph) {
        compute(cpu_backend, *cpu_graph);
        compute(gpu_backend, *gpu_graph);

        ggml_backend_tensor_copy(
            gpu_graph->output, aggregate->gpu_partial);
        result.cpu_partial_h2d =
            measure(
                [&]() {
                    ggml_backend_tensor_copy(
                        cpu_graph->output, aggregate->cpu_partial);
                    ggml_backend_synchronize(cpu_backend);
                    ggml_backend_synchronize(gpu_backend);
                },
                opt.warmup,
                opt.samples,
                opt.inner);
        result.has_cpu_partial_h2d = true;

        ggml_backend_tensor_copy(
            cpu_graph->output, aggregate->cpu_partial);
        ggml_backend_synchronize(cpu_backend);
        ggml_backend_synchronize(gpu_backend);

        result.gpu_aggregation =
            measure(
                [&]() {
                    ggml_backend_tensor_copy(
                        gpu_graph->output, aggregate->gpu_partial);
                    compute_sum(gpu_backend, *aggregate);
                },
                opt.warmup,
                opt.samples,
                opt.inner);
        result.has_gpu_aggregation = true;
    }

    if (cpu_graph && gpu_graph) {
        result.component_sum_median_ms =
            result.activation_d2h.median_ms +
            result.cpu_compute.median_ms +
            result.gpu_compute.median_ms +
            result.cpu_partial_h2d.median_ms +
            result.gpu_aggregation.median_ms;
        result.overlap_bound_median_ms =
            result.activation_d2h.median_ms +
            std::max(
                result.cpu_compute.median_ms,
                result.gpu_compute.median_ms) +
            result.cpu_partial_h2d.median_ms +
            result.gpu_aggregation.median_ms;
    } else if (cpu_graph) {
        result.component_sum_median_ms =
            result.activation_d2h.median_ms +
            result.cpu_compute.median_ms +
            result.cpu_partial_h2d.median_ms;
        // h=0 has no CPU/GPU compute overlap to introduce. Preserve the
        // measured direct path exactly; the decomposed sum is diagnostic only.
        result.overlap_bound_median_ms =
            result.direct_wall.median_ms;
    } else {
        result.component_sum_median_ms =
            result.gpu_compute.median_ms;
        // h=4 is already GPU-only, so the prospective overlap design cannot
        // improve it. Use the measured direct path rather than a separately
        // sampled component median.
        result.overlap_bound_median_ms =
            result.direct_wall.median_ms;
    }

    return result;
}

void print_stats(FILE * out, const stats & value) {
    std::fprintf(
        out,
        "{\"median_ms\":%.9f,\"p95_ms\":%.9f,\"min_ms\":%.9f,"
        "\"max_ms\":%.9f,\"mean_ms\":%.9f,\"samples_ms\":[",
        value.median_ms,
        value.p95_ms,
        value.min_ms,
        value.max_ms,
        value.mean_ms);
    for (size_t i = 0; i < value.samples_ms.size(); ++i) {
        if (i != 0) {
            std::fputc(',', out);
        }
        std::fprintf(out, "%.9f", value.samples_ms[i]);
    }
    std::fputs("]}", out);
}

void print_optional_stats(
        FILE * out,
        bool present,
        const stats & value) {
    if (!present) {
        std::fputs("null", out);
        return;
    }
    print_stats(out, value);
}

void print_case(FILE * out, const case_result & row) {
    std::fprintf(
        out,
        "{\"gpu_hits\":%d,\"cpu_misses\":%d,"
        "\"source_expert_ids\":[0,1,2,3],"
        "\"global_mix_weight\":0.25,"
        "\"direct_wall\":",
        row.gpu_hits,
        row.cpu_misses);
    print_stats(out, row.direct_wall);
    std::fputs(",\"async_wall\":", out);
    print_optional_stats(out, row.has_async_wall, row.async_wall);
    if (row.has_async_wall) {
        std::fprintf(
            out,
            ",\"async_parity\":{\"max_abs\":%.9g,"
            "\"max_abs_ref\":%.9g,\"relative_max\":%.9g,"
            "\"cosine\":%.12f,\"status\":\"%s\"}",
            row.async_parity.max_abs,
            row.async_parity.max_abs_ref,
            row.async_parity.relative_max,
            row.async_parity.cosine,
            row.async_parity.pass ? "PASS" : "FAIL");
    } else {
        std::fputs(",\"async_parity\":null", out);
    }

    std::fputs(",\"components\":{\"activation_d2h\":", out);
    print_optional_stats(
        out, row.has_activation_d2h, row.activation_d2h);
    std::fputs(",\"cpu_compute\":", out);
    print_optional_stats(
        out, row.has_cpu_compute, row.cpu_compute);
    std::fputs(",\"gpu_compute\":", out);
    print_optional_stats(
        out, row.has_gpu_compute, row.gpu_compute);
    std::fputs(",\"cpu_partial_h2d\":", out);
    print_optional_stats(
        out, row.has_cpu_partial_h2d, row.cpu_partial_h2d);
    std::fputs(",\"gpu_aggregation\":", out);
    print_optional_stats(
        out, row.has_gpu_aggregation, row.gpu_aggregation);
    std::fprintf(
        out,
        "},\"component_sum_median_ms\":%.9f,"
        "\"post_d2h_overlap_bound_median_ms\":%.9f,"
        "\"overlap_bound_speedup_vs_direct\":%.9f",
        row.component_sum_median_ms,
        row.overlap_bound_median_ms,
        row.direct_wall.median_ms / row.overlap_bound_median_ms);

    std::fprintf(
        out,
        ",\"parity\":{\"max_abs\":%.9g,\"max_abs_ref\":%.9g,"
        "\"relative_max\":%.9g,\"cosine\":%.12f,\"status\":\"%s\"}}",
        row.output_parity.max_abs,
        row.output_parity.max_abs_ref,
        row.output_parity.relative_max,
        row.output_parity.cosine,
        row.output_parity.pass ? "PASS" : "FAIL");
}

void print_live_timing_samples(
        FILE * out,
        const live_timing_samples & samples) {
    std::fputs("{\"activation_ready_ms\":[", out);
    for (size_t i = 0; i < samples.activation_ms.size(); ++i) {
        if (i != 0) {
            std::fputc(',', out);
        }
        std::fprintf(out, "%.9f", samples.activation_ms[i]);
    }
    std::fputs("],\"route_ready_ms\":[", out);
    for (size_t i = 0; i < samples.route_ms.size(); ++i) {
        if (i != 0) {
            std::fputc(',', out);
        }
        std::fprintf(out, "%.9f", samples.route_ms[i]);
    }
    std::fputs("]}", out);
}

void print_live_timing_exactness(
        FILE * out,
        const live_timing_exactness_snapshot & value) {
    std::fprintf(
        out,
        "{\"stock_decode_return_code\":%d,"
        "\"handoff_decode_return_code\":%d,"
        "\"stock_rollback\":%s,"
        "\"handoff_rollback\":%s,"
        "\"activation_bitwise_equal\":%s,"
        "\"activation_parity\":",
        value.stock_decode_return_code,
        value.handoff_decode_return_code,
        value.stock_rollback ? "true" : "false",
        value.handoff_rollback ? "true" : "false",
        value.activation_bitwise_equal ? "true" : "false");
    print_parity(out, value.activation_parity);
    std::fputs(",\"activation_vs_reference\":", out);
    print_parity(out, value.activation_vs_reference);
    std::fputs(",\"stock_output_vs_reference\":", out);
    print_parity(out, value.stock_output_vs_reference);
    std::fputs(",\"serial_vs_stock\":", out);
    print_parity(out, value.serial_vs_stock);
    std::fputs(",\"async_vs_stock\":", out);
    print_parity(out, value.async_vs_stock);
    std::fputs(",\"async_vs_serial\":", out);
    print_parity(out, value.async_vs_serial);
    std::fputc('}', out);
}

}  // namespace

int main(int argc, char ** argv) {
    const options opt = parse_options(argc, argv);

    ggml_backend_load_all();
    ggml_backend_dev_t cpu_dev =
        ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_CPU);
    ggml_backend_dev_t gpu_dev =
        ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_GPU);
    if (!cpu_dev || !gpu_dev) {
        fail("CPU and GPU backends are required");
    }

    backend_handle cpu;
    backend_handle gpu;
    cpu.backend = ggml_backend_dev_init(cpu_dev, nullptr);
    gpu.backend = ggml_backend_dev_init(gpu_dev, nullptr);
    if (!cpu.backend || !gpu.backend) {
        fail("failed to initialize CPU/GPU backend");
    }
    ggml_backend_cpu_set_n_threads(cpu.backend, opt.threads);

    ggml_backend_dev_props cpu_props = {};
    ggml_backend_dev_props gpu_props = {};
    ggml_backend_dev_get_props(cpu_dev, &cpu_props);
    ggml_backend_dev_get_props(gpu_dev, &gpu_props);
    if (
        (opt.async_overlap || opt.live_handoff_timing)
        && !gpu_props.caps.async
    ) {
        fail("GPU backend does not advertise async capability");
    }

    const ggml_backend_buffer_type_t cpu_bias_buft =
        ggml_backend_dev_buffer_type(cpu_dev);
    const ggml_backend_buffer_type_t cpu_weight_buft =
        select_cpu_compute_weight_buft(cpu_dev);
    const ggml_backend_buffer_type_t gpu_buft =
        ggml_backend_dev_buffer_type(gpu_dev);
    if (!cpu_bias_buft || !cpu_weight_buft || !gpu_buft) {
        fail("missing required backend buffer type");
    }

    if (opt.live_reinjection_exactness) {
        run_live_reinjection_exactness(
            opt, cpu.backend, gpu.backend,
            cpu_weight_buft, cpu_bias_buft, gpu_buft);
        return 0;
    }
    if (opt.split_graph_skip_exactness) {
        run_split_graph_skip_exactness(
            opt, cpu.backend, gpu.backend,
            cpu_weight_buft, cpu_bias_buft, gpu_buft);
        return 0;
    }
    if (opt.vertical_live_exactness) {
        run_vertical_live_exactness(opt, cpu.backend, gpu.backend, gpu_buft);
        return 0;
    }

    const std::string cpu_weight_buft_name =
        ggml_backend_buft_name(cpu_weight_buft);
    const std::string cpu_bias_buft_name =
        ggml_backend_buft_name(cpu_bias_buft);

    if (opt.live_handoff_timing) {
        const live_handoff_timing_result result =
            run_live_handoff_timing(
                opt,
                cpu.backend,
                gpu.backend,
                cpu_weight_buft,
                cpu_bias_buft,
                gpu_buft);

        FILE * out = std::fopen(opt.output.c_str(), "wx");
        if (!out) {
            fail(
                "refusing or unable to create output: " +
                opt.output);
        }

        std::fprintf(
            out,
            "{\"schema\":\"tesy.live_moe_handoff_timing_raw.v1\","
            "\"classification\":"
            "\"MEASURED_LIVE_MOE_HANDOFF_TIMING_RAW\","
            "\"layer\":0,\"ngl\":0,"
            "\"gpu_hits\":%d,\"cpu_misses\":%d,"
            "\"threads\":%d,"
            "\"warmup_triplets\":%d,"
            "\"sample_triplets\":%d,"
            "\"inner\":%d,"
            "\"resident_experts\":true,"
            "\"provenance_gate\":"
            "\"FILE_EXISTENCE_BEFORE_WARMUP\","
            "\"input_semantics\":"
            "\"HOST_CAPTURE_TO_CPU_AND_GPU_COMPACT_INPUTS\","
            "\"decode_input_token\":%" PRId32 ","
            "\"activation_tensor\":\"attn_post_norm-0\","
            "\"topk_tensor\":\"ffn_moe_topk-0\","
            "\"routing_weight_tensor\":"
            "\"ffn_moe_weights_softmax-0\","
            "\"stock_output_tensor\":\"ffn_moe_out-0\","
            "\"selected_experts\":[",
            result.gpu_hits,
            result.cpu_misses,
            opt.threads,
            opt.warmup,
            opt.samples,
            opt.inner,
            result.decode_input_token);

        for (size_t i = 0; i < result.selected_experts.size(); ++i) {
            if (i != 0) {
                std::fputc(',', out);
            }
            std::fprintf(out, "%d", result.selected_experts[i]);
        }

        std::fputs("],\"routing_weights\":[", out);
        for (size_t i = 0; i < result.routing_weights.size(); ++i) {
            if (i != 0) {
                std::fputc(',', out);
            }
            std::fprintf(out, "%.9g", result.routing_weights[i]);
        }

        std::fprintf(
            out,
            "],\"completed_trials\":{"
            "\"stock\":%d,\"serial\":%d,\"async\":%d},"
            "\"successful_timing_trial_rollbacks\":%d,"
            "\"triplet_order_cycle\":["
            "[\"stock\",\"serial\",\"async\"],"
            "[\"stock\",\"async\",\"serial\"],"
            "[\"serial\",\"stock\",\"async\"],"
            "[\"serial\",\"async\",\"stock\"],"
            "[\"async\",\"stock\",\"serial\"],"
            "[\"async\",\"serial\",\"stock\"]],"
            "\"measured_order_full_cycles\":13,"
            "\"measured_order_tail_indices\":[0,3,4],"
            "\"measured_ordinal_counts\":{"
            "\"stock\":[27,27,27],"
            "\"serial\":[27,27,27],"
            "\"async\":[27,27,27]},"
            "\"pre_exactness\":",
            result.completed_stock_trials,
            result.completed_serial_trials,
            result.completed_async_trials,
            result.successful_timing_trial_rollbacks);

        print_live_timing_exactness(
            out,
            result.pre_exactness);
        std::fputs(",\"post_exactness\":", out);
        print_live_timing_exactness(
            out,
            result.post_exactness);

        std::fputs(",\"modes\":{\"stock\":", out);
        print_live_timing_samples(out, result.stock);
        std::fputs(",\"serial\":", out);
        print_live_timing_samples(out, result.serial);
        std::fputs(",\"async\":", out);
        print_live_timing_samples(out, result.async);

        std::fputs(
            "},\"parity_thresholds\":{"
            "\"relative_max_max\":0.005,"
            "\"cosine_min\":0.9999},"
            "\"claim_boundary\":"
            "\"Resident-expert steady-state timing for one repeated live "
            "stock layer-0 route. Stock ends at callback-observed "
            "ffn_moe_out-0 and is therefore an instrumented comparator. "
            "Serial and async candidates include stock scheduler early-stop "
            "return, "
            "host activation updates into resident CPU/GPU compact inputs, "
            "Tesy expert execution, CPU-partial transfer and final GPU "
            "aggregation. Expert loading, cache misses, weight transfer, "
            "output reinjection, committed-token continuation, prefetch and "
            "physical traffic are excluded. Raw samples are authoritative; "
            "statistics and decision are recomputed independently.\"}\n",
            out);

        if (std::fclose(out) != 0) {
            fail("failed closing live handoff timing output");
        }

        std::printf("PASS_LIVE_MOE_HANDOFF_TIMING_RAW\n");
        std::printf("gpu_hits: %d\n", result.gpu_hits);
        std::printf("output: %s\n", opt.output.c_str());
        return 0;
    }

    if (opt.live_handoff_exactness) {
        const live_handoff_result result =
            run_live_handoff_exactness(
                opt,
                cpu.backend,
                gpu.backend,
                cpu_weight_buft,
                cpu_bias_buft,
                gpu_buft);

        FILE * out = std::fopen(opt.output.c_str(), "wx");
        if (!out) {
            fail(
                "refusing or unable to create output: " +
                opt.output);
        }

        std::fprintf(
            out,
            "{\"schema\":\"tesy.live_moe_handoff_exactness.v1\","
            "\"classification\":"
            "\"MEASURED_LIVE_MOE_HANDOFF_EXACTNESS\","
            "\"layer\":0,\"ngl\":0,"
            "\"decode_input_token\":%" PRId32 ","
            "\"stock_decode_return_code\":%d,"
            "\"handoff_decode_return_code\":%d,"
            "\"stock_rollback\":%s,"
            "\"handoff_rollback\":%s,"
            "\"activation_tensor\":\"attn_post_norm-0\","
            "\"topk_tensor\":\"ffn_moe_topk-0\","
            "\"routing_weight_tensor\":"
            "\"ffn_moe_weights_softmax-0\","
            "\"stock_output_tensor\":\"ffn_moe_out-0\","
            "\"activation_bitwise_equal\":%s,"
            "\"activation_parity\":",
            result.decode_input_token,
            result.stock_decode_return_code,
            result.handoff_decode_return_code,
            result.stock_rollback ? "true" : "false",
            result.handoff_rollback ? "true" : "false",
            result.activation_bitwise_equal ? "true" : "false");

        print_parity(out, result.activation_parity);

        std::fputs(",\"selected_experts\":[", out);
        for (size_t i = 0; i < result.selected_experts.size(); ++i) {
            if (i != 0) {
                std::fputc(',', out);
            }
            std::fprintf(out, "%d", result.selected_experts[i]);
        }

        std::fputs("],\"routing_weights\":[", out);
        for (size_t i = 0; i < result.routing_weights.size(); ++i) {
            if (i != 0) {
                std::fputc(',', out);
            }
            std::fprintf(out, "%.9g", result.routing_weights[i]);
        }

        std::fputs("],\"cases\":[", out);
        for (size_t i = 0; i < result.cases.size(); ++i) {
            if (i != 0) {
                std::fputc(',', out);
            }
            const routed_exactness_result & row =
                result.cases[i];
            std::fprintf(
                out,
                "{\"gpu_hits\":%d,\"cpu_misses\":%d,"
                "\"serial_vs_stock\":",
                row.gpu_hits,
                row.cpu_misses);
            print_parity(out, row.serial_vs_stock);
            std::fputs(",\"async_vs_stock\":", out);
            print_parity(out, row.async_vs_stock);
            std::fputs(",\"async_vs_serial\":", out);
            print_parity(out, row.async_vs_serial);
            std::fputc('}', out);
        }

        std::fputs(
            "],\"parity_thresholds\":{"
            "\"relative_max_max\":0.005,"
            "\"cosine_min\":0.9999},"
            "\"decision\":\"LIVE_MOE_HANDOFF_EXACTNESS_GO\","
            "\"claim_boundary\":"
            "\"Correctness-only in-process handoff for one repeated stock "
            "layer-0 route. The stock-reference arm supplies authoritative "
            "activation, top-k, final routing weights and ffn_moe_out. "
            "After explicit KV rollback, the handoff arm early-stops at the "
            "same final routing weights and Tesy executes controlled h=2/h=3 "
            "serial and async compact FFNs using that live activation. "
            "No timing, output reinjection, committed-token continuation, "
            "cache policy, prefetch or physical traffic claim follows.\"}\n",
            out);

        if (std::fclose(out) != 0) {
            fail("failed closing live handoff exactness output");
        }

        std::printf("PASS_LIVE_MOE_HANDOFF_EXACTNESS\n");
        std::printf("decision: LIVE_MOE_HANDOFF_EXACTNESS_GO\n");
        std::printf("output: %s\n", opt.output.c_str());
        return 0;
    }

    if (opt.routed_exactness) {
        const std::vector<float> input =
            read_exact_f32_file(
                opt.routed_input_f32,
                static_cast<size_t>(k_embd));
        const std::vector<float> stock_reference =
            read_exact_f32_file(
                opt.routed_reference_f32,
                static_cast<size_t>(k_embd));
        const std::vector<int> selected_experts =
            parse_int_csv(
                opt.routed_experts_csv,
                "routed experts");
        const std::vector<float> routing_weights =
            parse_float_csv(
                opt.routed_weights_csv,
                "routed weights");

        const routed_exactness_result result =
            run_routed_exactness(
                opt,
                cpu.backend,
                gpu.backend,
                cpu_weight_buft,
                cpu_bias_buft,
                gpu_buft,
                input,
                stock_reference,
                selected_experts,
                routing_weights);

        FILE * out = std::fopen(opt.output.c_str(), "wx");
        if (!out) {
            fail(
                "refusing or unable to create output: " +
                opt.output);
        }

        std::fprintf(
            out,
            "{\"schema\":\"tesy.routed_layer_exactness_raw.v1\","
            "\"classification\":"
            "\"MEASURED_ROUTED_LAYER_REPLAY_EXACTNESS\","
            "\"layer\":0,\"gpu_hits\":%d,\"cpu_misses\":%d,"
            "\"controlled_partition\":"
            "\"TOPK_SLOT_PREFIX_GPU_REMAINDER_CPU\","
            "\"cpu_weight_buffer_type\":\"%s\","
            "\"cpu_bias_buffer_type\":\"%s\","
            "\"selected_experts\":[",
            result.gpu_hits,
            result.cpu_misses,
            cpu_weight_buft_name.c_str(),
            cpu_bias_buft_name.c_str());

        for (size_t i = 0; i < selected_experts.size(); ++i) {
            if (i != 0) {
                std::fputc(',', out);
            }
            std::fprintf(out, "%d", selected_experts[i]);
        }

        std::fputs("],\"routing_weights\":[", out);
        for (size_t i = 0; i < routing_weights.size(); ++i) {
            if (i != 0) {
                std::fputc(',', out);
            }
            std::fprintf(out, "%.9g", routing_weights[i]);
        }

        std::fputs("],\"serial_vs_stock\":", out);
        print_parity(out, result.serial_vs_stock);
        std::fputs(",\"async_vs_stock\":", out);
        print_parity(out, result.async_vs_stock);
        std::fputs(",\"async_vs_serial\":", out);
        print_parity(out, result.async_vs_serial);
        std::fputs(
            ",\"parity_thresholds\":{"
            "\"relative_max_max\":0.005,"
            "\"cosine_min\":0.9999},"
            "\"claim_boundary\":"
            "\"Correctness-only replay of one stock llama.cpp layer-0 "
            "decode MoE event using the captured exact activation, router "
            "top-k and final routing weights. GPU/CPU residence is a "
            "controlled slot-prefix partition with no dynamic placement "
            "policy. No timing, full-model performance, or physical "
            "traffic claim follows.\"}\n",
            out);

        if (std::fclose(out) != 0) {
            fail("failed closing routed exactness output");
        }

        std::printf("PASS_ROUTED_LAYER_EXACTNESS_RAW\n");
        std::printf("output: %s\n", opt.output.c_str());
        return 0;
    }

    const std::vector<float> input = deterministic_input();
    const std::vector<float> reference =
        make_all_cpu_reference(
            opt,
            cpu.backend,
            cpu_weight_buft,
            cpu_bias_buft,
            input);

    const std::array<int, 5> measurement_order = {0, 4, 1, 3, 2};
    std::vector<case_result> rows;
    for (int h : measurement_order) {
        rows.push_back(
            run_case(
                opt,
                h,
                cpu.backend,
                gpu.backend,
                cpu_weight_buft,
                cpu_bias_buft,
                gpu_buft,
                input,
                reference));
    }
    std::sort(
        rows.begin(),
        rows.end(),
        [](const case_result & a, const case_result & b) {
            return a.gpu_hits < b.gpu_hits;
        });

    FILE * out = std::fopen(opt.output.c_str(), "wx");
    if (!out) {
        fail("refusing or unable to create output: " + opt.output);
    }

    std::fprintf(
        out,
        opt.async_overlap
            ? "{\"schema\":\"tesy.mixed_residency_async_raw.v1\","
              "\"classification\":\"MEASURED_MIXED_RESIDENCY_ASYNC_DIAGNOSTIC\","
            : "{\"schema\":\"tesy.mixed_residency_overlap_bound_raw.v1\","
              "\"classification\":\"MEASURED_MIXED_RESIDENCY_COMPONENT_DIAGNOSTIC\",");
    if (opt.async_overlap) {
        std::fputs(
            "\"async_schedule\":"
            "\"post_d2h_gpu_enqueue_cpu_sync_gpu_wait\","
            "\"paired_sample_order\":"
            "\"even_serial_async_odd_async_serial\",",
            out);
    }
    std::fprintf(
        out,
        "\"layer\":%d,\"threads\":%d,\"warmup\":%d,\"samples\":%d,"
        "\"inner\":%d,\"n_embd\":%" PRId64 ",\"top_k\":4,"
        "\"expert_count_model\":%" PRId64 ","
        "\"encoded_bytes_per_expert\":%zu,"
        "\"weight_type\":\"mxfp4\",\"bias_type\":\"f32\","
        "\"weight_shape\":[2880,2880,32],\"bias_shape\":[2880,32],"
        "\"cpu_weight_buffer_type\":\"%s\","
        "\"cpu_bias_buffer_type\":\"%s\","
        "\"gpu_async_capable\":%s,\"cpu_async_capable\":%s,"
        "\"expert_ids\":[0,1,2,3],\"mix_weights\":[0.25,0.25,0.25,0.25],"
        "\"measurement_order\":[0,4,1,3,2],"
        "\"cases\":[",
        opt.layer,
        opt.threads,
        opt.warmup,
        opt.samples,
        opt.inner,
        k_embd,
        k_expert_count,
        k_encoded_bytes_per_expert,
        cpu_weight_buft_name.c_str(),
        cpu_bias_buft_name.c_str(),
        gpu_props.caps.async ? "true" : "false",
        cpu_props.caps.async ? "true" : "false");
    for (size_t i = 0; i < rows.size(); ++i) {
        if (i != 0) {
            std::fputc(',', out);
        }
        print_case(out, rows[i]);
    }
    if (opt.async_overlap) {
        std::fputs(
            "],\"claim_boundary\":"
            "\"Same-campaign serial baseline plus measured post-D2H CPU/GPU "
            "compute overlap for mixed h=1..3 cases. The candidate completes D2H, "
            "enqueues the GPU graph asynchronously, executes the authoritative CPU "
            "subset synchronously, synchronizes the GPU, copies the CPU partial to "
            "GPU, and aggregates. h=0/h=4 remain serial anchors. Weights are already "
            "resident; no expert-weight transfer, routing, prefetch, cache management, "
            "full-model timing, or physical PCIe/DRAM/NVMe traffic is measured.\"}\n",
            out);
    } else {
        std::fputs(
            "],\"claim_boundary\":"
            "\"Direct serial isolated top-4 mixed CPU/GPU expert FFN timings plus "
            "separately measured component completion times. The overlap bound assumes "
            "the GPU and CPU subset computes can overlap only after the input D2H copy "
            "has completed; D2H, CPU-partial H2D and aggregation remain serialized. "
            "Weights are already resident in their assigned backend buffers; "
            "no expert-weight transfer, routing, prefetch, cache management or full-model timing "
            "is measured. CPU misses execute on the CPU backend using its first "
            "compatible extra/repack MXFP4 weight buffer for subset sizes 1..4, "
            "with CPU-default fallback; F32 biases use the CPU default buffer. "
            "Final output is materialized on GPU. Uniform 0.25 expert "
            "mixture weights are synthetic and affect correctness scaling, not routing.\"}\n",
            out);
    }

    if (std::fclose(out) != 0) {
        fail("failed closing output");
    }

    std::printf(
        opt.async_overlap
            ? "PASS_MIXED_RESIDENCY_ASYNC_RAW\n"
            : "PASS_MIXED_RESIDENCY_OVERLAP_BOUND_RAW\n");
    std::printf("output: %s\n", opt.output.c_str());
    return 0;
}
