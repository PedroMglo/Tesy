// Project observer prefix is assembled from the tested tiny client, excluding its graph code.
#define LLAMA_API_INTERNAL
#include "observe_prefix.hpp"
#include <sstream>
#include <array>

struct Identity {
    uint64_t dev,ino,bytes,mtime,ctime;
    bool operator==(const Identity &b) const {
        return dev==b.dev && ino==b.ino && bytes==b.bytes && mtime==b.mtime && ctime==b.ctime;
    }
};

static Identity stat_fd(int fd) {
    struct stat s{};
    must(fstat(fd,&s)==0 && S_ISREG(s.st_mode),"model FD");
    const auto ns=[](timespec t){return uint64_t(t.tv_sec)*1000000000+t.tv_nsec;};
    return {s.st_dev,s.st_ino,uint64_t(s.st_size),ns(s.st_mtim),ns(s.st_ctim)};
}

static void maps_at(const fs::path &dir,const char *name) {
    std::ifstream src("/proc/self/maps");
    std::ofstream dst(dir/name);
    dst<<src.rdbuf();
    dst.close();
    must(src.good() && bool(dst),"maps snapshot");
}

extern "C" ggml_status ggml_backend_graph_compute_async(ggml_backend_t, ggml_cgraph *) {
    std::fputs("UNEXPECTED_GRAPH_SUBMISSION\n", stderr);
    _exit(38);
}

static void census(llama_model *model,std::istream &plan) {
    std::string tag,name;
    uint64_t offset,bytes;
    int typ,count=0;
    std::array<int64_t,4> shape;
    while (plan>>tag) {
        must(tag=="T" && bool(plan>>name>>offset>>bytes>>typ>>shape[0]>>shape[1]>>shape[2]>>shape[3]),"plan row");
        const ggml_tensor *t=llama_get_model_tensor(model,name.c_str());
        must(t && t->data && t->buffer,"unmaterialized GGUF tensor");
        must(t->type==typ && ggml_nbytes(t)==bytes && std::equal(shape.begin(),shape.end(),t->ne),
             "GGUF geometry");
        auto host=ggml_backend_buffer_is_host(t->buffer);
        auto file=host?observe::file_offset(t->data,bytes):-1;
        std::printf("PLACE %s %d %" PRIu64 " %d %" PRId64 " %zu %s\n",name.c_str(),typ,bytes,int(host),
                    file,uintptr_t(t->data),ggml_backend_buffer_name(t->buffer));
        ++count;
    }
    must(plan.eof() && count==687,"plan cardinality");
}

// Public lookup returns one instance per name. The context map also contains the
// alternate bias used by the GPT-OSS graph for narrow batches.
static void bias_instances(llama_context *ctx) {
    const std::string suffix = "_exps.bias";
    for (const auto &[name, tensor] : llama_internal_get_tensor_map(ctx)) {
        if (name.size() < suffix.size() || name.compare(name.size() - suffix.size(), suffix.size(), suffix)) {
            continue;
        }
        must(tensor && tensor->buffer && tensor->data && tensor->type == GGML_TYPE_F32 &&
             tensor->ne[0] == 2880 && tensor->ne[1] == 128 && tensor->ne[2] == 1 && tensor->ne[3] == 1,
             "expert bias instance geometry");
        const bool host = ggml_backend_buffer_is_host(tensor->buffer);
        const size_t size = ggml_nbytes(tensor);
        const int64_t file = host ? observe::file_offset(tensor->data, size) : -1;
        std::printf("BIAS_INSTANCE %s %d %zu %d %" PRId64 " %zu %s\n", name.c_str(),
                    tensor->type, size, int(host), file, uintptr_t(tensor->data),
                    ggml_backend_buffer_name(tensor->buffer));
    }
}

