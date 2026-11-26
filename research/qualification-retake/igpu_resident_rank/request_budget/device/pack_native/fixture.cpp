// Only the test program injects synthetic records, one EINTR and the short-return control.
#include "phase-fd-integrated.h"
#include "ggml-cpu.h"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>

namespace fs=std::filesystem;
using json=nlohmann::json;
constexpr size_t slab=4406400, stride=13258752, role_span=36u<<20;
static_assert(3*slab==tesy_expert_store::weights);
std::atomic<long> attempts{0}, kernel_reads{0}, interruptions{0}, short_returns{0};
std::atomic<long long> asked{0}, delivered{0};
int tracked=-1;
bool packed=false,short_case=false;
void need(bool ok,const char *why) {if (!ok) throw std::runtime_error(why);}
uint8_t marker(int e,int k) {return uint8_t(16*e+k+1);}

struct TestBatch {int n_tokens; const int32_t *pos;};
struct ModelLike {
    llama_moe_stream &m;
    llama_moe_stream *moe_stream(){return &m;}
};
struct ContextLike {
    ModelLike model;
    std::function<int()> run;
    ModelLike &get_model(){return model;}
    int decode(TestBatch){return run();}
};
// Exact production outer call and inner graph seams extracted from the patched llama-context.cpp.
#include "borrowed-context.inc"

