#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"
#include "gguf.h"
#include "llama.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cinttypes>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr int64_t k_embd = 2880;
constexpr int64_t k_expert_count = 32;
constexpr size_t k_encoded_bytes_per_expert = 13253760;
constexpr float k_swiglu_alpha = 1.702f;
constexpr float k_swiglu_limit = 7.0f;

struct options {
    std::string model;
    std::string output;
    int layer = 0;
    int threads = 12;
    int warmup = 3;
    int samples = 21;
    int compute_inner = 5;
    int transfer_inner = 4;
    int activation_inner = 100;
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

    backend_handle() = default;
    backend_handle(const backend_handle &) = delete;
    backend_handle & operator=(const backend_handle &) = delete;

    ~backend_handle() {
        if (backend) {
            ggml_backend_free(backend);
        }
    }
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
    std::string weight_buffer_type;
    std::string bias_buffer_type;
    size_t weight_buffer_bytes = 0;
    size_t bias_buffer_bytes = 0;
};

struct compute_graph {
    context_buffer storage;
    ggml_cgraph * graph = nullptr;
    ggml_tensor * input = nullptr;
    ggml_tensor * ids = nullptr;
    ggml_tensor * mix = nullptr;
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

struct k_result {
    int k = 0;
    size_t requested_weight_bytes = 0;
    size_t activation_input_bytes = 0;
    size_t activation_output_bytes = 0;
    std::string cpu_weight_buffer_type;
    size_t cpu_weight_buffer_bytes = 0;
    stats cpu_compute;
    stats gpu_compute;
    stats activation_d2h;
    stats activation_h2d;
    stats weight_h2d_pageable;
    bool pinned_available = false;
    stats weight_h2d_pinned;
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
        "[--layer N] [--threads N] [--samples N] [--warmup N] "
        "[--compute-inner N] [--transfer-inner N] [--activation-inner N]\n",
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
        } else if (arg == "--compute-inner") {
            out.compute_inner = parse_positive(value("--compute-inner"), "--compute-inner");
        } else if (arg == "--transfer-inner") {
            out.transfer_inner = parse_positive(value("--transfer-inner"), "--transfer-inner");
        } else if (arg == "--activation-inner") {
            out.activation_inner = parse_positive(value("--activation-inner"), "--activation-inner");
        } else if (arg == "-h" || arg == "--help") {
            usage(argv[0], 0);
        } else {
            fail("unknown argument: " + arg);
        }
    }
    if (out.model.empty() || out.output.empty()) {
        usage(argv[0], 2);
    }
    return out;
}

ggml_context * make_context(size_t bytes = 8u * 1024u * 1024u) {
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

void json_string(FILE * out, const std::string & value) {
    std::fputc('"', out);
    for (unsigned char c : value) {
        switch (c) {
            case '"':  std::fputs("\\\"", out); break;
            case '\\': std::fputs("\\\\", out); break;
            case '\b': std::fputs("\\b", out); break;
            case '\f': std::fputs("\\f", out); break;
            case '\n': std::fputs("\\n", out); break;
            case '\r': std::fputs("\\r", out); break;
            case '\t': std::fputs("\\t", out); break;
            default:
                if (c < 0x20) {
                    std::fprintf(out, "\\u%04x", static_cast<unsigned>(c));
                } else {
                    std::fputc(c, out);
                }
        }
    }
    std::fputc('"', out);
}

struct tensor_spec {
    std::string name;
    ggml_type type = GGML_TYPE_COUNT;
    std::vector<int64_t> shape;
    size_t n_bytes = 0;
    size_t absolute_offset = 0;
    size_t per_expert_bytes = 0;
};

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
    const size_t per_expert_bytes =
        n_bytes / static_cast<size_t>(k_expert_count);
    if (
        tensor->nb[n_dims - 1] != per_expert_bytes
        || tensor->ne[n_dims - 1] != k_expert_count
    ) {
        fail("expert slices are not contiguous on the final GGUF dimension for " + name);
    }
    const size_t base = gguf_get_data_offset(gguf);
    const size_t relative = gguf_get_tensor_offset(gguf, id);
    if (relative > std::numeric_limits<size_t>::max() - base) {
        fail("tensor offset overflow for " + name);
    }
    return tensor_spec{
        name,
        type,
        expected_shape,
        n_bytes,
        base + relative,
        per_expert_bytes,
    };
}

