// C57 broadcast counterexample extended to padded/transposed IDs and guarded
// output rows. Link against the pinned GGML CPU/base. No model, timer or GPU.
#include "ggml.h"
#include "ggml-cpu.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

constexpr int width = 64, features = 16, ranks = 4, experts = 4;
constexpr uint32_t guard = 0xb4b4b4b4;
static void check(bool condition, const char *error) {
    if (!condition) throw std::runtime_error(error);
}

static uint32_t bits(float value) {
    uint32_t b;
    std::memcpy(&b, &value, sizeof(b));
    return b;
}

static int selected(int pattern, int rank, int token, int tokens) {
    if (pattern == 0) return -1;
    if (pattern == 1) return (token == tokens - 1 && rank == ranks - 1) ? 2 : -1;
    if (pattern == 2) return rank == (token+1) % ranks ? (token+2) % experts : -1;
    return (token+rank) % experts;
}

static ggml_tensor *id_view(ggml_context *c, int layout, int tokens) {
    if (layout == 0) return ggml_new_tensor_2d(c, GGML_TYPE_I32, ranks, tokens);
    const int columns = layout == 1 ? ranks : tokens;
    const int rows = layout == 1 ? tokens : ranks;
    auto *base = ggml_new_tensor_2d(c, GGML_TYPE_I32, columns+3, rows);
    std::fill_n(static_cast<int32_t *>(base->data), ggml_nelements(base), int32_t(1));
    auto *padded = ggml_view_2d(c, base, columns, rows, base->nb[1], sizeof(int32_t));
    return layout == 1 ? padded : ggml_transpose(c,padded);
}

static void set_id(ggml_tensor *ids, int t, int rank, int value) {
    std::memcpy(static_cast<char *>(ids->data) + t*ids->nb[1] + rank*ids->nb[0],
                &value, sizeof(int32_t));
}

