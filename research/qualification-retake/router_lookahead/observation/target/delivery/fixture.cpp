// The real C305 workers share one C291 packed FD. The barriers below order fixture events only.
#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include "c305-cpu-stage.h"
#include "ggml-cpu.h"
#include "../projector.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <future>
#include <iostream>
#include <set>
#include <thread>
using json=nlohmann::json;
using Stage=c305_cpu_stage;
using namespace std::chrono_literals;
using Quartet=std::array<int,4>;
constexpr size_t slab=Stage::slab, bytes=3*slab, stride=16384;
constexpr int layer=1, site=6;
void check(bool b,const char *msg){ if(!b) throw std::runtime_error(msg); }
uint8_t marker(int e,int k,size_t i){ return uint8_t(1+13*e+29*k+i%113); }

struct Witness {
    std::mutex lock;
    std::condition_variable changed;
    std::set<std::thread::id> workers;
    std::array<int,5> speculative{}, primary{}, held{};
    std::array<bool,5> release{};
    std::vector<std::pair<int,int>> copies;
    uintptr_t arena=0, end=0;
    int fd=-1, inflight=0, peak=0;
    bool pause=false;
} witness;
extern "C" ssize_t __real_pread(int,void*,size_t,off_t);
extern "C" ssize_t __wrap_pread(int fd,void *dst,size_t n,off_t off) {
    auto &v=witness;
    if (fd!=v.fd) return __real_pread(fd,dst,n,off);
    int e=int(off/stride);
    {
        std::unique_lock<std::mutex> g(v.lock);
        check(e>=0 && e<5 && off==off_t(e*stride) && n==bytes,"wrong pack window");
        check(v.workers.count(std::this_thread::get_id())==1,"nonworker issued IO");
        const auto a=reinterpret_cast<uintptr_t>(dst);
        const bool spec=a>=v.arena && a<v.end;
        ++(spec ? v.speculative : v.primary)[e];
        v.peak=std::max(v.peak,++v.inflight);
        if(v.pause && (e==1 || e==2)) {
            ++v.held[e]; v.changed.notify_all();
            check(v.changed.wait_for(g,5s,[&]{return v.release[e];}),"controlled read timeout");
        }
    }
    const auto rc=__real_pread(fd,dst,n,off);
    { std::lock_guard<std::mutex> g(v.lock); --v.inflight; }
    return rc;
}
extern "C" void __real_ggml_backend_tensor_set(ggml_tensor*,const void*,size_t,size_t);
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor *t,const void *src,size_t off,size_t n) {
    if (witness.fd>=0) {
        check(n==slab && off%slab==0,"wrong SET geometry");
        std::lock_guard<std::mutex> g(witness.lock);
        check(witness.workers.count(std::this_thread::get_id())==1,"SET from foreign thread");
        witness.copies.emplace_back(int(off/slab),int(n));
    }
    __real_ggml_backend_tensor_set(t,src,off,n);
}

template<class F> void until(llama_moe_stream &m,F f) {
    std::unique_lock<std::mutex> g(m.mtx);
    const auto end=std::chrono::steady_clock::now()+5s;
    while(!f()) {
        check(std::chrono::steady_clock::now()<end,"manager transition deadline");
        m.cv_done.wait_for(g,2ms);
    }
}
void open_gate(int e) {
    std::lock_guard<std::mutex> g(witness.lock);
    witness.release[e]=true; witness.changed.notify_all();
}
void pause_started(int e) {
    std::unique_lock<std::mutex> g(witness.lock);
    check(witness.changed.wait_for(g,5s,[&]{return witness.held[e]==1;}),"expected read not in flight");
}
json pool(llama_moe_stream &m) {
    std::lock_guard<std::mutex> g(m.mtx);
    auto &l=*m.layer(layer);
    return {l.slot_expert,l.slot_gen,l.slot_state,l.slot_claimed,l.route_hotness,l.slot_last_use};
}
Quartet forecast() {
    // The identical +1 arithmetic runs in OFF. Inputs are fixture markers.
    using namespace target_probe;
    std::vector<float> x(width,0),gamma(width,1),w(width*experts,0),bias(experts,0);
    x[0]=1;
    for(int e=0;e<4;++e)w[e*width]=float(4-e);
    prepare_matrix(w,false);
    return project(x.data(),gamma.data(),gamma.data(),w.data(),bias.data(),false);
}

