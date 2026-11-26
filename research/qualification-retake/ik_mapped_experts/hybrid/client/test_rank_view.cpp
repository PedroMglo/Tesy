#include "rank_view.hpp"
#include <cstdio>
#include <cstdlib>

static void need(bool ok) { if (!ok) std::abort(); }
static void run(int width) {
    ggml_context *ctx=ggml_init({4<<20,nullptr,false});
    need(ctx);
    auto *source=ggml_new_tensor_2d(ctx,GGML_TYPE_I32,8,width);
    auto *map=ggml_new_tensor_2d(ctx,GGML_TYPE_I32,1,8);
    for(int e=0;e<8;e++) ggml_set_i32_1d(map,e,(e+1)%8);
    for(int t=0;t<width;t++) for(int e=0;e<8;e++)
        ggml_set_i32_1d(source,8*t+e,e<4?(e+t)%8:7);
    auto *logical=ggml_view_2d(ctx,source,4,width,source->nb[1],0);
    ggml_set_name(logical,"ffn_moe_topk-0");
    auto *cont=ggml_cont(ctx,logical);
    auto *flat=ggml_reshape_1d(ctx,cont,4*width);
    auto *gather=ggml_get_rows(ctx,map,flat);
    auto *physical=ggml_reshape_2d(ctx,gather,4,width);
    auto *graph=ggml_new_graph(ctx);
    ggml_build_forward_expand(graph,physical);
    need(ggml_graph_compute_with_ctx(ctx,graph,1)==GGML_STATUS_SUCCESS);
    need(tiny_rank::router(logical->name) && !tiny_rank::router(cont->name) &&
         !tiny_rank::router(flat->name) && !tiny_rank::router(physical->name) &&
         tiny_rank::valid(logical,width) && tiny_rank::valid(physical,width));
    need(!tiny_rank::valid(map,width) && tiny_rank::valid(flat,width)==(width==1));
    for(int t=0;t<width;t++) for(int k=0;k<4;k++) {
        auto value=ggml_get_i32_nd(logical,k,t,0,0);
        need(value==(k+t)%8 && ggml_get_i32_nd(physical,k,t,0,0)==(value+1)%8);
    }
    auto invalid=*logical;
    invalid.nb[1]=12;
    need(!tiny_rank::valid(&invalid,width));
    invalid=*logical;
    invalid.view_offs=ggml_nbytes(invalid.view_src);
    need(!tiny_rank::valid(&invalid,width));
    std::printf("PASS_VIEW width=%d ids=%d logical_pitch=%zu physical_pitch=%zu\n",
                width,4*width,logical->nb[1],physical->nb[1]);
    ggml_free(ctx);
}
int main() { run(32); run(1); }
