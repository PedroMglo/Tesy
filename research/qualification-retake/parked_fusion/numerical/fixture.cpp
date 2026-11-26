// Numerical-only CPU fixture. No model, GPU, sampling or timing.
#include "ggml.h"
#include "ggml-cpu.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr int width = 32, ranks = 4, slots = 4;
constexpr uint32_t canary = 0x4b130101; // finite F32
using Count = uint64_t (*)();

void require(bool ok, const char *label) {
    if (!ok) throw std::runtime_error(label);
}
uint32_t bits(float x) {
    uint32_t b;
    std::memcpy(&b, &x, 4);
    return b;
}
char *cell(ggml_tensor *t, int i, int j = 0, int k = 0) {
    return static_cast<char *>(t->data) + i*t->nb[0] + j*t->nb[1] + k*t->nb[2];
}
template<class T> void write(ggml_tensor *t, int i, int j, int k, T v) {
    std::memcpy(cell(t,i,j,k), &v, 4);
}
float read(ggml_tensor *t, int i, int j, int k) {
    float v;
    std::memcpy(&v, cell(t,i,j,k), 4);
    return v;
}
bool env_is(const char *key, const char *value) {
    const char *actual = std::getenv(key);
    return value ? actual && std::strcmp(actual,value)==0 : !actual;
}
enum class Layout {plain, strided, requested, consumer, interleaved, id_gap, activation_alias};
constexpr std::array<const char *,7> layouts{
    "plain","strided","requested","consumer","interleaved","id_gap","activation_alias"
};
enum class Pattern {parked, last_active, mixed, one_parked, active};
constexpr std::array<const char *,5> patterns{"parked","last_active","mixed","one_parked","active"};
bool parked(Pattern p, int token, int rank, int n) {
    switch (p) {
    case Pattern::parked: return true;
    case Pattern::last_active: return !(token == n-1 && rank == ranks-1);
    case Pattern::mixed: return rank != (token+1)%ranks;
    case Pattern::one_parked: return token == 0 && rank == 0;
    case Pattern::active: return false;
    }
    throw std::logic_error("pattern");
}
int logical(int token, int rank) { return (token+rank+1)%slots; }
float down_bias(int f, int expert) {
    const float tiny=std::numeric_limits<float>::denorm_min();
    switch (f%8) {
    case 0: return 0.0f;
    case 1: return -0.0f;
    case 2: return tiny;
    case 3: return -tiny;
    case 4: return 0.5f*(expert+1);
    case 5: return -0.5f*(expert+1);
    case 6: return -0.125f;
    default: return 0.125f;
    }
}
float prior_value(int f,int rank) {
    switch ((f+rank)%4) {
    case 0: return -0.0f;
    case 1: return 0.0f;
    case 2: return 0.75f;
    default: return -0.75f;
    }
}
ggml_tensor *ids_view(ggml_context *ctx, int n, bool strided) {
    if (!strided) return ggml_new_tensor_2d(ctx,GGML_TYPE_I32,ranks,n);
    auto *backing=ggml_new_tensor_2d(ctx,GGML_TYPE_I32,n+3,ranks);
    std::fill_n(static_cast<int32_t *>(backing->data),(n+3)*ranks,2);
    auto *view=ggml_view_2d(ctx,backing,n,ranks,backing->nb[1],sizeof(int32_t));
    return ggml_transpose(ctx,view);
}

struct Case {
    std::string id;
    size_t offset, bytes;
    uint64_t expected, observed;
};

class Graph {
    std::unique_ptr<ggml_context,decltype(&ggml_free)> context;
    ggml_cgraph *g;
    ggml_tensor *x, *physical, *route, *mask, *prior;
    ggml_tensor *gate, *biased_gate, *down, *biased_down, *masked, *sum, *extra=nullptr;
    ggml_tensor *w[3], *bias[3];
    int n, threads;
    Layout layout;
    std::vector<uint32_t> arena;
    std::vector<bool> live;
    int row_pitch=width, token_pitch=ranks*width;
    int sequence=0;

