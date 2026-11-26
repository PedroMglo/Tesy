#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cuda.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace fs = std::filesystem;
constexpr int width = 2880, ranks = 4, slots = 40, n_experts = 128;
constexpr size_t slab = 4406400;
static size_t initial_free;
using tensor = ggml_tensor *;

static void check(bool condition, const std::string &what) {
    if (!condition) throw std::runtime_error(what);
}
template<class T> static std::vector<T> read(const fs::path &f, size_t n) {
    check(fs::file_size(f) == n*sizeof(T), f.string());
    std::ifstream input(f, std::ios::binary);
    std::vector<T> v(n);
    check(bool(input.read(reinterpret_cast<char *>(v.data()), n*sizeof(T))), "input read");
    return v;
}
static void write(const fs::path &path, const void *data, size_t bytes) {
    auto *f = std::fopen(path.c_str(), "wbx");
    check(f != nullptr, "exclusive output");
    bool ok = std::fwrite(data, 1, bytes, f) == bytes;
    check(std::fclose(f) == 0 && ok, "output write");
}
static void checkpoint(const fs::path &dir, const std::string &key) {
    write(dir/(key+".ready"), key.data(), key.size());
    for (int i = 0; i < 1000 && !fs::exists(dir/(key+".ack")); ++i)
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    check(fs::exists(dir/(key+".ack")), "resource handshake " + key);
}
static void observe_memory() {
    size_t free = 0, total = 0;
    ggml_backend_cuda_get_device_memory(0, &free, &total);
    check(free > 0 && total >= free && free + (size_t{1}<<30) >= initial_free, "VRAM cap");
    std::printf("device_memory %zu %zu\n", free, total);
}
struct Context {
    ggml_context *ctx = ggml_init({2<<20, nullptr, true});
    ggml_backend_buffer_t buffer = nullptr;
    Context() { check(ctx, "metadata"); }
    Context(const Context &) = delete;
    void allocate(ggml_backend_t backend) {
        buffer = ggml_backend_alloc_ctx_tensors(ctx, backend);
        check(buffer, "device allocation");
    }
    ~Context() {
        if (buffer) ggml_backend_buffer_free(buffer);
        ggml_free(ctx);
    }
};
struct Bank {
    Context memory;
    std::array<tensor,3> matrices, biases;
    std::array<int,n_experts> slot{};
    const fs::path src;
    const std::vector<int> ids;
    const std::vector<float> x, mix;
    Bank(const fs::path &p, ggml_backend_t gpu) : src(p), ids(read<int>(p/"logical.i32",12)),
        x(read<float>(p/"activation.f32",3*width)), mix(read<float>(p/"mix.f32",12)) {
        for (int k=0; k<3; ++k) {
            matrices[k]=ggml_new_tensor_3d(memory.ctx,GGML_TYPE_MXFP4,width,width,slots);
            biases[k]=ggml_new_tensor_2d(memory.ctx,GGML_TYPE_F32,width,n_experts);
            check(matrices[k]->nb[2] == slab && biases[k]->nb[1]==width*sizeof(float),"expert stride");
        }
        memory.allocate(gpu);
    }
    void place(bool alternate) {
        ggml_backend_buffer_clear(memory.buffer,0);
        const std::set<int> experts(ids.begin(),ids.end());
        check(experts.size()==10 && *experts.begin()>=0 && *experts.rbegin()<n_experts,"routed union");
        const std::array<std::string,3> roles{"gate","up","down"};
        int i=0;
        for (int e: experts) {
            slot[e] = alternate ? slots-1-i : i;
            for (int k=0; k<3; ++k) {
                auto bytes=read<unsigned char>(src/(roles[k]+".weight."+std::to_string(e)),slab);
                auto bias=read<float>(src/(roles[k]+".bias."+std::to_string(e)),width);
                ggml_backend_tensor_set(matrices[k],bytes.data(),slot[e]*slab,slab);
                ggml_backend_tensor_set(biases[k],bias.data(),e*width*sizeof(float),width*sizeof(float));
            }
            ++i;
        }
    }
    void mutate() {
        float value = 0;
        const size_t offset=ids.front()*width*sizeof(float);
        ggml_backend_tensor_get(biases[2],&value,offset,sizeof(value));
        value+=1.0f;
        ggml_backend_tensor_set(biases[2],&value,offset,sizeof(value));
    }
};

