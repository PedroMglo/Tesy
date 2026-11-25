#include "llama-moe-stream.h"
#include "c305-cpu-stage.h"
#include "c291-expert-store.h"
#include "fixture_observer.h"
#include <sys/syscall.h>
#include <zlib.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <thread>

using json = nlohmann::json;
using Stage = c305_cpu_stage;
using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;

namespace {
constexpr size_t region = ((128 * Stage::slab + 4095) / 4096) * 4096;
struct Job { int expert=-1, slot=-1; uint64_t generation=0, ticket=0; };
struct Event {
    const char *kind;
    long tid;
    int worker, component;
    int64_t ns;
    Job job;
};
thread_local int ordinal=-1;
thread_local Job service;
std::array<Event,256> journal;
size_t written=0;
bool observing=false;
std::atomic<bool> active{false};
std::mutex journal_mutex;
int primary_fd=-1, stage_fd=-1;
size_t stage_align=0;
std::mutex gate_mutex;
std::condition_variable gate_changed;
std::array<bool,5> arrived{}, released{};
std::array<std::array<int,3>,5> issued{}, delivered{};

void check(bool ok, const char *why) {
    if (!ok) { std::cerr << "FAIL: " << why << std::endl; std::_Exit(1); }
}
void await_read(int expert) {
    std::unique_lock<std::mutex> lock(gate_mutex);
    check(gate_changed.wait_for(lock, 10s, [&]{return arrived.at(expert);}), "read gate not reached");
}
void release_read(int expert) {
    std::lock_guard<std::mutex> lock(gate_mutex);
    check(arrived.at(expert) && !released.at(expert), "invalid release");
    released.at(expert)=true;
    gate_changed.notify_all();
}
template<class Predicate>
void await_manager(llama_moe_stream &mgr, Predicate predicate, const char *why) {
    const auto deadline=Clock::now()+10s;
    std::unique_lock<std::mutex> lock(mgr.mtx);
    // Finish's condition changes under mtx without a cv_done signal at entry.
    while (!predicate()) {
        check(!mgr.load_failed && Clock::now()<deadline, why);
        mgr.cv_done.wait_until(lock, std::min(deadline, Clock::now()+10ms));
    }
}
}

namespace ob {
void note(const char *kind, int expert, int slot, uint64_t generation, uint64_t ticket, int component) {
    if (!observing || (!active.load() && std::strcmp(kind,"worker_enter")!=0)) return;
    std::lock_guard<std::mutex> lock(journal_mutex);
    check(written<journal.size(),"observer overflow");
    const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
    journal[written++]={kind,syscall(SYS_gettid),ordinal,component,ns,{expert,slot,generation,ticket}};
}
void worker(int identity) { ordinal=identity; note("worker_enter"); }
void stage(int expert,uint64_t ticket) {
    service={expert,-1,0,ticket};
    note("stage_start",expert,-1,0,ticket);
}
void primary(int kind,int expert,int slot,uint64_t generation,int component) {
    if (kind==5) service={expert,slot,generation,0};
    const char *label=nullptr;
    switch (kind) {
    case 5: label="primary_accept"; break;
    case 8: label="copy_begin"; break;
    case 9: label="copy_end"; break;
    case 10: label="primary_publish"; break;
    case 11: label="barrier_begin"; break;
    case 12: label="barrier_end"; break;
    default: return;
    }
    note(label,expert,slot,generation,0,component);
}
}

// GNU ld redirects only references from this executable's objects. This calls
// the real pread once, outside the manager mutex, with its original arguments.
extern "C" ssize_t __real_pread(int,void*,size_t,off_t);
extern "C" ssize_t __wrap_pread(int fd,void *dst,size_t bytes,off_t offset) {
    if (!active.load() || (fd!=primary_fd && fd!=stage_fd)) return __real_pread(fd,dst,bytes,offset);
    const bool staged=fd==stage_fd;
    const int k=static_cast<int>(size_t(offset)/region), e=service.expert;
    check(k>=0 && k<3 && ((staged && e>=1 && e<=3) || (!staged && e==4)), "unexpected read identity");
    const size_t align=staged ? stage_align : 4096;
    const size_t logical=size_t(k)*region+size_t(e)*Stage::slab;
    const size_t head=logical%align;
    check(offset>=0 && size_t(offset)==logical-head && bytes==(head+Stage::slab+align-1)/align*align,
          "unexpected aligned range");
    ob::note(staged?"stage_read_begin":"direct_read_begin",e,service.slot,service.generation,service.ticket,k);
    {
        std::unique_lock<std::mutex> lock(gate_mutex);
        check(++issued.at(e).at(k)==1,"duplicate read");
        if (k==0) {
            arrived.at(e)=true;
            gate_changed.notify_all();
            check(gate_changed.wait_for(lock,10s,[&]{return released.at(e);}),"reader release timeout");
        }
    }
    const auto result=__real_pread(fd,dst,bytes,offset);
    check(result==ssize_t(bytes),"short/error synthetic positional read");
    {
        std::lock_guard<std::mutex> lock(gate_mutex);
        ++delivered.at(e).at(k);
    }
    ob::note(staged?"stage_read_end":"direct_read_end",e,service.slot,service.generation,service.ticket,k);
    return result;
}

