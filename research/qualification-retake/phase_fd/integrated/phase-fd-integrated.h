// Private two-TU C269 overlay. Never add members to the shipped manager or work item.
#pragma once
#include "llama-moe-stream.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <stdexcept>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

namespace pfj __attribute__((visibility("hidden"))) {
enum Kind : int {
    ENTER=1, RETURN, TILE, TILE_RETURN, SLOT, QUEUED_AT_CUT, FILE_ID, WEIGHT,
    REMAP_BEGIN, DEMAND, RESERVE, ENQUEUE, DISPATCH, SKIP, READ, SET, PUBLISH,
    LOAD_FAIL, BARRIER_ENTER, BARRIER_RETURN, VICTIM_WAIT, VICTIM_RESUME,
    REMAP_END, WORKER_EXIT, END, PENDING_AT_RETURN, RANKS, CANCEL_QUEUED
};
constexpr size_t capacity = 262144;
struct Header {
    char magic[8];
    uint64_t version, record_bytes, capacity, attempted, saved, flags, reserved;
};
struct Record {
    uint64_t ns, begin_ns, gen;
    int64_t a, b, c;
    int32_t kind, call, tile, wave, layer, expert, slot, worker, component, fd, error, reserved;
};
static_assert(sizeof(Header)==64 && sizeof(Record)==96 && __BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__);
constexpr size_t allocation = sizeof(Header) + capacity*sizeof(Record);

struct Site {
    int call=0, tile=-1, wave=-1, layer=-1, expert=-1, slot=-1, worker=-1, component=-1, fd=-1;
    uint64_t gen=0;
};
struct Journal {
    llama_moe_stream *manager;
    const char *trigger;
    int file;
    Header *header;
    std::atomic<uint64_t> count{0};
    std::atomic<bool> live{false}, invalid{false};
    int calls=0;
    Site origin[36][40]{};
    int components[36][3]{};
};
inline Journal *journal = nullptr; // set before native threads start, cleared only after join
inline thread_local Site host, job;
inline thread_local int worker_id=-1, component_index=-1;
inline thread_local bool computing=false;

inline uint64_t now() {
    timespec t{};
    if (clock_gettime(CLOCK_MONOTONIC, &t) != 0) std::abort();
    return uint64_t(t.tv_sec)*1000000000u + t.tv_nsec;
}
inline bool active() {
    return journal && journal->live.load(std::memory_order_acquire);
}
inline bool indices(int l, int s) { return l>=0 && l<36 && s>=0 && s<40; }

inline void emit(Kind kind, Site s, int64_t a=0, int64_t b=0, int64_t c=0,
                 uint64_t begin=0, uint64_t end=0, int error=0) {
    if (!active()) return;
    const uint64_t ns=end ? end : now();
    const auto i=journal->count.fetch_add(1, std::memory_order_relaxed);
    if (i>=capacity) return;
    auto *records=reinterpret_cast<Record *>(journal->header+1);
    records[i]={ns,begin,s.gen,a,b,c,kind,s.call,s.tile,s.wave,s.layer,s.expert,s.slot,
                s.worker,s.component,s.fd,error,0};
}
inline void install(llama_moe_stream *mgr) {
    const char *file=std::getenv("TESY_PHASE_FD_FILE");
    if (!file) return;
    const char *trigger=std::getenv("TESY_PHASE_FD_TRIGGER");
    if (journal || file[0]!='/' || (trigger && (trigger[0]!='/' || !std::strcmp(file,trigger))))
        throw std::runtime_error("invalid PFJ1 profile");
    auto j=std::make_unique<Journal>();
    j->manager=mgr;
    j->trigger=trigger;
    const int fd=::open(file,O_CREAT|O_EXCL|O_NOFOLLOW|O_RDWR|O_CLOEXEC,0600);
    if (fd<0) throw std::runtime_error("PFJ1 new output required");
    if (ftruncate(fd,allocation)!=0) { close(fd); throw std::runtime_error("PFJ1 capacity"); }
    void *mapping=mmap(nullptr,allocation,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if (mapping==MAP_FAILED) { close(fd); throw std::runtime_error("PFJ1 mmap"); }
    j->file=fd;
    j->header=static_cast<Header *>(mapping);
    *j->header={{'T','E','S','Y','P','F','1','\0'},1,sizeof(Record),capacity,0,0,0,0};
    journal=j.release();
}
inline Site slot_site(Site s, const llama_moe_stream_layer &sl, int index) {
    s.layer=sl.il; s.slot=index; s.expert=sl.slot_expert[index]; s.gen=sl.slot_gen[index];
    return s;
}
inline void queue(const llama_moe_stream &mgr, Kind kind, Site s, int cut) {
    int index=0;
    for (const auto &w:mgr.q_demand) {
        s.layer=w.sl->il; s.slot=w.slot; s.expert=w.expert; s.gen=w.gen;
        emit(kind,s,index++,cut);
    }
}
inline int claims(const llama_moe_stream &mgr) {
    int n=0;
    for (const auto &sl:mgr.layers) if(sl) for(auto value:sl->slot_claimed) n+=value;
    return n;
}
inline void bind_components(llama_moe_stream &mgr) {
    const char *names[]={"gate","down","up"};
    for (const auto &sl:mgr.layers) {
        if (!sl || sl->il<0 || sl->il>=36 || sl->weights.size()!=3) {
            journal->invalid=true;
            continue;
        }
        unsigned seen=0;
        for(size_t i=0;i<3;++i) {
            int role=-1;
            for(int k=0;k<3;k++) {
                char name[96];
                std::snprintf(name,sizeof(name),"blk.%d.ffn_%s_exps.weight.stream_cache",sl->il,names[k]);
                if(sl->weights[i].cache && !std::strcmp(sl->weights[i].cache->name,name)) role=k;
            }
            journal->components[sl->il][i]=role;
            if(role>=0) seen |= 1u<<role;
        }
        if(seen!=7) journal->invalid=true;
    }
}
inline void snapshot(llama_moe_stream &mgr, Site boundary) {
    if (mgr.layers.size()!=36 || mgr.n_slots!=40 || mgr.n_io_threads!=4 || !mgr.use_direct_io)
        journal->invalid=true;
    for(const auto &f:mgr.files) {
        struct stat st{};
        auto s=boundary;
        s.fd=f->file_id();
        int flags=fcntl(s.fd,F_GETFL);
        if (fstat(s.fd,&st)!=0 || flags<0 || !(flags&O_DIRECT)) journal->invalid=true;
        emit(FILE_ID,s,st.st_dev,st.st_ino,flags);
    }
    for (const auto &sl:mgr.layers) {
        if (!sl || sl->il<0 || sl->il>=36 || sl->n_slots!=40 || sl->slot_expert.size()!=40 ||
            sl->weights.size()!=3) { journal->invalid=true; continue; }
        for (int s=0;s<40;++s)
            emit(SLOT,slot_site(boundary,*sl,s),sl->slot_state[s],sl->slot_claimed[s]);
        for(size_t i=0;i<3;i++) {
            const auto &wt=sl->weights[i];
            auto s=boundary;
            s.layer=sl->il;
            s.component=journal->components[s.layer][i];
            if(s.component<0 || wt.file_idx>=mgr.files.size()) { journal->invalid=true; continue; }
            s.fd=mgr.files[wt.file_idx]->file_id();
            emit(WEIGHT,s,wt.offs,wt.nb_expert,wt.file_idx);
        }
    }
    queue(mgr,QUEUED_AT_CUT,boundary,1);
}
inline void enter(llama_moe_stream *mgr, int n, int p0, int p1) {
    if (!journal) return;
    if (mgr!=journal->manager || host.call) { journal->invalid=true; return; }
    if (!active() && journal->trigger && access(journal->trigger,F_OK)!=0) {
        if(errno!=ENOENT) journal->invalid=true;
        return;
    }
    const auto start=now();
    std::lock_guard<std::mutex> lock(mgr->mtx);
    const bool first=!active();
    host=Site{}; host.call=++journal->calls;
    // Bind component indices before publishing live to workers in flight at the cut.
    if(first) bind_components(*mgr);
    journal->live.store(true,std::memory_order_release);
    emit(ENTER,host,n,p0,p1,start);
    if(first) snapshot(*mgr,host);
}
inline void returned(llama_moe_stream *mgr, int rc) {
    if (!active() || !host.call) return;
    const auto start=now();
    std::lock_guard<std::mutex> lock(mgr->mtx);
    auto boundary=host; boundary.tile=-1;
    emit(RETURN,boundary,rc,mgr->q_demand.size(),claims(*mgr),start);
    for(const auto &sl:mgr->layers) if(sl) for(size_t s=0;s<sl->slot_state.size();++s)
        if(sl->slot_claimed[s] || sl->slot_state[s]==LLAMA_MOE_STREAM_SLOT_LOADING)
            emit(PENDING_AT_RETURN,slot_site(boundary,*sl,s),sl->slot_state[s],sl->slot_claimed[s]);
    queue(*mgr,QUEUED_AT_CUT,boundary,2);
    if(computing || rc) journal->invalid=true;
    host=Site{};
}
inline void graph(llama_moe_stream *mgr, int n, int p0, int p1) {
    if(!active()) return;
    if(!host.call || computing || mgr!=journal->manager) journal->invalid=true;
    host.tile=host.tile<0 ? 1 : host.tile+1;
    computing=true;
    emit(TILE,host,n,p0,p1);
}
inline void graph_return(int status) {
    if(!active()) return;
    if(!computing || status) journal->invalid=true;
    emit(TILE_RETURN,host,status);
    computing=false;
}
inline void consumer(llama_moe_stream_layer &sl,int wave,const int32_t *ids,int64_t n,int ranks) {
    if(!active()) return;
    if(sl.mgr!=journal->manager || !computing || !host.call || host.tile<1 ||
       host.layer!=-1 || ranks!=4 || n<0 || n%4) { journal->invalid=true; return; }
    host.layer=sl.il; host.wave=wave;
    emit(REMAP_BEGIN,host,n/4,ranks);
    if(wave<=0) for(int64_t i=0;i<n;i+=4) {
        uint32_t packed=0;
        for(int k=0;k<4;k++) {
            if(ids[i+k]<0 || ids[i+k]>=128) journal->invalid=true;
            packed |= static_cast<uint32_t>(ids[i+k]&255)<<(8*k);
        }
        emit(RANKS,host,packed,i/4);
    }
}
inline void finish_consumer() {
    if(!active()) return;
    emit(REMAP_END,host);
    host.wave=-1; host.layer=-1;
}
inline void reserve(llama_moe_stream_layer &sl,int slot,int victim) {
    if(!active()) return;
    if(!indices(sl.il,slot) || !computing || host.layer!=sl.il) { journal->invalid=true; return; }
    auto s=slot_site(host,sl,slot);
    journal->origin[sl.il][slot]=s;
    emit(RESERVE,s,victim);
}
inline void enqueue(const llama_moe_stream_layer &sl,int slot,int why) {
    if(active()) emit(ENQUEUE,slot_site(host,sl,slot),why);
}
inline void demands(const llama_moe_stream_layer &sl) {
    if(active()) for(auto slot:sl.demand_slots) emit(DEMAND,slot_site(host,sl,slot));
}
inline void dispatched(const llama_moe_stream_work &w,bool accepted) {
    if(!journal) return;
    Site s{}; // call zero is work that predates the captured window
    if(indices(w.sl->il,w.slot) && journal->origin[w.sl->il][w.slot].gen==w.gen)
        s=journal->origin[w.sl->il][w.slot];
    s.layer=w.sl->il; s.expert=w.expert; s.slot=w.slot; s.gen=w.gen; s.worker=worker_id;
    emit(accepted?DISPATCH:SKIP,s);
    if(accepted) job=s;
}
inline void component(const llama_moe_stream_layer &sl,size_t i,int fd) {
    if(!journal) return;
    component_index=static_cast<int>(i);
    job.fd=fd;
    if(sl.il!=job.layer) journal->invalid=true;
}
inline Site current_component() {
    Site s=job;
    if(active() && s.layer>=0 && s.layer<36 && component_index>=0 && component_index<3)
        s.component=journal->components[s.layer][component_index];
    return s;
}
inline ssize_t read(int fd,void *dst,size_t requested,off_t offset) {
    // Startup probe uses the same function but no worker job.
    if(!journal || job.worker<0) return ::pread(fd,dst,requested,offset);
    const uint64_t begin=active()?now():0;
    const ssize_t n=::pread(fd,dst,requested,offset);
    const int error=errno;
    if(active()) {
        auto s=current_component(); s.fd=fd;
        if(fd!=job.fd) journal->invalid=true;
        emit(READ,s,offset,requested,n,begin,now(),n<0?error:0);
    }
    errno=error;
    return n;
}
inline void loaded(bool ok) {
    if(!journal) return;
    job.fd=-1; job.component=-1;
    emit(ok?PUBLISH:LOAD_FAIL,job);
    job=Site{}; component_index=-1;
}
inline void finish(llama_moe_stream *mgr) {
    if(!journal) return;
    if(mgr!=journal->manager) { journal->invalid=true; return; }
    Site s{};
    emit(END,s,mgr->q_demand.size(),claims(*mgr),mgr->load_failed);
    const auto n=journal->count.load();
    auto *h=journal->header;
    h->attempted=n; h->saved=std::min<uint64_t>(n,capacity);
    h->flags=1u | (n>capacity?2u:0u) | ((!active() || journal->invalid.load())?4u:0u);
    const size_t used=sizeof(Header)+h->saved*sizeof(Record);
    int fd=journal->file;
    if(msync(h,used,MS_SYNC)!=0 || munmap(h,allocation)!=0 || ftruncate(fd,used)!=0 || close(fd)!=0)
        std::abort();
    delete journal;
    journal=nullptr;
}
} // namespace pfj
