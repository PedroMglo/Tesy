// The C291 manager installs the eight original pack records through its native FIFO.
#include "llama-moe-stream.h"
#include "c291-expert-store.h"
#include "ggml-cpu.h"
#include <openssl/sha.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <mutex>
#include <set>
#include <sys/syscall.h>
#include <unistd.h>

using json = nlohmann::json;
using Store = tesy_expert_store;
constexpr int width = 2880, ranks = 4;
using Ids = std::array<int32_t, ranks>;
static const Ids logical{47,82,75,52};

static void check(bool value, const char *reason) {
    if (!value) throw std::runtime_error(reason);
}

static std::string digest(const void *data, size_t size) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    check(SHA256(static_cast<const uint8_t *>(data),size,hash) != nullptr,"SHA256");
    constexpr char digits[] = "0123456789abcdef";
    std::string result;
    for (uint8_t b : hash) { result += digits[b >> 4]; result += digits[b & 15]; }
    return result;
}

static std::mutex log_lock;
static int pack_fd = -1;
static std::vector<off_t> reads;
static std::set<long> producers;
static unsigned weight_sets = 0;

extern "C" ssize_t __real_pread(int,void *,size_t,off_t);
extern "C" ssize_t __wrap_pread(int fd, void *data, size_t count, off_t off) {
    const ssize_t n = __real_pread(fd,data,count,off);
    if (fd == pack_fd) {
        std::lock_guard lock(log_lock);
        check(n == ssize_t(Store::window) && count == Store::window,"incomplete pack read");
        reads.push_back(off);
        producers.insert(syscall(SYS_gettid));
    }
    return n;
}

extern "C" void __real_ggml_backend_tensor_set(ggml_tensor *,const void *,size_t,size_t);
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor *t,const void *data,size_t off,size_t n) {
    if (n == Store::slab && std::string(ggml_get_name(t)).ends_with(".stream_cache")) {
        std::lock_guard lock(log_lock);
        ++weight_sets;
    }
    __real_ggml_backend_tensor_set(t,data,off,n);
}

static json projections(ggml_backend_t cpu, llama_moe_stream_layer &layer, const Ids &places, FILE *raw) {
    ggml_context_ptr ctx(ggml_init({2u<<20,nullptr,true}));
    auto *c = ctx.get();
    auto *x = ggml_new_tensor_3d(c,GGML_TYPE_F32,width,1,1);
    auto *ids = ggml_new_tensor_2d(c,GGML_TYPE_I32,ranks,1);
    ggml_set_input(x);
    ggml_set_input(ids);
    ggml_backend_sched_ptr sched(ggml_backend_sched_new(&cpu,nullptr,1,128,false,false));
    auto *graph = ggml_new_graph_custom(c,128,false);
    std::vector<ggml_tensor *> outputs;
    for (const auto &weight : layer.weights) {
        auto *y = ggml_mul_mat_id(c,weight.cache,x,ids);
        ggml_set_output(y);
        ggml_build_forward_expand(graph,y);
        outputs.push_back(y);
    }
    check(ggml_backend_sched_alloc_graph(sched.get(),graph),"scheduler cache views");
    std::array<float,width> input{};
    for (int i=0;i<width;++i) input[i] = float((i*17)%97-48) / 64.0f;
    ggml_backend_tensor_set(x,input.data(),0,sizeof(input));
    ggml_backend_tensor_set(ids,places.data(),0,sizeof(places));
    check(ggml_backend_sched_graph_compute(sched.get(),graph)==GGML_STATUS_SUCCESS,"scheduled projections");
    ggml_backend_sched_synchronize(sched.get());
    json hashes=json::array();
    for (auto *y : outputs) {
        std::array<float,width*ranks> values;
        check(ggml_nbytes(y)==sizeof(values) && ggml_backend_sched_get_tensor_backend(sched.get(),y)==cpu,
              "output geometry or provider");
        ggml_backend_tensor_get(y,values.data(),0,sizeof(values));
        check(std::all_of(values.begin(),values.end(),[](float v){return std::isfinite(v);}),"non-finite output");
        check(std::fwrite(values.data(),1,sizeof(values),raw)==sizeof(values),"raw output");
        hashes.push_back(digest(values.data(),sizeof(values)));
    }
    return {{"sha256",hashes},{"splits",ggml_backend_sched_get_n_splits(sched.get())},
            {"workspace_B",ggml_backend_sched_get_buffer_size(sched.get(),cpu)}};
}

