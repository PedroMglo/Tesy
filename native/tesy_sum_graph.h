#pragma once

#include "ggml.h"

// Both aggregation operands are independent leaves. Expanding this graph must
// never pull an already-computed expert graph into a second execution.
struct tesy_sum_nodes {
    ggml_tensor * gpu_partial;
    ggml_tensor * cpu_partial;
    ggml_tensor * output;
};

inline tesy_sum_nodes tesy_make_leaf_sum_nodes(ggml_context * ctx, int64_t n) {
    tesy_sum_nodes nodes{};
    nodes.gpu_partial = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, n, 1);
    nodes.cpu_partial = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, n, 1);
    nodes.output = ggml_add(ctx, nodes.gpu_partial, nodes.cpu_partial);
    return nodes;
}
