// Known-small native arithmetic and proof that the private executor hook is invoked.
#define main historical_c7_fixture_main
#include "c7_layer_reference.cpp"
#undef main
#include <atomic>
static std::atomic<unsigned> fixture_callbacks{0};
extern "C" void tesy_readiness_consume(const ggml_tensor *,int,int) { ++fixture_callbacks; }
int main() {
    backend_owner backend{ggml_backend_cpu_init()};require(backend.value,"CPU fixture backend");
    ggml_backend_cpu_set_n_threads(backend.value,8);owner g;g.ctx=context(16u*1024u*1024u);auto*c=g.ctx;
    auto*w=ggml_new_tensor_3d(c,GGML_TYPE_F32,32,16,4);auto*x=ggml_new_tensor_3d(c,GGML_TYPE_F32,32,1,1);
    auto*ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,1);
    auto*up=ggml_mul_mat_id(c,w,x,ids);auto*gate=ggml_mul_mat_id(c,w,x,ids);
    auto*act=ggml_swiglu_oai(c,gate,up,1.702f,7.0f);auto*graph=ggml_new_graph(c);ggml_build_forward_expand(graph,act);
    std::vector<ggml_tensor*>order;for(int i=0;i<ggml_graph_n_nodes(graph);i++)if(ggml_graph_node(graph,i)->op==GGML_OP_MUL_MAT_ID)order.push_back(ggml_graph_node(graph,i));
    require(order==std::vector<ggml_tensor*>{gate,up},"known-small actual graph order");
    ggml_set_output(gate);ggml_set_output(up);g.buffer=ggml_backend_alloc_ctx_tensors(c,backend.value);require(g.buffer,"fixture allocation");
    std::vector<float>weights(32*16*4),inputs(32,1);for(int e=0;e<4;e++)std::fill(weights.begin()+e*32*16,weights.begin()+(e+1)*32*16,float(e+1));
    const std::array<int32_t,4>expert_ids{3,0,2,1};ggml_backend_tensor_set(w,weights.data(),0,weights.size()*4);ggml_backend_tensor_set(x,inputs.data(),0,inputs.size()*4);ggml_backend_tensor_set(ids,expert_ids.data(),0,16);
    require(ggml_backend_graph_compute(backend.value,graph)==GGML_STATUS_SUCCESS,"fixture compute");
    auto result=tensor_get<float>(gate);for(int k=0;k<4;k++)for(int row=0;row<16;row++)require(result[k*16+row]==32*(expert_ids[k]+1),"independent F32 expected dot");
    require(fixture_callbacks>=64,"private executor hook did not run on eight-thread native MMID");
    std::cout<<"{\"hook_callbacks\":"<<fixture_callbacks.load()<<",\"known_small_independent_arithmetic\":\"PASS\"}\n";
}
