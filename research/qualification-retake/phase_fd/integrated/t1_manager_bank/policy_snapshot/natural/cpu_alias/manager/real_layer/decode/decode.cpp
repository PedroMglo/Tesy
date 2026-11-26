// Partial C270 R0 state at position 189, shape 1. The fixture reuses C291's live worker and remap.
#include "lease.h"
#include "c291-expert-store.h"
#include "ggml-cpu.h"
#include <openssl/sha.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <vector>

namespace fs=std::filesystem;
using json=nlohmann::json;
constexpr int width=2880;
constexpr size_t slab=4406400, window=13221888, stride=13258752, capacity=((40*window+16)/17)*17;
constexpr size_t span=((capacity+4095)/4096)*4096;
const std::array<int,4> keys{28,24,8,16}, dest{3,14,6,35}, gens{6,6,5,4};
const std::array<int,3> to_math{0,2,1};
const std::array<const char *,3> roles{"gate","down","up"};

void need(bool ok,const char *reason){if(!ok)throw std::runtime_error(reason);}
template<class T> std::vector<T> read(const fs::path &p,size_t count) {
    need(fs::file_size(p)==count*sizeof(T),"input dimensions");std::vector<T> v(count);
    std::ifstream f(p,std::ios::binary);need(bool(f.read(reinterpret_cast<char*>(v.data()),count*sizeof(T))),"input bytes");return v;
}
template<class T> void put(ggml_tensor *t,const std::vector<T> &v) {
    need(ggml_nbytes(t)==v.size()*sizeof(T),"tensor shape");ggml_backend_tensor_set(t,v.data(),0,v.size()*sizeof(T));
}
template<class T> std::vector<T> get(ggml_tensor *t){
    need(ggml_is_contiguous(t),"contiguous output");std::vector<T> v(ggml_nelements(t));
    need(ggml_nbytes(t)==v.size()*sizeof(T),"output type");ggml_backend_tensor_get(t,v.data(),0,v.size()*sizeof(T));return v;
}
template<class T> void equal(const std::vector<T>&a,const std::vector<T>&b){
    need(a.size()==b.size() && !std::memcmp(a.data(),b.data(),a.size()*sizeof(T)),"router/IDs bitwise");
}
std::string digest(const void *p,size_t size){
    unsigned char h[32];need(SHA256(static_cast<const unsigned char*>(p),size,h)!=nullptr,"SHA256");
    char hex[65];for(int i=0;i<32;++i)std::snprintf(hex+2*i,3,"%02x",h[i]);return hex;
}
json fstat_id(int fd){
    struct stat st{};need(fstat(fd,&st)==0,"fstat");
    auto ns=[](timespec ts){return int64_t(ts.tv_sec)*1000000000+ts.tv_nsec;};
    return {{"dev",st.st_dev},{"inode",st.st_ino},{"size_bytes",st.st_size},
            {"mtime_ns",ns(st.st_mtim)},{"ctime_ns",ns(st.st_ctim)}};
}
void *map_at(void *at,size_t n,int prot,int flags,int fd){
    auto *p=mmap(at,n,prot,flags,fd,0);need(p!=MAP_FAILED && (!at || p==at),"arena mapping");return p;
}
struct Backing {
    int fd;
    explicit Backing(size_t bytes):fd(memfd_create("tesy-C270-record",MFD_CLOEXEC)){
        need(fd>=0 && ftruncate(fd,bytes)==0,"backing allocation");
    }
    ~Backing(){close(fd);}
};
using Ref=std::shared_ptr<Backing>;
struct Mapping {
    uint8_t *p;size_t n;
    Mapping(size_t size,int prot,int fd):p(static_cast<uint8_t*>(map_at(nullptr,size,prot,fd<0?MAP_PRIVATE|MAP_ANONYMOUS:MAP_SHARED,fd))),n(size){}
    ~Mapping(){munmap(p,n);}
    Mapping(const Mapping&)=delete;
};
struct Context {
    std::string mode;bool decode=false; int fd=-1;
    llama_moe_stream *mgr=nullptr;
    uint8_t *base=nullptr;
    std::map<int,json> records;
    std::array<Ref,40> installed{};
    std::map<int,Ref> retained;
    std::array<ggml_tensor*,6> tensors{};
    std::mutex counters;
    int setup_reads=0,decode_reads=0;
    size_t copies=0;
    int victim_constraints=0;
    json differences=json::array();
} state;
thread_local Ref pending;

