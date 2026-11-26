// Capture one real GGML CPU graph view. Never delegate to the arithmetic kernel.
// Build as a diagnostic preload, exclusively for the descriptor-only driver.
#include "ggml-cpu.h"
#include "ggml-impl.h"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using json = nlohmann::json;
using Tensor = ggml_tensor;
constexpr char expected_fingerprint[] = "e569253a2f984a84";
constexpr std::array<const char *,3> weight_names = {
    "blk.0.ffn_gate_exps.weight.stream_cache", "blk.0.ffn_down_exps.weight.stream_cache",
    "blk.0.ffn_up_exps.weight.stream_cache"};
static void need(bool test, const std::string &why) {
    if (!test) throw std::runtime_error(why);
}

struct Graph {
    ggml_cgraph *g;
    std::vector<Tensor *> nodes;
    std::map<const Tensor *, int> indices;
    std::array<const Tensor *,3> weights{};
    std::map<const Tensor *, std::vector<int>> users;
    std::map<const Tensor *, size_t> keys;

    explicit Graph(ggml_cgraph *graph) : g(graph) {
        need(g != nullptr && ggml_graph_n_nodes(g)>0 && ggml_graph_n_nodes(g)<=2048,"graph size");
        for (int i=0;i<ggml_graph_n_nodes(g);++i) {
            auto *p=ggml_graph_node(g,i);
            need(p && indices.emplace(p,i).second,"duplicate or missing graph node");
            nodes.push_back(p);
            for (const auto *s:p->src) if (s) users[s].push_back(i);
            if (p->op==GGML_OP_MUL_MAT_ID) {
                for (size_t j=0;j<weights.size();++j)
                    if (p->src[0] && std::string(p->src[0]->name)==weight_names[j]) {
                        need(!weights[j] || weights[j]==p->src[0],"ambiguous weight role");
                        weights[j]=p->src[0];
                    }
            }
        }
        for (const Tensor *weight:weights) key(weight);
        for (const Tensor *p:nodes) key(p);
    }
    size_t key(const Tensor *p) {
        if (!p) return 0;
        return keys.emplace(p,keys.size()+1).first->second;
    }
    int idx(const Tensor *p) const {
        auto it=indices.find(p);
        return it==indices.end() ? -1 : it->second;
    }
    int only_user(const Tensor *p, ggml_op op, int slot) const {
        int found=-1;
        auto it=users.find(p);
        if (it!=users.end()) for (int i:it->second) {
            if (nodes[i]->op!=op || nodes[i]->src[slot]!=p) continue;
            if (found!=-1 && found!=i) return -1;
            found=i;
        }
        return found;
    }
    std::string describe(json &flat) {
        uint64_t h=UINT64_C(14695981039346656037);
        auto add=[&](uint64_t x){for (unsigned j=0;j<8;++j){h^=(x>>(8*j))&255;h*=UINT64_C(1099511628211);}};
        add(nodes.size());
        for (const Tensor *p:nodes) {
            json src=json::array(),shape=json::array(),strides=json::array();
            add(key(p));add(p->op);add(p->type);
            for (int d=0;d<GGML_MAX_DIMS;++d) {
                add(p->ne[d]);add(p->nb[d]);shape.push_back(p->ne[d]);strides.push_back(p->nb[d]);
            }
            add(key(p->view_src));add(p->view_offs);
            for (const auto *s:p->src) { add(key(s));src.push_back(key(s)); }
            const int i=idx(p);
            flat.push_back({{"index",i},{"key",key(p)},{"op",ggml_op_name(p->op)},
                {"type",ggml_type_name(p->type)},{"shape",shape},{"strides",strides},
                {"sources",src},{"view_key",key(p->view_src)},{"view_offset",p->view_offs},
                {"output",bool(p->flags&GGML_TENSOR_FLAG_OUTPUT)},{"compute",bool(p->flags&GGML_TENSOR_FLAG_COMPUTE)},
                {"use_count",ggml_node_get_use_count(g,i)}});
        }
        std::ostringstream s;s<<std::hex<<std::setfill('0')<<std::setw(16)<<h;return s.str();
    }
};

struct WaveState {
    Tensor *last_sum=nullptr;
    Tensor *logical=nullptr;
    ggml_custom_op_t remap=nullptr,mask=nullptr;
    std::set<void *> userdata;
};
static ggml_custom_op_params custom(Tensor *p) {
    ggml_custom_op_params params{};
    static_assert(sizeof(params)<=sizeof(p->op_params));
    std::memcpy(&params,p->op_params,sizeof(params));
    return params;
}

