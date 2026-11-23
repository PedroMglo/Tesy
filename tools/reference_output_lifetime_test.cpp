#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include <array>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

// Native allocator regression, without GGUF or model tensors. The downstream
// scale is allowed to reuse dead graph intermediates; outputs must survive it.
bool run(bool retain) {
    auto * c=ggml_init({2*1024*1024,nullptr,true});
    auto * input=ggml_new_tensor_2d(c,GGML_TYPE_F32,8,2);
    auto * ids=ggml_cont(c,ggml_argsort_top_k(c,input,4));
    auto * probs=ggml_reshape_3d(c,input,1,8,2);
    auto * mix=ggml_get_rows(c,probs,ids);
    mix=ggml_soft_max(c,ggml_reshape_2d(c,mix,4,2));
    mix=ggml_cont(c,ggml_reshape_3d(c,mix,1,4,2));
    auto * out=ggml_scale(c,mix,2.0f);
    if(retain){ggml_set_output(ids);ggml_set_output(mix);}
    ggml_set_output(out);
    auto * graph=ggml_new_graph(c);
    ggml_build_forward_expand(graph,ids);
    ggml_build_forward_expand(graph,mix);
    ggml_build_forward_expand(graph,out);
    auto backend=ggml_backend_cpu_init();
    ggml_backend_t backends[]={backend};
    auto sched=ggml_backend_sched_new(backends,nullptr,1,GGML_DEFAULT_GRAPH_SIZE,false,false);
    if(!ggml_backend_sched_alloc_graph(sched,graph))throw std::runtime_error("toy allocation");
    std::array<float,16> scores={0,1,2,3,4,5,6,7, 7,6,5,4,3,2,1,0};
    ggml_backend_tensor_set(input,scores.data(),0,sizeof(scores));
    if(ggml_backend_sched_graph_compute(sched,graph)!=GGML_STATUS_SUCCESS)throw std::runtime_error("toy compute");
    ggml_backend_sched_synchronize(sched);
    std::array<int32_t,8> observed_ids{};
    std::array<float,8> observed_mix{},output{};
    ggml_backend_tensor_get(ids,observed_ids.data(),0,sizeof(observed_ids));
    ggml_backend_tensor_get(mix,observed_mix.data(),0,sizeof(observed_mix));
    ggml_backend_tensor_get(out,output.data(),0,sizeof(output));
    const std::array<int32_t,8> expected_ids={7,6,5,4,0,1,2,3};
    bool good=observed_ids==expected_ids;
    for(int i=0;i<8;++i)good &= observed_mix[i]*2==output[i];
    ggml_backend_sched_free(sched);ggml_backend_free(backend);ggml_free(c);
    return good;
}
int main(){
    try{
        const bool unmarked=run(false),marked=run(true);
        std::cout<<"{\"unmarked_route_read_valid\":"<<(unmarked?"true":"false")
                 <<",\"marked_route_read_valid\":"<<(marked?"true":"false")<<"}\n";
        return !unmarked&&marked?0:1;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