static tensor row2(ggml_context *c,tensor v,int i) {
    return ggml_view_2d(c,v,v->ne[0],1,v->nb[1],i*v->nb[1]);
}
static tensor row3(ggml_context *c,tensor v,int i) {
    return ggml_view_3d(c,v,v->ne[0],v->ne[1],1,v->nb[1],v->nb[2],i*v->nb[2]);
}
static tensor join(ggml_context *c,tensor collected,tensor next,int axis) {
    return collected ? ggml_concat(c,collected,next,axis) : next;
}
static tensor activate(ggml_context *c,const Bank &b,tensor x,tensor phys,tensor logical) {
    auto *up=ggml_add_id(c,ggml_mul_mat_id(c,b.matrices[1],x,phys),b.biases[1],logical);
    auto *gate=ggml_add_id(c,ggml_mul_mat_id(c,b.matrices[0],x,phys),b.biases[0],logical);
    return ggml_swiglu_oai(c,gate,up,1.702f,7.0f);
}
static tensor project(ggml_context *c,const Bank &b,tensor h,tensor phys,tensor logical) {
    return ggml_add_id(c,ggml_mul_mat_id(c,b.matrices[2],h,phys),b.biases[2],logical);
}
static tensor reduce(ggml_context *c,ggml_cgraph *g,tensor h,tensor weights) {
    auto *weighted=ggml_mul(c,h,weights);
    ggml_build_forward_expand(g,weighted);
    std::array<tensor,ranks> parts;
    for (int k=0; k<ranks; ++k) {
        parts[k]=ggml_view_2d(c,weighted,width,h->ne[2],weighted->nb[2],k*weighted->nb[1]);
        ggml_build_forward_expand(g,parts[k]);
    }
    auto *sum=parts[0];
    for (int k=1; k<ranks; ++k) {
        sum=ggml_add(c,sum,parts[k]);
        ggml_build_forward_expand(g,sum);
    }
    return sum;
}
static std::vector<float> compute(ggml_backend_t gpu,const Bank &b,int first,int n,char mode) {
    Context mem;
    auto *c=mem.ctx;
    auto *g=ggml_new_graph_custom(c,256,false);
    auto *x=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,1,n);
    auto *rank_array=ggml_new_tensor_2d(c,GGML_TYPE_I32,n_experts,n);
    auto *logical=ggml_view_2d(c,rank_array,ranks,n,rank_array->nb[1],0);
    auto *phys=ggml_new_tensor_2d(c,GGML_TYPE_I32,ranks,n);
    auto *mix=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,ranks,n);
    tensor result=nullptr;
    if (mode=='F') {
        for (int i=0; i<n; ++i) {
            auto *p=row2(c,phys,i), *e=row2(c,logical,i);
            auto *h=activate(c,b,row3(c,x,i),p,e);
            auto *out=reduce(c,g,project(c,b,h,p,e),row3(c,mix,i));
            result=join(c,result,out,1);
        }
    } else {
        tensor h=nullptr, down=nullptr;
        if (mode=='U'||mode=='S') {
            for (int i=0; i<n; ++i)
                h=join(c,h,activate(c,b,row3(c,x,i),row2(c,phys,i),row2(c,logical,i)),2);
        } else {
            h=activate(c,b,x,phys,logical);
        }
        if (mode=='D'||mode=='S') {
            for (int i=0; i<n; ++i)
                down=join(c,down,project(c,b,row3(c,h,i),row2(c,phys,i),row2(c,logical,i)),2);
        } else {
            down=project(c,b,h,phys,logical);
        }
        result=reduce(c,g,down,mix);
    }
    ggml_set_output(result);
    ggml_build_forward_expand(g,result);
    mem.allocate(gpu);
    std::vector<int> logical_table(n_experts*n,-1), physical(ranks*n);
    for (int i=0; i<n; ++i)
        for (int k=0; k<ranks; ++k) {
            int e=b.ids[(first+i)*ranks+k];
            logical_table[i*n_experts+k]=e;
            physical[i*ranks+k]=b.slot[e];
        }
    ggml_backend_tensor_set(x,b.x.data()+first*width,0,n*width*sizeof(float));
    ggml_backend_tensor_set(rank_array,logical_table.data(),0,logical_table.size()*sizeof(int));
    ggml_backend_tensor_set(phys,physical.data(),0,physical.size()*sizeof(int));
    ggml_backend_tensor_set(mix,b.mix.data()+first*ranks,0,n*ranks*sizeof(float));
    observe_memory();
    check(ggml_backend_graph_compute(gpu,g)==GGML_STATUS_SUCCESS,"CUDA graph compute");
    ggml_backend_synchronize(gpu);
    observe_memory();
    check(ggml_is_contiguous(result) && ggml_nbytes(result)==size_t(n)*width*sizeof(float),"result shape");
    std::vector<float> output(n*width);
    ggml_backend_tensor_get(result,output.data(),0,output.size()*sizeof(float));
    return output;
}
int main(int argc,char **argv) try {
    static_assert(sizeof(int)==4 && sizeof(float)==4);
    check(argc==3,"fixture INPUTS NEW-OUTPUT");
    fs::path out(argv[2]);
    check(fs::create_directory(out),"exclusive result");
    check(ggml_backend_cuda_get_device_count()==1,"one GPU");
    size_t total=0;
    ggml_backend_cuda_get_device_memory(0,&initial_free,&total);
    char name[256]{};
    ggml_backend_cuda_get_device_description(0,name,sizeof(name));
    check(std::string(name).find("RTX 4060 Laptop GPU")!=std::string::npos,"target SKU");
    auto gpu=ggml_backend_cuda_init(0);
    check(gpu && ggml_backend_is_cuda(gpu),"CUDA init");
    {
        Bank b(argv[1],gpu);
        b.place(false);
        checkpoint(out,"before");
        for (std::string tag: {"A","B","U","D","S","F","B-alt","F-alt","mutant"}) {
            if (tag=="B-alt") b.place(true);
            if (tag=="mutant") b.mutate();
            std::vector<float> v;
            if (tag=="A") {
                for (int i=0; i<3; ++i) {
                    auto row=compute(gpu,b,i,1,'A');
                    v.insert(v.end(),row.begin(),row.end());
                }
            } else {
                v=compute(gpu,b,0,3,tag=="mutant" ? 'B' : tag[0]);
            }
            write(out/(tag+".f32"),v.data(),v.size()*sizeof(float));
        }
        checkpoint(out,"after");
    }
    ggml_backend_free(gpu);
    return 0;
} catch (const std::exception &e) {
    std::fprintf(stderr,"routed FFN: %s\n",e.what());
    return 1;
}
