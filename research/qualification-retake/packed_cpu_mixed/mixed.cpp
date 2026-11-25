// The frozen fixture supplies the sparse MXFP4 payloads and exact scalar reference.
#define main packed_cpu_single_backend_main
#include "../packed_cpu_views/operator.cpp"
#undef main
#include "ggml-cuda.h"
#include <algorithm>

namespace mixed {
using Tensor = ggml_tensor *;
constexpr int score_width = 128;

int selected(int n, int pos, int rank) {
    constexpr std::array<int,4> active{39,0,7,23};
    return n==3 && rank>=2 ? 34+rank : active[(rank+pos)%4];
}

struct Stage {
    Tensor weight{}, input{}, producer{}, mmid{}, sink{};
    uint8_t *address{};
    std::array<unsigned,3> completed{};
};

struct Checkpoint {
    int n;
    ggml_backend_sched_t scheduler;
    ggml_backend_t cpu, gpu;
    ggml_backend_buffer_t weight_buffer;
    ggml_backend_buffer_type_t cuda_buffer;
    Tensor sort{}, ids{};
    std::array<Stage,3> stages{};
    size_t slot_stride;
    unsigned sorts=0;
    std::string error;
    Values unmasked, masked;

    void verify_ids(Tensor t) const {
        check(t->type==GGML_TYPE_I32 && t->ne[0]>=ranks && t->ne[1]==n,"ID geometry");
        std::array<int32_t,ranks> picked{};
        for(int pos=0;pos<n;++pos) {
            ggml_backend_tensor_get(t,picked.data(),pos*t->nb[1],sizeof(picked));
            for(int r=0;r<ranks;++r) check(picked[r]==selected(n,pos,r),"ID transfer");
        }
    }

    void verify_activations(Tensor t,int k) const {
        int channels=k==1?ranks:1;
        check(t->type==GGML_TYPE_F32 && ggml_is_contiguous(t) &&
              t->ne[0]==width && t->ne[1]==channels && t->ne[2]==n,"input geometry");
        Values values(width*channels*n);
        ggml_backend_tensor_get(t,values.data(),0,values.size()*sizeof(float));
        for(int p=0;p<n;++p) for(int r=0;r<channels;++r) for(int c=0;c<width;++c)
            check(values[(p*channels+r)*width+c]==activation(p,r,c),"activation transfer");
    }

    Values verify_values(Tensor t,int k,bool mask) const {
        check(t->type==GGML_TYPE_F32 && ggml_is_contiguous(t) && t->ne[0]==width &&
              t->ne[1]==ranks && t->ne[2]==n,"output geometry");
        Values values(width*ranks*n);
        ggml_backend_tensor_get(t,values.data(),0,values.size()*sizeof(float));
        for(int p=0;p<n;++p) for(int r=0;r<ranks;++r) for(int y=0;y<width;++y) {
            const int s=selected(n,p,r);
            float gold=sign(k,s,y)*activation(p,k==1?r:0,coordinate(k,s,y));
            float value=values[(p*ranks+r)*width+y];
            if (mask && n==3 && r>=2) check(value==0.0f,"parking mask");
            else {
                if(gold==0) gold=0.0f;
                check(std::memcmp(&value,&gold,sizeof(value))==0,"MMID scalar oracle");
            }
        }
        return values;
    }

