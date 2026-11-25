// Synthetic CPU-only boundary fixture for the exact manager object in the new DSO build.
#include "phase-fd-integrated.h"
#include "ggml-cpu.h"
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <sys/syscall.h>

namespace {
using namespace std::chrono_literals;
using Path = std::filesystem::path;
constexpr size_t slab=128, page=4096;
constexpr std::array<size_t,3> bases={32,4*page+64,8*page+96};
constexpr off_t tail_page=(bases[2]+127*slab)&~(page-1);
struct IO {
    std::mutex lock;
    std::condition_variable changed;
    int fd=-1;
    bool entered=false, release=false;
    uint64_t attempts=0,requested=0,returned=0;
} io;
void require(bool ok,const char *message) { if(!ok) throw std::runtime_error(message); }

uint8_t source_byte(size_t i) {return uint8_t(i*17+i/19+11);}
struct ModelLike {
    llama_moe_stream &manager;
    llama_moe_stream *moe_stream() {return &manager;}
};
struct TestBatch {
    int n_tokens;
    const int32_t *pos;
};
struct ContextLike {
    ModelLike model;
    int (*run)(void *);
    void *userdata;
    ModelLike &get_model() {return model;}
    int decode(TestBatch) {return run(userdata);}
};
}

#include "borrowed-context.inc"

namespace {
void run_graph(llama_moe_stream &m,int call) {
    auto ctx=ggml_context_ptr(ggml_init({ggml_tensor_overhead()*12+ggml_graph_overhead_custom(16,false),
                                       nullptr,true}));
    ggml_backend_t cpu=ggml_backend_cpu_init();
    require(ctx && cpu,"CPU scheduler");
    ggml_backend_cpu_set_n_threads(cpu,4);
    auto sched=ggml_backend_sched_new(&cpu,nullptr,1,16,false,false);
    require(sched,"schedule");
    auto gf=ggml_new_graph_custom(ctx.get(),16,false);
    int nt=call==1?32:1;
    auto in=ggml_new_tensor_2d(ctx.get(),GGML_TYPE_I32,4,nt);
    ggml_set_input(in);
    ggml_tensor *out=nullptr;
    if(call==1) {
        ggml_tensor *args[]={in};
        out=ggml_custom_4d(ctx.get(),GGML_TYPE_I32,4,nt,1,1,args,1,
                           llama_moe_stream_wave_ids,1,m.layer(0)->wave_userdata(0,18));
    } else {
        out=ggml_map_custom1(ctx.get(),in,llama_moe_stream_remap,1,m.layer(1));
    }
    ggml_set_output(out);
    ggml_build_forward_expand(gf,out);
    require(ggml_backend_sched_alloc_graph(sched,gf),"graph alloc");
    std::vector<int32_t> ids(nt*4),pos(nt);
    for(size_t i=0;i<ids.size();++i) {
        const int j=i%42;
        ids[i]=j<18?j:j==18?127:j-1;
    }
    for(int i=0;i<nt;i++) pos[i]=call==1?i:32;
    ggml_backend_tensor_set(in,ids.data(),0,ids.size()*sizeof(ids[0]));
    auto run=[&](int,bool){return ggml_backend_sched_graph_compute_async(sched,gf);};
    require(borrowed_graph(ModelLike{m},TestBatch{nt,pos.data()},run)==GGML_STATUS_SUCCESS,"graph");
    ggml_backend_sched_synchronize(sched);
    std::vector<int32_t> slots(ids.size());
    ggml_backend_tensor_get(out,slots.data(),0,slots.size()*sizeof(slots[0]));
    const auto &layer=*m.layer(call==1?0:1);
    {
        std::lock_guard<std::mutex> locked(m.mtx);
        for(size_t i=0;i<ids.size();++i)
            if(call!=1 || ids[i]<18)
                require(slots[i]>=0 && slots[i]<40 && layer.slot_expert[slots[i]]==ids[i],"routed slot ID");
    }
    ggml_backend_sched_free(sched);
    ggml_backend_free(cpu);
}
struct Run {
    llama_moe_stream *manager;
    int call;
};
int callback(void *userdata) {
    auto &r=*static_cast<Run *>(userdata);
    run_graph(*r.manager,r.call);
    if(r.call==1) {
        std::unique_lock<std::mutex> lock(io.lock);
        require(io.changed.wait_for(lock,5s,[]{return io.entered;}),"exogenous pread barrier");
    }
    return 0;
}

void check_slots(const llama_moe_stream &m, bool fail, const std::vector<uint8_t> &input) {
    for(int il=0;il<2;++il) {
        const auto &sl=*m.layer(il);
        require(sl.expert_slot.size()==(il?4:36),"distinct jobs");
        for(auto [e,s]:sl.expert_slot) {
            const bool rejected=il==0 && e==127 && fail;
            require(sl.slot_claimed[s]==0 && sl.slot_state[s]==(rejected?LLAMA_MOE_STREAM_SLOT_LOADING:
                    LLAMA_MOE_STREAM_SLOT_RESIDENT),"terminal generation");
            for(size_t i=0;i<bases.size();++i) {
                std::array<uint8_t,slab> buf{};
                ggml_backend_tensor_get(sl.weights[i].cache,buf.data(),s*slab,slab);
                if(rejected && i==2)
                    require(std::all_of(buf.begin(),buf.end(),[](auto x){return x==0xcb;}),
                            "rejected destination");
                else require(std::equal(buf.begin(),buf.end(),input.begin()+bases[i]+e*slab),
                             "applied original bytes");
            }
        }
    }
}
} // namespace

