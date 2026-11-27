// Exercise the original GGML CPU graph, real MXFP4 kernels and repeated routing.
#include "ggml-cpu.h"
#include "ggml-impl.h"
#include <array>
#include <bit>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <dlfcn.h>
#include <memory>
#include <stdexcept>
#include <string>

static void check(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }
static constexpr int width=64, ranks=4;
struct Route { bool active=false, challenge=false; unsigned maps=0, masks=0; };

static void publish(ggml_tensor *out, int ith, int, void *user) {
    if (ith) return;
    auto &r=*static_cast<Route *>(user);
    auto *v=static_cast<int32_t *>(out->data);
    const int n=ggml_nelements(out);
    for (int i=0; i<n; ++i) v[i]=r.active && i==n-1 ? 3 : -1;
    ++r.maps;
}

static void mask(ggml_tensor *out, int ith, int, void *user) {
    if (ith) return;
    auto &r=*static_cast<Route *>(user);
    const auto *ids=static_cast<const int32_t *>(out->src[1]->data);
    auto *v=static_cast<float *>(out->data);
    for (int i=0; i<ggml_nelements(out); ++i) {
        v[i]=ids[i]>=0 ? 1.0f : r.challenge && i%3==1 ? 0.5f : 0.0f;
    }
    ++r.masks;
}

enum class Case { normal, strided, exposed, consumer, cropped, challenge };
using Count = uint64_t (*)();
using File = std::unique_ptr<FILE, decltype(&std::fclose)>;

static void save(FILE *out, ggml_tensor *value) {
    check(value->type==GGML_TYPE_F32 && ggml_is_contiguous(value),"result type");
    const auto *data=static_cast<const float *>(value->data);
    for (int i=0;i<ggml_nelements(value);++i) check(std::isfinite(data[i]),"nonfinite");
    check(std::fwrite(data,1,ggml_nbytes(value),out)==ggml_nbytes(value),"write");
}