    bool observe(Tensor t,bool ask) {
        if(t==sort) {
            if(!ask) {
                check(ggml_backend_sched_get_tensor_backend(scheduler,t)==gpu,"argsort not CUDA");
                verify_ids(t);
                ++sorts;
            }
            return true;
        }
        for(int k=0;k<3;++k) {
            Stage &s=stages[k];
            if(t!=s.producer && t!=s.mmid && t!=s.sink) continue;
            if(ask) return true;
            auto assigned=ggml_backend_sched_get_tensor_backend(scheduler,t);
            if(t==s.producer) {
                check(assigned==gpu,"activation producer not CUDA");
                verify_activations(t,k);
                ++s.completed[0];
            } else if(t==s.mmid) {
                Tensor w=t->src[0];
                check(assigned==cpu && t->op==GGML_OP_MUL_MAT_ID && w==s.weight &&
                      w->buffer==weight_buffer && w->data==s.address && w->nb[0]==block &&
                      w->nb[1]==row && w->nb[2]==slot_stride && w->nb[3]==slots*slot_stride &&
                      ggml_backend_buffer_get_usage(w->buffer)==GGML_BACKEND_BUFFER_USAGE_WEIGHTS,
                      "weight moved or MMID not CPU");
                check(t->src[1]!=s.producer && t->src[2]!=ids &&
                      ggml_backend_buffer_is_host(t->src[1]->buffer) &&
                      ggml_backend_buffer_is_host(t->src[2]->buffer),"missing CUDA-to-CPU edges");
                verify_ids(t->src[2]);
                verify_activations(t->src[1],k);
                auto data=verify_values(t,k,false);
                unmasked.insert(unmasked.end(),data.begin(),data.end());
                ++s.completed[1];
            } else {
                check(assigned==gpu && t->src[0]!=s.mmid &&
                      ggml_backend_buffer_get_type(t->src[0]->buffer)==cuda_buffer,
                      "missing CPU-to-CUDA edge");
                verify_values(t->src[0],k,false);
                auto data=verify_values(t,k,true);
                masked.insert(masked.end(),data.begin(),data.end());
                ++s.completed[2];
            }
            return true;
        }
        return false;
    }
};

bool witness(Tensor tensor,bool ask,void *opaque) {
    auto &state=*static_cast<Checkpoint *>(opaque);
    try { return state.observe(tensor,ask); }
    catch(const std::exception &e) { if(state.error.empty()) state.error=e.what(); return true; }
}

struct Outputs { Values unmasked,masked; int splits; };

Outputs graph(ggml_backend_t cpu,ggml_backend_t gpu,int n,bool packed) {
    const size_t capacity=packed ? ((slots*stride + block-1)/block)*block : 3*slots*slab;
    auto buft=ggml_backend_cpu_buffer_type();
    ggml_backend_buffer_ptr memory(ggml_backend_buft_alloc_buffer(buft,capacity+page));
    check(memory && ggml_backend_buffer_get_type(memory.get())==buft,"CPU normal weight buffer");
    ggml_backend_buffer_set_usage(memory.get(),GGML_BACKEND_BUFFER_USAGE_WEIGHTS);
    auto address=reinterpret_cast<uintptr_t>(ggml_backend_buffer_get_base(memory.get()));
    auto *base=reinterpret_cast<uint8_t *>((address+page-1)/page*page);
    ggml_context_ptr ctx(ggml_init({2u<<20,nullptr,true}));
    check(ctx!=nullptr,"context");
    auto *g=ggml_new_graph_custom(ctx.get(),256,false);
    std::array<ggml_backend_t,2> backends{gpu,cpu};
    std::array<ggml_backend_buffer_type_t,2> compute{
        ggml_backend_get_default_buffer_type(gpu),
        ggml_backend_dev_host_buffer_type(ggml_backend_get_device(gpu))};
    check(compute[0] && compute[1] && compute[1]!=buft && ggml_backend_buft_is_host(compute[1]),
          "R0 CPU compute requires GPU host buffer");
    ggml_backend_sched_ptr sched(ggml_backend_sched_new(backends.data(),compute.data(),2,256,false,false));
    check(sched!=nullptr,"scheduler");
    Checkpoint state{n,sched.get(),cpu,gpu,memory.get(),compute[0],nullptr,nullptr,{},
                     packed?stride:slab,0,{}, {}, {}};
    Tensor owner=nullptr;
    if(packed) {
        owner=ggml_new_tensor_1d(ctx.get(),GGML_TYPE_MXFP4,32*(capacity/block));
        check(ggml_backend_tensor_alloc(memory.get(),owner,base)==GGML_STATUS_SUCCESS,"owner");
    }
    auto scores=ggml_new_tensor_2d(ctx.get(),GGML_TYPE_F32,score_width,n);
    ggml_set_input(scores);
    state.ids=ggml_argsort_top_k(ctx.get(),scores,ranks);
    state.sort=state.ids->view_src;
    check(state.sort && state.sort->op==GGML_OP_ARGSORT,"argsort view");
    ggml_backend_sched_set_tensor_backend(sched.get(),state.sort,gpu);
    auto mask=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_F32,1,ranks,n);
    ggml_set_input(mask);
    for(int k=0;k<3;++k) {
        Stage &s=state.stages[k];
        s.address=base+(packed ? k*slab : k*slots*slab);
        for(int slot:{0,7,23,36,37,39}) {
            auto *dst=s.address+slot*state.slot_stride;
            std::memset(dst,0,slab);
            fill(dst,k,slot);
        }
        if(packed) {
            s.weight=ggml_view_3d(ctx.get(),owner,width,width,slots,row,stride,k*slab);
            check(ggml_backend_view_init(s.weight)==GGML_STATUS_SUCCESS,"weight view");
        } else {
            s.weight=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_MXFP4,width,width,slots);
            check(ggml_backend_tensor_alloc(memory.get(),s.weight,s.address)==GGML_STATUS_SUCCESS,
                  "dense weight");
        }
        check(s.address + ggml_nbytes(s.weight) <= base + capacity &&
              ggml_is_contiguous(s.weight)==!packed,"weight span");
        s.input=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_F32,width,k==1?ranks:1,n);
        ggml_set_input(s.input);
        s.producer=ggml_scale(ctx.get(),s.input,1.0f);
        ggml_backend_sched_set_tensor_backend(sched.get(),s.producer,gpu);
        s.mmid=ggml_mul_mat_id(ctx.get(),s.weight,s.producer,state.ids);
        s.sink=ggml_mul(ctx.get(),s.mmid,mask);
        ggml_backend_sched_set_tensor_backend(sched.get(),s.sink,gpu);
        ggml_set_output(s.sink);
        ggml_build_forward_expand(g,s.sink);
    }
    ggml_backend_sched_set_eval_callback(sched.get(),witness,&state);
    check(ggml_backend_sched_alloc_graph(sched.get(),g),"split allocation");
    const int splits=ggml_backend_sched_get_n_splits(sched.get());
    check(splits>=3 && ggml_backend_sched_get_n_backends(sched.get())==2 &&
          ggml_backend_sched_get_n_copies(sched.get())==1,"scheduler topology");
    for(auto &s:state.stages)
        check(ggml_backend_sched_get_tensor_backend(sched.get(),s.mmid)==cpu &&
              s.mmid->src[0]==s.weight,"MMID placement or copied weight at split");
    Values scores_in(score_width*n,-100.0f),masks;
    for(int p=0;p<n;++p) for(int r=0;r<ranks;++r) {
        scores_in[score_width*p+selected(n,p,r)]=100.0f-r;
        masks.push_back(n==3 && r>=2 ? 0.0f : 1.0f);
    }
    ggml_backend_tensor_set(scores,scores_in.data(),0,scores_in.size()*sizeof(float));
    ggml_backend_tensor_set(mask,masks.data(),0,masks.size()*sizeof(float));
    for(int k=0;k<3;++k) {
        Values input;
        for(int p=0;p<n;++p) for(int r=0;r<(k==1?ranks:1);++r) for(int c=0;c<width;++c)
            input.push_back(activation(p,r,c));
        ggml_backend_tensor_set(state.stages[k].input,input.data(),0,input.size()*sizeof(float));
    }
    check(ggml_backend_sched_graph_compute(sched.get(),g)==GGML_STATUS_SUCCESS,"graph compute");
    ggml_backend_sched_synchronize(sched.get());
    if(!state.error.empty()) throw std::runtime_error(state.error);
    check(state.sorts==1,"missing CUDA argsort");
    for(auto &s:state.stages) check(s.completed==std::array<unsigned,3>{1,1,1},"missing split node");
    return {std::move(state.unmasked),std::move(state.masked),splits};
}

