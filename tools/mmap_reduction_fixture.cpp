#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-backend-impl.h"
#include "ggml-cpu.h"
#include <array>
#include <vector>
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
static void req(bool b,const char*s){if(!b)throw std::runtime_error(s);}
static std::vector<float> compute(ggml_backend_t backend,int n,const std::vector<float>&x,const std::vector<float>&w){
 auto*c=ggml_init({1024*1024,nullptr,true});auto*a=ggml_new_tensor_3d(c,GGML_TYPE_F32,32,4,n);auto*b=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,4,n);ggml_set_input(a);ggml_set_input(b);auto*mul=ggml_mul(c,a,b);auto*g=ggml_new_graph(c);ggml_build_forward_expand(g,mul);std::array<ggml_tensor*,4>v;
 for(int e=0;e<4;e++){v[e]=ggml_view_2d(c,mul,32,n,mul->nb[2],e*mul->nb[1]);ggml_build_forward_expand(g,v[e]);}auto*sum=v[0];for(int e=1;e<4;e++){sum=ggml_add(c,sum,v[e]);ggml_build_forward_expand(g,sum);}ggml_set_output(sum);
 auto*s=ggml_backend_sched_new(&backend,nullptr,1,512,false,false);req(ggml_backend_sched_alloc_graph(s,g),"fixture alloc");ggml_backend_tensor_set(a,x.data(),0,x.size()*4);ggml_backend_tensor_set(b,w.data(),0,w.size()*4);req(ggml_backend_sched_graph_compute(s,g)==GGML_STATUS_SUCCESS,"fixture compute");ggml_backend_sched_synchronize(s);std::vector<float>out(32*n);ggml_backend_tensor_get(sum,out.data(),0,out.size()*4);ggml_backend_sched_free(s);ggml_free(c);return out;
}
static void matrix_control(ggml_backend_t cpu,ggml_type type){
 auto*c=ggml_init({1024*1024,nullptr,true});auto*w=ggml_new_tensor_3d(c,type,32,32,8);auto*x=ggml_new_tensor_3d(c,GGML_TYPE_F32,32,1,1);auto*ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,1);auto*y=ggml_mul_mat_id(c,w,x,ids);ggml_set_output(y);auto*g=ggml_new_graph(c);ggml_build_forward_expand(g,y);auto*s=ggml_backend_sched_new(&cpu,nullptr,1,512,false,false);req(ggml_backend_sched_alloc_graph(s,g),"matrix fixture alloc");std::vector<float>weights(32*32*8,1),input(32,1);std::vector<unsigned char>payload(ggml_nbytes(w));
 if(type==GGML_TYPE_MXFP4){ggml_quantize_init(type);req(ggml_quantize_chunk(type,weights.data(),payload.data(),0,32*8,32,nullptr)==payload.size(),"MXFP4 bytes");}
 else {for(size_t i=0;i<weights.size();i++)reinterpret_cast<ggml_fp16_t*>(payload.data())[i]=ggml_fp32_to_fp16(1);}
 int32_t route[4]={0,2,4,7};ggml_backend_tensor_set(w,payload.data(),0,payload.size());ggml_backend_tensor_set(x,input.data(),0,input.size()*4);ggml_backend_tensor_set(ids,route,0,sizeof(route));req(ggml_backend_sched_graph_compute(s,g)==GGML_STATUS_SUCCESS,"matrix compute");std::vector<float>out(128);ggml_backend_tensor_get(y,out.data(),0,out.size()*4);const float expected=type==GGML_TYPE_MXFP4 ? (32.f*127.f)*ggml_fp16_to_fp32(ggml_fp32_to_fp16(1.f/127.f)) : 32.f;for(float a:out)req(a==expected&&std::isfinite(a),"known dot32/Q8_0 contract mismatch");ggml_backend_sched_free(s);ggml_free(c);
}
int main(){try{
 ggml_backend_load_all();auto*cp=ggml_backend_cpu_init();auto*d=ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_GPU);req(d,"GPU missing");auto*gpu=ggml_backend_dev_init(d,nullptr);ggml_backend_cpu_set_n_threads(cp,8);matrix_control(cp,GGML_TYPE_MXFP4);matrix_control(cp,GGML_TYPE_F16);
 size_t diffs=0;for(int n:{1,32}){std::vector<float>x(32*4*n),w(4*n),expected(32*n);uint32_t z=1337;auto rnd=[&](){z^=z<<13;z^=z>>17;z^=z<<5;return (float(int32_t(z%200001)-100000)/997.f);};for(auto&a:x)a=rnd();for(auto&a:w)a=std::fabs(rnd()/100.f);
 for(int t=0;t<n;t++)for(int col=0;col<32;col++){float sum=x[t*128+col]*w[t*4];for(int e=1;e<4;e++)sum=std::fma(x[t*128+e*32+col],w[t*4+e],sum);expected[t*32+col]=sum;}
 auto a=compute(gpu,n,x,w),b=compute(cp,n,x,w);req(std::memcmp(a.data(),expected.data(),a.size()*4)==0,"GPU fused arithmetic differs from independent std::fma oracle");for(size_t i=0;i<a.size();i++){req(std::isfinite(a[i]),"nonfinite");diffs+=std::memcmp(&a[i],&b[i],4)!=0;}}
 req(diffs>0,"negative separate multiply-add control did not discriminate");std::cout<<"{\"GPU_F32_fused_vs_independent_fma\":\"BITWISE_PASS\",\"CPU_separate_vs_GPU_differing_values\":"<<diffs<<",\"MXFP4_CPU_known_dot32\":\"PASS\",\"F16_CPU_known_dot32\":\"PASS\",\"shapes\":[1,32],\"model_weights_loaded\":false}\n";ggml_backend_free(gpu);ggml_backend_free(cp);return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