std::vector<uint8_t> read_expert_slices(
        std::ifstream & file,
        const tensor_spec & spec,
        int k) {
    std::vector<uint8_t> out(spec.per_expert_bytes * static_cast<size_t>(k));
    for (int expert = 0; expert < k; ++expert) {
        const size_t offset =
            spec.absolute_offset + spec.per_expert_bytes * static_cast<size_t>(expert);
        if (offset > static_cast<size_t>(std::numeric_limits<std::streamoff>::max())) {
            fail("file offset does not fit streamoff for " + spec.name);
        }
        file.clear();
        file.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
        if (!file.good()) {
            fail("seek failed for " + spec.name);
        }
        file.read(
            reinterpret_cast<char *>(
                out.data() + spec.per_expert_bytes * static_cast<size_t>(expert)),
            static_cast<std::streamsize>(spec.per_expert_bytes));
        if (file.gcount() != static_cast<std::streamsize>(spec.per_expert_bytes)) {
            fail("short read for " + spec.name);
        }
    }
    return out;
}

tensor_bytes load_tensor_bytes(const std::string & model, int layer, int k) {
    if (k != 1 && k != 4) {
        fail("only k=1 and k=4 are admitted");
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
        gate_w.per_expert_bytes + up_w.per_expert_bytes + down_w.per_expert_bytes +
        gate_b.per_expert_bytes + up_b.per_expert_bytes + down_b.per_expert_bytes;
    if (one_expert != k_encoded_bytes_per_expert) {
        ggml_free(meta);
        gguf_free(gguf);
        fail(
            "encoded expert bytes mismatch: " + std::to_string(one_expert) +
            " != " + std::to_string(k_encoded_bytes_per_expert));
    }

    std::ifstream file(model, std::ios::binary);
    if (!file) {
        ggml_free(meta);
        gguf_free(gguf);
        fail("cannot open model for expert slice reads");
    }

    tensor_bytes result;
    result.gate_w = read_expert_slices(file, gate_w, k);
    result.up_w = read_expert_slices(file, up_w, k);
    result.down_w = read_expert_slices(file, down_w, k);
    result.gate_b = read_expert_slices(file, gate_b, k);
    result.up_b = read_expert_slices(file, up_b, k);
    result.down_b = read_expert_slices(file, down_b, k);

    ggml_free(meta);
    gguf_free(gguf);

    const size_t expected = k_encoded_bytes_per_expert * static_cast<size_t>(k);
    if (result.total() != expected) {
        fail("compact expert payload size mismatch");
    }
    return result;
}

bool supports_weight_buft(
        ggml_backend_dev_t dev,
        ggml_backend_buffer_type_t buft,
        int k) {
    ggml_context * ctx = make_context(1024u * 1024u);
    ggml_tensor * w =
        ggml_new_tensor_3d(ctx, GGML_TYPE_MXFP4, k_embd, k_embd, k);
    ggml_tensor * input =
        ggml_new_tensor_3d(ctx, GGML_TYPE_F32, k_embd, 1, 1);
    ggml_tensor * ids =
        ggml_new_tensor_2d(ctx, GGML_TYPE_I32, k, 1);

    ggml_backend_buffer_t dummy = ggml_backend_buft_alloc_buffer(buft, 0);
    if (!dummy) {
        ggml_free(ctx);
        return false;
    }
    w->buffer = dummy;
    ggml_tensor * op = ggml_mul_mat_id(ctx, w, input, ids);
    const bool supported = ggml_backend_dev_supports_op(dev, op);
    w->buffer = nullptr;
    ggml_backend_buffer_free(dummy);
    ggml_free(ctx);
    return supported;
}

ggml_backend_buffer_type_t select_cpu_weight_buft(
        ggml_backend_dev_t cpu_dev,
        int k) {
    std::vector<ggml_backend_buffer_type_t> candidates;
    auto * reg = ggml_backend_dev_backend_reg(cpu_dev);
    auto fn = reinterpret_cast<ggml_backend_dev_get_extra_bufts_t>(
        ggml_backend_reg_get_proc_address(reg, "ggml_backend_dev_get_extra_bufts"));
    if (fn) {
        ggml_backend_buffer_type_t * extra = fn(cpu_dev);
        while (extra && *extra) {
            candidates.push_back(*extra);
            ++extra;
        }
    }
    candidates.push_back(ggml_backend_dev_buffer_type(cpu_dev));

    for (auto buft : candidates) {
        if (!buft || !ggml_backend_buft_is_host(buft)) {
            continue;
        }
        if (supports_weight_buft(cpu_dev, buft, k)) {
            return buft;
        }
    }
    fail("no CPU buffer type supports MXFP4 MUL_MAT_ID");
}

std::unique_ptr<tensor_set> make_tensor_set(
        const tensor_bytes & data,
        int k,
        ggml_backend_buffer_type_t weight_buft,
        ggml_backend_buffer_type_t bias_buft) {
    auto result = std::make_unique<tensor_set>();
    result->weights.ctx = make_context();
    result->biases.ctx = make_context();

    result->gate_w = ggml_new_tensor_3d(
        result->weights.ctx, GGML_TYPE_MXFP4, k_embd, k_embd, k);
    result->up_w = ggml_new_tensor_3d(
        result->weights.ctx, GGML_TYPE_MXFP4, k_embd, k_embd, k);
    result->down_w = ggml_new_tensor_3d(
        result->weights.ctx, GGML_TYPE_MXFP4, k_embd, k_embd, k);

    result->gate_b =
        ggml_new_tensor_2d(result->biases.ctx, GGML_TYPE_F32, k_embd, k);
    result->up_b =
        ggml_new_tensor_2d(result->biases.ctx, GGML_TYPE_F32, k_embd, k);
    result->down_b =
        ggml_new_tensor_2d(result->biases.ctx, GGML_TYPE_F32, k_embd, k);

    result->weights.buffer =
        ggml_backend_alloc_ctx_tensors_from_buft(result->weights.ctx, weight_buft);
    result->biases.buffer =
        ggml_backend_alloc_ctx_tensors_from_buft(result->biases.ctx, bias_buft);
    if (!result->weights.buffer || !result->biases.buffer) {
        fail("failed to allocate static expert tensors");
    }
    ggml_backend_buffer_set_usage(
        result->weights.buffer, GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
    ggml_backend_buffer_set_usage(
        result->biases.buffer, GGML_BACKEND_BUFFER_USAGE_WEIGHTS);

    result->weight_buffer_type = ggml_backend_buft_name(weight_buft);
    result->bias_buffer_type = ggml_backend_buft_name(bias_buft);
    result->weight_buffer_bytes =
        ggml_backend_buffer_get_size(result->weights.buffer);
    result->bias_buffer_bytes =
        ggml_backend_buffer_get_size(result->biases.buffer);

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
            fail("tensor byte size mismatch while populating expert set");
        }
        ggml_backend_tensor_set(
            row.first, row.second->data(), 0, row.second->size());
    }
    return result;
}

