// Fixed teacher-forced mechanism workload; not a free-generation server benchmark.
#include "llama.h"
#include "llama-model.h"
#include "llama-moe-stream.h"
#include "ggml.h"
#include "ggml-backend.h"
#include <array>
#include <map>
#include <mutex>
#include <cstring>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>

#include "residency_journal_window.inl"

static void require(bool x,const char * s){if(!x)throw std::runtime_error(s);}
struct witness_state {
    bool enabled=false;int call=0;std::filesystem::path root;
    std::map<std::string,int> occurrences;std::string index;
};
static bool witness(ggml_tensor * t,bool ask,void * opaque) {
    auto & state=*static_cast<witness_state *>(opaque);if(!state.enabled)return false;
    std::string name=t->name;auto dash=name.rfind('-');if(dash==std::string::npos)return false;
    auto stage=name.substr(0,dash);auto layer=name.substr(dash+1);
    if(layer.empty()||layer.find_first_not_of("0123456789")!=std::string::npos)return false;
    const int il=std::stoi(layer);if(il<0||il>=36)return false;
    const std::array<const char *,6> core={"attn_post_norm","ffn_moe_logits","ffn_moe_probs","ffn_moe_topk","ffn_moe_weights_softmax","ffn_moe_out"};
    bool wanted=false;for(auto x:core)wanted|=stage==x;if(!wanted)return false;if(ask)return true;
    require(t->type==(stage=="ffn_moe_topk"?GGML_TYPE_I32:GGML_TYPE_F32),"witness dtype");
    const size_t bytes=ggml_nbytes(t);require(bytes<=64*1024*1024,"witness tensor bound");
    std::vector<uint8_t> data(bytes),packed;if(bytes)ggml_backend_tensor_get(t,data.data(),0,bytes);
    for(int64_t i3=0;i3<t->ne[3];++i3)for(int64_t i2=0;i2<t->ne[2];++i2)
    for(int64_t i1=0;i1<t->ne[1];++i1)for(int64_t i0=0;i0<t->ne[0];++i0){
        size_t at=i0*t->nb[0]+i1*t->nb[1]+i2*t->nb[2]+i3*t->nb[3];require(at+4<=data.size(),"witness stride");
        if(t->type==GGML_TYPE_F32){float x;std::memcpy(&x,data.data()+at,4);require(std::isfinite(x),"witness nonfinite");}
        else {int32_t x;std::memcpy(&x,data.data()+at,4);require(x>=0&&x<128,"witness routed ID");}
        packed.insert(packed.end(),data.begin()+at,data.begin()+at+4);
    }
    std::string key=std::to_string(state.call)+"-"+layer+"-"+stage;
    const std::string file=key+"-"+std::to_string(state.occurrences[key]++)+".bin";
    std::ofstream out(state.root/(file+".partial"),std::ios::binary);out.write(reinterpret_cast<const char *>(packed.data()),packed.size());out.close();require(bool(out),"witness write");
    std::filesystem::create_hard_link(state.root/(file+".partial"),state.root/file);std::filesystem::remove(state.root/(file+".partial"));
    state.index+=file+"\t"+std::to_string(packed.size())+"\t";
    for(int j=0;j<4;++j)state.index+=std::to_string(t->ne[j])+(j==3?"\n":",");return true;
}