    void init_weights() {
        const auto quantize=ggml_get_type_traits(GGML_TYPE_MXFP4)->from_float_ref;
        require(quantize!=nullptr,"MXFP4 reference converter");
        for (int k=0;k<3;k++) {
            for (int e=0;e<slots;e++) {
                for (int f=0;f<width;f++) {
                    float source[width];
                    for (int j=0;j<width;j++)
                        source[j] = (1+(j+f)%3)*(1+k+e)/32.f;
                    quantize(source,cell(w[k],0,f,e),width);
                    write(bias[k],f,e,0, k==2 ? down_bias(f,e) : (1+e+k)/8.f);
                }
            }
        }
    }
    void set_storage() {
        const size_t packed=size_t(n)*ranks*width;
        if (layout == Layout::strided) {
            row_pitch=width+3;
            token_pitch=ranks*row_pitch+5;
            arena.resize(7+n*token_pitch+9);
            down->data=arena.data()+7;
            down->nb[1]=row_pitch*4;
            down->nb[2]=token_pitch*4;
            down->nb[3]=n*down->nb[2];
            live.resize(arena.size(),false);
            for (int t=0;t<n;t++) for (int r=0;r<ranks;r++) for (int f=0;f<width;f++)
                live[7+t*token_pitch+r*row_pitch+f]=true;
        } else if (layout == Layout::activation_alias) {
            arena.resize(packed+16);
            x->data=down->data=arena.data()+8;
        } else if (layout == Layout::id_gap) {
            // Overlap of address spans, yet the actual ID and F32 cells are disjoint.
            // This is safe for the old worker teams, including the eight-thread control.
            const size_t stride=packed+16;
            arena.resize(n*stride+packed+16);
            physical->data=arena.data();
            physical->nb[1]=stride*4;
            physical->nb[2]=physical->nb[3]=n*stride*4;
            down->data=arena.data()+8;
        }
    }
public:
    Graph(int tokens,int team,Layout how)
        : context(ggml_init({4*1024*1024,nullptr,false}),ggml_free), n(tokens), threads(team), layout(how) {
        require(bool(context),"GGML context");
        auto *c=context.get();
        g=ggml_new_graph_custom(c,128,false);
        x=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,1,n);
        physical=ids_view(c,n,layout==Layout::strided);
        route=ids_view(c,n,layout==Layout::strided);
        mask=ggml_new_tensor_3d(c,GGML_TYPE_F32,1,ranks,n);
        prior=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,ranks,n);
        for (int k=0;k<3;k++) {
            w[k]=ggml_new_tensor_3d(c,GGML_TYPE_MXFP4,width,width,slots);
            bias[k]=ggml_new_tensor_2d(c,GGML_TYPE_F32,width,slots);
        }
        init_weights();
        ggml_build_forward_expand(g,physical);
        ggml_build_forward_expand(g,route);
        gate=ggml_mul_mat_id(c,w[0],x,physical);
        if (layout == Layout::interleaved) {
            ggml_build_forward_expand(g,gate);
            extra=ggml_scale(c,prior,0.5f);
            ggml_build_forward_expand(g,extra);
        }
        biased_gate=ggml_add_id(c,gate,bias[0],route);
        auto *up=ggml_mul_mat_id(c,w[1],x,physical);
        auto *biased_up=ggml_add_id(c,up,bias[1],route);
        auto *glu=ggml_swiglu_oai(c,biased_gate,biased_up,1.702f,7.f);
        down=ggml_mul_mat_id(c,w[2],glu,physical);
        if (layout == Layout::requested) ggml_set_output(biased_gate);
        set_storage();
        biased_down=ggml_add_id(c,down,bias[2],route);
        masked=ggml_mul(c,biased_down,mask);
        sum=ggml_add(c,prior,masked);
        ggml_build_forward_expand(g,sum);
        if (layout==Layout::consumer) {
            extra=ggml_scale(c,biased_gate,0.5f);
            ggml_build_forward_expand(g,extra);
        }
        if (layout==Layout::requested) extra=biased_gate;
    }

    Case run(const std::string &mode,Pattern p, Count counter, FILE *out) {
        if (!arena.empty()) std::fill(arena.begin(),arena.end(),canary);
        for (int t=0;t<n;t++) {
            for (int f=0;f<width;f++) write(x,f,0,t,(1+(f+t)%5)/8.f);
            for (int r=0;r<ranks;r++) {
                const bool absent=parked(p,t,r,n);
                write(physical,r,t,0,int32_t(absent ? -1 : (t+r+2)%slots));
                write(route,r,t,0,int32_t(logical(t,r)));
                write(mask,0,r,t,absent ? 0.0f : 1.0f);
                for (int f=0;f<width;f++) write(prior,f,r,t,prior_value(f,r));
            }
        }
        // Poison a retained value so a skipped producer cannot pass via stale bits.
        if (extra) for (int t=0;t<n;t++) for (int r=0;r<ranks;r++) for (int f=0;f<width;f++)
            write(extra,f,r,t,123.5f);
        const uint64_t before=counter ? counter() : 0;
        require(ggml_graph_compute_with_ctx(context.get(),g,threads)==GGML_STATUS_SUCCESS,"native compute");
        const uint64_t after=counter ? counter() : 0;
        require(after>=before,"witness regression");
        const bool expected=mode=="fusion" && n>1 && p==Pattern::parked &&
                            (layout==Layout::plain || layout==Layout::strided);
        std::vector<uint32_t> values;
        bool seen_negative_zero=false, seen_positive_zero=false;
        const std::array<ggml_tensor *,5> outputs{down,biased_down,masked,sum,extra};
        for (auto *v:outputs) {
            if (!v) continue;
            for (int t=0;t<n;t++) for (int r=0;r<ranks;r++) for (int f=0;f<width;f++) {
                const float val=read(v,f,r,t);
                if (mode=="original") {
                    require(std::isfinite(val),"reference nonfinite");
                    if (v==down && parked(p,t,r,n)) require(bits(val)==0,"reference parked down");
                    if (v==biased_down) {
                        float correct=read(down,f,r,t)+down_bias(f,logical(t,r));
                        require(bits(val)==bits(correct),"reference logical down bias");
                    }
                    if (v==masked) {
                        const float correct=read(biased_down,f,r,t)*(parked(p,t,r,n)?0.f:1.f);
                        require(bits(val)==bits(correct),"reference mask");
                        seen_negative_zero |= bits(val)==0x80000000U;
                        seen_positive_zero |= bits(val)==0;
                    }
                    if (v==sum) {
                        const float correct=prior_value(f,r)+read(masked,f,r,t);
                        require(bits(val)==bits(correct),"reference ordered accumulation");
                    }
                }
                values.push_back(bits(val));
            }
        }
        if (mode=="original" && p==Pattern::parked) {
            require(seen_negative_zero && seen_positive_zero,"missing signed zero coverage");
        }
        if (layout==Layout::strided) {
            for (size_t i=0;i<live.size();i++) if (!live[i]) values.push_back(arena[i]);
        }
        const long offset=std::ftell(out);
        require(offset>=0 && std::fwrite(values.data(),4,values.size(),out)==values.size(),"rows write");
        std::string id="n"+std::to_string(n)+"-t"+std::to_string(threads)+"-"+
            layouts.at(static_cast<size_t>(layout))+"-"+std::to_string(sequence++)+"-"+
            patterns.at(static_cast<size_t>(p));
        return {id,size_t(offset),values.size()*4,uint64_t(expected),after-before};
    }
};
} // namespace