std::unique_ptr<compute_graph> make_compute_graph(
        tensor_set & tensors,
        ggml_backend_t backend,
        int k,
        const std::vector<float> & input_values) {
    auto result = std::make_unique<compute_graph>();
    result->storage.ctx = make_context(16u * 1024u * 1024u);
    ggml_context * ctx = result->storage.ctx;

    result->input =
        ggml_new_tensor_3d(ctx, GGML_TYPE_F32, k_embd, 1, 1);
    result->ids =
        ggml_new_tensor_2d(ctx, GGML_TYPE_I32, k, 1);
    result->mix =
        ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 1, k, 1);

    ggml_tensor * up = ggml_mul_mat_id(
        ctx, tensors.up_w, result->input, result->ids);
    up = ggml_add_id(ctx, up, tensors.up_b, result->ids);

    ggml_tensor * gate = ggml_mul_mat_id(
        ctx, tensors.gate_w, result->input, result->ids);
    gate = ggml_add_id(ctx, gate, tensors.gate_b, result->ids);

    ggml_tensor * act =
        ggml_swiglu_oai(ctx, gate, up, k_swiglu_alpha, k_swiglu_limit);

    ggml_tensor * down =
        ggml_mul_mat_id(ctx, tensors.down_w, act, result->ids);
    down = ggml_add_id(ctx, down, tensors.down_b, result->ids);
    down = ggml_mul(ctx, down, result->mix);

    ggml_tensor * sum = nullptr;
    for (int expert = 0; expert < k; ++expert) {
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
        fail("failed to allocate expert compute graph");
    }

    if (input_values.size() != static_cast<size_t>(k_embd)) {
        fail("invalid input activation size");
    }
    ggml_backend_tensor_set(
        result->input,
        input_values.data(),
        0,
        input_values.size() * sizeof(float));

    std::vector<int32_t> ids(static_cast<size_t>(k));
    std::iota(ids.begin(), ids.end(), 0);
    ggml_backend_tensor_set(
        result->ids,
        ids.data(),
        0,
        ids.size() * sizeof(int32_t));

    std::vector<float> mix(static_cast<size_t>(k), 1.0f / static_cast<float>(k));
    ggml_backend_tensor_set(
        result->mix,
        mix.data(),
        0,
        mix.size() * sizeof(float));

    ggml_backend_synchronize(backend);
    return result;
}