static bool one(bool enabled, int tokens, int shared, int layout, int pattern,
                int threads, uint8_t poison, FILE *binary) {
    ggml_context *c = ggml_init({4*1024*1024, nullptr, false});
    check(c != nullptr, "ggml context");
    auto *weight = ggml_new_tensor_3d(c,GGML_TYPE_MXFP4,width,features,experts);
    auto *activation = ggml_new_tensor_3d(c,GGML_TYPE_F32,width,shared,tokens);
    auto *ids = id_view(c,layout,tokens);
    auto *result = ggml_mul_mat_id(c,weight,activation,ids);
    const auto convert = ggml_get_type_traits(GGML_TYPE_MXFP4)->from_float_ref;
    check(convert != nullptr,"MXFP4 quantizer");
    for (int e=0;e<experts;++e) {
        for (int f=0;f<features;++f) {
            float source[width];
            std::fill_n(source,width, (f%2 == 0 ? 1.f : -1.f)*(e+1)*(f+1)/8.f);
            convert(source, static_cast<char *>(weight->data)+e*weight->nb[2]+f*weight->nb[1],width);
        }
    }
    for (int t=0;t<tokens;++t) {
        for (int row=0;row<shared;++row) {
            auto *a = reinterpret_cast<float *>(static_cast<char *>(activation->data) +
                                                t*activation->nb[2]+row*activation->nb[1]);
            for (int k=0;k<width;++k) a[k]=(1.f+t+0.125f*row)*(1.f+k/128.f);
        }
        for (int r=0;r<ranks;++r) set_id(ids,t,r,selected(pattern,r,t,tokens));
    }

    // A non-overlapping, padded F32 destination. A flat zero fill destroys
    // these canaries or leaves live values unwritten. No subsequent op reads it.
    constexpr int leading = 4, rank_stride = features+3, token_stride = ranks*rank_stride+5;
    std::vector<uint32_t> storage(leading+tokens*token_stride+7,guard);
    result->data = storage.data()+leading;
    result->nb[1] = rank_stride*sizeof(float);
    result->nb[2] = token_stride*sizeof(float);
    result->nb[3] = tokens*result->nb[2];
    auto *graph = ggml_new_graph(c);
    ggml_build_forward_expand(graph,result);
    auto plan = ggml_graph_plan(graph,threads,nullptr);
    void *mem = nullptr;
    check(posix_memalign(&mem,64,plan.work_size)==0 && mem!=nullptr,"GGML workspace");
    plan.work_data = static_cast<uint8_t *>(mem);
    const size_t qbytes = ggml_row_size(GGML_TYPE_Q8_0,width)*shared*tokens;
    check(qbytes>0 && qbytes<=plan.work_size,"conversion workspace range");
    auto run = [&]() {
        std::fill(storage.begin(),storage.end(),guard);
        std::memset(mem,poison,plan.work_size);
        check(ggml_graph_compute(graph,&plan)==GGML_STATUS_SUCCESS,"CPU graph compute");
        std::vector<bool> live(storage.size(),false);
        std::vector<uint32_t> output;
        for (int t=0;t<tokens;++t) for (int r=0;r<ranks;++r) for (int f=0;f<features;++f) {
            size_t index = leading+t*token_stride+r*rank_stride+f;
            live[index]=true;
            output.push_back(storage[index]);
        }
        for (size_t i=0;i<storage.size();++i) check(live[i]||storage[i]==guard,"output padding");
        return output;
    };
    const auto observed=run();
    const bool untouched=std::all_of(plan.work_data,plan.work_data+qbytes,
                                      [&](uint8_t value){return value==poison;});
    const bool expect_skip = enabled && tokens>1 && pattern==0;
    check(untouched==expect_skip,"incorrect suppression of conversion");
    for (int t=0;t<tokens;++t) for (int r=0;r<ranks;++r) {
        if (selected(pattern,r,t,tokens)==-1) set_id(ids,t,r,1);
    }
    const auto active_reference=run();
    for (int t=0;t<tokens;++t) for (int r=0;r<ranks;++r) for (int f=0;f<features;++f) {
        const size_t ix=(t*ranks+r)*features+f;
        float v;
        std::memcpy(&v,&observed[ix],sizeof(v));
        check(std::isfinite(v),"nonfinite output");
        if (selected(pattern,r,t,tokens)<0) check(bits(v)==0,"parked result is not positive zero");
        else check(v!=0.f && observed[ix]==active_reference[ix],"broadcast/rank/stride mismatch");
    }
    check(std::fwrite(observed.data(),sizeof(uint32_t),observed.size(),binary)==observed.size(),"output write");
    std::free(mem);
    ggml_free(c);
    return untouched;
}

int main(int argc,char **argv) {
    try {
        check(argc==3,"usage: test-kernel-graph r0|off|on NEW_ROWS_BIN");
        const std::string arm=argv[1];
        const char *mode=std::getenv("TESY_CPU_MMX_ALL_PARKED");
        check((arm=="r0" && !mode) || (arm=="off" && mode && std::string(mode)=="0") ||
              (arm=="on" && mode && std::string(mode)=="1"),"arm/environment mismatch");
        FILE *binary=std::fopen(argv[2],"wbx");
        check(binary,"exclusive output");
        int cases=0, skipped=0;
        for (int tokens:{1,3}) for (int shared:{1,4}) for (int layout:{0,1,2})
            for (int pattern:{0,1,2,3}) for (int threads:{1,4}) for (uint8_t poison:{0x00,0x7f}) {
                skipped += one(arm=="on",tokens,shared,layout,pattern,threads,poison,binary);
                ++cases;
            }
        check(std::fclose(binary)==0 && cases==192 && skipped==(arm=="on"?24:0),"coverage");
        std::printf("PASS_PARKED_MMID_GRAPH cases=%d skipped=%d rows_bytes=98304\n",cases,skipped);
    } catch(const std::exception &e) {
        std::fprintf(stderr,"FAIL_PARKED_MMID_GRAPH %s\n",e.what());
        return 1;
    }
}
