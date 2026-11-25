// Model-free C291 worker integration. The real FIFO, claim, validation and publication run in the pinned TU.
#include "lease.h"
#include "c291-expert-store.h"
#include "ggml-backend.h"
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <set>
#include <map>

using json = nlohmann::json;
constexpr size_t width=2880, slots=40, slab=4406400, window=13221888, page=4096;
constexpr size_t owner_bytes=((slots*window+16)/17)*17;
constexpr size_t va_span=((owner_bytes+page-1)/page)*page;

void require(bool ok, const char *why) {
    if (!ok) { std::cerr << "FAIL " << why << std::endl; std::_Exit(1); }
}
void *mapping(void *where,size_t n,int prot,int flags,int fd) {
    auto *p=mmap(where,n,prot,flags,fd,0);
    require(p!=MAP_FAILED && (!where || p==where),"mmap bounds");
    return p;
}
int memfile(const char *name,size_t bytes) {
    const int fd=memfd_create(name,MFD_CLOEXEC);
    require(fd>=0 && ftruncate(fd,bytes)==0,"memfd extent");
    return fd;
}
struct Record {
    int key, fd;
    explicit Record(int k):key(k),fd(memfile("tesy-immutable-expert",window)) {}
    ~Record() { close(fd); }
    ino_t inode() const { struct stat st{}; require(fstat(fd,&st)==0,"backing identity"); return st.st_ino; }
    size_t bytes() const { struct stat st{}; require(fstat(fd,&st)==0,"backing size"); return size_t(st.st_blocks)*512; }
};
using Ref=std::shared_ptr<Record>;
struct Bound { Ref record; uint64_t gen=0; };
struct Fixture {
    llama_moe_stream *mgr=nullptr;
    llama_moe_stream_layer *layer=nullptr;
    uint8_t *base=nullptr;
    std::string mode;
    int source=-1;
    std::array<Bound,slots> bound{};
    std::mutex bank_mutex;
    Ref retained;
    uint64_t retained_gen=0;
    std::map<std::pair<int,uint64_t>,int> leases;
    std::atomic<int> reads{0}, hits{0};
    std::atomic<size_t> returned{0};
    bool group=false, proceed=false, waiting=false;
    std::set<std::thread::id> workers;
    std::array<bool,2> reader_ready{}, reader_go{}, reader_ok{}, reader_done{};
    json publications=json::array();
} s;
thread_local Ref prepared;
using Lock=std::unique_lock<std::mutex>;

void notify() { s.mgr->cv_done.notify_all(); }
template<class F> void until(Lock &lock,F predicate) {
    require(s.mgr->cv_done.wait_for(lock,std::chrono::seconds(15),predicate),"condition timeout");
}
bool matches(const llama_moe_stream_work &w) {
    return w.sl->slot_gen[w.slot]==w.gen && w.sl->slot_expert[w.slot]==w.expert;
}
bool lease_prepare(const llama_moe_stream_work &w) {
    require(!prepared && w.slot>=0 && w.slot<4 && w.expert>=0 && w.expert<5,"job range");
    {
        Lock lock(s.mgr->mtx);
        if (s.group) {
            s.workers.insert(std::this_thread::get_id());
            notify();
            until(lock,[]{return s.proceed;});
        }
    }
    {
        std::lock_guard<std::mutex> lock(s.bank_mutex);
        if (s.retained && s.retained->key==w.expert) {
            require(w.slot==0 && w.gen==3 && s.retained_gen==1,"retained source generation");
            prepared=s.retained;
            ++s.hits;
            return true;
        }
    }
    prepared=std::make_shared<Record>(w.expert);
    void *dst=mapping(nullptr,window,PROT_READ|PROT_WRITE,MAP_SHARED,prepared->fd);
    const auto n=pread(s.source,dst,window,off_t(w.expert)*window);
    ++s.reads;
    require(n>=0 && munmap(dst,window)==0,"source read or writable alias cleanup");
    s.returned+=size_t(n);
    return n==ssize_t(window);
}
void lease_wait(const llama_moe_stream_work &w,Lock &lock,bool ok) {
    const auto prior=s.bound[w.slot].gen;
    auto released=[&]{return !s.leases.count({w.slot,prior}) || !matches(w) || s.mgr->shutting_down;};
    if (ok && s.mode!="early" && !released()) {
        s.waiting=true; notify();
        until(lock,released);
    }
}
void lease_install(const llama_moe_stream_work &w) {
    auto &old=s.bound[w.slot];
    require(matches(w) && w.sl->slot_claimed[w.slot]==0 && prepared && prepared->key==w.expert,
            "invalid install before publication");
    require(!s.leases.count({w.slot,old.gen}) || s.mode=="early","unreleased lease");
    if(old.record && old.record->key==0 && s.mode!="no-bank") {
        require(w.slot==0 && old.gen==1 && w.gen==2,"unexpected eviction generation");
        std::lock_guard<std::mutex> lock(s.bank_mutex);
        s.retained=old.record; s.retained_gen=old.gen;
    }
    mapping(s.base+w.slot*window,window,PROT_READ,MAP_FIXED|MAP_SHARED,prepared->fd);
    old={prepared,w.gen};
    s.publications.push_back({w.slot,w.expert,w.gen});
}
void lease_end() { prepared.reset(); }

