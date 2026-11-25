#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include "selector.h"
#include <openssl/sha.h>
#include <array>
#include <cstring>
#include <dlfcn.h>
#include <numeric>
#include <climits>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <sstream>
#include <unistd.h>

using json = nlohmann::json;
using Store = tesy_expert_store;
using namespace retained;
constexpr size_t slab = Store::slab, payload = 3*slab, stride = 13258752, window = 13221888;
void ensure(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
std::string sha(const void *p, size_t n) {
    unsigned char b[SHA256_DIGEST_LENGTH]; char text[65]{};
    ensure(SHA256(static_cast<const unsigned char *>(p),n,b) != nullptr,"SHA256");
    for(int i=0;i<32;i++) std::snprintf(text+2*i,3,"%02x",b[i]);
    return text;
}
#include "replay.inc"

namespace {
enum Phase { warm, offer_phase, prefill, decode };
struct Job {
    int phase, key, slot, source, reads=0, sets=0;
    uint64_t gen;
    const uint8_t *base=nullptr;
};
thread_local Job job{};
struct State {
    Phase phase=warm;
    bool sealed=false;
    std::string mode;
    std::unique_ptr<Selector> bank;
    llama_moe_stream *manager=nullptr;
    llama_moe_stream_layer *layer=nullptr;
    int fd=-1;
    std::array<int,4> reads{}, sets{}, publishes{};
    json jobs=json::array(), captures=json::array(), ranks=json::array();
} s;
int rec(int e) {
    ensure(e>=0 && e<=44,"expert in generated index");
    return e<36 ? 0 : std::min(5, e-35);
}
}
void retained_rank(llama_moe_stream_layer &l,const int32_t *ids,int64_t n) {
    if (s.phase==warm) s.bank->ranks(l.il,ids,size_t(n));
}
void retained_offer(llama_moe_stream_layer &l,int v) {
    if (s.sealed || l.slot_state.at(v)==LLAMA_MOE_STREAM_SLOT_EMPTY) return;
    const int e=l.slot_expert.at(v);
    ensure(l.slot_state.at(v)==LLAMA_MOE_STREAM_SLOT_RESIDENT && l.expert_slot.at(e)==v &&
           !l.slot_claimed.at(v) && !l.keep.at(v),"ineligible capture");
    s.bank->offer({l.il,e},[&]() -> Lease {
        auto buff=std::make_shared<Data>(payload);
        for(size_t k=0;k<3;k++) {
            const auto &wt=l.weights.at(k);
            ensure(wt.nb_expert==slab && wt.cache->nb[2]==slab &&
                   ggml_backend_buffer_is_host(wt.cache->buffer),"host source layout");
            ggml_backend_tensor_get(wt.cache,buff->data()+k*slab,size_t(v)*slab,slab);
        }
        s.captures.push_back({e,v,l.slot_gen.at(v)});
        return buff;
    });
}
Lease retained_claim(const llama_moe_stream_work &w) {
    auto &l=*w.sl;
    ensure(l.slot_gen.at(w.slot)==w.gen && l.slot_expert.at(w.slot)==w.expert &&
           l.slot_state.at(w.slot)==LLAMA_MOE_STREAM_SLOT_LOADING && l.slot_claimed.at(w.slot),
           "claim identity/state");
    Lease chosen;
    int source=-1;
    if(s.sealed && s.mode!="freq_disk") {
        source=s.mode=="wrong" && w.expert==36 ? 38 : w.expert;
        chosen=s.bank->lookup({l.il,source});
        if(!chosen) source=-1;
    }
    job={int(s.phase),w.expert,w.slot,source,0,0,w.gen,chosen ? chosen->data() : nullptr};
    return chosen;
}
extern "C" ssize_t __real_pread(int,void*,size_t,off_t);
extern "C" ssize_t __wrap_pread(int fd,void *dst,size_t n,off_t off) {
    if(fd!=s.fd || s.fd<0) return __real_pread(fd,dst,n,off);
    ensure(job.source==-1 && job.reads==0 && !job.base && n==window &&
           off==off_t(rec(job.key)*stride),"pack read extent");
    ssize_t got=__real_pread(fd,dst,n,off);
    ensure(got==ssize_t(n),"unexpected pread (no retry)");
    job.reads++;
    job.base=static_cast<const uint8_t*>(dst);
    return got;
}
extern "C" void __real_ggml_backend_tensor_set(ggml_tensor*,const void*,size_t,size_t);
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor *t,const void *src,size_t off,size_t n) {
    int k=-1;
    if(s.layer) for(size_t i=0;i<s.layer->weights.size();i++)
        if(t==s.layer->weights[i].cache) k=int(i);
    if(k<0) {__real_ggml_backend_tensor_set(t,src,off,n);return;}
    ensure(job.sets==k && job.base && src==job.base+k*slab && n==slab &&
           off==size_t(job.slot)*slab,"worker SET pointer/order");
    {
        std::lock_guard<std::mutex> lk(s.manager->mtx);
        auto &l=*s.layer;
        ensure(l.slot_claimed.at(job.slot) && l.slot_state.at(job.slot)==LLAMA_MOE_STREAM_SLOT_LOADING &&
               l.slot_gen.at(job.slot)==job.gen && l.slot_expert.at(job.slot)==job.key,
               "early publication or changed owner");
    }
    __real_ggml_backend_tensor_set(t,src,off,n);
    ++job.sets;
}
void retained_publish(const llama_moe_stream_work &w) {
    ensure(job.key==w.expert && job.slot==w.slot && job.gen==w.gen && job.sets==3 &&
           w.sl->slot_state.at(w.slot)==LLAMA_MOE_STREAM_SLOT_RESIDENT &&
           !w.sl->slot_claimed.at(w.slot) && job.reads==(job.source<0),"publish");
    s.reads.at(job.phase)+=job.reads;
    s.sets.at(job.phase)+=job.sets;
    ++s.publishes.at(job.phase);
    if(job.phase>=prefill) s.jobs.push_back({{"phase",job.phase},{"expert",job.key},{"slot",job.slot},
        {"generation",job.gen},{"bank_expert",job.source},{"preads",job.reads},{"sets",job.sets}});
}