static unsigned run(int n, int nth, Case how, bool enabled, Count witness, FILE *out) {
    std::unique_ptr<ggml_context, decltype(&ggml_free)> ctx(ggml_init({16U<<20,nullptr,false}),ggml_free);
    check(bool(ctx),"arena");
    auto *c=ctx.get();
    auto *g=ggml_new_graph_custom(c,128,false);
    auto *x=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,1,n);
    auto *prev=ggml_new_tensor_3d(c,GGML_TYPE_F32,width,ranks,n);
    const int pitch=how==Case::strided ? 128 : ranks;
    auto *parent=ggml_new_tensor_2d(c,GGML_TYPE_I32,pitch,n);
    auto *logical=ggml_view_2d(c,parent,ranks,n,parent->nb[1],0);
    auto *cont=ggml_cont(c,logical);
    Route route;
    ggml_tensor *sources[2]={cont,ggml_view_1d(c,prev,1,0)};
    auto *ids=ggml_custom_4d(c,GGML_TYPE_I32,ranks,n,1,1,sources,2,publish,1,&route);
    ggml_tensor *w[3], *b[3];
    const std::array<uint32_t,9> bits={0x80000000u,0u,1u,0x80000001u,0x00800000u,
                                        0x80800000u,0x3e800000u,0xbe000000u,0x3f000000u};
    for (int k=0;k<3;++k) {
        w[k]=ggml_new_tensor_3d(c,GGML_TYPE_MXFP4,width,width,40);
        auto *bytes=static_cast<unsigned char *>(w[k]->data);
        for (size_t i=0;i<ggml_nbytes(w[k]);++i) bytes[i]=i%17==0 ? 124 : 0x12+k;
        b[k]=ggml_new_tensor_2d(c,GGML_TYPE_F32,width,128);
        for (int i=0;i<width*128;++i)
            static_cast<float *>(b[k]->data)[i]=std::bit_cast<float>(bits[(i+i/width+k)%bits.size()]);
    }
    for (int i=0;i<n*width;++i) static_cast<float *>(x->data)[i]=(i%9-4)*0.0625f;
    for (int i=0;i<n*ranks*width;++i)
        static_cast<float *>(prev->data)[i]=std::bit_cast<float>(bits[(i+i/width)%bits.size()]);
    auto *gate=ggml_add_id(c,ggml_mul_mat_id(c,w[0],x,ids),b[0],logical);
    auto *up=ggml_add_id(c,ggml_mul_mat_id(c,w[1],x,ids),b[1],logical);
    auto *activation=ggml_swiglu_oai(c,gate,up,1.702f,7.0f);
    auto *down=ggml_add_id(c,ggml_mul_mat_id(c,w[2],activation,ids),b[2],logical);
    ggml_tensor *ms[2]={cont,ids};
    auto *weights=ggml_custom_4d(c,GGML_TYPE_F32,1,ranks,n,1,ms,2,mask,1,&route);
    auto *product=ggml_mul(c,down,weights);
    auto *sum=ggml_add(c,prev,product);
    if (how==Case::exposed) ggml_set_output(gate);
    ggml_build_forward_expand(g,sum);
    ggml_tensor *extra=nullptr;
    if (how==Case::consumer) {
        extra=ggml_scale(c,gate,0.5f);
        ggml_build_forward_expand(g,extra);
    }
    int cut=0;
    while (cut<ggml_graph_n_nodes(g) && ggml_graph_node(g,cut)!=weights) ++cut;
    check(cut>0 && cut<ggml_graph_n_nodes(g),"mask boundary");
    unsigned total=0;
    for (int visit=0;visit<3;++visit) {
        route.active=visit==1;
        route.challenge=how==Case::challenge;
        for (int t=0;t<n;++t) for (int r=0;r<ranks;++r)
            static_cast<int32_t *>(parent->data)[t*pitch+r]=(visit+5*t+r)%128;
        const uint64_t before=witness ? witness() : 0;
        if (how==Case::cropped) {
            auto first=ggml_graph_view(g,0,cut);
            auto last=ggml_graph_view(g,cut,ggml_graph_n_nodes(g));
            for (auto *part : {&first,&last})
                check(ggml_graph_compute_with_ctx(c,part,nth)==GGML_STATUS_SUCCESS,"subgraph compute");
        } else {
            check(ggml_graph_compute_with_ctx(c,g,nth)==GGML_STATUS_SUCCESS,"compute");
        }
        const uint64_t after=witness ? witness() : 0;
        const bool eligible=how==Case::normal || how==Case::strided || how==Case::challenge;
        check(after-before==unsigned(enabled && n>1 && !route.active && eligible),"fusion witness");
        check(route.maps==unsigned(visit+1) && route.masks==route.maps,"callback conservation");
        save(out,sum);
        if (how==Case::exposed) save(out,gate);
        if (extra) save(out,extra);
        total+=after-before;
    }
    return total;
}

int main(int argc,char **argv) {
    try {
        check(argc==3,"fixture ORIGINAL|OFF|ON NEW_BINARY_OUTPUT");
        const std::string mode=argv[1];
        check(mode=="ORIGINAL" || mode=="OFF" || mode=="ON","arm");
        auto witness=reinterpret_cast<Count>(dlsym(RTLD_DEFAULT,"tesy_cpu_wave_count"));
        check(bool(witness)==(mode!="ORIGINAL"),"CPU DSO witness identity");
        File out(std::fopen(argv[2],"wbx"),std::fclose);
        check(bool(out),"exclusive output");
        unsigned fusions=0, runs=0;
        for (int n : {1,5,20,32}) for (int nth : {1,8})
            for (auto how : {Case::normal,Case::strided,Case::exposed,Case::consumer,Case::cropped,Case::challenge}) {
                fusions+=run(n,nth,how,mode=="ON",witness,out.get());
                runs+=3;
            }
        check(std::fflush(out.get())==0,"flush");
        std::printf("submissions=%u remaps=%u masks=%u fusions=%u bytes=%ld\n",
                    runs,runs,runs,fusions,std::ftell(out.get()));
    } catch (const std::exception &ex) {
        std::fprintf(stderr,"fixture failed: %s\n",ex.what()); return 1;
    }
}
