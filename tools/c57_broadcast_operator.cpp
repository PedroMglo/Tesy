// Model-free C48 broadcast discriminant; run against old and repaired CPU libs.
#include "ggml.h"
#include "ggml-cpu.h"
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static void need(bool ok,const char *message) {
    if (!ok) { std::fprintf(stderr,"C57_OPERATOR_ERROR %s\n",message);std::exit(2); }
}

static bool one(ggml_type type,int64_t ne11,int poison,int pattern) {
    const ggml_init_params p={32*1024*1024,nullptr,false};
    ggml_context *ctx=ggml_init(p);need(ctx,"context");
    constexpr int64_t k=64,m=16,n_experts=4,n_ids=4,n_tokens=2;
    auto *weights=ggml_new_tensor_3d(ctx,type,k,m,n_experts);
    auto *input=ggml_new_tensor_3d(ctx,GGML_TYPE_F32,k,ne11,n_tokens);
    auto *ids=ggml_new_tensor_2d(ctx,GGML_TYPE_I32,n_ids,n_tokens);
    auto *out=ggml_mul_mat_id(ctx,weights,input,ids);
    auto *convert=ggml_get_type_traits(type)->from_float_ref;
    need(convert!=nullptr || type==GGML_TYPE_F32,"weight conversion");
    for (int64_t expert=0;expert<n_experts;++expert) {
        for (int64_t row=0;row<m;++row) {
            std::vector<float> source(k,float(expert+1)/4);
            void *destination=(char *)weights->data+expert*weights->nb[2]+row*weights->nb[1];
            if (type==GGML_TYPE_F32)std::memcpy(destination,source.data(),k*sizeof(float));
            else convert(source.data(),destination,k);
        }
    }
    for (int64_t token=0;token<n_tokens;++token)
        for (int64_t row=0;row<ne11;++row)
            std::fill_n((float *)((char *)input->data+token*input->nb[2]+row*input->nb[1]),
                        k,float(token+1)*(1+float(row)/8));
    int32_t selected[n_ids*n_tokens]={-1,1,-1,-1,2,-1,-1,-1};
    if (pattern==1) { // first active, later pairs parked
        int32_t replacement[n_ids*n_tokens]={1,-1,-1,-1,2,-1,-1,-1};
        std::memcpy(selected,replacement,sizeof(selected));
    } else if (pattern==2) {
        std::fill_n(selected,n_ids*n_tokens,-1); // no active pairs
    } else if (pattern==3) {
        int32_t replacement[n_ids*n_tokens]={1,2,3,0,2,3,0,1};
        std::memcpy(selected,replacement,sizeof(selected));
    }
    std::memcpy(ids->data,selected,sizeof(selected));
    auto *graph=ggml_new_graph(ctx);ggml_build_forward_expand(graph,out);
    auto plan=ggml_graph_plan(graph,4,nullptr);
    void *work=nullptr;
    if (plan.work_size)need(posix_memalign(&work,64,plan.work_size)==0,"work allocation");
    plan.work_data=(uint8_t *)work;
    auto execute=[&](int value) {
        if (work)std::memset(work,value,plan.work_size);
        need(ggml_graph_compute(graph,&plan)==GGML_STATUS_SUCCESS,"graph compute");
        return std::vector<float>((float *)out->data,(float *)out->data+ggml_nelements(out));
    };
    auto observed=execute(poison);
    for (int64_t index=0;index<n_ids*n_tokens;++index)
        if (((int32_t *)ids->data)[index]<0)
            ((int32_t *)ids->data)[index]=2; // every shared row now converted
    auto control=execute(poison);
    bool equal=true,nonfinite=false,parked_zero=true;
    for (int64_t index=0;index<n_ids*n_tokens;++index) {
        for (int64_t feature=0;feature<m;++feature) {
            const float a=observed[index*m+feature],b=control[index*m+feature];
            if (selected[index]>=0) {
                equal &= std::memcmp(&a,&b,sizeof(float))==0;
                nonfinite |= !__builtin_isfinite(a);
            } else {
                uint32_t bits;
                std::memcpy(&bits,&a,sizeof(bits));
                parked_zero &= bits==0;
            }
        }
    }
    need(parked_zero,"parked output must be +0");
    std::printf("C57_OPERATOR type=%s ne11=%lld poison=%d pattern=%d active_equal=%d active_nonfinite=%d\n",
                ggml_type_name(type),(long long)ne11,poison,pattern,int(equal),int(nonfinite));
    free(work);ggml_free(ctx);
    return equal;
}

int main(int argc,char **argv) {
    need(argc==2,"usage: --expect-bug or --expect-fixed");
    bool bug=std::strcmp(argv[1],"--expect-bug")==0;
    need(bug || std::strcmp(argv[1],"--expect-fixed")==0,"mode");
    for (auto type:{GGML_TYPE_MXFP4,GGML_TYPE_F16,GGML_TYPE_F32}) {
        bool broadcast0=one(type,1,0x00,0);
        bool broadcast7=one(type,1,0x7f,0);
        bool nonbroadcast=one(type,4,0x00,0);
        need(nonbroadcast,"nonbroadcast control mismatch");
        for (int pattern=1;pattern<=3;++pattern)
            for (int poison:{0x00,0x7f})
                need(one(type,1,poison,pattern),"additional broadcast pattern mismatch");
        bool conversion_expected=type!=GGML_TYPE_F32;
        if (bug)need(conversion_expected ? (!broadcast0 || !broadcast7) : (broadcast0 && broadcast7),
                     "historical C48 bug not reproduced as expected");
        else need(broadcast0 && broadcast7,"repaired active output mismatch");
    }
    std::puts(bug?"C57_BROADCAST_BUG_REPRODUCED_MODEL_FREE":"C57_BROADCAST_REPAIR_PASS_MODEL_FREE");
}
