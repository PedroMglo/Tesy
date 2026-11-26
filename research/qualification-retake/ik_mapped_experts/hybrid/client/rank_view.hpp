#pragma once
#include "ggml.h"
#include <cstdint>
#include <cstring>

namespace tiny_rank {
inline bool router(const char *name) {
    return !std::strcmp(name, "ffn_moe_topk-0") || !std::strcmp(name, "ffn_moe_topk-1");
}

inline bool valid(const ggml_tensor *ids, int width) {
    if (!ids || (width != 1 && width != 32) || ids->type != GGML_TYPE_I32 ||
        ids->ne[0] != 4 || ids->ne[1] != width || ids->ne[2] != 1 || ids->ne[3] != 1 ||
        ids->nb[0] != sizeof(int32_t) || ids->nb[1] < 4 * sizeof(int32_t) ||
        ids->nb[1] % sizeof(int32_t) != 0) return false;
    const size_t size = ggml_nbytes(ids);
    if (ids->view_src) {
        const size_t span = ggml_nbytes(ids->view_src);
        if (ids->view_offs > span || size > span - ids->view_offs) return false;
    }
    return size >= 4*sizeof(int32_t) &&
        (width == 1 || ids->nb[1] <= (size - 4*sizeof(int32_t))/size_t(width-1));
}
}