template <class Fn>
stats measure(
        Fn && fn,
        int warmup,
        int samples,
        int inner) {
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
        static_cast<size_t>(std::ceil(0.95 * static_cast<double>(ordered.size()))) - 1);
    out.p95_ms = ordered[p95_index];
    out.mean_ms = std::accumulate(
        ordered.begin(), ordered.end(), 0.0) /
        static_cast<double>(ordered.size());
    return out;
}

void require_compute(
        ggml_backend_t backend,
        compute_graph & graph) {
    const ggml_status status =
        ggml_backend_graph_compute(backend, graph.graph);
    if (status != GGML_STATUS_SUCCESS) {
        fail("ggml_backend_graph_compute failed");
    }
}

std::vector<float> read_output(
        ggml_backend_t backend,
        ggml_tensor * tensor) {
    ggml_backend_synchronize(backend);
    const size_t n = ggml_nelements(tensor);
    std::vector<float> values(n);
    ggml_backend_tensor_get(
        tensor, values.data(), 0, values.size() * sizeof(float));
    return values;
}

parity compare_outputs(
        const std::vector<float> & cpu,
        const std::vector<float> & gpu) {
    if (cpu.size() != gpu.size() || cpu.empty()) {
        fail("output size mismatch for CPU/GPU parity");
    }
    double dot = 0.0;
    double norm_cpu = 0.0;
    double norm_gpu = 0.0;
    parity out;
    for (size_t i = 0; i < cpu.size(); ++i) {
        if (!std::isfinite(cpu[i]) || !std::isfinite(gpu[i])) {
            fail("non-finite CPU/GPU output");
        }
        const double a = cpu[i];
        const double b = gpu[i];
        out.max_abs = std::max(out.max_abs, std::abs(a - b));
        out.max_abs_ref = std::max(out.max_abs_ref, std::abs(a));
        dot += a * b;
        norm_cpu += a * a;
        norm_gpu += b * b;
    }
    out.relative_max =
        out.max_abs / std::max(1.0, out.max_abs_ref);
    out.cosine =
        dot / std::max(1e-30, std::sqrt(norm_cpu * norm_gpu));
    out.pass = out.relative_max <= 0.005 && out.cosine >= 0.9999;
    return out;
}

