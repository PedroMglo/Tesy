// Five cold logical misses; all banks, staging pages and workers prepared before t0.
#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include "ggml-cpu.h"
#include <openssl/sha.h>
#include <dlfcn.h>
#include <sys/resource.h>
#include <time.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <condition_variable>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <thread>
#ifndef TESY_STORE_TESTING
#error Limited authenticated index for a service fixture only
#endif
using Store=tesy_expert_store;
using json=nlohmann::json;
namespace fs=std::filesystem;
constexpr size_t slab=4406400, window=13221888, stride=13258752;
constexpr std::array<int,5> ordered{45,60,98,57,49}, on_disk{45,49,57,60,98};
constexpr std::array<const char*,3> roles{"gate","down","up"};
static_assert(slab==Store::slab && sizeof(int32_t)==4);
static void need(bool cond,const char *reason){if(!cond)throw std::runtime_error(reason);}
static int64_t now(){timespec ts{}; if(clock_gettime(CLOCK_MONOTONIC_RAW,&ts))std::abort();return int64_t(ts.tv_sec)*1000000000+ts.tv_nsec;}
static rusage process_usage() {
    rusage out{};
    need(getrusage(RUSAGE_SELF, &out) == 0, "process page fault counters");
    need(out.ru_minflt >= 0 && out.ru_majflt >= 0, "negative process page fault counters");
    return out;
}
static std::string digest(const void *data,size_t size){
    unsigned char bytes[SHA256_DIGEST_LENGTH];need(SHA256(static_cast<const unsigned char*>(data),size,bytes)!=nullptr,"SHA256");
    std::ostringstream text;for(auto c:bytes)text<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(c);return text.str();
}
static std::string provider(void *fn){Dl_info d{};need(dladdr(fn,&d)&&d.dli_fname,"missing runtime provider");return fs::canonical(d.dli_fname).string();}
struct Interval{int64_t begin=0,end=0;};
struct alignas(64) Job{
    int expert=-1,slot=-1,worker=-1;uint64_t gen=0;int reads=0,sets=0,pubs=0;
    size_t requested=0;int64_t enqueue=0,publish=0;Interval read;std::array<Interval,3> copies{};
};
struct State{
    llama_moe_stream *mgr=nullptr;llama_moe_stream_layer *sl=nullptr;std::array<ggml_tensor*,3> views{};
    std::array<Job,5> jobs{};int fd=-1,queued=0,committed=0,ready=0;size_t pitch=0;
    bool direct=false,detail=false;std::atomic<bool> active=false;std::atomic<const char*> error=nullptr;
    std::mutex gate_mtx;std::condition_variable gate;int64_t t0=0,tP=0,tR=0;
    void fail(const char *message){const char *empty=nullptr;error.compare_exchange_strong(empty,message);}
};
static std::atomic<State *> state=nullptr;
static thread_local int worker=-1;
static thread_local Job *current=nullptr;
static thread_local uintptr_t source=0;
static std::atomic<bool> link_test=false;
static std::array<std::atomic<int>,3> reached{};
extern "C" void real_one(std::condition_variable *) asm("__real__ZNSt18condition_variable10notify_oneEv");
extern "C" void wrap_one(std::condition_variable *) asm("__wrap__ZNSt18condition_variable10notify_oneEv");
extern "C" void real_all(std::condition_variable *) asm("__real__ZNSt18condition_variable10notify_allEv");
extern "C" void wrap_all(std::condition_variable *) asm("__wrap__ZNSt18condition_variable10notify_allEv");
extern "C" void real_wait(std::condition_variable *,std::unique_lock<std::mutex>&) asm("__real__ZNSt18condition_variable4waitERSt11unique_lockISt5mutexE");
extern "C" void wrap_wait(std::condition_variable *,std::unique_lock<std::mutex>&) asm("__wrap__ZNSt18condition_variable4waitERSt11unique_lockISt5mutexE");
extern "C" ssize_t __real_pread(int,void*,size_t,off_t);
extern "C" void __real_ggml_backend_tensor_set(ggml_tensor*,const void*,size_t,size_t);
static Job *by_expert(State &s,int expert){auto it=std::find(on_disk.begin(),on_disk.end(),expert); if(it==on_disk.end()){s.fail("unselected expert");return nullptr;}return &s.jobs[it-on_disk.begin()];}
extern "C" void wrap_one(std::condition_variable *cv){
    if(link_test) ++reached[0];
    auto *s=state.load(std::memory_order_relaxed);
    if(s && s->active && cv==&s->mgr->cv_work){
        const auto &queue=s->mgr->q_demand;
        if(queue.empty() || s->queued>=5){s->fail("enqueue count");}
        else {const auto &w=queue.back();auto *j=by_expert(*s,w.expert);
            if(!j || w.expert!=ordered[s->queued] || w.sl!=s->sl || w.slot!=s->queued || w.gen!=1 || j->expert!=-1) s->fail("FIFO identity");
            else {j->expert=w.expert;j->slot=w.slot;j->gen=w.gen;if(s->detail)j->enqueue=now();}
            ++s->queued;}
    }
    real_one(cv);
}
extern "C" void wrap_all(std::condition_variable *cv){
    if(link_test) ++reached[1];
    auto *s=state.load(std::memory_order_relaxed);
    if(s && s->active && cv==&s->mgr->cv_done){
        // Manager already owns mtx. The previous source statement committed the identity and accounts its bytes.
        const int ordinal=++s->committed;const int64_t ns=(s->detail||ordinal==5)?now():0;
        if(ordinal==5)s->tP=ns;
        if(!current || worker<0 || s->mgr->stats.n_store_loads!=ordinal) s->fail("unexpected worker notification");
        else {auto &j=*current;const int k=j.slot;
            if(k<0 || k>=40 || s->sl->slot_state[k]!=LLAMA_MOE_STREAM_SLOT_RESIDENT || s->sl->slot_expert[k]!=j.expert ||
               s->sl->slot_gen[k]!=j.gen || s->sl->slot_claimed[k] || j.worker!=worker || ++j.pubs!=1) s->fail("publication identity");
            j.publish=ns;current=nullptr;source=0;}
    }
    real_all(cv);
}
extern "C" void wrap_wait(std::condition_variable *cv,std::unique_lock<std::mutex>&lock){
    if(link_test) ++reached[2];
    auto *s=state.load(std::memory_order_relaxed);
    if(s && cv==&s->mgr->cv_work && worker<0){
        std::lock_guard<std::mutex> ready(s->gate_mtx);worker=s->ready++;s->gate.notify_all();
    }
    const bool consumer=s && s->active && cv==&s->mgr->cv_done;
    if(consumer && !s->t0){
        if(s->queued!=5 || s->mgr->q_demand.size()!=5 || s->mgr->stats.n_store_loads) s->fail("consumer did not release five fresh jobs");
        s->t0=now();
    }
    real_wait(cv,lock);
    if(consumer && s->mgr->stats.n_store_loads==5 && !s->tR)s->tR=now();
}
extern "C" ssize_t __wrap_pread(int fd,void *dst,size_t bytes,off_t off){
    auto *s=state.load(std::memory_order_relaxed);if(!s || !s->active || fd!=s->fd)return __real_pread(fd,dst,bytes,off);
    if(off<0 || size_t(off)%stride || size_t(off)/stride>=5){s->fail("unmapped offset");errno=EIO;return -1;}
    auto &j=s->jobs[size_t(off)/stride];current=&j;source=uintptr_t(dst);
    if(worker<0 || worker>=4 || j.reads++ || bytes!=window || j.slot<0 || j.slot>=40) s->fail("read identity");
    j.worker=worker;j.requested=bytes;
    if(j.slot>=0 && j.slot<40 && s->direct!=(source==uintptr_t(s->views[0]->data)+size_t(j.slot)*s->pitch))s->fail("read destination");
    if(s->detail)j.read.begin=now();
    const ssize_t count=__real_pread(fd,dst,bytes,off);
    if(s->detail)j.read.end=now();
    if(count!=ssize_t(window))s->fail("short read or retry");return count;
}
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor*t,const void*src,size_t off,size_t bytes){
    auto *s=state.load(std::memory_order_relaxed);if(!s || !s->active){__real_ggml_backend_tensor_set(t,src,off,bytes);return;}
    auto it=std::find(s->views.begin(),s->views.end(),t);
    if(it==s->views.end()){__real_ggml_backend_tensor_set(t,src,off,bytes);return;}
    const int k=it-s->views.begin();auto *j=current;
    if(!j || j->worker!=worker || j->sets++!=k || s->direct || bytes!=slab ||
       off!=size_t(j->slot)*s->pitch || uintptr_t(src)!=source+k*slab)s->fail("tensor SET identity");
    if(s->detail && j)j->copies[k].begin=now();
    __real_ggml_backend_tensor_set(t,src,off,bytes);
    if(s->detail && j)j->copies[k].end=now();
}
static void self_test(){
    std::condition_variable cv;std::mutex mutex;bool waiting=false,go=false;link_test=true;
    std::thread worker_thread([&]{std::unique_lock<std::mutex> lock(mutex);waiting=true;cv.notify_all();cv.wait(lock,[&]{return go;});});
    {std::unique_lock<std::mutex> lock(mutex);cv.wait(lock,[&]{return waiting;});go=true;cv.notify_one();}
    worker_thread.join();link_test=false;need(reached[0]>0 && reached[1]>0 && reached[2]>0,"ABI interposition did not reach each CV symbol");
}
static json rows(const State&s){json out=json::array();if(!s.detail)return out;
    auto emit=[&](const Job&j,const char*kind,int64_t ns,int tid,int k,size_t bytes){out.push_back({{"event",kind},{"ns",ns},{"worker",tid},
        {"expert",j.expert},{"slot",j.slot},{"generation",j.gen},{"component",k},{"bytes",bytes}});};
    for(const auto &j:s.jobs){emit(j,"enqueue",j.enqueue,-1,-1,0);emit(j,"read_begin",j.read.begin,j.worker,-1,window);emit(j,"read_end",j.read.end,j.worker,-1,window);
        for(int k=0;k<j.sets;++k){emit(j,"set_begin",j.copies[k].begin,j.worker,k,slab);emit(j,"set_end",j.copies[k].end,j.worker,k,slab);}
        emit(j,"publish",j.publish,j.worker,-1,0);}
    return out; // per-job order; raw_ns determines chronology between workers
}
static ggml_context_ptr ctx(bool no_alloc){ggml_context_ptr c(ggml_init({2u<<20,nullptr,no_alloc}));need(bool(c),"GGML context");return c;}
static json measure(const fs::path &in,const std::string&layout,const std::string&observer){
    need(layout=="DENSE"||layout=="STAGED"||layout=="DIRECT","layout");need(observer=="MIN"||observer=="DETAIL","observer");
    const char *env=std::getenv("TESY_PACKED_CPU_SLOTS");
    need(layout=="DENSE"?!env:(env && env==std::string(layout=="DIRECT"?"direct":"staged")),"layout environment");
    need(std::getenv("TESY_CPU_WAVE_SKIP_PARKED") && std::string(std::getenv("TESY_CPU_WAVE_SKIP_PARKED"))=="1","C47");
    json inputs;{std::ifstream f(in/"prepare.json");f>>inputs;need(bool(f)&&inputs.at("status")=="PASS_PREPARED_REAL_TILE","input identity");}
    const auto route_file=in/"ffn_moe_topk-0.bin";std::array<int32_t,153*4> allroutes{};
    {std::ifstream f(route_file,std::ios::binary);need(fs::file_size(route_file)==sizeof(allroutes) && bool(f.read(reinterpret_cast<char*>(allroutes.data()),sizeof(allroutes))),"route bytes");}
    need(digest(allroutes.data(),sizeof(allroutes))=="14ada9ecbfe77401ff5d40955e9b491c6ebc82f34787737c2e4c8910ffa6cd96","route identity");
    const auto *logical=allroutes.data()+32*4;State s;s.pitch=layout=="DENSE"?slab:window;s.direct=layout=="DIRECT";s.detail=observer=="DETAIL";
    auto meta=ctx(true);auto graph=ctx(false);llama_moe_stream mgr(1,40,4,true);s.mgr=&mgr;
    for(int k=0;k<3;++k){auto *m=ggml_new_tensor_3d(meta.get(),GGML_TYPE_MXFP4,2880,2880,128);ggml_format_name(m,"blk.0.ffn_%s_exps.weight",roles[k]);
        s.views[k]=mgr.create_cache_tensor(0,ggml_backend_cpu_buffer_type(),m,0,inputs.at("weight_bases").at(k).get<size_t>());}
    mgr.alloc_bufs(false);s.sl=mgr.layer(0);mgr.expert_store=std::make_unique<Store>();auto &store=*mgr.expert_store;
    const auto pack=in/"pack.bin";store.data.open_file(pack.c_str());s.fd=store.data.descriptor();
    const size_t align=store.data.offset_alignment();need(align && (3*slab+align-1)/align*align==window,"DENSE read length would differ");
    const int flags=fcntl(s.fd,F_GETFL);need(flags>=0 && (flags&O_DIRECT) && store.data.file_size()==5*stride,"pack fd/geometry");
    struct stat before{};need(!fstat(s.fd,&before),"pack initial fstat");
    for(auto &e:store.entries[0])e.offset=UINT64_MAX;
    for(int i=0;i<5;++i){auto &e=store.entries[0][on_disk[i]];e.offset=i*stride;e.relative={0,slab,2*slab};}
    for(auto *v:s.views)need(v->data && v->nb[2]==s.pitch && (ggml_is_contiguous(v)==(layout=="DENSE")),"slot geometry");
    // Equal logical payload in slot/component order, plus the packed layout's private padding.
    const auto faults_before=process_usage();
    const auto pre_start=now();
    for(int slot=0;slot<40;++slot){for(auto *v:s.views)std::memset(static_cast<char*>(v->data)+slot*s.pitch,0xa3,slab);
        if(layout!="DENSE")std::memset(static_cast<char*>(s.views[0]->data)+slot*s.pitch+3*slab,0xa3,window-3*slab);}
    const auto pre_end=now();
    const auto faults_after=process_usage();
    need(faults_after.ru_minflt >= faults_before.ru_minflt &&
         faults_after.ru_majflt >= faults_before.ru_majflt, "regressing process page fault counters");
    auto *ids=ggml_new_tensor_2d(graph.get(),GGML_TYPE_I32,4,32);std::memcpy(ids->data,logical,128*sizeof(int32_t));
    ggml_tensor *args[]={ids};auto *wave=s.sl->wave_userdata(0,18);
    auto *out=ggml_custom_4d(graph.get(),GGML_TYPE_I32,4,32,1,1,args,1,llama_moe_stream_wave_ids,1,wave);
    state=&s;
    {std::lock_guard<std::mutex> lock(mgr.mtx);need(mgr.q_demand.empty() && s.sl->expert_slot.empty(),"entry cache");mgr.start_workers_locked();}
    {std::unique_lock<std::mutex> lock(s.gate_mtx);need(s.gate.wait_for(lock,std::chrono::seconds(10),[&]{return s.ready==4;}),"worker ready barrier");}
    s.active=true;const auto outer_start=now();llama_moe_stream_wave_ids(out,0,1,wave);const auto outer_end=now();s.active=false;
    if(auto *msg=s.error.load())throw std::runtime_error(msg);
    need(outer_start<=s.t0 && s.t0<s.tP && s.tP<=s.tR && s.tR<=outer_end,"service endpoints");
    need(s.queued==5 && s.committed==5 && s.sl->expert_slot.size()==5 && mgr.stats.n_store_loads==5 &&
         mgr.stats.n_store_read_bytes==5*3*int64_t(slab) && !mgr.load_failed && mgr.q_demand.empty() &&
         mgr.stats.n_wave_calls==1 && mgr.stats.n_waves_run==1 && mgr.stats.n_miss==5,"terminal manager");
    const auto *physical=static_cast<const int32_t*>(out->data);
    for(int i=0;i<128;++i)need(s.sl->expert_slot.at(logical[i])==physical[i],"rank/slot mapping");
    json confirmed=json::array();size_t count_bytes=0;int total_sets=0;
    for(int e:ordered){auto *j=by_expert(s,e);need(j && j->reads==1 && j->pubs==1 && j->sets==(s.direct?0:3) && j->gen==1 &&
            s.sl->slot_state[j->slot]==LLAMA_MOE_STREAM_SLOT_RESIDENT && !s.sl->slot_claimed[j->slot],"final generation");
        for(int k=0;k<3;++k){auto *src=static_cast<uint8_t*>(s.views[k]->data)+j->slot*s.pitch;
            need(digest(src,slab)==inputs.at("components").at(std::to_string(e)).at(k).at("sha256"),"delivered component SHA");}
        confirmed.push_back({j->expert,j->slot,j->gen});count_bytes+=j->requested;total_sets+=j->sets;}
    struct stat after{},pathstat{};need(!fstat(s.fd,&after)&&!stat(pack.c_str(),&pathstat),"pack final stat");
    auto same=[&](const struct stat&t){return t.st_dev==before.st_dev && t.st_ino==before.st_ino && t.st_size==before.st_size &&
        t.st_mtim.tv_sec==before.st_mtim.tv_sec && t.st_mtim.tv_nsec==before.st_mtim.tv_nsec && t.st_ctim.tv_sec==before.st_ctim.tv_sec && t.st_ctim.tv_nsec==before.st_ctim.tv_nsec;};
    need(same(after)&&same(pathstat),"pack identity changed");state=nullptr;
    return {{"schema","tesy-c291-five-misses-v1"},{"layout",layout},{"observer",observer},{"clock","MONOTONIC_RAW_NS"},
        {"outer_start",outer_start},{"t0",s.t0},{"last_publication",s.tP},{"resume",s.tR},{"outer_end",outer_end},
        {"ready_workers",s.ready},{"workers_before_destructor",mgr.workers.size()},{"load_count",mgr.stats.n_store_loads},
        {"requested_bytes",count_bytes},{"logical_bytes",mgr.stats.n_store_read_bytes},{"set_count",total_sets},
        {"queue_empty",true},{"verified_payload",true},{"confirmed_slots",confirmed},{"events",rows(s)},
        {"prefault_bytes",40*(layout=="DENSE"?3*slab:window)},{"prefault_ns",pre_end-pre_start},
        {"prefault_faults",{{"scope","RUSAGE_SELF"},
            {"minflt_before",faults_before.ru_minflt},{"minflt_after",faults_after.ru_minflt},
            {"minflt_delta",faults_after.ru_minflt-faults_before.ru_minflt},
            {"majflt_before",faults_before.ru_majflt},{"majflt_after",faults_after.ru_majflt},
            {"majflt_delta",faults_after.ru_majflt-faults_before.ru_majflt}}},
        {"providers",{{"cpu",provider(reinterpret_cast<void*>(&ggml_backend_cpu_init))},{"base",provider(reinterpret_cast<void*>(&ggml_backend_sched_graph_compute))}}}};
}
int main(int argc,char**argv){try{
    if(argc==2 && std::string(argv[1])=="--self-test"){self_test();std::cout<<"PASS_C291_SERVICE_CV_LINK\n";return 0;}
    need(argc==5,"usage: service INPUT_DIR LAYOUT MIN|DETAIL NEW_OUTPUT_DIR");fs::path out(argv[4]);need(fs::create_directory(out),"new output");
    auto j=measure(argv[1],argv[2],argv[3]);j["joined_workers"]=j.at("workers_before_destructor");j["status"]="PASS_C291_FIVE_MISS_SERVICE";
    {std::ofstream f(out/".pending");f<<j.dump(2)<<'\n';f.close();need(bool(f),"receipt write");}fs::rename(out/".pending",out/"service.json");
    std::cout<<j.at("status").get<std::string>()<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"FAIL_SERVICE: "<<e.what()<<'\n';return 1;}}
