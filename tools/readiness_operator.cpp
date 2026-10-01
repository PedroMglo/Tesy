// Isolated original CPU FFN. Only selected canonical expert slices, no Transformer/token generation.
// Reuses canonical capture/metadata/comparison helpers; original reference source remains unchanged.
#define main historical_c7_reference_main
#include "c7_layer_reference.cpp"
#undef main
#include "c210_direct_reader.h"
#include <chrono>

namespace {
using clock_type = std::chrono::steady_clock;
double us(clock_type::time_point a, clock_type::time_point b) {
    return std::chrono::duration<double,std::micro>(b-a).count();
}
struct selected_storage {
    std::array<ggml_tensor*,6> pool{};
    std::array<spec,6> canonical{};
    std::array<int32_t,4> ids{}, slots{};
    tesy_witness::direct_reader * reader=nullptr;
};
void load_selected(selected_storage & s) {
    for (int component=0;component<6;++component) {
        const auto & meta=s.canonical[component];
        const size_t slice=meta.bytes/experts;
        require(slice==(component<3?4406400u:11520u),"selected slice bytes");
        std::vector<uint8_t> raw(slice), back(slice);
        for (int k=0;k<4;++k) {
            s.reader->read(raw.data(),slice,meta.offset+static_cast<uint64_t>(s.ids[k])*slice);
            const size_t target=component<3?static_cast<size_t>(s.slots[k]):static_cast<size_t>(s.ids[k]);
            ggml_backend_tensor_set(s.pool[component],raw.data(),target*slice,slice);
            ggml_backend_tensor_get(s.pool[component],back.data(),target*slice,slice);
            require(raw==back,"canonical bytes differ at CPU consumer buffer");
        }
    }
}
void run_case(ggml_backend_t backend, selected_storage & storage,
              const std::vector<captured> & rows, const std::string & phase, int layer, int slots) {
    const auto & a=one(rows,phase,"attn_post_norm");
    const auto & i=one(rows,phase,"ffn_moe_topk");
    const auto & si=one(rows,phase,"ffn_moe_topk_stream");
    const auto & w=one(rows,phase,"ffn_moe_weights_softmax");
    const auto & o=one(rows,phase,"ffn_moe_out");
    require(a.ne[0]==embd && a.ne[1]==1 && i.ne[0]==4 && i.ne[1]==1 && si.ne[0]==4 && si.ne[1]==1,"frozen decode shape");
    auto input=read_strided<float>(a,embd,1,a.nb[0],a.nb[1]);
    auto logical=read_strided<int32_t>(i,4,1,i.nb[0],i.nb[1]);
    auto physical=read_strided<int32_t>(si,4,1,si.nb[0],si.nb[1]);
    auto mix=read_strided<float>(w,4,1,w.nb[1],w.nb[2]);
    auto expected=read_strided<float>(o,embd,1,o.nb[0],o.nb[1]);
    for(int k=0;k<4;k++) {
        require(logical[k]>=0 && logical[k]<128 && physical[k]>=0 && physical[k]<slots,"expert/slot range");
        for(int j=0;j<k;j++)require(logical[k]!=logical[j] && physical[k]!=physical[j],"duplicate authoritative expert/slot");
        storage.ids[k]=logical[k];storage.slots[k]=physical[k];
    }
    load_selected(storage);
    owner graph;graph.ctx=context(16u*1024u*1024u);auto*c=graph.ctx;
    auto*inp=ggml_new_tensor_2d(c,GGML_TYPE_F32,embd,1);
    auto*ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,1);
    auto*pids=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,1);
    auto*weights=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,4,1);
    auto*inp3=ggml_reshape_3d(c,inp,embd,1,1);
    auto*up_mm=ggml_mul_mat_id(c,storage.pool[1],inp3,pids);ggml_set_name(up_mm,"up_MMID");
    auto*up=ggml_add_id(c,up_mm,storage.pool[4],ids);
    auto*gate_mm=ggml_mul_mat_id(c,storage.pool[0],inp3,pids);ggml_set_name(gate_mm,"gate_MMID");
    auto*gate=ggml_add_id(c,gate_mm,storage.pool[3],ids);
    auto*act=ggml_swiglu_oai(c,gate,up,1.702f,7.0f);
    auto*down_mm=ggml_mul_mat_id(c,storage.pool[2],act,pids);ggml_set_name(down_mm,"down_MMID");
    auto*down=down_mm;
    down=ggml_add_id(c,down,storage.pool[5],ids);down=ggml_mul(c,down,weights);
    ggml_tensor*sum=nullptr;
    for(int k=0;k<4;k++){auto*v=ggml_view_2d(c,down,embd,1,down->nb[2],k*down->nb[1]);sum=sum?ggml_add(c,sum,v):v;}
    auto*output=ggml_cont(c,sum);ggml_set_output(output);ggml_set_output(gate_mm);
    auto*full=ggml_new_graph(c);ggml_build_forward_expand(full,output);
    std::vector<ggml_tensor*> mmids;
    for(int k=0;k<ggml_graph_n_nodes(full);k++)if(ggml_graph_node(full,k)->op==GGML_OP_MUL_MAT_ID)mmids.push_back(ggml_graph_node(full,k));
    require(mmids==std::vector<ggml_tensor*>{gate_mm,up_mm,down_mm},"native graph order differs from gate/up/down");
    auto*first=ggml_new_graph(c);ggml_build_forward_expand(first,gate_mm);
    graph.buffer=ggml_backend_alloc_ctx_tensors(c,backend);require(graph.buffer,"operator graph allocation");
    ggml_backend_tensor_set(inp,input.data(),0,input.size()*4);
    ggml_backend_tensor_set(ids,logical.data(),0,16);ggml_backend_tensor_set(pids,physical.data(),0,16);
    ggml_backend_tensor_set(weights,mix.data(),0,16);
    auto compute=[&](ggml_cgraph*g){auto begin=clock_type::now();require(ggml_backend_graph_compute(backend,g)==GGML_STATUS_SUCCESS,"operator compute");ggml_backend_synchronize(backend);return us(begin,clock_type::now());};
    compute(full);
    auto cmp=compare(tensor_get<float>(output),expected);require(cmp.bitwise && !cmp.nonfinite,"FFN differs from original selected C127 reference");
    auto gate_expected=tensor_get<float>(gate_mm);
    for(const std::string condition:{"resident-hot","direct-reload-selected"}) {
        for(int rep=0;rep<6;rep++) {
            const auto r0=clock_type::now();if(condition=="direct-reload-selected")load_selected(storage);const auto r1=clock_type::now();
            double first_time=0,full_time=0;
            if(rep%2==0){first_time=compute(first);require(compare(tensor_get<float>(gate_mm),gate_expected).bitwise,"first MMID mismatch");full_time=compute(full);}
            else{full_time=compute(full);first_time=compute(first);require(compare(tensor_get<float>(gate_mm),gate_expected).bitwise,"first MMID mismatch");}
            require(compare(tensor_get<float>(output),expected).bitwise,"repeated FFN mismatch");
            std::cout<<std::setprecision(12)<<"{\"layer\":"<<layer<<",\"slots\":"<<slots<<",\"phase\":\""<<phase<<"\",\"condition\":\""<<condition<<"\",\"rep\":"<<rep<<",\"first_MMID\":\"gate\",\"first_us\":"<<first_time<<",\"full_ffn_us\":"<<full_time<<",\"reload_and_verify_us\":"<<us(r0,r1)<<",\"bitwise\":true,\"finite\":true}\n"<<std::flush;
        }
    }
}
}