int decode_allowed_slot() {return state.decode?14:-1;}
bool lease_prepare(const llama_moe_stream_work &w){
    need(!pending && w.sl==state.mgr->layer(0),"worker identity");
    const auto &record=state.records.at(w.expert);
    need(record.at("capture_slot")==w.slot && record.at("capture_generation")==w.gen &&
         (w.expert==24)==state.decode,"setup or decode binding");
    auto file=std::make_shared<Backing>(stride);
    {
        Mapping dst(stride,PROT_READ|PROT_WRITE,file->fd);
        const auto off=record.at("record_offset").get<off_t>();
        need(record.at("record_bytes")==stride && off>=0 && size_t(off)%stride==0,"index offset");
        const auto n=pread(state.fd,dst.p,stride,off);
        need(n==ssize_t(stride),"incomplete expert record");
        for(int k=0;k<6;++k){
            const auto &component=record.at("components").at(k);
            const size_t start=component.at("packed_relative_offset"), bytes=component.at("size_bytes");
            need(bytes==(k<3?slab:size_t(4*width)) && start<=stride-bytes &&
                 component.at("pack_absolute_offset")==off_t(off+start) &&
                 (k>=3 || start==size_t(k)*slab) && digest(dst.p+start,bytes)==component.at("sha256"),
                 "expert payload digest or layout");
            if(k>=3){
                // Independent writable rows, published before this worker releases the manager claim.
                auto *bias=state.tensors[3+to_math[k-3]];
                ggml_backend_tensor_set(bias,dst.p+start,size_t(w.expert)*width*4,bytes);
            }
        }
    }
    need(ftruncate(file->fd,window)==0,"drop on-disk biases beyond backing");
    std::lock_guard<std::mutex> g(state.counters);
    if(state.decode){++state.decode_reads;pending=file;return true;}
    ++state.setup_reads;state.retained.emplace(w.expert,file);
    if(state.mode=="COPY"){
        pending=std::make_shared<Backing>(window);
        Mapping src(window,PROT_READ,file->fd), dst(window,PROT_WRITE,pending->fd);
        std::memcpy(dst.p,src.p,window);state.copies+=window;
    }else pending=file;
    return true;
}
void lease_wait(const llama_moe_stream_work &,std::unique_lock<std::mutex> &,bool){}
void lease_install(const llama_moe_stream_work &w){
    need(pending && !state.installed[w.slot],"single fixed-VA bind");
    map_at(state.base+size_t(w.slot)*window,window,PROT_READ,MAP_SHARED|MAP_FIXED,pending->fd);
    state.installed[w.slot]=pending;
}
void lease_end(){pending.reset();}

#include "pairs-finish.inc"