bool equal(const Values &a,const Values &b) {
    return a.size()==b.size() && std::memcmp(a.data(),b.data(),a.size()*sizeof(float))==0;
}
} // namespace mixed

int main(int argc,char **argv) try {
    check(argc==2 && std::filesystem::is_directory(argv[1]) && std::filesystem::is_empty(argv[1]),
          "expected an empty output directory");
    check(ggml_backend_cuda_get_device_count()==1,"expected a single CUDA device");
    ggml_backend_ptr cpu(ggml_backend_cpu_init()), gpu(ggml_backend_cuda_init(0));
    check(cpu && gpu && ggml_backend_is_cuda(gpu.get()),"mixed backends");
    ggml_backend_cpu_set_n_threads(cpu.get(),2);
    auto dir=std::filesystem::path(argv[1]);
    for(int n:{1,32,3}) {
        auto a=mixed::graph(cpu.get(),gpu.get(),n,false);
        auto b=mixed::graph(cpu.get(),gpu.get(),n,true);
        check(mixed::equal(a.unmasked,b.unmasked) && mixed::equal(a.masked,b.masked),
              "dense versus packed bits");
        check(b.masked.size()==size_t(3*n*ranks*width) && b.masked.size()==b.unmasked.size(),
              "incomplete checkpoint");
        std::ofstream output(dir/(std::to_string(n)+".f32"),std::ios::binary);
        output.exceptions(std::ios::failbit|std::ios::badbit);
        for(const auto *v:{&b.unmasked,&b.masked})
            output.write(reinterpret_cast<const char *>(v->data()),v->size()*sizeof(float));
        output.close();
        std::cout << "PASS " << n << ' ' << a.splits << ' ' << b.splits << ' '
                  << b.masked.size() << '\n';
    }
    std::ofstream providers(dir/"providers.txt");
    providers.exceptions(std::ios::failbit|std::ios::badbit);
    providers << provider(reinterpret_cast<void *>(&ggml_backend_cpu_init)) << '\n'
              << provider(reinterpret_cast<void *>(&ggml_backend_sched_graph_compute)) << '\n'
              << provider(reinterpret_cast<void *>(&ggml_backend_cuda_init)) << '\n';
    providers.close();
    return 0;
} catch(const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
}
