// One true ub32 FFN tile. The router keeps its original C265 span of 153.
#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include "ggml-cpu.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <type_traits>
#ifndef TESY_C47_CPU_SKIP_PARKED
#error Build the manager and use a CPU runtime with the R0 parked-row implementation
#endif
#ifndef TESY_STORE_TESTING
#error This partial per-layer index is a fixture only
#endif
namespace fs=std::filesystem;
using json=nlohmann::json;
constexpr size_t slab=4406400,window=13221888,stride=13258752;
constexpr int width=2880,all=153,first=32,nt=32;
constexpr std::array<int,5> selected{45,49,57,60,98};
static void need(bool x,const char *reason){if(!x) throw std::runtime_error(reason);}
static ggml_context_ptr context(){ggml_context_ptr ctx(ggml_init({16ULL<<20,nullptr,true})); need(bool(ctx),"GGML context");return ctx;}
template<class T> static std::vector<T> read(const fs::path &p,size_t count){
    need(fs::file_size(p)==count*sizeof(T),"input length"); std::ifstream f(p,std::ios::binary);std::vector<T> v(count);
    need(bool(f.read(reinterpret_cast<char *>(v.data()),count*sizeof(T))),"input read");return v;
}
template<class T> static std::vector<T> values(ggml_tensor *t){
    need(ggml_is_contiguous(t),"expected complete contiguous output"); std::vector<T> v(ggml_nelements(t));
    need(v.size()*sizeof(T)==ggml_nbytes(t),"output type/bytes"); ggml_backend_tensor_get(t,v.data(),0,ggml_nbytes(t));return v;
}
template<class T> static void equal(const std::vector<T>&observed,const std::vector<T>&expected,const char *reason){
    need(observed.size()==expected.size() && !std::memcmp(observed.data(),expected.data(),observed.size()*sizeof(T)),reason);
    if constexpr(std::is_floating_point_v<T>) for(T x:observed)need(std::isfinite(x),"nonfinite");
}
template<class T> static void put(ggml_tensor *tensor,const std::vector<T> &v){
    need(ggml_nbytes(tensor)==v.size()*sizeof(T),"input tensor type/bytes");ggml_backend_tensor_set(tensor,v.data(),0,ggml_nbytes(tensor));
}
// Exact two functions copied from the SHA-pinned block_expert_reuse_operator.cpp at build time.
#include "pairs-finish.inc"
#include "slot_witness.h"
struct Inputs {std::vector<float> activation,weights;std::vector<int> ids;};
static Inputs routing(const fs::path &p,ggml_backend_t cpu){
    auto ctx=context();auto *c=ctx.get(); auto *x=ggml_new_tensor_2d(c,GGML_TYPE_F32,width,all);
    auto *router=ggml_new_tensor_2d(c,GGML_TYPE_F32,width,128);auto *bias=ggml_new_tensor_1d(c,GGML_TYPE_F32,128);
    auto *logits=ggml_mul_mat(c,router,x);auto *biased=ggml_add(c,logits,bias);
    auto *ids=ggml_cont(c,ggml_argsort_top_k(c,biased,4)); auto *w=ggml_get_rows(c,ggml_reshape_3d(c,biased,1,128,all),ids);
    w=ggml_cont(c,ggml_reshape_3d(c,ggml_soft_max(c,ggml_reshape_2d(c,w,4,all)),1,4,all));
    auto *g=ggml_new_graph(c); ggml_build_forward_expand(g,ids); ggml_build_forward_expand(g,w);
    ggml_backend_buffer_ptr memory(ggml_backend_alloc_ctx_tensors(c,cpu));need(bool(memory),"router allocation");
    Inputs in;in.activation=read<float>(p/"attn_post_norm-0.bin",width*all);put(x,in.activation);
    put(router,read<float>(p/"router.weight",width*128));put(bias,read<float>(p/"router.bias",128));
    need(ggml_backend_graph_compute(cpu,g)==GGML_STATUS_SUCCESS,"router compute");ggml_backend_synchronize(cpu);
    equal(values<float>(logits),read<float>(p/"ffn_moe_logits-0.bin",128*all),"all pre-bias router logits");
    equal(values<float>(biased),read<float>(p/"ffn_moe_logits_biased-0.bin",128*all),"all biased router logits");
    in.ids=values<int>(ids);in.weights=values<float>(w);
    equal(in.ids,read<int>(p/"ffn_moe_topk-0.bin",4*all),"all ordered IDs");
    equal(in.weights,read<float>(p/"ffn_moe_weights_softmax-0.bin",4*all),"all routing weights");return in;
}
static std::string provider(void *symbol) {
    Dl_info info{}; need(dladdr(symbol,&info) && info.dli_fname,"missing runtime provider");
    return fs::canonical(info.dli_fname).string();
}
static void counterexamples(){
    int tensor,copy,buffer,other; std::array<uint8_t,64> data{};
    auto source=[&](int *t,const void *ptr,int *buf,size_t pitch){
        return same_operand(t,&tensor,ptr,data.data(),buf,&buffer,pitch,window);};
    need(source(&tensor,data.data(),&buffer,window),"positive operand");
    need(!source(&copy,data.data(),&buffer,window) && !source(&tensor,data.data()+1,&buffer,window) &&
         !source(&tensor,data.data(),&other,window) && !source(&tensor,data.data(),&buffer,slab),"missed copy/stride mutation");
    Audit a;a.seen_ids.fill(1);a.seen_masks.fill(1);for(auto &seen:a.seen_mm)seen.fill(1);
    need(complete(a),"positive wave coverage");a.seen_mm[7][2]=0;need(!complete(a),"missed final parked projection");
    std::vector<int> ids{45,49,57,60},reordered{49,45,57,60};bool rejected=false;
    try{equal(ids,reordered,"wrong rank");}catch(const std::runtime_error&){rejected=true;}need(rejected,"rank order mutation");
}
template<class T> static std::vector<T> tile(const std::vector<T>&v,size_t per_position){
    return {v.begin()+first*per_position,v.begin()+(first+nt)*per_position};
}
static json run(const fs::path &p,const std::string &mode,const fs::path &output){
    static_assert(sizeof(int)==4 && sizeof(float)==4);
    need(mode=="DENSE"||mode=="STAGED"||mode=="DIRECT","invalid arm");
    const char *env=std::getenv("TESY_PACKED_CPU_SLOTS");
    need(mode=="DENSE"?!env:(env && env==std::string(mode=="DIRECT"?"direct":"staged")),"layout environment");
    need(std::getenv("TESY_CPU_WAVE_SKIP_PARKED") && std::string(std::getenv("TESY_CPU_WAVE_SKIP_PARKED"))=="1","parked CPU mode");
    ggml_backend_ptr backend(ggml_backend_cpu_init());need(bool(backend),"CPU init");ggml_backend_cpu_set_n_threads(backend.get(),8);
    auto in=routing(p,backend.get());const auto ids=tile(in.ids,4);
    const std::set<int> union_ids(ids.begin(),ids.end());need(union_ids==std::set<int>(selected.begin(),selected.end()),"selected union");
    std::set<std::array<int,4>> tuples;for(int i=0;i<nt;++i){std::array<int,4> r;std::copy_n(ids.begin()+4*i,4,r.begin());tuples.insert(r);}
    need(tuples.size()==7,"rank pattern count");
    auto meta=context(); auto biases=context();std::array<ggml_tensor*,6> t{};
    // pairs() takes gate,up,down; native layer registration and on-disk components are gate,down,up.
    const int order[]={0,2,1};const char *roles[]={"gate","up","down"}; Audit observed; observed.cpu=backend.get();
    observed.slot_stride=mode=="DENSE"?slab:window;observed.direct=mode=="DIRECT";observed.slots.fill(-1);
    std::copy(ids.begin(),ids.end(),observed.logical.begin());
    json info;{std::ifstream f(p/"prepare.json");f>>info;need(bool(f)&&info.at("status")=="PASS_PREPARED_REAL_TILE","input receipt");}
    llama_moe_stream manager(1,40,4,true);observed.manager=&manager;
    for(int k=0;k<3;++k){const int i=order[k];auto *m=ggml_new_tensor_3d(meta.get(),GGML_TYPE_MXFP4,width,width,128);
        ggml_format_name(m,"blk.0.ffn_%s_exps.weight",roles[i]);t[i]=manager.create_cache_tensor(0,ggml_backend_cpu_buffer_type(),m,0,info.at("weight_bases").at(k).get<size_t>());
        observed.weights[k]=t[i];t[i+3]=ggml_new_tensor_2d(biases.get(),GGML_TYPE_F32,width,128);}
    manager.alloc_bufs(false);observed.layer=manager.layer(0);
    ggml_backend_buffer_ptr biasmem(ggml_backend_alloc_ctx_tensors(biases.get(),backend.get()));need(bool(biasmem),"bias buffers");
    for(int k=0;k<3;++k){auto *w=observed.weights[k];observed.addresses[k]=static_cast<uint8_t *>(w->data);observed.buffers[k]=w->buffer;
        need(w->nb[2]==observed.slot_stride && ggml_is_contiguous(w)==(mode=="DENSE"),"weight geometry");
        if(mode!="DENSE") need(w->view_src==observed.weights[0]->view_src && w->view_src && w->buffer==observed.buffers[0] &&
            observed.addresses[k]==observed.addresses[0]+k*slab && uintptr_t(observed.addresses[0])%4096==0,"aligned bank geometry");
        put(t[3+order[k]],read<float>(p/(std::string(roles[order[k]])+".bias"),width*128));}
    manager.expert_store=std::make_unique<tesy_expert_store>();auto &store=*manager.expert_store;
    store.data.open_file((p/"pack.bin").c_str());observed.fd=store.data.descriptor();need(store.data.file_size()==selected.size()*stride,"pack size");
    for(auto &entry:store.entries[0])entry.offset=UINT64_MAX;
    for(size_t i=0;i<selected.size();++i){auto &e=store.entries[0][selected[i]];e.offset=i*stride;e.relative={0,slab,2*slab};}
    need(manager.workers.empty() && manager.q_demand.empty() && observed.layer->expert_slot.empty(),"cold entry");
    auto ctx=context();auto *c=ctx.get();auto *g=ggml_new_graph_custom(c,1024,false);
    auto *x=ggml_new_tensor_2d(c,GGML_TYPE_F32,width,nt);auto *r=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,nt);auto *mix=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,4,nt);
    for(auto *l:{x,r,mix})ggml_set_input(l);ggml_tensor *sum=nullptr;
    for(int w=0;w<8;++w){ggml_tensor *args[]={r,sum?ggml_view_1d(c,sum,1,0):nullptr};auto *ud=observed.layer->wave_userdata(w,18);
        auto *physical=ggml_custom_4d(c,GGML_TYPE_I32,4,nt,1,1,args,sum?2:1,llama_moe_stream_wave_ids,1,ud);observed.wave_ids.emplace(physical,w);
        auto *value=pairs(c,t,x,r,physical);ggml_tensor *mo[]={r,physical};
        auto *mask=ggml_custom_4d(c,GGML_TYPE_F32,1,4,nt,1,mo,2,llama_moe_stream_wave_mask,1,ud);observed.masks.emplace(mask,w);
        value=ggml_mul(c,value,mask);sum=sum?ggml_add(c,sum,value):value;ggml_build_forward_expand(g,sum);
        for(int n=0;n<ggml_graph_n_nodes(g);++n){auto *node=ggml_graph_node(g,n);if(node->op!=GGML_OP_MUL_MAT_ID||node->src[2]!=physical)continue;
            auto it=std::find(observed.weights.begin(),observed.weights.end(),node->src[0]);need(it!=observed.weights.end(),"unknown MMID source");
            observed.mmids.emplace(node,std::make_pair(w,int(it-observed.weights.begin())));}}
    auto *out=finish(c,g,sum,mix);need(observed.mmids.size()==24,"graph MMID coverage");
    auto *cpu=backend.get();ggml_backend_sched_ptr scheduler(ggml_backend_sched_new(&cpu,nullptr,1,1024,false,false));need(bool(scheduler),"scheduler");
    observed.sched=scheduler.get();ggml_backend_sched_set_eval_callback(scheduler.get(),observe,&observed);
    need(ggml_backend_sched_alloc_graph(scheduler.get(),g),"FFN graph allocation");
    put(x,tile(in.activation,width));put(r,ids);put(mix,tile(in.weights,4));audit=&observed;
    need(ggml_backend_sched_graph_compute(scheduler.get(),g)==GGML_STATUS_SUCCESS,"FFN compute");ggml_backend_sched_synchronize(scheduler.get());
    const auto found=values<float>(out);equal(found,tile(read<float>(p/"ffn_moe_out-0.bin",all*width),width),"full FFN tile");
    need(complete(observed),"incomplete wave or projection");
    {std::lock_guard<std::mutex> lock(manager.mtx);need(!manager.load_failed && manager.q_demand.empty() && manager.workers.size()==4 && observed.layer->expert_slot.size()==5 &&
        manager.stats.n_store_loads==5 && manager.stats.n_store_read_bytes==5*3*int64_t(slab) && manager.stats.n_wave_calls==8 && manager.stats.n_waves_run==1,"final manager counters");
        for(int e:selected){int s=observed.slots[e];need(s>=0 && observed.reads[e]==1 && observed.copies[e]==(observed.direct?0:3) &&
            observed.layer->slot_state[s]==LLAMA_MOE_STREAM_SLOT_RESIDENT && !observed.layer->slot_claimed[s] && observed.layer->slot_gen[s]==1,"final slot identity");}}
    need(!observed.invalid,"observer rejected source/slot/worker identity");audit=nullptr;
    {std::ofstream f(output/"tile.f32",std::ios::binary);need(bool(f.write(reinterpret_cast<const char*>(found.data()),found.size()*4)),"output write");}
    return {{"arm",mode},{"router_positions",153},{"ffn_positions",32},{"full_ffn_values",found.size()},{"graph_waves",8},{"active_waves",1},
        {"mmid_nodes_observed",24},{"unique_loads",5},{"weight_sets",observed.direct?0:15},{"compute_backend","CPU"},
        {"roles",{"gate","down","up"}},{"pread_bytes",observed.pread_bytes},{"logical_weight_bytes",5*3*slab},
        {"dio_offset_alignment",store.data.offset_alignment()},{"workers_before_destructor",manager.workers.size()},
        {"providers",{{"cpu",provider(reinterpret_cast<void *>(&ggml_backend_cpu_init))},{"base",provider(reinterpret_cast<void *>(&ggml_backend_sched_graph_compute))}}}};
}
int main(int argc,char **argv){try{
    if(argc==2 && std::string(argv[1])=="--self-test"){counterexamples();std::cout<<"PASS_C291_TILE_COUNTEREXAMPLES\n";return 0;}
    need(argc==4,"usage: layer INPUT_DIR DENSE|STAGED|DIRECT NEW_OUTPUT_DIR");
    fs::path out(argv[3]);need(fs::create_directory(out),"exclusive output");auto receipt=run(argv[1],argv[2],out);
    // In the sealed C291 destructor every one of its four std::threads joins before run returns.
    receipt["manager_destructor_returned"]=true;
    receipt["joined_workers"]=receipt.at("workers_before_destructor");
    receipt["status"]="PASS_C291_CPU0_ROUTED_TILE";std::cout<<receipt.dump()<<'\n';return 0;
}catch(const std::exception &e){std::cerr<<"FAIL_C291_CPU0_TILE "<<e.what()<<'\n';return 1;}}