int main(int argc,char **argv) {
    check(argc==4 && (std::string(argv[1])=="ON" || std::string(argv[1])=="OFF"), "arguments");
    observing=std::string(argv[1])=="ON";
    const std::string root=argv[3];
    ggml_context_ptr meta(ggml_init({1024*1024,nullptr,true}));
    ggml_context_ptr ids_ctx(ggml_init({1024*1024,nullptr,false}));
    check(meta && ids_ctx,"metadata contexts");
    auto *ids=ggml_new_tensor_2d(ids_ctx.get(),GGML_TYPE_I32,4,1);
    auto *out=ggml_dup_tensor(ids_ctx.get(),ids);
    std::array<std::array<uint64_t,3>,36> offsets{};
    for (auto &layer:offsets) for (int k=0;k<3;++k) layer[k]=k*region;
    json result;
    {
        llama_moe_stream mgr(36,40,4,true);
        for (int k=0;k<3;++k) {
            auto *t=ggml_new_tensor_3d(meta.get(),GGML_TYPE_MXFP4,2880,2880,128);
            mgr.create_cache_tensor(2,ggml_backend_cpu_buffer_type(),t,0,offsets[2][k]);
        }
        mgr.alloc_bufs(false);
        mgr.files.emplace_back(new llama_file(argv[2],"rb",true));
        mgr.prediction_stage=std::make_unique<Stage>(argv[2],offsets);
        auto &stage=*mgr.prediction_stage;
        primary_fd=mgr.files[0]->file_id(); stage_fd=stage.reader.descriptor(); stage_align=stage.reader.offset_alignment();
        auto direct=[](int fd){int flags=fcntl(fd,F_GETFL);return flags>=0 && (flags&O_DIRECT);};
        check(primary_fd!=stage_fd && direct(primary_fd) && direct(stage_fd),"O_DIRECT admission");
        auto *sl=mgr.layer(2);
        auto route=[&](std::array<int32_t,4> experts){
            std::memcpy(ids->data,experts.data(),sizeof(experts));
            llama_moe_stream_remap(out,ids,0,1,sl);
        };
        route({8,9,10,11});
        mgr.window.call.store(1); mgr.prediction_begin(true);
        active.store(true);
        mgr.prediction_request(1,2,{1,2,3,8});
        for (int e:{1,2,3}) await_read(e);
        std::thread router([&]{route({1,4,8,9});ob::note("remap_return");});
        await_manager(mgr,[&]{return stage.stats.waits==1;},"missing attach/park");
        release_read(2); await_read(4); release_read(1);
        await_manager(mgr,[&]{return sl->slot_state.at(sl->expert_slot.at(1))==LLAMA_MOE_STREAM_SLOT_RESIDENT;},
                      "attached destination did not publish");
        release_read(4); router.join();
        std::thread finisher([&]{mgr.prediction_finish();});
        await_manager(mgr,[&]{return !stage.enabled && stage.running==1 && !stage.idle();},"drain lacks live producer");
        release_read(3); finisher.join();
        for (int e:{1,2,3,4}) for (int k=0;k<3;++k)
            check(issued[e][k]==1 && delivered[e][k]==1,"missing/extra real reads");
        result["counters"]={{"issued",stage.stats.issued},{"reads",stage.stats.reads},{"completed_reads",stage.stats.completed_reads},
            {"expired_running",stage.stats.expired_running},{"waits",stage.stats.waits},{"consumed",stage.stats.consumed},
            {"errors",stage.stats.errors},{"peak_running_spec",stage.stats.peak_running_spec}};
        result["terminal"]={{"idle",stage.idle()},{"workers",mgr.workers.size()},{"queue",mgr.q_demand.size()},
            {"claimed",std::count(sl->slot_claimed.begin(),sl->slot_claimed.end(),1)},{"shutting_down",mgr.shutting_down},
            {"load_failed",mgr.load_failed},{"direct_primary",direct(primary_fd)},{"direct_stage",direct(stage_fd)}};
        check(mgr.stats.n_calls==2 && mgr.stats.n_miss==6 && mgr.stats.n_hit==2,"native touched populations");
        result["destinations"]=json::array();
        std::vector<uint8_t> slab(Stage::slab);
        for (int rank=0;rank<4;++rank) {
            const auto slot=static_cast<const int32_t*>(out->data)[rank];
            const int expert=sl->slot_expert.at(slot);
            check(sl->slot_state.at(slot)==LLAMA_MOE_STREAM_SLOT_RESIDENT,"unpublished slot");
            json files=json::array();
            for (int k=0;k<3;++k) {
                auto &w=sl->weights.at(k);
                check(w.nb_expert==slab.size(),"encoding/size");
                ggml_backend_tensor_get(w.cache,slab.data(),size_t(slot)*w.nb_expert,w.nb_expert);
                const std::string name="rank"+std::to_string(rank)+"-component"+std::to_string(k)+".bin.gz";
                gzFile gzip=gzopen((root+"/"+name).c_str(),"wb1"); check(gzip,"compressed output");
                check(gzwrite(gzip,slab.data(),slab.size())==int(slab.size()) && gzclose(gzip)==Z_OK,"write destination");
                files.push_back(name);
            }
            result["destinations"].push_back({{"expert",expert},{"slot",slot},{"generation",sl->slot_gen.at(slot)},{"files",files}});
        }
    }
    result["events"]=json::array();
    for (size_t i=0;i<written;++i) {
        const auto &v=journal.at(i);
        result["events"].push_back({{"seq",i+1},{"ns",v.ns},{"tid",v.tid},{"worker",v.worker},{"kind",v.kind},
            {"expert",v.job.expert},{"slot",v.job.slot},{"generation",v.job.generation},{"ticket",v.job.ticket},{"component",v.component}});
    }
    std::ofstream raw(root+"/raw.json");
    raw << result.dump(2) << std::endl; check(bool(raw),"close raw");
}
