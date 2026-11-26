// Reuse the qualified loader observer, including inode and VMA checks.
#define main tiny_loader_observer_main
#include "../../tiny_loader/probe.cpp"
#undef main

#include "ggml-backend.h"
#include <array>
#include <cerrno>
#include <chrono>
#include <filesystem>
#include <stdexcept>
#include <vector>

namespace fs = std::filesystem;

static void require(bool condition, const char *label) {
    if (!condition) throw std::runtime_error(label);
}

static void phase(const char *label) {
    struct timespec t{};
    require(clock_gettime(CLOCK_MONOTONIC, &t) == 0, "monotonic clock");
    std::printf("PHASE %s %lld\n", label, 1000000000LL*t.tv_sec + t.tv_nsec);
}

static void provider(const char *label, const void *symbol) {
    Dl_info info{};
    require(dladdr(symbol, &info) && info.dli_fname, "dladdr");
    const auto path = fs::canonical(info.dli_fname);
    std::printf("PROVIDER %s %s\n", label, path.c_str());
}

static void exact_read(const fs::path &path, void *ptr, size_t size) {
    std::ifstream f(path, std::ios::binary);
    require(bool(f.read(static_cast<char *>(ptr), size)), "short or absent input");
    require(f.peek() == std::ifstream::traits_type::eof() && !f.bad(), "overlong or failed input");
}

struct Runtime {
    llama_model *model{};
    llama_context *ctx{};
    std::vector<const ggml_tensor *> weights;

    ~Runtime() {
        phase("cleanup_begin");
        if (ggml_moe_prefetch_enabled()) {
            for (const auto *weight : weights) ggml_moe_prefetch_wait(weight);
            ggml_moe_prefetch_set_n_threads(0);
        }
        std::printf("DRAIN %zu %d %d\n", weights.size(), int(ggml_moe_prefetch_enabled()), tasks());
        if (ctx) llama_free(ctx);
        if (model) llama_free_model(model);
        llama_backend_free();
        phase("cleanup_end");
    }
};

static int row(llama_context *ctx, int pos, int vocab, int expected, const fs::path &out,
               const fs::path &reference) {
    const auto *values = llama_get_logits_ith(ctx, -1);
    require(values, "missing last logits");
    const auto name = "pos"+std::to_string(pos)+".f32";
    const size_t size = vocab*sizeof(float);
    std::ofstream f(out/name, std::ios::binary);
    f.write(reinterpret_cast<const char *>(values), size);
    f.close();
    require(bool(f), "row write");
    int best = 0, ties = 0;
    for (int i = 0; i < vocab; ++i) {
        if (!std::isfinite(values[i])) return 45;
        if (values[i] > values[best]) {
            best = i;
            ties = 1;
        } else if (values[i] == values[best]) {
            ++ties;
        }
    }
    std::printf("ROW %d %d %d %d\n", pos, vocab, best, ties);
    if (!reference.empty()) {
        std::vector<float> prior(vocab);
        exact_read(reference/name, prior.data(), size);
        if (std::memcmp(prior.data(), values, size)) return pos == 15 ? 43 : 44;
    }
    if (pos == 15 && (ties != 1 || (expected >= 0 && expected != best))) return 42;
    return 0;
}

