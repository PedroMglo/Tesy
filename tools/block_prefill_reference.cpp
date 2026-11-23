// New block rows: independent resident logical-expert FFN on the same device.
// Only selected canonical slices are read; historical 36 references unchanged.
#define main tesy_original_layer_reference_main
#include "c7_layer_reference.cpp"
#undef main
#include "c210_direct_reader.h"
#include <set>

namespace {
void precheck_router(const std::string & phase, const std::vector<captured> & rows,
        ggml_backend_t backend, const std::array<ggml_tensor *, 8> & tensors) {
    const auto & input_row = one(rows, phase, "attn_post_norm");
    const auto & ids_row = one(rows, phase, "ffn_moe_topk");
    const auto & weights_row = one(rows, phase, "ffn_moe_weights_softmax");
    const size_t n = input_row.ne[1];
    const auto input = read_strided<float>(input_row, embd, n, input_row.nb[0], input_row.nb[1]);
    const auto expected_ids = read_strided<int32_t>(ids_row, topk, n, ids_row.nb[0], ids_row.nb[1]);
    const auto expected_weights = read_strided<float>(weights_row, topk, n, weights_row.nb[1], weights_row.nb[2]);
    owner graph; graph.ctx = context(16u*1024u*1024u);
    auto * c = graph.ctx;
    auto * inp = ggml_new_tensor_2d(c, GGML_TYPE_F32, embd, n);
    auto * logits = ggml_add(c, ggml_mul_mat(c, tensors[6], inp), tensors[7]);
    auto * ids = ggml_cont(c, ggml_argsort_top_k(c, logits, topk));
    auto * weights = ggml_get_rows(c, ggml_reshape_3d(c, logits, 1, experts, n), ids);
    weights = ggml_soft_max(c, ggml_reshape_2d(c, weights, topk, n));
    weights = ggml_cont(c, ggml_reshape_3d(c, weights, 1, topk, n));
    auto * gf = ggml_new_graph(c);
    ggml_build_forward_expand(gf, ids); ggml_build_forward_expand(gf, weights);
    graph.buffer = ggml_backend_alloc_ctx_tensors(c, backend);
    require(graph.buffer != nullptr, "router reference allocation failed");
    ggml_backend_tensor_set(inp, input.data(), 0, input.size()*sizeof(float));
    require(ggml_backend_graph_compute(backend, gf) == GGML_STATUS_SUCCESS, "router reference compute failed");
    ggml_backend_synchronize(backend);
    require(tensor_get<int32_t>(ids) == expected_ids, "independent router differs; do not consume unselected slices");
    const auto comp = compare(tensor_get<float>(weights), expected_weights);
    require(comp.bitwise && comp.nonfinite == 0, "independent routing weights differ");
}
} // namespace


