#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace fs = std::filesystem;
constexpr int width = 2880, experts = 128;
static void need(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
static std::array<std::atomic<int>, 5> counters{};  // rejected/accepted width 1 and 3, routed F32 dots
struct ggml_compute_params;

#ifdef COUNT_DISPATCH
extern "C" bool llamafile_sgemm(const ggml_compute_params *p, int64_t m, int64_t n, int64_t k,
    const void *a,int64_t lda,const void *b,int64_t ldb,void *c,int64_t ldc,int ta,int tb,int tc) {
    const int saved = errno;
    static auto fn=reinterpret_cast<decltype(&llamafile_sgemm)>(dlsym(RTLD_NEXT, "llamafile_sgemm"));
    if (!fn) std::abort();
    errno=saved;
    const bool ok=fn(p,m,n,k,a,lda,b,ldb,c,ldc,ta,tb,tc);
    const int returned=errno;
    if (m==experts && (n==1 || n==3) && k==width && ta==GGML_TYPE_F32 && tb==ta && tc==ta)
        counters[(n==1 ? 0 : 2)+(ok ? 1 : 0)].fetch_add(1,std::memory_order_relaxed);
    errno=returned;
    return ok;
}
extern "C" void ggml_vec_dot_f32(int n,float *s,size_t bs,const float *x,size_t bx,
                                  const float *y,size_t by,int nrc) {
    const int saved=errno;
    static auto fn=reinterpret_cast<decltype(&ggml_vec_dot_f32)>(dlsym(RTLD_NEXT, "ggml_vec_dot_f32"));
    if (!fn) std::abort();
    errno=saved;
    fn(n,s,bs,x,bx,y,by,nrc);
    const int returned=errno;
    if(n==width && nrc==1) counters[4].fetch_add(1,std::memory_order_relaxed);
    errno=returned;
}
#endif

static std::vector<float> read_input(const fs::path &file, size_t n) {
    need(fs::file_size(file)==n*4, "input length");
    std::vector<float> v(n);
    std::ifstream f(file,std::ios::binary);
    need(bool(f.read(reinterpret_cast<char *>(v.data()),n*4)), "input read");
    need(std::all_of(v.begin(),v.end(),[](float x){return std::isfinite(x);}),"finite input");
    return v;
}

static void save_rows(const fs::path &path, ggml_tensor *t, int d, int n) {
    need(t->ne[0]==d && t->ne[1]==n && t->ne[2]==1 && t->ne[3]==1 && t->nb[0]==4
         && t->nb[1]>=size_t(d)*4 && (t->type==GGML_TYPE_F32 || t->type==GGML_TYPE_I32),
         "output shape/stride");
    std::vector<uint32_t> row(d);
    need(!fs::exists(path), "new output file");
    std::ofstream f(path,std::ios::binary);
    for(int j=0;j<n;++j){
        ggml_backend_tensor_get(t,row.data(),j*t->nb[1],d*4);
        f.write(reinterpret_cast<const char *>(row.data()),d*4);
    }
    f.close(); need(f.good(),"write output");
}

static void graph(ggml_backend_t cpu, const std::string &tag, const fs::path &out,
        const std::vector<float> &weight, const std::vector<float> &bias, const float *x, int n) {
    auto *ctx=ggml_init({2u<<20,nullptr,true}); need(ctx,"context");
    auto *w=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,width,experts);
    auto *b=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,experts);
    auto *src=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,width,n);
    ggml_tensor *logits;
    if(tag=="split"){
        std::array<ggml_tensor*,3> parts;
        for(int j=0;j<3;++j){
            auto *slice=ggml_view_2d(ctx,src,width,1,src->nb[1],src->nb[1]*j);
            parts[j]=ggml_mul_mat(ctx,w,slice);
        }
        logits=ggml_concat(ctx,ggml_concat(ctx,parts[0],parts[1],1),parts[2],1);
    } else logits=ggml_mul_mat(ctx,w,src);
    auto *biased=ggml_add(ctx,logits,b);
    auto *ids=ggml_argsort_top_k(ctx,biased,4);
    auto *scores=ggml_reshape_3d(ctx,biased,1,experts,n);
    auto *gather=ggml_get_rows(ctx,scores,ids);
    auto *mix=ggml_soft_max(ctx,ggml_reshape_2d(ctx,gather,4,n));
    auto *g=ggml_new_graph(ctx); ggml_build_forward_expand(g,mix);
    auto *buf=ggml_backend_alloc_ctx_tensors(ctx,cpu);
    need(buf && ggml_backend_buffer_get_type(w->buffer)==ggml_backend_cpu_buffer_type()
         && ggml_is_contiguous(w) && ggml_is_contiguous(src)
         && w->nb[1]==width*4 && src->nb[1]==width*4 && ids->nb[1]==experts*4,
         "CPU backing or pitch");
    ggml_backend_tensor_set(w,weight.data(),0,weight.size()*4);
    ggml_backend_tensor_set(b,bias.data(),0,bias.size()*4);
    ggml_backend_tensor_set(src,x,0,size_t(width)*n*4);
    for(auto &v:counters) v.store(0,std::memory_order_relaxed);
    need(ggml_backend_graph_compute(cpu,g)==GGML_STATUS_SUCCESS,"CPU graph");
    ggml_backend_synchronize(cpu);
    std::cout<<tag;
    for(auto &v:counters) std::cout<<" "<<v.load(std::memory_order_relaxed);
    std::cout<<"\n";
    save_rows(out/(tag+".logits"),logits,experts,n);
    save_rows(out/(tag+".biased"),biased,experts,n);
    save_rows(out/(tag+".ids"),ids,4,n);
    save_rows(out/(tag+".mix"),mix,4,n);
    ggml_backend_buffer_free(buf);ggml_free(ctx);
}

static fs::path provider(void *symbol){
    Dl_info info{};need(dladdr(symbol,&info) && info.dli_fname,"provider");
    return fs::canonical(info.dli_fname);
}

int main(int argc,char **argv){
    try{
        need(argc==5,"fixture WEIGHT BIAS X3 OUTPUT");
        fs::path out=argv[4];need(fs::create_directory(out),"new output");
        auto weight=read_input(argv[1],width*experts);
        auto bias=read_input(argv[2],experts);
        auto x=read_input(argv[3],3*width);
        auto *cpu=ggml_backend_cpu_init();need(cpu,"CPU backend");
        ggml_backend_cpu_set_n_threads(cpu,8);
        std::cout<<"cpu "<<provider(reinterpret_cast<void*>(&ggml_backend_cpu_init)).string()<<"\n"
                 <<"base "<<provider(reinterpret_cast<void*>(&ggml_mul_mat)).string()<<"\n";
#ifdef COUNT_DISPATCH
        for(const char *name:{"llamafile_sgemm","ggml_vec_dot_f32"})
            std::cout<<name<<" "<<provider(dlsym(RTLD_NEXT,name)).string()<<"\n";
#endif
        for(int j=0;j<3;++j) graph(cpu,"ar"+std::to_string(j),out,weight,bias,x.data()+width*j,1);
        graph(cpu,"batch",out,weight,bias,x.data(),3);
        graph(cpu,"split",out,weight,bias,x.data(),3);
        std::swap_ranges(weight.begin(),weight.begin()+width,weight.begin()+width);
        graph(cpu,"mutant",out,weight,bias,x.data(),3);
        ggml_backend_free(cpu);
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
