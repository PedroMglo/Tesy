// Included after the authenticated C266 helpers and before the original graph.
#include <sched.h>
#include <sys/syscall.h>
#include <unistd.h>

#ifdef TEAM_ORIGINAL
static int team_observe_init() {return 0;}
static int team_observe_add(const ggml_tensor *, int, int) {return 0;}
static void team_observe_begin(int) {}
static int team_observe_end() {return 0;}
static int team_observe_row(int,int*,int*,int*,int*,int*,int*,int*,int64_t*,int64_t*) {return -1;}
#else
extern "C" int team_observe_init();
extern "C" int team_observe_add(const ggml_tensor *, int, int);
extern "C" void team_observe_begin(int);
extern "C" int team_observe_end();
extern "C" int team_observe_row(int,int*,int*,int*,int*,int*,int*,int*,int64_t*,int64_t*);
#endif

static std::vector<int> allowed_cpus(pid_t tid) {
    cpu_set_t mask;
    need(sched_getaffinity(tid, sizeof(mask), &mask) == 0, "thread disappeared or affinity unavailable");
    std::vector<int> cpus;
    for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu) if (CPU_ISSET(cpu, &mask)) cpus.push_back(cpu);
    return cpus;
}

// Executed once at entry of each authentic C291 worker, before its staging allocation.
static std::mutex io_mutex;
static std::map<int,std::vector<int>> worker_masks;
extern "C" void team_io_started() {
    const auto tid = static_cast<pid_t>(syscall(SYS_gettid));
    auto mask = allowed_cpus(tid);
    std::lock_guard<std::mutex> lock(io_mutex);
    worker_masks.emplace(tid, std::move(mask));
}

static json workers(const std::vector<int> &original) {
    std::lock_guard<std::mutex> lock(io_mutex);
    need(worker_masks.size() == 4, "four original workers");
    json result=json::array();
    for (const auto &[tid, mask]:worker_masks) {
        need(mask == original && allowed_cpus(tid) == original, "I/O worker mask changed");
        result.push_back({tid,mask});
    }
    return result;
}

struct IoCounts {
    std::atomic<int> reads{0}, sets{0};
    std::atomic<int64_t> bytes{0}, payload{0};
    int fd=-1;
    std::array<ggml_tensor*,3> weights{};
} static io_counts;
extern "C" ssize_t __real_pread(int, void*, size_t, off_t);
extern "C" ssize_t __wrap_pread(int fd, void* buffer, size_t size, off_t offset) {
    const auto n = __real_pread(fd,buffer,size,offset);
    if (fd == io_counts.fd) {
        io_counts.reads++;
        io_counts.bytes += n;
    }
    return n;
}
extern "C" void __real_ggml_backend_tensor_set(ggml_tensor*,const void*,size_t,size_t);
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor* t,const void* data,size_t off,size_t size) {
    __real_ggml_backend_tensor_set(t,data,off,size);
    if (std::find(io_counts.weights.begin(),io_counts.weights.end(),t) != io_counts.weights.end()) {
        io_counts.sets++;
        io_counts.payload += size;
    }
}
static json io_evidence() {
    return {{"reads",io_counts.reads.load()},{"sets",io_counts.sets.load()},
            {"returned_bytes",io_counts.bytes.load()},{"set_bytes",io_counts.payload.load()}};
}

static json manager_state(llama_moe_stream &manager, llama_moe_stream_layer *layer) {
    std::lock_guard<std::mutex> lock(manager.mtx);
    need(!manager.load_failed && manager.q_demand.empty() && manager.workers.size()==4 &&
         layer->expert_slot.size()==5 && layer->slot_expert.size()==40, "drain/membership");
    for (int i=0; i<40; ++i) {
        const auto e=layer->slot_expert.at(i);
        bool ready=layer->slot_state.at(i)==LLAMA_MOE_STREAM_SLOT_RESIDENT;
        need(!layer->slot_claimed.at(i), "live claim");
        if (ready) {
            need(std::find(selected.begin(),selected.end(),e)!=selected.end() &&
                 layer->expert_slot.at(e)==i && layer->slot_gen.at(i)==1, "resident identity");
        } else {
            need(e==-1 && layer->slot_state.at(i)==LLAMA_MOE_STREAM_SLOT_EMPTY &&
                 layer->slot_gen.at(i)==0, "empty slot identity");
        }
    }
    return {{"owners",layer->slot_expert},{"generations",layer->slot_gen},
            {"states",layer->slot_state},{"claims",layer->slot_claimed}};
}

static json read_rows(int count, int64_t start, int64_t end, const std::string &mode,
                      const std::vector<int> &original) {
    json rows=json::array(), masks=json::object();
    std::map<int,int> tids;
    std::set<std::array<int,3>> keys;
    for (int i=0; i<count; ++i) {
        int wave,role,ith,nth,tid,entry,exit;
        int64_t a,b;
        need(team_observe_row(i,&wave,&role,&ith,&nth,&tid,&entry,&exit,&a,&b)==0, "missing MMID record");
        need(wave>=0&&wave<8&&role>=0&&role<3&&ith>=0&&ith<8&&nth==8&&
             start<=a&&a<b&&b<=end&&keys.insert({wave,role,ith}).second, "MMID key/time");
        if (!tids.count(ith)) {
            auto mask=allowed_cpus(tid);
            const auto expected=mode=="R"?original:std::vector<int>{(mode=="A"?4:0)+ith};
            need(!worker_masks.count(tid)&&mask==expected, "GGML/IO team identity or mask");
            tids[ith]=tid;
            masks[std::to_string(tid)]=mask;
        }
        need(tids.at(ith)==tid && entry>=0 && exit>=0, "compute TID/CPU changed");
        const auto &mask=masks.at(std::to_string(tid));
        need(std::find(mask.begin(),mask.end(),entry)!=mask.end() &&
             std::find(mask.begin(),mask.end(),exit)!=mask.end(), "execution outside prescribed mask");
        rows.push_back({wave,role,ith,nth,tid,entry,exit,a,b});
    }
    need(count==0 || (std::set<int>{tids.at(0),tids.at(1),tids.at(2),tids.at(3),tids.at(4),
        tids.at(5),tids.at(6),tids.at(7)}.size()==8 && keys.size()==192),"incomplete 24×8");
    return {{"rows",rows},{"compute_masks",masks}};
}
