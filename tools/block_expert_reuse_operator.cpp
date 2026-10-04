// Isolated CPU layer: native C75 demand/preload waves shared across selected
// numerical tiles. No Transformer rewrite, global cache or future routing.
#define main historical_layer_reference_main
#include "c7_layer_reference.cpp"
#undef main
#include "llama-moe-stream.h"
#include "c210_direct_reader.h"
#include "json.hpp"
#include <chrono>
#include <mutex>
#include <set>
using reuse_json=nlohmann::ordered_json;
namespace {
struct tile {
    std::string phase;
    int n=0;
    std::vector<float> input,mix,expected;
    std::vector<int32_t> ids;
};
struct witness_state {
    tesy_witness::direct_reader * reader=nullptr;
    std::array<spec,6> specs{};
    std::array<ggml_tensor*,6> tensors{};
    uint64_t combinations=0;
    bool enabled=false;
};
static witness_state * active_witness=nullptr;
void consuming_wave(ggml_tensor * dst,int ith,int nth,void * opaque) {
    llama_moe_stream_wave_ids(dst,ith,nth,opaque);
    if(ith!=0||!active_witness||!active_witness->enabled)return;
    auto & s=*active_witness;auto * ud=static_cast<llama_moe_stream_wave*>(opaque);auto * sl=ud->sl;
    auto * logical=static_cast<const int32_t*>(dst->src[0]->data);
    auto * physical=static_cast<const int32_t*>(dst->data);
    std::lock_guard<std::mutex> lock(sl->mgr->mtx);
    std::set<int32_t> seen;
    for(int64_t p=0;p<ggml_nelements(dst);++p) {
        const int e=logical[p],slot=physical[p];
        if(sl->expert_wave[e]!=ud->wave){require(slot==-1,"parked CPU pair must carry C47 sentinel");continue;}
        require(slot>=0&&slot<static_cast<int>(sl->n_slots)&&sl->keep[slot]&&sl->slot_expert[slot]==e&&
                sl->slot_state[slot]==LLAMA_MOE_STREAM_SLOT_RESIDENT&&sl->slot_gen[slot]>0&&!sl->slot_claimed[slot],"expert/slot/generation/lifetime invalid before tile consumption");
        if(!seen.insert(e).second)continue;
        for(int k=0;k<6;++k) {
            const size_t bytes=s.specs[k].bytes/128;require(bytes==(k<3?4406400u:11520u),"canonical component byte shape changed");
            std::vector<uint8_t> a(bytes),b(bytes);
            s.reader->read(a.data(),bytes,s.specs[k].offset+static_cast<uint64_t>(e)*bytes);
            ggml_backend_tensor_get(s.tensors[k],b.data(),static_cast<size_t>(k<3?slot:e)*bytes,bytes);
            require(a==b,"native loaded byte differs at consumer boundary");
        }
        ++s.combinations;
    }
}
struct graph_plan {
    owner mem;
    ggml_cgraph * graph=nullptr;
    std::vector<ggml_tensor*> outputs;
    std::vector<std::pair<ggml_tensor*,std::vector<uint8_t>>> values;
    std::vector<int> group_tokens,wave_counts;
};
template<typename T> void put(graph_plan & g,ggml_tensor * t,const std::vector<T> & v) {
    require(ggml_nbytes(t)==v.size()*sizeof(T),"input tensor bytes/shape mismatch");
    std::vector<uint8_t> b(v.size()*sizeof(T));std::memcpy(b.data(),v.data(),b.size());g.values.push_back({t,std::move(b)});
}
ggml_tensor * pairs(ggml_context * c,const std::array<ggml_tensor*,6> & t,ggml_tensor * inp,ggml_tensor * logical,ggml_tensor * physical) {
    auto * in3=ggml_reshape_3d(c,inp,inp->ne[0],1,inp->ne[1]);
    auto * up=ggml_mul_mat_id(c,t[1],in3,physical);up=ggml_add_id(c,up,t[4],logical);
    auto * gate=ggml_mul_mat_id(c,t[0],in3,physical);gate=ggml_add_id(c,gate,t[3],logical);
    auto * act=ggml_swiglu_oai(c,gate,up,1.702f,7.0f);
    auto * down=ggml_mul_mat_id(c,t[2],act,physical);return ggml_add_id(c,down,t[5],logical);
}
ggml_tensor * finish(ggml_context * c,ggml_cgraph * graph,ggml_tensor * expert_pairs,ggml_tensor * weights) {
    auto * weighted=ggml_mul(c,expert_pairs,weights);ggml_build_forward_expand(graph,weighted);
    ggml_tensor * sum=nullptr;
    for(int k=0;k<4;++k){auto * v=ggml_view_2d(c,weighted,weighted->ne[0],weighted->ne[2],weighted->nb[2],k*weighted->nb[1]);
        ggml_build_forward_expand(graph,v);sum=sum?ggml_add(c,sum,v):v;ggml_build_forward_expand(graph,sum);}
    ggml_set_output(sum);return sum;
}
void build(graph_plan & g,ggml_backend_t backend,llama_moe_stream_layer * sl,const std::array<ggml_tensor*,6> & tensors,
           const std::vector<tile> & tiles,bool reuse) {
    g.mem.ctx=context(32u*1024u*1024u);auto * c=g.mem.ctx;g.graph=ggml_new_graph_custom(c,8192,false);
    std::vector<ggml_tensor*> inputs,ids,mix;
    for(const auto & tile:tiles){auto * x=ggml_new_tensor_2d(c,GGML_TYPE_F32,tensors[0]->ne[0],tile.n);
        auto * i=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,tile.n);auto * m=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,4,tile.n);
        inputs.push_back(x);ids.push_back(i);mix.push_back(m);put(g,x,tile.input);put(g,i,tile.ids);put(g,m,tile.mix);}
    ggml_tensor * previous_group=nullptr;
    const int capacity=(sl->n_slots-4)/2;require(capacity>=4,"wave capacity invalid");
    const int groups=reuse?1:static_cast<int>(tiles.size());
    for(int group=0;group<groups;++group){
        const int first=reuse?0:group,last=reuse?static_cast<int>(tiles.size()):group+1;
        auto * logical=ids[first];int tokens=tiles[first].n;
        for(int k=first+1;k<last;++k){logical=ggml_concat(c,logical,ids[k],1);tokens+=tiles[k].n;}
        logical=ggml_cont(c,logical);const int waves=(std::min<int>(sl->n_expert,4*tokens)+capacity-1)/capacity;
        g.group_tokens.push_back(tokens);g.wave_counts.push_back(waves);
        std::vector<ggml_tensor*> sums(last-first,nullptr);ggml_tensor * previous=previous_group;
        for(int w=0;w<waves;++w){
            ggml_tensor * args[2]={logical,previous};const int count=previous?2:1;
            auto * physical=ggml_custom_4d(c,GGML_TYPE_I32,4,tokens,1,1,args,count,consuming_wave,1,sl->wave_userdata(w,capacity));
            ggml_set_name(physical,("reuse-slot-group-"+std::to_string(group)+"-wave-"+std::to_string(w)).c_str());
            ggml_tensor * masks[2]={logical,physical};auto * mask=ggml_custom_4d(c,GGML_TYPE_F32,1,4,tokens,1,masks,2,llama_moe_stream_wave_mask,1,sl->wave_userdata(w,capacity));
            int offset=0;ggml_tensor * dependency=nullptr;
            for(int k=first;k<last;++k){const int n=tiles[k].n;
                auto * pi=ggml_view_2d(c,physical,4,n,physical->nb[1],offset*physical->nb[1]);
                auto * ma=ggml_view_3d(c,mask,1,4,n,mask->nb[1],mask->nb[2],offset*mask->nb[2]);
                auto * value=ggml_mul(c,pairs(c,tensors,inputs[k],ids[k],pi),ma);
                auto & sum=sums[k-first];sum=sum?ggml_add(c,sum,value):value;
                ggml_set_name(sum,("reuse-consumed-tile-"+std::to_string(k)+"-wave-"+std::to_string(w)).c_str());
                ggml_build_forward_expand(g.graph,sum);
                // Every original numerical tile must finish consuming the
                // resident group before a later wave may reuse its slots.
                auto * scalar=ggml_view_1d(c,sum,1,0);dependency=dependency?ggml_concat(c,dependency,scalar,0):scalar;
                offset+=n;
            }
            previous=dependency;
        }
        for(int k=first;k<last;++k)g.outputs.push_back(finish(c,g.graph,sums[k-first],mix[k]));
        previous_group=ggml_view_1d(c,g.outputs.back(),1,0);
    }
    g.mem.buffer=ggml_backend_alloc_ctx_tensors(c,backend);require(g.mem.buffer,"reuse graph allocation failed");
    for(const auto & value:g.values)ggml_backend_tensor_set(value.first,value.second.data(),0,value.second.size());
}
void validate(const std::vector<tile> & tiles) {
    require(tiles.size()==3,"exactly three selected tiles required");
    for(const auto & t:tiles){require(t.n>0&&t.n<=32&&t.ids.size()==static_cast<size_t>(4*t.n),"tile shape/ID cardinality invalid");
        for(int n=0;n<t.n;++n){std::set<int> unique;for(int k=0;k<4;++k){int e=t.ids[4*n+k];require(e>=0&&e<128&&unique.insert(e).second,"wrong/duplicate routed expert pair");}}
        require(t.mix.size()==t.ids.size()&&t.input.size()==static_cast<size_t>(embd*t.n)&&t.expected.size()==t.input.size(),"tile activation/mix/output cardinality invalid");
    }
}
reuse_json state(llama_moe_stream & mgr,int layer) {
    std::unique_lock<std::mutex> lock(mgr.mtx);auto * sl=mgr.layer(layer);
    const auto ready=[&]{if(!mgr.q_demand.empty())return false;for(size_t k=0;k<sl->n_slots;++k)if(sl->slot_claimed[k]||sl->slot_state[k]==LLAMA_MOE_STREAM_SLOT_LOADING)return false;return true;};
    require(mgr.cv_done.wait_for(lock,std::chrono::seconds(5),ready)&&!mgr.load_failed,"native workers did not drain/error");
    return {{"slot_expert",sl->slot_expert},{"slot_state",sl->slot_state},{"slot_generation",sl->slot_gen},
        {"demand_loads",mgr.stats.n_miss},{"preload_loads",mgr.stats.n_preload_issued},{"waves",mgr.stats.n_waves_run},
        {"wait_union_us",mgr.stats.t_stall_wave_us},{"logical_bytes_per_load",13219200},{"cache_bytes",mgr.size_bufs()}};
}
}
namespace {
void ancestors(ggml_tensor * t,std::set<ggml_tensor*> & visited,std::set<std::string> & names) {
    if(!t||!visited.insert(t).second)return;
    names.insert(ggml_get_name(t));for(auto * src:t->src)ancestors(src,visited,names);
}
bool complete_dependency(ggml_tensor * node) {
    std::set<ggml_tensor*> visited;std::set<std::string> names;ancestors(node->src[1],visited,names);
    for(int tile=0;tile<3;++tile)if(!names.count("reuse-consumed-tile-"+std::to_string(tile)+"-wave-0"))return false;
    return true;
}
void graph_self_test() {
    backend_owner backend{ggml_backend_cpu_init()};require(backend.value,"graph fixture CPU backend unavailable");
    owner metadata;metadata.ctx=context(8u*1024u*1024u);
    llama_moe_stream mgr(36,12,4,true);std::array<ggml_tensor*,6> t{};
    for(int k=0;k<3;++k){auto * m=ggml_new_tensor_3d(metadata.ctx,GGML_TYPE_F32,k==2?16:32,k==2?32:16,16);
        t[k]=mgr.create_cache_tensor(0,ggml_backend_cpu_buffer_type(),m,0,0);}
    for(int k=3;k<6;++k)t[k]=ggml_new_tensor_2d(metadata.ctx,GGML_TYPE_F32,k==5?32:16,16);
    mgr.alloc_bufs(false);metadata.buffer=ggml_backend_alloc_ctx_tensors(metadata.ctx,backend.value);
    std::vector<tile> tiles;
    for(int i=0;i<3;++i){tile value;value.n=2;value.input.assign(64,1);value.mix.assign(8,.25f);value.ids={0,1,2,3,4,5,6,7};tiles.push_back(value);}
    graph_plan g;build(g,backend.value,mgr.layer(0),t,tiles,true);
    require(g.group_tokens==std::vector<int>{6}&&g.wave_counts==std::vector<int>{4},"single union group shape invalid");
    ggml_tensor * next=nullptr,*only_first=nullptr;
    for(int i=0;i<ggml_graph_n_nodes(g.graph);++i){auto * node=ggml_graph_node(g.graph,i);const std::string name=ggml_get_name(node);
        if(name=="reuse-slot-group-0-wave-1")next=node;
        if(name=="reuse-consumed-tile-0-wave-0")only_first=node;}
    require(next&&only_first&&complete_dependency(next),"next wave not dependent on all three tile consumers");
    auto * full=next->src[1];next->src[1]=only_first;require(!complete_dependency(next),"omitted tile consumption was not detected");next->src[1]=full;
    graph_plan control;build(control,backend.value,mgr.layer(0),t,tiles,false);
    require(control.group_tokens==std::vector<int>({2,2,2})&&control.wave_counts==std::vector<int>({2,2,2}),"original tile groups not conserved");
    std::cout<<"{\"status\":\"PASS_MODEL_FREE_ALL_TILE_DEPENDENCY_COUNTERPROOF\",\"weights_loaded\":false,\"operator_compute\":false,\"native_io_executed\":false}\n";
}
}
int main(int argc,char ** argv) {try {
    if(argc==2&&std::string(argv[1])=="--graph-self-test"){graph_self_test();return 0;}

    require(argc==6,"usage: block_expert_reuse MODEL CAPTURE LAYER MODE(numeric-A|numeric-B|timing-A|timing-B) RESULT");
    require(!std::filesystem::exists(argv[5]),"reuse output already exists");
    const int layer=std::stoi(argv[3]);const std::string mode=argv[4];require(layer==0||layer==12||layer==24,"frozen CPU layer selection");
    require(mode=="numeric-A"||mode=="numeric-B"||mode=="timing-A"||mode=="timing-B","invalid reuse mode");
    require(getenv("TESY_CPU_WAVE_SKIP_PARKED")&&std::string(getenv("TESY_CPU_WAVE_SKIP_PARKED"))=="1"&&!getenv("GOMP_SPINCOUNT"),"unfrozen native skip/wait environment");
    const auto rows=index(std::filesystem::path(argv[2]),layer);std::vector<tile> tiles;
    for(const std::string phase:{"prefill0","prefill128","prefill_final"}){
        const auto & a=one(rows,phase,"attn_post_norm"),&i=one(rows,phase,"ffn_moe_topk"),&w=one(rows,phase,"ffn_moe_weights_softmax"),&o=one(rows,phase,"ffn_moe_out");
        require(a.ne[0]==embd&&i.ne[0]==4&&o.ne[0]==embd&&a.ne[1]==o.ne[1],"selected tile shape mismatch");tile t;t.phase=phase;t.n=static_cast<int>(a.ne[1]);
        t.input=read_strided<float>(a,embd,t.n,a.nb[0],a.nb[1]);t.ids=read_strided<int32_t>(i,4,t.n,i.nb[0],i.nb[1]);
        t.mix=read_strided<float>(w,4,t.n,w.nb[1],w.nb[2]);t.expected=read_strided<float>(o,embd,t.n,o.nb[0],o.nb[1]);tiles.push_back(std::move(t));
    }
    validate(tiles);require(tiles[0].n==32&&tiles[1].n==32&&tiles[2].n==29,"original disjoint selected tile sizes changed");
    ggml_context * meta=nullptr;gguf_init_params params{true,&meta};auto * gguf=gguf_init_from_file(argv[1],params);require(meta&&gguf,"GGUF metadata unavailable");
    tesy_witness::direct_reader reader;reader.open_file(argv[1]);
    backend_owner backend{ggml_backend_cpu_init()};require(backend.value,"CPU backend unavailable");ggml_backend_cpu_set_n_threads(backend.value,8);
    llama_moe_stream mgr(36,40,4,true);owner biases;biases.ctx=context(8u*1024u*1024u);witness_state witness;witness.reader=&reader;
    const std::array<std::string,6> names{"gate_exps.weight","up_exps.weight","down_exps.weight","gate_exps.bias","up_exps.bias","down_exps.bias"};
    for(int k=0;k<6;++k){const auto name="blk."+std::to_string(layer)+".ffn_"+names[k];auto * src=ggml_get_tensor(meta,name.c_str());require(src,"canonical component metadata missing");
        witness.specs[k]=get_spec(gguf,meta,src,name,k<3?GGML_TYPE_MXFP4:GGML_TYPE_F32,k<3?std::vector<int64_t>{embd,embd,128}:std::vector<int64_t>{embd,128});reader.validate_range(witness.specs[k].offset,witness.specs[k].bytes);
        if(k>=3)witness.tensors[k]=ggml_new_tensor_2d(biases.ctx,GGML_TYPE_F32,embd,128);
    }
    // Original openai-moe model creation order is gate, down, up.
    for(int k:{0,2,1})witness.tensors[k]=mgr.create_cache_tensor(layer,ggml_backend_cpu_buffer_type(),witness.specs[k].tensor,0,witness.specs[k].offset);
    mgr.alloc_bufs(false);mgr.open_files({argv[1]});require(mgr.use_direct_io,"native buffered fallback rejected");
    for(const auto & f:mgr.files)require(fcntl(f->file_id(),F_GETFL)&O_DIRECT,"native model fd is not O_DIRECT");
    biases.buffer=ggml_backend_alloc_ctx_tensors(biases.ctx,backend.value);require(biases.buffer,"bias allocation failed");
    for(int k=3;k<6;++k){std::vector<uint8_t> data(witness.specs[k].bytes);reader.read(data.data(),data.size(),witness.specs[k].offset);ggml_backend_tensor_set(witness.tensors[k],data.data(),0,data.size());}
    graph_plan graph;const bool reuse=mode.back()=='B';build(graph,backend.value,mgr.layer(layer),witness.tensors,tiles,reuse);
    const bool numeric=mode.rfind("numeric",0)==0;witness.enabled=numeric;active_witness=&witness;
    const auto initial=state(mgr,layer);const auto start=std::chrono::steady_clock::now();
    require(ggml_backend_graph_compute(backend.value,graph.graph)==GGML_STATUS_SUCCESS,"reuse CPU graph failed");ggml_backend_synchronize(backend.value);
    const double wall=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();active_witness=nullptr;
    const auto final=state(mgr,layer);reuse_json outputs=reuse_json::array();
    for(size_t i=0;i<tiles.size();++i){const auto result=tensor_get<float>(graph.outputs[i]);const auto cmp=compare(result,tiles[i].expected);
        outputs.push_back({{"phase",tiles[i].phase},{"tokens",tiles[i].n},{"bitwise",cmp.bitwise},{"nonfinite",cmp.nonfinite},{"max_abs",cmp.max_abs}});
        if(!cmp.bitwise||cmp.nonfinite)std::cerr<<outputs.back().dump()<<'\n';
        require(cmp.bitwise&&!cmp.nonfinite,"selected native FFN reference mismatch");}
    require(!numeric||witness.combinations>0,"consumer bytes witness omitted");
    const reuse_json report={{"status",numeric?"PASS_SELECTED_REUSE_NUMERIC":"MEASURED_SELECTED_REUSE_SERVICE"},{"mode",mode},{"layer",layer},{"slots",40},{"threads",8},{"wave_capacity",18},
        {"original_tile_shapes",{32,32,29}},{"groups",graph.group_tokens},{"waves_by_group",graph.wave_counts},{"outputs",outputs},{"consumer_byte_combinations",witness.combinations},
        {"service_wall_s",wall},{"timing_excludes","GGUF metadata, bias initialization, graph allocation, post-compute reference verification; includes native loads, preloads, compute, masks, ordered reduction and coordination"},
        {"initial",initial},{"final",final},{"direct_reader",true},{"logical_bytes_not_NVMe_traffic",true},{"source_scope","Selected disjoint original CPU tiles; not complete prefill or server measurement"}};
    const int fd=open(argv[5],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);require(fd>=0,"reuse receipt reused/unavailable");
    const auto text=report.dump(2)+"\n";size_t done=0;while(done<text.size()){const ssize_t n=write(fd,text.data()+done,text.size()-done);require(n>0,"reuse receipt short write");done+=static_cast<size_t>(n);}
    require(fsync(fd)==0&&close(fd)==0,"reuse receipt flush failed");std::cout<<report.dump()<<'\n';ggml_free(meta);gguf_free(gguf);return 0;
}catch(const std::exception & e){std::cerr<<"EXPERT_REUSE_FAIL: "<<e.what()<<'\n';return 1;}}
