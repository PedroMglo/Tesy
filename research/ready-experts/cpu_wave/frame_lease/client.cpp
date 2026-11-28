// Submit the pinned CPU0 FFN with its original arithmetic and a competing frame replacement.
#include "ggml-cpp.h"
#include "ggml-cpu.h"
#include <nlohmann/json.hpp>
#include <openssl/sha.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace fs = std::filesystem;
using json = nlohmann::json;
constexpr int width = 2880, nt = 32, ranks = 4, waves = 8, contested = 1249;
constexpr size_t slab = 4406400, window = 13221888, frames = 1252;
static void need(bool ok, const char *message) {
    if (!ok) { std::cerr << message << std::endl; std::_Exit(2); }
}
#include "helpers.inc"
#include "arithmetic.inc"
#include "lease.h"

static std::string digest(const void *data, size_t bytes) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    SHA256(static_cast<const unsigned char *>(data), bytes, hash);
    const char *hex = "0123456789abcdef";
    std::string result;
    for (auto c : hash) { result += hex[c >> 4]; result += hex[c & 15]; }
    return result;
}
static json load(const fs::path &p) {
    std::ifstream input(p);
    json result;
    input >> result;
    need(bool(input), "JSON read");
    return result;
}
static ggml_context_ptr graph_context() {
    ggml_context_ptr ctx(ggml_init({16u << 20, nullptr, true}));
    need(bool(ctx), "graph metadata");
    return ctx;
}

struct Routed {
    std::vector<float> x, mix, gold;
    std::vector<int> ranks, places;
    std::vector<float> masks;
    std::array<std::map<int,int>, waves> bindings;
    json signature;
};

static Routed route(const json &plan, const std::string &name, ggml_backend_t cpu) {
    const fs::path inputs = plan.at("inputs").get<std::string>();
    const auto p = inputs / name;
    const int n = name == "five" ? 153 : 32, first = n == 153 ? 32 : 0;
    auto ctx = graph_context();
    auto *c = ctx.get();
    auto *x = ggml_new_tensor_2d(c, GGML_TYPE_F32, width, n);
    auto *w = ggml_new_tensor_2d(c, GGML_TYPE_F32, width, 128);
    auto *b = ggml_new_tensor_1d(c, GGML_TYPE_F32, 128);
    auto *logits = ggml_mul_mat(c,w,x), *biased = ggml_add(c,logits,b);
    auto *ids = ggml_cont(c,ggml_argsort_top_k(c,biased,ranks));
    auto *mix = ggml_get_rows(c,ggml_reshape_3d(c,biased,1,128,n),ids);
    mix = ggml_cont(c,ggml_reshape_3d(c,ggml_soft_max(c,ggml_reshape_2d(c,mix,ranks,n)),1,ranks,n));
    auto *g = ggml_new_graph(c);
    ggml_build_forward_expand(g,ids);
    ggml_build_forward_expand(g,mix);
    ggml_backend_buffer_ptr buf(ggml_backend_alloc_ctx_tensors(c,cpu));
    need(bool(buf), "router buffer");
    auto inputs_x = read<float>(p/"x",width*n);
    put(x,inputs_x);
    put(w,read<float>(inputs/"router.weight",128*width));
    put(b,read<float>(inputs/"router.bias",128));
    need(ggml_backend_graph_compute(cpu,g) == GGML_STATUS_SUCCESS, "target router");
    ggml_backend_synchronize(cpu);
    Routed r;
    const auto all_ids = values<int>(ids);
    const auto all_mix = values<float>(mix);
    equal(all_ids, read<int>(p/"ranks",n*ranks), "target top four");
    equal(all_mix, read<float>(p/"mix",n*ranks), "target mixing weights");
    equal(values<float>(logits), read<float>(p/"logits",128*n), "target router logits");
    equal(values<float>(biased), read<float>(p/"biased",128*n), "target biased router logits");
    r.signature = {{"positions",n},{"first",first},{"ranks",digest(all_ids.data(),all_ids.size()*4)},
                   {"mix",digest(all_mix.data(),all_mix.size()*4)},
                   {"logits",digest(logits->data,ggml_nbytes(logits))},
                   {"biased",digest(biased->data,ggml_nbytes(biased))}};
    r.x.assign(inputs_x.begin()+first*width, inputs_x.begin()+(first+nt)*width);
    r.ranks.assign(all_ids.begin()+first*ranks, all_ids.begin()+(first+nt)*ranks);
    r.mix.assign(all_mix.begin()+first*ranks, all_mix.begin()+(first+nt)*ranks);
    r.gold = read<float>(p/"ffn",width*nt);
    r.places = read<int>(plan.at("places").at(name).get<std::string>(),waves*nt*ranks);
    r.masks = read<float>(p/"masks",waves*nt*ranks);
    std::map<int,int> owner_wave;
    for (int wave=0; wave<waves; ++wave) {
        std::map<int,int> reverse;
        for (int j=0; j<nt*ranks; ++j) {
            int i=wave*nt*ranks+j, e=r.ranks[j], slot=r.places[i];
            need(slot>=-1 && slot<40 && r.masks[i] == (slot<0 ? 0.f : 1.f), "parked or active mask");
            if (slot<0) continue;
            need(r.bindings[wave].emplace(e,slot).first->second==slot, "logical slot consistency");
            need(reverse.emplace(slot,e).first->second == e, "two experts alias primary");
            need(owner_wave.emplace(e,wave).first->second == wave, "two active waves for expert");
        }
    }
    need(r.bindings[0].at(r.ranks[0])==0 && owner_wave.size()==(name=="five" ? 5u : 66u),
         "chosen first-wave consumer and routed expert count");
    return r;
}

