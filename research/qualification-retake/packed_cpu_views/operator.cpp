// Synthetic C269 CPU MUL_MAT_ID. No model, model routing, I/O or latency measurement.
#include "ggml-cpp.h"
#include "ggml-cpu.h"

#include <dlfcn.h>
#include <sys/mman.h>

#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr int width = 2880, slots = 40, ranks = 4, positions = 3;
constexpr size_t block = 17, row = width/32 * block, slab = width * row;
constexpr size_t stride = 13'221'888, page = 4096;
static_assert(slab == 4'406'400 && stride - 3*slab == 2688);

constexpr std::array<const char *, 3> names{"gate", "down", "up"};
constexpr std::array<int32_t, ranks * positions> routes{39, 0, 7, 23, 7, 39, 23, 0, 23, 7, 0, 39};

void check(bool ok, const char *reason) {
    if (!ok) throw std::runtime_error(reason);
}

struct Region {
    size_t bytes;
    uint8_t *base;
    ggml_backend_buffer_ptr buffer;

    explicit Region(size_t needed) : bytes((needed + page-1)/page*page), base(nullptr) {
        void *all = mmap(nullptr, bytes+2*page, PROT_NONE, MAP_ANONYMOUS|MAP_PRIVATE, -1, 0);
        check(all != MAP_FAILED, "mmap");
        base = static_cast<uint8_t *>(all)+page;
        check(mprotect(base, bytes, PROT_READ|PROT_WRITE)==0, "guard");
        buffer.reset(ggml_backend_cpu_buffer_from_ptr(base, bytes));
        check(buffer != nullptr, "CPU buffer");
    }
    ~Region() { buffer.reset(); munmap(base-page, bytes+2*page); }
    Region(const Region &) = delete;
    Region &operator=(const Region &) = delete;
};

// All source rows have one exactly representable E2M1 value, ±1, at a known coordinate.
// For each activation block max(abs(x))=127, hence Q8_0 scale=1 and integral payload.
int coordinate(int component, int slot, int output) {
    return (29*output + 67*slot + 347*component + 31) % width;
}
int sign(int component, int slot, int output) {
    return ((slot + output/7 + component) % 2) ? -1 : 1;
}
float activation(int token, int rank, int col) {
    if (col % 32 == 0) return 127.0f;
    return static_cast<float>((col*19 + token*31 + rank*37) % 223 - 111);
}

void fill(uint8_t *bytes, int component, int slot) {
    for (int y=0; y<width; ++y) {
        int c = coordinate(component, slot, y);
        auto *b = bytes + y*row + c/32*block;
        b[0] = 127; // E8M0 2^0, nibble 2 or 10 gives ±1.
        b[1+c%16] = static_cast<uint8_t>((sign(component,slot,y)>0 ? 2 : 10) << (c%32>=16 ? 4 : 0));
    }
}

enum class Layout { control, packed, wrong_stride, wrong_component };
using Values = std::vector<float>;
struct Result { Values values; size_t scalar_mismatches=0; };

struct Observed {
    const std::array<ggml_tensor *,3> *outputs;
    std::array<int,3> finished{};
};

bool watch(ggml_tensor *tensor, bool ask, void *opaque) {
    auto &obs=*static_cast<Observed *>(opaque);
    for (int k=0; k<3; ++k) {
        if (tensor==(*obs.outputs)[k]) {
            if (!ask) ++obs.finished[k];
            return true;
        }
    }
    return false;
}

