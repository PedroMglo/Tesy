#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml-impl.h"

#include <array>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>

namespace {

using context_ptr = std::unique_ptr<ggml_context, decltype(&ggml_free)>;
using backend_ptr = std::unique_ptr<ggml_backend, decltype(&ggml_backend_free)>;
using scheduler_ptr = std::unique_ptr<ggml_backend_sched, decltype(&ggml_backend_sched_free)>;
using buffer_ptr = std::unique_ptr<ggml_backend_buffer, decltype(&ggml_backend_buffer_free)>;

void require(bool condition, const char * message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void middle_op(ggml_tensor * dst, const ggml_tensor * src, int ith, int nth, void * user_data) {
    (void) nth;
    if (ith != 0) {
        return;
    }
    auto * count = static_cast<int *>(user_data);
    ++*count;
    auto * out = static_cast<float *>(dst->data);
    const auto * in = static_cast<const float *>(src->data);
    for (int i = 0; i < 4; ++i) {
        out[i] = 2.0f * in[i];
    }
}

struct outcome {
    std::array<float, 4> output{};
    int middle_calls = 0;
    int prefix_compute_count = 0;
    int middle_compute_count = 0;
    int suffix_compute_count = 0;
};

outcome run_case(bool segmented, bool skip_middle) {
    outcome result;
    ggml_init_params params{};
    params.mem_size = 1024 * 1024;
    params.no_alloc = true;
    context_ptr ctx(ggml_init(params), ggml_free);
    require(ctx != nullptr, "ggml_init failed");

    auto * x = ggml_new_tensor_1d(ctx.get(), GGML_TYPE_F32, 4);
    auto * one = ggml_new_tensor_1d(ctx.get(), GGML_TYPE_F32, 4);
    ggml_set_input(x);
    ggml_set_input(one);
    auto * a = ggml_add(ctx.get(), x, one);
    ggml_set_name(a, "A");
    auto * b = ggml_map_custom1(ctx.get(), a, middle_op, 1, &result.middle_calls);
    ggml_set_name(b, "B-middle");
    auto * c = ggml_add(ctx.get(), b, one);
    ggml_set_name(c, "C-output");
    ggml_set_output(c);

    auto * graph = ggml_new_graph_custom(ctx.get(), 64, false);
    ggml_build_forward_expand(graph, c);
    int a_idx = -1;
    int b_idx = -1;
    int c_idx = -1;
    for (int i = 0; i < graph->n_nodes; ++i) {
        if (graph->nodes[i] == a) a_idx = i;
        if (graph->nodes[i] == b) b_idx = i;
        if (graph->nodes[i] == c) c_idx = i;
    }
    require(a_idx >= 0 && b_idx == a_idx + 1 && c_idx == b_idx + 1,
            "A/B/C graph order changed");

    backend_ptr cpu(ggml_backend_cpu_init(), ggml_backend_free);
    require(cpu != nullptr, "CPU backend init failed");
    ggml_backend_t backend = cpu.get();
    ggml_backend_buffer_type_t buft = ggml_backend_get_default_buffer_type(backend);
    scheduler_ptr sched(ggml_backend_sched_new(&backend, &buft, 1, 64, false, true),
                        ggml_backend_sched_free);
    require(sched != nullptr, "scheduler init failed");
    require(ggml_backend_sched_alloc_graph(sched.get(), graph), "full graph allocation failed");
    for (int i = 0; i < graph->n_nodes; ++i) {
        require(ggml_backend_sched_get_tensor_backend(sched.get(), graph->nodes[i]) == backend,
                "graph node not assigned to CPU backend");
        require(graph->nodes[i]->buffer != nullptr && graph->nodes[i]->data != nullptr,
                "allocated node has no buffer/data");
    }

    const std::array<float, 4> input{1.0f, 2.0f, 3.0f, 4.0f};
    const std::array<float, 4> ones{1.0f, 1.0f, 1.0f, 1.0f};
    ggml_backend_tensor_set(x, input.data(), 0, sizeof(input));
    ggml_backend_tensor_set(one, ones.data(), 0, sizeof(ones));
    void * const a_data = a->data;
    void * const b_data = b->data;
    void * const c_data = c->data;

    if (!segmented) {
        require(ggml_backend_sched_graph_compute(sched.get(), graph) == GGML_STATUS_SUCCESS,
                "MF0 full scheduler compute failed");
    } else {
        auto prefix = ggml_graph_view(graph, 0, b_idx);
        auto middle = ggml_graph_view(graph, b_idx, b_idx + 1);
        auto suffix = ggml_graph_view(graph, b_idx + 1, graph->n_nodes);
        require(ggml_backend_graph_compute(backend, &prefix) == GGML_STATUS_SUCCESS,
                "prefix compute failed");
        ++result.prefix_compute_count;
        if (skip_middle) {
            const std::array<float, 4> exact_middle{4.0f, 6.0f, 8.0f, 10.0f};
            ggml_backend_tensor_set(b, exact_middle.data(), 0, sizeof(exact_middle));
        } else {
            require(ggml_backend_graph_compute(backend, &middle) == GGML_STATUS_SUCCESS,
                    "middle compute failed");
            ++result.middle_compute_count;
        }
        require(ggml_backend_graph_compute(backend, &suffix) == GGML_STATUS_SUCCESS,
                "suffix compute failed");
        ++result.suffix_compute_count;
    }
    require(a->data == a_data && b->data == b_data && c->data == c_data,
            "tensor buffers changed between views");
    require(ggml_backend_sched_get_tensor_backend(sched.get(), b) == backend,
            "scheduler allocation was reset");
    ggml_backend_tensor_get(c, result.output.data(), 0, sizeof(result.output));
    return result;
}

void check_immediate_stage_capture() {
    ggml_init_params params{};
    params.mem_size = 1024 * 1024;
    params.no_alloc = true;
    context_ptr ctx(ggml_init(params), ggml_free);
    require(ctx != nullptr, "diagnostic context allocation failed");
    backend_ptr cpu(ggml_backend_cpu_init(), ggml_backend_free);
    require(cpu != nullptr, "diagnostic CPU backend failed");
    auto * input = ggml_new_tensor_1d(ctx.get(), GGML_TYPE_F32, 4);
    auto * one = ggml_new_tensor_1d(ctx.get(), GGML_TYPE_F32, 4);
    auto * two = ggml_new_tensor_1d(ctx.get(), GGML_TYPE_F32, 4);
    auto * first = ggml_add(ctx.get(), input, one);
    auto * second = ggml_mul(ctx.get(), first, two);
    auto * output = ggml_add(ctx.get(), second, one);
    auto * graph = ggml_new_graph_custom(ctx.get(), 64, false);
    ggml_build_forward_expand(graph, output);
    int first_index = -1;
    int second_index = -1;
    for (int i = 0; i < graph->n_nodes; ++i) {
        if (graph->nodes[i] == first) first_index = i;
        if (graph->nodes[i] == second) second_index = i;
    }
    require(first_index >= 0 && second_index > first_index &&
            second_index + 1 < graph->n_nodes,
            "diagnostic stage topology changed");
    buffer_ptr allocation(
        ggml_backend_alloc_ctx_tensors(ctx.get(), cpu.get()),
        ggml_backend_buffer_free);
    require(allocation != nullptr, "diagnostic graph allocation failed");
    const std::array<float, 4> x{1.0f, 2.0f, 3.0f, 4.0f};
    const std::array<float, 4> ones{1.0f, 1.0f, 1.0f, 1.0f};
    const std::array<float, 4> twos{2.0f, 2.0f, 2.0f, 2.0f};
    ggml_backend_tensor_set(input, x.data(), 0, sizeof(x));
    ggml_backend_tensor_set(one, ones.data(), 0, sizeof(ones));
    ggml_backend_tensor_set(two, twos.data(), 0, sizeof(twos));
    require(ggml_backend_graph_compute(cpu.get(), graph) == GGML_STATUS_SUCCESS,
            "diagnostic full graph compute failed");
    std::array<float, 4> full{};
    ggml_backend_tensor_get(output, full.data(), 0, sizeof(full));

    auto prefix = ggml_graph_view(graph, 0, first_index + 1);
    require(ggml_backend_graph_compute(cpu.get(), &prefix) == GGML_STATUS_SUCCESS,
            "diagnostic prefix failed");
    std::array<float, 4> captured_first{};
    ggml_backend_tensor_get(first, captured_first.data(), 0, sizeof(captured_first));
    auto middle = ggml_graph_view(graph, first_index + 1, second_index + 1);
    require(ggml_backend_graph_compute(cpu.get(), &middle) == GGML_STATUS_SUCCESS,
            "diagnostic middle failed");
    std::array<float, 4> captured_second{};
    ggml_backend_tensor_get(second, captured_second.data(), 0, sizeof(captured_second));
    auto suffix = ggml_graph_view(graph, second_index + 1, graph->n_nodes);
    require(ggml_backend_graph_compute(cpu.get(), &suffix) == GGML_STATUS_SUCCESS,
            "diagnostic suffix failed");
    std::array<float, 4> replay{};
    ggml_backend_tensor_get(output, replay.data(), 0, sizeof(replay));
    const std::array<float, 4> expected_first{2.0f, 3.0f, 4.0f, 5.0f};
    const std::array<float, 4> expected_second{4.0f, 6.0f, 8.0f, 10.0f};
    require(std::memcmp(captured_first.data(), expected_first.data(), sizeof(expected_first)) == 0 &&
            std::memcmp(captured_second.data(), expected_second.data(), sizeof(expected_second)) == 0 &&
            std::memcmp(full.data(), replay.data(), sizeof(full)) == 0,
            "immediate stage capture or segmented replay changed graph output");
}

} // namespace

int main() {
    try {
        const auto mf0 = run_case(false, false);
        const auto mf1 = run_case(true, false);
        const auto mf2 = run_case(true, true);
        require(mf0.middle_calls == 1 && mf1.middle_calls == 1,
                "MF0/MF1 did not call middle exactly once");
        require(mf2.middle_calls == 0 && mf2.middle_compute_count == 0,
                "MF2 executed the middle");
        require(mf1.prefix_compute_count == 1 && mf1.middle_compute_count == 1 &&
                mf1.suffix_compute_count == 1, "MF1 view counts invalid");
        require(mf2.prefix_compute_count == 1 && mf2.suffix_compute_count == 1,
                "MF2 view counts invalid");
        require(std::memcmp(mf0.output.data(), mf1.output.data(), sizeof(mf0.output)) == 0,
                "MF1 output differs bitwise from MF0");
        require(std::memcmp(mf0.output.data(), mf2.output.data(), sizeof(mf0.output)) == 0,
                "MF2 output differs bitwise from MF0");
        check_immediate_stage_capture();
        std::puts("SPLIT_GRAPH_MODEL_FREE_MF0_MF1_MF2_PASS");
        return 0;
    } catch (const std::exception & error) {
        std::fprintf(stderr, "SPLIT_GRAPH_MODEL_FREE_FAIL: %s\n", error.what());
        return 1;
    }
}