struct Arena {
    unsigned char *data;
    ggml_backend_buffer_ptr buf;
    std::array<int,128> bank{};
    std::vector<unsigned char> saved;
    int reads = 0, checks = 0;
    unsigned char *at(int frame) { return data + frame*window; }
    Arena(const json &plan, const Routed &r) : saved(window) {
        data = static_cast<unsigned char *>(mmap(nullptr, frames*window, PROT_READ|PROT_WRITE,
                                            MAP_ANONYMOUS|MAP_PRIVATE,-1,0));
        need(data!=MAP_FAILED,"arena mmap");
        buf.reset(ggml_backend_cpu_buffer_from_ptr(data,frames*window));
        need(bool(buf),"host arena");
        ggml_backend_buffer_set_usage(buf.get(),GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
        const int fd=open(plan.at("pack").get<std::string>().c_str(),O_RDONLY|O_CLOEXEC|O_DIRECT);
        need(fd>=0 && (fcntl(fd,F_GETFL)&O_DIRECT), "read-only direct pack");
        const auto &id=plan.at("pack_stat");
        auto identity = [&] {
            struct stat st{};
            need(fstat(fd,&st)==0 && st.st_dev==id["dev"] && st.st_ino==id["inode"] &&
                 st.st_size==id["size_bytes"] && st.st_mtim.tv_sec*1000000000LL+st.st_mtim.tv_nsec==id["mtime_ns"] &&
                 st.st_ctim.tv_sec*1000000000LL+st.st_ctim.tv_nsec==id["ctime_ns"], "pack fd identity");
        };
        identity();
        auto fetch = [&](int e,int frame) {
            const auto &row = plan.at("records").at(std::to_string(e));
            const auto offset=row.at("offset").get<off_t>();
            need(offset%4096==0 && pread(fd,at(frame),window,offset)==ssize_t(window), "short expert read");
            for (int k=0;k<3;++k) {
                need(digest(at(frame)+k*slab,slab)==row.at("sha").at(k).get<std::string>(),
                     "incorrect original MXFP4 matrix");
                ++checks;
            }
            ++reads;
        };
        bank.fill(-1);
        std::set<int> keys(r.ranks.begin(),r.ranks.end());
        int index=1000;
        for (int e:keys) { bank[e]=e==r.ranks[0] ? contested : index++; fetch(e,bank[e]); }
        int k=0;
        for (int e=0;k<4;++e) if (!keys.count(e)) fetch(e,980+k++);
        std::memcpy(saved.data(),at(contested),window);
        identity();
        need(close(fd)==0 && index<contested,"initialized frame bank");
    }
    ~Arena() { buf.reset(); munmap(data,frames*window); }
};

struct Submission {
    Arena &arena;
    const Routed &r;
    Replacements &replacement;
    std::array<ggml_tensor *,6> tensors{};
    std::array<int,40> resident;
    int common_sets=0, hit_sets=0, id_calls=0, mask_calls=0;