static std::vector<llama_token> row(std::ifstream & in,const char * label) {
    std::string line;std::getline(in,line);require(line.rfind(std::string(label)+"\t",0)==0,"input field");
    std::istringstream values(line.substr(line.find('\t')+1));std::string part;std::vector<llama_token> ids;
    while(std::getline(values,part,',')){int id=std::stoi(part);require(id>=0&&id<201088,"input token");ids.push_back(id);}return ids;
}
int main(int argc,char ** argv) {
    try {
        require(argc==4,"MODEL IDS OUTPUT");std::filesystem::path root=argv[3];
        require(std::filesystem::create_directory(root),"new probe output");
        std::ifstream in(argv[2]);auto prefix=row(in,"prefix"),warm=row(in,"warm"),tf=row(in,"decode");
        require(prefix.size()==2044&&warm.size()>=128&&warm.size()<=160&&tf.size()==47,"frozen counts");
        require(std::getenv("TESY_CPU_WAVE_SKIP_PARKED")&&!std::getenv("LLAMA_MOE_STREAM_NO_PRELOAD")&&!std::getenv("LD_PRELOAD"),"frozen profile env");
        const bool logged=std::getenv("TESY_C152_SNAPSHOT_ENABLED");
        if(logged)for(auto name:{"TESY_C152_MODEL_HASH","TESY_C152_SOURCE_HASH","TESY_C152_BUILD_HASH","TESY_C152_PROFILE_HASH","TESY_C84_EXPERT_TRACE_FILE","TESY_C152_ROUTE_FILE"})require(std::getenv(name),"logger identity missing before model");
        witness_state witness_data;const bool numeric=std::getenv("TESY_C156_NUMERIC_WITNESS");
        if(numeric){witness_data.root=root/"witness";require(std::filesystem::create_directory(witness_data.root),"new witness directory");}
        llama_backend_init();auto mp=llama_model_default_params();
        mp.n_gpu_layers=12;mp.use_mmap=false;mp.use_direct_io=true;mp.use_extra_bufts=false;mp.check_tensors=false;
        mp.moe_stream=true;mp.moe_stream_slots=44;mp.moe_stream_io_threads=4;mp.moe_stream_direct=true;
        auto * model=llama_model_load_from_file(argv[1],mp);require(model,"model init");
        auto cp=llama_context_default_params();cp.n_ctx=8192;cp.n_batch=256;cp.n_ubatch=32;cp.n_seq_max=1;
        cp.n_threads=cp.n_threads_batch=8;cp.op_offload=false;cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;
        cp.type_k=cp.type_v=GGML_TYPE_F16;cp.swa_full=true;cp.offload_kqv=true;cp.kv_unified=true;
        if(numeric){cp.cb_eval=witness;cp.cb_eval_user_data=&witness_data;}
        auto * ctx=llama_init_from_model(model,cp);require(ctx,"ctx8192 init");
        auto * mgr=model->moe_stream();require(mgr,"stream manager");
        std::ofstream plan(root/"calls.tsv");plan<<"call\trequest\tphase\tfirst\tlast\tn_tokens\tbegin_us\tend_us\n";
        int call=0;std::vector<float> logits;logits.reserve(57*201088);
        std::ofstream snapshot_times(root/"snapshots.tsv");snapshot_times<<"name\tbegin_us\tend_us\tbytes\n";
        auto decode=[&](const std::vector<llama_token> & ids,int pos,int request,const char * phase) {
            auto b=llama_batch_init(ids.size(),0,1);b.n_tokens=ids.size();
            for(int i=0;i<b.n_tokens;++i){b.token[i]=ids[i];b.pos[i]=pos+i;b.n_seq_id[i]=1;b.seq_id[i][0]=0;b.logits[i]=i==b.n_tokens-1;}
            witness_data.enabled=numeric&&request==2&&(std::string(phase)=="warm-prefill"||call==10||call==56);witness_data.call=call+1;
            auto begin=ggml_time_us();int rc=llama_decode(ctx,b);llama_synchronize(ctx);auto end=ggml_time_us();
            llama_batch_free(b);require(rc==0,"forward failed");
            plan<<++call<<'\t'<<request<<'\t'<<phase<<'\t'<<pos<<'\t'<<pos+ids.size()-1<<'\t'<<ids.size()<<'\t'<<begin<<'\t'<<end<<'\n';
            auto * values=llama_get_logits(ctx);require(values,"full logits");
            for(int i=0;i<201088;++i)require(std::isfinite(values[i]),"nonfinite logits");
            logits.insert(logits.end(),values,values+201088);
        };
        auto take_snapshot=[&](const char * name,int sequence,int phase,int first,int last){
            auto a=ggml_time_us();mgr->snapshot((root/name).c_str(),sequence,phase,first,last);auto b=ggml_time_us();
            snapshot_times<<name<<'\t'<<a<<'\t'<<b<<'\t'<<std::filesystem::file_size(root/name)<<'\n';
        };
        std::cout<<"C153_CONTEXT_READY ctx8192 P12 slots44"<<std::endl;
        if(logged)mgr->journal_request(1);
        for(size_t p=0;p<prefix.size();p+=256) {
            size_t end=std::min(prefix.size(),p+256);decode({prefix.begin()+p,prefix.begin()+end},p,1,"prefix-warmup");
            if(logged) {
                // The accepted journal is the warm window. Bound temporary prefix logs
                // at each natural call boundary; retain all logical manager/worker state.
                // No draining, cancellation or cache mutation. Retrospective pending
                // worker spans can publish later and are seeded by before-warm.snap.
                reset_warmup_journal(mgr);
            }
        }
        if(logged) {
            mgr->journal_request(2);
            take_snapshot("before-warm.snap",0,0,2044,2044+warm.size()-1);
        }
        decode({warm.begin(),warm.begin()+5},2044,2,"warm-prefill");
        decode({warm.begin()+5,warm.end()},2049,2,"warm-prefill");
        if(logged)take_snapshot("after-prefill.snap",1,1,2044,2044+warm.size()-1);
        for(int i=0;i<47;++i)decode({tf[i]},2044+warm.size()+i,2,"decode");
        if(logged)take_snapshot("final.snap",2,2,2044+warm.size(),2044+warm.size()+46);
        snapshot_times.close();
        if(numeric){std::ofstream i(witness_data.root/"index.tsv");i<<witness_data.index;i.close();require(bool(i),"witness index");}
        plan.close();require(bool(plan),"call plan output");
        std::ofstream out(root/"full-logits.f32",std::ios::binary);out.write(reinterpret_cast<const char *>(logits.data()),logits.size()*sizeof(float));out.close();require(bool(out),"logit output");
        std::cout<<"C153_FIXED_WORK_PASS prefix2044 new="<<warm.size()<<" teacher_forced_calls=47 full_logit_rows="<<call<<std::endl;
        llama_free(ctx);llama_model_free(model);llama_backend_free();return 0;
    }catch(const std::exception & e){std::cerr<<"C153_FAIL: "<<e.what()<<std::endl;return 1;}
}
