// Movement-only affine operator; no target model or authoritative routing.
#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "json.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <numeric>
#include <thread>
#include <vector>
using json=nlohmann::ordered_json;
void require(bool v,const char *s){if(!v)throw std::runtime_error(s);}
std::vector<float> read(const std::filesystem::path &p,size_t n){
    require(std::filesystem::file_size(p)==n*4,"bounded exact F32 array");
    std::vector<float> x(n);std::ifstream f(p,std::ios::binary);f.read((char*)x.data(),n*4);
    require(bool(f),"F32 short read");for(float a:x)require(std::isfinite(a),"nonfinite F32 value");return x;
}
struct affine {
    ggml_context *ctx=nullptr;ggml_backend_t cpu=nullptr;ggml_backend_buffer_t buffer=nullptr;
    ggml_tensor *input=nullptr,*output=nullptr;ggml_cgraph *graph=nullptr;
    affine(const float *w,const float *b,ggml_backend_t shared):cpu(shared){
        const size_t meta=ggml_graph_overhead()+16*ggml_tensor_overhead()+65536;
        require(meta<=1024*1024,"bounded affine metadata");ctx=ggml_init({meta,nullptr,true});require(ctx,"affine context");
        auto *weight=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,128,128);
        auto *bias=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,128);
        input=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,128,1);
        output=ggml_add(ctx,ggml_mul_mat(ctx,weight,input),bias);ggml_set_output(output);
        graph=ggml_new_graph(ctx);ggml_build_forward_expand(graph,output);
        buffer=ggml_backend_alloc_ctx_tensors(ctx,cpu);require(buffer,"affine tensor allocation");
        ggml_backend_tensor_set(weight,w,0,128*128*4);ggml_backend_tensor_set(bias,b,0,128*4);
    }
    ~affine(){if(buffer)ggml_backend_buffer_free(buffer);if(ctx)ggml_free(ctx);}
    std::array<float,128> score(const float *x){
        ggml_backend_tensor_set(input,x,0,128*4);
        require(ggml_backend_graph_compute(cpu,graph)==GGML_STATUS_SUCCESS,"native affine compute");ggml_backend_synchronize(cpu);
        std::array<float,128> y{};ggml_backend_tensor_get(output,y.data(),0,128*4);
        for(float a:y)require(std::isfinite(a),"nonfinite native affine output");return y;
    }
};
int main(int argc,char **argv){try{
    require(argc==4,"usage WEIGHTS_DIR ORIGINAL_SCORE_ROOT NEW_OUTPUT");
    auto dir=std::filesystem::path(argv[1]),root=std::filesystem::path(argv[2]),out=std::filesystem::path(argv[3]);
    require(!std::filesystem::exists(out),"new native output required");
    auto w=read(dir/"weight.f32",23*128*128),b=read(dir/"bias.f32",23*128);
    auto file=root/"prediction-scores.f32";
    if(!std::filesystem::exists(file))file=root/"early-native-scores.f32";
    const auto size=std::filesystem::file_size(file);require(size%(23*128*4)==0,"complete score rows");
    const size_t n=size/(23*128*4);require(n>=16&&n<=128,"native frame bound");auto x=read(file,n*23*128);
    auto cpu=ggml_backend_cpu_init();require(cpu,"native CPU backend");ggml_backend_cpu_set_n_threads(cpu,8);
    std::array<std::unique_ptr<affine>,23> ops;
    for(int i=0;i<23;i++)ops[i]=std::make_unique<affine>(w.data()+i*128*128,b.data()+i*128,cpu);
    std::vector<float> y(x.size());std::vector<std::array<double,4>> timings(n*23);
    std::vector<int> selected(n*23*4);
    for(int rep=0;rep<4;rep++)for(size_t row=0;row<n*23;row++){
        const auto begin=std::chrono::steady_clock::now();auto v=ops[row%23]->score(x.data()+row*128);
        std::array<int,128> rank{};std::iota(rank.begin(),rank.end(),0);
        std::stable_sort(rank.begin(),rank.end(),[&](int a,int c){return v[a]>v[c];});
        const auto end=std::chrono::steady_clock::now();timings[row][rep]=std::chrono::duration<double,std::micro>(end-begin).count();
        if(rep==0){std::copy(v.begin(),v.end(),y.begin()+row*128);std::copy_n(rank.begin(),4,selected.begin()+row*4);}
        else require(std::equal(v.begin(),v.end(),y.begin()+row*128),"deterministic native affine changed");
    }
    std::filesystem::create_directory(out);
    std::ofstream f(out/"corrected-scores.f32",std::ios::binary);f.write((char*)y.data(),y.size()*4);require(bool(f),"native output write");f.close();
    json costs=json::array();for(auto t:timings){std::sort(t.begin(),t.end());costs.push_back((t[1]+t[2])/2);}
    json result={{"schema","native-score-affine-evaluation-v1"},{"status","PASS_NATIVE_AFFINE_EVALUATION"},{"threads",8},{"frames",n},{"layers",{2,24}},{"input",file.string()},{"repetitions",4},{"weights_bytes",(w.size()+b.size())*4},{"score_cost_median_us",costs},{"top4_ids",selected},{"all_repeats_bitwise",true},{"scope","Native isolated auxiliary operator, no target model/IO/contention. Add to original measured feature costs only in conditional service scenario; not integrated latency."}};
    std::ofstream o(out/"result.json");o<<result.dump(2)<<'\n';require(bool(o),"native result write");o.close();
    std::this_thread::sleep_for(std::chrono::seconds(5));
    for(auto &op:ops)op.reset();ggml_backend_free(cpu);
    std::cout<<"PASS_NATIVE_AFFINE_EVALUATION\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