Result run(ggml_backend_t cpu, Layout mode) {
    bool packed = mode != Layout::control;
    size_t owner_blocks = (slots*stride + block-1)/block;
    Region memory(packed ? owner_blocks*block : 3*slots*slab);
    ggml_context_ptr ctx(ggml_init({2u<<20, nullptr, true}));
    check(ctx != nullptr, "context");
    ggml_tensor *owner=nullptr;
    if (packed) {
        owner=ggml_new_tensor_1d(ctx.get(), GGML_TYPE_MXFP4, 32*owner_blocks);
        check(ggml_backend_tensor_alloc(memory.buffer.get(),owner,memory.base)==GGML_STATUS_SUCCESS,
              "owner allocation");
    }
    if (packed) check(reinterpret_cast<uintptr_t>(owner->data) % page == 0, "DIO arena base");
    const size_t advance = packed ? stride : slab;
    auto placement = [&](int k, int s) {
        return memory.base + (packed ? k*slab : k*slots*slab) + s*advance;
    };

    ggml_backend_sched_ptr sched(ggml_backend_sched_new(&cpu,nullptr,1,256,false,false));
    check(sched != nullptr, "scheduler");
    auto *g=ggml_new_graph_custom(ctx.get(),256,false);
    auto *ids=ggml_new_tensor_2d(ctx.get(),GGML_TYPE_I32,ranks,positions);
    ggml_set_input(ids);
    std::array<ggml_tensor *,3> x{}, weight{}, output{};
    for (int k=0; k<3; ++k) {
        for (int s : {0,7,23,39}) fill(placement(k,s),k,s);
        if (packed) {
            size_t offset = (mode==Layout::wrong_component ? (k+1)%3 : k)*slab;
            size_t slot_stride = mode==Layout::wrong_stride ? 3*slab : stride;
            weight[k]=ggml_view_3d(ctx.get(),owner,width,width,slots,row,slot_stride,offset);
            check(ggml_backend_view_init(weight[k])==GGML_STATUS_SUCCESS,"initialize weight view");
        } else {
            weight[k]=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_MXFP4,width,width,slots);
            check(ggml_backend_tensor_alloc(memory.buffer.get(),weight[k],placement(k,0))==
                  GGML_STATUS_SUCCESS,"control allocation");
        }
        check(weight[k]->nb[0]==block && weight[k]->nb[1]==row &&
              weight[k]->ne[2]==slots,"native geometry");
        x[k]=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_F32,width,k==1?ranks:1,positions);
        const size_t expected_stride = mode==Layout::wrong_stride ? 3*slab : advance;
        const size_t span = (slots-1)*expected_stride + slab;
        check(weight[k]->nb[2]==expected_stride && weight[k]->nb[3]==slots*expected_stride &&
              ggml_nbytes(weight[k])==span && weight[k]->ne[3]==1, "MMID view bounds");
        auto *first=static_cast<uint8_t *>(weight[k]->data);
        check(first >= memory.base && first+span <= memory.base+memory.bytes, "owner overrun");
        check(ggml_is_contiguous(weight[k])==!packed, "weight storage density");
        ggml_set_input(x[k]);
        output[k]=ggml_mul_mat_id(ctx.get(),weight[k],x[k],ids);
        ggml_set_name(output[k],names[k]);
        ggml_set_output(output[k]);
        ggml_build_forward_expand(g,output[k]);
    }
    Observed observed{&output, {}};
    ggml_backend_sched_set_eval_callback(sched.get(),watch,&observed);
    check(ggml_backend_sched_alloc_graph(sched.get(),g),"allocate graph");
    check(ggml_backend_sched_get_n_backends(sched.get())==1 &&
          ggml_backend_sched_get_n_splits(sched.get())==1 &&
          ggml_backend_sched_get_n_copies(sched.get())==1, "unexpected scheduler split or copies");
    ggml_backend_tensor_set(ids,routes.data(),0,sizeof(routes));
    for (int k=0;k<3;++k) {
        check(ggml_backend_sched_get_tensor_backend(sched.get(),output[k])==cpu &&
              ggml_backend_supports_op(cpu,output[k]) && output[k]->op==GGML_OP_MUL_MAT_ID && output[k]->src[0]==weight[k] &&
              output[k]->src[0]->buffer==memory.buffer.get(),"CPU MMID or weight address changed");
        int channels=k==1?ranks:1;
        Values input;
        for (int t=0;t<positions;++t) for (int r=0;r<channels;++r) for (int c=0;c<width;++c)
            input.push_back(activation(t,r,c));
        ggml_backend_tensor_set(x[k],input.data(),0,input.size()*sizeof(float));
    }
    check(ggml_backend_sched_graph_compute(sched.get(),g)==GGML_STATUS_SUCCESS,"CPU compute");
    ggml_backend_sched_synchronize(sched.get());
    check(observed.finished==std::array<int,3>{1,1,1},"missing computed MMID callback");
    Result result;
    for (int k=0;k<3;++k) {
        auto *o=output[k];
        check(o->ne[0]==width && o->ne[1]==ranks && o->ne[2]==positions,"output geometry");
        Values values(width*ranks*positions);
        ggml_backend_tensor_get(o,values.data(),0,values.size()*sizeof(float));
        for(int t=0;t<positions;++t) for(int r=0;r<ranks;++r) for(int y=0;y<width;++y) {
            int s=routes[t*ranks+r];
            float gold=sign(k,s,y)*activation(t,k==1?r:0,coordinate(k,s,y));
            // MXFP4 multiplication may produce signed zero; require canonical +0 for the sum.
            if (gold==0) gold=0.0f;
            const float value=values[(t*ranks+r)*width+y];
            result.scalar_mismatches += std::memcmp(&gold,&value,sizeof(float))!=0;
        }
        result.values.insert(result.values.end(),values.begin(),values.end());
    }
    return result;
}

std::string provider(void *symbol) {
    Dl_info info{};
    check(dladdr(symbol,&info) && info.dli_fname, "missing DSO provider");
    return std::filesystem::canonical(info.dli_fname).string();
}
}

int main(int argc,char **argv) try {
    check(argc==2 && std::filesystem::is_directory(argv[1]) &&
          std::filesystem::is_empty(argv[1]),"expected an existing empty output directory");
    auto dir=std::filesystem::path(argv[1]);
    ggml_backend_ptr cpu(ggml_backend_cpu_init());
    check(cpu!=nullptr,"CPU init");
    ggml_backend_cpu_set_n_threads(cpu.get(),2);
    Result a=run(cpu.get(),Layout::control), b=run(cpu.get(),Layout::packed);
    check(a.scalar_mismatches==0 && b.scalar_mismatches==0,"scalar oracle");
    check(a.values.size()==b.values.size() &&
          std::memcmp(a.values.data(),b.values.data(),a.values.size()*sizeof(float))==0,"layout bits");
    auto wrong_stride=run(cpu.get(),Layout::wrong_stride);
    auto wrong_component=run(cpu.get(),Layout::wrong_component);
    check(wrong_stride.scalar_mismatches && wrong_component.scalar_mismatches,"insensitive oracle");
    for (const auto &[name, result] :
         std::array<std::pair<const char *,const Result *>,2>{{{"control",&a},{"packed",&b}}}) {
        std::ofstream file(dir/(std::string(name)+".f32"),std::ios::binary);
        file.exceptions(std::ios::failbit|std::ios::badbit);
        file.write(reinterpret_cast<const char *>(result->values.data()),
                   result->values.size()*sizeof(float));
        file.close();
    }
    std::ofstream providers(dir/"providers.txt");
    providers.exceptions(std::ios::failbit|std::ios::badbit);
    providers << provider(reinterpret_cast<void *>(&ggml_backend_cpu_init)) << '\n'
              << provider(reinterpret_cast<void *>(&ggml_backend_sched_graph_compute)) << '\n';
    providers.close();
    std::cout << "PASS " << a.values.size() << ' ' << wrong_stride.scalar_mismatches << ' '
              << wrong_component.scalar_mismatches << '\n';
    return 0;
} catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
}
