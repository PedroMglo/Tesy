// Compile ALL translation units with TESY_STORE_TESTING. No production manifest is fabricated.
// fixture DENSE|STAGED|DIRECT success|short|short_tail|shutdown PACK GOLD.json NEW_RECEIPT.json
// short_tail is the packed-reader ABI fault: a full syscall is masked to the exact logical
// weight count, so rejection proves the reader requires its entire transported window.
// GNU ld --wrap=pread --wrap=ggml_backend_tensor_set; packs supply weights in every arm.
#ifndef TESY_STORE_TESTING
#error "The fixture must build against the C291 synthetic constructor"
#endif
#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include <openssl/evp.h>
#include <openssl/sha.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <dlfcn.h>
#include <sys/syscall.h>
#include <fcntl.h>
#include <unistd.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <thread>
#include <vector>

namespace {
using json = nlohmann::json;
using Store = tesy_expert_store;
using namespace std::chrono_literals;
constexpr size_t slab = Store::slab, window = 13221888, stride = 13258752;
constexpr int layer = 0, slots = 40, experts = 128;
constexpr std::array<const char *, 3> roles = {"gate", "down", "up"};
static_assert(3*slab == 13219200 && window % 4096 == 0 && stride % 4096 == 0);

FILE *receipt = nullptr;
std::mutex error_mutex;
void check(bool ok, const char *why) {
    if (ok) return;
    std::lock_guard<std::mutex> lk(error_mutex);
    if (receipt) {
        std::fprintf(receipt, "{\"status\":\"FAIL_PRESERVED\",\"reason\":\"%s\"}\n", why);
        std::fflush(receipt);
    }
    std::cerr << "FAIL " << why << std::endl;
    std::_Exit(1);
}
std::string digest(const uint8_t *p, size_t n) {
    unsigned char sum[SHA256_DIGEST_LENGTH];
    check(SHA256(p,n,sum)!=nullptr,"SHA256");
    std::ostringstream s;
    for (uint8_t c:sum) s<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(c);
    return s.str();
}
int record_for(int expert) { check(expert>=0 && expert<=40,"unexpected_expert"); return expert<36?0:expert-35; }
struct Phase {
    int reads=0, sets=0;
    uint64_t requested=0, delivered=0, copied=0;
};
struct Job {
    int record=-1, slot=-1, expert=-1;
    uint64_t gen=0;
    long tid=-1;
    uintptr_t pread_dst=0;
    size_t requested=0;
    ssize_t kernel_returned=-1, returned=-1;
    std::array<std::pair<uintptr_t,uintptr_t>,3> copies{};
    int sets=0;
};
struct State {
    int fd=-1;
    std::string mode, test, phase;
    llama_moe_stream *mgr=nullptr;
    llama_moe_stream_layer *sl=nullptr;
    std::mutex m;
    std::condition_variable cv;
    bool hold=false, release=false;
    int want=0;
    std::vector<Job> group;
    std::vector<json> observed;
    std::map<std::string,Phase> totals;
};
State s;
thread_local int current_record = -1;
thread_local uintptr_t current_dst = 0;
bool inside(const void *address, size_t n, const void *base, size_t bytes) {
    auto p=reinterpret_cast<uintptr_t>(address), b=reinterpret_cast<uintptr_t>(base);
    return b<=p && p-b<=bytes && n<=bytes-(p-b);
}
ggml_backend_buffer_t backing(ggml_tensor *t) {
    while (!t->buffer && t->view_src) t=t->view_src;
    check(t->buffer && ggml_backend_buffer_get_type(t->buffer)==ggml_backend_cpu_buffer_type(),"not_native_CPU_buffer");
    return t->buffer;
}
uint8_t *view(int k, int slot) {
    auto *t=s.sl->weights.at(k).cache;
    const size_t offset=size_t(slot)*t->nb[2];
    uint8_t *ptr=static_cast<uint8_t*>(t->data)+offset;
    auto *b=backing(t);
    check(inside(ptr,slab,ggml_backend_buffer_get_base(b),ggml_backend_buffer_get_size(b)),"slab_outside_owning_CPU_buffer");
    return ptr;
}
bool any_cache_buffer(void *ptr, size_t len) {
    for (const auto &b:s.mgr->bufs) {
        auto *start=ggml_backend_buffer_get_base(b.get());
        const auto n=ggml_backend_buffer_get_size(b.get());
        // Reject either direction of overlap.
        if (inside(ptr,1,start,n) || inside(start,1,ptr,len)) return true;
    }
    return false;
}
Job &job_for(int rec) {
    auto it=std::find_if(s.group.begin(),s.group.end(),[&](const Job &j){return j.record==rec;});
    check(it!=s.group.end(),"missing_READ_for_SET");
    return *it;
}
void phase(const std::string &name, int jobs) {
    std::lock_guard<std::mutex> lk(s.m);
    s.phase=name; s.hold=jobs!=0; s.release=false; s.want=jobs; s.group.clear();
}
void held(const std::vector<int> &ids, const std::vector<int> &slots_expected) {
    {
        std::unique_lock<std::mutex> lk(s.m);
        check(s.cv.wait_for(lk,30s,[]{return int(s.group.size())>=s.want;}),"held_reads_missing");
    }
    // All intercepted calls have already been claimed. The workers do not own
    // the manager mutex while the real destination is held outstanding.
    std::lock_guard<std::mutex> lock(s.mgr->mtx);
    std::lock_guard<std::mutex> events(s.m);
    check(s.mgr->workers.size()==4 && s.group.size()==ids.size(),"worker_pool_or_group");
    std::array<uint8_t,slots> keep;
    keep.fill(1);
    std::set<long> tids;
    std::set<uintptr_t> addresses;
    for (size_t i=0;i<ids.size();++i) {
        int e=ids[i], v=slots_expected[i];
        Job &j=job_for(record_for(e));
        check(s.sl->expert_slot.at(e)==v && s.sl->slot_expert.at(v)==e &&
              s.sl->slot_state.at(v)==LLAMA_MOE_STREAM_SLOT_LOADING && s.sl->slot_claimed.at(v)==1,
              "not_claimed_LOADING");
        j.slot=v; j.expert=e; j.gen=s.sl->slot_gen.at(v);
        tids.insert(j.tid); addresses.insert(j.pread_dst);
        keep[v]=0;
        if(s.mode=="DIRECT") {
            auto *b=backing(s.sl->weights[0].cache);
            check(j.pread_dst==reinterpret_cast<uintptr_t>(view(0,v)) &&
                  inside(view(0,v),j.requested,ggml_backend_buffer_get_base(b),ggml_backend_buffer_get_size(b)),
                  "direct_read_not_to_owned_slot");
        } else {
            check(!any_cache_buffer(reinterpret_cast<void*>(j.pread_dst),j.requested),"staging_aliases_cache");
        }
    }
    check(tids.size()==ids.size() && addresses.size()==ids.size(),"worker_or_destination_collision");
    // Every alternative slot protected, all outstanding reads are ineligible.
    check(s.mgr->pick_victim_locked(*s.sl,keep.data())==-1,"loading_is_victim");
    // Offer slot 35 as the sole legal alternative (resident in success, empty in faults).
    keep[35]=0;
    check(s.mgr->pick_victim_locked(*s.sl,keep.data())==35,"available_victim_not_used");
}
void release() {
    std::lock_guard<std::mutex> lk(s.m);
    s.release=true;
    s.cv.notify_all();
}
void complete_group(bool successful, bool short_result=false) {
    std::lock_guard<std::mutex> lk(s.m);
    for (const auto &j:s.group) {
        if (s.mode=="DIRECT" || short_result) check(j.sets==0,"unexpected_SET");
        else if (successful) check(j.sets==3,"missing_SET");
        else check(j.sets>=0 && j.sets<=3,"invalid_cancelled_SET_count");
        const bool tail=s.test=="short_tail";
        const ssize_t actual=ssize_t(j.requested-(s.test=="short"?4096:0));
        check(j.kernel_returned==actual && j.returned==(tail?ssize_t(3*slab):actual),
              "unexpected_pread_return");
        json puts=json::array();
        for(int k=0;k<j.sets;++k) {
            auto [src,dst]=j.copies[k];
            check(src==j.pread_dst+k*slab && dst==reinterpret_cast<uintptr_t>(view(k,j.slot)),
                  "SET_src_or_slot_destination");
            puts.push_back({{"component",k},{"src_delta_from_pread_dst",src-j.pread_dst},
                            {"dst_delta_from_role_view",size_t(j.slot)*s.sl->weights[k].cache->nb[2]}});
        }
        s.observed.push_back({{"phase",s.phase},{"expert",j.expert},{"slot",j.slot},{"gen",j.gen},
            {"worker_tid",j.tid},{"pread_dst_class",s.mode=="DIRECT"?"OWNED_SLOT_BASE":"OUTSIDE_CACHE"},
            {"direct_dst_offset_from_slot0",s.mode=="DIRECT"?json(j.pread_dst-reinterpret_cast<uintptr_t>(view(0,0))):json(nullptr)},
            {"requested",j.requested},{"syscall_return",j.kernel_returned},{"reader_return",j.returned},
            {"sets",puts},{"publish_expected",successful}});
    }
}
void check_stats(const std::string &p,int n) {
    std::lock_guard<std::mutex> lk(s.m);
    const auto counters=s.totals[p];
    check(counters.reads==n && counters.sets==(s.mode=="DIRECT"?0:3*n),"phase_work");
    check(counters.copied==uint64_t(counters.sets)*slab,"phase_SET_bytes");
}

} // namespace

