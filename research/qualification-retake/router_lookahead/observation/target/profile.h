// Private context side of the probe. The scheduler invokes both phases on the submitting thread.
#pragma once
#include "lookahead.h"
#include "projector.h"

namespace target_probe __attribute__((visibility("hidden"))) {
constexpr auto data_event=static_cast<pfj::Kind>(35);
constexpr auto get_event=static_cast<pfj::Kind>(36);

inline int buffer_kind(ggml_backend_buffer_t buffer) {
    const char *name=ggml_backend_buffer_name(buffer);
    if (!std::strcmp(name,"CPU")) return 1;
    if (!std::strcmp(name,"CPU_Mapped")) return 2;
    if (!std::strcmp(name,"CUDA0")) return 3;
    if (!std::strcmp(name,"CUDA_Host")) return 4;
    return 0;
}

// Recover exactly the effective buffer that the pinned ggml_backend_tensor_get reads.
inline std::vector<float> read(pfj::Site site, int part, ggml_tensor *t, int n0, int n1) {
    require(t && t->data && t->type==GGML_TYPE_F32 && t->ne[0]==n0 && t->ne[1]==n1 &&
            t->ne[2]==1 && t->ne[3]==1 && ggml_is_contiguous(t), "router probe F32 shape");
    auto buf=t->view_src ? t->view_src->buffer : t->buffer;
    require(buf && buffer_kind(buf), "router probe unknown buffer");
    const size_t bytes=size_t(n0)*n1*sizeof(float);
    require(ggml_nbytes(t)==bytes, "router probe tensor extent");
    std::vector<float> values(bytes/sizeof(float));
    const uint64_t start=pfj::now();
    ggml_backend_tensor_get(t,values.data(),0,bytes);
    const uint64_t end=pfj::now();
    site.component=part;
    pfj::emit(get_event,site,bytes,buffer_kind(buf),ggml_backend_buffer_is_host(buf),start,end);
    return values;
}

struct Session {
    const llama_model& model;
    const llama_ubatch& batch;
    const int outputs;
    ggml_backend_sched_t scheduler;
    ggml_backend_sched_eval_callback previous;
    void *previous_data;
    std::array<bool,35> observed{};
    ggml_tensor *waiting=nullptr;
    bool delegated=false, own=false;
    uint64_t asked=0;

    void observe(ggml_tensor *t,int source,uint64_t entered) {
        require(source>=0 && source<35 && !observed[source],"duplicate router probe");
        observed[source]=true;
        const int target=source+1, n=int(batch.n_tokens);
        auto site=pfj::host; site.layer=target;
        auto executing=ggml_backend_sched_get_tensor_backend(scheduler,t);
        require(executing!=nullptr,"unknown producer backend");
        const char *name=ggml_backend_name(executing);
        int backend=!std::strcmp(name,"CPU") ? 1 : (!std::strcmp(name,"CUDA0") ? 3 : 0);
        require(backend!=0,"unqualified producer backend");
        pfj::emit(data_event,site,source,backend,n,asked,entered);
        lookahead::begin(*model.moe_stream(),target,n*width*4,(2*width+width*experts+experts)*4);
        auto &src=model.layers[source], &dst=model.layers[target];
        auto x=read(site,0,t,width,n);
        auto gamma=read(site,1,src.attn_post_norm,width,1);
        auto next=read(site,2,dst.attn_post_norm,width,1);
        auto w=read(site,3,dst.ffn_gate_inp,width,experts);
        auto b=read(site,4,dst.ffn_gate_inp_b,experts,1);
        const bool half=reduced(target,target==35 ? outputs : n);
        prepare_matrix(w,half);
        for (int i=0; i<n; ++i) {
            if (!selected(batch,outputs,target,i)) continue;
            const auto ranks=project(x.data()+i*width,gamma.data(),next.data(),w.data(),b.data(),half);
            lookahead::publish(*model.moe_stream(),target,i,batch.pos[i],ranks.data());
        }
    }

    static bool callback(ggml_tensor *t,bool ask,void *opaque) {
        auto &s=*static_cast<Session *>(opaque);
        if (ask) {
            s.delegated=s.previous && s.previous(t,true,s.previous_data);
            const int layer=source_layer(t->name);
            s.own=layer>=0 && (layer!=34 || s.outputs>0);
            if (s.own) s.asked=pfj::now();
            s.waiting=(s.own || s.delegated) ? t : nullptr;
            return s.waiting!=nullptr;
        }
        const uint64_t entered=pfj::now();
        if (t!=s.waiting) { pfj::journal->invalid=true; return false; }
        // Preserve the old callback's stop. Never ask it for data it declined.
        if (s.delegated && !s.previous(t,false,s.previous_data)) { pfj::journal->invalid=true; return false; }
        if (s.own) {
            try { s.observe(t,source_layer(t->name),entered); }
            catch (const std::exception &) { pfj::journal->invalid=true; }
        }
        s.waiting=nullptr;
        return true;
    }

    template<class Compute> ggml_status run(Compute compute) {
        if (model.arch!=LLM_ARCH_OPENAI_MOE || model.layers.size()!=36 || !model.moe_stream() ||
                batch.n_tokens==0 || batch.n_tokens>32 || outputs<0 || outputs>int(batch.n_tokens)) {
            pfj::journal->invalid=true;
            return compute();
        }
        lookahead::emit_tile(*model.moe_stream(),batch,outputs);
        if (pfj::journal->invalid.load()) return compute();
        struct Restore {
            Session &s;
            ~Restore() { ggml_backend_sched_set_eval_callback(s.scheduler,s.previous,s.previous_data); }
        } restore{*this};
        ggml_backend_sched_set_eval_callback(scheduler,callback,this);
        auto result=compute();
        for (int i=0;i<35;++i) {
            if (observed[i]!=(i!=34 || outputs>0)) pfj::journal->invalid=true;
        }
        if (waiting) pfj::journal->invalid=true;
        return result;
    }
};
} // namespace target_probe