static int probe(int argc,char **argv) {
    must(argc==4,"capacity-client ORIGINAL.GGUF PLAN.TSV NEW_NATIVE_DIR");
    const auto env=[](const char *name,const char *value){
        const char *v=std::getenv(name); return v && std::string(v)==value;
    };
    must(env("CUDA_VISIBLE_DEVICES","0") && env("GGML_CUDA_NO_PINNED","1") &&
         env("GGML_MOE_PREFETCH_AHEAD","0") && env("CUDA_CACHE_DISABLE","1") &&
         !std::getenv("GGML_CUDA_REGISTER_HOST") && !std::getenv("GGML_CUDA_ENABLE_UNIFIED_MEMORY"),
         "closed CUDA environment");
    std::ifstream plan(argv[2]);
    std::string tag,path;
    Identity id{};
    must(bool(plan>>tag>>path>>id.dev>>id.ino>>id.bytes>>id.mtime>>id.ctime) && tag=="MODEL" && path==argv[1]
         && path=="/home/pmglo/models/tesy-gpt-oss-120b-nvme/gpt-oss-120b-MXFP4.gguf" && id.bytes==63387346208ULL,
         "sealed plan first row");
    int fd=open(path.c_str(),O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    must(fd>=0 && stat_fd(fd)==id && !fstat(fd,&file_id),"initial model FD identity");
    must(mkdir(argv[3],0700)==0,"exclusive output directory");
    const fs::path dir(argv[3]);
    observe::witness=ik_vma::Inspect::capture(path.c_str(),file_id);
    handoff(false,'E');
    observe::phase=1;
    llama_backend_init();
    auto m=llama_model_default_params();
    m.n_gpu_layers=99; m.ncmoe=36; m.split_mode=LLAMA_SPLIT_MODE_LAYER; m.main_gpu=0;
    m.defer_experts=true; m.use_mmap=true; m.type_k=m.type_v=GGML_TYPE_F16;
    m.fit=m.use_mlock=m.use_thp=m.dry_run=m.repack_tensors=m.merge_qkv=m.merge_up_gate_exps=false;
    m.check_tensors=m.validate_quants=m.flash_attn=m.swa_compress=false;
    m.max_ctx_size=8192; m.n_ubatch=32; m.n_seq_max=1;
    loading=true;
    auto *model=llama_model_load_from_file(path.c_str(),m);
    loading=false;
    must(model && llama_n_vocab(model)==201088 && llama_n_layer(model)==36 && llama_model_n_embd(model)==2880,
         "target architecture");
    census(model,plan);
    maps_at(dir,"load.maps");
    handoff(false,'L');
    observe::phase=2;
    auto p=llama_context_default_params();
    p.n_ctx=8192;p.n_seq_max=1;p.n_batch=256;p.n_ubatch=32;p.n_threads=p.n_threads_batch=8;
    p.type_k=p.type_v=GGML_TYPE_F16;p.flash_attn=p.swa_compress=false;
    p.fused_moe_up_gate=p.fused_up_gate=p.fused_mmad=false;p.prefetch_experts=false;
    p.moe_cache_policy=LLAMA_MOE_CACHE_POLICY_CLASSLRU;p.moe_cache_cpu_share=0;
    p.moe_cache_size=3644ULL<<20;p.offload_kqv=true;p.cb_eval=nullptr;
    auto *ctx=llama_init_from_model(model,p);
    // At this pin llama_n_seq_max returns kv_self.size. The request above fixes one sequence.
    must(ctx && llama_n_ctx(ctx)==8192 && llama_n_seq_max(ctx)==8192 && llama_n_batch(ctx)==256
        && llama_n_ubatch(ctx)==32 && !ggml_moe_prefetch_enabled() && !llama_get_kv_cache_token_count(ctx)
        && !llama_get_kv_cache_used_cells(ctx),"context geometry or nonempty KV");
    bias_instances(ctx);
    const llama_context *contexts[]={ctx};
    const auto n=llama_memory_breakdown(contexts,1,nullptr,0,nullptr,0);
    must(n>=2 && n<=32,"memory rows");
    std::vector<llama_memory_row> rows(n);
    must(llama_memory_breakdown(contexts,1,nullptr,0,rows.data(),n)==n,"unstable memory rows");
    for(const auto &v:rows)
        std::printf("MEMORY %s\t%d\t%zu\t%zu\t%zu\t%zu\t%zu\t%zu\n",v.name,int(v.is_device),
                    v.model,v.context,v.compute,v.mmproj,v.total,v.free);
    std::puts("CONTEXT 8192 1 256 32 0 0");
    std::printf("KV_CELLS %u\n",llama_n_seq_max(ctx));
    maps_at(dir,"context.maps");
    handoff(false,'C');
    observe::phase=5;
    llama_free(ctx);llama_free_model(model);llama_backend_free();
    must(stat_fd(fd)==id && close(fd)==0,"final model FD identity");
    maps_at(dir,"freed.maps");
    handoff(false,'F');
    observe::phase=0;
    std::puts("STATUS COMPLETED_IK_CAPACITY_ZERO_FORWARD");
    return 0;
}

int main(int argc,char **argv) {
    setvbuf(stdout,nullptr,_IOLBF,0);
    try { return probe(argc,argv); }
    catch(const std::exception &e) { std::fprintf(stderr,"capacity: %s\n",e.what()); return 1; }
}
