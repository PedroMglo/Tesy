// Model-free producer and authoritative remap on the original C291 CPU manager.
#include "lookahead.h"
#include "ggml-cpu.h"
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <numeric>

using json = nlohmann::json;
struct TestBatch {
    int n_tokens;
    const int32_t *pos;
    const int8_t *output = nullptr;
    const int32_t *n_seq_id = nullptr;
    int32_t *const *seq_id = nullptr;
    int outputs = 0;
};
struct ModelLike { llama_moe_stream &m; llama_moe_stream *moe_stream() { return &m; } };
struct ContextLike {
    ModelLike model;
    std::function<int()> run;
    ModelLike &get_model() { return model; }
    int decode(TestBatch) { return run(); }
};
#include "borrowed-context.inc"

using Quartet = std::array<int32_t,4>;
using Features = std::array<float,6>;
void need(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }

Features materialize_source(int position, int source_layer) {
    Features result{};
    const int first = (position + source_layer + 1 + (position % 3 == 0)) % 6;
    for (int k=0; k<6; ++k) result[(first+k)%6] = float(6-k);
    return result;
}
Quartet project(const Features &signal) {
    // Small, independent pointwise router. No target ID or cache input.
    static const auto matrix = [] {
        std::array<Features,6> weights{};
        for (int i=0; i<6; ++i) weights[i][i] = 1;
        return weights;
    }();
    std::array<int,6> ids{0,1,2,3,4,5};
    Features scores{};
    for (int e=0; e<6; ++e)
        scores[e] = std::inner_product(matrix[e].begin(), matrix[e].end(), signal.begin(), 0.f);
    std::sort(ids.begin(), ids.end(), [&](int a,int b){ return scores[a] > scores[b]; });
    return {ids[0],ids[1],ids[2],ids[3]};
}

Quartet official(int position, int layer) {
    const int k = (position+layer)%6;
    return {k,(k+1)%6,(k+2)%6,position==2197 ? 6 : (k+3)%6};
}

void run_layer(llama_moe_stream &m, int layer, const std::vector<int32_t> &positions,
               const std::vector<int> &indices, bool late, json &report) {
    const size_t n = indices.size();
    if (!n) return;
    std::vector<Quartet> shadow(n);
    if (pfj::active()) {
        std::vector<Features> features;
        for (int i:indices) features.push_back(materialize_source(positions[i],layer-1));
        lookahead::begin(m,layer,n*sizeof(Features),6*sizeof(Features));
        for (size_t i=0; i<n; ++i) shadow[i] = project(features[i]);
    }
    const auto publish = [&] {
        if (pfj::active())
            for (size_t i=0; i<n; ++i)
                lookahead::publish(m,layer,indices[i],positions[indices[i]],shadow[i].data());
    };
    if (!late) publish();

    ggml_context_ptr ctx(ggml_init({1u<<20,nullptr,false}));
    need(bool(ctx),"input context");
    auto *ids = ggml_new_tensor_2d(ctx.get(), GGML_TYPE_I32, 4, n);
    auto *slots = ggml_dup_tensor(ctx.get(),ids);
    auto *input = static_cast<int32_t *>(ids->data);
    for (size_t i=0; i<n; ++i) {
        auto truth = official(positions[indices[i]], layer);
        std::copy(truth.begin(),truth.end(),input+4*i);
    }
    auto &sl = *m.layer(layer);
    llama_moe_stream_remap(slots,ids,0,1,&sl);
    if (late) publish(); // deliberately delay disclosure; START never gives usable predictions
    const auto *output = static_cast<const int32_t *>(slots->data);
    std::lock_guard<std::mutex> lock(m.mtx);
    for (size_t i=0; i<n; ++i) {
        Quartet mapped{};
        for (int k=0; k<4; ++k) {
            const int expert=input[4*i+k], slot=output[4*i+k];
            need(slot>=0 && slot<40 && sl.slot_expert[slot]==expert && sl.slot_gen[slot]==1 &&
                 sl.slot_state[slot]==LLAMA_MOE_STREAM_SLOT_RESIDENT, "routed binding");
            for (int c=0;c<3;++c) {
                uint8_t data[128];
                ggml_backend_tensor_get(sl.weights[c].cache,data,slot*sizeof(data),sizeof(data));
                const int tag = (7*layer+13*c+expert) & 255;
                need(std::all_of(data,data+128,[tag](uint8_t x){return x==tag;}), "payload");
            }
            mapped[k]=slot;
        }
        report["rows"].push_back({positions[indices[i]],layer,official(positions[indices[i]],layer),mapped});
    }
}

json run(const char *data) {
    json r; r["rows"]=json::array();
    ggml_context_ptr ctx(ggml_init({ggml_tensor_overhead()*110,nullptr,true}));
    need(bool(ctx),"cache tensor metadata");
    {
        llama_moe_stream m(36,40,4,true);
        const char *roles[]{"gate","down","up"};
        for (int l=0;l<36;++l) for (int k=0;k<3;++k) {
            auto *w=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_I8,128,1,128);
            ggml_format_name(w,"blk.%d.ffn_%s_exps.weight",l,roles[k]);
            m.create_cache_tensor(l,ggml_backend_cpu_buffer_type(),w,0,(3*l+k)*16384);
        }
        m.alloc_bufs(false);
        m.open_files({data});
        need(m.use_direct_io,"direct file descriptor");
        int pos=2044;
        for (const int length : {5,148,1}) {
            std::vector<int32_t> all(length);
            std::iota(all.begin(),all.end(),pos);
            ContextLike c{{m},[&] {
                for(int first=0;first<length;first+=32) {
                    const int n=std::min(32,length-first);
                    std::vector<int32_t> positions(all.begin()+first,all.begin()+first+n);
                    auto step=[&](int,bool) {
                        std::vector<int> active(n),selected;
                        std::iota(active.begin(),active.end(),0);
                        for(int i=0;i<n;++i) if(first+i==length-1) selected.push_back(i);
                        run_layer(m,1,positions,active,length==1,r);
                        run_layer(m,35,positions,selected,false,r);
                        return 0;
                    };
                    std::vector<int8_t> mask(n,0);
                    int count = (first + n == length);
                    if (count) mask.back() = 1;
                    std::vector<int32_t> seq_counts(n,1);
                    int32_t sequence=0;
                    std::vector<int32_t*> sequences(n,&sequence);
                    TestBatch tile{n,positions.data(),mask.data(),seq_counts.data(),sequences.data(),count};
                    need(borrowed_graph(ModelLike{m},tile,step)==0,"tile");
                }
                return 0;
            }};
            need(borrowed_call(&c, TestBatch{length,all.data()})==0,"call");
            pos+=length;
        }
        need(!m.load_failed && m.workers.size()==4 && m.q_demand.empty(),"pool drain");
        r["misses"]=m.stats.n_miss; r["hits"]=m.stats.n_hit;
    }
    r["status"]="PASS_MARKER_BINDINGS_AND_DRAIN";
    return r;
}
int main(int argc,char **argv) {
    try {
        need(argc==3,"expected source and new result");
        auto report=run(argv[1]); std::ofstream f(argv[2]); f<<report.dump()<<'\n';
        f.close(); need(bool(f),"write native receipt"); return 0;
    } catch(const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
