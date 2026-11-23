// Isolated per-slot readiness pilot; original C75 loader/workers and native arithmetic.
#define main historical_c7_main
#include "c7_layer_reference.cpp"
#undef main
#include "c210_direct_reader.h"
#include "readiness_pilot_state.h"
#include "nlohmann/json.hpp"
#include <future>
#include <sys/resource.h>
using json=nlohmann::json;
static std::atomic<readiness_request*> current_request{nullptr};
static std::atomic<uint64_t> native_hook_calls{0};
extern "C" void tesy_readiness_consume(const ggml_tensor * weights,int slot,int ith) {
    (void)ith;++native_hook_calls;
    auto*r=current_request.load(std::memory_order_acquire);
    if(!r)return;
    for(const auto&w:r->layer->weights)if(w.cache==weights) {
        if(!r->wait(slot))std::abort();
        return;
    }
}

namespace {
using pilot_clock=std::chrono::steady_clock;
double seconds(pilot_clock::time_point a,pilot_clock::time_point b){return std::chrono::duration<double>(b-a).count();}
struct operator_graph {
    owner allocation;ggml_cgraph* graph=nullptr;ggml_tensor* output=nullptr;
};
void graph_for(operator_graph&g,ggml_backend_t backend,const std::array<ggml_tensor*,6>&t,
               const std::vector<float>&input,const std::array<int32_t,4>&logical,
               const std::array<int32_t,4>&slots,const std::vector<float>&mix) {
    g.allocation.ctx=context(16u*1024u*1024u);auto*c=g.allocation.ctx;
    auto*inp=ggml_new_tensor_2d(c,GGML_TYPE_F32,embd,1);
    auto*ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,1);auto*pids=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,1);
    auto*weights=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,4,1);auto*inp3=ggml_reshape_3d(c,inp,embd,1,1);
    auto*up=ggml_mul_mat_id(c,t[1],inp3,pids);up=ggml_add_id(c,up,t[4],ids);
    auto*gate=ggml_mul_mat_id(c,t[0],inp3,pids);gate=ggml_add_id(c,gate,t[3],ids);
    auto*act=ggml_swiglu_oai(c,gate,up,1.702f,7.0f);
    auto*down=ggml_mul_mat_id(c,t[2],act,pids);down=ggml_add_id(c,down,t[5],ids);down=ggml_mul(c,down,weights);
    ggml_tensor*sum=nullptr;for(int k=0;k<4;k++){auto*v=ggml_view_2d(c,down,embd,1,down->nb[2],k*down->nb[1]);sum=sum?ggml_add(c,sum,v):v;}
    g.output=ggml_cont(c,sum);ggml_set_output(g.output);g.graph=ggml_new_graph(c);ggml_build_forward_expand(g.graph,g.output);
    g.allocation.buffer=ggml_backend_alloc_ctx_tensors(c,backend);require(g.allocation.buffer,"pilot graph allocation");
    ggml_backend_tensor_set(inp,input.data(),0,input.size()*4);ggml_backend_tensor_set(ids,logical.data(),0,16);
    ggml_backend_tensor_set(pids,slots.data(),0,16);ggml_backend_tensor_set(weights,mix.data(),0,16);
}
bool all_ready_locked(readiness_request&r) {
    if(r.layer->mgr->load_failed||r.layer->mgr->shutting_down)throw std::runtime_error("native loader error/shutdown");
    for(int i=0;i<4;i++){require(r.identity_locked(i),"stale identity or lost keep pin");if(r.layer->slot_state[r.slots[i]]!=LLAMA_MOE_STREAM_SLOT_RESIDENT)return false;}
    return true;
}
void witness(tesy_witness::direct_reader&reader,const std::array<spec,6>&s,
             const std::array<ggml_tensor*,6>&t,const readiness_request&r) {
    for(int component=0;component<6;component++) {
        size_t bytes=s[component].bytes/128;require(bytes==(component<3?4406400u:11520u),"native slice size");
        std::vector<uint8_t> a(bytes),b(bytes);
        for(int k=0;k<4;k++) {
            reader.read(a.data(),bytes,s[component].offset+static_cast<uint64_t>(r.experts[k])*bytes);
            ggml_backend_tensor_get(t[component],b.data(),static_cast<size_t>(component<3?r.slots[k]:r.experts[k])*bytes,bytes);
            require(a==b,"native payload/witness mismatch");
        }
    }
}
void self_test() {
    llama_moe_stream mgr(1,4,4,true);llama_moe_stream_layer l;l.mgr=&mgr;l.n_slots=4;
    l.slot_expert={0,1,2,3};l.slot_state={1,1,1,1};l.slot_gen={1,1,1,1};l.keep={1,1,1,1};
    readiness_request r;r.layer=&l;r.experts={0,1,2,3};r.slots={0,1,2,3};r.generations={1,1,1,1};for(auto&p:r.published)p.store(false);
    {std::lock_guard<std::mutex> lock(mgr.mtx);l.slot_gen[0]=2;}
    require(!r.wait(0),"stale generation must reject");
    {std::lock_guard<std::mutex> lock(mgr.mtx);l.slot_gen[0]=1;l.slot_expert[0]=9;}
    require(!r.wait(0),"wrong expert must reject");
    {std::lock_guard<std::mutex> lock(mgr.mtx);l.slot_expert[0]=0;l.keep[0]=0;}
    require(!r.wait(0),"lost keep pin must reject before publication");
    {std::lock_guard<std::mutex> lock(mgr.mtx);l.keep[0]=1;}
    {std::lock_guard<std::mutex> lock(mgr.mtx);l.slot_expert[0]=0;mgr.load_failed=true;}
    require(!r.wait(0),"read failure must reject");mgr.load_failed=false;
    auto blocked=std::async(std::launch::async,[&]{return r.wait(0);});
    r.cancelled.store(true);mgr.cv_done.notify_all();require(!blocked.get(),"cancel must terminate blocked consumer");
    {std::lock_guard<std::mutex> lock(mgr.mtx);l.slot_state[0]=2;}mgr.cv_done.notify_all();
    require(!r.wait(0),"late commit cannot revive cancellation");
    r.cancelled.store(false);require(r.wait(0),"valid committed identity must pass");
    require(!r.wait(99),"unknown slot must reject");
    std::cout<<"{\"status\":\"PASS_MODEL_FREE_READINESS_IDENTITY_ERROR_CANCEL_LATE_WORKER\",\"model_weights_loaded\":false}\n";
}
}

