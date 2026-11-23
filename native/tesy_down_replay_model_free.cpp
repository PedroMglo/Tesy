#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"
#include "ggml-impl.h"

#include <array>
#include <cstdio>
#include <memory>
#include <stdexcept>

namespace {

void require(bool value, const char * message) {
    if (!value) throw std::runtime_error(message);
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

}  // namespace

int main() {
    try {
        backend_ptr backend(ggml_backend_cpu_init(), ggml_backend_free);
        require(backend != nullptr, "CPU backend failed");
        ggml_backend_cpu_set_n_threads(backend.get(), 1);
        auto weights_ctx = make_context();
        auto * weights = ggml_new_tensor_3d(weights_ctx.get(), GGML_TYPE_F32, 4, 4, 4);
        buffer_ptr weight_buffer(
            ggml_backend_alloc_ctx_tensors(weights_ctx.get(), backend.get()),
            ggml_backend_buffer_free);
        require(weight_buffer != nullptr, "weight allocation failed");
        std::array<float, 64> weight_values{};
        for (int expert = 0; expert < 4; ++expert) {
            for (int dim = 0; dim < 4; ++dim) {
                weight_values[static_cast<size_t>(expert * 16 + dim * 4 + dim)] =
                    static_cast<float>(expert + 1);
            }
        }
        ggml_backend_tensor_set(weights, weight_values.data(), 0,
                                sizeof(weight_values));

        auto graph_ctx = make_context();
        auto * input = ggml_new_tensor_3d(graph_ctx.get(), GGML_TYPE_F32, 4, 4, 1);
        auto * ids = ggml_new_tensor_2d(graph_ctx.get(), GGML_TYPE_I32, 4, 1);
        auto * down = ggml_mul_mat_id(graph_ctx.get(), weights, input, ids);
        auto * graph = ggml_new_graph(graph_ctx.get());
        ggml_build_forward_expand(graph, down);
        require(graph->n_nodes == 1 && graph->nodes[0] == down &&
                    down->op == GGML_OP_MUL_MAT_ID && down->src[1] == input &&
                    down->src[2] == ids,
                "down replay graph contains ancestors or wrong operator");
        buffer_ptr graph_buffer(
            ggml_backend_alloc_ctx_tensors(graph_ctx.get(), backend.get()),
            ggml_backend_buffer_free);
        require(graph_buffer != nullptr, "graph allocation failed");
        const std::array<int32_t, 4> route{2, 0, 3, 1};
        ggml_backend_tensor_set(ids, route.data(), 0, sizeof(route));
        std::array<float, 16> values{};
        for (int slot = 0; slot < 4; ++slot) {
            for (int dim = 0; dim < 4; ++dim) {
                values[static_cast<size_t>(slot * 4 + dim)] =
                    static_cast<float>(dim + 1);
            }
        }
        ggml_backend_tensor_set(input, values.data(), 0, sizeof(values));
        require(ggml_backend_graph_compute(backend.get(), graph) == GGML_STATUS_SUCCESS,
                "first replay failed");
        std::array<float, 16> first{};
        ggml_backend_tensor_get(down, first.data(), 0, sizeof(first));
        for (int slot = 0; slot < 4; ++slot) {
            for (int dim = 0; dim < 4; ++dim) {
                require(first[static_cast<size_t>(slot * 4 + dim)] ==
                            static_cast<float>((route[static_cast<size_t>(slot)] + 1) *
                                               (dim + 1)),
                        "global expert/slot mapping failed");
            }
        }
        for (int dim = 0; dim < 4; ++dim) {
            values[static_cast<size_t>(4 + dim)] += 1.0f;
        }
        ggml_backend_tensor_set(input, values.data(), 0, sizeof(values));
        require(ggml_backend_graph_compute(backend.get(), graph) == GGML_STATUS_SUCCESS,
                "second replay failed");
        std::array<float, 16> second{};
        ggml_backend_tensor_get(down, second.data(), 0, sizeof(second));
        for (int slot = 0; slot < 4; ++slot) {
            for (int dim = 0; dim < 4; ++dim) {
                const size_t index = static_cast<size_t>(slot * 4 + dim);
                require(second[index] == first[index] + (slot == 1 ? 1.0f : 0.0f),
                        "slot input substitution changed another expert");
            }
        }
        require(graph->n_nodes == 1, "replay recomputed an ancestor");
        std::puts("DOWN_REPLAY_MODEL_FREE_PASS");
        return 0;
    } catch (const std::exception & error) {
        std::fprintf(stderr, "DOWN_REPLAY_MODEL_FREE_FAIL: %s\n", error.what());
        return 1;
    }
}
