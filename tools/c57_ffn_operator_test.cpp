// Synthetic model-free gate/up/down, biases, mask, reduction broadcast test.
#include "ggml.h"
#include "ggml-cpu.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static void need(bool condition,const char *why) {
    if (!condition) {std::fprintf(stderr,"C57_FFN_ERROR %s\n",why);std::exit(2);}
}

static bool trial(ggml_type type,int poison) {
    const ggml_init_params params={64*1024*1024,nullptr,false};
    auto *c=ggml_init(params);need(c,"context");
    constexpr int64_t width=64,experts=4,pairs=4,tokens=2;
    auto *input=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,1,tokens);
    auto *ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,pairs,tokens);
    auto *gate_w=ggml_new_tensor_3d(c,type,width,width,experts);
    auto *up_w=ggml_new_tensor_3d(c,type,width,width,experts);
    auto *down_w=ggml_new_tensor_3d(c,type,width,width,experts);
    auto *gate_b=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,pairs,tokens);
    auto *up_b=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,pairs,tokens);
    auto *down_b=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,pairs,tokens);
    auto *mask=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,pairs,tokens);
    auto *up=ggml_add(c,ggml_mul_mat_id(c,up_w,input,ids),up_b);
    auto *gate=ggml_add(c,ggml_mul_mat_id(c,gate_w,input,ids),gate_b);
    auto *act=ggml_swiglu_oai(c,gate,up,1.702f,7.0f);
    auto *down=ggml_add(c,ggml_mul_mat_id(c,down_w,act,ids),down_b);
    auto *masked=ggml_mul(c,down,mask);
    ggml_tensor *sum=nullptr;
    for(int64_t pair=0;pair<pairs;++pair) {
        auto *view=ggml_view_2d(c,masked,width,tokens,masked->nb[2],pair*masked->nb[1]);
        sum=sum?ggml_add(c,sum,view):view;
    }
    auto *output=ggml_cont(c,sum);
    auto convert=ggml_get_type_traits(type)->from_float_ref;
    need(convert || type==GGML_TYPE_F32,"conversion");
    for(auto *weight:{gate_w,up_w,down_w})
        for(int64_t expert=0;expert<experts;++expert)
            for(int64_t row=0;row<width;++row) {
                std::vector<float> values(width,0.025f*float(expert+1));
                void *dst=(char *)weight->data+expert*weight->nb[2]+row*weight->nb[1];
                if(type==GGML_TYPE_F32)std::memcpy(dst,values.data(),width*sizeof(float));
                else convert(values.data(),dst,width);
            }
    for(int64_t token=0;token<tokens;++token)
        for(int64_t feature=0;feature<width;++feature) {
            auto *row=(float *)((char *)input->data+token*input->nb[2]);
            row[feature]=(feature%16==0)?-0.0f:0.1f*float(token+1);
        }
    const int32_t parked[pairs*tokens]={-1,1,-1,-1,2,-1,3,-1};
    std::memcpy(ids->data,parked,sizeof(parked));
    for(int64_t index=0;index<pairs*tokens;++index)
        for(int64_t feature=0;feature<width;++feature) {
            const int64_t flat=index*width+feature;
            ((float *)gate_b->data)[flat]=0.02f;
            ((float *)up_b->data)[flat]=0.03f;
            ((float *)down_b->data)[flat]=0.04f;
            ((float *)mask->data)[flat]=parked[index]<0?0.0f:1.0f;
        }
    auto *graph=ggml_new_graph(c);ggml_build_forward_expand(graph,output);
    auto plan=ggml_graph_plan(graph,4,nullptr);
    void *scratch=nullptr;
    if(plan.work_size)need(posix_memalign(&scratch,64,plan.work_size)==0,"scratch allocation");
    plan.work_data=(uint8_t *)scratch;
    auto compute=[&]() {
        if(scratch)std::memset(scratch,poison,plan.work_size);
        need(ggml_graph_compute(graph,&plan)==GGML_STATUS_SUCCESS,"compute");
        return std::vector<float>((float *)output->data,(float *)output->data+ggml_nelements(output));
    };
    auto actual=compute();
    for(int64_t index=0;index<pairs*tokens;++index)
        if(((int32_t *)ids->data)[index]<0)((int32_t *)ids->data)[index]=0;
    auto control=compute();
    bool equal=actual.size()==control.size(),finite=true;
    for(size_t i=0;i<actual.size();++i) {
        equal &= std::memcmp(&actual[i],&control[i],sizeof(float))==0;
        finite &= std::isfinite(actual[i]);
    }
    std::printf("C57_FFN type=%s poison=%d equal=%d finite=%d first=%g control=%g\n",
                ggml_type_name(type),poison,int(equal),int(finite),
                double(actual[0]),double(control[0]));
    free(scratch);ggml_free(c);
    return equal && finite;
}

int main(int argc,char **argv) {
    need(argc==2,"--expect-bug or --expect-fixed");
    const bool bug=std::strcmp(argv[1],"--expect-bug")==0;
    need(bug || std::strcmp(argv[1],"--expect-fixed")==0,"mode");
    for(auto type:{GGML_TYPE_MXFP4,GGML_TYPE_F16,GGML_TYPE_F32}) {
        const bool zero=trial(type,0x00),poison=trial(type,0x7f);
        if(bug)need(type==GGML_TYPE_F32 ? (zero && poison):(!zero || !poison),
                    "historical mismatch not reproduced");
        else need(zero && poison,"repaired FFN graph mismatch");
    }
    std::puts(bug?"C57_FFN_BUG_REPRODUCED_MODEL_FREE":"C57_FFN_REPAIR_PASS_MODEL_FREE");
}
