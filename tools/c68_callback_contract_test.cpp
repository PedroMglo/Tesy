// Reproduce the GGML scheduler's ask/observe continuation contract without a model.
#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

static void need(bool yes,const char *why) {
    if (!yes) {std::fprintf(stderr,"C68_CALLBACK_ERROR %s\n",why);std::exit(2);}
}

struct observed {bool keep;int ask=0;int deliver=0;};

static bool callback(ggml_tensor *tensor,bool ask,void *arg) {
    auto &state=*static_cast<observed *>(arg);
    if (std::strcmp(tensor->name,"attn_post_norm-1")!=0) return false;
    if (ask) {++state.ask;return true;}
    ++state.deliver;
    return state.keep;
}

static float one(bool keep) {
    const ggml_init_params params={4*1024*1024,nullptr,true};
    auto *ctx=ggml_init(params);need(ctx,"ctx");
    auto *a=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,1);
    auto *b=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,1);
    ggml_set_input(a);ggml_set_input(b);
    auto *middle=ggml_add(ctx,a,b);
    ggml_set_name(middle,"attn_post_norm-1");
    auto *last=ggml_add(ctx,middle,b);
    ggml_set_name(last,"downstream");
    auto *graph=ggml_new_graph(ctx);
    ggml_build_forward_expand(graph,last);
    auto *backend=ggml_backend_cpu_init();need(backend,"CPU backend");
    auto *sched=ggml_backend_sched_new(&backend,nullptr,1,64,false,false);
    need(sched && ggml_backend_sched_alloc_graph(sched,graph),"scheduler allocation");
    const float va=1.0f,vb=2.0f,sentinel=-777.0f;
    ggml_backend_tensor_set(last,&sentinel,0,sizeof(sentinel));
    ggml_backend_tensor_set(a,&va,0,sizeof(va));
    ggml_backend_tensor_set(b,&vb,0,sizeof(vb));
    observed state{keep};
    ggml_backend_sched_set_eval_callback(sched,callback,&state);
    need(ggml_backend_sched_graph_compute(sched,graph)==GGML_STATUS_SUCCESS,"graph compute");
    float actual=0;
    ggml_backend_tensor_get(last,&actual,0,sizeof(actual));
    need(state.ask==1 && state.deliver==1,"callback selection/delivery count");
    ggml_backend_sched_free(sched);ggml_backend_free(backend);ggml_free(ctx);
    return actual;
}

int main() {
    const float cancelled=one(false),continued=one(true);
    std::printf("C68 callback false=%g true=%g\n",double(cancelled),double(continued));
    // The allocator reuses the middle node's storage for the uncomputed last
    // node; 3 is the middle value, while 5 requires the downstream add.
    need(cancelled==3.0f,"false observation did not cancel downstream node");
    need(continued==5.0f,"true observation did not compute downstream node");
    std::puts("C68_CALLBACK_CANCEL_CONTRACT_REPRODUCED_MODEL_FREE");
}
