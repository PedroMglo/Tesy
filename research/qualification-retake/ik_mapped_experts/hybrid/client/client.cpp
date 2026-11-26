#define main tiny_loader_legacy_entry
#include "../../tiny_loader/probe.cpp"
#undef main
#include "../../cpu_numeric/vma/inspect.hpp"
#include "ggml-backend.h"
#include "hooks.hpp"
#include "rank_view.hpp"
#include <atomic>
#include <cinttypes>
#include <filesystem>
#include <poll.h>
#include <vector>

namespace fs = std::filesystem;
static void must(bool v, const char *why) {
    if (!v) throw std::runtime_error(why);
}

namespace observe {
int phase{};
thread_local unsigned long owner{};
static std::atomic_ulong ticket{0};
static ik_vma::Inspect witness;
int64_t file_offset(const void *p, size_t n) {
    const uintptr_t addr = uintptr_t(p);
    if (!base || addr < base || addr-base >= length) return -1;
    auto current = witness;
    current.maps = ik_vma::read_maps();
    auto region = ik_vma::cover(current.maps, addr);
    if (region.inode != witness.key.inode || region.path != witness.key.path) return -1;
    return static_cast<int64_t>(current.offset("transfer",base,length,addr,n));
}
void transfer(const char *api, void *dst, const void *src, size_t n, int kind, int rc) {
    if (!phase) return;
    const int64_t off = kind == 1 || kind == 4 ? file_offset(src,n) : -1;
    std::printf("COPY %d %lu %s %d %zu %zu %zu %lld %d\n",phase,owner,api,kind,
                uintptr_t(dst),uintptr_t(src),n,(long long)off,rc);
}
}

template <typename T> static T next_fn(const char *name) {
    auto p = dlsym(RTLD_NEXT,name);
    if (!p) std::abort();
    return reinterpret_cast<T>(p);
}

struct Set {
    unsigned long saved = observe::owner;
    Set(const char *api, ggml_tensor *t, const void *src, size_t off, size_t n) {
        if (!observe::phase) return;
        observe::owner = ++observe::ticket;
        std::printf("SET %d %lu %lu %s %s %zu %zu %zu %zu %lld\n",observe::phase,
                    observe::owner,saved,api,*t->name?t->name:"-",uintptr_t(t->data),off,n,uintptr_t(src),
                    (long long)observe::file_offset(src,n));
    }
    ~Set() { observe::owner = saved; }
};

extern "C" void ggml_backend_tensor_set(ggml_tensor *t,const void *src,size_t off,size_t n) {
    static auto real = next_fn<decltype(&ggml_backend_tensor_set)>("ggml_backend_tensor_set");
    Set scope("sync",t,src,off,n);
    real(t,src,off,n);
}
extern "C" void ggml_backend_tensor_set_async(ggml_backend_t b, ggml_tensor *t, const void *src,
                                              size_t off, size_t n) {
    static auto real = next_fn<decltype(&ggml_backend_tensor_set_async)>("ggml_backend_tensor_set_async");
    Set scope("async",t,src,off,n);
    real(b,t,src,off,n);
}
static bool multiply(const ggml_tensor *t) { return t->op == GGML_OP_MUL_MAT_ID; }
static bool interest(const ggml_tensor *t) { return multiply(t) || t->op == GGML_OP_ADD_ID; }

extern "C" ggml_status ggml_backend_graph_compute_async(ggml_backend_t b, ggml_cgraph *g) {
    static auto real = next_fn<decltype(&ggml_backend_graph_compute_async)>("ggml_backend_graph_compute_async");
    auto rc = real(b,g);
    if (observe::phase == 3 || observe::phase == 4) {
        for (int i=0; i<ggml_graph_n_nodes(g); ++i) {
            const auto *t = ggml_graph_node(g,i);
            if (interest(t)) std::printf("SUBMIT %d %zu %s %d\n", observe::phase,uintptr_t(t),
                                        ggml_backend_name(b),int(rc));
        }
    }
    return rc;
}

