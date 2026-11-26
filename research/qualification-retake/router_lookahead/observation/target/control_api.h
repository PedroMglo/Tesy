// Model-free test doubles for the GGML transport only. Real Session and projector run unchanged.
#pragma once
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
struct llama_ubatch { int n_tokens; int *pos,*output; };
using ggml_backend_buffer_t=void *;
using ggml_backend_sched_t=void *;
using ggml_status=int;
constexpr int GGML_TYPE_F32=0, LLM_ARCH_OPENAI_MOE=1;
struct ggml_tensor {
    const char *name; float *data; int ne[4]; int type=0;
    ggml_tensor *view_src=nullptr; void *buffer=this;
};
using ggml_backend_sched_eval_callback=bool(*)(ggml_tensor*,bool,void*);
inline void ggml_backend_sched_set_eval_callback(void*,ggml_backend_sched_eval_callback,void*) {}
inline void *ggml_backend_sched_get_tensor_backend(void*,ggml_tensor *t) {return t->buffer;}
inline const char *ggml_backend_buffer_name(void*) {return "CPU";}
inline const char *ggml_backend_name(void*) {return "CPU";}
inline bool ggml_backend_buffer_is_host(void*) {return true;}
inline bool ggml_is_contiguous(ggml_tensor*) {return true;}
inline std::size_t ggml_nbytes(ggml_tensor *t) {return size_t(t->ne[0])*t->ne[1]*4;}
inline void ggml_backend_tensor_get(ggml_tensor *t,void *p,size_t offset,size_t bytes) {
    assert(offset==0 && bytes==ggml_nbytes(t)); std::memcpy(p,t->data,bytes);
}
struct llama_model {
    struct Layer { ggml_tensor *attn_post_norm,*ffn_gate_inp,*ffn_gate_inp_b; };
    int arch=1; std::array<Layer,36> layers{};
    const llama_model *moe_stream() const {return this;}
};
namespace pfj {
enum Kind:int { };
struct Site { int layer,component; };
inline Site host{};
struct Journal { std::atomic<bool> invalid{false}; };
inline Journal state, *journal=&state;
inline uint64_t now() { static uint64_t clock=0; return ++clock; }
inline int gets=0,data=0;
inline void emit(Kind k,Site,int64_t,int64_t,int64_t,uint64_t begin,uint64_t end) {
    assert(begin<=end);
    if (int(k)==36) ++gets; else if(int(k)==35) ++data; else assert(false);
}
}
namespace lookahead {
inline std::vector<std::array<int,4>> ids;
inline int last_position=-1;
inline void emit_tile(const llama_model&,const llama_ubatch&,int) {}
inline void begin(const llama_model&,int,size_t,size_t) {}
inline void publish(const llama_model&,int,int,int pos,const int *r) {
    ids.push_back({r[0],r[1],r[2],r[3]}); last_position=pos;
}
}