json execute(const char *pack,const char *gold_file) {
    s.bank=std::make_unique<Selector>(3,s.mode!="lru_bank");
    std::ifstream gf(gold_file); json gold; gf>>gold;
    ggml_context_ptr ctx(ggml_init({1<<20,nullptr,true})), inputs(ggml_init({1<<20,nullptr,false}));
    ensure(ctx && inputs,"GGML contexts");
    json terminal=json::array(), bad=json::array(), bank;
    {
        llama_moe_stream m(1,40,4,true);
        const std::array<const char*,3> roles{"gate","down","up"};
        for(size_t k=0;k<3;++k) {
            auto *t=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_MXFP4,2880,2880,128);
            ggml_format_name(t,"blk.0.ffn_%s_exps.weight",roles[k]);
            m.create_cache_tensor(0,ggml_backend_cpu_buffer_type(),t,0,k*128*slab);
        }
        m.alloc_bufs(false);
        s.manager=&m; s.layer=m.layer(0);
        m.expert_store=std::make_unique<Store>();
        auto &store=*m.expert_store;
        store.data.open_file(pack);
        s.fd=store.data.descriptor();
        struct stat st{};
        ensure(!fstat(s.fd,&st) && S_ISREG(st.st_mode) && !(st.st_mode&0222) &&
               st.st_size==6*off_t(stride) && (fcntl(s.fd,F_GETFL)&O_DIRECT),"pack fd");
        auto id=Store::identity(pack);
        ensure(id.at("inode")==st.st_ino && id.at("dev")==st.st_dev &&
               store.data.offset_alignment()==4096,"pack identity/alignment");
        for(int e=0;e<=44;++e) store.entries[0][e]={size_t(rec(e))*stride,{0,slab,2*slab}};
        auto route=[&](std::vector<int32_t> logical,std::vector<int32_t> expected) {
            auto *a=ggml_new_tensor_2d(inputs.get(),GGML_TYPE_I32,4,logical.size()/4);
            auto *b=ggml_dup_tensor(inputs.get(),a);
            std::memcpy(a->data,logical.data(),logical.size()*4);
            llama_moe_stream_remap(b,a,0,1,s.layer);
            ensure(!std::memcmp(b->data,expected.data(),expected.size()*4),"target remap order");
            s.ranks.push_back(expected);
        };
        route({36,37,38,39,36,0,1,2},{0,1,2,3,0,4,5,6});
        for(int e=3;e<=31;e+=4) route({e,e+1,e+2,e+3},{e+4,e+5,e+6,e+7});
        route({35,32,33,34},{39,36,37,38});
        s.phase=offer_phase;
        route({40,41,42,43},{0,1,2,3});
        {
            std::lock_guard<std::mutex> guard(m.mtx);
            ensure(m.q_demand.empty() && !m.shutting_down && !m.load_failed &&
                   m.workers.size()==4,"T1 drain");
            for(size_t i=0;i<40;++i)
                ensure(s.layer->slot_state[i]==LLAMA_MOE_STREAM_SLOT_RESIDENT &&
                       !s.layer->slot_claimed[i],"T1 slot not ready");
            s.sealed=true;
            bank=selector_receipt(*s.bank);
        }
        s.phase=prefill;
        route({36,38,39,44},{4,5,6,7});
        s.phase=decode;
        route({37,38,39,44},{8,5,6,7});
        std::lock_guard<std::mutex> guard(m.mtx);
        Data temp(slab);
        for(int i=0;i<40;++i) {
            const int e=i<4 ? 40+i : i<9 ? std::array<int,5>{36,38,39,44,37}[i-4] : i-4;
            auto &l=*s.layer;
            ensure(l.slot_expert[i]==e && l.expert_slot.at(e)==i &&
                   l.slot_gen[i]==uint64_t(i<9 ? 2:1) && !l.slot_claimed[i] &&
                   l.slot_state[i]==LLAMA_MOE_STREAM_SLOT_RESIDENT,"terminal slot/generation");
            json hashes=json::array();
            for(int k=0;k<3;++k) {
                ggml_backend_tensor_get(l.weights[k].cache,temp.data(),i*slab,slab);
                auto observed=sha(temp.data(),temp.size());
                auto expected=gold["records"][rec(e)]["role_sha256"][k];
                if(observed!=expected) bad.push_back({i,e,k,observed});
                hashes.push_back(observed);
            }
            terminal.push_back({i,e,l.slot_gen[i],hashes});
        }
        ensure(bank==selector_receipt(*s.bank) && m.q_demand.empty() && !m.load_failed &&
               m.stats.n_store_loads==std::accumulate(s.reads.begin(),s.reads.end(),0),
               "sealed bank or terminal load accounting");
        ensure(Store::identity(pack)==id,"FD identity changed");
        s.fd=-1;
    }
    auto provider=[](const void *p) {
        Dl_info info{};
        ensure(dladdr(p,&info) && info.dli_fname,"actual provider");
        char path[PATH_MAX]{};
        ensure(realpath(info.dli_fname,path)!=nullptr,"provider path");
        return std::string(path);
    };
    return {{"status","COMPLETED_C291_RETAINED_DELIVERY"},{"mode",s.mode},{"reads",s.reads},
            {"publications",s.publishes},{"sets",s.sets},{"work",s.jobs},{"ranks",s.ranks},
            {"captures",s.captures},{"bank",bank},{"terminal",terminal},{"mismatches",bad},
            {"workers_joined",4},{"pack_extent",window},
            {"providers",{{"ggml",provider(reinterpret_cast<const void *>(&__real_ggml_backend_tensor_set))},
                          {"crypto",provider(reinterpret_cast<const void *>(&SHA256))}}}};
}
int main(int argc,char **argv) {
    try {
        ensure(argc==5,"EXE MODE PACK|PFJ GOLD|CUT NEWOUT");
        s.mode=argv[1];
        ensure(s.mode=="replay" || s.mode=="freq_bank" || s.mode=="freq_disk" ||
               s.mode=="lru_bank" || s.mode=="wrong","arm");
        auto result=s.mode=="replay" ? replay(argv[2],std::stoull(argv[3])) : execute(argv[2],argv[3]);
        int fd=open(argv[4],O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC,0600);
        ensure(fd>=0,"new native output");
        FILE *out=fdopen(fd,"w"); ensure(out,"fdopen");
        auto text=result.dump(); ensure(fwrite(text.data(),1,text.size(),out)==text.size() &&
             fputc('\n',out)!=EOF && !fflush(out) && !fsync(fd) && !fclose(out),"save");
        return 0;
    } catch(const std::exception &ex) {std::cerr<<ex.what()<<"\n";return 1;}
}
