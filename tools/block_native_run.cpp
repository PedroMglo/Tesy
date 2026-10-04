// Production C75 C-API calls: native IDs, draft-free fixed-grid reference,
// and controlled complete-output timing. No server lifecycle implementation.
#include "llama.h"
#include "llama-model.h"
#include "llama-moe-stream.h"
#include "ggml.h"
#include "ggml-backend.h"
#include "json.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <vector>
#include <fcntl.h>
#include <unistd.h>

namespace {
using json = nlohmann::ordered_json;
constexpr int vocab = 201088;
using clock_type = std::chrono::steady_clock;

void check(bool value, const char * reason) { if (!value) throw std::runtime_error(reason); }

void save(const std::filesystem::path & path, const json & value) {
    const auto temp = path.string()+".partial";
    const std::string text = value.dump(2)+"\n";
    const int fd = open(temp.c_str(), O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC, 0600);
    check(fd >= 0, "cannot create native receipt");
    size_t done = 0;
    while (done < text.size()) {
        const ssize_t n = write(fd, text.data()+done, text.size()-done);
        check(n > 0, "native receipt write failed"); done += static_cast<size_t>(n);
    }
    check(fsync(fd) == 0 && close(fd) == 0, "native receipt flush failed");
    // A live progress file can be replaced atomically; its final run root is new.
    std::filesystem::rename(temp, path);
}

void binary(const std::filesystem::path & path, const std::vector<float> & values) {
    const int fd = open(path.c_str(), O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC, 0600);
    check(fd >= 0, "binary root reused");
    const auto * data = reinterpret_cast<const char *>(values.data());
    size_t done = 0, bytes = values.size()*sizeof(float);
    while (done < bytes) { const ssize_t n=write(fd,data+done,bytes-done); check(n>0,"binary short write"); done+=static_cast<size_t>(n); }
    check(close(fd)==0,"binary close failed");
}

llama_token greedy(const float * row) {
    check(row != nullptr, "missing native logit row");
    int winner=0;
    for (int i=0; i<vocab; ++i) {
        check(std::isfinite(row[i]), "nonfinite native logit row");
        if (row[i]>row[winner]) winner=i;
    }
    return winner;
}

int logit_index(bool all, int output_row) {
    // Positive API indices identify input positions, not compact output rows.
    // With only the last input flagged, -1 identifies its compact last output.
    check(output_row>=0 && (all || output_row==0), "invalid compact logit mapping");
    return all ? output_row : -1;
}

struct rows_observer {
    int expected=0, ffn=0, projection=0;
};
bool observe_rows(ggml_tensor * tensor, bool, void * opaque) {
    auto & rows=*static_cast<rows_observer *>(opaque);
    const std::string name=ggml_get_name(tensor);
    if (name=="ffn_moe_out-35") rows.ffn=static_cast<int>(tensor->ne[1]);
    if (name=="result_output") rows.projection=static_cast<int>(tensor->ne[1]);
    // No requested tensor delivery, tensor_get, or forced synchronization.
    return false;
}

struct runtime {
    llama_model * model=nullptr;
    llama_context * ctx=nullptr;
    rows_observer rows;
    ~runtime() { if(ctx)llama_free(ctx); if(model)llama_model_free(model); llama_backend_free(); }
    explicit runtime(const char * path) {
        check(!getenv("GOMP_SPINCOUNT") && !getenv("LD_PRELOAD") &&
              !getenv("LLAMA_MOE_STREAM_NO_PRELOAD") && !getenv("TESY_CPU_FA_PREFILL_VEC_COMPAT"), "unfrozen profile environment");
        llama_backend_init();
        auto mp=llama_model_default_params();
        mp.n_gpu_layers=12;mp.use_mmap=false;mp.use_direct_io=true;mp.use_extra_bufts=false;
        mp.moe_stream=true;mp.moe_stream_slots=40;mp.moe_stream_io_threads=4;mp.moe_stream_direct=true;
        model=llama_model_load_from_file(path,mp);check(model,"native model load failed");
        auto cp=llama_context_default_params();
        cp.n_ctx=8192;cp.n_batch=256;cp.n_ubatch=32;cp.n_seq_max=1;
        cp.n_threads=8;cp.n_threads_batch=8;cp.op_offload=false;
        cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;cp.type_k=GGML_TYPE_F16;cp.type_v=GGML_TYPE_F16;
        cp.swa_full=true;cp.offload_kqv=true;cp.kv_unified=true;
        cp.cb_eval=observe_rows;cp.cb_eval_user_data=&rows;
        ctx=llama_init_from_model(model,cp);check(ctx,"native context init failed");
        check(llama_vocab_n_tokens(llama_model_get_vocab(model))==vocab,"vocabulary changed");
        std::cout<<"C80_CONTEXT_READY native=1 P12 slots40 ub32 ctx8192\n"<<std::flush;
    }
    std::vector<float> call(const std::vector<llama_token> & ids,int position,bool all) {
        check(!ids.empty() && ids.size()<=256 && position>=0 && position+ids.size()<=8192,"native call plan invalid");
        rows.expected=all?static_cast<int>(ids.size()):1;rows.ffn=rows.projection=0;
        llama_batch batch=llama_batch_init(static_cast<int>(ids.size()),0,1);batch.n_tokens=static_cast<int>(ids.size());
        for(int i=0;i<batch.n_tokens;++i){batch.token[i]=ids[static_cast<size_t>(i)];batch.pos[i]=position+i;batch.n_seq_id[i]=1;batch.seq_id[i][0]=0;batch.logits[i]=all||i==batch.n_tokens-1;}
        const int rc=llama_decode(ctx,batch);llama_batch_free(batch);check(rc==0,"native decode failed");llama_synchronize(ctx);
        check(rows.ffn==rows.expected&&rows.projection==rows.expected,"native complete FFN/projection rows missing");
        std::vector<float> out(static_cast<size_t>(rows.expected)*vocab);
        for(int i=0;i<rows.expected;++i){const float * data=llama_get_logits_ith(ctx,logit_index(all,i));check(data,"missing native output row");std::memcpy(out.data()+static_cast<size_t>(i)*vocab,data,vocab*sizeof(float));}
        return out;
    }
    void trim(int position) {llama_synchronize(ctx);check(llama_memory_seq_rm(llama_get_memory(ctx),0,position,-1),"rollback rejected");}
    json snapshot() {
        auto * mgr=model->moe_stream();check(mgr,"native stream manager unavailable");
        std::unique_lock<std::mutex> lock(mgr->mtx);
        const auto drained=[&]{
            if(!mgr->q_demand.empty())return false;
            for(const auto & sl:mgr->layers)if(sl)for(size_t i=0;i<sl->slot_state.size();++i)
                if(sl->slot_claimed[i]||sl->slot_state[i]==LLAMA_MOE_STREAM_SLOT_LOADING)return false;
            return true;
        };
        check(mgr->cv_done.wait_for(lock,std::chrono::seconds(5),drained),"pending expert workers did not drain within5s");
        check(!mgr->load_failed,"stream load failed");
        json states=json::array();
        for(const auto & sl:mgr->layers)if(sl){
            size_t bytes=0;for(const auto & weight:sl->weights)bytes+=weight.nb_expert;
            check(!sl->weights.empty(),"stream layer has no native weights");
            states.push_back({{"layer",sl->il},{"slot_expert",sl->slot_expert},{"slot_state",sl->slot_state},
            {"slot_claimed",sl->slot_claimed},{"slot_generation",sl->slot_gen},{"slot_last_use",sl->slot_last_use},
            {"route_hotness",sl->route_hotness},{"seen",sl->seen},{"use_counter",sl->use_counter},
            {"keep",sl->keep},{"expert_wave",sl->expert_wave},{"plan_next_wave",sl->plan_next_wave},
            {"native_cache_buffer",ggml_backend_buffer_name(sl->weights[0].cache->buffer)},
            {"logical_bytes_per_load",bytes}});}
        return {{"layers",states},{"pending_queue",mgr->q_demand.size()},
            {"n_calls",mgr->stats.n_calls},{"n_miss",mgr->stats.n_miss},{"n_preload",mgr->stats.n_preload_issued},
            {"n_waves",mgr->stats.n_waves_run},{"stall_us",mgr->stats.t_stall_us},{"stall_wave_us",mgr->stats.t_stall_wave_us},
            {"note","Metadata snapshot after bounded worker drain; not KV-only restoration or physical-byte traffic"}};
    }
    std::vector<std::vector<int32_t>> last_routes() {
        auto * mgr=model->moe_stream();std::lock_guard<std::mutex> lock(mgr->mtx);
        std::vector<std::vector<int32_t>> result;
        for(const auto & sl:mgr->layers)if(sl)result.push_back(sl->uniq);
        check(result.size()==36,"last authoritative layer route metadata missing");
        return result;
    }
};
} // namespace