static void examine(Graph &graph, Tensor *glu, int wave, WaveState &state, json &row) {
    auto &all=graph.nodes;
    Tensor *bias_g=glu->src[0], *bias_u=glu->src[1];
    need(ggml_get_glu_op(glu)==GGML_GLU_OP_SWIGLU_OAI && bias_g && bias_u &&
         bias_g!=bias_u && bias_g->op==GGML_OP_ADD_ID && bias_u->op==GGML_OP_ADD_ID,"gate/up bias -> OAI GLU");
    Tensor *gate=bias_g->src[0], *up=bias_u->src[0];
    need(gate && up && gate!=up && gate->op==GGML_OP_MUL_MAT_ID && up->op==GGML_OP_MUL_MAT_ID &&
         gate->src[1]==up->src[1],"separate gate/up projections");
    Tensor *physical=gate->src[2], *logical=bias_g->src[2];
    need(physical && logical && physical!=logical && up->src[2]==physical && bias_u->src[2]==logical &&
         physical->op==GGML_OP_CUSTOM && physical->src[0]==logical,"common logical and wave remap IDs");
    int down_index=graph.only_user(glu,GGML_OP_MUL_MAT_ID,1);
    need(down_index>=0,"GLU -> unique down projection");
    Tensor *down=all[down_index];
    need(down->src[2]==physical && graph.weights[0]==gate->src[0] &&
         graph.weights[1]==down->src[0] && graph.weights[2]==up->src[0],"roles or down physical IDs");
    const int b=graph.only_user(down,GGML_OP_ADD_ID,0);
    const int m=graph.only_user(physical,GGML_OP_CUSTOM,1);
    need(b>=0 && m>=0,"retained down bias or retained mask");
    Tensor *down_bias=all[b], *mask=all[m];
    need(down_bias->src[2]==logical && mask->src[0]==logical,"tail logical IDs");
    for (auto *a:{bias_g,bias_u,down_bias})
        need(a->src[1] && a->src[1]->type==GGML_TYPE_F32 && a->src[1]->ne[0]==2880 &&
             a->src[1]->ne[1]==128,"bias dimensions");
    need(std::set<Tensor *>{bias_g->src[1],bias_u->src[1],down_bias->src[1]}.size()==3,"three distinct biases");
    const int product=graph.only_user(down_bias,GGML_OP_MUL,0);
    need(product>=0 && all[product]->src[1]==mask,"masked down bias");
    const auto r=custom(physical), k=custom(mask);
    need(r.fun && k.fun && r.fun!=k.fun && r.n_tasks==1 && k.n_tasks==1 &&
         r.userdata && r.userdata==k.userdata && state.userdata.insert(r.userdata).second,"wave custom operators");
    if (wave==0) {
        need(!physical->src[1],"first remap depends on prior wave");
        state.logical=logical;state.remap=r.fun;state.mask=k.fun;state.last_sum=all[product];
    } else {
        need(logical==state.logical && r.fun==state.remap && k.fun==state.mask,"wave owner or logical IDs");
        const auto *prev=physical->src[1];
        need(prev && prev->op==GGML_OP_VIEW && prev->src[0]==state.last_sum,"previous sum -> ordered remap");
        const int sum=graph.only_user(all[product],GGML_OP_ADD,1);
        need(sum>=0 && all[sum]->src[0]==state.last_sum,"ordered accumulation");
        state.last_sum=all[sum];
    }
    row["tail"]={{"remap",graph.idx(physical)},{"down_bias",b},{"mask",m},{"product",product},
                 {"accumulator",graph.idx(state.last_sum)}};
    std::array<int,6> ids={graph.idx(gate),graph.idx(bias_g),graph.idx(up),graph.idx(bias_u),
                           graph.idx(glu),down_index};
    std::sort(ids.begin(),ids.end());
    need(ids.front()>=0 && ids.back()==down_index &&
         std::adjacent_find(ids.begin(),ids.end())==ids.end(),"six distinct ordered nodes");
    std::array<ggml_op,6> ops{};
    bool contiguous=true,internal=true;
    json uses=json::array();
    for (size_t j=0;j<ids.size();++j) {
        const int i=ids[j];const auto *n=all[i];ops[j]=n->op;
        if (i!=ids.front()+int(j)) contiguous=false;
        std::vector<int> outside;
        for (int u:graph.users[n]) if (!std::binary_search(ids.begin(),ids.end(),u)) outside.push_back(u);
        if (i!=down_index && (!outside.empty() || (n->flags&GGML_TENSOR_FLAG_OUTPUT))) internal=false;
        uses.push_back({{"index",i},{"outside",outside},{"native_uses",ggml_node_get_use_count(graph.g,i)}});
    }
    const bool gate_ok=ggml_can_fuse_subgraph_ext(graph.g,ids.data(),ids.size(),ops.data(),&down_index,1);
    row["indices"]=ids;row["uses"]=uses;row["contiguous"]=contiguous;row["native_gate"]=gate_ok;
    row["no_internal_escape"]=internal;
    row["certified"]=contiguous && internal && gate_ok && graph.idx(physical)<ids.front() &&
                     down_index<b && b<product && std::find(ids.begin(),ids.end(),m)==ids.end();
    if (!row["certified"].get<bool>()) {
        row["reason"]=!contiguous?"interleaved node":!internal?"external consumer or output":
                      !gate_ok?"C269 ggml_can_fuse_subgraph_ext rejected":"retained edge order";
    }
}