static int execute(int argc, char **argv) {
    require(argc == 7 || argc == 8, "PROFILE MODE MODEL IDS17.I32 EXPECTED_ARGMAX NEW_OUTPUT_DIR [D0_RAW_DIR]");
    const std::string profile = argv[1], mode = argv[2];
    const bool tiny = profile == "synthetic", calibration = tiny && mode == "CAL", prefetch = mode == "D1";
    require(tiny || profile == "c110", "profile");
    require(calibration || prefetch || mode == "D0", "mode");
    require((argc == 8) == prefetch, "D1 needs authenticated D0 rows");
    const std::string expected_word(argv[5]);
    const int expected = std::stoi(expected_word);
    const int vocab = tiny ? 32 : 201088, layers = tiny ? 2 : 36, hidden = tiny ? 256 : 2880;
    const int experts = tiny ? 8 : 128;
    require(expected_word == std::to_string(expected) &&
            (calibration ? expected == -1 : (expected >= 0 && expected < vocab)), "expected argmax");
    require(tiny || expected == 3659, "C110 first greedy");
    const char *ahead = std::getenv("GGML_MOE_PREFETCH_AHEAD");
    require(ahead && std::string(ahead) == "0", "AHEAD=0");
    require(stat(argv[3], &file_id) == 0 && S_ISREG(file_id.st_mode) &&
            file_id.st_size == (tiny ? 3390592LL : 63387346208LL), "model profile/size");

    std::array<llama_token, 17> ids{};
    static_assert(sizeof(llama_token) == 4 && sizeof(float) == 4 && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);
    exact_read(argv[4], ids.data(), sizeof(ids));
    for (auto id : ids) require(id >= 0 && id < vocab, "token outside vocabulary");
    require(ids[16] == (tiny ? 6 : 976), "teacher");
    const fs::path out(argv[6]);
    require(mkdir(out.c_str(), 0700) == 0, "new output directory");
    const fs::path reference = prefetch ? fs::path(argv[7]) : fs::path();
    if (prefetch) for (const auto name : {"pos15.f32", "pos16.f32"})
        require(fs::file_size(reference/name) == size_t(vocab)*4, "D0 reference shape");
    provider("llama", reinterpret_cast<const void *>(&llama_decode));
    provider("ggml", reinterpret_cast<const void *>(&ggml_backend_cpu_init));

    phase("load_begin");
    llama_backend_init();
    Runtime r;
    auto mp = llama_model_default_params();
    mp.n_gpu_layers = 0;
    mp.use_mmap = mp.defer_experts = mp.flash_attn = true;
    mp.fit = mp.use_mlock = mp.use_thp = mp.dry_run = mp.swa_compress = false;
    mp.repack_tensors = mp.merge_qkv = mp.merge_up_gate_exps = false;
    mp.check_tensors = mp.validate_quants = false;
    mp.type_k = mp.type_v = GGML_TYPE_F16;
    mp.n_ubatch = 32; mp.n_seq_max = 1; mp.max_ctx_size = 8192;
    loading = true;
    r.model = llama_model_load_from_file(argv[3], mp);
    loading = false;
    require(r.model && llama_n_vocab(r.model) == vocab && llama_n_layer(r.model) == layers &&
            llama_model_n_embd(r.model) == hidden, "model geometry");
    for (int layer = 0; layer < layers; ++layer) {
        for (const auto role : {"gate", "up", "down"}) {
            for (const auto kind : {std::string("weight"), std::string("bias")}) {
                const auto name = "blk."+std::to_string(layer)+".ffn_"+role+"_exps."+kind;
                inspect(r.model, name);
                const auto *t = llama_get_model_tensor(r.model, name.c_str());
                const bool weight = kind == "weight";
                require(t->type == (weight ? GGML_TYPE_MXFP4 : GGML_TYPE_F32) && t->ne[0] == hidden &&
                        t->ne[1] == (weight ? hidden : experts) && t->ne[2] == (weight ? experts : 1)
                        && t->ne[3] == 1, "mapped expert type/shape");
                if (weight) r.weights.push_back(t);
            }
        }
    }
    phase("load_end");
    auto p = llama_context_default_params();
    p.n_ctx = 8192; p.n_batch = 256; p.n_ubatch = 32; p.n_seq_max = 1;
    p.n_threads = p.n_threads_batch = 8;
    p.offload_kqv = p.swa_compress = p.logits_all = false;
    p.type_k = p.type_v = GGML_TYPE_F16;
    p.flash_attn = true;
    p.moe_cache_size = 0; p.prefetch_experts = prefetch; p.prefetch_experts_threads = 4;
    phase("context_begin");
    const int before = tasks();
    r.ctx = llama_init_from_model(r.model, p);
    require(r.ctx, "context");
    std::printf("POOL %d %d %d\n", before, tasks(), int(ggml_moe_prefetch_enabled()));
    require(ggml_moe_prefetch_enabled() == prefetch && llama_n_ctx(r.ctx) == 8192 &&
            llama_n_batch(r.ctx) == 256 && llama_n_ubatch(r.ctx) == 32 && llama_n_seq_max(r.ctx) == 8192
            && llama_get_kv_cache_used_cells(r.ctx) == 0 &&
            llama_n_threads(r.ctx) == 8 && llama_n_threads_batch(r.ctx) == 8, "effective geometry/pool");
    phase("context_end");
    phase("prefill_begin");
    require(!llama_decode(r.ctx, llama_batch_get_one(ids.data(), 16, 0, 0)), "prefill decode");
    llama_synchronize(r.ctx);
    phase("prefill_end");
    require(llama_get_kv_cache_used_cells(r.ctx) == 16, "16 used KV cells");
    std::printf("KV 15 16\n");
    const int first = row(r.ctx, 15, vocab, expected, out, reference);
    if (first) return first;
    phase("teacher_begin");
    require(!llama_decode(r.ctx, llama_batch_get_one(&ids[16], 1, 16, 0)), "teacher decode");
    llama_synchronize(r.ctx);
    phase("teacher_end");
    require(llama_get_kv_cache_used_cells(r.ctx) == 17, "17 used KV cells");
    std::printf("KV 16 17\n");
    return row(r.ctx, 16, vocab, expected, out, reference);
}

int main(int argc, char **argv) {
    setvbuf(stdout, nullptr, _IOLBF, 0);
    int rc = 1;
    try {
        rc = execute(argc, argv);
    } catch (const std::exception &e) {
        std::fprintf(stderr, "%s\n", e.what());
    }
    struct rusage usage{};
    if (!getrusage(RUSAGE_SELF, &usage)) std::printf("RSS %ld\n", usage.ru_maxrss);
    const char *status = "FAIL_IK_CPU_NUMERIC";
    switch (rc) {
        case 0: status = "PASS_IK_CPU_NUMERIC_ROWS"; break;
        case 42: status = "STOP_FIRST_GREEDY"; break;
        case 43: status = "STOP_FIRST_D0_BITS"; break;
        case 44: status = "STOP_SECOND_D0_BITS"; break;
        case 45: status = "STOP_NONFINITE"; break;
    }
    std::printf("STATUS %s\n", status);
    return rc;
}