extern "C" ssize_t __real_pread(int,void*,size_t,off_t);
extern "C" ssize_t __wrap_pread(int fd,void *dst,size_t n,off_t off) {
    if (fd!=tracked) return __real_pread(fd,dst,n,off);
    ++attempts;asked+=n;
    if (packed && !short_case && off==0 && interruptions.fetch_add(1)==0) {errno=EINTR;return -1;}
    ++kernel_reads;
    ssize_t result=__real_pread(fd,dst,n,off);
    const int saved=errno;
    if (packed && short_case && off==5*off_t(stride) && result==ssize_t(n)) {
        ++short_returns;result=3*slab-1;
    }
    if(result>0) delivered+=result;
    errno=saved;return result;
}
json stat_fd(int fd){
    struct stat st{};need(!fstat(fd,&st),"fstat source");
    return {{"dev",st.st_dev},{"ino",st.st_ino},{"size",st.st_size}};
}
std::vector<int32_t> graph(llama_moe_stream &manager,int tile){
    ggml_context_ptr ctx(ggml_init({1u<<20,nullptr,true}));
    ggml_backend_ptr cpu(ggml_backend_cpu_init());need(ctx&&cpu,"CPU graph");
    ggml_backend_cpu_set_n_threads(cpu.get(),1);
    auto *cp=cpu.get();
    ggml_backend_sched_ptr sched(ggml_backend_sched_new(&cp,nullptr,1,32,false,false));
    auto *in=ggml_new_tensor_2d(ctx.get(),GGML_TYPE_I32,4,1);ggml_set_input(in);
    auto *mapped=ggml_map_custom1(ctx.get(),in,llama_moe_stream_remap,1,manager.layer(0));
    ggml_set_output(mapped);
    auto *g=ggml_new_graph_custom(ctx.get(),32,false);ggml_build_forward_expand(g,mapped);
    need(ggml_backend_sched_alloc_graph(sched.get(),g),"GGML graph allocation");
    std::array<int32_t,4> ids{0,1,2,int32_t(tile==1?3:4)};
    ggml_backend_tensor_set(in,ids.data(),0,sizeof(ids));
    int32_t pos=tile-1;
    auto compute=[&](int,bool){return ggml_backend_sched_graph_compute_async(sched.get(),g);};
    need(borrowed_graph(ModelLike{manager},TestBatch{1,&pos},compute)==GGML_STATUS_SUCCESS,"remap graph");
    // CPU fixture's existing synchronization solely to inspect the result.
    ggml_backend_sched_synchronize(sched.get());
    std::vector<int32_t> slots(4);ggml_backend_tensor_get(mapped,slots.data(),0,16);
    std::lock_guard<std::mutex> lock(manager.mtx);
    for(int i=0;i<4;++i){
        const auto &sl=*manager.layer(0);
        need(slots[i]>=0 && slots[i]<40 && sl.slot_expert[slots[i]]==ids[i] &&
             sl.slot_state[slots[i]]==LLAMA_MOE_STREAM_SLOT_RESIDENT && sl.slot_gen[slots[i]]==1,"actual routed slot");
    }
    return slots;
}
void setup_failure(llama_moe_stream &m){
    // A failed authoritative callback aborts the process. A manual speculative reservation
    // gives the real C291 worker the same job while allowing its fail-closed state to be reviewed.
    auto &l=*m.layer(0);std::unique_lock<std::mutex> lk(m.mtx);
    m.start_workers_locked();
    const int32_t ids[]{5,0,1,2};
    if(pfj::active())pfj::consumer(l,-1,ids,4,4);
    m.reserve_slot_locked(l,5,5);
    m.q_demand.push_back({&l,5,5,l.slot_gen[5]});
    if(pfj::active())pfj::enqueue(l,5,2);
    m.cv_work.notify_one();
    if(pfj::active())pfj::finish_consumer();
    need(m.cv_done.wait_for(lk,std::chrono::seconds(8),[&]{return m.load_failed;}) &&
         !l.slot_claimed[5] && l.slot_state[5]==LLAMA_MOE_STREAM_SLOT_LOADING,"short not published");
}
json run(const fs::path &data,const fs::path &output) {
    json report;json routes=json::array();int checked=0;
    ggml_context_ptr ctx(ggml_init({ggml_tensor_overhead()*110,nullptr,true}));need(bool(ctx),"metadata");
    {
        llama_moe_stream m(36,40,4,true);
        const char *role[]{"gate","down","up"};
        for(int i=0;i<36;++i)for(int k=0;k<3;++k){
            auto *t=i==0?ggml_new_tensor_3d(ctx.get(),GGML_TYPE_MXFP4,2880,2880,128):
                         ggml_new_tensor_3d(ctx.get(),GGML_TYPE_I8,128,1,128);
            ggml_format_name(t,"blk.%d.ffn_%s_exps.weight",i,role[k]);
            m.create_cache_tensor(i,ggml_backend_cpu_buffer_type(),t,0,k*role_span);
        }
        m.alloc_bufs(false);m.open_files({(data/"gguf.test").string()});
        need(m.use_direct_io && m.hot_decay_interval>2,"direct open and policy");
        int fd=m.files[0]->file_id();report["gguf_fd"]=fd;report["gguf_stat"]=stat_fd(fd);
        if(packed){
            m.expert_store=std::make_unique<tesy_expert_store>();
            auto &s=*m.expert_store;s.data.open_file((data/"pack.test").c_str());
            for(int e=0;e<6;++e)s.entries[0][e]={size_t(e)*stride,{0,slab,2*slab}};
            tracked=s.data.descriptor();report["pack_fd"]=tracked;report["pack_stat"]=stat_fd(tracked);
            need(s.data.offset_alignment()==4096,"fixture requires qualified 4096 byte pack alignment");
        }else {tracked=fd;report["pack_fd"]=-1;report["pack_stat"]=nullptr;}
        int32_t positions[2]{0,1};
        ContextLike c{{m},[&](){
            if(short_case){int32_t pos=0;auto step=[&](int,bool){setup_failure(m);return 0;};
                need(borrowed_graph(ModelLike{m},TestBatch{1,&pos},step)==0,"short seam");
            }else for(int ti=1;ti<=2;++ti)routes.push_back(graph(m,ti));
            return 0;
        }};
        need(borrowed_call(&c,TestBatch{short_case?1:2,positions})==0,"call");
        auto &l=*m.layer(0);
        std::vector<uint8_t> buf(slab);
        if(!short_case){
            need(!m.load_failed && l.expert_slot.size()==5,"five successful experts");
            for(int e=0;e<5;++e){
                auto slot=l.expert_slot.at(e);
                for(int k=0;k<3;++k){
                    ggml_backend_tensor_get(l.weights[k].cache,buf.data(),size_t(slot)*slab,slab);
                    need(buf.front()==marker(e,k) && buf.back()==marker(e,k)+80 &&
                         std::all_of(buf.begin()+1,buf.end()-1,[](uint8_t x){return !x;}),"complete slot payload");
                }
                ++checked;
            }
        }else need(m.load_failed && l.expert_slot.at(5)==5 && !m.stats.n_store_loads,"short state");
        need(m.workers.size()==4 && m.q_demand.empty() &&
             m.stats.n_store_loads==(packed && !short_case?5:0),"worker pool and publications");
        report["store_loads"]=m.stats.n_store_loads;report["load_failed"]=m.load_failed;
    }
    report.update(json{{"status","PASS_PACK_NATIVE_CASE"},{"transport",packed?"pack":"gguf"},{"short",short_case},
        {"joined_workers",4},{"native_calls",1},{"native_tiles",short_case?json{1}:json{1,1}},
        {"requested",asked.load()},{"returned",delivered.load()},{"attempts",attempts.load()},
        {"kernel_reads",kernel_reads.load()},{"eintr",attempts.load()-kernel_reads.load()},
        {"short_injected",short_returns.load()},{"checked_jobs",checked},{"native_slots",routes},
        {"validated_matrix_bytes",size_t(checked)*3*slab}});
    std::ofstream f(output);f<<report.dump()<<'\n';f.close();need(bool(f),"save receipt");
    return report;
}
int main(int argc,char **argv) {
    try{
        need(argc==4,"NEW case data-dir native.json");
        std::string mode=argv[1];packed=mode!="gguf";short_case=mode=="short";
        need(packed?(mode=="pack"||mode=="short"):true,"mode");
        auto r=run(argv[2],argv[3]);std::cout<<r.at("status")<<'\n';return 0;
    }catch(const std::exception &exc){std::cerr<<"FAIL: "<<exc.what()<<'\n';return 1;}
}