extern "C" ssize_t __real_pread(int fd,void *dst,size_t bytes,off_t off);
extern "C" ssize_t __wrap_pread(int fd,void *dst,size_t bytes,off_t off) {
    if(fd!=s.fd) return __real_pread(fd,dst,bytes,off);
    check(off>=0 && size_t(off)%stride==0 && size_t(off)/stride<6,"unmapped_pack_read");
    const int rec=static_cast<int>(size_t(off)/stride);
    const size_t align=s.mgr->expert_store->data.offset_alignment();
    const size_t aligned=((3*slab+align-1)/align)*align;
    check(bytes==(s.mode=="DENSE"?aligned:window),"unexpected_read_extent");
    current_record=rec;
    current_dst=reinterpret_cast<uintptr_t>(dst);
    check(current_dst%s.mgr->expert_store->data.memory_alignment()==0,"unaligned_pread_destination");
    {
        std::unique_lock<std::mutex> lk(s.m);
        auto &t=s.totals[s.phase];
        ++t.reads; t.requested+=bytes;
        if(s.phase=="warm") {
            check(rec==0, "warm_index");
        } else {
            check(s.hold && rec>0 && int(s.group.size())<s.want,"unexpected_extra_read");
            Job j;
            j.record=rec; j.tid=syscall(SYS_gettid); j.pread_dst=current_dst; j.requested=bytes;
            s.group.push_back(j); s.cv.notify_all();
            check(s.cv.wait_for(lk,30s,[]{return s.release;}),"controller_release_timeout");
        }
    }
    const size_t syscall_size=s.test=="short"?bytes-4096:bytes;
    const ssize_t kernel_returned=__real_pread(fd,dst,syscall_size,off);
    const int saved_errno=errno;
    const ssize_t returned=(s.test=="short_tail" && kernel_returned==ssize_t(bytes))?
            ssize_t(3*slab):kernel_returned;
    {
        std::lock_guard<std::mutex> lk(s.m);
        if(returned>0)s.totals[s.phase].delivered+=size_t(returned);
        if(s.phase!="warm") { auto &j=job_for(rec); j.kernel_returned=kernel_returned; j.returned=returned; }
    }
    errno=saved_errno;
    return returned;
}