// The source writer repeats an explicitly generated 256-byte pattern per component. The consumer
// computes every expected coordinate independently from its logical expert, role and byte index.
void source_data() {
    s.source=memfile("tesy-synthetic-read-source",5*window);
    auto *p=static_cast<uint8_t*>(mapping(nullptr,5*window,PROT_WRITE,MAP_SHARED,s.source));
    for (unsigned e=0;e<5;++e) for (unsigned k=0;k<3;++k) {
        std::array<uint8_t,256> pattern{};
        uint8_t val=uint8_t(17+29*e+61*k);
        for(auto &b:pattern){b=val;val+=13;}
        auto *part=p+e*window+k*slab;
        for(size_t i=0;i<slab;i+=pattern.size())
            std::memcpy(part+i,pattern.data(),std::min(slab-i,pattern.size()));
    }
    require(munmap(p,5*window)==0,"source seal");
}
bool valid_payload(int slot,int key) {
    size_t bad=0;
    for(int k=0;k<3;++k) {
        auto *v=s.layer->weights[k].cache;
        auto *p=static_cast<const uint8_t*>(v->data)+slot*v->nb[2];
        require(v->type==GGML_TYPE_MXFP4 && v->nb[2]==window && p==s.base+slot*window+k*slab,
                "consumer stride/address");
        for(size_t i=0;i<slab;++i) bad+=(p[i]!=uint8_t(17+key*29+k*61+i*13));
    }
    return bad==0;
}
bool release_token(int slot,uint64_t generation) {
    auto it=s.leases.find({slot,generation});
    if(it==s.leases.end())return false;
    if(--it->second==0)s.leases.erase(it);
    notify(); return true;
}
bool acquire_token(int slot,int expert,uint64_t generation) {
    const auto &b=s.bound[slot];
    if (!b.record || b.record->key!=expert || b.gen!=generation ||
        s.layer->slot_state[slot]!=LLAMA_MOE_STREAM_SLOT_RESIDENT ||
        s.layer->slot_gen[slot]!=generation || s.layer->slot_expert[slot]!=expert)
        return false;
    ++s.leases[{slot,generation}]; return true;
}
void reader(int id) {
    Lock lock(s.mgr->mtx);
    require(acquire_token(0,0,1),"reader acquired wrong generation");
    lock.unlock();
    require(valid_payload(0,0),"initial reader gold");
    lock.lock(); s.reader_ready[id]=true; notify();
    until(lock,[&]{return s.reader_go[id];});
    lock.unlock();
    const bool ok=valid_payload(0,0);
    lock.lock(); s.reader_ok[id]=ok;
    require(release_token(0,1),"release generation");
    s.reader_done[id]=true; notify();
}
void reserve(int key,int slot) {
    auto &m=*s.mgr;
    std::array<uint8_t,slots> keep{}; keep.fill(1); keep[slot]=0;
    require(m.pick_victim_locked(*s.layer,keep.data())==slot,"native eligible victim");
    m.reserve_slot_locked(*s.layer,key,slot);
    m.q_demand.push_back({s.layer,key,slot,s.layer->slot_gen[slot]});
    m.cv_work.notify_all();
}
bool resident(int slot,int key,int gen) {
    return s.layer->slot_state[slot]==LLAMA_MOE_STREAM_SLOT_RESIDENT &&
           s.layer->slot_expert[slot]==key && s.layer->slot_gen[slot]==uint64_t(gen) &&
           !s.layer->slot_claimed[slot] && s.bound[slot].gen==uint64_t(gen);
}
size_t backing_bytes() {
    std::set<Record*> unique;
    for (const auto &b:s.bound) if (b.record) unique.insert(b.record.get());
    if (s.retained) unique.insert(s.retained.get());
    size_t bytes=0;
    for (auto *r:unique) bytes+=r->bytes();
    require(bytes==unique.size()*window,"physical backing hole or duplicate");
    return bytes;
}
void bind_views(llama_moe_stream &mgr,ggml_context *ctx) {
    s.base=static_cast<uint8_t*>(mapping(nullptr,va_span,PROT_NONE,MAP_ANONYMOUS|MAP_PRIVATE,-1));
    ggml_backend_buffer_ptr buffer(ggml_backend_cpu_buffer_from_ptr(s.base,owner_bytes));
    require(buffer && std::string(ggml_backend_buffer_name(buffer.get()))=="CPU_Mapped" &&
            ggml_backend_buffer_get_base(buffer.get())==s.base,"CPU_Mapped weights");
    ggml_backend_buffer_set_usage(buffer.get(),GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
    auto *owner=ggml_new_tensor_1d(ctx,GGML_TYPE_MXFP4,32*(owner_bytes/17));
    require(ggml_backend_tensor_alloc(buffer.get(),owner,s.base)==GGML_STATUS_SUCCESS,"owner");
    const std::array<const char *,3> roles={"gate","down","up"};
    for(int k=0;k<3;++k) {
        auto *meta=ggml_new_tensor_3d(ctx,GGML_TYPE_MXFP4,width,width,128);
        ggml_format_name(meta,"blk.0.ffn_%s_exps.weight",roles[k]);
        mgr.create_cache_tensor(0,ggml_backend_cpu_buffer_type(),meta,0,k*128*slab);
        auto *v=ggml_view_3d(ctx,owner,width,width,slots,ggml_row_size(GGML_TYPE_MXFP4,width),window,k*slab);
        require(ggml_backend_view_init(v)==GGML_STATUS_SUCCESS && v->buffer==buffer.get(),"backing of view");
        auto &wt=mgr.layer(0)->weights.at(k);
        require(wt.nb_expert==slab && v->view_src==owner,"C291 weight geometry");
        wt.cache=v;
    }
    mgr.bufs.emplace_back(std::move(buffer));
    s.layer=mgr.layer(0);
}
json exercise(llama_moe_stream &mgr) {
    s.mgr=&mgr; auto &m=mgr; auto &l=*s.layer;
    Lock lock(m.mtx);
    m.start_workers_locked(); require(m.workers.size()==4,"four native workers");
    reserve(0,0); until(lock,[]{return resident(0,0,1);});
    const ino_t original=s.bound[0].record->inode();
    json report;
    if(s.mode=="short" || s.mode=="stale") {
        s.group=true; reserve(1,0);
        until(lock,[]{return s.workers.size()==1;});
        require(l.slot_claimed[0] && l.slot_gen[0]==2,"fault claim");
        if(s.mode=="short")require(ftruncate(s.source,2*window-page)==0,"truncate test source");
        else ++l.slot_gen[0]; // inject obsolete completion while worker owns the previous identity
        s.proceed=true; notify();
        until(lock,[&]{return m.load_failed;});
        require(l.slot_state[0]==LLAMA_MOE_STREAM_SLOT_LOADING && s.bound[0].gen==1 &&
                s.bound[0].record->inode()==original && valid_payload(0,0) &&
                l.slot_gen[0]==(s.mode=="short"?2u:3u) && l.slot_claimed[0]==(s.mode=="stale") &&
                s.publications.size()==1 && s.reads==2 && s.hits==0 &&
                s.returned==2*window-(s.mode=="short"?page:0),"error published or wrong old generation");
        report["sticky_load_failed"]=true;
        report["installed_generation"]=s.bound[0].gen;
        report["failed_ticket_state"]={l.slot_expert[0],l.slot_gen[0],l.slot_state[0],l.slot_claimed[0]};
    } else {
        std::array<std::thread,2> readers{std::thread(reader,0),std::thread(reader,1)};
        until(lock,[]{return s.reader_ready[0] && s.reader_ready[1];});
        require(!release_token(0,99) && s.leases.at({0,1})==2,"stale release accepted");
        s.group=true;
        for(int i=0;i<4;++i)reserve(i+1,i);
        until(lock,[]{return s.workers.size()==4;});
        require(!acquire_token(0,0,1) && !acquire_token(0,1,2) && s.leases.at({0,1})==2,
                "late reader entered reserved slot");
        report["late_reader_rejected"]=true;
        for(int i=0;i<4;++i)
            require(l.slot_claimed[i] && l.slot_state[i]==LLAMA_MOE_STREAM_SLOT_LOADING &&
                    l.slot_gen[i]==(i==0?2u:1u),"simultaneous claim");
        s.proceed=true; notify();
        until(lock,[]{return resident(1,2,1) && resident(2,3,1) && resident(3,4,1) &&
                              (s.mode=="early"?resident(0,1,2):s.waiting);});
        for(int i=1;i<4;++i)require(valid_payload(i,i+1),"independent worker payload");
        if(s.mode!="early")require(l.slot_claimed[0] && s.bound[0].gen==1,"old reader lost generation");
        for(int i=0;i<2;++i) {
            s.reader_go[i]=true; notify();
            until(lock,[&]{return s.reader_done[i];});
            require(s.reader_ok[i]==(s.mode!="early"),"early overwrite not discriminated");
            if(i==0 && s.mode!="early")
                require(l.slot_claimed[0] && l.slot_state[0]==LLAMA_MOE_STREAM_SLOT_LOADING &&
                        s.leases.at({0,1})==1 && s.bound[0].record->inode()==original,"last reader barrier");
        }
        until(lock,[]{return resident(0,1,2);});
        lock.unlock(); for(auto &r:readers)r.join(); lock.lock();
        require(valid_payload(0,1) && s.bound[0].record->inode()!=original,"replacement payload");
        report["replacement_unique_backing_bytes"]=backing_bytes();
        require(backing_bytes()==(s.mode=="no-bank"?4:5)*window,"replacement backing count");
        s.group=false; reserve(0,0); until(lock,[]{return resident(0,0,3);});
        require(valid_payload(0,0) && s.hits==(s.mode=="no-bank"?0:1) &&
                s.reads==(s.mode=="no-bank"?6:5) && s.returned==s.reads*window &&
                (s.bound[0].record->inode()==original)==(s.mode!="no-bank") &&
                s.publications.size()==6 && !m.load_failed && m.q_demand.empty(),"restoration mismatch");
        report["restored_original_backing"]=s.mode!="no-bank";
        report["restored_unique_backing_bytes"]=backing_bytes();
        require(backing_bytes()==4*window,"restoration backing count");
        report["stale_release_rejected"]=true;
        report["independent_old_reader_checks"]=s.reader_ok;
        report["three_other_slots_published_with_two_old_readers"]=true;
        report["last_reader_blocked_replacement"]=s.waiting;
    }
    report["concurrent_workers"]=s.workers.size();
    report["reads"]=s.reads.load(); report["source_bytes"]=s.returned.load(); report["bank_hits"]=s.hits.load();
    report["publications_slot_expert_gen"]=s.publications;
    return report;
}
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    s.mode=argv[1];
    require(s.mode=="alias" || s.mode=="no-bank" || s.mode=="early" || s.mode=="short" ||
            s.mode=="stale","mode");
    require(sysconf(_SC_PAGESIZE)==page,"native page");
    source_data(); json report;
    ggml_context_ptr ctx(ggml_init({2u<<20,nullptr,true})); require(bool(ctx),"view context");
    {
        llama_moe_stream mgr(1,slots,4,true);
        bind_views(mgr,ctx.get());
        report=exercise(mgr);
    }
    require(munmap(s.base,va_span)==0 && close(s.source)==0,"post-join cleanup");
    report["mode"]=s.mode; report["manager_destructor_returned"]=true;
    report["status"]="PASS_EXPECTED_MANAGER_OBSERVATION";
    std::cout<<report.dump()<<std::endl;
}
