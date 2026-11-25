// Common, non-operational C294 client witness for target positions and ordered IDs.
#pragma once
#include "ggml-backend.h"
#include <array>
#include <charconv>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string_view>
#include <vector>

struct routed_witness {
    std::vector<uint8_t> bytes {'W','R','T','1'};

    static void need(bool ok, const char *reason) {
        if (!ok) throw std::runtime_error(reason);
    }
    void begin_call(int first, int size) {
        need(!in_call && !finished && first==total && size>0 && size<=256, "witness call");
        in_call=true; start=first; length=size; used=0;
        byte('C'); word(first); word(size);
    }
    void end_call() {
        need(in_call && used==length, "incomplete witness call");
        close_graph(); in_call=false; total+=length; byte('D');
    }
    void finish() {
        need(!in_call && total>0 && !finished, "incomplete witness");
        finished=true; byte('F');
    }
    // GGML asks once for each scheduled node. Only a true answer yields a
    // delivery after computation/synchronization. Never read at query time.
    bool observe(ggml_tensor *t, bool ask) {
        const std::string_view n(ggml_get_name(t));
        int layer=route_layer(n);
        const bool pos=n=="Qcur-0" && t->op==GGML_OP_ROPE;
        const bool selector=n=="ffn_inp-35" && t->ne[1]>0;
        if (!pos && !selector && layer<0) return false;
        if (layer == 35 && t->ne[1] == 0) {
            need(ask && in_call && width > 0 && used < length && next_layer==35 &&
                 !empty_seen && t->ne[0]==4 && t->type==GGML_TYPE_I32, "unexpected empty final router");
            empty_seen=true;
            return false;
        }
        if (ask) return true;
        need(in_call, "node outside supplied call");
        if (pos) positions(t);
        else if (selector) selection(t);
        else route(layer,t);
        return true;
    }
private:
    int start=0, length=0, used=0, total=0, width=0, next_layer=0;
    bool in_call=false, output_seen=false, empty_seen=false, finished=false;
    static int route_layer(std::string_view n) {
        constexpr std::string_view prefix="ffn_moe_topk-";
        if (n.size()<=prefix.size() || n.substr(0,prefix.size())!=prefix) return -1;
        n.remove_prefix(prefix.size());
        int layer=-1;
        auto end=n.data()+n.size();
        auto parsed=std::from_chars(n.data(),end,layer);
        need(parsed.ec==std::errc() && parsed.ptr==end && layer>=0 && layer<36 &&
             !(n.size()>1 && n[0]=='0'), "invalid target topk name");
        return layer;
    }
    void byte(int value) {
        need(bytes.size()<1024*1024 && value>=0 && value<256, "witness overflow");
        bytes.push_back(static_cast<uint8_t>(value));
    }
    void word(int value) { need(value>=0 && value<65536,"witness word"); byte(value&255); byte(value>>8); }
    void close_graph() {
        if (!width) return;
        bool final=used==length;
        need(next_layer==(final?36:35) && output_seen==final, "missing routed layer or final selector");
        width=next_layer=0; output_seen=false; empty_seen=false; byte('E');
    }
    void positions(ggml_tensor *q) {
        close_graph();
        auto *p=q->src[1];
        need(q->op==GGML_OP_ROPE && p && p->type==GGML_TYPE_I32 &&
             p->ne[0]>0 && p->ne[0]<=32 && p->ne[1]==1 && p->ne[2]==1 && p->ne[3]==1 &&
             p->nb[0]==sizeof(int32_t) && q->ne[2]==p->ne[0], "unexpected RoPE position view");
        width=static_cast<int>(p->ne[0]);
        need(used+width<=length,"unexpected extra ubatch");
        std::array<int32_t,32> actual{};
        ggml_backend_tensor_get(p,actual.data(),0,width*sizeof(int32_t));
        byte('U'); byte(width);
        for(int i=0;i<width;++i) {
            need(actual[i]==start+used+i && actual[i]<8192,"wrong graph position");
            word(actual[i]);
        }
        used+=width;
    }
    void selection(ggml_tensor *t) {
        // Both residual operands at the final FFN are GGML_OP_GET_ROWS using
        // the target's actual requested-output indices for this ubatch.
        need(width>0 && used==length && next_layer==35 && !output_seen &&
             t->op==GGML_OP_ADD && t->ne[1]==1, "unexpected final FFN selector");
        for(int i=0;i<2;++i) {
            auto *get=t->src[i];
            need(get && get->op==GGML_OP_GET_ROWS && get->src[1],"missing final get_rows");
            auto *index=get->src[1];
            need(index->type==GGML_TYPE_I32 && ggml_nelements(index)==1,"last-output index shape");
            int32_t row=-1;
            ggml_backend_tensor_get(index,&row,0,sizeof(row));
            need(row==width-1,"wrong final physical row");
        }
        output_seen=true; byte('O'); byte(width-1);
    }
    void route(int layer, ggml_tensor *t) {
        need(width>0 && layer==next_layer && (layer!=35 || output_seen),"routed layer order");
        const int rows=layer==35?1:width;
        need(t->type==GGML_TYPE_I32 && t->ne[0]==4 && t->ne[1]==rows &&
             t->ne[2]==1 && t->ne[3]==1 && t->nb[0]==4 &&
             t->nb[1]>=16 && t->nb[1]<=512 && t->nb[1]%4==0,"unexpected logical router view");
        size_t span=(rows-1)*t->nb[1]+16;
        std::array<int32_t,32*128> raw{};
        need(span<=ggml_nbytes(t),"strided payload length");
        ggml_backend_tensor_get(t,raw.data(),0,span);
        byte('R'); byte(layer); byte(rows); word(static_cast<int>(t->nb[1]));
        for(int i=0;i<rows;++i) {
            std::array<bool,128> seen{};
            for(int rank=0;rank<4;++rank) {
                const int id=raw[i*(t->nb[1]/4)+rank];
                need(id>=0 && id<128 && !seen[id],"invalid top-4 IDs");
                seen[id]=true; byte(id);
            }
        }
        ++next_layer;
    }
};