#include "json.hpp"
using json = nlohmann::json;
namespace {
std::vector<captured> whole_rows(const std::filesystem::path & root,int layer) {
    std::ifstream f(root/"result.json");json v;f>>v;require(bool(f),"R2 capture receipt missing");
    require(v.at("status")=="COMPLETE_NATIVE_LAYER_REUSE_FIDELITY" && v.at("mode")=="r2-tile","independent reference source changed");
    std::vector<captured> out;
    for(const auto & r:v.at("stages"))if(r.at("layer")==layer){
        captured c{"warm153",layer,r.at("stage").get<std::string>(),{},{},{}};
        const auto ne=r.at("ne").get<std::vector<size_t>>();require(ne.size()==4,"shape rank changed");
        size_t size=4;for(int i=0;i<4;++i){c.ne[i]=ne[i];c.nb[i]=size;require(c.ne[i]>0&&c.ne[i]<=2880,"capture shape outside bounds");size*=c.ne[i];}
        const std::string name=c.name+"-"+std::to_string(layer)+".bin";require(r.at("file")==name,"capture file/namespace changed");c.path=root/name;
        require(std::filesystem::file_size(c.path)==size&&r.at("bytes")==size,"reference capture truncated");out.push_back(c);
    }
    require(out.size()==6,"complete layer six stages required");return out;
}
void canonical_tiles(const std::vector<captured> & rows,ggml_backend_t backend,const std::array<ggml_tensor*,8> & tensors){
    const auto & input_row=one(rows,"warm153","attn_post_norm");const size_t total=input_row.ne[1];
    const auto input=read_strided<float>(input_row,embd,total,input_row.nb[0],input_row.nb[1]);
    const auto & id_row=one(rows,"warm153","ffn_moe_topk");const auto ids=read_strided<int32_t>(id_row,topk,total,id_row.nb[0],id_row.nb[1]);
    const auto & mix_row=one(rows,"warm153","ffn_moe_weights_softmax");const auto weights=read_strided<float>(mix_row,topk,total,mix_row.nb[1],mix_row.nb[2]);
    const auto & out_row=one(rows,"warm153","ffn_moe_out");const auto expected=read_strided<float>(out_row,embd,total,out_row.nb[0],out_row.nb[1]);
    for(size_t first=0;first<total;first+=32){const size_t n=std::min<size_t>(32,total-first);owner graph;graph.ctx=context(16u*1024u*1024u);auto * c=graph.ctx;
        auto * inp=ggml_new_tensor_2d(c,GGML_TYPE_F32,embd,n);auto * route=ggml_new_tensor_2d(c,GGML_TYPE_I32,topk,n);auto * mix=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,topk,n);
        auto * inp3=ggml_reshape_3d(c,inp,embd,1,n);
        auto * up=ggml_add_id(c,ggml_mul_mat_id(c,tensors[1],inp3,route),tensors[4],route);
        auto * gate=ggml_add_id(c,ggml_mul_mat_id(c,tensors[0],inp3,route),tensors[3],route);
        auto * act=ggml_swiglu_oai(c,gate,up,1.702f,7.0f);
        auto * down=ggml_add_id(c,ggml_mul_mat_id(c,tensors[2],act,route),tensors[5],route);down=ggml_mul(c,down,mix);
        ggml_tensor * sum=nullptr;for(int k=0;k<topk;++k){auto * x=ggml_view_2d(c,down,embd,n,down->nb[2],k*down->nb[1]);sum=sum?ggml_add(c,sum,x):x;}
        auto * output=ggml_cont(c,sum);auto * gf=ggml_new_graph(c);ggml_build_forward_expand(gf,output);graph.buffer=ggml_backend_alloc_ctx_tensors(c,backend);require(graph.buffer,"native reference allocation failed");
        ggml_backend_tensor_set(inp,input.data()+first*embd,0,n*embd*4);ggml_backend_tensor_set(route,ids.data()+first*topk,0,n*topk*4);ggml_backend_tensor_set(mix,weights.data()+first*topk,0,n*topk*4);
        require(ggml_backend_graph_compute(backend,gf)==GGML_STATUS_SUCCESS,"native canonical FFN failed");ggml_backend_synchronize(backend);
        const std::vector<float> gold(expected.begin()+first*embd,expected.begin()+(first+n)*embd);const auto result=compare(tensor_get<float>(output),gold);
        std::cout<<"CANONICAL_R2_TILE first="<<first<<" n="<<n<<" bitwise="<<result.bitwise<<" nonfinite="<<result.nonfinite<<" max_abs="<<result.max_abs<<'\n'<<std::flush;
        require(result.bitwise&&!result.nonfinite,"canonical same-device tile FFN differs");
    }
}
}
int main(int argc, char ** argv) {
    if (argc != 5) {
        std::cerr << "usage: block_prefill_reference MODEL R2_TILE_CAPTURE LAYER DEVICE\n";
        return 2;
    }
    try {
        const std::string model = argv[1], device = argv[4], phase = "warm153";
        const int layer = std::stoi(argv[3]);
        require((layer == 0 && device == "cpu") || ((layer == 25 || layer == 35) && device == "cuda"),
                "unfrozen reference device/layer");
        const auto rows = whole_rows(std::filesystem::path(argv[2]), layer);
        const auto & input = one(rows, phase, "attn_post_norm");
        require(input.ne[0] == embd && input.ne[1] == static_cast<size_t>(layer==35?1:153), "reference input shape changed");
        const auto & ids_row = one(rows, phase, "ffn_moe_topk");
        const auto ids = read_strided<int32_t>(ids_row, topk, input.ne[1], ids_row.nb[0], ids_row.nb[1]);
        std::set<int32_t> selected(ids.begin(), ids.end());
        for (int32_t id : selected) require(id >= 0 && id < experts, "invalid canonical selected ID");
        ggml_backend_load_all();
        auto * dev = ggml_backend_dev_by_type(device == "cpu" ? GGML_BACKEND_DEVICE_TYPE_CPU : GGML_BACKEND_DEVICE_TYPE_GPU);
        require(dev != nullptr, "reference backend unavailable");
        backend_owner backend{ggml_backend_dev_init(dev, nullptr)};
        require(backend.value != nullptr, "reference backend init failed");
        if (device == "cpu") ggml_backend_cpu_set_n_threads(backend.value, 8);
        owner storage; storage.ctx = context(8u*1024u*1024u);
        auto * c = storage.ctx;
        std::array<ggml_tensor *, 8> tensors{
            ggml_new_tensor_3d(c, GGML_TYPE_MXFP4, embd, embd, experts),
            ggml_new_tensor_3d(c, GGML_TYPE_MXFP4, embd, embd, experts),
            ggml_new_tensor_3d(c, GGML_TYPE_MXFP4, embd, embd, experts),
            ggml_new_tensor_2d(c, GGML_TYPE_F32, embd, experts),
            ggml_new_tensor_2d(c, GGML_TYPE_F32, embd, experts),
            ggml_new_tensor_2d(c, GGML_TYPE_F32, embd, experts),
            ggml_new_tensor_2d(c, GGML_TYPE_F32, embd, experts),
            ggml_new_tensor_1d(c, GGML_TYPE_F32, experts)};
        ggml_context * meta = nullptr;
        gguf_init_params params{true, &meta};
        gguf_context * gguf = gguf_init_from_file(model.c_str(), params);
        require(gguf && meta && ggml_used_mem(meta) <= 64u*1024u*1024u, "canonical metadata invalid/too large");
        const std::string base = "blk." + std::to_string(layer) + ".";
        std::array<spec, 8> specs{
            get_spec(gguf,meta,tensors[0],base+"ffn_gate_exps.weight",GGML_TYPE_MXFP4,{embd,embd,experts}),
            get_spec(gguf,meta,tensors[1],base+"ffn_up_exps.weight",GGML_TYPE_MXFP4,{embd,embd,experts}),
            get_spec(gguf,meta,tensors[2],base+"ffn_down_exps.weight",GGML_TYPE_MXFP4,{embd,embd,experts}),
            get_spec(gguf,meta,tensors[3],base+"ffn_gate_exps.bias",GGML_TYPE_F32,{embd,experts}),
            get_spec(gguf,meta,tensors[4],base+"ffn_up_exps.bias",GGML_TYPE_F32,{embd,experts}),
            get_spec(gguf,meta,tensors[5],base+"ffn_down_exps.bias",GGML_TYPE_F32,{embd,experts}),
            get_spec(gguf,meta,tensors[6],base+"ffn_gate_inp.weight",GGML_TYPE_F32,{embd,experts}),
            get_spec(gguf,meta,tensors[7],base+"ffn_gate_inp.bias",GGML_TYPE_F32,{experts})};
        ggml_free(meta); gguf_free(gguf);
        storage.buffer = ggml_backend_alloc_ctx_tensors_from_buft(c, ggml_backend_dev_buffer_type(dev));
        require(storage.buffer != nullptr, "canonical storage allocation failed");
        tesy_witness::direct_reader reader; reader.open_file(model.c_str());
        size_t logical_bytes = 0;
        for (size_t kind = 0; kind < specs.size(); ++kind) {
            const auto & item = specs[kind]; reader.validate_range(item.offset, item.bytes);
            const size_t slice = kind < 6 ? item.bytes/experts : item.bytes;
            require(slice <= 4406400u, "canonical scratch exceeds bounded slice");
            if (kind < 6) require(slice == (kind < 3 ? 4406400u : 11520u), "canonical slice encoding changed");
            std::vector<uint8_t> payload(slice);
            if (kind < 6) {
                for (int32_t expert : selected) {
                    const size_t offset = static_cast<size_t>(expert)*slice;
                    reader.read(payload.data(), payload.size(), item.offset+offset);
                    ggml_backend_tensor_set(item.tensor, payload.data(), offset, payload.size());
                    logical_bytes += payload.size();
                }
            } else {
                reader.read(payload.data(), payload.size(), item.offset);
                ggml_backend_tensor_set(item.tensor, payload.data(), 0, payload.size());
                logical_bytes += payload.size();
            }
        }
        ggml_backend_synchronize(backend.value);
        // Before any FFN consumer, prove native canonical routing only touches
        // precisely the slices loaded from the original logical namespace.
        precheck_router(phase, rows, backend.value, tensors);
        canonical_tiles(rows,backend.value,tensors);
        std::cout<<"PASS_NATIVE_CANONICAL_R2_LAYER layer="<<layer<<" device="<<device<<" logical_bytes_read="<<logical_bytes<<" O_DIRECT=1\n"<<std::flush;
        return 0;
    } catch (const std::exception & exc) {
        std::cerr << "BLOCK_REFERENCE_FAIL: " << exc.what() << "\n";
        return 1;
    }
}
