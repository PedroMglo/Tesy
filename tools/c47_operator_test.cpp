// Model-free discriminant for C47's parked (-1) CPU MMID pair contract.
#include "ggml.h"
#include "ggml-cpu.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static void require(bool ok, const char * why) {
    if (!ok) {
        std::fprintf(stderr, "C47 operator FAIL: %s\n", why);
        std::exit(1);
    }
}

static void one_type(ggml_type type) {
    const ggml_init_params params = {16*1024*1024, nullptr, false};
    ggml_context * ctx = ggml_init(params);
    require(ctx != nullptr, "context");
    constexpr int64_t k = 32, m = 16, n_experts = 4, n_used = 2, n_tokens = 3;
    ggml_tensor * weights = ggml_new_tensor_3d(ctx, type, k, m, n_experts);
    ggml_tensor * input   = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, k, n_used, n_tokens);
    ggml_tensor * ids     = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, n_used, n_tokens);
    ggml_tensor * output  = ggml_mul_mat_id(ctx, weights, input, ids);
    for (int64_t e = 0; e < n_experts; e++) {
        for (int64_t r = 0; r < m*k; r++) {
            if (type == GGML_TYPE_F32) {
                ((float *) weights->data)[e*m*k+r] = float(e+1);
            } else {
                ((ggml_fp16_t *) weights->data)[e*m*k+r] = ggml_fp32_to_fp16(float(e+1));
            }
        }
    }
    for (int64_t i = 0; i < ggml_nelements(input); i++) {
        ((float *) input->data)[i] = 1.0f;
    }
    const int32_t selected[] = {-1, 1, 0, -1, -1, 3};
    std::memcpy(ids->data, selected, sizeof(selected));
    ggml_cgraph * graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(graph, output);
    require(ggml_graph_compute_with_ctx(ctx, graph, 4) == GGML_STATUS_SUCCESS, "sentinel compute");
    const auto * first = (const float *) output->data;
    std::vector<float> snapshot(first, first + ggml_nelements(output));
    for (int64_t t = 0; t < n_tokens; t++) {
        for (int64_t u = 0; u < n_used; u++) {
            const int id = selected[t*n_used+u];
            for (int64_t r = 0; r < m; r++) {
                const float value = snapshot[t*n_used*m+u*m+r];
                require(value == (id < 0 ? 0.0f : float(k*(id+1))), "parked zero or active exact dot");
                if (id < 0) {
                    uint32_t bits;
                    std::memcpy(&bits, &value, sizeof(bits));
                    require(bits == 0, "parked must be positive zero");
                }
            }
        }
    }
    auto * mutable_ids = (int32_t *) ids->data;
    for (int i = 0; i < 6; i++) {
        if (mutable_ids[i] < 0) mutable_ids[i] = 2;
    }
    require(ggml_graph_compute_with_ctx(ctx, graph, 4) == GGML_STATUS_SUCCESS, "resident control compute");
    const auto * control = (const float *) output->data;
    for (int64_t t = 0; t < n_tokens; t++) {
        for (int64_t u = 0; u < n_used; u++) {
            for (int64_t r = 0; r < m; r++) {
                const int64_t idx = t*n_used*m+u*m+r;
                if (selected[t*n_used+u] >= 0) {
                    require(std::memcmp(&snapshot[idx], &control[idx], sizeof(float)) == 0,
                            "active bits changed by skipped neighbors");
                } else {
                    require(control[idx] == 96.0f, "resident control mutant");
                }
            }
        }
    }
    ggml_free(ctx);
}

int main() {
    one_type(GGML_TYPE_F32);
    one_type(GGML_TYPE_F16);
    std::puts("C47_OPERATOR_PASS F32 F16 parked/active/control");
}
