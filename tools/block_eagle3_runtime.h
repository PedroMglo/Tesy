#pragma once
// One native A2 boundary probe; reuse the qualified target API/profile unchanged.
#define main block_native_prior_entrypoint
#include "block_native_run.cpp"
#undef main
#include "speculative.h"
#include "llama-ext.h"
#include "common.h"

namespace {
void require_clean_head_tail(int last_position,int start){
    check(start>=0 && last_position<start,"head KV proposed suffix still present before feature processing");
}
struct head_runtime {
    llama_model * model=nullptr;
    llama_context * ctx=nullptr;
    common_speculative * spec=nullptr;
    ~head_runtime(){if(spec)common_speculative_free(spec);if(ctx)llama_free(ctx);if(model)llama_model_free(model);}
    head_runtime(runtime & target,const char * path){
        auto mp=llama_model_default_params();mp.n_gpu_layers=1;mp.use_mmap=false;mp.use_extra_bufts=false;
        model=llama_model_load_from_file(path,mp);check(model,"head model load failed");
        auto cp=llama_context_default_params();cp.n_ctx=8192;cp.n_batch=256;cp.n_ubatch=32;cp.n_seq_max=1;
        cp.n_threads=8;cp.n_threads_batch=8;cp.op_offload=false;
        cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;cp.type_k=GGML_TYPE_F16;cp.type_v=GGML_TYPE_F16;
        cp.offload_kqv=true;cp.kv_unified=true;cp.ctx_other=target.ctx;
        ctx=llama_init_from_model(model,cp);check(ctx,"head context init failed");
        check(llama_get_ctx_other(ctx)==target.ctx,"head sharing target context missing");
        const auto * layers=llama_model_target_layer_ids(model);
        check(llama_model_target_layer_ids_n(model)==3 && layers[0]==2 && layers[1]==18 && layers[2]==33,"head feature layer contract changed");
        common_params_speculative params;params.types={COMMON_SPECULATIVE_TYPE_DRAFT_EAGLE3};
        params.draft.ctx_tgt=target.ctx;params.draft.ctx_dft=ctx;
        params.draft.n_max=7;params.draft.n_min=7;params.draft.p_min=0;params.draft.backend_sampling=false;
        spec=common_speculative_init(params,1);check(spec,"head speculative initialization failed");
    }
};

std::vector<float> target_call(runtime & run,head_runtime * head,const std::vector<llama_token> & ids,int position,bool all,double & processing_s){
    check(!ids.empty() && ids.size()<=256 && position>=0 && position+ids.size()<=8192,"head target call invalid");
    run.rows.expected=all?static_cast<int>(ids.size()):1;run.rows.ffn=run.rows.projection=0;
    llama_batch batch=llama_batch_init(static_cast<int>(ids.size()),0,1);batch.n_tokens=static_cast<int>(ids.size());
    for(int i=0;i<batch.n_tokens;++i){batch.token[i]=ids[i];batch.pos[i]=position+i;batch.n_seq_id[i]=1;batch.seq_id[i][0]=0;batch.logits[i]=all||i==batch.n_tokens-1;}
    const int rc=llama_decode(run.ctx,batch);check(rc==0,"feature target decode failed");llama_synchronize(run.ctx);
    check(run.rows.ffn==run.rows.expected && run.rows.projection==run.rows.expected,"feature full rows missing");
    std::vector<float> out(static_cast<size_t>(run.rows.expected)*vocab);
    for(int i=0;i<run.rows.expected;++i){const auto * row=llama_get_logits_ith(run.ctx,logit_index(all,i));check(row,"feature logit row absent");std::memcpy(out.data()+static_cast<size_t>(i)*vocab,row,vocab*sizeof(float));greedy(row);}
    if(head){const auto begin=clock_type::now();check(common_speculative_process(head->spec,batch),"head feature processing failed");llama_synchronize(head->ctx);processing_s+=std::chrono::duration<double>(clock_type::now()-begin).count();}
    llama_batch_free(batch);return out;
}
}