    void stage(int e,int slot,bool hit) {
        static constexpr int packed[] = {0,2,1}; // GGML order gate/up/down, pack gate/down/up.
        for (int k=0;k<3;++k)
            ggml_backend_tensor_set(tensors[k],arena.at(arena.bank[e])+packed[k]*slab,slot*window,slab);
        (hit ? hit_sets : common_sets) += 3;
        resident[slot]=e;
    }
};

struct Wave { Submission *step; int w; };

static void publish_ids(ggml_tensor *dst,int ith,int,void *opaque) {
    if (ith) return;
    auto [step,w]=*static_cast<Wave *>(opaque);
    const auto &r=step->r;
    need(w==step->id_calls++, "graph wave dispatch order");
    for (auto [e,slot]:r.bindings[w]) {
        bool hit = (e==r.ranks[0]);
        if (hit && step->replacement.direct()) continue;
        if (step->resident[slot]!=e) step->stage(e,slot,hit);
    }
    auto *out=static_cast<int *>(dst->data);
    const auto *logical=static_cast<const int *>(dst->src[0]->data);
    for (int j=0;j<nt*ranks;++j) {
        const int e=logical[j];
        need(e==r.ranks[j], "target rank changed in graph");
        const int native=r.places[w*nt*ranks+j];
        out[j]=(native>=0 && e==r.ranks[0] && step->replacement.direct()) ? contested : native;
        need((out[j]<0)==(r.masks[w*nt*ranks+j]==0) &&
             (out[j]<0 || out[j]==contested || step->resident[out[j]]==e), "unpublished selection");
    }
    if (w==0) step->replacement.launch();
}

static void wave_mask(ggml_tensor *dst,int ith,int,void *opaque) {
    if (ith) return;
    auto [step,w]=*static_cast<Wave *>(opaque);
    need(w==step->mask_calls++, "mask call order");
    auto *out=static_cast<float *>(dst->data);
    const auto *logical=static_cast<const int *>(dst->src[0]->data);
    const auto *physical=static_cast<const int *>(dst->src[1]->data);
    for (int j=0;j<nt*ranks;++j) {
        out[j]=step->r.bindings[w].count(logical[j]) ? 1.f : 0.f;
        need(out[j]==step->r.masks[w*nt*ranks+j] && (out[j]>0)==(physical[j]>=0), "target mask");
    }
}

static void before(ggml_tensor *dst,const ggml_tensor *src,int ith,int,void *p) {
    if (!ith) { need(dst->data==src->data,"in-place activation"); static_cast<Replacements *>(p)->before_down(); }
}
static void after(ggml_tensor *dst,const ggml_tensor *src,int ith,int,void *p) {
    if (!ith) { need(dst->data==src->data,"in-place down output"); static_cast<Replacements *>(p)->after_down(); }
}

static std::string tensor_hash(ggml_tensor *t) {
    need(t->type==GGML_TYPE_F32 && t->nb[0]==4, "F32 witness");
    std::vector<float> ordered;
    ordered.reserve(ggml_nelements(t));
    for (int64_t i3=0;i3<t->ne[3];++i3) for (int64_t i2=0;i2<t->ne[2];++i2)
        for (int64_t i1=0;i1<t->ne[1];++i1) {
            const auto off=i3*t->nb[3]+i2*t->nb[2]+i1*t->nb[1];
            const auto *row=reinterpret_cast<const float *>(static_cast<const char *>(t->data)+off);
            ordered.insert(ordered.end(),row,row+t->ne[0]);
        }
    for(float f:ordered) need(std::isfinite(f),"nonfinite intermediate");
    return digest(ordered.data(),ordered.size()*4);
}

static json trial(ggml_backend_t cpu,Arena &arena,const Routed &r,const fs::path &inputs,
                  const std::string &role,bool exact) {
    std::memcpy(arena.at(contested),arena.saved.data(),window);
    Replacements replacement(arena.data,window,contested,role,exact);
    Submission sub{arena,r,replacement};
    sub.resident.fill(-1);
    const size_t count=role=="COPY40" ? 40 : frames;
    auto meta=graph_context(), biases=graph_context(), graph=graph_context();
    const std::array<std::string,3> names={"gate","up","down"};
    const int packed[]={0,2,1};
    for (int k=0;k<3;++k) {
        auto *t=ggml_new_tensor_3d(meta.get(),GGML_TYPE_MXFP4,width,width,count);
        need(t->nb[2]==slab,"matrix geometry");
        t->nb[2]=window; t->nb[3]=count*window;
        need(ggml_backend_tensor_alloc(arena.buf.get(),t,arena.data+packed[k]*slab)==GGML_STATUS_SUCCESS,
             "strided CPU weights");
        sub.tensors[k]=t;
        sub.tensors[k+3]=ggml_new_tensor_2d(biases.get(),GGML_TYPE_F32,width,128);
    }
    ggml_backend_buffer_ptr biasbuf(ggml_backend_alloc_ctx_tensors(biases.get(),cpu));
    need(bool(biasbuf),"bias tensors");
    for (int k=0;k<3;++k) put(sub.tensors[k+3],read<float>(inputs/(names[k]+".bias"),width*128));
    for (auto [e,slot]:r.bindings[0]) if(e!=r.ranks[0]) sub.stage(e,slot,false);
    sub.common_sets=0;
    auto *c=graph.get();
    auto *g=ggml_new_graph_custom(c,1024,false);
    auto *x=ggml_new_tensor_2d(c,GGML_TYPE_F32,width,nt);
    auto *ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,ranks,nt);
    auto *mix=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,ranks,nt);
    for (auto *v:{x,ids,mix}) ggml_set_input(v);
    std::map<std::string,ggml_tensor *> cuts;
    auto audit = [&](std::string name,ggml_tensor *t) {
        if (exact) { ggml_set_output(t); cuts.emplace(std::move(name),t); }
    };
    std::array<Wave,waves> contexts;
    ggml_tensor *sum=nullptr;
    for (int w=0;w<waves;++w) {
        contexts[w]={&sub,w};
        ggml_tensor *args[]={ids,sum?ggml_view_1d(c,sum,1,0):nullptr};
        auto *physical=ggml_custom_4d(c,GGML_TYPE_I32,ranks,nt,1,1,args,sum?2:1,publish_ids,1,&contexts[w]);
        auto *result=pairs(c,sub.tensors,x,ids,physical);
        auto *down=result->src[0], *activation=down->src[1];
        need(result->op==GGML_OP_ADD_ID && down->op==GGML_OP_MUL_MAT_ID && down->src[0]==sub.tensors[2],
             "canonical down landmark");
        if(w==0) {
            down->src[1]=ggml_map_custom1_inplace(c,activation,before,1,&replacement);
            result->src[0]=ggml_map_custom1_inplace(c,down,after,1,&replacement);
        }
        const std::string key=std::to_string(w)+"/";
        audit(key+"gate",activation->src[0]->src[0]); audit(key+"gate_bias",activation->src[0]);
        audit(key+"up",activation->src[1]->src[0]); audit(key+"up_bias",activation->src[1]);
        audit(key+"activation",activation); audit(key+"down",down); audit(key+"down_bias",result);
        ggml_tensor *args_mask[]={ids,physical};
        auto *mask=ggml_custom_4d(c,GGML_TYPE_F32,1,ranks,nt,1,args_mask,2,wave_mask,1,&contexts[w]);
        auto *product=ggml_mul(c,result,mask);
        sum=sum?ggml_add(c,sum,product):product;
        audit(key+"mask",mask); audit(key+"product",product); audit(key+"sum",sum);
        ggml_build_forward_expand(g,sum);
    }
    const int start=ggml_graph_n_nodes(g);
    auto *output=finish(c,g,sum,mix);
    int reductions=0;
    for(int i=start;i<ggml_graph_n_nodes(g);++i) {
        auto *t=ggml_graph_node(g,i);
        if(t->op==GGML_OP_ADD) audit("rank_sum"+std::to_string(++reductions),t);
        else if(t->op==GGML_OP_MUL) audit("mixed",t);
    }
    need(reductions==3,"ordered rank reductions");
    ggml_backend_sched_ptr scheduler(ggml_backend_sched_new(&cpu,nullptr,1,1024,false,false));
    need(scheduler && ggml_backend_sched_alloc_graph(scheduler.get(),g),"allocate FFN graph");
    put(x,r.x); put(ids,r.ranks); put(mix,r.mix);
    const int64_t origin=now_ns();
    need(ggml_backend_sched_graph_compute(scheduler.get(),g)==GGML_STATUS_SUCCESS,"CPU0 FFN");
    ggml_backend_sched_synchronize(scheduler.get());
    replacement.drain_graph();
    json j=replacement.finish(origin);
    auto ffn=values<float>(output);
    int mismatches=0;
    for(size_t i=0;i<ffn.size();++i) {
        need(std::isfinite(ffn[i]),"nonfinite FFN");
        mismatches+=std::memcmp(&ffn[i],&r.gold[i],sizeof(float))!=0;
    }
    need((mismatches!=0)==(role=="EARLY") && sub.id_calls==waves && sub.mask_calls==waves &&
         sub.hit_sets==(replacement.direct()?0:3), "FFN reference, callbacks or hit cost");
    j.update({{"role",role},{"ffn",digest(ffn.data(),ffn.size()*4)},{"different_F32",mismatches},
              {"weight_frames",count},{"hit_sets",sub.hit_sets},{"other_sets",sub.common_sets},
              {"wave_calls",sub.id_calls},{"mask_calls",sub.mask_calls},
              {"workspace_B",ggml_backend_sched_get_buffer_size(scheduler.get(),cpu)}});
    if(exact) {
        for (auto &[name,t]:cuts) j["cuts"][name]=tensor_hash(t);
        need(j["cuts"].size()==84,"full numerical audit coverage");
    }
    for(int k=0;k<4;++k) {
        const int dest=k==0?contested:970+k;
        need(!std::memcmp(arena.at(dest),arena.at(980+k),window),"all four published payloads");
    }
    return j;
}

