// Serve one authoritative CPU0 wave through the native GGML weight buffers.
#include "ggml-cpp.h"
#include "ggml-cpu.h"
#include <nlohmann/json.hpp>
#include <openssl/sha.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <set>
#include <sys/mman.h>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <vector>

using json = nlohmann::json;
using Clock = std::chrono::steady_clock;
using Tick = std::chrono::nanoseconds;
constexpr size_t slab = 4406400, window = 13221888, frames = 1252;
constexpr int workers = 4;

static void need(bool ok, const char *why) {
    if (!ok) { std::cerr << why << '\n'; std::_Exit(2); }
}
static std::string digest(const void *p, size_t n) {
    unsigned char buf[SHA256_DIGEST_LENGTH];
    SHA256(static_cast<const unsigned char *>(p), n, buf);
    const char *hex = "0123456789abcdef";
    std::string out;
    for (const auto v : buf) { out += hex[v >> 4]; out += hex[v & 15]; }
    return out;
}
static void *region(size_t n) {
    auto *p = mmap(nullptr,n,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE,-1,0);
    need(p != MAP_FAILED, "arena allocation");
    return p;
}

struct Job { int index, expert, slot, gen, old, worker; bool hit; int64_t reserve, dispatch, ready; };
struct View { int expert=-1, gen=-1, frame=-1; };
struct Event { int64_t reserve=0, dispatch=0, ready=0, publish=0; int sets=0, reads=0; };

class Arena {
    const json &plan;
    uint8_t *const memory = static_cast<uint8_t *>(region(frames*window));
    ggml_context_ptr context{ggml_init({2u<<20,nullptr,true})};
    ggml_backend_buffer_ptr buffer{ggml_backend_cpu_buffer_from_ptr(memory,frames*window)};
    std::array<ggml_tensor *,3> weights{};
    std::set<int> prepared;
    std::array<off_t,128> offsets{};
    int fd;
public:
    int bootstrap = 0;
    explicit Arena(const json &p) : plan(p), fd(open(p.at("pack").get<std::string>().c_str(),
                                                      O_RDONLY|O_CLOEXEC|O_DIRECT)) {
        need(fd>=0 && (fcntl(fd,F_GETFL)&O_DIRECT) && context && buffer, "pack or backend buffer");
        identity();
        ggml_backend_buffer_set_usage(buffer.get(),GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
        for (int k=0;k<3;++k) {
            auto *t=ggml_new_tensor_3d(context.get(),GGML_TYPE_MXFP4,2880,2880,frames);
            need(t->nb[2]==slab, "target weight stride");
            t->nb[2]=window; t->nb[3]=frames*window;
            need(ggml_backend_tensor_alloc(buffer.get(),t,memory+k*slab)==GGML_STATUS_SUCCESS,
                 "original GGML tensor binding");
            weights[k]=t;
        }
        for(auto it=p.at("records").begin();it!=p.at("records").end();++it)
            offsets.at(std::stoi(it.key()))=it.value().at("offset").get<off_t>();
    }
    ~Arena() { identity(); need(close(fd)==0, "pack close"); buffer.reset(); munmap(memory,frames*window); }
    void identity() const {
        const auto &id=plan.at("pack_stat"); struct stat s{};
        need(fstat(fd,&s)==0 && s.st_dev==id.at("dev") && s.st_ino==id.at("inode") &&
             s.st_size==id.at("size_bytes") && s.st_mtim.tv_sec*1000000000LL+s.st_mtim.tv_nsec==id.at("mtime_ns") &&
             s.st_ctim.tv_sec*1000000000LL+s.st_ctim.tv_nsec==id.at("ctime_ns"), "original pack FD");
    }
    uint8_t *at(int f) const { need(f>=0 && size_t(f)<frames,"invalid frame"); return memory+f*window; }
    static int source(int expert) { return 1000+expert; }
    void fetch(int e, uint8_t *dest) const {
        const auto off=offsets.at(e);
        need(off%4096==0 && pread(fd,dest,window,off)==ssize_t(window), "incomplete direct record");
    }
    void preload(int e) {
        if (!prepared.insert(e).second) return;
        auto *dest=at(source(e)); fetch(e,dest); ++bootstrap;
        const auto &hash=plan.at("records").at(std::to_string(e)).at("sha");
        for (int k=0;k<3;++k)
            need(digest(dest+k*slab,slab)==hash.at(k).get<std::string>(), "source payload SHA");
    }
    void materialize(int slot, const uint8_t *src) {
        for (int k=0;k<3;++k) ggml_backend_tensor_set(weights[k],src+k*slab,slot*window,slab);
    }
    bool correct(int frame, int e, std::vector<uint8_t> &scratch) const {
        const auto &expected=plan.at("records").at(std::to_string(e)).at("sha");
        bool ok=true;
        for (int k=0;k<3;++k) {
            ggml_backend_tensor_get(weights[k],scratch.data(),frame*window,slab);
            const auto h=digest(scratch.data(),slab);
            if(h != expected.at(k).get<std::string>()) ok=false;
        }
        return ok;
    }
};

class Team {
    Arena &arena;
    const json &scenario;
    const bool bank;
    const int last;
    std::vector<Job> jobs;
    std::array<std::vector<int>,workers> queues;
    std::array<std::thread,workers> pool;
    std::array<View,40> slots{};
    std::map<int,std::pair<int,int>> demanded;
    std::array<uint8_t *,workers> staging{};
    std::vector<Event> event;
    std::mutex mutex;
    std::condition_variable cv;
    Clock::time_point epoch;
    int accepted=0, turn=0, idle=0, published=0, sequence=0;
    bool closing=false;
    std::string role;
    int single=-1, fault_source=-1;
    int64_t ns() const { return std::chrono::duration_cast<Tick>(Clock::now()-epoch).count(); }
    void wait_at(int64_t offset) const { std::this_thread::sleep_until(epoch+Tick(offset)); }

