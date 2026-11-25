// A small real GGML scheduler/CPU backend. No Transformer, files or GPU data.
#include "routed_witness.h"
#include "ggml-cpu.h"
#include <fstream>
#include <iostream>
#include <memory>
#include <string>

static bool callback(ggml_tensor *t, bool ask, void *data) {
    return static_cast<routed_witness *>(data)->observe(t,ask);
}

static void graph(routed_witness &obs, int first, int n, bool outputs, const std::string &mutation) {
    auto ctx=ggml_init({2*1024*1024,nullptr,true});
    auto cpu=ggml_backend_cpu_init();
    ggml_backend_cpu_set_n_threads(cpu,1);
    auto sched=ggml_backend_sched_new(&cpu,nullptr,1,1024,false,false);
    auto g=ggml_new_graph_custom(ctx,1024,false);
    auto pos=ggml_new_tensor_1d(ctx,GGML_TYPE_I32,n);
    auto source=ggml_new_tensor_3d(ctx,GGML_TYPE_F32,4,1,n);
    auto pre=ggml_dup(ctx,source);
    ggml_set_name(pre,"Qcur-0"); // build_qkv also labels the pre-RoPE tensor Qcur-0
    routed_witness::need(!obs.observe(pre,true),"pre-RoPE node incorrectly subscribed");
    auto q=ggml_rope(ctx,pre,pos,4,0);
    ggml_set_name(q,"Qcur-0");
    ggml_build_forward_expand(g,q);
    std::vector<ggml_tensor *> inputs;
    auto selector=ggml_new_tensor_1d(ctx,GGML_TYPE_I32,1);
    ggml_tensor *residual=nullptr;
    for(int l=0;l<(outputs?36:35);++l) {
        if(mutation=="omit-layer" && l==17) continue;
        int rows=l==35?1:n;
        if(l==35) {
            residual=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,4,n);
            auto x=ggml_get_rows(ctx,residual,selector);
            auto y=ggml_get_rows(ctx,residual,selector);
            auto ffn=ggml_add(ctx,x,y);
            ggml_set_name(ffn,"ffn_inp-35");
            ggml_build_forward_expand(g,ffn);
        }
        auto scores=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,128,rows);
        inputs.push_back(scores);
        auto top=ggml_argsort_top_k(ctx,scores,4);
        ggml_set_name(top,("ffn_moe_topk-"+std::to_string(l)).c_str());
        ggml_build_forward_expand(g,top);
    }
    if (!outputs && mutation!="pruned-entirely") {
        auto *empty=ggml_view_2d(ctx,inputs.back(),4,0,128*sizeof(int32_t),0);
        // A zero-row final router may still occur in the scheduler's node list.
        auto *as_ids=ggml_cast(ctx,empty,GGML_TYPE_I32);
        ggml_set_name(as_ids,"ffn_moe_topk-35");
        ggml_build_forward_expand(g,as_ids);
    }
    // Input tensors must remain distinct until their initial values have
    // been consumed. Real model graph inputs are marked in the same way.
    ggml_set_input(pos); ggml_set_input(source);
    if(outputs) {ggml_set_input(residual); ggml_set_input(selector);}
    for(auto *p:inputs)ggml_set_input(p);
    ggml_backend_sched_set_eval_callback(sched,callback,&obs);
    routed_witness::need(ggml_backend_sched_alloc_graph(sched,g),"fixture allocation");
    std::array<int32_t,32> positions{};
    for(int i=0;i<n;++i)positions[i]=first+i;
    if(mutation=="wrong-position" && n>1)std::swap(positions[0],positions[1]);
    ggml_backend_tensor_set(pos,positions.data(),0,n*sizeof(int32_t));
    std::array<float,4*32> x{};
    ggml_backend_tensor_set(source,x.data(),0,n*4*sizeof(float));
    if(outputs) {
        int32_t last=mutation=="wrong-output" ? 0 : n-1;
        ggml_backend_tensor_set(selector,&last,0,sizeof(last));
        ggml_backend_tensor_set(residual,x.data(),0,n*4*sizeof(float));
    }
    for(size_t l=0;l<inputs.size();++l) {
        auto *p=inputs[l];
        std::vector<float> scores(128*p->ne[1]);
        for(int i=0;i<p->ne[1];++i) {
            const int original=(l==35?first+n-1:first+i);
            const int position=(mutation=="swapped-rows" && l==0 && n>1 && i<2)?first+1-i:original;
            for(int e=0;e<128;++e)scores[128*i+e]=static_cast<float>((e+3*position+5*l)%128);
            if(mutation=="swapped-ranks" && l==0) {
                int a=(127-3*position)%128; if(a<0)a+=128;
                std::swap(scores[128*i+a],scores[128*i+(a+127)%128]);
            }
        }
        ggml_backend_tensor_set(p,scores.data(),0,scores.size()*sizeof(float));
    }
    routed_witness::need(ggml_backend_sched_graph_compute(sched,g)==GGML_STATUS_SUCCESS,"CPU graph");
    ggml_backend_sched_free(sched); ggml_backend_free(cpu); ggml_free(ctx);
}

int main(int argc,char **argv) {
    try {
        routed_witness::need(argc==3,"mutation and new journal required");
        const std::string variant=argv[1];
        routed_witness obs;
        obs.begin_call(0,5);
        graph(obs,0,3,false,variant);
        graph(obs,3,2,true,variant);
        obs.end_call(); obs.finish();
        std::ofstream f(argv[2],std::ios::binary);
        f.write(reinterpret_cast<const char *>(obs.bytes.data()),obs.bytes.size());f.close();
        routed_witness::need(bool(f),"journal write");
        return 0;
    } catch(const std::exception &e) {std::cerr<<e.what()<<"\n";return 1;}
}