static json snapshot(llama_moe_stream_layer &l){
    json list=json::array();
    for(int e:keys){
        auto it=l.expert_slot.find(e);
        if(it==l.expert_slot.end()){list.push_back({e,-1,0});continue;}
        int s=it->second;need(l.slot_expert[s]==e && l.slot_state[s]==LLAMA_MOE_STREAM_SLOT_RESIDENT &&
              !l.slot_claimed[s] && state.installed[s],"snapshot binding");
        list.push_back({e,s,l.slot_gen[s]});
    }
    return list;
}
struct Witness {
    ggml_backend_sched_t sched;ggml_backend_t cpu;
    ggml_tensor *remap,*ids;
    std::vector<int> physical;
    int remaps=0,mmids=0,biases=0;
};
void inspect_components(){
    for(int rank=0;rank<4;++rank){
        const int e=keys[rank],slot=dest[rank];const auto &rec=state.records.at(e);
        for(int k=0;k<6;++k){
            auto *t=state.tensors[to_math[k%3]+(k<3?0:3)];
            const auto *p=static_cast<const uint8_t*>(t->data)+(k<3?size_t(slot)*window:size_t(e)*width*4);
            const size_t bytes=k<3?slab:width*4;
            const auto got=digest(p,bytes);
            if(got==rec.at("components").at(k).at("sha256"))continue;
            state.differences.push_back({e,k});
            need(state.mode=="WRONG" && k==0 && rank<2 &&
                 got==state.records.at(keys[1-rank]).at("components").at(k).at("sha256"),"wrong expert/role digest");
        }
    }
}
bool observe(ggml_tensor *t,bool ask,void *ctx){
    auto &w=*static_cast<Witness*>(ctx);
    const bool target=t==w.remap || t->op==GGML_OP_MUL_MAT_ID || t->op==GGML_OP_ADD_ID;
    if(!target || ask)return target;
    need(ggml_backend_sched_get_tensor_backend(w.sched,t)==w.cpu,"wrong compute backend");
    if(t==w.remap) {
        need(w.remaps++==0 && w.mmids==0,"remap before weights");
        w.physical=get<int>(t);
        equal(w.physical,std::vector<int>(dest.begin(),dest.end()));
        if(state.mode=="WRONG"){
            // Test-only fault. The scheduler has synchronized the remap and has not run an MMID.
            Mapping a(window,PROT_READ|PROT_WRITE,state.installed[dest[0]]->fd);
            Mapping b(window,PROT_READ|PROT_WRITE,state.installed[dest[1]]->fd);
            std::swap_ranges(a.p,a.p+slab,b.p);
        }
        inspect_components();
    }else if(t->op==GGML_OP_MUL_MAT_ID){
        ++w.mmids;need(w.remaps==1 && t->src[2]==w.remap,"physical ranks provenance");
        auto *wt=t->src[0];int k=0;
        while(k<3 && state.tensors[to_math[k]]!=wt)++k;
        need(k<3 && wt->view_src && wt->nb[2]==window && wt->data==state.base+k*slab &&
             ggml_backend_buffer_get_base(wt->buffer)==state.base &&
             ggml_backend_buffer_get_usage(wt->buffer)==GGML_BACKEND_BUFFER_USAGE_WEIGHTS &&
             std::string(ggml_backend_buffer_name(wt->buffer))=="CPU_Mapped","copied weight operand");
    }else{
        ++w.biases;need(t->src[2]==w.ids && std::find(state.tensors.begin()+3,state.tensors.end(),
             t->src[1])!=state.tensors.end(),"bias logical lookup");
    }
    return true;
}
using F=std::vector<float>;
using I=std::vector<int>;
ggml_context_ptr context(){
    ggml_context_ptr ctx(ggml_init({16u<<20,nullptr,true}));need(bool(ctx),"GGML context");return ctx;
}
struct Input{F x,weights;I ids;};
Input route(const fs::path &prefill,const fs::path &ref,ggml_backend_t cpu){
    auto ctx=context();auto *c=ctx.get();
    auto *x=ggml_new_tensor_2d(c,GGML_TYPE_F32,width,1);
    auto *wt=ggml_new_tensor_2d(c,GGML_TYPE_F32,width,128);
    auto *bias=ggml_new_tensor_1d(c,GGML_TYPE_F32,128);
    auto *raw=ggml_mul_mat(c,wt,x);auto *probs=ggml_add(c,raw,bias);
    auto *ids=ggml_cont(c,ggml_argsort_top_k(c,probs,4));
    auto *rows=ggml_get_rows(c,ggml_reshape_3d(c,probs,1,128,1),ids);
    auto *weights=ggml_cont(c,ggml_reshape_3d(c,ggml_soft_max(c,ggml_reshape_2d(c,rows,4,1)),1,4,1));
    auto *g=ggml_new_graph(c);ggml_build_forward_expand(g,weights);
    ggml_backend_buffer_ptr memory(ggml_backend_alloc_ctx_tensors(c,cpu));need(bool(memory),"router buffer");
    auto activation=read<float>(ref/"attn_post_norm.bin",width);
    put(x,activation);put(wt,read<float>(prefill/"router.weight",width*128));put(bias,read<float>(prefill/"router.bias",128));
    need(ggml_backend_graph_compute(cpu,g)==GGML_STATUS_SUCCESS,"router");ggml_backend_synchronize(cpu);
    equal(get<float>(raw),read<float>(ref/"ffn_moe_logits.bin",128));equal(get<float>(probs),read<float>(ref/"ffn_moe_probs.bin",128));
    auto logical=get<int>(ids);equal(logical,read<int>(ref/"ffn_moe_topk.bin",4));equal(logical,I(keys.begin(),keys.end()));
    auto mix=get<float>(weights);equal(mix,read<float>(ref/"ffn_moe_weights_softmax.bin",4));
    return {std::move(activation),std::move(mix),std::move(logical)};
}
void views(llama_moe_stream &m,ggml_context *c,ggml_context *bc){
    ggml_backend_buffer_ptr buf(ggml_backend_cpu_buffer_from_ptr(state.base,capacity));
    need(buf && std::string(ggml_backend_buffer_name(buf.get()))=="CPU_Mapped","mapped weight buffer");
    auto *owner=ggml_new_tensor_1d(c,GGML_TYPE_MXFP4,32*(capacity/17));ggml_backend_buffer_set_usage(buf.get(),GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
    need(ggml_backend_tensor_alloc(buf.get(),owner,state.base)==GGML_STATUS_SUCCESS,"mx owner");
    for(int k=0;k<3;++k){
        auto *meta=ggml_new_tensor_3d(c,GGML_TYPE_MXFP4,width,width,128);
        ggml_format_name(meta,"blk.0.ffn_%s_exps.weight",roles[k]);
        m.create_cache_tensor(0,ggml_backend_cpu_buffer_type(),meta,0,0);
        auto *v=ggml_view_3d(c,owner,width,width,40,ggml_row_size(GGML_TYPE_MXFP4,width),window,k*slab);
        need(ggml_backend_view_init(v)==GGML_STATUS_SUCCESS && v->buffer==buf.get(),"native weight view");
        m.layer(0)->weights[k].cache=state.tensors[to_math[k]]=v;
        state.tensors[3+to_math[k]]=ggml_new_tensor_2d(bc,GGML_TYPE_F32,width,128);
    }
    m.bufs.emplace_back(std::move(buf));
}
void seed(llama_moe_stream &m){
    std::unique_lock<std::mutex> lock(m.mtx);
    auto &l=*m.layer(0);m.start_workers_locked();
    for(int i=0;i<4;++i){
        const int e=keys[i],s=dest[i];l.slot_gen[s]=gens[i]-1;
        if(e==24)continue;
        m.reserve_slot_locked(l,e,s);m.q_demand.push_back({&l,e,s,l.slot_gen[s]});
    }
    m.cv_work.notify_all();
    need(m.cv_done.wait_for(lock,std::chrono::seconds(20),[&]{
        return m.load_failed || (l.slot_state[3]==2 && l.slot_state[6]==2 && l.slot_state[35]==2);
    }) && !m.load_failed && m.q_demand.empty() && l.expert_slot.size()==3 && state.setup_reads==3 &&
       l.slot_state[14]==LLAMA_MOE_STREAM_SLOT_EMPTY,"cut preparation");
    for(int i:{0,2,3})need((state.installed[dest[i]]==state.retained.at(keys[i]))==(state.mode!="COPY"),"backing provenance");
}
std::string provider(void *symbol){
    Dl_info info{};need(dladdr(symbol,&info) && info.dli_fname,"mapped provider");
    return fs::canonical(info.dli_fname).string();
}
json run(const fs::path &prefill,const fs::path &ref,const fs::path &pack,const fs::path &out){
    json plan;{std::ifstream f(ref/"plan.json");f>>plan;}
    need(plan.at("rows")==1 && plan.at("position")==189 && plan.at("layer")==0 && plan.at("logical_order")==keys &&
         plan.at("records").size()==4,"decode reference plan");
    for(size_t i=0;i<4;++i){
        const auto &r=plan.at("records").at(i);need(r.at("expert")==keys[i] && r.at("rank")==i,"plan row");
        state.records.emplace(keys[i],r);
    }
    ggml_backend_ptr cpu(ggml_backend_cpu_init());need(bool(cpu),"CPU backend");ggml_backend_cpu_set_n_threads(cpu.get(),8);
    auto in=route(prefill,ref,cpu.get());
    auto meta=context(), biases=context(), graph=context();
    Mapping arena(span,PROT_NONE,-1);state.base=arena.p;
    llama_moe_stream mgr(1,40,4,true);state.mgr=&mgr;views(mgr,meta.get(),biases.get());
    ggml_backend_buffer_ptr biasmem(ggml_backend_alloc_ctx_tensors(biases.get(),cpu.get()));need(bool(biasmem),"bias allocation");
    mgr.expert_store=std::make_unique<tesy_expert_store>();mgr.expert_store->data.open_file(pack.c_str());
    state.fd=mgr.expert_store->data.descriptor();
    const auto stat=fstat_id(state.fd);
    need(stat==plan.at("pack_stat") && (fcntl(state.fd,F_GETFL)&O_DIRECT) &&
         stride%mgr.expert_store->data.offset_alignment()==0 && 4096%mgr.expert_store->data.memory_alignment()==0,"expected O_DIRECT FD");
    seed(mgr);auto &l=*mgr.layer(0);
    auto before=snapshot(l);
    const json wanted_before={{28,3,6},{24,-1,0},{8,6,5},{16,35,4}};
    const json wanted_after={{28,3,6},{24,14,6},{8,6,5},{16,35,4}};
    need(before==wanted_before && mgr.stats.n_store_loads==3,"verified cut");
    state.decode=true;
    auto *c=graph.get();auto *g=ggml_new_graph_custom(c,256,false);
    auto *x=ggml_new_tensor_2d(c,GGML_TYPE_F32,width,1);auto *ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,1);
    auto *mix=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,4,1);for(auto *t:{x,ids,mix})ggml_set_input(t);
    auto *physical=ggml_map_custom1(c,ids,llama_moe_stream_remap,1,&l);
    auto *paired=pairs(c,state.tensors,x,ids,physical);
    auto *sum=finish(c,g,paired,mix);
    auto *ptr=cpu.get(); ggml_backend_sched_ptr sched(ggml_backend_sched_new(&ptr,nullptr,1,256,false,false));
    need(bool(sched),"scheduler");Witness w{sched.get(),cpu.get(),physical,ids,{}};
    ggml_backend_sched_set_eval_callback(sched.get(),observe,&w);
    need(ggml_backend_sched_alloc_graph(sched.get(),g),"allocation");
    put(x,in.x);put(ids,in.ids);put(mix,in.weights);
    need(ggml_backend_sched_graph_compute(sched.get(),g)==GGML_STATUS_SUCCESS,"decode graph");
    ggml_backend_sched_synchronize(sched.get());
    auto actual=get<float>(sum);const F gold=read<float>(ref/"ffn_moe_out.bin",width);
    {std::ofstream f(out/"decode.f32",std::ios::binary);need(bool(f.write(reinterpret_cast<const char*>(actual.data()),actual.size()*4)),"saved result");}
    size_t different=0;bool finite=true;need(actual.size()==gold.size(),"decode output dimensions");
    for(size_t i=0;i<gold.size();++i){different+=std::memcmp(&actual[i],&gold[i],4)!=0;finite=finite&&std::isfinite(actual[i])&&std::isfinite(gold[i]);}
    equal(w.physical,read<int>(ref/"ffn_moe_topk_stream.bin",4));
    auto after=snapshot(l);
    need(finite && (different!=0)==(state.mode=="WRONG") && after==wanted_after && w.remaps==1 && w.mmids==3 && w.biases==3 &&
         state.differences.size()==(state.mode=="WRONG"?2u:0u) && state.decode_reads==1 && mgr.stats.n_calls==1 &&
         mgr.stats.n_hit==3 && mgr.stats.n_miss==1 && mgr.stats.n_store_loads==4 && !mgr.load_failed && mgr.q_demand.empty() &&
         mgr.workers.size()==4 && fstat_id(state.fd)==stat,"decode identity, resources or numeric comparison");
    return {{"mode",state.mode},{"before",before},{"after",after},{"pack_stat",stat},{"setup_reads",3},{"setup_bytes",3*stride},
            {"decode_reads",1},{"decode_bytes",stride},{"hits",mgr.stats.n_hit},{"misses",mgr.stats.n_miss},{"copy_bytes",state.copies},
            {"mismatched_components",state.differences},{"equal_components",24-state.differences.size()},{"finite",finite},{"unequal",different},
            {"mmid_nodes",w.mmids},{"add_id_nodes",w.biases},{"router_positions",1},
            {"providers",{{"cpu",provider(reinterpret_cast<void*>(&ggml_backend_cpu_init))},{"base",provider(reinterpret_cast<void*>(&ggml_backend_sched_graph_compute))},
                          {"crypto",provider(reinterpret_cast<void*>(&SHA256))}}}};
}
int main(int n,char **v){
    try{
        need(n==6 && sysconf(_SC_PAGESIZE)==4096,"arguments");state.mode=v[4];
        need(state.mode=="COPY" || state.mode=="ALIAS" || state.mode=="WRONG","arm");
        fs::path out=v[5];need(fs::create_directory(out),"exclusive output");
        auto result=run(v[1],v[2],v[3],out);result["joined_workers"]=4;result["status"]="PASS_C291_CPU0_DECODE_HANDOFF";
        std::cout<<result.dump()<<'\n';return 0;
    }catch(const std::exception &e){std::cerr<<"FAIL_C291_CPU0_DECODE "<<e.what()<<'\n';return 1;}
}