    void serve(int w, int pos) {
        const auto &j=jobs[pos];
        auto &v=event[pos];
        wait_at(j.dispatch);
        {
            std::unique_lock lock(mutex);
            cv.wait(lock,[&]{return turn==pos && accepted>pos;});
            v.dispatch=ns(); ++turn; cv.notify_all();
        }
        const uint8_t *src=arena.at(Arena::source(j.expert));
        if (!bank) wait_at(j.ready);
        else if (!j.hit || role=="DISK") {
            arena.fetch(j.expert,staging[w]); src=staging[w]; ++v.reads;
        }
        v.ready=ns();
        const bool direct=j.hit && (role=="ALL" || role=="MUTANT" || j.expert==single);
        int dest=j.slot;
        if(direct) dest=Arena::source(role=="MUTANT" && j.expert==last ? fault_source : j.expert);
        else { arena.materialize(j.slot,src); v.sets=3; }
        {
            std::lock_guard lock(mutex);
            need(slots[j.slot].expert==j.expert && slots[j.slot].gen==j.gen && slots[j.slot].frame==-1,
                 "stale publication");
            slots[j.slot]={j.expert,j.gen,dest};
            ++published; v.publish=ns(); cv.notify_all();
        }
    }
    void loop(int w) {
        int seen=0;
        std::unique_lock lock(mutex);
        ++idle; cv.notify_all();
        for (;;) {
            cv.wait(lock,[&]{return closing || seen!=sequence;});
            if(closing) return;
            seen=sequence; lock.unlock();
            for (auto pos : queues[w]) serve(w,pos);
            lock.lock(); ++idle; cv.notify_all();
        }
    }
public:
    Team(Arena &a,const json &s,bool is_bank,int last_expert) : arena(a),scenario(s),bank(is_bank),last(last_expert) {
        for (const auto &j : s.at("jobs")) {
            Job v{j["index"],j["expert"],j["slot"],j["gen"],j["old"],j["worker"],j["hit"],
                  j["reserve_ns"],j["dispatch_ns"],j["ready_ns"]};
            queues.at(v.worker).push_back(jobs.size()); jobs.push_back(v);
            arena.preload(v.old);
            if(!bank || v.hit) arena.preload(v.expert);
            if(v.hit && v.expert!=last) fault_source=v.expert;
        }
        need(fault_source>=0,"no fault source");
        for(const auto &k : s.at("demands")) demanded[k[3].get<int>()]={k[1],k[2]};
        for(const auto &k : s.at("entry")) {
            const int e=k[3], slot=k[1]; arena.preload(e);
            arena.materialize(slot,arena.at(Arena::source(e))); slots[slot]={e,k[2],slot};
        }
        for(int w=0;w<workers;++w) {
            need(!queues[w].empty(),"missing original worker");
            staging[w]=static_cast<uint8_t *>(region(window));
            std::memset(staging[w],0,window);
            pool[w]=std::thread([this,w]{loop(w);});
        }
        std::unique_lock lock(mutex); cv.wait(lock,[&]{return idle==workers;});
    }
    ~Team() {
        { std::lock_guard lock(mutex); closing=true; cv.notify_all(); }
        for(int w=0;w<workers;++w) {pool[w].join(); munmap(staging[w],window);}
    }