extern "C" ssize_t __real_pread(int,void *,size_t,off_t);
extern "C" ssize_t __wrap_pread(int fd,void *data,size_t requested,off_t off) {
    if (fd!=io.fd) return __real_pread(fd,data,requested,off);
    if(off==tail_page) {
        std::unique_lock<std::mutex> lock(io.lock);
        io.entered=true;
        io.changed.notify_all();
        if(!io.changed.wait_for(lock,8s,[]{return io.release;})) std::abort();
    }
    const auto n=__real_pread(fd,data,requested,off);
    const int saved=errno;
    {
        std::lock_guard<std::mutex> lock(io.lock);
        ++io.attempts;
        io.requested+=requested;
        if(n>0) io.returned+=n;
    }
    errno=saved;
    return n;
}
int main(int argc,char **argv) {
    try {
        require(argc==4,"usage: PROGRAM NEW_DIR ok|short both|inherited");
        const Path root=argv[1];
        const bool fail=std::string(argv[2])=="short", inherited=std::string(argv[3])=="inherited";
        require((fail || std::string(argv[2])=="ok") && (inherited || std::string(argv[3])=="both"),
                "fixture mode");
        require(std::filesystem::is_directory(root) && std::filesystem::is_empty(root),"new empty directory");
        std::vector<uint8_t> input(bases[2]+128*slab-(fail?1:0));
        for(size_t i=0;i<input.size();i++) input[i]=source_byte(i);
        Path datafile=root/"synthetic.bin";
        {std::ofstream f(datafile,std::ios::binary);f.write(reinterpret_cast<char*>(input.data()),input.size());
         require(f.good(),"synthetic bytes");}
        const int fd=::open(datafile.c_str(),O_RDONLY|O_DIRECT|O_CLOEXEC);
        require(fd>=0 && ((fcntl(fd,F_GETFL)&O_DIRECT)!=0),"fixture O_DIRECT");
        std::unique_ptr<FILE,decltype(&fclose)> owned(fdopen(fd,"rb"),fclose);
        require(owned!=nullptr,"fdopen");
        auto ctx=ggml_context_ptr(ggml_init({ggml_tensor_overhead()*110,nullptr,true}));
        require(ctx!=nullptr,"weights metadata");
        {
            llama_moe_stream m(36,40,4,true);
            m.files.emplace_back(new llama_file(owned.get()));
            io.fd=m.files.front()->file_id();
            require(io.fd==fd,"reader fd identity");
            const char *names[]={"gate","down","up"};
            for(int il=0;il<36;il++) for(int i=0;i<3;i++) {
                auto t=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_I8,slab,1,128);
                ggml_format_name(t,"blk.%d.ffn_%s_exps.weight",il,names[i]);
                m.create_cache_tensor(il,ggml_backend_cpu_buffer_type(),t,0,bases[i]);
            }
            m.alloc_bufs(false);
            std::array<uint8_t,40*slab> sentinel{};
            sentinel.fill(0xcb);
            for(int il=0;il<2;il++) for(const auto &w:m.layer(il)->weights)
                ggml_backend_tensor_set(w.cache,sentinel.data(),0,sentinel.size());
            std::array<int32_t,33> pos{};
            for(int i=0;i<33;i++) pos[i]=i;
            for(int call=1;call<=2;call++) {
                if(inherited && call==2) {
                    const char *marker=std::getenv("TESY_PHASE_FD_TRIGGER");
                    require(marker!=nullptr && !std::filesystem::exists(marker),"unused trigger");
                    std::ofstream f(marker); f<<"armed\n"; require(f.good(),"trigger");
                }
                Run r{&m,call}; ContextLike test{{m},callback,&r};
                require(borrowed_call(&test,TestBatch{call==1?32:1,pos.data()+(call==1?0:32)})==0,"call");
                std::lock_guard<std::mutex> locked(m.mtx);
                require(m.layer(0)->slot_claimed.at(m.layer(0)->expert_slot.at(127)),"returned falsely drained");
            }
            {
                std::lock_guard<std::mutex> lock(io.lock);
                io.release=true;
            }
            io.changed.notify_all();
            {
                std::unique_lock<std::mutex> lock(m.mtx);
                require(m.cv_done.wait_for(lock,5s,[&]{return m.q_demand.empty() && !pfj::claims(m);}),
                        "actual terminal work");
                require(m.load_failed==fail && m.workers.size()==4,"terminal condition");
                check_slots(m,fail,input);
            }
        }
        require(io.attempts==120,"independent syscall count");
        std::printf("{\"status\":\"PASS\",\"reads\":%llu,\"requested\":%llu,\"returned\":%llu,"
                    "\"payload\":%zu,\"publications\":%d,\"joined\":4}\n",
                    (unsigned long long)io.attempts,(unsigned long long)io.requested,
                    (unsigned long long)io.returned,slab*(120-(fail?1:0)),40-(fail?1:0));
        return 0;
    } catch(const std::exception &e) {
        std::fprintf(stderr,"PFJ1_FIXTURE_FAIL %s\n",e.what());
        return 1;
    }
}
