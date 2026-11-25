"""Insert the six-node CPU fusion into the authenticated parked-MMID C269 TU."""

import argparse
import hashlib
from pathlib import Path

ORIGINAL = "1b44449183cf431b5a623c083c9d52edfcfbfef7d6f6b1369988e7295b3c815b"
FUNCTION = "static int ggml_cpu_try_fuse_ops(\n"
ANCHOR = "    if (node->op == GGML_OP_RMS_NORM) {"
FUSION = """\
#ifdef TESY_C47_CPU_SKIP_PARKED
// Numerical fixture witness: one increment per region, by the graph executor
// with ith == 0. There is no mutation of the routing, graph or shared ID data.
static _Atomic uint64_t tesy_parked_regions = 0;
GGML_BACKEND_API uint64_t tesy_parked_fusion_count(void);
uint64_t tesy_parked_fusion_count(void) {
    return atomic_load_explicit(&tesy_parked_regions, memory_order_relaxed);
}

static bool tesy_separate(const struct ggml_tensor *a, const struct ggml_tensor *b) {
    // Conservative backing spans include padding. Subtraction avoids overflow
    // when adding a length to an address close to UINTPTR_MAX.
    const uintptr_t x = (uintptr_t)a->data, y = (uintptr_t)b->data;
    return x < y ? y-x >= ggml_nbytes(a) : x-y >= ggml_nbytes(b);
}

static bool tesy_shape(const struct ggml_tensor *t, enum ggml_type type,
        int64_t width, int64_t rows, int64_t positions) {
    return t && t->data && t->type == type && t->ne[0] == width &&
        t->ne[1] == rows && t->ne[2] == positions && t->ne[3] == 1;
}

static bool tesy_rows(const struct ggml_tensor *t) {
    // MXFP4 matrices and F32 activation/result rows. Accept non-overlapping
    // padded rows and expert slices. ID views have their own stride contract.
    return t->nb[0] == ggml_type_size(t->type) &&
        t->nb[1] >= ggml_row_size(t->type, t->ne[0]) &&
        t->nb[2] >= (size_t)t->ne[1]*t->nb[1] &&
        t->nb[3] >= (size_t)t->ne[2]*t->nb[2];
}

static bool tesy_region(const struct ggml_cgraph *g, int start,
        const struct ggml_compute_params *params) {
    enum { NGROUP = 6 };
    static const enum ggml_op ops[NGROUP] = { GGML_OP_MUL_MAT_ID, GGML_OP_ADD_ID,
        GGML_OP_MUL_MAT_ID, GGML_OP_ADD_ID, GGML_OP_GLU, GGML_OP_MUL_MAT_ID };
    const char *mode = getenv("TESY_CPU_PARKED_FUSION");
    if (!mode || !strcmp(mode, "0")) {
        return false;
    }
    if (strcmp(mode, "1")) {
        GGML_ABORT("TESY_CPU_PARKED_FUSION must be absent, 0 or 1");
    }
    const char *single = getenv("TESY_CPU_MMX_ALL_PARKED");
    if (!single || strcmp(single, "1")) {
        GGML_ABORT("region requires the qualified all-parked MMID");
    }
    // The sixth node is the only output of this region; its ADD_ID runs
    // normally at start+6. A scheduler slice ending inside it cannot fuse.
    if (g->n_nodes-start <= NGROUP || g->nodes[start+NGROUP]->op != GGML_OP_ADD_ID) {
        return false;
    }
    for (int i=0; i<NGROUP; ++i) {
        if (g->nodes[start+i]->op != ops[i]) return false;
    }
    const int down_idx = start+NGROUP-1;
    if (!ggml_can_fuse_subgraph(g, start, NGROUP, ops, &down_idx, 1)) return false;

    struct ggml_tensor *gate = g->nodes[start], *gate_bias = g->nodes[start+1];
    struct ggml_tensor *up = g->nodes[start+2], *up_bias = g->nodes[start+3];
    struct ggml_tensor *glu = g->nodes[start+4], *down = g->nodes[down_idx];
    struct ggml_tensor *down_bias = g->nodes[start+NGROUP];
    const struct ggml_tensor *x = gate->src[1], *ids = gate->src[2], *logical = gate_bias->src[2];
    if (!x || !ids || !logical || ids==logical || gate_bias->src[0]!=gate ||
        up_bias->src[0]!=up || down_bias->src[0]!=down || up->src[1]!=x ||
        up->src[2]!=ids || down->src[2]!=ids || up_bias->src[2]!=logical ||
        down_bias->src[2]!=logical || glu->src[0]!=gate_bias || glu->src[1]!=up_bias ||
        down->src[1]!=glu || ggml_get_glu_op(glu)!=GGML_GLU_OP_SWIGLU_OAI ||
        ggml_get_op_params_i32(glu,1)!=0 || ggml_get_op_params_f32(glu,2)!=1.702f ||
        ggml_get_op_params_f32(glu,3)!=7.0f) return false;
    // C269's original SwiGLU kernel asserts contiguous_1 for both of its
    // inputs and its result. Row padding alone does not establish this.
    if (!ggml_is_contiguous_1(gate_bias) || !ggml_is_contiguous_1(up_bias) ||
        !ggml_is_contiguous_1(glu)) return false;
    const int64_t n = ids->ne[1], ranks = 4, width = x->ne[0], ff = glu->ne[0];
    if (n<2 || n>32 || width<=0 || ff<=0 || width%32 || ff%32 ||
        !tesy_shape(ids,GGML_TYPE_I32,ranks,n,1) || !tesy_shape(logical,GGML_TYPE_I32,ranks,n,1) ||
        ids->nb[0]%sizeof(int32_t) || ids->nb[1]%sizeof(int32_t) ||
        logical->nb[0]%sizeof(int32_t) || logical->nb[1]%sizeof(int32_t) ||
        !tesy_shape(x,GGML_TYPE_F32,width,1,n) || !tesy_rows(x)) return false;
    const struct ggml_tensor *weight[] = {gate->src[0],up->src[0],down->src[0]};
    const struct ggml_tensor *bias[] = {gate_bias->src[1],up_bias->src[1],down_bias->src[1]};
    if (!weight[0] || !bias[0]) return false;
    const int64_t slots = weight[0]->ne[2], experts = bias[0]->ne[1];
    if (slots<=0 || experts<=0) return false;
    for (int i=0; i<3; ++i) {
        if (!tesy_shape(weight[i],GGML_TYPE_MXFP4,i==2?ff:width,i==2?width:ff,slots) ||
            !tesy_rows(weight[i]) || !tesy_shape(bias[i],GGML_TYPE_F32,i==2?width:ff,experts,1) ||
            !tesy_rows(bias[i])) return false;
    }
    const struct ggml_tensor *protected_inputs[] = {
        x, ids, logical, weight[0],weight[1],weight[2],bias[0],bias[1],bias[2] };
    for (int i=0; i<NGROUP; ++i) {
        const struct ggml_tensor *t = g->nodes[start+i];
        if (!tesy_shape(t,GGML_TYPE_F32,i==NGROUP-1?width:ff,ranks,n) ||
            !tesy_rows(t) || t->view_src) return false;
        for (size_t j=0; j<sizeof(protected_inputs)/sizeof(protected_inputs[0]); ++j) {
            if (!tesy_separate(t,protected_inputs[j])) return false;
        }
    }
    // The two bias-adds which disappear ordinarily check the logical IDs.
    // Keep their original handling of invalid inputs, including assertions.
    // Every thread reads the SAME physical and logical views. No thread can
    // overwrite either view as it writes the disjoint down destination.
    for (int64_t t=0; t<n; ++t) for (int64_t r=0; r<ranks; ++r) {
        int32_t physical, expert;
        const char *ps = (const char *)ids->data+r*ids->nb[0]+t*ids->nb[1];
        const char *ls = (const char *)logical->data+r*logical->nb[0]+t*logical->nb[1];
        memcpy(&physical,ps,sizeof(physical));
        memcpy(&expert,ls,sizeof(expert));
        if (physical!=-1 || expert<0 || expert>=experts) return false;
    }
    for (int64_t row=params->ith; row<n*ranks; row+=params->nth) {
        char *out = (char *)down->data+(row/ranks)*down->nb[2]+(row%ranks)*down->nb[1];
        memset(out,0,width*sizeof(float));
    }
    if (params->ith==0) atomic_fetch_add_explicit(&tesy_parked_regions, 1, memory_order_relaxed);
    return true;
}
#endif

"""
HOOK = """\
#ifdef TESY_C47_CPU_SKIP_PARKED
    // The native outer guard already enforces disable_fusion and use_ref.
    // Keep abort callbacks at their original node boundaries.
    if (node->op == GGML_OP_MUL_MAT_ID && !cplan->abort_callback &&
            tesy_region(cgraph,node_n,params)) {
        return 5;
    }
#endif

"""


def materialize(source: Path, dest: Path) -> str:
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != ORIGINAL:
        raise ValueError("expected authenticated C269 parked-MMID source")
    body = original.decode("utf-8")
    if body.count(FUNCTION) != 1:
        raise ValueError("CPU fusion entry point")
    before, after = body.split(FUNCTION)
    guard = after.index("if (ggml_cpu_disable_fusion || cplan->use_ref)")
    if after.count(ANCHOR) != 1 or not guard < after.index(ANCHOR) < after.index("return 1;"):
        raise ValueError("C269 fusion guard and hook")
    result = (before + FUSION + FUNCTION + after.replace(ANCHOR, HOOK + ANCHOR, 1)).encode()
    with dest.open("xb") as output:
        output.write(result)
    return hashlib.sha256(result).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--new-source", type=Path, required=True)
    args = parser.parse_args()
    print(materialize(args.source, args.new_source))


if __name__ == "__main__":
    main()
