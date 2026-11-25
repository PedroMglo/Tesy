// Scope: original CPU MUL_MAT_ID with fixed, synthetic bytes and independent RHS packing.
#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"

#include <dlfcn.h>
#include <omp.h>
#include <openssl/sha.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
constexpr int width = 2880, ranks = 4, slots = 40, threads = 8;
constexpr size_t expert_bytes = 4406400, qrow = 3060;
constexpr int routing[3][ranks] = {{3,0,6,2}, {1,3,4,0}, {6,5,2,3}};

static void require(bool valid, const char *why) {
    if (!valid) throw std::runtime_error(why);
}

static std::string digest(const void *data, size_t n) {
    unsigned char bytes[SHA256_DIGEST_LENGTH];
    require(SHA256(static_cast<const unsigned char *>(data), n, bytes) != nullptr, "SHA256");
    char hex[SHA256_DIGEST_LENGTH*2+1] = {};
    for (size_t i=0; i<sizeof(bytes); ++i) std::snprintf(hex+2*i, 3, "%02x", bytes[i]);
    return hex;
}

static void write_bytes(const fs::path &path, const void *data, size_t n) {
    FILE *f = std::fopen(path.c_str(), "wbx");
    require(f != nullptr, "exclusive output");
    bool good = std::fwrite(data, 1, n, f)==n;
    require(std::fclose(f)==0 && good, "complete output");
}

static std::string provider(const void *address) {
    Dl_info info{};
    require(dladdr(address, &info) && info.dli_fname, "provider");
    return fs::canonical(info.dli_fname).string();
}

static uint32_t advance(uint32_t &x) {
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
}

static void fill_weights(ggml_tensor *w) {
    auto *data = static_cast<uint8_t *>(w->data);
    for (int expert=0; expert<7; ++expert) {
        uint32_t state = 0x17ad943bu ^ ((expert+1u)*0x9e3779b9u);
        uint8_t *dest = data + expert*w->nb[2];
        for (size_t o=0; o<expert_bytes; o+=17) {
            dest[o] = uint8_t(123 + (advance(state) & 7u));
            for (size_t j=1; j<17; ++j) dest[o+j] = uint8_t(advance(state) >> 24);
        }
    }
}

static void activation(float *row, int position, int component) {
    uint32_t state=0x413ae29bu ^ ((position+1u)*0x4570d1f7u) ^ ((component+1u)*0xb718bb61u);
    for (int k=0; k<width; ++k) {
        const int value = int(advance(state) >> 16)-32768;
        row[k] = std::ldexp(float(value), -13 - ((k/32+position+component)%5));
    }
}

using Context = std::unique_ptr<ggml_context, decltype(&ggml_free)>;

static void run(ggml_tensor *weights, ggml_threadpool *pool, int shared,
                const std::vector<int> &order, bool wrong, const fs::path &prefix) {
    const int n = int(order.size());
    Context ctx(ggml_init({2u<<20, nullptr, false}), ggml_free);
    require(ctx != nullptr, "graph context");
    auto *x = ggml_new_tensor_3d(ctx.get(), GGML_TYPE_F32, width, shared, n);
    auto *ids = ggml_new_tensor_2d(ctx.get(), GGML_TYPE_I32, ranks, n);
    auto *y = ggml_mul_mat_id(ctx.get(), weights, x, ids);
    require(y->op==GGML_OP_MUL_MAT_ID && y->ne[0]==width && y->ne[1]==ranks &&
            y->ne[2]==n && y->ne[3]==1 && y->nb[1]==sizeof(float)*width &&
            y->nb[2]==sizeof(float)*width*ranks && ggml_is_contiguous(x) &&
            x->nb[2]==sizeof(float)*width*shared && ids->nb[1]==ranks*sizeof(int32_t),
            "logical shapes/strides");
    auto *floats = static_cast<float *>(x->data);
    auto *indices = static_cast<int32_t *>(ids->data);
    std::vector<uint8_t> packed(qrow*shared*n);
    auto convert = ggml_get_type_traits_cpu(GGML_TYPE_Q8_0)->from_float;
    for (int t=0; t<n; ++t) {
        for (int r=0; r<ranks; ++r) indices[t*ranks+r] = routing[order[t]][r];
        for (int r=0; r<shared; ++r) {
            const int block = t*shared+r;
            activation(floats+block*width, order[t], r);
            convert(floats+block*width, packed.data()+block*qrow, width);
        }
    }
    if (wrong) indices[0]=5;
    auto *graph = ggml_new_graph_custom(ctx.get(), 16, false);
    ggml_build_forward_expand(graph,y);
    require(ggml_graph_n_nodes(graph)==1 && ggml_graph_node(graph,0)==y, "single MMID");
    auto plan=ggml_graph_plan(graph,threads,pool);
    void *mem=nullptr;
    require(plan.n_threads==threads && plan.threadpool==pool && plan.work_size>=packed.size() &&
            posix_memalign(&mem,64,plan.work_size)==0, "workspace and team");
    std::unique_ptr<void,decltype(&std::free)> workspace(mem,std::free);
    plan.work_data=static_cast<uint8_t *>(mem);
    std::memset(mem,0xda,plan.work_size);
    std::fill_n(static_cast<uint32_t *>(y->data), ggml_nelements(y), UINT32_C(0x7fc01234));
    require(ggml_graph_compute(graph,&plan)==GGML_STATUS_SUCCESS,"compute");
    require(!std::all_of(plan.work_data,plan.work_data+packed.size(),
                         [](uint8_t v){return v==0xda;}),"MMID left the Q8 workspace untouched");
    for (int64_t i=0;i<ggml_nelements(y);++i)
        require(std::isfinite(static_cast<float *>(y->data)[i]),"non-finite output");
    write_bytes(prefix.string()+".f32",y->data,ggml_nbytes(y));
    write_bytes(prefix.string()+".q8",mem,packed.size());
    write_bytes(prefix.string()+".reference-q8",packed.data(),packed.size());
    write_bytes(prefix.string()+".x",x->data,ggml_nbytes(x));
    write_bytes(prefix.string()+".ids",ids->data,ggml_nbytes(ids));
}