static std::string provider(void *symbol) {
    Dl_info i{};
    need(symbol && dladdr(symbol,&i) && i.dli_fname,"unknown ELF provider");
    return std::filesystem::canonical(i.dli_fname).string();
}
static int emit(ggml_cgraph *g, const char *phase,void *caller) {
    try {
        Graph graph(g);
        json nodes=json::array(),rows=json::array();
        const auto signature=graph.describe(nodes);
        int mmids=0,nglu=0,certified=0,fully_examined=0;
        WaveState state;
        for (auto *p:graph.nodes) {
            if (p->op==GGML_OP_MUL_MAT_ID) ++mmids;
            if (p->op!=GGML_OP_GLU) continue;
            json row={{"wave",nglu},{"glu_index",graph.idx(p)},{"certified",false}};
            try { examine(graph,p,nglu,state,row); ++fully_examined; }
            catch (const std::runtime_error &e) { row["reason"]=e.what(); }
            if (row["certified"].get<bool>()) ++certified;
            rows.push_back(row);++nglu;
        }
        const bool identified=signature==expected_fingerprint && graph.nodes.size()==110 && mmids==24 && nglu==8;
        const char *structure=!identified || fully_examined!=8?"UNIDENTIFIED_GRAPH":certified==8?"CERTIFIED_ALL":"CUT_REJECTED";
        json report={{"status","PASS_SEAM_CAPTURE"},{"phase",phase},{"kernel_executed",false},
            {"graph_nodes",graph.nodes.size()},{"graph_mmid_nodes",mmids},{"graph_fingerprint",signature},
            {"certified_waves",certified},{"fully_examined_waves",fully_examined},{"structure",structure},{"nodes",nodes},{"rows",rows},
            {"caller",provider(caller)},{"cpu_provider",provider(dlsym(RTLD_NEXT,"ggml_graph_compute"))},
            {"base_provider",provider(reinterpret_cast<void *>(&ggml_graph_n_nodes))}};
        const char *path=std::getenv("TESY_FUSION_SEAM_JSON");
        need(path && path[0]=='/',"missing absolute capture destination");
        FILE *f=std::fopen(path,"wx");
        need(f!=nullptr,"exclusive capture destination");
        const auto body=report.dump(1)+"\n";
        const bool wrote=std::fwrite(body.data(),1,body.size(),f)==body.size();
        const bool closed=std::fclose(f)==0;
        need(wrote && closed,"capture write");
        return 0;
    } catch (const std::exception &e) {
        std::fprintf(stderr,"SEAM_CAPTURE_FAILED %s\n",e.what());return 1;
    }
}
} // namespace

extern "C" int tesy_parked_fusion_observe(ggml_cgraph *g) {
    return emit(g,"before_scheduler",__builtin_return_address(0));
}
extern "C" ggml_status ggml_graph_compute(ggml_cgraph *g,ggml_cplan *) {
    return emit(g,"cpu_graph_compute",__builtin_return_address(0))==0 ? GGML_STATUS_SUCCESS : GGML_STATUS_FAILED;
}
