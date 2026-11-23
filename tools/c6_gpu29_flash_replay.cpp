#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cuda.h"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

static void require(bool ok,const std::string & reason) {
    if (!ok) throw std::runtime_error(reason);
}

static std::vector<uint8_t> read_exact(const std::string & path,size_t expected) {
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    require(bool(f),"missing replay source: "+path);
    require(static_cast<size_t>(f.tellg())==expected,"replay source byte count changed: "+path);
    std::vector<uint8_t> data(expected);
    f.seekg(0);
    f.read(reinterpret_cast<char *>(data.data()),static_cast<std::streamsize>(expected));
    require(bool(f),"short replay source read: "+path);
    return data;
}

static void write_new(const std::string & path,const void * data,size_t n) {
    const int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    require(fd>=0,"output exists or cannot be created: "+path);
    const auto * p=static_cast<const uint8_t *>(data);
    while (n) {
        const auto wrote=write(fd,p,n);
        if (wrote<=0) { close(fd); throw std::runtime_error("replay output write failed"); }
        p+=wrote; n-=static_cast<size_t>(wrote);
    }
    require(close(fd)==0,"replay output close failed");
}

int main(int argc,char ** argv) {
    if (argc!=4) {
        std::cerr<<"usage: c6_gpu29_flash_replay A32|C64|C32second normal OUTPUT.f32\n";
        return 2;
    }
    try {
        const std::string arm=argv[1], mode=argv[2], output=argv[3];
        require(arm=="A32" || arm=="C64" || arm=="C32second","unknown replay input arm");
        require(mode=="normal","unknown native GPU mode");
        const int n=arm=="C64" ? 64 : 32;
        const int source_n=arm=="A32" ? 32 : 64;
        const std::string root=arm=="A32" ?
            "results/c6-d2diag-gpu29src-aplus32-on01.raw/" :
            "results/c6-d2diag-gpu29src-c64-on01.raw/";
        auto q=read_exact(root+"flash_src_q.bin",static_cast<size_t>(source_n)*4096*4);
        auto k=read_exact(root+"flash_src_k.bin",64*8*256*2);
        auto v=read_exact(root+"flash_src_v.bin",64*8*256*2);
        auto mask=read_exact(root+"flash_src_mask.bin",static_cast<size_t>(source_n)*256*2);
        auto sinks=read_exact(root+"flash_src_sinks.bin",64*4);

        ggml_init_params init={};
        init.mem_size=4u*1024u*1024u;
        init.no_alloc=true;
        ggml_context * ctx=ggml_init(init);
        require(ctx!=nullptr,"native GGML context allocation failed");
        ggml_tensor * q_base=ggml_new_tensor_3d(ctx,GGML_TYPE_F32,64,64,n);
        ggml_tensor * k_base=ggml_new_tensor_3d(ctx,GGML_TYPE_F16,64,8,256);
        ggml_tensor * v_base=ggml_new_tensor_3d(ctx,GGML_TYPE_F16,64,8,256);
        ggml_tensor * m=ggml_new_tensor_2d(ctx,GGML_TYPE_F16,256,n);
        ggml_tensor * s=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,64);
        ggml_tensor * q_native=ggml_permute(ctx,q_base,0,2,1,3);
        ggml_tensor * k_native=ggml_permute(ctx,k_base,0,2,1,3);
        ggml_tensor * v_native=ggml_permute(ctx,v_base,0,2,1,3);
        require(q_native->ne[0]==64 && q_native->ne[1]==n && q_native->ne[2]==64 &&
                k_native->ne[0]==64 && k_native->ne[1]==256 && k_native->ne[2]==8 &&
                v_native->ne[0]==64 && v_native->ne[1]==256 && v_native->ne[2]==8,
                "native replay source shape changed");
        auto * flash=ggml_flash_attn_ext(ctx,q_native,k_native,v_native,m,0.125f,0.0f,0.0f);
        require(flash!=nullptr,"native Flash Attention graph creation failed");
        ggml_flash_attn_ext_add_sinks(flash,s);
        ggml_flash_attn_ext_set_prec(flash,GGML_PREC_F32);
        auto * graph=ggml_new_graph_custom(ctx,256,false);
        ggml_build_forward_expand(graph,flash);
        auto * backend=ggml_backend_cuda_init(0);
        require(backend!=nullptr,"native CUDA backend unavailable");
        auto * buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);
        require(buffer!=nullptr,"native CPU tensor allocation failed");
        const size_t query_offset=arm=="C32second" ? static_cast<size_t>(32)*4096*4 : 0;
        ggml_backend_tensor_set(q_base,q.data()+query_offset,0,static_cast<size_t>(n)*4096*4);
        ggml_backend_tensor_set(k_base,k.data(),0,k.size());
        ggml_backend_tensor_set(v_base,v.data(),0,v.size());
        const size_t mask_offset=arm=="C32second" ? static_cast<size_t>(32)*256*2 : 0;
        ggml_backend_tensor_set(m,mask.data()+mask_offset,0,static_cast<size_t>(n)*256*2);
        ggml_backend_tensor_set(s,sinks.data(),0,sinks.size());
        require(ggml_backend_graph_compute(backend,graph)==GGML_STATUS_SUCCESS,
                "native Flash Attention compute failed");
        std::vector<float> result(static_cast<size_t>(n)*4096);
        require(ggml_nbytes(flash)==result.size()*sizeof(float),"native output size changed");
        ggml_backend_tensor_get(flash,result.data(),0,result.size()*sizeof(float));
        for (float x:result) require(std::isfinite(x),"non-finite native replay result");
        write_new(output,result.data(),result.size()*sizeof(float));
        std::cout<<"C6_GPU29_NATIVE_REPLAY input="<<arm<<" mode="<<mode
                 <<" n_queries="<<n<<" n_keys=256 dtype_q=f32 dtype_kv=f16"
                 <<" mask=f16 sinks=f32 device=CUDA0 scale=0.125 max_bias=0"
                 <<" logit_softcap=0 output_f32="<<result.size()<<'\n';
        ggml_backend_buffer_free(buffer);
        ggml_backend_free(backend);
        ggml_free(ctx);
        return 0;
    } catch (const std::exception & error) {
        std::cerr<<"C6_GPU29_NATIVE_REPLAY_FAIL: "<<error.what()<<'\n';
        return 1;
    }
}