int main(int argc,char**argv){try {
    if(argc==2&&std::string(argv[1])=="--self-test"){self_test();return 0;}
    require(argc==4,"usage: readiness_pilot MODEL CAPTURE CASES_JSON");
    auto protocol=json::parse(std::ifstream(argv[3]));
    ggml_context*meta=nullptr;gguf_init_params params{true,&meta};auto*gguf=gguf_init_from_file(argv[1],params);require(gguf&&meta,"pilot metadata");
    tesy_witness::direct_reader reader;reader.open_file(argv[1]);
    backend_owner backend{ggml_backend_cpu_init()};require(backend.value,"pilot CPU backend");ggml_backend_cpu_set_n_threads(backend.value,8);
    for(const auto&test:protocol.at("cases")) {
        int layer=test.at("operator_layer");auto rows=index(std::filesystem::path(argv[2]),layer);
        const auto&a=one(rows,"decode0","attn_post_norm");const auto&i=one(rows,"decode0","ffn_moe_topk");
        const auto&si=one(rows,"decode0","ffn_moe_topk_stream");const auto&w=one(rows,"decode0","ffn_moe_weights_softmax");const auto&o=one(rows,"decode0","ffn_moe_out");
        require(a.ne[1]==1&&i.ne[0]==4&&si.ne[0]==4,"pilot captured decode shape");
        auto input=read_strided<float>(a,embd,1,a.nb[0],a.nb[1]);auto logical=read_strided<int32_t>(i,4,1,i.nb[0],i.nb[1]);
        auto slots=read_strided<int32_t>(si,4,1,si.nb[0],si.nb[1]);auto mix=read_strided<float>(w,4,1,w.nb[1],w.nb[2]);auto expected=read_strided<float>(o,embd,1,o.nb[0],o.nb[1]);
        llama_moe_stream mgr(36,44,4,true);owner biases;biases.ctx=context(8u*1024u*1024u);
        std::array<ggml_tensor*,6> tensors{};std::array<spec,6> specs{};
        const std::array<std::string,6> names{"gate_exps.weight","up_exps.weight","down_exps.weight","gate_exps.bias","up_exps.bias","down_exps.bias"};
        std::array<ggml_tensor*,6> canonical{};
        for(int k=0;k<6;k++) {
            const auto name="blk."+std::to_string(layer)+".ffn_"+names[k];canonical[k]=ggml_get_tensor(meta,name.c_str());require(canonical[k],"pilot canonical tensor missing");
            specs[k]=get_spec(gguf,meta,canonical[k],name,k<3?GGML_TYPE_MXFP4:GGML_TYPE_F32,k<3?std::vector<int64_t>{embd,embd,128}:std::vector<int64_t>{embd,128});
            if(k>=3)tensors[k]=ggml_new_tensor_2d(biases.ctx,GGML_TYPE_F32,embd,128);
        }
        // Register in actual snapshot/native-loader order, not guessed graph order.
        for(const auto&component:test.at("native_components")) {
            uint64_t offset=component.at("offset");int k=-1;for(int j=0;j<3;j++)if(specs[j].offset==offset)k=j;
            require(k>=0&&!tensors[k]&&component.at("expert_bytes")==4406400,"native component identity/order");
            tensors[k]=mgr.create_cache_tensor(layer,ggml_backend_cpu_buffer_type(),canonical[k],0,offset);
        }
        for(int k=0;k<3;k++)require(tensors[k],"missing native cache component");
        mgr.alloc_bufs(false);mgr.open_files({argv[1]});require(mgr.use_direct_io,"native loader buffered fallback rejected");
        for(const auto&file:mgr.files)require(fcntl(file->file_id(),F_GETFL)&O_DIRECT,"native model descriptor not direct");
        biases.buffer=ggml_backend_alloc_ctx_tensors(biases.ctx,backend.value);require(biases.buffer,"bias allocation");
        for(int k=3;k<6;k++)for(int j=0;j<4;j++){std::vector<uint8_t> data(11520);reader.read(data.data(),data.size(),specs[k].offset+static_cast<uint64_t>(logical[j])*11520);ggml_backend_tensor_set(tensors[k],data.data(),static_cast<size_t>(logical[j])*11520,data.size());}
        auto*sl=mgr.layer(layer);readiness_request r;r.layer=sl;
        for(int k=0;k<4;k++){r.experts[k]=logical[k];r.slots[k]=slots[k];require(logical[k]>=0&&logical[k]<128&&slots[k]>=0&&slots[k]<44,"pilot expert/slot");for(int j=0;j<k;j++)require(logical[k]!=logical[j]&&slots[k]!=slots[j],"pilot duplicate IDs");}
        {
            std::unique_lock<std::mutex> lock(mgr.mtx);mgr.start_workers_locked();
            for(int k=0;k<4;k++){mgr.reserve_slot_locked(*sl,r.experts[k],r.slots[k]);sl->keep[r.slots[k]]=1;r.generations[k]=sl->slot_gen[r.slots[k]];r.published[k].store(false);mgr.q_demand.push_back({sl,r.experts[k],r.slots[k],r.generations[k]});}
            mgr.cv_work.notify_all();mgr.cv_done.wait(lock,[&]{return all_ready_locked(r);});
        }
        witness(reader,specs,tensors,r);
        operator_graph graph;graph_for(graph,backend.value,tensors,input,r.experts,r.slots,mix);
        require(ggml_backend_graph_compute(backend.value,graph.graph)==GGML_STATUS_SUCCESS,"pilot initial FFN");ggml_backend_synchronize(backend.value);
        auto initial_cmp=compare(tensor_get<float>(graph.output),expected);
        require(initial_cmp.bitwise&&!initial_cmp.nonfinite,"private executor neutrality vs C127 FFN");
        const auto mask=test.at("miss_mask").get<std::array<bool,4>>();
        const std::array<bool,8> schedule{false,true,true,false,false,true,true,false};
        for(int rep=0;rep<8;rep++) {
            const bool candidate=schedule[rep];r.checks=0;r.slow_checks=0;r.cancelled=false;
            const auto start=pilot_clock::now();const uint64_t hooks_before=native_hook_calls;
            double collective_wait=0;
            {
                std::unique_lock<std::mutex> lock(mgr.mtx);require(all_ready_locked(r),"previous window pending");
                require(mgr.q_demand.empty(),"pending queue before new window");
                for(int k=0;k<4;k++) {
                    if(mask[k]){mgr.reserve_slot_locked(*sl,r.experts[k],r.slots[k]);mgr.q_demand.push_back({sl,r.experts[k],r.slots[k],sl->slot_gen[r.slots[k]]});}
                    sl->keep[r.slots[k]]=1;r.generations[k]=sl->slot_gen[r.slots[k]];r.published[k].store(!mask[k],std::memory_order_release);
                }
                mgr.cv_work.notify_all();
                if(!candidate){const auto wait_start=pilot_clock::now();mgr.cv_done.wait(lock,[&]{return all_ready_locked(r);});collective_wait=seconds(wait_start,pilot_clock::now());}
            }
            current_request.store(candidate?&r:nullptr,std::memory_order_release);
            require(ggml_backend_graph_compute(backend.value,graph.graph)==GGML_STATUS_SUCCESS,"pilot FFN execution");ggml_backend_synchronize(backend.value);
            current_request.store(nullptr,std::memory_order_release);const auto finish=pilot_clock::now();
            {std::lock_guard<std::mutex> lock(mgr.mtx);require(all_ready_locked(r),"FFN completed before bytes ready");for(int k=0;k<4;k++)require(!sl->slot_claimed[r.slots[k]],"worker still owns consumed slot");}
            auto cmp=compare(tensor_get<float>(graph.output),expected);require(cmp.bitwise&&!cmp.nonfinite,"per-slot pilot changed arithmetic");
            witness(reader,specs,tensors,r);require(native_hook_calls>hooks_before,"native MMID callback not exercised");
            if(candidate)require(r.checks>=32,"per-slot consume checks missing");
            std::cout<<json{{"case",test.at("name")},{"layer",layer},{"rep",rep},{"arm",candidate?"B":"A"},{"wall_s",seconds(start,finish)},{"collective_wait_s",collective_wait},{"consume_checks",r.checks.load()},{"slow_consume_checks",r.slow_checks.load()},{"native_hook_calls",native_hook_calls.load()-hooks_before},{"bitwise",true},{"finite",true},{"original_native_loader_direct",true},{"slots",44},{"threads",8}}.dump()<<'\n'<<std::flush;
        }
        {std::lock_guard<std::mutex> lock(mgr.mtx);for(int k=0;k<4;k++)sl->keep[r.slots[k]]=0;}
    }
    ggml_free(meta);gguf_free(gguf);return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