static std::string rank_ids(const ggml_tensor *ids, const ggml_tensor *node, const char *kind) {
    must(ids && node, "rank operand missing");
    std::printf("RANK_VIEW %d %s %s %d %lld %lld %lld %lld %zu %zu %zu %zu %zu\n",
                observe::phase, kind, node->name, int(ids->type),
                (long long)ids->ne[0], (long long)ids->ne[1], (long long)ids->ne[2], (long long)ids->ne[3],
                ids->nb[0], ids->nb[1], ids->nb[2], ids->nb[3], ggml_nbytes(ids));
    must(tiny_rank::valid(ids, observe::phase == 3 ? 32 : 1), "rank shape/stride/extent");

    std::string arg;
    for (int i=0; i<ids->ne[1]; ++i) {
        int32_t v[4]{};
        ggml_backend_tensor_get(ids,v,i*ids->nb[1],sizeof(v));
        for (int x : v) {
            if (!arg.empty()) arg += ',';
            arg += std::to_string(x);
        }
    }
    return arg;
}
static int callback(ggml_tensor *t, bool ask, void *) {
    const bool route = tiny_rank::router(t->name);
    if (!interest(t) && !route) return false;
    if (ask) return 1; // stock scheduler synchronizes before reading this node
    if (route) {
        std::printf("ROUTE %d %s %s\n",observe::phase,t->name,rank_ids(t,t,"logical").c_str());
        return 1;
    }
    const bool mm = multiply(t);
    auto *w = t->src[mm ? 0 : 1];
    must(w, "consumer weight");
    auto *buf = w->view_src ? w->view_src->buffer : w->buffer;
    must(buf && t->buffer, "materialized operand");
    const auto arg = rank_ids(t->src[2],t,mm?"physical":"bias");
    std::printf("NODE %d %zu %s %s %s %zu %lld %zu %s %s %s\n",observe::phase,uintptr_t(t),
                mm ? "mm" : "bias",t->name,w->name,uintptr_t(w->data),(long long)w->ne[2],
                w->nb[2],ggml_backend_buffer_name(buf),ggml_backend_buffer_name(t->buffer),arg.c_str());
    return 1;
}

static void output(llama_context *ctx, int n, const fs::path &dst) {
    std::ofstream file(dst,std::ios::binary);
    for (int i=0; i<n; ++i) {
        const auto *v=llama_get_logits_ith(ctx,i);
        must(v,"omitted output");
        for(int j=0; j<32; ++j) must(std::isfinite(v[j]),"nonfinite");
        file.write(reinterpret_cast<const char *>(v),32*sizeof(float));
    }
    file.close();
    must(bool(file),"output write");
}
static void census(llama_model *model) {
    for(int i=0;i<2;++i) for(const char *role:{"gate","up","down"}) for(const char *kind:{"weight","bias"}) {
        auto name = "blk."+std::to_string(i)+".ffn_"+role+"_exps."+kind;
        auto *w = llama_get_model_tensor(model,name.c_str());
        must(w && w->buffer && w->data,"model tensor");
        std::printf("ORIG %s %zu %zu %lld %d %s\n",name.c_str(),uintptr_t(w->data),ggml_nbytes(w),
                    (long long)observe::file_offset(w->data,ggml_nbytes(w)),int(w->type),
                    ggml_backend_buffer_name(w->buffer));
    }
}

