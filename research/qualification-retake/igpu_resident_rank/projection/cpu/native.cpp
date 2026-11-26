// Reuse the complete pinned shape-one driver; change only the callback registered with GGML.
#include "ggml-backend.h"
static void install_capture(ggml_backend_sched_t, ggml_backend_sched_eval_callback, void *);
#define ggml_backend_sched_set_eval_callback install_capture
#define main reference_main
#include "decode.cpp"
#undef main
#undef ggml_backend_sched_set_eval_callback

extern "C" void quantize_row_q8_0(const float *, void *, int64_t);

namespace {
const std::string x_hash = "f4b7b1fc1595244c263e292a8cd2d6c1d3c939e00b56e151c5c5d48fc403092e";
const std::string weight_hash = "3a76d368a4c215dafd9d39e740d1db137709d8bac6df70084c918656ec31cc50";
ggml_tensor *gate_node = nullptr;
int captures = 0, bias_edges = 0;
F x, captured;
std::vector<uint8_t> weights;

bool shaped(const ggml_tensor *t, ggml_type type, int64_t n0, int64_t n1, int64_t n2) {
    return t && t->type == type && t->ne[0] == n0 && t->ne[1] == n1 &&
           t->ne[2] == n2 && t->ne[3] == 1;
}

bool capture(ggml_tensor *node, bool ask, void *opaque) {
    const bool subscribed = observe(node, ask, opaque);
    if (ask || !subscribed) return subscribed;
    auto &w = *static_cast<Witness *>(opaque);
    if (node->op == GGML_OP_MUL_MAT_ID && node->src[0] == state.tensors[0]) {
        auto *weight = node->src[0];
        need(++captures == 1 && bias_edges == 0 && w.remaps == 1, "gate observed once after remap");
        need(shaped(weight, GGML_TYPE_MXFP4, width, width, 40) && weight->nb[1] == 1530 &&
             weight->nb[2] == window && node->src[2] == w.remap &&
             shaped(node->src[1], GGML_TYPE_F32, width, 1, 1) &&
             shaped(node, GGML_TYPE_F32, width, 4, 1) && node->nb[0] == sizeof(float) &&
             node->nb[1] == width*sizeof(float), "gate geometry or physical source");
        equal(get<int>(w.ids), I(keys.begin(), keys.end()));
        equal(get<int>(w.remap), I(dest.begin(), dest.end()));
        {
            std::lock_guard<std::mutex> guard(state.mgr->mtx);
            auto &layer = *state.mgr->layer(0);
            need(layer.slot_expert[3] == 28 && layer.slot_gen[3] == 6 &&
                 layer.slot_state[3] == LLAMA_MOE_STREAM_SLOT_RESIDENT, "e28 resident generation");
        }
        x = get<float>(node->src[1]);
        need(digest(x.data(), x.size()*sizeof(float)) == x_hash, "C270 activation bytes");
        weights.resize(slab);
        ggml_backend_tensor_get(weight, weights.data(), size_t(dest[0])*weight->nb[2], slab);
        need(digest(weights.data(), weights.size()) == weight_hash, "e28 gate slab");
        gate_node = node;
        captured.resize(width);
        ggml_backend_tensor_get(node, captured.data(), 0, width*sizeof(float));
    } else if (node->op == GGML_OP_ADD_ID && node->src[1] == state.tensors[3]) {
        need(++bias_edges == 1 && captures == 1 && node->src[0] == gate_node &&
             node->src[2] == w.ids, "gate must feed original logical gate bias");
    }
    return subscribed;
}

template<class T> void write_bytes(const fs::path &path, const std::vector<T> &v) {
    std::ofstream f(path, std::ios::binary);
    need(bool(f.write(reinterpret_cast<const char *>(v.data()), v.size()*sizeof(T))), "write row");
    f.close();
    need(bool(f), "close row");
}

void compare_single(const fs::path &out) {
    need(captures == 1 && bias_edges == 1 && captured.size() == width, "exact capture coverage");
    write_bytes(out/"gate-rank0.f32", captured);
    ggml_backend_ptr cpu(ggml_backend_cpu_init());
    need(bool(cpu), "single CPU backend");
    ggml_backend_cpu_set_n_threads(cpu.get(), 8);
    auto ctx = context();
    auto *c = ctx.get();
    auto *weight = ggml_new_tensor_3d(c, GGML_TYPE_MXFP4, width, width, 1);
    auto *rhs = ggml_new_tensor_3d(c, GGML_TYPE_F32, width, 1, 1);
    auto *id = ggml_new_tensor_2d(c, GGML_TYPE_I32, 1, 1);
    auto *gate = ggml_mul_mat_id(c, weight, rhs, id);
    auto *graph = ggml_new_graph(c);
    ggml_build_forward_expand(graph, gate);
    ggml_backend_buffer_ptr memory(ggml_backend_alloc_ctx_tensors(c, cpu.get()));
    need(bool(memory) && shaped(gate, GGML_TYPE_F32, width, 1, 1), "compact graph storage");
    put(weight, weights);
    put(rhs, x);
    put(id, I{0});
    need(ggml_backend_graph_compute(cpu.get(), graph) == GGML_STATUS_SUCCESS, "compact graph compute");
    ggml_backend_synchronize(cpu.get());
    const F single = get<float>(gate);
    write_bytes(out/"single-rank0.f32", single);
    std::vector<uint8_t> q8(ggml_row_size(GGML_TYPE_Q8_0, width));
    need(q8.size() == 3060, "Q8_0 row size");
    quantize_row_q8_0(x.data(), q8.data(), width);
    write_bytes(out/"activation.q8", q8);
    int finite = 0, unequal = 0;
    for (int i = 0; i < width; ++i) {
        finite += std::isfinite(single[i]) && std::isfinite(captured[i]);
        unequal += std::memcmp(&single[i], &captured[i], sizeof(float)) != 0;
    }
    json proof = {
        {"status", unequal || finite != width ? "FAIL_PROJECTION_BITS" : "PASS_CPU0_E28_GATE_AND_SINGLE_RANK"},
        {"source","original_gate_mmid_before_add_id"}, {"shape",{width,4,1,1}},
        {"positions",1}, {"rank",0}, {"expert",28}, {"slot",3}, {"generation",6},
        {"gate_observations",captures}, {"bias_edges",bias_edges}, {"finite_values",finite},
        {"unequal_single",unequal}, {"gate_sha256",digest(captured.data(),width*4)},
        {"single_sha256",digest(single.data(),width*4)}, {"x_sha256",x_hash},
        {"weight_sha256",weight_hash}, {"q8_sha256",digest(q8.data(),q8.size())},
        {"provider_cpu",provider(reinterpret_cast<void *>(&quantize_row_q8_0))},
        {"provider_base",provider(reinterpret_cast<void *>(&ggml_backend_tensor_get))}
    };
    std::ofstream f(out/"gate.json");
    f << proof.dump() << '\n';
    f.close();
    need(bool(f) && unequal == 0 && finite == width, "finite exact single-rank replay");
}
} // namespace

static void install_capture(ggml_backend_sched_t sched, ggml_backend_sched_eval_callback cb, void *data) {
    need(cb == observe, "sole original observer");
    ggml_backend_sched_set_eval_callback(sched, capture, data);
}

int main(int argc, char **argv) {
    try {
        need(argc == 6 && std::string(argv[4]) == "ALIAS", "one ALIAS arm");
        const fs::path out = fs::path(argv[5]).parent_path()/"projection";
        need(fs::create_directory(out), "exclusive projection directory");
        const int status = reference_main(argc, argv);
        if (status != 0) return status;
        compare_single(out);
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL_CPU0_E28_GATE " << error.what() << '\n';
        return 1;
    }
}