int main(int argc,char ** argv) {
    if(argc==2 && std::string(argv[1])=="--self-test"){
        try{
            for(int B:{2,4,8})for(int i=0;i<B;++i)check(logit_index(true,i)==i,"all-row mapping changed");
            check(logit_index(false,0)==-1,"last-only warmup must address -1");
            bool rejected=false;try{logit_index(false,1);}catch(const std::exception&){rejected=true;}
            check(rejected,"compact-index misuse not rejected");
            std::cout<<"{\"status\":\"PASS_MODEL_FREE_NATIVE_LOGIT_MAPPING\",\"all_rows\":[2,4,8],\"last_only_index\":-1,\"weights_loaded\":false}\n";return 0;
        }catch(const std::exception & exc){std::cerr<<exc.what()<<"\n";return 1;}
    }
    if(argc!=8){std::cerr<<"usage: block_native_run MODEL FIXTURE CASE OUTPUT MODE(generate|grid|ar|block) COUNT v1\n";return 2;}
    try{
        std::ifstream input(argv[2]);json fixtures;input>>fixtures;check(bool(input),"fixture read failed");
        const std::string id=argv[3],mode=argv[5];const int count=std::stoi(argv[6]);
        // argv7 is a prospective literal protocol version, not a sampler knob.
        check(std::string(argv[7])=="v1","unfrozen native contract version");
        check(mode=="generate"||mode=="grid"||mode=="ar"||mode=="block","unknown native mode");
        check(fixtures.contains(id),"unknown native case");const json fixture=fixtures.at(id);
        const auto prefix=fixture.at("ids").get<std::vector<llama_token>>();
        check(!prefix.empty()&&prefix.size()<=7936,"input/context reserve invalid");
        for(llama_token token:prefix)check(token>=0&&token<vocab,"invalid official input ID");
        check((mode=="generate"&&count==128)||(mode!="generate"&&(count==2||count==4||count==8)),"unfrozen count/block shape");
        std::vector<llama_token> continuation;
        if(mode!="generate"){
            continuation=fixture.at("continuation_ids").get<std::vector<llama_token>>();
            for(llama_token token:continuation)check(token>=0&&token<vocab,"invalid native continuation ID");
            check(continuation.size()>=static_cast<size_t>(mode=="grid"?count:32),"insufficient frozen native continuation");
        }
        const std::filesystem::path root=argv[4];check(std::filesystem::create_directory(root),"native output root reused");
        runtime run(argv[1]);
        const int origin=static_cast<int>(prefix.size());
        auto plan=fixture.value("warmup_calls",std::vector<int>{});
        if(plan.empty())for(int left=origin;left>0;left-=std::min(left,256))plan.push_back(std::min(left,256));
        int position=0;std::vector<float> latest;
        for(int n:plan){check(n>0&&n<=256&&position+n<=origin,"warmup external calls invalid");latest=run.call({prefix.begin()+position,prefix.begin()+position+n},position,false);position+=n;}
        check(position==origin,"warmup did not cover official prefix");
        const auto initial=run.snapshot();save(root/"initial-residency.json",initial);
        json receipt={{"case",id},{"mode",mode},{"B",mode=="generate"?1:count},{"official_prefix_ids",prefix},
            {"warmup_calls",plan},{"rows_policy","All rows FFN+vocabulary; no tensor capture during timing"},
            {"R0","Autoregressive C75/P12/slots40/ub32"},{"sampling","Native greedy only; proposed/teacher-forced inputs are not confirmed throughput"}};
        if(mode=="generate"){
            std::vector<llama_token> generated;std::string finish="DIAGNOSTIC_CAP";
            for(int i=0;i<count;++i){const auto token=greedy(latest.data());generated.push_back(token);
                if(llama_vocab_is_eog(llama_model_get_vocab(run.model),token)){finish="EOS";break;}
                latest=run.call({token},origin+i,true);
                if(i%8==0){receipt["native_generated_ids"]=generated;receipt["status"]="PARTIAL_NATIVE_CONTROL";save(root/"progress.json",receipt);}}
            receipt["native_generated_ids"]=generated;receipt["finish"]=finish;receipt["status"]="NATIVE_CONTROL_IDS_CAPTURED";
        }else{
            if(mode=="grid"){
                const std::vector<llama_token> first(continuation.begin(),continuation.begin()+count);
                auto base=run.call(first,origin,true);binary(root/"production-base.logits.f32",base);
                json checks=json::array();
                for(int known=1;known<=count;++known){auto padded=first;std::fill(padded.begin()+known,padded.end(),0);run.trim(origin);
                    const auto reference=run.call(padded,origin,true);binary(root/("prefix-only-"+std::to_string(known)+".logits.f32"),reference);
                    const bool same=std::memcmp(base.data(),reference.data(),static_cast<size_t>(known)*vocab*sizeof(float))==0;
                    checks.push_back({{"known_rows",known},{"fixed_padding",0},{"prefix_only_inputs",padded},{"preceding_complete_rows_bitwise",same}});
                    receipt["checks"]=checks;receipt["status"]=same?"PARTIAL_R1_REFERENCE":"FAIL_R1_DEPENDS_ON_FUTURE";save(root/"progress.json",receipt);
                    check(same,"prefix-only fixed-grid R1 differs from speculative future");}
                receipt["status"]="PASS_SELECTED_DRAFT_INDEPENDENT_GRID";
            }else{
                const int block=mode=="ar"?1:count;const auto begin=clock_type::now();
                std::vector<llama_token> winners;
                std::vector<std::vector<std::vector<int32_t>>> routes;
                for(int i=0;i<32;i+=block){const auto out=run.call({continuation.begin()+i,continuation.begin()+i+block},origin+i,true);
                    for(int j=0;j<block;++j)winners.push_back(greedy(out.data()+static_cast<size_t>(j)*vocab));
                    routes.push_back(run.last_routes());}
                // Metadata is sampled only once per complete call. No tensor
                // dump or router D2H copy is added by this observation.
                // Its small lock/copy overhead is included in both paths.
                const double wall=std::chrono::duration<double>(clock_type::now()-begin).count();
                receipt["wall_s"]=wall;receipt["positions"]=32;receipt["calls"]=32/block;receipt["complete_logit_rows"]=32;
                receipt["native_teacher_forced_inputs"]=std::vector<llama_token>(continuation.begin(),continuation.begin()+32);
                receipt["native_argmax_ids"]=winners;receipt["ideal_L"]=32;receipt["D_assumed_s"]=0;receipt["R_assumed_s"]=0;
                receipt["authoritative_union_by_call_layer"]=routes;
                receipt["status"]="MEASURED_CONTROLLED_COMPLETE_OUTPUT_PATH";
            }
        }
        save(root/"result.json",receipt);save(root/"final-residency.json",run.snapshot());
        std::cout<<receipt.dump()<<"\n"<<std::flush;return 0;
    }catch(const std::exception & exc){std::cerr<<"BLOCK_NATIVE_FAIL: "<<exc.what()<<"\n";return 1;}
}
