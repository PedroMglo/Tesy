// Reuse the authenticated pack/SET counters and SHA implementation of the fixed-owner control.
#define main shared_owner_control_main
#define __wrap_pread observed_pread
#include "../fixture.cpp"
#undef __wrap_pread
#undef main
#include <atomic>
#include <chrono>

using Clock=std::chrono::steady_clock;
static int64_t ns() { return std::chrono::duration_cast<std::chrono::nanoseconds>(
    Clock::now().time_since_epoch()).count(); }
static std::atomic<off_t> short_offset{-1};
extern "C" ssize_t __wrap_pread(int fd,void *data,size_t count,off_t off) {
    const auto n=observed_pread(fd,data,count,off);
    return fd==pack_fd && off==short_offset.load() && n==ssize_t(count) ? n-4096 : n;
}

// One actual CPU scheduler for each consumer width. All three outputs stay live until release.
class Projections {
public:
    Projections(ggml_backend_t cpu,llama_moe_stream_layer &layer,int nr)
        : ctx(ggml_init({2u<<20,nullptr,true})), sched(ggml_backend_sched_new(&cpu,nullptr,1,128,false,false)),
          nr(nr) {
        auto *c=ctx.get();
        auto *x=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,1,1);
        ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,nr,1);
        ggml_set_input(x);
        ggml_set_input(ids);
        graph=ggml_new_graph_custom(c,128,false);
        for (int k=0;k<3;++k) {
            outputs[k]=ggml_mul_mat_id(c,layer.weights[k].cache,x,ids);
            ggml_set_output(outputs[k]);
            ggml_build_forward_expand(graph,outputs[k]);
        }
        check(ggml_backend_sched_alloc_graph(sched.get(),graph),"CPU graph allocation");
        std::array<float,width> input{};
        for (int i=0;i<width;++i) input[i]=float((i*17)%97-48)/64.f;
        ggml_backend_tensor_set(x,input.data(),0,sizeof(input));
    }
    void compute(const int *frames) {
        ggml_backend_tensor_set(ids,frames,0,nr*sizeof(int32_t));
        check(ggml_backend_sched_graph_compute(sched.get(),graph)==GGML_STATUS_SUCCESS,"CPU projections");
        ggml_backend_sched_synchronize(sched.get());
    }
    json audit(FILE *raw) {
        json hashes=json::array(),first_rank=json::array();
        for (auto *y : outputs) {
            std::vector<float> values(size_t(width)*nr);
            const auto bytes=values.size()*sizeof(float);
            check(bytes==ggml_nbytes(y),"projection dimensions");
            ggml_backend_tensor_get(y,values.data(),0,bytes);
            check(std::all_of(values.begin(),values.end(),[](float v){return std::isfinite(v);}),"nonfinite F32");
            if(raw)check(std::fwrite(values.data(),1,bytes,raw)==bytes,"save F32");
            hashes.push_back(digest(values.data(),bytes));
            first_rank.push_back(digest(values.data(),width*sizeof(float)));
        }
        return {{"sha256",hashes},{"first_rank",first_rank}};
    }
private:
    ggml_context_ptr ctx;
    ggml_backend_sched_ptr sched;
    int nr;
    ggml_tensor *ids;
    ggml_cgraph *graph;
    std::array<ggml_tensor *,3> outputs;
};

static constexpr Ids slots_used{26,35,20,11};

static void issue(llama_moe_stream &mgr,llama_moe_stream_layer &sl,const Ids &wanted) {
    std::lock_guard lock(mgr.mtx);
    mgr.start_workers_locked();
    for (int i=0;i<ranks;++i) {
        const int s=slots_used[i];
        check(!sl.expert_slot.count(wanted[i]) && !sl.slot_claimed[s],"reservation conflict");
        mgr.reserve_slot_locked(sl,wanted[i],s);
        mgr.q_demand.push_back({&sl,wanted[i],s,sl.slot_gen[s]});
    }
    mgr.cv_work.notify_all();
}

template<typename Pred>
static void await_state(llama_moe_stream &mgr,Pred predicate) {
    std::unique_lock lock(mgr.mtx);
    check(mgr.cv_done.wait_for(lock,std::chrono::seconds(6),[&] {return mgr.load_failed || predicate();}),
          "consumer wait expired");
    check(!mgr.load_failed,"worker failed");
}

static bool published(llama_moe_stream_layer &sl,int i) {
    return sl.slot_state[slots_used[i]]==LLAMA_MOE_STREAM_SLOT_RESIDENT;
}

static void content(llama_moe_stream_layer &sl,int frame,const json &record) {
    for (size_t k=0;k<3;++k) {
        auto *t=sl.weights[k].cache;
        auto *p=static_cast<const uint8_t *>(t->data)+size_t(frame)*t->nb[2];
        check(digest(p,Store::slab)==record.at("sha").at(k).get<std::string>(),"wrong matrix content");
    }
}

