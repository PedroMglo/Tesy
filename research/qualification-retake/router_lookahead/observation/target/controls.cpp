// Exercise the actual callback multiplexer and projector without an external backend.
#include "profile.h"
#include <cassert>

int main() {
    using namespace target_probe;
    assert(source_layer("attn_post_norm-0")==0 && source_layer("attn_post_norm-34")==34);
    assert(source_layer("attn_post_norm-03")==-1 && source_layer("attn_post_norm-35")==-1);
    assert(reduced(25,29) && !reduced(25,5) && !reduced(25,20) && !reduced(24,32));
    float one=1, even, odd;
    uint32_t bits=0x3f801000; std::memcpy(&even,&bits,4);
    bits=0x3f803000; std::memcpy(&odd,&bits,4);
    assert(tf32(even)==one && tf32(odd)==1.001953125f);

    llama_model model;
    int positions[]={187,188}; int mask[]={0,1};
    llama_ubatch batch{2,positions,mask};
    std::array<int,2> counts{};
    auto previous=[](ggml_tensor *t,bool ask,void *p) {
        auto& counts=*static_cast<std::array<int,2>*>(p); ++counts[ask ? 0 : 1];
        return std::strcmp(t->name,"attn_post_norm-0")!=0;
    };
    Session s{model,batch,1,nullptr,previous,&counts};
    std::vector<float> x(2*width,0), gamma(width,1), w(width*experts,0), b(experts,0);
    x[0]=1; x[width]=-1;
    for (int i=0;i<experts;++i) w[i*width]=float(i);
    ggml_tensor a{"attn_post_norm-0",x.data(),{width,2,1,1}};
    ggml_tensor g{"gamma",gamma.data(),{width,1,1,1}};
    ggml_tensor weights{"gate",w.data(),{width,experts,1,1}};
    ggml_tensor bias{"bias",b.data(),{experts,1,1,1}};
    for (auto &l:model.layers) { l={&g,&weights,&bias}; }
    assert(Session::callback(&a,true,&s) && Session::callback(&a,false,&s));
    assert(counts[0]==1 && counts[1]==0 && lookahead::ids.size()==2);
    assert((lookahead::ids[0]==std::array<int,4>{127,126,125,124}));
    a.name="attn_post_norm-34";
    assert(Session::callback(&a,true,&s) && Session::callback(&a,false,&s));
    assert(counts[0]==2 && counts[1]==1 && lookahead::ids.size()==3 && lookahead::last_position==188);
    assert((lookahead::ids.back()==std::array<int,4>{0,1,2,3}));
    a.name="unrelated";
    assert(Session::callback(&a,true,&s) && Session::callback(&a,false,&s));
    assert(counts[0]==3 && counts[1]==2 && lookahead::ids.size()==3);
    assert(!pfj::journal->invalid && pfj::gets==10 && pfj::data==2);
    a.name="attn_post_norm-1"; gamma[1]=0;
    assert(Session::callback(&a,true,&s) && Session::callback(&a,false,&s));
    assert(pfj::journal->invalid && lookahead::ids.size()==3);
    return 0;
}