void submit(llama_moe_stream &m,int expert,int slot) {
    std::lock_guard<std::mutex> g(m.mtx);
    auto *l=m.layer(layer);
    m.reserve_slot_locked(*l,expert,slot);
    m.enqueue_locked(l,expert,slot,l->slot_gen[slot]);
    m.cv_work.notify_all();
}
void verify_bytes(llama_moe_stream_layer &l,int e) {
    int s=l.expert_slot.at(e);
    check(l.slot_state[s]==LLAMA_MOE_STREAM_SLOT_RESIDENT&&!l.slot_claimed[s],"wrong published state");
    for(int k=0;k<3;++k) {
        const auto *p=static_cast<const uint8_t*>(l.weights[k].cache->data)+size_t(s)*slab;
        for(size_t i=0;i<slab;++i) check(p[i]==marker(e,k,i),"wrong published bytes");
    }
}
std::vector<int> route(llama_moe_stream &m) {
    ggml_context_ptr c(ggml_init({1<<20,nullptr,false}));
    auto *ids=ggml_new_tensor_2d(c.get(),GGML_TYPE_I32,4,32);
    auto *dest=ggml_dup_tensor(c.get(),ids);
    dest->src[0]=ids;
    auto *p=static_cast<int32_t*>(ids->data);
    const Quartet official{0,1,3,4};
    for(int j=0;j<32;++j)std::copy(official.begin(),official.end(),p+j*4);
    auto *sl=m.layer(layer);
    auto *wave=sl->wave_userdata(0,32);
    llama_moe_stream_wave_ids(dest,0,1,wave);
    auto *slots=static_cast<int32_t*>(dest->data);
    for(int i=0;i<128;++i) check(slots[i]==sl->expert_slot.at(p[i]),"architectural slot remap");
    return {slots,slots+128};
}