static json exercise(const json &p,const std::string &role,bool exact,FILE *raw) {
    const bool disk=role=="DISK",fault=role=="EIO",wrong=role=="WRONG";
    const std::string mode=(fault || wrong)?"ID":role;
    check(!std::getenv("TESY_PACKED_CPU_SLOTS") && !std::getenv("TESY_CPU_RENEWAL") &&
          !setenv("TESY_PACKED_CPU_SLOTS","shared",1) && !setenv("TESY_CPU_RENEWAL",mode.c_str(),1),
          "isolated bank option");
    auto wall_start=ns();
    ggml_backend_ptr cpu(ggml_backend_cpu_init());
    ggml_backend_cpu_set_n_threads(cpu.get(),8);
    ggml_context_ptr meta(ggml_init({2u<<20,nullptr,true})), remap(ggml_init({1u<<20,nullptr,false}));
    llama_moe_stream mgr(36,40,4,true);
    for(int l=0;l<25;++l) for(int k=0;k<3;++k) {
        auto *t=ggml_new_tensor_3d(meta.get(),GGML_TYPE_MXFP4,width,width,128);
        ggml_set_name(t,Store::component_name(l,k,"weight").c_str());
        mgr.create_cache_tensor(l,ggml_backend_cpu_buffer_type(),t,0,0);
    }
    mgr.alloc_bufs(false);
    auto &sl=*mgr.layer(0);
    mgr.expert_store=std::make_unique<Store>();
    auto &store=*mgr.expert_store;
    store.data.open_file(p.at("pack").get<std::string>().c_str());
    pack_fd=store.data.descriptor();
    check((fcntl(pack_fd,F_GETFL)&O_DIRECT) && store.data.file_size()==p.at("pack_stat").at("size_bytes"),
          "real direct source");
    Ids b=p.at("B").get<Ids>(),a=p.at("A").get<Ids>();
    check(a==logical && slots_used==p.at("slots").get<Ids>(),"registered ranks and locations");
    for(const auto &r : p.at("records")) {
        auto &e=store.entries.at(0).at(r.at("expert").get<int>());
        e.offset=r.at("offset");
        e.relative={0,Store::slab,2*Store::slab};
    }
    Projections old(cpu.get(),sl,1),consumer(cpu.get(),sl,4);
    auto *logical_ids=ggml_new_tensor_2d(remap.get(),GGML_TYPE_I32,ranks,1);
    auto *emitted=ggml_dup_tensor(remap.get(),logical_ids);
    json rows=json::array();
    Ids previous{};
    const auto prepared=ns();
    uint64_t prior_captures=0,prior_hits=0;
    for(int phase=0;phase<4;++phase) {
        const Ids &wanted=phase%2 ? a : b;
        const bool have_old=phase>0;
        CpuWeightBank::Loan first,second;
        const size_t nread=reads.size(),nset=weight_sets;
        auto start=ns();
        if(have_old) {
            std::lock_guard lock(mgr.mtx);
            int s=slots_used[0];
            first=mgr.acquire_cpu_locked(sl,s,sl.slot_gen[s]);
            second=mgr.acquire_cpu_locked(sl,s,sl.slot_gen[s]);
            check(first.ticket && second.ticket && first.ticket!=second.ticket && first.frame==second.frame,
                  "two readers");
        }
        if(fault && phase==1) short_offset=store.entries[0][a[0]].offset;
        issue(mgr,sl,wanted);
        auto accepted=ns();
        if(fault && phase==1) {
            check(mgr.release_cpu(first) && mgr.release_cpu(second),"fault reader drain");
            std::unique_lock lock(mgr.mtx);
            check(mgr.cv_done.wait_for(lock,std::chrono::seconds(6),[&]{
                return mgr.load_failed && mgr.q_demand.empty() &&
                       std::none_of(sl.slot_claimed.begin(),sl.slot_claimed.end(),[](auto v){return v!=0;});
            }),"fault drain");
            int s=slots_used[0];
            check(!published(sl,0) && !mgr.acquire_cpu_locked(sl,s,sl.slot_gen[s]).ticket &&
                  mgr.cpu_bank->drained(),"partial read became usable");
            return {{"role",role},{"failed_closed",true},{"reads",reads.size()},{"sets",weight_sets},
                {"published_before_fault",4},{"quarantined_expert",a[0]}};
        }
        bool peers_before=false,first_before=false,protected_after_first=false,stale_rejected=false;
        int64_t old_ns=0;
        if(have_old) {
            if(exact) {
                await_state(mgr,[&]{return published(sl,1)&&published(sl,2)&&published(sl,3)&&
                                         (disk||published(sl,0));});
                std::lock_guard lock(mgr.mtx);
                peers_before=true;
                first_before=published(sl,0);
                check(first_before!=disk && (!disk || !sl.slot_claimed[slots_used[0]]),
                      "disputed destination or blocked worker");
                stale_rejected=!mgr.acquire_cpu_locked(sl,slots_used[0],sl.slot_gen[slots_used[0]]-1).ticket;
                check(stale_rejected,"stale logical acquire");
            }
            check(mgr.release_cpu(first),"first release");
            if(exact) {
                check(!mgr.release_cpu(first),"duplicate release");
                auto forged=second;
                ++forged.epoch;
                check(!mgr.release_cpu(forged),"forged epoch");
                std::lock_guard lock(mgr.mtx);
                protected_after_first=published(sl,0)!=disk;
                check(protected_after_first,"first reader released the second");
            }
            auto t=ns();
            old.compute(&second.frame);
            old_ns=ns()-t;
            if(exact) {
                const auto &r=p.at("records").at(phase%2 ? 4 : 0);
                content(sl,second.frame,r);
                check(old.audit(nullptr).at("sha256")==rows.back().at("hashes").at("first_rank"),
                      "leased reader projection differs from its earlier full rank");
            }
            check(mgr.release_cpu(second),"last release");
        }
        auto released=ns();
        await_state(mgr,[&]{for(int i=0;i<ranks;++i) if(!published(sl,i))return false;return true;});
        auto ready=ns();
        std::memcpy(logical_ids->data,wanted.data(),sizeof(wanted));
        llama_moe_stream_remap(emitted,logical_ids,0,1,&sl);
        Ids frames{},places{};
        std::memcpy(frames.data(),emitted->data,sizeof(frames));places=frames;
        std::array<CpuWeightBank::Loan,4> readers;
        std::array<int64_t,4> publication;
        {
            std::lock_guard lock(mgr.mtx);
            for(int i=0;i<ranks;++i) {
                int s=slots_used[i];
                readers[i]=mgr.acquire_cpu_locked(sl,s,sl.slot_gen[s]);
                check(readers[i].ticket && readers[i].frame==frames[i] && sl.slot_expert[s]==wanted[i] &&
                      sl.slot_gen[s]==uint64_t(phase+1),"native rank or generation");
                publication[i]=mgr.cpu_publish_ns[s]-start;
            }
        }
        if(wrong && phase==3) places=previous;
        consumer.compute(places.data());
        auto result=ns();
        json hashes=nullptr;
        if(exact) {
            for(int i=0;i<ranks;++i)content(sl,frames[i],p.at("records").at((phase%2 ? 0:4)+i));
            hashes=consumer.audit(raw);
        }
        for(auto r:readers)check(mgr.release_cpu(r),"consumer release");
        auto drain=ns();
        auto &st=mgr.cpu_bank->stats;
        check(mgr.cpu_bank->drained(),"held source or pending publication");
        rows.push_back({{"phase",phase},{"frames",frames},{"computed",places},{"hashes",hashes},
            {"reads",reads.size()-nread},{"sets",weight_sets-nset},{"captures",st.captures-prior_captures},
            {"hits",st.hits-prior_hits},{"accepted_ns",accepted-start},{"old_compute_ns",old_ns},
            {"released_ns",released-start},{"ready_ns",ready-start},{"result_ns",result-start},
            {"drain_ns",drain-start},{"publication_ns",publication},{"peers_before",peers_before},
            {"first_before",first_before},{"protected_after_first",protected_after_first},{"stale_rejected",stale_rejected}});
        prior_captures=st.captures;prior_hits=st.hits;previous=frames;
    }
    auto &st=mgr.cpu_bank->stats;
    check(st.loans==st.releases && mgr.workers.size()==4 && !mgr.load_failed && mgr.q_demand.empty() &&
          mgr.stats.n_store_loads==int64_t(reads.size()),"terminal native ownership");
    return {{"role",role},{"phase",exact ? "exact":"price"},{"rows",rows},{"prepared_ns",prepared-wall_start},
        {"setup_and_phases_ns",ns()-wall_start},{"workers",4},{"reading_workers",producers.size()},
        {"arena_B",mgr.size_bufs()},{"reads",reads.size()},{"sets",weight_sets},{"loans",st.loans},
        {"releases",st.releases},{"copies",st.copies},{"staged_hits",st.staged_hits},
        {"reservations",st.reservations},{"bank_entries",mgr.cpu_bank->occupied()}};
}

int main(int argc,char **argv) {
    try {
        check(argc==5,"plan, role, phase and output");
        std::ifstream f(argv[1]);json p;f>>p;
        const bool exact=std::string(argv[3])=="exact";
        check(exact || std::string(argv[3])=="price","unknown phase");
        FILE *fp=exact ? std::fopen(argv[4],"wbx") : nullptr;
        check(!exact||fp,"exclusive numerical output");
        auto begin=ns();
        auto r=exercise(p,argv[2],exact,fp);
        if(fp)check(std::fclose(fp)==0,"F32 close");
        r["process_through_teardown_ns"]=ns()-begin;
        std::cout<<r.dump()<<"\n";
        return 0;
    } catch(const std::exception &e) {
        std::cerr<<e.what()<<"\n";return 1;
    }
}