static json run(const json &plan, const std::string &role, FILE *raw) {
    const bool shared = role != "STAGED";
    check(shared ? role=="SHARED" || role=="WRONG" : true,"unknown role");
    check(!std::getenv("TESY_PACKED_CPU_SLOTS") &&
          !setenv("TESY_PACKED_CPU_SLOTS",shared ? "shared" : "staged",1),"select CPU owner");
    ggml_backend_ptr cpu(ggml_backend_cpu_init());
    check(bool(cpu),"CPU backend");
    ggml_backend_cpu_set_n_threads(cpu.get(),8);
    ggml_context_ptr meta(ggml_init({2u<<20,nullptr,true})), scratch(ggml_init({2u<<20,nullptr,false}));
    llama_moe_stream manager(36,40,4,true);
    std::set<ggml_tensor *> owners;
    for (int l=0;l<25;++l) {
        for (int k=0;k<3;++k) {
            auto *t=ggml_new_tensor_3d(meta.get(),GGML_TYPE_MXFP4,width,width,128);
            ggml_set_name(t,Store::component_name(l,k,"weight").c_str());
            manager.create_cache_tensor(l,ggml_backend_cpu_buffer_type(),t,0,0);
        }
        auto *sl=manager.layer(l);
        check(sl && sl->n_slots==40 && sl->weights.size()==3,"logical geometry");
        owners.insert(sl->packed_owner);
    }
    manager.alloc_bufs(false);
    const size_t count = shared ? 1252 : 1000;
    check(owners.size()==(shared ? 1u : 25u) && !owners.count(nullptr) &&
          manager.size_bufs()>=count*Store::window &&
          manager.size_bufs()<=count*Store::window+8192*owners.size(),"single storage budget");
    std::set<ggml_backend_buffer_t> buffers;
    for (int l=0;l<25;++l) {
        auto *sl=manager.layer(l);
        for (int k=0;k<3;++k) {
            auto *v=sl->weights[k].cache;
            check(v->view_src==sl->packed_owner && v->buffer==sl->packed_owner->buffer &&
                  v->ne[2]==(shared ? 1252 : 40) && v->nb[2]==Store::window &&
                  v->data==static_cast<uint8_t *>(sl->packed_owner->data)+k*Store::slab &&
                  ggml_backend_buffer_is_host(v->buffer),"layer matrix view");
            buffers.insert(v->buffer);
        }
    }
    check(buffers.size()==owners.size(),"duplicated or missing owners");
    if (shared) {
        for (int s=0;s<ranks;++s) {
            manager.layer(0)->cpu_frames[s]=1248+s;
            manager.layer(24)->cpu_frames[s]=s;
        }
        std::set<int> used;
        for (int l=0;l<25;++l) for (int s=0;s<40;++s) {
            const int f=manager.layer(l)->weight_frame(s);
            check(f>=0 && f<1252 && used.insert(f).second,"primary frame alias");
        }
        check(used.size()==1000,"primary frames");
    }

    manager.expert_store=std::make_unique<Store>();
    auto &store=*manager.expert_store;
    store.data.open_file(plan.at("pack").get<std::string>().c_str());
    pack_fd=store.data.descriptor();
    check((fcntl(pack_fd,F_GETFL)&O_DIRECT) && store.data.file_size()==plan.at("pack_stat").at("size_bytes"),
          "original direct pack");
    std::vector<off_t> expected;
    for (const auto &row : plan.at("records")) {
        const int l=row.at("layer"), e=row.at("expert");
        auto &entry=store.entries.at(l).at(e);
        entry.offset=row.at("offset");
        entry.relative={0,Store::slab,2*Store::slab};
        expected.push_back(entry.offset);
    }

    auto *ids=ggml_new_tensor_2d(scratch.get(),GGML_TYPE_I32,ranks,1);
    auto *dst=ggml_dup_tensor(scratch.get(),ids);
    auto *mask=ggml_new_tensor_2d(scratch.get(),GGML_TYPE_F32,ranks,1);
    dst->src[0]=ids;
    mask->src[0]=ids;
    std::memcpy(ids->data,logical.data(),sizeof(logical));
    json visits=json::array();
    Ids peer{};
    for (int l : {0,24,0}) {
        auto &sl=*manager.layer(l);
        llama_moe_stream_remap(dst,ids,0,1,&sl);
        Ids place{};
        std::memcpy(place.data(),dst->data,sizeof(place));
        for (int r=0;r<ranks;++r) {
            const int f=shared && l==0 ? 1248+r : r;
            check(place[r]==f && sl.expert_slot.at(logical[r])==r && sl.slot_gen[r]==1 &&
                  sl.slot_state[r]==LLAMA_MOE_STREAM_SLOT_RESIDENT && !sl.slot_claimed[r],"published generation");
            const auto &row=plan.at("records").at((l==24 ? ranks : 0)+r);
            check(row.at("expert")==logical[r] && row.at("layer")==l,"target identity");
            for (int k=0;k<3;++k) {
                auto *v=sl.weights[k].cache;
                const auto *p=static_cast<const uint8_t *>(v->data)+size_t(f)*v->nb[2];
                check(digest(p,Store::slab)==row.at("sha").at(k),"expert or layer payload");
            }
        }
        for (int w=0;w<2;++w) {
            auto *ud=sl.wave_userdata(w,18);
            llama_moe_stream_wave_ids(dst,0,1,ud);
            llama_moe_stream_wave_mask(mask,0,1,ud);
            for (int r=0;r<ranks;++r)
                check(static_cast<int32_t *>(dst->data)[r]==(w ? -1 : place[r]) &&
                      static_cast<float *>(mask->data)[r]==(w ? 0.f : 1.f),"wave address or parking");
        }
        if(l==24) peer=place;
        const Ids arithmetic=(role=="WRONG" && visits.size()==2) ? peer : place;
        visits.push_back({{"layer",l},{"frames",place},{"computed",arithmetic},
            {"projections",projections(cpu.get(),sl,arithmetic,raw)},{"reads_after",manager.stats.n_store_loads}});
    }
    check(manager.workers.size()==4 && !manager.load_failed && manager.q_demand.empty() &&
          manager.stats.n_store_loads==8 && manager.stats.n_store_read_bytes==int64_t(8*Store::weights),
          "native FIFO, accounting or drain");
    std::sort(reads.begin(),reads.end());
    std::sort(expected.begin(),expected.end());
    check(reads==expected && reads.size()==8 && weight_sets==24 && producers.size()<=4,"paid original operations");
    return {{"role",role},{"owners",owners.size()},{"data_buffers",buffers.size()},{"views",75},
            {"allocation_B",manager.size_bufs()},{"addressed_records",count},{"visits",visits},
            {"requested_pack_B",reads.size()*Store::window},{"reads",reads.size()},{"sets",weight_sets},
            {"workers",manager.workers.size()},{"reading_workers",producers.size()}};
}

int main(int argc,char **argv) {
    try {
        check(argc==4,"plan, role, new F32 output");
        std::ifstream f(argv[1]);
        json plan; f>>plan;
        std::unique_ptr<FILE,decltype(&std::fclose)> raw(std::fopen(argv[3],"wbx"),&std::fclose);
        check(bool(raw),"exclusive output");
        const auto report=run(plan,argv[2],raw.get());
        check(std::fflush(raw.get())==0,"flush raw output");
        std::cout<<report.dump()<<"\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr<<e.what()<<"\n";
        return 1;
    }
}