json exercise(const char *path,bool on,bool fault) {
    auto &v=witness;
    llama_moe_stream m(36,40,4,true);
    ggml_context_ptr meta(ggml_init({1<<20,nullptr,true}));
    for(int k=0;k<3;++k) {
        auto *wt=ggml_new_tensor_3d(meta.get(),GGML_TYPE_I8,slab,1,128);
        m.create_cache_tensor(layer,ggml_backend_cpu_buffer_type(),wt,0,k*slab);
    }
    m.alloc_bufs(false);
    m.expert_store=std::make_unique<tesy_expert_store>();
    auto &pack=*m.expert_store;
    pack.data.open_file(path);
    check(pack.data.file_size()==5*stride && (fcntl(pack.data.descriptor(),F_GETFL)&O_DIRECT),"fixture pack FD/range");
    for(int e=0;e<5;++e)pack.entries[layer][e]={e*stride,{0,slab,2*slab}};
    m.prediction_stage=std::make_unique<Stage>(pack);
    auto &s=*m.prediction_stage;
    s.journal_enabled=true;
    auto &l=*m.layer(layer);
    {
        std::lock_guard<std::mutex> g(m.mtx);
        m.start_workers_locked();
        v.fd=pack.data.descriptor();
        v.arena=reinterpret_cast<uintptr_t>(s.arena.get());
        v.end=v.arena+size_t(s.slots)*s.entry_stride;
        for(auto &worker:m.workers)v.workers.insert(worker.get_id());
        check(v.workers.size()==4,"worker count");
    }
    m.prediction_begin(on); m.select_prefill_tile(2,1);
    submit(m,3,0);
    until(m,[&]{return l.slot_state[0]==LLAMA_MOE_STREAM_SLOT_RESIDENT;});
    auto before=pool(m);
    auto guessed=forecast(); check(guessed==Quartet{0,1,2,3},"forecast");
    { std::lock_guard<std::mutex> g(v.lock); v.pause=true; }
    for(int i=0;i<32;++i)m.prediction_request(site,layer,guessed);
    uint64_t read_ticket=0;
    if(on) {
        pause_started(1); pause_started(2);
        until(m,[&]{auto i=s.find(site,layer,0);return i>=0 && s.entries[i].status==Stage::READY;});
        std::lock_guard<std::mutex> g(m.mtx);
        read_ticket=s.entries[s.find(site,layer,1)].ticket;
    }
    check(before==pool(m),"prediction changed the primary");
    if(fault) {
        submit(m,1,1);
        until(m,[&]{return s.stats.waits==1;});
        {
            std::lock_guard<std::mutex> g(m.mtx);
            check(l.slot_gen[1]==1 && l.slot_claimed[1],"negative setup");
            ++l.slot_gen[1]; // different live owner: the stale consumer must not clear its claim
        }
        open_gate(1); open_gate(2);
        until(m,[&]{return m.load_failed&&s.running==0;});
        {
            std::lock_guard<std::mutex> g(m.mtx);
            s.finish();
            check(s.idle() && l.slot_gen[1]==2 && l.slot_claimed[1] &&
                  l.slot_state[1]==LLAMA_MOE_STREAM_SLOT_LOADING,"stale publish/claim/lease");
        }
        check(v.copies.size()==3,"stale bytes written to new owner");
        return {{"status","PASS_STALE_OWNER_REJECTED"},{"stale_sets",0},{"new_claim_preserved",true},
                {"new_generation",2},{"idle",true},{"workers",v.workers.size()}};
    }
    auto official=std::async(std::launch::async,[&]{return route(m);});
    pause_started(1);
    if(on)until(m,[&]{return s.stats.waits==1 && s.entries[s.find(site,layer,1)].demand;});
    open_gate(1);
    check(official.wait_for(5s)==std::future_status::ready,"route deadline");
    auto slots=official.get();
    if(on) {
        std::lock_guard<std::mutex> g(m.mtx);
        bool wrong_live=false;
        for(const auto &e:s.entries)if(e.expert==2 && e.status==Stage::READING && e.expired)wrong_live=true;
        check(wrong_live,"cancelled bytes unleased before read ended");
    }
    open_gate(2);
    m.prediction_finish();
    check(s.idle() && !m.load_failed,"cleanup");
    int consumed=s.stats.consumed, waits=s.stats.waits, cancelled=s.stats.expired_running;
    check(v.speculative==(on?std::array<int,5>{1,1,1,0,0}:std::array<int,5>{0,0,0,0,0}),"spec IO");
    check(v.primary==(on?std::array<int,5>{0,0,0,1,1}:std::array<int,5>{1,1,0,1,1}),"demand IO");
    check(consumed==(on?2:0) && waits==int(on) && cancelled==int(on) && v.copies.size()==12,"conservation");
    for(auto e:Quartet{0,1,3,4})verify_bytes(l,e);
    auto final=pool(m);
    if(on) {
        std::lock_guard<std::mutex> g(m.mtx);
        s.begin(true);
        int i=s.request(7,layer,2);
        check(i>=0 && s.entries[i].ticket>read_ticket,"reused old ticket");
        bool rejected=false;
        try { s.demand(i,read_ticket); } catch(const std::runtime_error&){rejected=true;}
        check(rejected,"stale staging ticket");
        s.finish();check(s.idle(),"queued teardown");
    }
    return {{"status","PASS_PREFILL_PACKED_DELIVERY"},{"workers",v.workers.size()},
            {"peak_reads",v.peak},{"issued_spec_reads",v.speculative},{"issued_primary_reads",v.primary},
            {"delivered",consumed},{"attached_before_ready",waits},{"running_waste_drained",cancelled},
            {"slab",slab},{"window",bytes},{"sets",v.copies.size()},{"primary",final},
            {"initial",before},{"routed_slots",slots},{"proposal",guessed},{"arena",s.entry_stride*s.slots}};
}
int main(int argc,char **argv) {
    try {
        check(argc==3,"pack and mode"); const std::string mode=argv[2];
        check(mode=="OFF"||mode=="ON"||mode=="STALE","mode");
        auto r=exercise(argv[1],mode!="OFF",mode=="STALE");
        r["mode"]=mode;r["manager_destroyed"]=true; // destructor joined before exercise returned
        std::cout<<r.dump()<<std::endl;return 0;
    } catch(const std::exception &e) {std::cerr<<e.what()<<std::endl;return 1;}
}