int main(int argc,char **argv) {
    try {
        require(argc==2,"usage: fixture NEW_DIRECTORY");
        const fs::path out=argv[1];
        require(fs::create_directory(out),"exclusive native directory");
        ggml_cpu_init();
        auto traits=ggml_get_type_traits_cpu(GGML_TYPE_MXFP4);
        require(traits && traits->vec_dot_type==GGML_TYPE_Q8_0 && traits->nrows==1 &&
                ggml_cpu_has_avx2() && ggml_row_size(GGML_TYPE_Q8_0,width)==qrow,
                "native MXFP4 CPU traits");
        auto pp=ggml_threadpool_params_default(threads);
        std::unique_ptr<ggml_threadpool,decltype(&ggml_threadpool_free)>
            pool(ggml_threadpool_new(&pp),ggml_threadpool_free);
        require(pool && pp.n_threads==threads && !omp_get_dynamic(),"eight-thread pool");
        int actual=0;
#pragma omp parallel num_threads(threads)
        {
#pragma omp single
            actual=omp_get_num_threads();
        }
        require(actual==threads,"OpenMP team");
        Context ctx(ggml_init({1u<<20,nullptr,true}),ggml_free);
        require(ctx != nullptr,"weight context");
        auto *w=ggml_new_tensor_3d(ctx.get(),GGML_TYPE_MXFP4,width,width,slots);
        auto buft=ggml_backend_cpu_buffer_type();
        std::unique_ptr<ggml_backend_buffer,decltype(&ggml_backend_buffer_free)> buffer(
            ggml_backend_alloc_ctx_tensors_from_buft(ctx.get(),buft),ggml_backend_buffer_free);
        require(buffer && w->data && w->buffer==buffer.get() && w->extra==nullptr &&
                ggml_backend_buffer_get_type(w->buffer)==buft && w->nb[2]==expert_bytes &&
                ggml_nbytes(w)==slots*expert_bytes, "standard CPU forty-slot backing");
        ggml_backend_buffer_clear(w->buffer, 0);
        fill_weights(w);
        std::printf("weight_sha256 %s\n",digest(w->data,ggml_nbytes(w)).c_str());
        std::printf("cpu %s\n",provider((const void *)ggml_graph_compute).c_str());
        std::printf("dot %s\n",provider((const void *)traits->vec_dot).c_str());
        std::printf("convert %s\n",provider((const void *)
                    ggml_get_type_traits_cpu(GGML_TYPE_Q8_0)->from_float).c_str());
        std::printf("base %s\n",provider((const void *)ggml_mul_mat_id).c_str());
        for (int shared:{1,4}) {
            const std::string stem=std::to_string(shared)+"-";
            for(int i=0;i<3;++i) run(w,pool.get(),shared,{i},false,out/(stem+"ar"+std::to_string(i)));
            run(w,pool.get(),shared,{0,1,2},false,out/(stem+"batch"));
            run(w,pool.get(),shared,{2,0,1},false,out/(stem+"permuted"));
            run(w,pool.get(),shared,{0,1,2},true,out/(stem+"wrong"));
        }
        std::puts("status PASS_CAPTURED_CPU_MMID");
    } catch(const std::exception &e) {
        std::fprintf(stderr,"FAIL %s\n",e.what());
        return 1;
    }
}
