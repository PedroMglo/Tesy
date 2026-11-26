// Exercise the real optimized GGML PLT and team on 24 tiny synthetic MMIDs.
#include "ggml-cpu.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>

extern "C" int team_observe_init();
extern "C" int team_observe_add(const ggml_tensor*,int,int);
extern "C" void team_observe_begin(int);
extern "C" int team_observe_end();
extern "C" int team_observe_row(int,int*,int*,int*,int*,int*,int*,int*,int64_t*,int64_t*);
static void require(bool ok,const char *why) {
    if (!ok) { std::fprintf(stderr,"FAIL small MMID: %s\n",why);std::exit(1); }
}
int main() {
    auto *cpu=ggml_backend_cpu_init();
    auto *c=ggml_init({16U<<20,nullptr,true});
    require(cpu && c,"runtime");
    ggml_backend_cpu_set_n_threads(cpu,8);
    auto *g=ggml_new_graph_custom(c,512,false);
    auto *weights=ggml_new_tensor_3d(c,GGML_TYPE_MXFP4,32,32,4);
    auto *x=ggml_new_tensor_3d(c,GGML_TYPE_F32,32,1,32);
    auto *active=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,32);
    auto *parked=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,32);
    require(team_observe_init()==0,"observer ELF/callsites");
    for (int wave=0;wave<8;++wave) for (int role=0;role<3;++role) {
        auto *node=ggml_mul_mat_id(c,weights,x,wave==0?active:parked);
        require(team_observe_add(node,wave,role)==0,"register");
        ggml_build_forward_expand(g,node);
    }
    auto *buf=ggml_backend_alloc_ctx_tensors(c,cpu);
    require(buf,"buffer");
    std::memset(weights->data,0,ggml_nbytes(weights));
    std::memset(x->data,0,ggml_nbytes(x));
    for(int i=0;i<128;++i) {
        static_cast<int32_t*>(active->data)[i]=i%4;
        static_cast<int32_t*>(parked->data)[i]=-1;
    }
    for(int mode: {0,1}) {
        team_observe_begin(mode);
        require(ggml_backend_graph_compute(cpu,g)==GGML_STATUS_SUCCESS,"compute");
        ggml_backend_synchronize(cpu);
        const int rows=team_observe_end();
        require(rows==mode*192,"MMID bounds/coverage");
        std::set<int> tids;
        for(int i=0;i<rows;++i) {
            int wave,role,lane,nth,tid,entry,exit;
            int64_t start,end;
            require(team_observe_row(i,&wave,&role,&lane,&nth,&tid,&entry,&exit,&start,&end)==0 &&
                wave==i/24 && role==(i/8)%3 && lane==i%8 && nth==8 && start<end, "row identity");
            tids.insert(tid);
        }
        require(tids.size()==size_t(mode*8),"team members");
    }
    ggml_backend_buffer_free(buf);ggml_free(c);ggml_backend_free(cpu);
    std::puts("PASS_C269_RESIDENT_TEAM_SYNTHETIC_24X8");
}
