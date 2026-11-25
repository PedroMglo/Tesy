// Isolated CPU traversal using the genuine C291 direct reader, C305 worker pool and GGML operators.
#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include "c305-cpu-stage.h"
#include "ggml-cpu.h"
#include <openssl/sha.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <set>
#include <tuple>
#include <vector>

namespace fs=std::filesystem;
using json=nlohmann::json;
using F=std::vector<float>;
using I=std::vector<int32_t>;
constexpr int width=2880,nt=32;
constexpr size_t slab=4406400,window_bytes=13221888,stride=13258752;
struct CheckError : std::runtime_error { using runtime_error::runtime_error; };
static void need(bool ok,const char *why){if(!ok) throw CheckError(why);}
static int64_t now_ns(){return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();}
static std::string digest(const void *p,size_t n){
    unsigned char h[SHA256_DIGEST_LENGTH];need(SHA256(static_cast<const unsigned char*>(p),n,h),"SHA-256 failure");
    static constexpr char hex[]="0123456789abcdef";std::string s(64,'0');
    for(size_t i=0;i<sizeof(h);++i){s[2*i]=hex[h[i]>>4];s[2*i+1]=hex[h[i]&15];} return s;
}
template<class T> static std::vector<T> read(const fs::path &p,size_t n){
    need(fs::is_regular_file(p)&&fs::file_size(p)==n*sizeof(T),"prepared vector type/length");
    std::vector<T> out(n);std::ifstream f(p,std::ios::binary);
    need(bool(f.read(reinterpret_cast<char*>(out.data()),n*sizeof(T))),"prepared vector read");
    return out;
}
template<class T> static std::vector<T> values(ggml_tensor *t){
    need(ggml_is_contiguous(t)&&size_t(ggml_nbytes(t))==size_t(ggml_nelements(t))*sizeof(T),"output stride");
    std::vector<T> out(ggml_nelements(t));ggml_backend_tensor_get(t,out.data(),0,ggml_nbytes(t));return out;
}
template<class T> static void put(ggml_tensor *t,const std::vector<T> &v){
    need(ggml_is_contiguous(t)&&v.size()*sizeof(T)==ggml_nbytes(t),"input shape");
    ggml_backend_tensor_set(t,v.data(),0,ggml_nbytes(t));
}
static ggml_context_ptr context(){
    ggml_context_ptr c(ggml_init({16ull<<20,nullptr,true}));need(bool(c),"GGML metadata allocation");return c;
}
#include "graph.inc"

extern "C" int site(int,int,int,int,const float*,const float*,const float*,const float*,const float*,
                    const uint8_t*,const uint8_t*,int*,int*,uint64_t*);
extern "C" int scipy_openblas_get_num_threads64_();
using Binding=std::array<int,4>; // layer,expert,slot,generation
using Key=std::pair<int,int>;
struct Inputs {
    F x,gamma,router,bias,mix;
    I ids;
};
struct Witness {
    std::mutex lock;
    std::set<std::thread::id> workers;
    std::map<Key,std::array<std::string,3>> hashes;
    std::map<const ggml_tensor*,Key> tensors;
    std::map<Key,Binding> authoritative;
    std::vector<std::array<int64_t,5>> reads;
    std::vector<std::array<int64_t,7>> sets;
    std::vector<int64_t> check_hashes;
    std::vector<c294_event> journal;
    std::vector<c305_cpu_stage::event> stage;
    c305_cpu_stage::counters stats;
    int fd=-1; uintptr_t arena=0,end=0;
    bool exact=false,drained=false;
    int64_t joined=0;
    size_t preload=0;
} wit;
static thread_local bool isworker=false;
static thread_local Binding claim{{-1,-1,-1,-1}};