extern "C" void __real_ggml_backend_tensor_set(ggml_tensor *,const void *,size_t,size_t);
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor *tensor,const void *src,size_t off,size_t n) {
    if (s.fd>=0 && s.sl) {
        int k=-1;
        for(int i=0;i<3;++i) if(s.sl->weights.at(i).cache==tensor) k=i;
        if(k>=0) {
            std::lock_guard<std::mutex> lk(s.m);
            check(n==slab && current_record>=0 && s.mode!="DIRECT","unexpected_SET");
            auto &t=s.totals[s.phase]; ++t.sets; t.copied+=n;
            const auto source=reinterpret_cast<uintptr_t>(src);
            check(source==current_dst+size_t(k)*slab,"SET_not_from_same_read");
            if(s.phase!="warm") {
                auto &j=job_for(current_record);
                check(j.tid==syscall(SYS_gettid) && j.sets==k && j.returned==ssize_t(j.requested),
                      "SET_before_read_or_wrong_worker");
                j.copies[k]={source,reinterpret_cast<uintptr_t>(tensor->data)+off};
                ++j.sets;
            }
        }
    }
    __real_ggml_backend_tensor_set(tensor,src,off,n);
}

namespace {
json descriptor_identity(int fd) {
    struct stat st{};
    check(fstat(fd,&st)==0 && S_ISREG(st.st_mode) && !(st.st_mode&0222),"pack_must_be_readonly");
    return {{"dev",st.st_dev},{"inode",st.st_ino},{"size_bytes",st.st_size},
            {"mtime_ns",uint64_t(st.st_mtim.tv_sec)*1000000000+st.st_mtim.tv_nsec},
            {"ctime_ns",uint64_t(st.st_ctim.tv_sec)*1000000000+st.st_ctim.tv_nsec}};
}
std::string hash_pack_fd(int fd) {
    // Private proof scan of the SAME O_DIRECT descriptor. Outside native service
    // counters; never turn its DIO bytes or cost into a product timing.
    constexpr size_t chunk=1<<20;
    void *raw=nullptr;
    check(posix_memalign(&raw,4096,chunk)==0,"pack_hash_buffer");
    std::unique_ptr<void,decltype(&std::free)> data(raw,&std::free);
    std::unique_ptr<EVP_MD_CTX,decltype(&EVP_MD_CTX_free)> ctx(EVP_MD_CTX_new(),&EVP_MD_CTX_free);
    check(ctx && EVP_DigestInit_ex(ctx.get(),EVP_sha256(),nullptr)==1,"pack_hash_init");
    for(size_t i=0;i<6*stride;i+=chunk) {
        size_t n=std::min(chunk,6*stride-i);
        check(__real_pread(fd,data.get(),n,off_t(i))==ssize_t(n),"pack_hash_direct_read");
        check(EVP_DigestUpdate(ctx.get(),data.get(),n)==1,"pack_hash_update");
    }
    unsigned char sum[32]; unsigned int n=0;
    check(EVP_DigestFinal_ex(ctx.get(),sum,&n)==1 && n==32,"pack_hash_final");
    std::ostringstream out;
    for(auto c:sum) out<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(c);
    return out.str();
}
void check_views() {
    for(int k=0;k<3;++k) {
        const auto &w=s.sl->weights.at(k);
        check(w.nb_expert==slab && w.cache->type==GGML_TYPE_MXFP4 &&
              w.cache->ne[0]==2880 && w.cache->ne[1]==2880 && w.cache->ne[2]==40 &&
              w.cache->nb[2]==(s.mode=="DENSE"?slab:window),"cache_descriptor");
        if(s.mode!="DENSE") {
            check(backing(w.cache)==backing(s.sl->weights[0].cache) &&
                  view(k,39)==view(0,39)+size_t(k)*slab &&
                  view(k,0)==view(0,0)+size_t(k)*slab,"AoS_view_owner_or_offset");
        }
    }
    if(s.mode!="DENSE")check(reinterpret_cast<uintptr_t>(view(0,0))%4096==0,"AoS_base_alignment");
}

json verify_slots(const json &gold, bool replacement) {
    json rows=json::array();
    std::vector<uint8_t> data(slab);
    for (int v=0;v<slots;++v) {
        const int e=replacement && v==0?40:v;
        const uint64_t generation=replacement && v==0?2:1;
        check(s.sl->slot_state[v]==LLAMA_MOE_STREAM_SLOT_RESIDENT && !s.sl->slot_claimed[v] &&
              s.sl->slot_gen[v]==generation && s.sl->slot_expert[v]==e &&
              s.sl->expert_slot.at(e)==v,"published_slot_identity");
        const int rec=record_for(e);
        json observed=json::array();
        for(int k=0;k<3;++k) {
            auto *tensor=s.sl->weights[k].cache;
            ggml_backend_tensor_get(tensor,data.data(),size_t(v)*tensor->nb[2],slab);
            const auto sum=digest(data.data(),data.size());
            check(sum==gold.at("records").at(rec).at("role_sha256").at(k),"independent_role_hash");
            observed.push_back(sum);
        }
        if(s.mode=="DIRECT") {
            check(digest(view(0,v)+3*slab,window-3*slab)==gold.at("records").at(rec).at("weight_window_tail_sha256"),
                  "direct_weight_window_padding_changed");
        }
        rows.push_back({{"slot",v},{"expert",e},{"generation",generation},{"role_sha256",observed}});
    }
    return rows;
}

json run(const char *pack, const json &gold) {
    check(gold.at("schema")=="synthetic-c291-slot-v1" && gold.at("records").size()==6 &&
          gold.at("expert_records").size()==41 && gold.at("pack_stride")==stride &&
          gold.at("slab")==slab && gold.at("window")==window && gold.at("pack_bytes")==6*stride,
          "synthetic_gold_geometry");
    ggml_context_ptr ctx(ggml_init({1024*1024,nullptr,true})), idctx(ggml_init({1024*1024,nullptr,false}));
    check(ctx && idctx,"ggml_contexts");
    auto *ids=ggml_new_tensor_2d(idctx.get(),GGML_TYPE_I32,4,1);
    auto *out=ggml_dup_tensor(idctx.get(),ids);
    json result;
    {
        llama_moe_stream manager(1,slots,4,true);
        s.mgr=&manager;
        for(int k=0;k<3;++k) {
            auto *m=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_MXFP4,2880,2880,experts);
            ggml_format_name(m,"blk.0.ffn_%s_exps.weight",roles[k]);
            manager.create_cache_tensor(layer,ggml_backend_cpu_buffer_type(),m,0,k*size_t(experts)*slab);
        }
        manager.alloc_bufs(false);
        s.sl=manager.layer(layer);
        check(s.sl && s.sl->n_slots==40 && s.sl->n_expert==128,"one_layer_dimensions");
        check_views();
        manager.expert_store=std::make_unique<Store>();
        auto &store=*manager.expert_store;
        store.data.open_file(pack);
        const int flags=fcntl(store.data.descriptor(),F_GETFL);
        check(store.data.file_size()==6*stride && flags>=0 && (flags&O_DIRECT) &&
              store.data.memory_alignment() && 4096%store.data.memory_alignment()==0 &&
              store.data.offset_alignment() && 4096%store.data.offset_alignment()==0,"pack_identity");
        const auto initial_identity=descriptor_identity(store.data.descriptor());
        check(initial_identity==Store::identity(pack),"pack_path_descriptor_mismatch");
        const auto measured_hash=hash_pack_fd(store.data.descriptor());
        check(measured_hash==gold.at("pack_sha256"),"pack_hash_mismatch");
        result["pack"]={{"bytes",store.data.file_size()},{"declared_write_stream_sha256",gold.at("pack_sha256")},
            {"sha256_from_serviced_fd",measured_hash},{"identity",initial_identity},
            {"proof_scan_DIO_bytes",6*stride},
            {"alignment_memory",store.data.memory_alignment()},{"alignment_offset",store.data.offset_alignment()}};
        for(auto &entry:store.entries[layer])entry.offset=std::numeric_limits<uint64_t>::max();
        for(int e=0;e<=40;++e) {
            const int rec=record_for(e);
            check(gold.at("expert_records").at(e)==rec && gold.at("records").at(rec).at("offset")==rec*stride,
                  "synthetic_entry_mapping");
            auto &entry=store.entries[layer][e]; entry.offset=rec*stride; entry.relative={0,slab,2*slab};
        }
        s.fd=store.data.descriptor();
        auto route=[&](std::array<int32_t,4> v) {
            std::memcpy(ids->data,v.data(),sizeof(v));
            llama_moe_stream_remap(out,ids,0,1,s.sl);
        };
        auto expect=[&](std::array<int32_t,4> want) {
            check(std::memcmp(out->data,want.data(),sizeof(want))==0,"remapped_rank_order");
        };
        if(s.test=="success") {
            phase("warm",0);
            for(int i=0;i<36;i+=4) { route({i,i+1,i+2,i+3}); expect({i,i+1,i+2,i+3}); }
            check_stats("warm",36);
            check(manager.stats.n_store_loads==36 && manager.stats.n_miss==36,"warm_native_work");
            for(int v=0;v<36;++v)
                check(s.sl->slot_expert[v]==v && s.sl->slot_gen[v]==1 &&
                      s.sl->slot_state[v]==LLAMA_MOE_STREAM_SLOT_RESIDENT,"warm_snapshot");
            phase("four",4);
            std::thread router([&]{route({36,37,38,39});});
            held({36,37,38,39},{36,37,38,39});
            check(manager.stats.n_store_loads==36,"premature_publication");
            release(); router.join(); expect({36,37,38,39}); complete_group(true); check_stats("four",4);
            result["before_replacement"]=verify_slots(gold,false);
            // A second order must hit exactly the same published generations; no reads or sets.
            phase("hits",0); route({39,36,38,37}); expect({39,36,38,37}); check_stats("hits",0);
            phase("replace",1);
            std::thread replacement([&]{route({40,37,38,39});});
            held({40},{0}); release(); replacement.join(); expect({0,37,38,39});
            complete_group(true); check_stats("replace",1);
            result["after_replacement"]=verify_slots(gold,true);
            check(manager.stats.n_calls==12 && manager.stats.n_hit==7 && manager.stats.n_miss==41 &&
                  manager.stats.n_store_loads==41 && manager.stats.n_store_read_bytes==int64_t(41*3*slab) &&
                  s.sl->expert_slot.count(0)==0 && !manager.load_failed && !manager.shutting_down &&
                  manager.q_demand.empty(),"final_positive_counters");
        } else {
            // Direct admission without the remap-level GGML_ABORT permits inspection after a worker error.
            // This is the native queue and reservation primitive used by remap; no model-side recovery.
            phase("fault",1);
            {
                std::lock_guard<std::mutex> lk(manager.mtx);
                manager.start_workers_locked();
                int v=manager.pick_victim_locked(*s.sl,nullptr);
                check(v==0,"first_victim");
                manager.reserve_slot_locked(*s.sl,36,v);
                manager.q_demand.push_back({s.sl,36,v,s.sl->slot_gen[v]});
                manager.cv_work.notify_one();
            }
            held({36},{0});
            {
                std::lock_guard<std::mutex> lk(manager.mtx);
                if(s.test=="shutdown") {
                    // Reproduce the native shutdown flag/empty queue before the held pread returns.
                    manager.shutting_down=true; manager.q_demand.clear(); manager.cv_work.notify_all();
                }
            }
            release();
            {
                std::unique_lock<std::mutex> lk(manager.mtx);
                check(manager.cv_done.wait_for(lk,30s,[]{return s.sl->slot_claimed[0]==0;}),"fault_drain");
                check(s.sl->slot_gen[0]==1 && s.sl->slot_expert[0]==36 &&
                      s.sl->slot_state[0]==LLAMA_MOE_STREAM_SLOT_LOADING && manager.stats.n_store_loads==0 &&
                      manager.stats.n_store_read_bytes==0 && manager.load_failed==(s.test!="shutdown") &&
                      manager.shutting_down==(s.test=="shutdown") && manager.q_demand.empty(),"failed_publication");
            }
            complete_group(false,s.test!="shutdown");
            result["terminal_state"]={{"slot",0},{"generation",1},{"claimed",false},{"state","LOADING"},
                {"native_loads_committed",0},{"sticky_load_failed",manager.load_failed},
                {"shutting_down",manager.shutting_down}};
        }
        {
            std::lock_guard<std::mutex> lk(s.m);
            for(const auto &[name,t]:s.totals)result["phases"][name]={{"reads",t.reads},{"sets",t.sets},
                {"requested",t.requested},{"delivered",t.delivered},{"bytes_set",t.copied}};
        }
        result["native"]={{"calls",manager.stats.n_calls},{"hits",manager.stats.n_hit},
            {"misses",manager.stats.n_miss},{"store_loads",manager.stats.n_store_loads},
            {"store_read_logical",manager.stats.n_store_read_bytes},{"workers",manager.workers.size()}};
        check(descriptor_identity(store.data.descriptor())==initial_identity && Store::identity(pack)==initial_identity,
              "pack_mutated_during_arm");
    }
    s.fd=-1; s.mgr=nullptr; s.sl=nullptr;
    Dl_info g{},crypto{};
    check(dladdr(reinterpret_cast<void*>(&ggml_backend_buffer_get_type),&g)!=0 && g.dli_fname &&
          dladdr(reinterpret_cast<void*>(&EVP_sha256),&crypto)!=0 && crypto.dli_fname,
          "loaded_provider_unknown");
    result["mapped_providers"]={{"ggml",g.dli_fname},{"crypto",crypto.dli_fname}};
    std::ifstream cgroup("/proc/self/cgroup");
    std::string membership;
    check(bool(std::getline(cgroup,membership)) && membership.compare(0,4,"0::/")==0,"scope_membership");
    result["cgroup_membership"]=membership;
    result["manager_destructor_returned"]=true;
    result["observed_claims"]=s.observed;
    result["status"]="PASS_SYNTHETIC_WORKER_FIXTURE";
    result["mode"]=s.mode; result["case"]=s.test; result["model_forwards"]=0;
    result["scope"]="CPU single test layer; synthetic test index, no manifest qualification, CUDA, FFN, logits or benchmark";
    struct rusage usage{};
    check(getrusage(RUSAGE_SELF,&usage)==0 && usage.ru_maxrss>0 && usage.ru_maxrss<1024*1024,"RSS_limit");
    result["maxrss_KiB"]=usage.ru_maxrss;
    return result;
}
}

