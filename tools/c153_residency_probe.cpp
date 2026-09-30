// Fixed teacher-forced mechanism workload; not a free-generation server benchmark.
#include "llama.h"
#include "llama-model.h"
#include "llama-moe-stream.h"
#include "ggml.h"
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>

static void require(bool x,const char * s){if(!x)throw std::runtime_error(s);}
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
        llama_backend_init();auto mp=llama_model_default_params();
        mp.n_gpu_layers=12;mp.use_mmap=false;mp.use_extra_bufts=false;mp.check_tensors=false;
        mp.moe_stream=true;mp.moe_stream_slots=44;mp.moe_stream_io_threads=4;mp.moe_stream_direct=true;
        auto * model=llama_model_load_from_file(argv[1],mp);require(model,"model init");
        auto cp=llama_context_default_params();cp.n_ctx=8192;cp.n_batch=256;cp.n_ubatch=32;cp.n_seq_max=1;
        cp.n_threads=cp.n_threads_batch=8;cp.op_offload=false;cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;
        cp.type_k=cp.type_v=GGML_TYPE_F16;cp.swa_full=true;cp.offload_kqv=true;cp.kv_unified=true;
        auto * ctx=llama_init_from_model(model,cp);require(ctx,"ctx8192 init");
        auto * mgr=model->moe_stream();require(mgr,"stream manager");
        std::ofstream plan(root/"calls.tsv");plan<<"call\trequest\tphase\tfirst\tlast\tn_tokens\tbegin_us\tend_us\n";
        int call=0;std::vector<float> logits;
        auto decode=[&](const std::vector<llama_token> & ids,int pos,int request,const char * phase) {
            auto b=llama_batch_init(ids.size(),0,1);b.n_tokens=ids.size();
            for(int i=0;i<b.n_tokens;++i){b.token[i]=ids[i];b.pos[i]=pos+i;b.n_seq_id[i]=1;b.seq_id[i][0]=0;b.logits[i]=i==b.n_tokens-1;}
            auto begin=ggml_time_us();int rc=llama_decode(ctx,b);llama_synchronize(ctx);auto end=ggml_time_us();
            llama_batch_free(b);require(rc==0,"forward failed");
            plan<<++call<<'\t'<<request<<'\t'<<phase<<'\t'<<pos<<'\t'<<pos+ids.size()-1<<'\t'<<ids.size()<<'\t'<<begin<<'\t'<<end<<'\n';
            auto * values=llama_get_logits(ctx);require(values,"full logits");
            for(int i=0;i<201088;++i)require(std::isfinite(values[i]),"nonfinite logits");
            logits.insert(logits.end(),values,values+201088);
        };
        std::cout<<"C153_CONTEXT_READY ctx8192 P12 slots44"<<std::endl;
        if(logged)mgr->journal_request(1);
        for(size_t p=0;p<prefix.size();p+=256) {
            size_t end=std::min(prefix.size(),p+256);decode({prefix.begin()+p,prefix.begin()+end},p,1,"prefix-warmup");
        }
        if(logged) {
            mgr->journal_request(2);
            mgr->snapshot((root/"before-warm.snap").c_str(),0,0,2044,2044+warm.size()-1);
        }
        decode({warm.begin(),warm.begin()+5},2044,2,"warm-prefill");
        decode({warm.begin()+5,warm.end()},2049,2,"warm-prefill");
        if(logged)mgr->snapshot((root/"after-prefill.snap").c_str(),1,1,2044,2044+warm.size()-1);
        for(int i=0;i<47;++i)decode({tf[i]},2044+warm.size()+i,2,"decode");
        if(logged)mgr->snapshot((root/"final.snap").c_str(),2,2,2044+warm.size(),2044+warm.size()+46);
        plan.close();require(bool(plan),"call plan output");
        std::ofstream out(root/"full-logits.f32",std::ios::binary);out.write(reinterpret_cast<const char *>(logits.data()),logits.size()*sizeof(float));out.close();require(bool(out),"logit output");
        std::cout<<"C153_FIXED_WORK_PASS prefix2044 new="<<warm.size()<<" teacher_forced_calls=47 full_logit_rows="<<call<<std::endl;
        llama_free(ctx);llama_model_free(model);llama_backend_free();return 0;
    }catch(const std::exception & e){std::cerr<<"C153_FAIL: "<<e.what()<<std::endl;return 1;}
}
