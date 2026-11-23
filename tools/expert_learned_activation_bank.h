#pragma once
#include "expert_activation_estimator.h"
#include <openssl/sha.h>
#include <iomanip>
#include <sstream>
// Fixed movement-only affine after the original auxiliary gate evaluation.
// Target graph, true router and staged-byte worker remain untouched.
struct learned_score_affine {
    ggml_backend_t backend=nullptr;
    ggml_context *ctx=nullptr;ggml_backend_buffer_t buffer=nullptr;
    ggml_tensor *input=nullptr,*output=nullptr;ggml_cgraph *graph=nullptr;
    static size_t metadata(){return ggml_graph_overhead()+16*ggml_tensor_overhead()+65536;}
    learned_score_affine(const float *w,const float *b,ggml_backend_t shared):backend(shared){
        check(backend&&metadata()<=1024*1024,"bounded learned affine metadata/backend");
        ctx=ggml_init({metadata(),nullptr,true});check(ctx,"learned affine context");
        auto *weight=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,128,128);
        auto *bias=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,128);
        input=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,128,1);
        output=ggml_add(ctx,ggml_mul_mat(ctx,weight,input),bias);ggml_set_output(output);
        graph=ggml_new_graph(ctx);ggml_build_forward_expand(graph,output);
        buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);check(buffer,"learned affine buffer");
        ggml_backend_tensor_set(weight,w,0,128*128*4);ggml_backend_tensor_set(bias,b,0,128*4);
    }
    ~learned_score_affine(){if(buffer)ggml_backend_buffer_free(buffer);if(ctx)ggml_free(ctx);}
    std::array<float,128> score(const float *x){
        ggml_backend_tensor_set(input,x,0,128*4);
        check(ggml_backend_graph_compute(backend,graph)==GGML_STATUS_SUCCESS,"native learned affine compute");ggml_backend_synchronize(backend);
        std::array<float,128> y{};ggml_backend_tensor_get(output,y.data(),0,128*4);
        for(float f:y)check(std::isfinite(f),"nonfinite learned movement score");return y;
    }
};
inline void learned_affine_fixture(ggml_backend_t backend){
    std::vector<float> w(128*128,0),b(128);std::array<float,128>x{};
    for(int i=0;i<128;i++){w[i*128+i]=1; b[i]=i; x[i]=i;}
    learned_score_affine op(w.data(),b.data(),backend);
    for(int r=0;r<4;r++){auto y=op.score(x.data());for(int i=0;i<128;i++)check(y[i]==2*i,"synthetic learned affine identity/bias/row mapping");}
}
struct learned_activation_bank:activation_bank {
    std::array<std::unique_ptr<learned_score_affine>,23> calibration;
    std::vector<float> uncalibrated_scores;
    json auxiliary_manifest;
    std::filesystem::path auxiliary_root;
    static std::vector<float> load(const std::filesystem::path &p,size_t n,const std::string &expected){
        check(std::filesystem::file_size(p)==n*4,"exact auxiliary weight size");
        std::vector<float> out(n);std::ifstream f(p,std::ios::binary);f.read((char*)out.data(),n*4);check(bool(f),"auxiliary short read");
        unsigned char digest[SHA256_DIGEST_LENGTH];SHA256((const unsigned char*)out.data(),n*4,digest);
        std::ostringstream hex;for(unsigned char c:digest)hex<<std::hex<<std::setfill('0')<<std::setw(2)<<(int)c;
        check(hex.str()==expected,"runtime auxiliary weight SHA256");for(float x:out)check(std::isfinite(x),"nonfinite auxiliary weight");return out;
    }
    explicit learned_activation_bank(llama_model *model,const char *path):activation_bank(model),uncalibrated_scores(32*23*128){
        check(path&&*path,"frozen auxiliary root required");auxiliary_root=path;
        std::ifstream f(auxiliary_root/"manifest.json");f>>auxiliary_manifest;check(bool(f),"auxiliary manifest absent");
        const auto &m=auxiliary_manifest;
        check(m.at("schema")=="original-score-affine-calibration-v1"&&m.at("status")=="PASS_FIXED_TRAINING_ONLY_FIT","auxiliary fit identity");
        check(m.at("model_sha256")=="582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"&&m.at("source_horizon")==2&&m.at("CPU_target_layers")==json({2,24}),"original target/auxiliary scope");
        check(m.at("training_rows_per_layer")==1024&&m.at("weights_bytes")==1519104&&m.at("development_used")==false&&m.at("holdout_used")==false,"fixed training-only weights");
        const size_t graphs=23*(ggml_graph_overhead()+32*ggml_tensor_overhead()+65536+learned_score_affine::metadata());
        const size_t capture=(inputs.size()+scores.size()+true_scores.size()+uncalibrated_scores.size()+33ull*vocab)*4;
        check(graphs<=23*1024*1024&&graphs+capture+2*1519104+2*1024*1024<=64*1024*1024,"bounded auxiliary/capture/metadata accounting");
        auto w=load(auxiliary_root/"weight.f32",23*128*128,m.at("sha256").at("weight.f32"));
        auto b=load(auxiliary_root/"bias.f32",23*128,m.at("sha256").at("bias.f32"));
        for(int i=0;i<23;i++)calibration[i]=std::make_unique<learned_score_affine>(w.data()+i*128*128,b.data()+i*128,backend);
    }
    ~learned_activation_bank(){for(auto &p:calibration)p.reset();}
    void observe(runtime &r,ggml_tensor *norm,int source,int call){
        check(call>=1&&call<=32&&source>=0&&source<=22,"learned estimator frozen scope");
        check(norm->op==GGML_OP_MUL&&norm->src[0]&&norm->src[0]->op==GGML_OP_RMS_NORM,"learned early residual dependency");
        auto *raw=norm->src[0]->src[0];check(raw&&raw->type==GGML_TYPE_F32&&raw->ne[0]==2880&&raw->ne[1]==1&&ggml_is_contiguous(raw)&&raw->buffer&&ggml_backend_buffer_is_host(raw->buffer),"learned original residual lifetime/device/shape");
        const auto begin=clock_type::now();const int target=source+2;const size_t row=(call-1)*23+source;
        float *values=inputs.data()+row*2880;ggml_backend_tensor_get(raw,values,0,2880*4);
        for(int i=0;i<2880;i++)check(std::isfinite(values[i]),"nonfinite source residual");
        auto original=estimators[source]->score(values);std::copy(original.begin(),original.end(),uncalibrated_scores.begin()+row*128);
        auto predicted=calibration[source]->score(original.data());std::copy(predicted.begin(),predicted.end(),scores.begin()+row*128);
        std::array<int,128> sorted{};for(int i=0;i<128;i++)sorted[i]=i;
        std::stable_sort(sorted.begin(),sorted.end(),[&](int a,int b){return predicted[a]>predicted[b];});
        record receipt;receipt.call=call;receipt.source=source;receipt.target=target;auto *mgr=r.model->moe_stream();
        {std::lock_guard<std::mutex> lock(mgr->mtx);const auto *sl=mgr->layer(target);
         for(int k=0;k<4;k++){const int expert=sorted[k];auto it=sl->expert_slot.find(expert);const int slot=it==sl->expert_slot.end()?-1:it->second;
             receipt.ids[k]=expert;receipt.slots[k]=slot;receipt.states[k]=slot<0?0:sl->slot_state[slot];receipt.generations[k]=slot<0?0:sl->slot_gen[slot];}}
        check(count<records.size(),"learned receipt bound");receipt.predictor_us=std::chrono::duration<double,std::micro>(clock_type::now()-begin).count();records[count++]=receipt;
    }
};
