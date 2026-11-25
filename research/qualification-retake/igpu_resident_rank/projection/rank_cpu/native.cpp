// The included graph and its original observer are unmodified.
#include "ggml-backend.h"
static void install_rank_observer(ggml_backend_sched_t, ggml_backend_sched_eval_callback, void *);
#define ggml_backend_sched_set_eval_callback install_rank_observer
#define main original_main
#include "decode.cpp"
#undef main
#undef ggml_backend_sched_set_eval_callback

extern "C" void quantize_row_q8_0(const float *, void *, int64_t);

namespace {
constexpr int ranks=4;
constexpr const char * names[]={"gate","up","down"};
const std::string x_hash="f4b7b1fc1595244c263e292a8cd2d6c1d3c939e00b56e151c5c5d48fc403092e";
std::array<ggml_tensor*,3> projections{}, biases{};
ggml_tensor *activation=nullptr, *weighted=nullptr;
std::map<std::string,F> values;
int additions=0, reduction_proofs=0;

bool shape(const ggml_tensor *t, ggml_type type, int n0, int n1, int n2=1) {
    return t && t->type==type && t->ne[0]==n0 && t->ne[1]==n1 && t->ne[2]==n2 && t->ne[3]==1;
}

F &capture_row(ggml_tensor *node,const std::string &name) {
    need(shape(node,GGML_TYPE_F32,width,ranks) && node->nb[1]==width*sizeof(float),"rank-major F32");
    auto inserted=values.emplace(name,get<float>(node));
    need(inserted.second,"duplicate stage");
    auto &v=inserted.first->second;
    need(std::all_of(v.begin(),v.end(),[](float a){return std::isfinite(a);}),"nonfinite rank");
    return v;
}

int role(ggml_tensor *tensor, int first) {
    for (int i=0;i<3;++i) if(tensor==state.tensors[first+i]) return i;
    throw std::runtime_error("unknown weight/bias operand");
}

void verify_binding(Witness &w) {
    equal(get<int>(w.ids),I(keys.begin(),keys.end()));
    equal(get<int>(w.remap),I(dest.begin(),dest.end()));
    std::lock_guard<std::mutex> guard(state.mgr->mtx);
    auto &l=*state.mgr->layer(0);
    for (int r=0;r<ranks;++r)
        need(l.slot_expert[dest[r]]==keys[r] && l.slot_gen[dest[r]]==gens[r] &&
             l.slot_state[dest[r]]==LLAMA_MOE_STREAM_SLOT_RESIDENT,"generation at projection");
}

void verify_reduction(ggml_tensor *final) {
    // Inspect the final graph's actual edges. This walk does not request another graph split.
    need(++reduction_proofs==1 && weighted,"single four-rank output");
    auto view=[&](ggml_tensor *v,int rank) {
        need(v && v->op==GGML_OP_VIEW && v->view_src==weighted && v->src[0]==weighted &&
             v->view_offs==size_t(rank)*weighted->nb[1] && shape(v,GGML_TYPE_F32,width,1),
             "ordered reduction view");
    };
    auto *sum=final;
    for(int r=ranks-1;r>=1;--r) {
        need(sum && sum->op==GGML_OP_ADD,"left-associated reduction ADD");
        view(sum->src[1],r);
        sum=sum->src[0];
    }
    view(sum,0);
}

bool observe_ranks(ggml_tensor *node,bool ask,void *opaque) {
    auto &w=*static_cast<Witness*>(opaque);
    const bool original=observe(node,ask,opaque);
    const bool extra=node->op==GGML_OP_GLU || node->op==GGML_OP_MUL;
    if(ask) {
        if(node->op==GGML_OP_ADD && (node->flags&GGML_TENSOR_FLAG_OUTPUT)) verify_reduction(node);
        return original || extra;
    }
    if(!original && !extra) return false;
    need(ggml_backend_sched_get_tensor_backend(w.sched,node)==w.cpu,"CPU execution");
    if(node->op==GGML_OP_MUL_MAT_ID) {
        const int i=role(node->src[0],0);
        need(!projections[i] && node->src[2]==w.remap &&
             shape(node->src[0],GGML_TYPE_MXFP4,width,width,40) &&
             node->src[0]->nb[1]==1530 && node->src[0]->nb[2]==window,"MMID operands");
        verify_binding(w);
        if(i==2) {
            need(activation && node->src[1]==activation,"down consumes SwiGLU");
        } else {
            auto src=get<float>(node->src[1]);
            need(shape(node->src[1],GGML_TYPE_F32,width,1) &&
                 digest(src.data(),src.size()*sizeof(float))==x_hash,"C270 activation");
        }
        projections[i]=node;
        capture_row(node,names[i]);
    } else if(node->op==GGML_OP_ADD_ID) {
        const int i=role(node->src[1],3);
        need(projections[i] && node->src[0]==projections[i] && !biases[i] && node->src[2]==w.ids &&
             shape(node->src[1],GGML_TYPE_F32,width,128),"logical bias consumer");
        biases[i]=node;
        const F &unbiased=values.at(names[i]);
        const F &biased=capture_row(node,std::string(names[i])+"-biased");
        F bias(width);
        for(int r=0;r<ranks;++r) {
            ggml_backend_tensor_get(node->src[1],bias.data(),keys[r]*node->src[1]->nb[1],width*4);
            for(int j=0;j<width;++j) {
                const int k=r*width+j;
                float expected=unbiased[k]+bias[j];
                need(!std::memcmp(&expected,&biased[k],sizeof(float)),"ADD_ID result versus expert bias");
                ++additions;
            }
        }
    } else if(node->op==GGML_OP_GLU) {
        need(!activation && biases[0] && biases[1] && node->src[0]==biases[0] &&
             node->src[1]==biases[1] && ggml_get_glu_op(node)==GGML_GLU_OP_SWIGLU_OAI,
             "gate/up to SwiGLU");
        activation=node;
        capture_row(node,"swiglu");
    } else if(node->op==GGML_OP_MUL) {
        need(!weighted && biases[2] && node->src[0]==biases[2] &&
             shape(node->src[1],GGML_TYPE_F32,1,ranks),"down-biased times router weights");
        weighted=node;
        capture_row(node,"weighted");
        values.emplace("mix",get<float>(node->src[1]));
    }
    return true;
}

template<class T> void save(const fs::path &out,const std::string &name,const std::vector<T> &v,json &files) {
    std::ofstream stream(out/name,std::ios::binary);
    const auto bytes=v.size()*sizeof(T);
    need(bool(stream.write(reinterpret_cast<const char*>(v.data()),bytes)),"output write");
    stream.close();need(bool(stream),"output close");
    files[name]=digest(v.data(),bytes);
}

void finish_capture(const fs::path &out) {
    need(values.size()==9 && reduction_proofs==1 && additions==3*ranks*width,"stage and bias coverage");
    json files;
    for(const auto &pair:values) save(out,pair.first+".f32",pair.second,files);
    std::vector<uint8_t> q8(ggml_row_size(GGML_TYPE_Q8_0,width));
    need(q8.size()==3060,"down input row");
    quantize_row_q8_0(values.at("swiglu").data(),q8.data(),width);
    save(out,"down-rank0.q8",q8,files);
    json proof={{"status","PASS_CPU0_RANK_STAGES_CAPTURE"},{"shape",{width,ranks,1,1}},
        {"logical",keys},{"physical",dest},{"generations",gens},
        {"mmid_edges",3},{"bias_edges",3},{"glu_edges",1},{"weighted_edges",1},
        {"reduction_views",4},{"reduction_adds",3},{"biased_values_checked",additions},
        {"files_sha256",files},{"provider_cpu",provider(reinterpret_cast<void*>(&quantize_row_q8_0))},
        {"provider_base",provider(reinterpret_cast<void*>(&ggml_backend_tensor_get))}};
    std::ofstream f(out/"rank.json");
    f<<proof.dump()<<'\n';f.close();need(bool(f),"rank proof");
}
}

static void install_rank_observer(ggml_backend_sched_t s,ggml_backend_sched_eval_callback cb,void *data) {
    need(cb==observe,"original callback");
    ggml_backend_sched_set_eval_callback(s,observe_ranks,data);
}

int main(int argc,char **argv) {
    try {
        need(argc==6 && std::string(argv[4])=="ALIAS","one ALIAS arm");
        fs::path out=fs::path(argv[5]).parent_path()/"rank";
        need(fs::create_directory(out),"exclusive rank folder");
        const int rc=original_main(argc,argv);
        if(rc!=0) return rc;
        finish_capture(out);
        return 0;
    } catch(const std::exception &e) {
        std::cerr<<"FAIL_CPU0_RANK_STAGES "<<e.what()<<'\n';return 1;
    }
}