int main(int argc,char **argv) {
    try {
        require(argc==3,"usage: fixture original|off|mmid|fusion NEW_BINARY_ROWS");
        const std::string mode=argv[1];
        const bool original=mode=="original", fusion=mode=="fusion";
        require(original || mode=="off" || mode=="mmid" || fusion,"unknown mode");
        require(env_is("TESY_CPU_WAVE_SKIP_PARKED","1") &&
                env_is("TESY_CPU_MMX_ALL_PARKED",original ? nullptr : mode=="off" ? "0" : "1") &&
                env_is("TESY_CPU_PARKED_FUSION",original ? nullptr : fusion ? "1" : "0"),"native mode mismatch");
        const uint32_t one=1;
        require(*reinterpret_cast<const uint8_t *>(&one)==1 && sizeof(float)==4 &&
                std::numeric_limits<float>::is_iec559,"LE IEEE F32 required");
        auto counter=reinterpret_cast<Count>(dlsym(RTLD_DEFAULT,"tesy_parked_fusion_count"));
        require(bool(counter)==!original,"numerical counter provider");
        if (counter) require(counter()==0,"counter is not initially zero");
        auto *out=std::fopen(argv[2],"wbx");
        require(out!=nullptr,"exclusive rows output");
        const auto close_file=[](FILE *f){ std::fclose(f); };
        std::unique_ptr<FILE,decltype(close_file)> file(out,close_file);
        std::vector<Case> cases;
        for (const int n:{1,2,20,32}) for (const int threads:{1,8}) {
            Graph plain(n,threads,Layout::plain);
            for (Pattern p:{Pattern::parked,Pattern::last_active,Pattern::mixed,Pattern::one_parked,
                            Pattern::active,Pattern::parked})
                cases.push_back(plain.run(mode,p,counter,out));
            for (Layout layout:{Layout::strided,Layout::requested,Layout::consumer,Layout::interleaved,
                                Layout::id_gap,Layout::activation_alias}) {
                Graph other(n,threads,layout);
                cases.push_back(other.run(mode,Pattern::parked,counter,out));
            }
        }
        const long size=std::ftell(out);
        require(size>0 && std::fclose(file.release())==0 && cases.size()==96,"rows completion");
        uint64_t count=0;
        for (const auto &row:cases) count+=row.observed;
        require(count==(counter ? counter() : 0),"counter conservation");
        std::cout<<"{\"status\":\"PASS_NUMERIC_PARKED_FUSION_FIXTURE\",\"mode\":\""<<mode
                 <<"\",\"total_bytes\":"<<size<<",\"fused_regions\":"<<count<<",\"cases\":[";
        for (size_t i=0;i<cases.size();i++) {
            const auto &row=cases[i];
            std::cout<<(i?",":"")<<"{\"id\":\""<<row.id<<"\",\"offset\":"<<row.offset
                     <<",\"bytes\":"<<row.bytes<<",\"expected_fusions\":"<<row.expected
                     <<",\"observed_fusions\":"<<row.observed<<"}";
        }
        std::cout<<"]}\n";
    } catch(const std::exception &e) {
        std::fprintf(stderr,"FAIL_NUMERIC_PARKED_FUSION_FIXTURE %s\n",e.what());
        return 1;
    }
    return 0;
}