void tile_register_worker(){
    std::lock_guard<std::mutex> g(wit.lock);
    need(!isworker && wit.workers.insert(std::this_thread::get_id()).second,"fifth/duplicate worker");
    isworker=true;
}
void tile_claim(int l,int e,int s,uint64_t gen){
    need(isworker&&gen<1000,"foreign claim or generation");
    claim={l,e,s,int(gen)};
    need(wit.authoritative.at({l,e})==claim,"primary C292 generation/slot divergence");
}
void tile_workers_joined(llama_moe_stream &m){
    wit.joined=now_ns();
    if(std::uncaught_exceptions()||!m.prediction_stage)return;
    auto &stage=*m.prediction_stage;
    const auto count=m.window.count.load();
    need(!m.window.overflow.load()&&count<=m.window.events.size(),"worker journal overflow");
    wit.journal.assign(m.window.events.begin(),m.window.events.begin()+count);
    wit.stage.assign(stage.journal.begin(),stage.journal.begin()+stage.journal_count);
    wit.stats=stage.stats;
    wit.preload=m.stats.n_preload_issued;
    wit.drained=!m.load_failed&&m.q_demand.empty()&&m.workers.size()==4&&stage.idle();
    for(int l=0;l<2;++l){
        const auto &sl=*m.layer(l);
        for(int s=0;s<40;++s)wit.drained&=sl.slot_claimed[s]==0&&sl.slot_state[s]!=LLAMA_MOE_STREAM_SLOT_LOADING;
    }
}
extern "C" ssize_t __real_pread(int,void*,size_t,off_t);
extern "C" ssize_t __wrap_pread(int fd,void *buf,size_t n,off_t off){
    if(fd!=wit.fd)return __real_pread(fd,buf,n,off);
    need(isworker&&off>=0&&off%stride==0&&n==window_bytes,"foreign or wrong packed read");
    int rec=off/stride,l=rec/128,e=rec%128;
    const auto &gold=wit.hashes.at({l,e});
    uintptr_t a=reinterpret_cast<uintptr_t>(buf);
    bool spec=a>=wit.arena&&a<wit.end;
    need(spec || (claim[0]==l && claim[1]==e),"authoritative bytes unrelated to claim");
    const auto start=now_ns();auto rc=__real_pread(fd,buf,n,off);auto stop=now_ns();
    need(rc==ssize_t(n),"pack pread short/error/retry");
    if(wit.exact)for(size_t k=0;k<3;++k)need(
        digest(static_cast<uint8_t*>(buf)+k*slab,slab)==gold[k],"pack bytes differ from C290");
    {
        std::lock_guard<std::mutex> g(wit.lock);wit.reads.push_back({l,e,spec,start,stop});
        if(wit.exact)wit.check_hashes.push_back(3);
    }
    return rc;
}
extern "C" void __real_ggml_backend_tensor_set(ggml_tensor*,const void*,size_t,size_t);
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor *t,const void *p,size_t off,size_t n){
    const auto it=wit.tensors.find(t);
    if(it==wit.tensors.end()){__real_ggml_backend_tensor_set(t,p,off,n);return;}
    const auto [l,k]=it->second;
    need(isworker&&claim[0]==l&&off==size_t(claim[2])*slab&&n==slab,"primary SET claim/offset");
    auto start=now_ns();__real_ggml_backend_tensor_set(t,p,off,n);auto stop=now_ns();
    if(wit.exact)need(!memcmp(static_cast<uint8_t*>(t->data)+off,p,slab),"primary payload after SET");
    std::lock_guard<std::mutex> g(wit.lock);
    wit.sets.push_back({l,claim[1],claim[2],claim[3],k,start,stop});
}
static json fd_identity(int fd){
    struct stat s{};need(!fstat(fd,&s)&&S_ISREG(s.st_mode)&&!(s.st_mode&0222),"readonly opened pack");
    return {{"dev",s.st_dev},{"inode",s.st_ino},{"size_bytes",s.st_size},
            {"mtime_ns",s.st_mtim.tv_sec*1000000000LL+s.st_mtim.tv_nsec},
            {"ctime_ns",s.st_ctim.tv_sec*1000000000LL+s.st_ctim.tv_nsec}};
}
static void traffic(json &r){
    size_t h=0;for(auto n:wit.check_hashes)h+=n;
    need(wit.drained&&wit.workers.size()==4&&wit.sets.size()==375,"terminal worker conservation");
    std::map<Binding,std::set<int>> dst;std::map<Binding,int> published;std::set<Binding> queued;
    std::map<int,int64_t> waits;int64_t wait_ns=0;
    json intervals=json::array(),stages=json::array();
    for(auto &s:wit.sets)need(dst[{int(s[0]),int(s[1]),int(s[2]),int(s[3])}].insert(s[4]).second,"duplicate SET");
    for(auto &e:wit.journal){
        auto b=Binding{e.layer,e.expert,e.slot,int(e.gen)};
        if(e.kind==4)need(queued.insert(b).second,"duplicate queue");
        if(e.kind==10)++published[b];
        if(e.kind==11)need(waits.emplace(e.layer,e.us).second,"nested wait");
        if(e.kind==12){
            auto start=waits.at(e.layer);need(start<=e.us,"invalid wait");
            intervals.push_back({e.layer,start,e.us});wait_ns+=(e.us-start)*1000;waits.erase(e.layer);
        }
    }
    need(queued.size()==125&&waits.empty()&&dst.size()==125&&published.size()==125,"generation census");
    for(const auto &[key,b]:wit.authoritative)
        need(queued.count(b)&&dst.at(b)==std::set<int>{0,1,2}&&published.at(b)==1,"incomplete generation");
    for(auto &s:wit.stage)stages.push_back({s.kind,s.expert,s.ticket,s.slot,s.generation,s.us});
    need(wit.reads.size()<=130&&(!wit.exact||h==3*wit.reads.size()),"physical read cap/digests");
    const auto &s=wit.stats;
    r.update(json{{"stage",{{"issued",s.issued},{"reads",s.reads},{"consumed",s.consumed},{"waits",s.waits},
                  {"expired_queued",s.expired_queued},{"expired_ready",s.expired_ready},{"expired_running",s.expired_running}}},
                  {"stage_events",stages},{"workers",wit.workers.size()},{"drained",wit.drained},
                  {"slab_hashes",h},{"pread_bytes",window_bytes*wit.reads.size()},{"read_jobs",wit.reads.size()},
                  {"reads",wit.reads},{"sets",wit.sets.size()},{"service",wit.sets},{"wait_ns",wait_ns},
                  {"wait_intervals_us",intervals},{"slot_bindings",queued},{"preloads",wit.preload}});
}

