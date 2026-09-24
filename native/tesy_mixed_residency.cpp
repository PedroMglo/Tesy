#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"
#include "gguf.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cinttypes>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <memory>
#include <numeric>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr int64_t k_embd = 2880;
constexpr int64_t k_expert_count = 32;
constexpr int k_top_k = 4;
constexpr size_t k_encoded_bytes_per_expert = 13253760;
constexpr float k_swiglu_alpha = 1.702f;
constexpr float k_swiglu_limit = 7.0f;
constexpr float k_mix_weight = 0.25f;

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
    std::string routed_input_f32;
    std::string routed_reference_f32;
    std::string routed_experts_csv;
    std::string routed_weights_csv;
    int routed_gpu_hits = -1;
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
        "--routed-experts CSV --routed-weights CSV --routed-gpu-hits N]\n",
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
        const std::vector<float> & input_values) {
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

    std::vector<float> mix(static_cast<size_t>(count), k_mix_weight);
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
        ggml_backend_t gpu_backend,
        ggml_tensor * gpu_partial) {
    auto result = std::make_unique<sum_graph>();
    result->storage.ctx = make_context(1024u * 1024u);
    ggml_context * ctx = result->storage.ctx;
    result->cpu_partial =
        ggml_new_tensor_2d(ctx, GGML_TYPE_F32, k_embd, 1);
    result->output =
        ggml_add(ctx, gpu_partial, result->cpu_partial);
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
        aggregate = make_sum_graph(
            gpu_backend, gpu_graph->output);
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
                [&]() { compute_sum(gpu_backend, *aggregate); },
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
    if (opt.async_overlap && !gpu_props.caps.async) {
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

    const std::string cpu_weight_buft_name =
        ggml_backend_buft_name(cpu_weight_buft);
    const std::string cpu_bias_buft_name =
        ggml_backend_buft_name(cpu_bias_buft);

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
