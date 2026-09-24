#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"
#include "ggml-impl.h"
#include "tesy_sum_graph.h"

#include <array>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>

namespace {

void require(bool value, const char * message) {
    if (!value) throw std::runtime_error(message);
}

void counted_double(ggml_tensor * dst, const ggml_tensor * src,
                    int ith, int nth, void * user_data) {
    (void) nth;
    if (ith != 0) return;
    ++*static_cast<int *>(user_data);
    const auto * in = static_cast<const float *>(src->data);
    auto * out = static_cast<float *>(dst->data);
    for (int i = 0; i < 4; ++i) out[i] = in[i] * 2.0f;
}

using context_ptr = std::unique_ptr<ggml_context, decltype(&ggml_free)>;
using backend_ptr = std::unique_ptr<ggml_backend, decltype(&ggml_backend_free)>;
using buffer_ptr = std::unique_ptr<ggml_backend_buffer, decltype(&ggml_backend_buffer_free)>;

context_ptr make_context() {
    ggml_init_params params{};
    params.mem_size = 1024 * 1024;
    params.no_alloc = true;
    context_ptr ctx(ggml_init(params), ggml_free);
    require(ctx != nullptr, "context allocation failed");
    return ctx;
}

} // namespace

int main() {
    try {
        backend_ptr backend(ggml_backend_cpu_init(), ggml_backend_free);
        require(backend != nullptr, "CPU backend failed");

        auto expert_ctx = make_context();
        auto * input = ggml_new_tensor_1d(expert_ctx.get(), GGML_TYPE_F32, 4);
        int expert_calls = 0;
        auto * expert_output = ggml_map_custom1(
            expert_ctx.get(), input, counted_double, 1, &expert_calls);
        auto * expert_graph = ggml_new_graph(expert_ctx.get());
        ggml_build_forward_expand(expert_graph, expert_output);
        buffer_ptr expert_buffer(
            ggml_backend_alloc_ctx_tensors(expert_ctx.get(), backend.get()),
            ggml_backend_buffer_free);
        require(expert_buffer != nullptr, "expert buffer failed");

        auto sum_ctx = make_context();
        const auto sum = tesy_make_leaf_sum_nodes(sum_ctx.get(), 4);
        auto * sum_graph = ggml_new_graph(sum_ctx.get());
        ggml_build_forward_expand(sum_graph, sum.output);
        require(sum_graph->n_nodes == 1 && sum_graph->nodes[0] == sum.output,
                "aggregation pulled expert ancestors into graph");
        require(sum.output->src[0] == sum.gpu_partial &&
                sum.output->src[1] == sum.cpu_partial &&
                sum.gpu_partial->op == GGML_OP_NONE &&
                sum.cpu_partial->op == GGML_OP_NONE,
                "aggregation operands are not independent leaves");
        buffer_ptr sum_buffer(
            ggml_backend_alloc_ctx_tensors(sum_ctx.get(), backend.get()),
            ggml_backend_buffer_free);
        require(sum_buffer != nullptr, "sum buffer failed");

        const std::array<float, 4> x{1.0f, 2.0f, 3.0f, 4.0f};
        const std::array<float, 4> cpu_partial{3.0f, 3.0f, 3.0f, 3.0f};
        ggml_backend_tensor_set(input, x.data(), 0, sizeof(x));
        require(ggml_backend_graph_compute(backend.get(), expert_graph) ==
                    GGML_STATUS_SUCCESS, "expert compute failed");
        require(expert_calls == 1, "expert did not execute once");
        ggml_backend_tensor_copy(expert_output, sum.gpu_partial);
        ggml_backend_tensor_set(sum.cpu_partial, cpu_partial.data(), 0,
                                sizeof(cpu_partial));
        require(ggml_backend_graph_compute(backend.get(), sum_graph) ==
                    GGML_STATUS_SUCCESS, "aggregation compute failed");
        std::array<float, 4> observed{};
        const std::array<float, 4> expected{5.0f, 7.0f, 9.0f, 11.0f};
        ggml_backend_tensor_get(sum.output, observed.data(), 0, sizeof(observed));
        require(std::memcmp(observed.data(), expected.data(), sizeof(observed)) == 0,
                "aggregation output incorrect");
        require(expert_calls == 1, "aggregation re-executed expert compute");
        std::puts("SUM_GRAPH_MODEL_FREE_TOPOLOGY_EXECUTION_PASS");
        return 0;
    } catch (const std::exception & error) {
        std::fprintf(stderr, "SUM_GRAPH_MODEL_FREE_FAIL: %s\n", error.what());
        return 1;
    }
}
