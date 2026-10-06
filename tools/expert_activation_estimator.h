#pragma once
#include "ggml-cpu.h"
#include <array>
#include <memory>
// Auxiliary movement-only estimator: original destination norm/gate/bias
// applied to an earlier CPU residual. It never replaces authoritative routing.
struct activation_estimator {
    ggml_backend_t backend=nullptr;
    ggml_context *ctx=nullptr;
    ggml_backend_buffer_t buffer=nullptr;
    ggml_tensor *input=nullptr,*output=nullptr;
    ggml_cgraph *graph=nullptr;
    activation_estimator(llama_model *model,int target,ggml_backend_t shared_backend):activation_estimator(model->layers.at(target).attn_post_norm,model->layers.at(target).ffn_gate_inp,model->layers.at(target).ffn_gate_inp_b,model->hparams.f_norm_rms_eps,target,shared_backend) {}
    activation_estimator(ggml_tensor *norm,ggml_tensor *gate,ggml_tensor *bias,float eps,int target,ggml_backend_t shared_backend):backend(shared_backend) {
        check(target>=2&&target<=24,"estimator CPU target bound");
        check(norm&&gate&&bias,"destination gate metadata");
        for(auto *t:{norm,gate,bias})check(t->type==GGML_TYPE_F32&&ggml_backend_buffer_is_host(t->buffer),"original CPU gate values/device");
        check(gate->ne[0]==2880&&gate->ne[1]==128,"original gate shape");
        check(backend,"shared estimator CPU backend");
        const size_t meta=ggml_graph_overhead()+32*ggml_tensor_overhead()+65536;
        check(meta<=1024*1024,"auxiliary graph metadata bound");ctx=ggml_init({meta,nullptr,true});check(ctx,"estimator bounded context");
        input=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,2880,1);
        auto *n=ggml_rms_norm(ctx,input,eps);
        n=ggml_mul(ctx,n,norm);
        output=ggml_add(ctx,ggml_mul_mat(ctx,gate,n),bias);ggml_set_output(output);
        graph=ggml_new_graph(ctx);ggml_build_forward_expand(graph,output);
        buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);check(buffer,"estimator buffer allocation");
    }
    ~activation_estimator(){if(buffer)ggml_backend_buffer_free(buffer);if(ctx)ggml_free(ctx);}
    std::array<float,128> score(const float *residual) {
        ggml_backend_tensor_set(input,residual,0,2880*4);
        check(ggml_backend_graph_compute(backend,graph)==GGML_STATUS_SUCCESS,"auxiliary gate compute");ggml_backend_synchronize(backend);
        std::array<float,128> logits{};ggml_backend_tensor_get(output,logits.data(),0,128*4);
        for(float f:logits)check(std::isfinite(f),"nonfinite auxiliary prediction");return logits;
    }
};
struct activation_bank {
    ggml_backend_t backend=nullptr;
    std::array<std::unique_ptr<activation_estimator>,23> estimators;
    std::vector<float> inputs,scores,true_scores;size_t true_count=0;
    std::array<uint8_t,32*23> true_seen{};
    struct record {int call=0,source=0,target=0;std::array<int,4> ids{},slots{},states{};std::array<uint64_t,4> generations{};double predictor_us=0;};
    std::array<record,32*23> records{};size_t count=0;
    explicit activation_bank(llama_model *model):inputs(32*23*2880),scores(32*23*128),true_scores(32*23*128) {
        backend=ggml_backend_cpu_init();check(backend,"auxiliary CPU backend");ggml_backend_cpu_set_n_threads(backend,8);
        for(int i=0;i<23;i++)estimators[i]=std::make_unique<activation_estimator>(model,i+2,backend);
    }
    ~activation_bank(){for(auto &p:estimators)p.reset();if(backend)ggml_backend_free(backend);}
    void label(ggml_tensor *t,int target,int call) {
        check(call>=1&&call<=32&&target>=2&&target<=24,"true gate capture scope");
        check(t->type==GGML_TYPE_F32&&t->ne[0]==128&&t->ne[1]==1&&ggml_is_contiguous(t)&&t->buffer&&ggml_backend_buffer_is_host(t->buffer),"true gate label shape/device");
        const size_t row=(call-1)*23+target-2;check(!true_seen[row],"true gate label duplicate");true_seen[row]=1;true_count++;
        float *out=true_scores.data()+row*128;ggml_backend_tensor_get(t,out,0,128*4);
        for(int i=0;i<128;i++)check(std::isfinite(out[i]),"nonfinite true gate label");
    }
    void observe(runtime &r,ggml_tensor *norm,int source,int call) {
        check(call>=1&&call<=32&&source>=0&&source<=22,"activation capture frozen scope");
        check(norm->op==GGML_OP_MUL&&norm->src[0]&&norm->src[0]->op==GGML_OP_RMS_NORM,"pre-attention raw dependency shape changed");
        auto *raw=norm->src[0]->src[0];check(raw&&raw->type==GGML_TYPE_F32&&raw->ne[0]==2880&&raw->ne[1]==1&&ggml_is_contiguous(raw)&&raw->buffer&&ggml_backend_buffer_is_host(raw->buffer),"raw residual lifetime/host/shape");
        const auto begin=clock_type::now();const int target=source+2;size_t row=(call-1)*23+source;
        float *values=inputs.data()+row*2880;ggml_backend_tensor_get(raw,values,0,2880*4);
        for(int i=0;i<2880;i++)check(std::isfinite(values[i]),"nonfinite source residual");
        auto predicted=estimators[source]->score(values);std::copy(predicted.begin(),predicted.end(),scores.begin()+row*128);
        std::array<int,128> sorted{};for(int i=0;i<128;i++)sorted[i]=i;
        std::stable_sort(sorted.begin(),sorted.end(),[&](int a,int b){return predicted[a]>predicted[b];});
        record receipt;receipt.call=call;receipt.source=source;receipt.target=target;auto *mgr=r.model->moe_stream();
        {std::lock_guard<std::mutex> lock(mgr->mtx);const auto *sl=mgr->layer(target);
         for(int k=0;k<4;k++){const int expert=sorted[k];auto it=sl->expert_slot.find(expert);const int slot=it==sl->expert_slot.end()?-1:it->second;
             receipt.ids[k]=expert;receipt.slots[k]=slot;receipt.states[k]=slot<0?0:sl->slot_state[slot];receipt.generations[k]=slot<0?0:sl->slot_gen[slot];}}
        check(count<records.size(),"predictor receipt bound");receipt.predictor_us=std::chrono::duration<double,std::micro>(clock_type::now()-begin).count();records[count++]=receipt;
    }
};