static void handoff(bool cpu, char expected) {
    if (cpu) return;
    const char *tx=std::getenv("TESY_TEST_TX"), *rx=std::getenv("TESY_TEST_RX");
    must(tx && rx,"GPU monitor missing");
    const int w=std::stoi(tx), r=std::stoi(rx);
    must(w!=r && w>2 && r>2 && write(w,&expected,1)==1,"notify monitor");
    pollfd wait{r,POLLIN,0};
    char ack=0;
    must(poll(&wait,1,3000)==1 && (wait.revents & POLLIN) && read(r,&ack,1)==1 && ack==expected,
         "GPU monitor acknowledgement");
}
static int run(int argc,char **argv) {
    must(argc==4,"client CPU|RESIDENT|BANK9|BANK7 TINY.GGUF NEW_DIR");
    auto mode=std::string(argv[1]);
    bool cpu=mode=="CPU", bank=mode=="BANK9" || mode=="BANK7";
    must(cpu || bank || mode=="RESIDENT","mode");
    must(stat(argv[2],&file_id)==0 && S_ISREG(file_id.st_mode) && file_id.st_size==3390592,"tiny only");
    const char *ahead=std::getenv("GGML_MOE_PREFETCH_AHEAD");
    must(ahead && std::string(ahead)=="0" && !std::getenv("GGML_CUDA_REGISTER_HOST") &&
         !std::getenv("GGML_CUDA_ENABLE_UNIFIED_MEMORY"),"environment");
    must(mkdir(argv[3],0700)==0,"new raw directory");
    fs::path dst(argv[3]);
    observe::witness=ik_vma::Inspect::capture(argv[2], file_id);
    handoff(cpu,'E');
    observe::phase=1;
    llama_backend_init();
    auto m=llama_model_default_params();
    m.n_gpu_layers=cpu ? 0 : 99; m.ncmoe=bank ? 999 : 0; m.split_mode=LLAMA_SPLIT_MODE_LAYER;
    m.defer_experts=bank; m.use_mmap=true; m.type_k=m.type_v=GGML_TYPE_F16;
    m.fit=m.use_mlock=m.use_thp=m.dry_run=m.repack_tensors=m.merge_qkv=m.merge_up_gate_exps=false;
    m.check_tensors=m.validate_quants=m.flash_attn=m.swa_compress=false;
    m.max_ctx_size=256; m.n_ubatch=32; m.n_seq_max=1;
    loading=true;
    auto *model=llama_model_load_from_file(argv[2],m);
    loading=false;
    must(model && llama_n_vocab(model)==32 && llama_n_layer(model)==2 && llama_model_n_embd(model)==256,"shape");
    census(model);
    observe::phase=2;
    auto p=llama_context_default_params();
    p.n_ctx=256; p.n_seq_max=1; p.n_batch=p.n_ubatch=32; p.n_threads=p.n_threads_batch=8;
    p.type_k=p.type_v=GGML_TYPE_F16; p.flash_attn=p.swa_compress=false;
    p.fused_moe_up_gate=p.fused_up_gate=p.fused_mmad=false; p.prefetch_experts=false;
    p.moe_cache_policy=LLAMA_MOE_CACHE_POLICY_LRU; p.moe_cache_cpu_share=0.0f;
    p.moe_cache_size=mode=="BANK9" ? 1048576 : mode=="BANK7" ? 835584 : 0;
    p.offload_kqv=!cpu; p.cb_eval=callback; p.logits_all=true;
    auto *ctx=llama_init_from_model(model,p);
    must(ctx && llama_n_ctx(ctx)==256 && llama_n_ubatch(ctx)==32 && !ggml_moe_prefetch_enabled(),"context");
    handoff(cpu,'A');
    for (int n : {32,1}) {
        observe::phase=n==32 ? 3 : 4;
        auto batch=llama_batch_init(n,0,1);
        batch.n_tokens=n;
        for(int i=0;i<n;++i) {
            batch.token[i]=7; batch.pos[i]=(n==32 ? 0 : 32)+i;
            batch.n_seq_id[i]=1; batch.seq_id[i][0]=0; batch.logits[i]=1;
        }
        must(!llama_decode(ctx,batch),"llama_decode");
        llama_synchronize(ctx);
        output(ctx,n,dst/(n==32 ? "prefill.f32":"teacher.f32"));
        llama_batch_free(batch);
    }
    {std::ifstream maps("/proc/self/maps"); std::ofstream snap(dst/"maps");
     snap<<maps.rdbuf(); snap.close(); must(bool(snap),"maps");}
    handoff(cpu,'F');
    observe::phase=5;
    llama_free(ctx); llama_free_model(model); llama_backend_free();
    observe::phase=0;
    std::puts("STATUS COMPLETED_TINY_HYBRID_CLIENT");
    return 0;
}
int main(int argc,char **argv) {
    setvbuf(stdout,nullptr,_IOLBF,0);
    try { return run(argc,argv); }
    catch(const std::exception &e) { std::fprintf(stderr,"client: %s\n",e.what()); return 1; }
}
