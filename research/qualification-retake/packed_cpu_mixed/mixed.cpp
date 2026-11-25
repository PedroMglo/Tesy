// The frozen fixture supplies the sparse MXFP4 payloads and exact scalar reference.
#define main packed_cpu_single_backend_main
#include "../packed_cpu_views/operator.cpp"
#undef main
#include "ggml-cuda.h"
#include <algorithm>
#include <openssl/sha.h>
#include <sstream>

namespace mixed {
using Tensor = ggml_tensor *;
constexpr int score_width = 128;
std::string sha(const Values &v) {
    unsigned char h[SHA256_DIGEST_LENGTH];
    check(SHA256(reinterpret_cast<const unsigned char*>(v.data()), v.size()*sizeof(float), h)!=nullptr,
          "SHA256");
    std::string hex;
    constexpr char digits[] = "0123456789abcdef";
    for (auto b:h) { hex.push_back(digits[b>>4]); hex.push_back(digits[b&15]); }
    return hex;
}
uint32_t bits(float v) { uint32_t out; std::memcpy(&out,&v,sizeof(out)); return out; }

int selected(int n, int pos, int rank) {
    constexpr std::array<int,4> active{39,0,7,23};
    return n==3 && rank>=2 ? 34+rank : active[(rank+pos)%4];
}

struct Stage {
    Tensor weight{}, input{}, producer{}, mmid{}, sink{};
    uint8_t *address{};
    std::array<unsigned,3> completed{};
    Values pre;
    std::string cpu_sha, mask_sha;
    ggml_backend_buffer_t pre_buffer{}, out_buffer{};
    void *pre_address{}, *out_address{};
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
    const char *layout;
    std::ostream &journal;
    int component=-1;
    const char *phase="init";

    std::string context() const {
        return "n="+std::to_string(n)+" layout="+layout+" phase="+phase+" k="+std::to_string(component);
    }
    void mismatch(int p,int r,int y,uint32_t expected,uint32_t actual) const {
        std::ostringstream out;
        out << context() << " pos="<<p<<" rank="<<r<<" row="<<y
            <<" expected_bits="<<expected<<" observed_bits="<<actual;
        throw std::runtime_error(out.str());
    }
    void verify_ids(Tensor t) const {
        check(t->type==GGML_TYPE_I32 && t->ne[0]>=ranks && t->ne[1]==n,"ID geometry");
        std::array<int32_t,ranks> picked{};
        for(int pos=0;pos<n;++pos) {
            ggml_backend_tensor_get(t,picked.data(),pos*t->nb[1],sizeof(picked));
            for(int r=0;r<ranks;++r) if(picked[r]!=selected(n,pos,r))
                mismatch(pos,r,0,selected(n,pos,r),picked[r]);
        }
    }

    void verify_activations(Tensor t,int k) const {
        int channels=k==1?ranks:1;
        check(t->type==GGML_TYPE_F32 && ggml_is_contiguous(t) &&
              t->ne[0]==width && t->ne[1]==channels && t->ne[2]==n,"input geometry");
        Values values(width*channels*n);
        ggml_backend_tensor_get(t,values.data(),0,values.size()*sizeof(float));
        for(int p=0;p<n;++p) for(int r=0;r<channels;++r) for(int c=0;c<width;++c)
            if(bits(values[(p*channels+r)*width+c])!=bits(activation(p,r,c)))
                mismatch(p,r,c,bits(activation(p,r,c)),bits(values[(p*channels+r)*width+c]));
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
            if (mask && n==3 && r>=2) {
                if(value!=0.0f) mismatch(p,r,y,bits(0.0f),bits(value));
            }
            else {
                if(gold==0) gold=0.0f;
                if(bits(value)!=bits(gold)) mismatch(p,r,y,bits(gold),bits(value));
            }
        }
        return values;
    }