void copy_tensor_set(
        const tensor_set & source,
        tensor_set & destination,
        ggml_backend_t gpu_backend) {
    const std::array<std::pair<const ggml_tensor *, ggml_tensor *>, 6> rows = {{
        {source.gate_w, destination.gate_w},
        {source.up_w, destination.up_w},
        {source.down_w, destination.down_w},
        {source.gate_b, destination.gate_b},
        {source.up_b, destination.up_b},
        {source.down_b, destination.down_b},
    }};
    for (const auto & row : rows) {
        ggml_backend_tensor_copy(row.first, row.second);
    }
    ggml_backend_synchronize(gpu_backend);
}

void verify_gpu_tensor_set(
        const tensor_bytes & expected,
        const tensor_set & gpu) {
    const std::array<std::pair<const ggml_tensor *, const std::vector<uint8_t> *>, 6> rows = {{
        {gpu.gate_w, &expected.gate_w},
        {gpu.up_w, &expected.up_w},
        {gpu.down_w, &expected.down_w},
        {gpu.gate_b, &expected.gate_b},
        {gpu.up_b, &expected.up_b},
        {gpu.down_b, &expected.down_b},
    }};
    for (const auto & row : rows) {
        std::vector<uint8_t> observed(row.second->size());
        ggml_backend_tensor_get(
            row.first, observed.data(), 0, observed.size());
        if (observed != *row.second) {
            fail("GPU tensor bytes differ after Host->GPU transfer");
        }
    }
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

void print_result(FILE * out, const k_result & row) {
    std::fprintf(
        out,
        "{\"k\":%d,\"source_expert_ids\":[",
        row.k);
    for (int i = 0; i < row.k; ++i) {
        if (i != 0) {
            std::fputc(',', out);
        }
        std::fprintf(out, "%d", i);
    }
    std::fprintf(
        out,
        "],\"requested_weight_bytes\":%zu,"
        "\"activation_input_bytes\":%zu,\"activation_output_bytes\":%zu,"
        "\"cpu_weight_buffer_type\":",
        row.requested_weight_bytes,
        row.activation_input_bytes,
        row.activation_output_bytes);
    json_string(out, row.cpu_weight_buffer_type);
    std::fprintf(
        out,
        ",\"cpu_weight_buffer_bytes\":%zu,"
        "\"cpu_compute\":",
        row.cpu_weight_buffer_bytes);
    print_stats(out, row.cpu_compute);
    std::fputs(",\"gpu_compute\":", out);
    print_stats(out, row.gpu_compute);
    std::fputs(",\"activation_d2h\":", out);
    print_stats(out, row.activation_d2h);
    std::fputs(",\"activation_h2d\":", out);
    print_stats(out, row.activation_h2d);
    std::fputs(",\"weight_h2d_pageable\":", out);
    print_stats(out, row.weight_h2d_pageable);
    std::fprintf(
        out,
        ",\"pinned_available\":%s",
        row.pinned_available ? "true" : "false");
    if (row.pinned_available) {
        std::fputs(",\"weight_h2d_pinned\":", out);
        print_stats(out, row.weight_h2d_pinned);
    } else {
        std::fputs(",\"weight_h2d_pinned\":null", out);
    }
    std::fprintf(
        out,
        ",\"parity\":{\"max_abs\":%.9g,\"max_abs_ref\":%.9g,"
        "\"relative_max\":%.9g,\"cosine\":%.12f,\"status\":\"%s\"},"
        "\"derived\":{\"cpu_path_median_ms\":%.9f,"
        "\"cold_gpu_pageable_median_ms\":%.9f,"
        "\"resident_gpu_median_ms\":%.9f",
        row.output_parity.max_abs,
        row.output_parity.max_abs_ref,
        row.output_parity.relative_max,
        row.output_parity.cosine,
        row.output_parity.pass ? "PASS" : "FAIL",
        row.activation_d2h.median_ms +
            row.cpu_compute.median_ms +
            row.activation_h2d.median_ms,
        row.weight_h2d_pageable.median_ms +
            row.gpu_compute.median_ms,
        row.gpu_compute.median_ms);
    if (row.pinned_available) {
        std::fprintf(
            out,
            ",\"cold_gpu_pinned_median_ms\":%.9f",
            row.weight_h2d_pinned.median_ms +
                row.gpu_compute.median_ms);
    } else {
        std::fputs(",\"cold_gpu_pinned_median_ms\":null", out);
    }
    std::fputs("}}", out);
}

k_result run_k(
        const options & opt,
        int k,
        ggml_backend_dev_t cpu_dev,
        ggml_backend_dev_t gpu_dev,
        ggml_backend_t cpu_backend,
        ggml_backend_t gpu_backend) {
    const tensor_bytes data = load_tensor_bytes(opt.model, opt.layer, k);

    const ggml_backend_buffer_type_t cpu_default =
        ggml_backend_dev_buffer_type(cpu_dev);
    const ggml_backend_buffer_type_t gpu_default =
        ggml_backend_dev_buffer_type(gpu_dev);
    const ggml_backend_buffer_type_t cpu_weight =
        select_cpu_weight_buft(cpu_dev, k);

    auto cpu_set = make_tensor_set(
        data, k, cpu_weight, cpu_default);
    auto gpu_set = make_tensor_set(
        data, k, gpu_default, gpu_default);
    auto pageable_set = make_tensor_set(
        data, k, cpu_default, cpu_default);

    ggml_backend_buffer_type_t pinned_buft =
        ggml_backend_dev_host_buffer_type(gpu_dev);
    std::unique_ptr<tensor_set> pinned_set;
    if (pinned_buft) {
        pinned_set = make_tensor_set(
            data, k, pinned_buft, pinned_buft);
    }

    std::vector<float> input(static_cast<size_t>(k_embd));
    for (int64_t i = 0; i < k_embd; ++i) {
        input[static_cast<size_t>(i)] =
            0.5f * std::sin(static_cast<float>(i) * 0.017f);
    }

    auto cpu_graph =
        make_compute_graph(*cpu_set, cpu_backend, k, input);
    auto gpu_graph =
        make_compute_graph(*gpu_set, gpu_backend, k, input);

    require_compute(cpu_backend, *cpu_graph);
    require_compute(gpu_backend, *gpu_graph);
    const std::vector<float> cpu_output =
        read_output(cpu_backend, cpu_graph->output);
    const std::vector<float> gpu_output =
        read_output(gpu_backend, gpu_graph->output);
    const parity check = compare_outputs(cpu_output, gpu_output);
    if (!check.pass) {
        fail("CPU/GPU numerical parity gate failed");
    }

    copy_tensor_set(*pageable_set, *gpu_set, gpu_backend);
    verify_gpu_tensor_set(data, *gpu_set);

    const stats cpu_compute = measure(
        [&] { require_compute(cpu_backend, *cpu_graph); },
        opt.warmup,
        opt.samples,
        opt.compute_inner);
    const stats gpu_compute = measure(
        [&] { require_compute(gpu_backend, *gpu_graph); },
        opt.warmup,
        opt.samples,
        opt.compute_inner);

    const stats weight_pageable = measure(
        [&] { copy_tensor_set(*pageable_set, *gpu_set, gpu_backend); },
        opt.warmup,
        opt.samples,
        opt.transfer_inner);

    stats weight_pinned;
    const bool pinned_available = static_cast<bool>(pinned_set);
    if (pinned_available) {
        copy_tensor_set(*pinned_set, *gpu_set, gpu_backend);
        verify_gpu_tensor_set(data, *gpu_set);
        weight_pinned = measure(
            [&] { copy_tensor_set(*pinned_set, *gpu_set, gpu_backend); },
            opt.warmup,
            opt.samples,
            opt.transfer_inner);
    }

    require_compute(cpu_backend, *cpu_graph);
    const stats activation_d2h = measure(
        [&] {
            ggml_backend_tensor_copy(
                gpu_graph->input, cpu_graph->input);
            ggml_backend_synchronize(gpu_backend);
            ggml_backend_synchronize(cpu_backend);
        },
        opt.warmup,
        opt.samples,
        opt.activation_inner);

    const stats activation_h2d = measure(
        [&] {
            ggml_backend_tensor_copy(
                cpu_graph->output, gpu_graph->output);
            ggml_backend_synchronize(cpu_backend);
            ggml_backend_synchronize(gpu_backend);
        },
        opt.warmup,
        opt.samples,
        opt.activation_inner);

    return k_result{
        k,
        data.total(),
        static_cast<size_t>(k_embd) * sizeof(float),
        static_cast<size_t>(k_embd) * sizeof(float),
        cpu_set->weight_buffer_type,
        cpu_set->weight_buffer_bytes,
        cpu_compute,
        gpu_compute,
        activation_d2h,
        activation_h2d,
        weight_pageable,
        pinned_available,
        weight_pinned,
        check,
    };
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
        fail("CPU and CUDA GPU backends are both required");
    }

    backend_handle cpu;
    backend_handle gpu;
    cpu.backend = ggml_backend_dev_init(cpu_dev, nullptr);
    gpu.backend = ggml_backend_dev_init(gpu_dev, nullptr);
    if (!cpu.backend || !gpu.backend) {
        fail("failed to initialize CPU/GPU backend");
    }

    ggml_backend_cpu_set_n_threads(cpu.backend, opt.threads);

    const k_result k1 = run_k(
        opt, 1, cpu_dev, gpu_dev, cpu.backend, gpu.backend);
    const k_result k4 = run_k(
        opt, 4, cpu_dev, gpu_dev, cpu.backend, gpu.backend);

    FILE * out = std::fopen(opt.output.c_str(), "wx");
    if (!out) {
        fail("refusing or unable to create output: " + opt.output);
    }

    std::fputs(
        "{\"schema\":\"tesy.expert_crossover_raw.v1\","
        "\"classification\":\"MEASURED_EXPERT_CROSSOVER_MICROBENCHMARK\","
        "\"layer\":",
        out);
    std::fprintf(
        out,
        "%d,\"threads\":%d,\"warmup\":%d,\"samples\":%d,"
        "\"compute_inner\":%d,\"transfer_inner\":%d,"
        "\"activation_inner\":%d,\"n_embd\":%" PRId64 ","
        "\"expert_count_model\":%" PRId64 ","
        "\"encoded_bytes_per_expert\":%zu,"
        "\"weight_type\":\"mxfp4\",\"bias_type\":\"f32\","
        "\"weight_shape\":[2880,2880,32],\"bias_shape\":[2880,32],"
        "\"cpu_device\":",
        opt.layer,
        opt.threads,
        opt.warmup,
        opt.samples,
        opt.compute_inner,
        opt.transfer_inner,
        opt.activation_inner,
        k_embd,
        k_expert_count,
        k_encoded_bytes_per_expert);
    json_string(out, ggml_backend_dev_description(cpu_dev));
    std::fputs(",\"gpu_device\":", out);
    json_string(out, ggml_backend_dev_description(gpu_dev));
    std::fputs(",\"results\":[", out);
    print_result(out, k1);
    std::fputc(',', out);
    print_result(out, k4);
    std::fputs(
        "],\"claim_boundary\":"
        "\"Real encoded expert weights and the pinned ggml expert FFN operators "
        "are measured. Host-to-GPU and activation-copy byte counts are requested "
        "tensor bytes and wall times, not physical PCIe traffic. Setup/file reads "
        "and allocation/repack costs are excluded from steady-state timings. "
        "Routing is excluded; k=1 and k=4 use deterministic compact expert IDs.\"}\n",
        out);

    if (std::fclose(out) != 0) {
        fail("failed closing output file");
    }

    std::printf("PASS_EXPERT_CROSSOVER_RAW\n");
    std::printf("output: %s\n", opt.output.c_str());
    return 0;
}