int main(int argc,char **argv) {
    if(argc!=6)return 2;
    alarm(235);
    int fd=open(argv[5],O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC,0600);
    if(fd<0)return 2;
    receipt=fdopen(fd,"w");
    if(!receipt) return 2;
    try {
        s.mode=argv[1]; s.test=argv[2];
        check((s.mode=="DENSE" || s.mode=="STAGED" || s.mode=="DIRECT") &&
              (s.test=="success" || s.test=="short" || s.test=="shutdown" ||
               (s.test=="short_tail" && s.mode!="DENSE")), "CLI");
        check(!getenv("TESY_PACKED_CPU_SLOTS") && !getenv("TESY_EXPERT_STORE_MANIFEST"),
              "inherited_test_environment");
        if(s.mode!="DENSE")
            check(setenv("TESY_PACKED_CPU_SLOTS",s.mode=="DIRECT"?"direct":"staged",1)==0,"mode_environment");
        std::ifstream g(argv[4]); json gold; g>>gold; check(bool(g),"gold_json");
        const auto result=run(argv[3],gold);
        std::fprintf(receipt,"%s\n",result.dump(2).c_str());
        check(std::fflush(receipt)==0 && fsync(fd)==0,"receipt_write");
        return std::fclose(receipt)==0?0:1;
    } catch(...) {
        check(false,"unexpected_fixture_exception");
        return 1;
    }
}
