// Included in C269's CPU executor, under TESY_C47_CPU_SKIP_PARKED.
static bool tesy_wave_enabled = false; // set inside the existing CPU initialization lock

#ifdef TESY_WAVE_AUDIT
static _Atomic uint64_t tesy_wave_count;
GGML_BACKEND_API uint64_t tesy_cpu_wave_count(void);
uint64_t tesy_cpu_wave_count(void) {
    return atomic_load_explicit(&tesy_wave_count, memory_order_relaxed);
}
__attribute__((destructor)) static void tesy_wave_report(void) {
    if (getenv("TESY_WAVE_REPORT")) {
        fprintf(stderr, "TESY_CPU_WAVES=%" PRIu64 "\n", tesy_cpu_wave_count());
    }
}
#endif

static bool tesy_dims(const struct ggml_tensor * t, enum ggml_type type, int64_t x, int64_t y, int64_t z) {
    return t && t->data && t->type == type && t->ne[0] == x && t->ne[1] == y && t->ne[2] == z && t->ne[3] == 1;
}

static bool tesy_disjoint(const struct ggml_tensor * a, const struct ggml_tensor * b) {
    const uintptr_t x = (uintptr_t) a->data, y = (uintptr_t) b->data;
    return x < y ? y - x >= ggml_nbytes(a) : x - y >= ggml_nbytes(b);
}

// Reproduce three individually rounded F32 operations, including the sign of zero.
__attribute__((optimize("fp-contract=off")))
static void tesy_sum_row(float * out, const float * prev, const float * bias, float mask, int64_t width) {
    for (int64_t i = 0; i < width; ++i) {
        const float projected = 0.0f + bias[i];
        const float weighted = projected * mask;
        out[i] = prev[i] + weighted;
    }
}

static bool tesy_parked_wave(const struct ggml_cgraph * graph, int at, const struct ggml_compute_params * p) {
    enum { count = 10, ranks = 4, max_rows = 32*ranks };
    static const enum ggml_op pattern[count] = {
        GGML_OP_MUL_MAT_ID, GGML_OP_ADD_ID, GGML_OP_MUL_MAT_ID, GGML_OP_ADD_ID, GGML_OP_GLU,
        GGML_OP_MUL_MAT_ID, GGML_OP_ADD_ID, GGML_OP_CUSTOM, GGML_OP_MUL, GGML_OP_ADD
    };
    const int last = at + count - 1;
    if (at < 1 || last >= graph->n_nodes) return false;
    struct ggml_tensor * const * v = graph->nodes + at;
    for (int i = 0; i < count; ++i) {
        if (v[i]->op != pattern[i]) return false;
    }
    const struct ggml_tensor * ids = v[0]->src[2], * logical = v[1]->src[2];
    const struct ggml_tensor * prev = v[9]->src[0], * bias = v[6]->src[1];
    struct ggml_tensor * mask = v[7], * sum = v[9];
    if (!ids || ids != v[-1] || ids->op != GGML_OP_CUSTOM || !logical || !prev || !bias) return false;
    const int64_t n = ids->ne[1], width = prev->ne[0], ff = v[4]->ne[0];
    const struct ggml_tensor * contiguous = ids->src[0], * order = ids->src[1];
    if (n < 2 || n > 32 || width < 32 || ff < 32 || width % 32 || ff % 32 ||
        !tesy_dims(ids, GGML_TYPE_I32, ranks, n, 1) || !ggml_is_contiguous(ids) ||
        !tesy_dims(logical, GGML_TYPE_I32, ranks, n, 1) ||
        !tesy_dims(contiguous, GGML_TYPE_I32, ranks, n, 1) || !ggml_is_contiguous(contiguous) ||
        (contiguous != logical && (contiguous->op != GGML_OP_CONT || contiguous->src[0] != logical)) ||
        !order || order->op != GGML_OP_VIEW || order->src[0] != prev ||
        mask->src[0] != contiguous || mask->src[1] != ids ||
        !tesy_dims(mask, GGML_TYPE_F32, 1, ranks, n) || !ggml_is_contiguous(mask)) return false;
    const int32_t * physical = ids->data;
    for (int i = 0; i < n*ranks; ++i) {
        if (physical[i] != -1) return false;
    }
    if (v[2]->src[1] != v[0]->src[1] || v[4]->src[0] != v[1] || v[4]->src[1] != v[3] ||
        ggml_get_glu_op(v[4]) != GGML_GLU_OP_SWIGLU_OAI || v[5]->src[1] != v[4] ||
        v[8]->src[0] != v[6] || v[8]->src[1] != mask || sum->src[1] != v[8] ||
        !tesy_dims(prev, GGML_TYPE_F32, width, ranks, n) || !ggml_is_contiguous(prev) ||
        !tesy_dims(sum, GGML_TYPE_F32, width, ranks, n) || !ggml_is_contiguous(sum) ||
        !tesy_dims(v[0]->src[1], GGML_TYPE_F32, width, 1, n) ||
        ggml_get_op_params_i32(v[4],1) != 0 || ggml_get_op_params_f32(v[4],2) != 1.702f ||
        ggml_get_op_params_f32(v[4],3) != 7.0f) return false;
    const int mats[] = {0,2,5};
    for (int k = 0; k < 3; ++k) {
        const struct ggml_tensor * mat = v[mats[k]], * add = v[mats[k]+1];
        const int64_t input = k == 2 ? ff : width, output = k == 2 ? width : ff;
        if (mat->src[2] != ids || add->src[0] != mat || add->src[2] != logical ||
            !tesy_dims(mat->src[0], GGML_TYPE_MXFP4, input, output, 40) ||
            !tesy_dims(add->src[1], GGML_TYPE_F32, output, 128, 1) ||
            !tesy_dims(mat, GGML_TYPE_F32, output, ranks, n) ||
            !tesy_dims(add, GGML_TYPE_F32, output, ranks, n)) return false;
    }
    if (!ggml_is_contiguous(bias) || !tesy_disjoint(bias, sum) || !tesy_disjoint(bias, mask) ||
        !tesy_disjoint(prev, mask) || (sum->data != prev->data && !tesy_disjoint(prev, sum)) ||
        !ggml_can_fuse_subgraph(graph, at, count, pattern, &last, 1)) return false;

    // The allocator only owes us the original lifetimes. Keep the logical IDs
    // before the mask, and keep its produced values before writing the final sum.
    int32_t expert[max_rows];
    float weight[max_rows];
    for (int row = 0; row < n*ranks; ++row) {
        const char * ptr = (const char *) logical->data +
                (row/ranks)*logical->nb[1] + (row%ranks)*logical->nb[0];
        memcpy(&expert[row], ptr, sizeof(expert[row]));
        if (expert[row] < 0 || expert[row] >= 128) return false;
    }
    ggml_barrier(p->threadpool);
    ggml_compute_forward_custom(p, mask);
    ggml_barrier(p->threadpool);
    memcpy(weight, mask->data, (size_t)(n*ranks)*sizeof(float));
    ggml_barrier(p->threadpool);
    for (int row = p->ith; row < n*ranks; row += p->nth) {
        const size_t pos = (size_t)row*width;
        tesy_sum_row((float *) sum->data + pos, (const float *) prev->data + pos,
                     (const float *) bias->data + (size_t)expert[row]*width, weight[row], width);
    }
#ifdef TESY_WAVE_AUDIT
    if (p->ith == 0) atomic_fetch_add_explicit(&tesy_wave_count, 1, memory_order_relaxed);
#endif
    return true;
}