int main(int argc,char**argv){try {
    if(argc==2 && std::string(argv[1])=="--self-test") {
        backend_owner backend{ggml_backend_cpu_init()};require(backend.value,"CPU fixture backend");ggml_backend_cpu_set_n_threads(backend.value,8);
        owner g;g.ctx=context(16u*1024u*1024u);auto*c=g.ctx;
        auto*w=ggml_new_tensor_3d(c,GGML_TYPE_F32,32,16,4);auto*x=ggml_new_tensor_3d(c,GGML_TYPE_F32,32,1,1);auto*ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,1);
        auto*up=ggml_mul_mat_id(c,w,x,ids);ggml_set_name(up,"up");auto*gate=ggml_mul_mat_id(c,w,x,ids);ggml_set_name(gate,"gate");
        auto*act=ggml_swiglu_oai(c,gate,up,1.702f,7.0f);auto*graph=ggml_new_graph(c);ggml_build_forward_expand(graph,act);
        std::vector<std::string> order;for(int i=0;i<ggml_graph_n_nodes(graph);i++)if(ggml_graph_node(graph,i)->op==GGML_OP_MUL_MAT_ID)order.push_back(ggml_graph_node(graph,i)->name);
        require(order==std::vector<std::string>{"gate","up"},"actual graph visits gate before constructed-first up");
        ggml_set_output(gate);ggml_set_output(up);g.buffer=ggml_backend_alloc_ctx_tensors(c,backend.value);require(g.buffer,"fixture allocation");
        std::vector<float> weights(32*16*4),inputs(32,1);for(int e=0;e<4;e++)std::fill(weights.begin()+e*32*16,weights.begin()+(e+1)*32*16,float(e+1));
        const std::array<int32_t,4> expert_ids{3,0,2,1};ggml_backend_tensor_set(w,weights.data(),0,weights.size()*4);ggml_backend_tensor_set(x,inputs.data(),0,inputs.size()*4);ggml_backend_tensor_set(ids,expert_ids.data(),0,16);
        require(ggml_backend_graph_compute(backend.value,graph)==GGML_STATUS_SUCCESS,"fixture graph compute");auto result=tensor_get<float>(gate);
        for(int k=0;k<4;k++)for(int row=0;row<16;row++)require(result[k*16+row]==32*(expert_ids[k]+1),"independent known-small dot result");
        std::cout<<"{\"status\":\"PASS_MODEL_FREE_OPERATOR_AND_GRAPH_ORDER\",\"actual_order\":[\"gate\",\"up\"],\"threads\":8,\"model_weights_loaded\":false}\n";return 0;
    }
    require(argc==4,"usage: readiness_operator MODEL CAPTURE LAYER (0/12/24)");
    const int layer=std::stoi(argv[3]);require(layer==0||layer==12||layer==24,"frozen three CPU layers");
    const auto rows=index(std::filesystem::path(argv[2]),layer);
    ggml_context*meta=nullptr;gguf_init_params params{true,&meta};auto*gguf=gguf_init_from_file(argv[1],params);
    require(gguf && meta,"metadata-only GGUF init");
    tesy_witness::direct_reader reader;reader.open_file(argv[1]);
    std::cerr<<"READER_DIRECT_READY mem_align="<<reader.memory_alignment()<<" off_align="<<reader.offset_alignment()<<"\n";
    backend_owner backend{ggml_backend_cpu_init()};require(backend.value,"CPU backend init");ggml_backend_cpu_set_n_threads(backend.value,8);
    const std::array<std::string,6> names{"gate_exps.weight","up_exps.weight","down_exps.weight","gate_exps.bias","up_exps.bias","down_exps.bias"};
    for(int slots:{40,44}) {
        owner store;store.ctx=context(8u*1024u*1024u);selected_storage storage;storage.reader=&reader;
        for(int k=0;k<6;k++) {
            const bool weight=k<3;
            storage.pool[k]=weight?ggml_new_tensor_3d(store.ctx,GGML_TYPE_MXFP4,embd,embd,slots):ggml_new_tensor_2d(store.ctx,GGML_TYPE_F32,embd,experts);
            const auto name="blk."+std::to_string(layer)+".ffn_"+names[k];
            auto*source=ggml_get_tensor(meta,name.c_str());require(source,"canonical metadata tensor missing");
            storage.canonical[k]=get_spec(gguf,meta,source,name,weight?GGML_TYPE_MXFP4:GGML_TYPE_F32,weight?std::vector<int64_t>{embd,embd,experts}:std::vector<int64_t>{embd,experts});
            reader.validate_range(storage.canonical[k].offset,storage.canonical[k].bytes);
        }
        store.buffer=ggml_backend_alloc_ctx_tensors(store.ctx,backend.value);require(store.buffer,"selected pool allocation");
        // Only four selected expert slices are populated per phase. Other slots are not demanded.
        for(const std::string phase:{"decode0","decode1","decode7","decode31"})run_case(backend.value,storage,rows,phase,layer,slots);
    }
    ggml_free(meta);gguf_free(gguf);return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