static json run(const fs::path &dir,const fs::path &pack_path,const std::string &mode,const std::string &grade){
    need((mode=="ON"||mode=="OFF")&&(grade=="EXACT"||grade=="TIME"),"mode or grade");
    need(getenv("TESY_CPU_WAVE_SKIP_PARKED") && !strcmp(getenv("TESY_CPU_WAVE_SKIP_PARKED"),"1")
         && !getenv("LLAMA_MOE_STREAM_NO_PRELOAD") && scipy_openblas_get_num_threads64_()==1,
         "C269 parked mask, normal preload and one BLAS thread required");
    json plan;std::ifstream prepare(dir/"prepare.json");prepare>>plan;
    need(bool(prepare)&&plan.at("status")=="PASS_REAL_TILE_INPUT"&&plan.at("entries").size()==125,"unqualified inputs");
    wit.exact=grade=="EXACT";
    std::array<Inputs,2> in;
    for(int l=0;l<2;++l){
        const auto base="L"+std::to_string(l)+".";
        in[l].x=read<float>(dir/(base+"x.f32"),32*2880);
        in[l].mix=read<float>(dir/(base+"mix.f32"),32*4);
        in[l].ids=read<int32_t>(dir/(base+"ids.i32"),32*4);
        in[l].gamma=read<float>(dir/(base+"gamma.f32"),2880);
    }
    in[1].router=read<float>(dir/"L1.router.f32",128*2880);in[1].bias=read<float>(dir/"L1.bias.f32",128);
    const auto predicted=read<int32_t>(dir/"predicted.i32",128);
    ggml_backend_ptr cpu(ggml_backend_cpu_init());need(bool(cpu),"CPU backend");
    ggml_backend_cpu_set_n_threads(cpu.get(),8);
    auto m=std::make_unique<llama_moe_stream>(2,40,4,true);
    auto meta=context(),biasmeta=context();
    std::array<std::array<ggml_tensor*,6>,2> tensors{};
    std::array<const char*,3> roles{"gate","down","up"};
    std::array<int,3> order{0,2,1};
    for(int l=0;l<2;++l)for(int k=0;k<3;++k){
        int j=order[k];
        auto *source=ggml_new_tensor_3d(meta.get(),GGML_TYPE_MXFP4,width,width,128);
        ggml_format_name(source,"blk.%d.ffn_%s_exps.weight",l,roles[k]);
        tensors[l][j]=m->create_cache_tensor(l,ggml_backend_cpu_buffer_type(),source,0,
                                                plan.at("weight_bases").at(l).at(k).get<size_t>());
        tensors[l][3+j]=ggml_new_tensor_2d(biasmeta.get(),GGML_TYPE_F32,width,128);
        wit.tensors.emplace(tensors[l][j],Key{l,k});
    }
    m->alloc_bufs(false);
    ggml_backend_buffer_ptr biasram(ggml_backend_alloc_ctx_tensors(biasmeta.get(),cpu.get()));need(bool(biasram),"bias memory");
    for(int l=0;l<2;++l)for(int k=0;k<3;++k){
        auto *w=tensors[l][order[k]];
        need(w->nb[2]==slab&&ggml_nbytes(w)==40*slab,"40 slot GGML MXFP4 primary");
        put(tensors[l][3+order[k]],read<float>(dir/("L"+std::to_string(l)+"."+roles[k]+".bias.f32"),width*128));
    }
    m->expert_store=std::make_unique<tesy_expert_store>();auto &store=*m->expert_store;
    store.data.open_file(pack_path.c_str());wit.fd=store.data.descriptor();
    need(fd_identity(wit.fd)==plan.at("pack_stat")&&store.data.file_size()==4608*stride,"C290 opened inode");
    need((fcntl(wit.fd,F_GETFL)&O_DIRECT)&&store.data.offset_alignment()==4096,"O_DIRECT alignment");
    for(auto &layer:store.entries)for(auto &r:layer)r.offset=UINT64_MAX;
    for(const auto &row:plan.at("entries")){
        int l=row.at("layer"),e=row.at("expert"),slot=row.at("slot"),gen=row.at("gen");
        need(l>=0&&l<2&&e>=0&&e<128&&slot>=0&&slot<40&&gen>0,"prepared generation bounds");
        auto pos=(l*128ull+e)*stride;need(pos==row.at("pack_offset").get<uint64_t>(),"record offset");
        store.data.validate_range(pos,window_bytes);store.entries[l][e]={pos,{0,slab,2*slab}};
        need(wit.hashes.emplace(Key{l,e},row.at("hashes").get<std::array<std::string,3>>()).second,"repeated record");
        wit.authoritative.emplace(Key{l,e},Binding{l,e,slot,gen});
    }
    m->prediction_stage=std::make_unique<c305_cpu_stage>(store);auto &stage=*m->prediction_stage;
    need(stage.entry_stride==window_bytes&&stage.slots==10,"packed lookaside geometry");
    wit.arena=reinterpret_cast<uintptr_t>(stage.arena.get());wit.end=wit.arena+stage.slots*stage.entry_stride;
    stage.journal_enabled=true;
    m->window.call.store(1);m->window.enabled.store(true);
    m->prediction_begin(mode=="ON");m->select_prefill_tile(1,1);
    std::array<std::unique_ptr<UnitGraph>,2> graphs;
    for(int l=0;l<2;++l){
        need(m->layer(l)->expert_slot.empty()&&m->workers.empty(),"first tile starts cold");
        graphs[l]=std::make_unique<UnitGraph>(cpu.get(),*m,l,tensors[l]);graphs[l]->load_gold(dir);
    }
    std::array<uint8_t,128> occupancy{};std::array<uint8_t,32> mask;mask.fill(1);
    I projections(128);std::array<int,4> offers{};
    uint64_t projector=0; std::array<int64_t,8> epochs{};
    epochs[0]=now_ns();
    need(site(1,1,1,32,in[0].x.data(),in[0].gamma.data(),in[1].gamma.data(),in[1].router.data(),
              in[1].bias.data(),mask.data(),occupancy.data(),projections.data(),offers.data(),&projector)==32,
         "invalid resident projector");
    need(projections==predicted&&offers==std::array<int,4>{42,19,56,113},"predicted rows/offers diverged");
    m->prediction_request(1,1,offers);
    epochs[1]=now_ns();
    graphs[0]->execute(in[0].x,in[0].ids,in[0].mix);
    epochs[2]=now_ns();auto num0=graphs[0]->check(dir);epochs[3]=now_ns();
    // The destination's graph inputs are not submitted until after the independent FFN0 check.
    graphs[1]->execute(in[1].x,in[1].ids,in[1].mix);
    epochs[4]=now_ns();auto num1=graphs[1]->check(dir);epochs[5]=now_ns();
    m->prediction_finish();epochs[6]=now_ns();
    // The manager destructor's joining hook stops the primary clock before releasing the large buffers.
    auto remap0=graphs[0]->remap_intervals(),remap1=graphs[1]->remap_intervals();
    need(fd_identity(wit.fd)==plan.at("pack_stat")&&tesy_expert_store::identity(pack_path.c_str())==fd_identity(wit.fd),
         "changed pack before cleanup");
    graphs[0].reset();graphs[1].reset();
    m.reset();epochs[7]=wit.joined;
    need(std::is_sorted(epochs.begin(),epochs.end()),"backwards primary clock");
    json r={{"status","PASS_REAL_TILE"},{"mode",mode},{"grade",grade},{"offers",offers},
            {"numeric",{{"L0",num0},{"L1",num1}}},{"epochs_ns",epochs},{"elapsed_ns",epochs[7]-epochs[0]},
            {"producer_ns",projector},{"drain_ns",epochs[7]-epochs[5]},{"remap_ns",{{"L0",remap0},{"L1",remap1}}}};
    traffic(r);return r;
}
int main(int argc,char **argv){
    try{need(argc==5,"real-tile INPUT_DIR PACK_PATH OFF|ON EXACT|TIME");
        auto result=run(argv[1],argv[2],argv[3],argv[4]);std::cout<<result.dump()<<"\n";return 0;
    }catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 1;}
}
