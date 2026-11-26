#pragma once
#include "lease.h"
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>

using Lock=std::unique_lock<std::mutex>;
constexpr size_t capacity=((40*window+16)/17)*17;
constexpr size_t span=((capacity+4095)/4096)*4096;
static void *map_at(void *at,size_t n,int protection,int flags,int fd) {
    void *p=mmap(at,n,protection,flags,fd,0);
    need(p!=MAP_FAILED && (!at || p==at),"mapped address");
    return p;
}
struct Arena {
    uint8_t *base=static_cast<uint8_t*>(map_at(nullptr,span,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1));
    ~Arena(){munmap(base,span);}
};
struct Data {
    const int expert;
    const int fd;
    explicit Data(int e):expert(e),fd(memfd_create("tesy-cpu0-record",MFD_CLOEXEC)) {
        need(fd>=0 && ftruncate(fd,window)==0,"backing fd");
    }
    ~Data(){close(fd);}
};
using Entry=std::shared_ptr<Data>;
struct Binding { Entry backing; uint64_t generation=0; };
struct Context {
    uint8_t *base=nullptr;
    llama_moe_stream *mgr=nullptr;
    std::string mode;
    std::array<Binding,40> bound{};
    std::array<uint64_t,40> held{};
    std::array<int,4> initial{};
    std::map<int,Entry> handoff;
    std::set<std::thread::id> waiting;
    bool transitioning=false;
    int number=0;
    std::atomic<size_t> copies{0},reads{0},returned{0};
    Audit *audit=nullptr;
} state;
static thread_local Entry pending;
static Entry clone_record(const Entry &src) {
    auto out=std::make_shared<Data>(src->expert);
    void *a=map_at(nullptr,window,PROT_READ,MAP_SHARED,src->fd);
    void *b=map_at(nullptr,window,PROT_WRITE,MAP_SHARED,out->fd);
    std::memcpy(b,a,window);
    need(munmap(a,window)==0 && munmap(b,window)==0,"copy view release");
    state.copies+=window;
    return out;
}
static void reset_views(ggml_context *ctx,llama_moe_stream &m,Audit &a,std::array<ggml_tensor*,6> &t) {
    ggml_backend_buffer_ptr buf(ggml_backend_cpu_buffer_from_ptr(state.base,capacity));
    need(buf && std::string(ggml_backend_buffer_name(buf.get()))=="CPU_Mapped","mapped CPU weight buffer");
    ggml_backend_buffer_set_usage(buf.get(),GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
    auto *owner=ggml_new_tensor_1d(ctx,GGML_TYPE_MXFP4,32*(capacity/17));
    need(ggml_backend_tensor_alloc(buf.get(),owner,state.base)==GGML_STATUS_SUCCESS,"owner alloc");
    const int order[]={0,2,1};
    for(int k=0;k<3;++k) {
        auto *v=ggml_view_3d(ctx,owner,width,width,40,ggml_row_size(GGML_TYPE_MXFP4,width),window,k*slab);
        need(ggml_backend_view_init(v)==GGML_STATUS_SUCCESS && v->buffer==buf.get() &&
             v->view_src==owner && v->nb[2]==window && v->data==state.base+k*slab,"weight view");
        m.layer(0)->weights.at(k).cache=v;
        a.weights[k]=t[order[k]]=v; a.addresses[k]=static_cast<uint8_t*>(v->data);a.buffers[k]=v->buffer;
    }
    m.bufs.push_back(std::move(buf));
}
static json fd_identity(int fd) {
    struct stat st{};need(fstat(fd,&st)==0,"store stat");
    auto ns=[](timespec t){return int64_t(t.tv_sec)*1000000000+t.tv_nsec;};
    return {{"dev",st.st_dev},{"ino",st.st_ino},{"size",st.st_size},
            {"mtime_ns",ns(st.st_mtim)},{"ctime_ns",ns(st.st_ctim)}};
}
bool lease_prepare(const llama_moe_stream_work &w) {
    need(!pending && w.sl==state.mgr->layer(0),"unexpected worker job");
    Entry saved;
    {
        std::lock_guard<std::mutex> g(state.mgr->mtx);
        if(state.transitioning) {
            int e=w.expert;
            if(state.mode=="WRONG" && state.number==2 && (e==45 || e==49)) e=e==45?49:45;
            saved=state.handoff.at(e);
        }
    }
    if(saved) {
        pending=state.mode=="COPY"?clone_record(saved):saved;
        return true;
    }
    auto &s=*state.mgr->expert_store;
    const auto offset=s.entries[0][w.expert].offset;
    need(offset!=UINT64_MAX && offset%stride==0 && selected.at(offset/stride)==w.expert,"store index");
    pending=std::make_shared<Data>(w.expert);
    void *dst=map_at(nullptr,window,PROT_READ|PROT_WRITE,MAP_SHARED,pending->fd);
    const auto n=pread(s.data.descriptor(),dst,window,offset);
    need(munmap(dst,window)==0,"unmap writable temporary view");
    state.reads++;
    if(n>=0)state.returned+=size_t(n);
    return n==ssize_t(window);
}
void lease_wait(const llama_moe_stream_work &w,Lock &lock,bool ok) {
    if(!ok || !state.held[w.slot])return;
    need(state.transitioning && state.held[w.slot]==state.bound[w.slot].generation,"unexpected lease");
    state.waiting.insert(std::this_thread::get_id());
    state.mgr->cv_done.notify_all();
    need(state.mgr->cv_done.wait_for(lock,std::chrono::seconds(20),[&]{return !state.held[w.slot];}),
         "last-reader notification timeout");
}
void lease_install(const llama_moe_stream_work &w) {
    auto &binding=state.bound[w.slot];
    const bool deliberately_wrong=state.mode=="WRONG" && state.number==2 && (w.expert==45 || w.expert==49);
    need(!state.held[w.slot] && pending && binding.generation+1==w.gen &&
         (pending->expert==w.expert)!=deliberately_wrong,"backing identity before publication");
    map_at(state.base+size_t(w.slot)*window,window,PROT_READ,MAP_FIXED|MAP_SHARED,pending->fd);
    binding={pending,w.gen};
    auto &a=*state.audit;
    a.slots[w.expert]=w.slot; a.generations[w.expert]=w.gen;
}
void lease_end(){ pending.reset(); }
static void alias_hold_locked(Audit &a) {
    std::set<int> active(a.logical.begin(),a.logical.end());
    for(int e:active){
        const int slot=a.layer->expert_slot.at(e);
        auto &b=state.bound[slot];
        need(a.layer->slot_state[slot]==LLAMA_MOE_STREAM_SLOT_RESIDENT && !a.layer->slot_claimed[slot] &&
             a.layer->slot_gen[slot]==b.generation && b.backing && !state.held[slot],"graph input lease");
        state.held[slot]=b.generation;
    }
}
static json bindings(llama_moe_stream_layer &l) {
    json all=json::array();
    for(int e:selected) {int i=l.expert_slot.at(e); all.push_back({e,i,l.slot_gen.at(i)});}
    return all;
}
static json handover(llama_moe_stream &m,int step) {
    Lock lock(m.mtx);auto &l=*m.layer(0);
    need(step==++state.number && m.q_demand.empty() && !m.load_failed &&
         state.handoff.empty() && !state.transitioning,"handover start");
    std::array<int,4> before{},next{};
    for(int i=0;i<4;++i) {
        int e=selected[i]; int slot=l.expert_slot.at(e);
        before[i]=slot;
        if(step==1)state.initial[i]=slot;
        auto &b=state.bound[slot];
        need(l.slot_state[slot]==LLAMA_MOE_STREAM_SLOT_RESIDENT && !l.slot_claimed[slot] &&
             l.slot_gen[slot]==b.generation && b.backing->expert==e && state.held[slot]==b.generation,
             "old-generation handoff proof");
        state.handoff[e]=state.mode=="COPY"?clone_record(b.backing):b.backing;
    }
    // Atomic permutation of already resident identities. A sequential reserve would erase
    // the new association of a source that occupies the next destination in the cycle.
    for(int i=0;i<4;++i){l.expert_slot.erase(selected[i]); l.slot_expert[before[i]]=-1;}
    state.transitioning=true;state.waiting.clear();
    for(int i=0;i<4;++i){
        const int dest=step==1?state.initial[(i+1)%4]:state.initial[i]; next[i]=dest;
        m.reserve_slot_locked(l,selected[i],dest);
        m.q_demand.push_back({&l,selected[i],dest,l.slot_gen[dest]});
    }
    m.cv_work.notify_all();
    need(m.cv_done.wait_for(lock,std::chrono::seconds(25),[]{return state.waiting.size()==4;}),
         "four live workers behind real-reader leases");
    for(int slot:next)
        need(l.slot_claimed[slot] && l.slot_state[slot]==LLAMA_MOE_STREAM_SLOT_LOADING &&
             l.slot_gen[slot]==state.held[slot]+1 && state.bound[slot].generation==state.held[slot],
             "worker crossed pending reader");
    state.held.fill(0); m.cv_done.notify_all();
    need(m.cv_done.wait_for(lock,std::chrono::seconds(20),[&]{
        return m.load_failed || std::all_of(next.begin(),next.end(),[&](int slot){
            return l.slot_state[slot]==LLAMA_MOE_STREAM_SLOT_RESIDENT;});
    }),"handover completion timeout");
    need(!m.load_failed && m.q_demand.empty(),"handover worker rejected");
    for(int i=0;i<4;++i){
        const auto &b=state.bound[next[i]];
        need(!l.slot_claimed[next[i]] && l.slot_gen[next[i]]==b.generation && l.expert_slot.at(selected[i])==next[i],
             "committed handoff");
        if(state.mode!="COPY" && !(state.mode=="WRONG" && step==2 && i<2))
            need(b.backing==state.handoff.at(selected[i]),"alias acquired different physical object");
        if(state.mode=="COPY")need(b.backing!=state.handoff.at(selected[i]),"control missing copy");
    }
    state.handoff.clear();state.transitioning=false;
    return {{"workers",4},{"reservations",4},{"last_reader",true},{"sources",before},{"destinations",next}};
}
