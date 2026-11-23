// Metadata-only native model graph. No llama_decode, tensor_set/get, or weight reads.
#include "llama.h"
#include "llama-context.h"
#include "llama-graph.h"
#include "llama-memory.h"
#include "ggml-backend-impl.h"
#include "ggml-impl.h"
#include "ggml-cpu.h"
#include <iostream>
#include <stdexcept>
#include <map>
#include <vector>
#include <string>
#include <iomanip>
static void req(bool b,const char*s){if(!b)throw std::runtime_error(s);}
static std::string q(const char*s){std::string o="\"";for(;*s;s++){if(*s=='"'||*s=='\\')o+='\\';if((unsigned char)*s<32)throw std::runtime_error("control in name");o+=*s;}return o+'"';}
int main(int argc,char**argv){try{
 req(argc==2,"MODEL metadata path required");llama_backend_init();auto mp=llama_model_default_params();
 llama_model_tensor_buft_override ov[]={{R"(\.ffn_(up|down|gate|gate_up)_(ch|)exps)",ggml_backend_cpu_buffer_type()},{nullptr,nullptr}};
 mp.tensor_buft_overrides=ov;mp.n_gpu_layers=12;mp.no_alloc=true;mp.load_mode=LLAMA_LOAD_MODE_NONE;mp.use_extra_bufts=false;mp.check_tensors=false;
 auto*m=llama_model_load_from_file(argv[1],mp);req(m,"metadata model init");
 auto cp=llama_context_default_params();cp.n_ctx=8192;cp.n_batch=256;cp.n_ubatch=32;cp.n_seq_max=1;cp.n_threads=cp.n_threads_batch=8;cp.op_offload=false;cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;cp.type_k=cp.type_v=GGML_TYPE_F16;cp.swa_full=true;cp.offload_kqv=true;cp.kv_unified=true;
 auto*c=llama_init_from_model(m,cp);req(c,"metadata context init");
 std::cout<<"{\"schema\":\"tesy-native-scheduled-plan-v1\",\"no_alloc\":true,\"variants\":[";
 for(int n:{32,1}){
 auto mem=c->get_memory()->init_full();auto*g=c->graph_reserve(n,1,1,mem.get(),true);req(g,"native graph split");auto s=c->get_sched();
 std::map<ggml_tensor*,std::vector<ggml_tensor*>> deps;
 ggml_backend_graph_optimize_params p{[](void*u,ggml_tensor*t,ggml_tensor*until){(*static_cast<decltype(deps)*>(u))[until].push_back(t);},&deps};
 // Run the real backend optimizer without compute to identify fusion allocation witnesses.
 for(int a=0;a<ggml_graph_n_nodes(g);){auto*b=ggml_backend_sched_get_tensor_backend(s,ggml_graph_node(g,a));int e=a+1;while(e<ggml_graph_n_nodes(g)&&ggml_backend_sched_get_tensor_backend(s,ggml_graph_node(g,e))==b)e++;auto v=ggml_graph_view(g,a,e);if(b&&b->iface.graph_optimize)b->iface.graph_optimize(b,&v,&p);a=e;}
 std::cout<<(n==1?",":"")<<"{\"tokens\":"<<n<<",\"scheduler_splits\":"<<ggml_backend_sched_get_n_splits(s)<<",\"nodes\":[";
 for(int i=0;i<ggml_graph_n_nodes(g);i++){auto*t=ggml_graph_node(g,i);auto*b=ggml_backend_sched_get_tensor_backend(s,t);req(b,"missing backend");auto bt=ggml_backend_sched_get_buffer_type(s,b);
 std::cout<<(i?",":"")<<"{\"index\":"<<i<<",\"name\":"<<q(t->name)<<",\"op\":"<<q(ggml_op_desc(t))<<",\"backend\":"<<q(ggml_backend_name(b))<<",\"output_buffer\":"<<q(t->buffer?ggml_backend_buffer_name(t->buffer):ggml_backend_buft_name(bt))<<",\"dtype\":"<<q(ggml_type_name(t->type))<<",\"shape\":[";
 for(int j=0;j<4;j++)std::cout<<(j?",":"")<<t->ne[j];std::cout<<"],\"op_params\":[";for(size_t j=0;j<sizeof(t->op_params)/sizeof(int32_t);j++)std::cout<<(j?",":"")<<t->op_params[j];std::cout<<"],\"inputs\":[";
 bool first=true;for(int j=0;j<GGML_MAX_SRC;j++)if(auto*x=t->src[j]){auto*xb=ggml_backend_sched_get_tensor_backend(s,x);auto*buf=x->view_src?x->view_src->buffer:x->buffer;
 std::cout<<(first?"":",")<<"{\"name\":"<<q(x->name)<<",\"op\":"<<q(ggml_op_desc(x))<<",\"backend\":"<<q(xb?ggml_backend_name(xb):"UNKNOWN")<<",\"storage_buffer\":"<<q(buf?ggml_backend_buffer_name(buf):"UNALLOCATED")<<",\"dtype\":"<<q(ggml_type_name(x->type))<<"}";first=false;}
 std::cout<<"],\"optimizer_dependencies\":[";first=true;for(auto*x:deps[t]){std::cout<<(first?"":",")<<q(x->name);first=false;}std::cout<<"]}";}
 std::cout<<"]}";}
 std::cout<<"]}\n";llama_free(c);llama_model_free(m);llama_backend_free();return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