int main(int argc,char **argv) {
    try {
        need(argc==4,"plan, case, exact|price");
        const std::string name=argv[2], phase=argv[3];
        need((name=="five"||name=="many") && (phase=="exact"||phase=="price"),"unknown phase/case");
        const auto plan=load(argv[1]);
        check_generations();
        ggml_backend_ptr cpu(ggml_backend_cpu_init());
        need(bool(cpu),"pinned CPU backend");
        ggml_backend_cpu_set_n_threads(cpu.get(),8);
        auto routed=route(plan,name,cpu.get());
        Arena arena(plan,routed);
        const fs::path inputs=plan.at("inputs").get<std::string>();
        json rows=json::array();
        std::vector<std::string> order={"COPY40","COPY1252","DRAIN","LAST"};
        auto one=[&](const std::string &role,bool exact,int block,int direction) {
            auto row=trial(cpu.get(),arena,routed,inputs,role,exact);
            row["block"]=block; row["direction"]=direction;
            rows.push_back(std::move(row));
        };
        if (phase=="exact") {
            for(auto &role:order) one(role,true,0,0);
            one("EARLY",true,0,0);
        } else {
            for(auto &role:order) one(role,false,0,0);
            for(int p=1;p<=7;++p) for(int dir=0;dir<2;++dir)
                for(int j=0;j<4;++j) one(order[dir?3-j:j],false,p,dir);
        }
        json receipt={{"case",name},{"phase",phase},{"router",routed.signature},
                      {"witness_expert",routed.ranks[0]},{"pack_reads",arena.reads},
                      {"matrix_hashes",arena.checks},{"rows",rows}};
        std::cout<<receipt.dump()<<'\n';
    } catch(const std::exception &e) { std::cerr<<e.what()<<std::endl; return 1; }
}