    json submit(const std::string &arm,int block,int direction,bool exact) {
        std::unique_lock lock(mutex);
        need(idle==workers,"undrained prior submission");
        for(const auto &j:jobs) {
            arena.materialize(j.slot,arena.at(Arena::source(j.old)));
            slots[j.slot]={j.old,j.gen-1,j.slot};
        }
        role=arm; single=arm.starts_with("ONE_") ? std::stoi(arm.substr(4)) : -1;
        event.assign(jobs.size(),{}); accepted=0; turn=0; idle=0; published=0;
        const auto barrier=scenario.at("barrier_ns").get<int64_t>();
        epoch=Clock::now(); ++sequence; cv.notify_all(); lock.unlock();
        for(const auto &j:jobs) {
            wait_at(j.reserve); lock.lock();
            auto &s=slots[j.slot];
            need(s.expert==j.old && s.gen+1==j.gen && s.frame==j.slot, "wrong reservation victim");
            s={j.expert,j.gen,-1}; event[accepted].reserve=ns(); ++accepted;
            cv.notify_all(); lock.unlock();
        }
        wait_at(barrier); lock.lock(); const auto arrived=ns();
        cv.wait(lock,[&]{return size_t(published)==jobs.size();});
        for(const auto &[e,sg] : demanded) {
            const auto &v=slots[sg.first];
            need(v.gen==sg.second && v.expert==e && v.frame>=0,"consumer saw a stale slot");
        }
        const auto consumer=ns();
        cv.wait(lock,[&]{return idle==workers;});
        const auto drain=ns();
        json events=json::array();
        for(const auto &v:event) events.push_back({v.reserve,v.dispatch,v.ready,v.publish,v.reads,v.sets});
        json out={{"role",arm},{"block",block},{"direction",direction},{"events",events},
                  {"arrival_ns",arrived},{"consumer_ns",consumer},{"drain_ns",drain}};
        if(exact) {
            std::vector<uint8_t> scratch(slab);
            std::map<int,bool> matches;
            for(const auto &[e,sg]:demanded) matches[e]=arena.correct(slots[sg.first].frame,e,scratch);
            int active=0, parked=0, corrupt=0;
            std::set<int> wrong;
            for(size_t i=0;i<scenario.at("view").size();++i) for(int k=0;k<4;++k) {
                const int e=scenario.at("logical")[i][k], slot=scenario.at("view")[i][k];
                if(slot==-1) { need(!demanded.count(e),"parked real rank"); ++parked; continue; }
                need(demanded.at(e).first==slot && slots[slot].expert==e,"rank address");
                ++active;
                if(!matches.at(e)) {wrong.insert(e); ++corrupt;}
            }
            need(wrong==(role=="MUTANT" ? std::set<int>{last} : std::set<int>{}),"unexpected weight mismatch");
            out["exact"]={{"active",active},{"parked",parked},{"wrong_ranks",corrupt},{"wrong_experts",wrong},
                          {"matrix_hashes",3*demanded.size()}};
        }
        return out;
    }
};

int main(int argc,char **argv) {
    need(argc==6,"usage: service PLAN TAG CASE REGIME PHASE");
    std::ifstream input(argv[1]); json plan; input>>plan; need(bool(input),"plan");
    const std::string tag=argv[2], name=argv[3], regime=argv[4], phase=argv[5];
    ggml_backend_ptr cpu(ggml_backend_cpu_init()); need(bool(cpu),"native CPU provider");
    const auto &s=plan.at("scenarios").at(tag).at(name);
    Arena arena(plan); Team team(arena,s,regime=="BANK",name=="decode4" ? 52 : 63);
    std::vector<std::string> roles;
    if(regime=="BANK") roles.push_back("DISK");
    roles.push_back("COPY");
    for(const auto &j:s.at("jobs"))
        if(j.at("hit").get<bool>() && (name=="decode4" || j.at("expert")==63))
            roles.push_back("ONE_"+std::to_string(j.at("expert").get<int>()));
    roles.push_back("ALL");
    json rows=json::array();
    const auto path="raw/"+tag+"-"+name+"-"+regime+"-"+phase+".jsonl";
    FILE *journal=fopen(path.c_str(),"wx");
    need(journal!=nullptr,"exclusive trial journal");
    auto record = [&](const std::string &arm,int p,int d,bool exact) {
        auto row=team.submit(arm,p,d,exact);
        const auto line=row.dump()+"\n";
        need(fwrite(line.data(),1,line.size(),journal)==line.size() && fflush(journal)==0,
             "trial journal");
        rows.push_back(std::move(row));
    };
    if(phase=="exact") {
        for(const auto &arm:roles) record(arm,0,0,true);
        record("MUTANT",0,0,true);
    } else {
        need(phase=="price","unknown phase");
        for(const auto &arm:roles) record(arm,0,0,false);
        for(int p=1;p<=7;++p) for(int d=0;d<2;++d) {
            for(size_t i=0;i<roles.size();++i)
                record(roles[d?roles.size()-1-i:i],p,d,false);
        }
    }
    need(fclose(journal)==0,"trial journal close");
    std::cout << json{{"journal",tag},{"case",name},{"regime",regime},{"phase",phase},{"rows",rows},
                      {"bootstrap_records",arena.bootstrap},{"arena_B",frames*window},
                      {"staging_B",workers*window}} << '\n';
}