    bool observe(Tensor t,bool ask) {
        if(t==sort) {
            if(!ask) {
                component=-1; phase="argsort";
                check(ggml_backend_sched_get_tensor_backend(scheduler,t)==gpu,"argsort not CUDA");
                verify_ids(t);
                ++sorts;
            }
            return true;
        }
        for(int k=0;k<3;++k) {
            Stage &s=stages[k];
            if(t!=s.producer && t!=s.mmid && t!=s.sink) continue;
            component=k;
            if(ask) {
                if(t==s.sink) {
                    // Scheduler submitted ALL split input copies before asking about this node.
                    // Do not sample the output here: its kernel has not run.
                    phase="cuda_copy_before_mul";
                    ggml_backend_synchronize(gpu);
                    Tensor src=t->src[0], mask=t->src[1];
                    check(s.pre.empty() && s.completed[1]==1 && t->op==GGML_OP_MUL &&
                          src!=s.mmid && ggml_backend_buffer_get_type(src->buffer)==cuda_buffer,
                          "unordered or absent input copy");
                    s.pre=verify_values(src,k,false);
                    check(sha(s.pre)==s.cpu_sha,"GPU copy differs from CPU result");
                    s.pre_buffer=src->buffer; s.out_buffer=t->buffer;
                    s.pre_address=src->data; s.out_address=t->data;
                    phase="mask_before_mul";
                    check(mask->type==GGML_TYPE_F32 && ggml_is_contiguous(mask) && mask->ne[0]==1 &&
                          mask->ne[1]==ranks && mask->ne[2]==n,"mask geometry");
                    Values mask_values(ranks*n);
                    ggml_backend_tensor_get(mask,mask_values.data(),0,mask_values.size()*sizeof(float));
                    for(int p=0;p<n;++p) for(int r=0;r<ranks;++r) {
                        float want=n==3 && r>=2 ? 0.0f : 1.0f;
                        if(bits(mask_values[p*ranks+r])!=bits(want))
                            mismatch(p,r,0,bits(want),bits(mask_values[p*ranks+r]));
                    }
                    s.mask_sha=sha(mask_values);
                }
                return true;
            }
            auto assigned=ggml_backend_sched_get_tensor_backend(scheduler,t);
            if(t==s.producer) {
                phase="cuda_activation_output";
                check(assigned==gpu,"activation producer not CUDA");
                verify_activations(t,k);
                ++s.completed[0];
            } else if(t==s.mmid) {
                phase="cpu_mmid_weight";
                Tensor w=t->src[0];
                check(assigned==cpu && t->op==GGML_OP_MUL_MAT_ID && w==s.weight &&
                      w->buffer==weight_buffer && w->data==s.address && w->nb[0]==block &&
                      w->nb[1]==row && w->nb[2]==slot_stride && w->nb[3]==slots*slot_stride &&
                      ggml_backend_buffer_get_usage(w->buffer)==GGML_BACKEND_BUFFER_USAGE_WEIGHTS,
                      "weight moved or MMID not CPU");
                check(t->src[1]!=s.producer && t->src[2]!=ids &&
                      ggml_backend_buffer_is_host(t->src[1]->buffer) &&
                      ggml_backend_buffer_is_host(t->src[2]->buffer),"missing CUDA-to-CPU edges");
                phase="cpu_mmid_ids"; verify_ids(t->src[2]);
                phase="cpu_mmid_input"; verify_activations(t->src[1],k);
                phase="cpu_mmid_output";
                auto data=verify_values(t,k,false);
                s.cpu_sha=sha(data);
                unmasked.insert(unmasked.end(),data.begin(),data.end());
                ++s.completed[1];
            } else {
                phase="cuda_masked_output";
                check(assigned==gpu && t->src[0]!=s.mmid &&
                      ggml_backend_buffer_get_type(t->src[0]->buffer)==cuda_buffer,
                      "missing CPU-to-CUDA edge");
                auto data=verify_values(t,k,true);
                auto *src=t->src[0];
                check(s.pre.size()==data.size() && s.pre_buffer==src->buffer && s.out_buffer==t->buffer &&
                      s.pre_address==src->data && s.out_address==t->data,"changed view identity");
                const bool same_buffer=src->buffer==t->buffer, same_address=src->data==t->data;
                phase="v2_diagnostic_post_operand";
                Values late(data.size());
                ggml_backend_tensor_get(src,late.data(),0,late.size()*sizeof(float));
                size_t different=0, outside=0; int first=-1; uint32_t was=0,now=0;
                for(size_t i=0;i<late.size();++i) {
                    if(bits(late[i])!=bits(s.pre[i])) {
                        if(first<0) { first=int(i); was=bits(s.pre[i]); now=bits(late[i]); }
                        ++different;
                        if(n!=3 || (i/width)%ranks<2) ++outside;
                    }
                }
                check(!same_address || std::memcmp(late.data(),data.data(),late.size()*sizeof(float))==0,
                      "observed same address but divergent masked values");
                journal<<layout<<' '<<n<<' '<<k<<' '<<same_buffer<<' '<<same_address<<' '
                       <<s.cpu_sha<<' '<<sha(s.pre)<<' '<<s.mask_sha<<' '<<sha(late)<<' '<<sha(data)
                       <<' '<<different<<' '<<outside<<' '<<first<<' '<<was<<' '<<now<<std::endl;
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
    if(!state.error.empty()) return !ask;
    try { return state.observe(tensor,ask); }
    catch(const std::exception &e) { state.error=state.context()+": "+e.what(); return true; }
}

struct Outputs { Values unmasked,masked; int splits; };

Outputs graph(ggml_backend_t cpu,ggml_backend_t gpu,int n,bool packed,std::ostream &journal) {
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
                     packed?stride:slab,0,{}, {}, {},packed?"packed":"dense",journal};
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
    std::ofstream journal(dir/"boundary.tsv");
    journal.exceptions(std::ios::failbit|std::ios::badbit);
    for(int n:{1,32,3}) {
        auto a=mixed::graph(cpu.get(),gpu.get(),n,false,journal);
        auto b=mixed::graph(cpu.get(),gpu.get(),n,true,journal);
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
              << provider(reinterpret_cast<void *>(&ggml_backend_cuda_init)) << '\n'
              << provider(reinterpret_cast<void *>(&SHA256)) << '\n';
    providers.close();
    return 0;
} catch(const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
}
