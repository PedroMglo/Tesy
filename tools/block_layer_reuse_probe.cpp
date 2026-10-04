// Bounded layer R2 fidelity client; production runtime stays separate.
#define main previous_native_main
#include "block_native_run.cpp"
#undef main
#include "c262-expert-tiles.h"
#include "c210_direct_reader.h"
#include "ggml-cpu.h"
#include "gguf.h"
#include <array>
#include <set>
#include <functional>
namespace {
struct observer {
    runtime * owner=nullptr;
    bool enabled=false;
    std::filesystem::path root;
    json stages=json::array(),witness=json::array();
    tesy_witness::direct_reader reader;
    std::array<std::array<uint64_t,6>,36> offsets{};
    size_t bytes=0;
    std::set<std::string> emitted;
    void canonical(const char * path) {
        reader.open_file(path);ggml_context * meta=nullptr;gguf_init_params p{true,&meta};auto * f=gguf_init_from_file(path,p);
        check(f&&meta,"canonical metadata missing");
        const std::array<const char*,6> names={"gate_exps.weight","up_exps.weight","down_exps.weight","gate_exps.bias","up_exps.bias","down_exps.bias"};
        for(int l:{0,12,24,25,35})for(int k=0;k<6;++k){const std::string n="blk."+std::to_string(l)+".ffn_"+names[k];const auto i=gguf_find_tensor(f,n.c_str());
            check(i>=0,"canonical tensor missing");auto * t=ggml_get_tensor(meta,n.c_str());
            const size_t per=k<3?4406400:11520;check(t&&ggml_nbytes(t)==128*per&&t->ne[k<3?2:1]==128&&t->type==(k<3?GGML_TYPE_MXFP4:GGML_TYPE_F32),"canonical encoding/shape changed");
            offsets[l][k]=gguf_get_data_offset(f)+gguf_get_tensor_offset(f,i);reader.validate_range(offsets[l][k],128*per);
        }
        check(ggml_used_mem(meta)<=64*1024*1024,"canonical metadata exceeds64MiB");ggml_free(meta);gguf_free(f);
    }
};
struct custom_parameters {ggml_custom_op_t fun;int tasks;void * opaque;};
void consumer(observer & o,ggml_tensor * t,int layer) {
    check(t->op==GGML_OP_CUSTOM||t->op==GGML_OP_MAP_CUSTOM1,"consumer is not a native remap op");custom_parameters p{};std::memcpy(&p,t->op_params,sizeof(p));
    check(p.tasks==1&&p.opaque,"native consumer parameters changed");
    const bool wave=t->op==GGML_OP_CUSTOM;if(wave)check(p.fun==llama_moe_stream_wave_ids,"native wave callback changed");else check(reinterpret_cast<ggml_custom1_op_t>(p.fun)==llama_moe_stream_remap,"native remap callback changed");
    auto * w=wave?static_cast<llama_moe_stream_wave*>(p.opaque):nullptr;auto * sl=wave?w->sl:static_cast<llama_moe_stream_layer*>(p.opaque);const int wave_index=wave?w->wave:-1;check(sl&&sl->il==layer&&sl->n_slots==40,"consumer layer/pool changed");
    const size_t n=ggml_nelements(t);std::vector<int32_t> logical(n),physical(n);check(t->src[0]->type==GGML_TYPE_I32&&ggml_is_contiguous(t->src[0])&&ggml_nbytes(t)==n*4,"consumer ID shape changed");
    ggml_backend_tensor_get(t->src[0],logical.data(),0,n*4);ggml_backend_tensor_get(t,physical.data(),0,n*4);
    std::lock_guard<std::mutex> lock(sl->mgr->mtx);std::set<int> seen;
    const bool cpu=ggml_backend_buffer_is_host(sl->weights[0].cache->buffer);
    for(size_t i=0;i<n;++i){const int e=logical[i],slot=physical[i];check(e>=0&&e<128,"logical expert invalid");
        if(wave&&sl->expert_wave[e]!=wave_index){if(cpu)check(slot==-1,"parked CPU pair lacks sentinel");continue;}
        check(slot>=0&&slot<40&&sl->slot_expert[slot]==e&&sl->slot_state[slot]==LLAMA_MOE_STREAM_SLOT_RESIDENT&&sl->slot_gen[slot]>0&&sl->keep[slot]&&!sl->slot_claimed[slot],"consumer generation/lifetime invalid");
        if(!seen.insert(e).second)continue;
        if(layer!=0&&layer!=12&&layer!=24&&layer!=25&&layer!=35)continue;
        const auto & l=o.owner->model->layers[layer];const std::array<ggml_tensor*,6> tensors={l.ffn_gate_exps,l.ffn_up_exps,l.ffn_down_exps,l.ffn_gate_exps_b,l.ffn_up_exps_b,l.ffn_down_exps_b};
        for(int k=0;k<6;++k){const size_t size=k<3?4406400:11520;std::vector<uint8_t> expected(size),actual(size);
            o.reader.read(expected.data(),size,o.offsets[layer][k]+static_cast<uint64_t>(e)*size);check(tensors[k],"consumer tensor missing");
            ggml_backend_tensor_get(tensors[k],actual.data(),static_cast<size_t>(k<3?slot:e)*size,size);check(expected==actual,"consumer byte mismatch");
            o.witness.push_back({{"layer",layer},{"wave",wave_index},{"logical",e},{"slot",slot},{"generation",sl->slot_gen[slot]},{"component",k},{"bytes",size}});
        }
    }
}
bool observe(ggml_tensor * t,bool ask,void * pointer){auto & o=*static_cast<observer*>(pointer);const bool row_interest=o.owner&&observe_rows(t,ask,&o.owner->rows);if(!o.enabled)return row_interest;
    const std::string name=ggml_get_name(t);const auto sep=name.rfind('-');if(sep==std::string::npos)return row_interest;
    const std::string stage=name.substr(0,sep);int layer=-1;try{layer=std::stoi(name.substr(sep+1));}catch(...){return row_interest;}if(layer<0||layer>=36||name!=stage+"-"+std::to_string(layer))return row_interest;
    const std::set<std::string> wanted={"attn_post_norm","ffn_moe_logits","ffn_moe_logits_biased","ffn_moe_topk","ffn_moe_weights_softmax","ffn_moe_out"};
    if(stage=="c262_shared_slots"||stage=="ffn_moe_topk_stream"){if(ask)return true;consumer(o,t,layer);return true;}
    if(!wanted.count(stage))return row_interest;if(ask)return true;
    check(o.emitted.insert(name).second,"duplicate complete-layer stage");check(t->type==GGML_TYPE_F32||t->type==GGML_TYPE_I32,"capture dtype changed");
    std::vector<uint8_t> raw(ggml_nbytes(t));ggml_backend_tensor_get(t,raw.data(),0,raw.size());std::vector<float> compact(ggml_nelements(t));size_t i=0;
    for(int64_t d=0;d<t->ne[3];++d)for(int64_t c=0;c<t->ne[2];++c)for(int64_t b=0;b<t->ne[1];++b)for(int64_t a=0;a<t->ne[0];++a){const size_t off=a*t->nb[0]+b*t->nb[1]+c*t->nb[2]+d*t->nb[3];check(off+4<=raw.size(),"capture stride outside bytes");std::memcpy(&compact[i],raw.data()+off,4);if(t->type==GGML_TYPE_F32)check(std::isfinite(compact[i]),"nonfinite stage");++i;}
    o.bytes+=compact.size()*4;check(o.bytes<=256*1024*1024,"capture bound exceeded");binary(o.root/(name+".bin"),compact);
    o.stages.push_back({{"name",name},{"layer",layer},{"stage",stage},{"dtype",t->type==GGML_TYPE_F32?"f32":"i32"},{"ne",{t->ne[0],t->ne[1],t->ne[2],t->ne[3]}},{"bytes",compact.size()*4},{"file",name+".bin"}});return true;
}
void ancestors(ggml_tensor * t,std::set<ggml_tensor*> & nodes,std::set<std::string> & names){if(!t||!nodes.insert(t).second)return;names.insert(ggml_get_name(t));for(auto * s:t->src)ancestors(s,nodes,names);}
void graph_test(){llama_backend_init();ggml_init_params cp{16*1024*1024,nullptr,true};auto * c=ggml_init(cp);check(c,"test metadata allocation failed");llama_moe_stream manager(36,40,4,true);
    std::array<ggml_tensor*,3> w{};for(int i=0;i<3;++i){auto * src=ggml_new_tensor_3d(c,GGML_TYPE_F32,4,4,128);w[i]=manager.create_cache_tensor(0,ggml_backend_cpu_buffer_type(),src,0,0);}manager.alloc_bufs(false);
    auto * x=ggml_new_tensor_3d(c,GGML_TYPE_F32,4,1,153);auto * ids=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,153);
    for(bool reuse:{false,true}){auto * g=ggml_new_graph_custom(c,8192,false);std::vector<ggml_tensor*> slots;int gemms=0;
        auto * result=c262_expert_tiles(c,g,manager.layer(0),x,ids,153,4,128,4,reuse,
            [&](ggml_tensor * cur,ggml_tensor * pi,ggml_tensor *){check(cur->ne[2]==32||cur->ne[2]==25,"native MMID shape changed");++gemms;return ggml_mul_mat_id(c,w[0],cur,pi);},
            [&](ggml_tensor * t){slots.push_back(t);});ggml_build_forward_expand(g,result);check(result->ne[2]==153,"tile concat lost positions");
        check(slots.size()==static_cast<size_t>(reuse?8:38)&&gemms==(reuse?40:38),"wave/tile plan changed");
        // The scheduler names derived views/contiguous copies from their source.
        // Only the exact native callback name denotes a remap consumer.
        observer probe;probe.enabled=true;ggml_set_name(slots[0],"c262_shared_slots-0");
        check(observe(slots[0],true,&probe),"native consumer name omitted");
        auto * derived=ggml_view_2d(c,slots[0],4,1,slots[0]->nb[1],0);
        check(!observe(derived,true,&probe),"derived view mistaken for native consumer");
        auto * copied=ggml_cont(c,derived);check(!observe(copied,true,&probe),"derived contiguous copy mistaken for consumer");
        if(reuse){const auto complete=[&]{std::set<ggml_tensor*> nodes;std::set<std::string> names;ancestors(slots[1]->src[1],nodes,names);for(int t=0;t<5;++t)if(!names.count("c262-tile-"+std::to_string(t)+"-wave-0"))return false;return true;};
            check(complete(),"replacement lacks all five consumers");auto * full=slots[1]->src[1];slots[1]->src[1]=ggml_graph_node(g,0);check(!complete(),"missing-consumer mutation escaped");slots[1]->src[1]=full;}
    }
    ggml_free(c);llama_backend_free();std::cout<<"{\"status\":\"PASS_REAL_C262_GRAPH_METADATA_AND_LIFETIME_COUNTERPROOF\",\"weights_loaded\":false,\"forwards\":0}\n";
}
}
int main(int argc,char ** argv){try{if(argc==2&&std::string(argv[1])=="--graph-self-test"){graph_test();return 0;}
    check(argc==7&&std::string(argv[6])=="v1","usage MODEL FIXTURE CASE NEWROOT MODE(r0|r2-tile|r2-reuse) v1");
    const std::filesystem::path root=argv[4];check(!std::filesystem::exists(root),"root reused");std::filesystem::create_directories(root);
    check(getenv("TESY_C262_LAYER_SPAN")&&std::string(getenv("TESY_C262_LAYER_SPAN"))=="153","layer-span identity absent");const std::string mode=argv[5];check(mode=="r0"||mode=="r2-tile"||mode=="r2-reuse","mode invalid");
    std::ifstream f(argv[2]);json fixtures;f>>fixtures;check(bool(f),"fixture missing");const auto ids=fixtures.at(argv[3]).at("ids").get<std::vector<llama_token>>();const auto continuation=fixtures.at(argv[3]).at("continuation_ids").get<std::vector<llama_token>>();check(ids.size()==2197&&continuation.size()>=6,"frozen warm153 input absent");
    observer o;o.root=root;if(mode!="r0")o.canonical(argv[1]);runtime r(argv[1],observe,&o);o.owner=&r;
    for(int pos=0;pos<2044;pos+=256){const int n=std::min(256,2044-pos);r.call(std::vector<llama_token>(ids.begin()+pos,ids.begin()+pos+n),pos,false);}
    const auto initial=r.snapshot();const int m=mode=="r0"?0:(mode=="r2-tile"?1:2);check(llama_c262_set_layer_mode(r.ctx,m),"mode change rejected");o.enabled=m!=0;
    auto logits=r.call(std::vector<llama_token>(ids.begin()+2044,ids.end()),2044,false);o.enabled=false;binary(root/"prefill.logits.f32",logits);const auto final=r.snapshot();std::vector<int> winners={greedy(logits.data())};
    for(int i=0;i<6;++i){logits=r.call({continuation[i]},2197+i,false);binary(root/("decode"+std::to_string(i)+".logits.f32"),logits);winners.push_back(greedy(logits.data()));}
    save(root/"result.json",{{"status","COMPLETE_NATIVE_LAYER_REUSE_FIDELITY"},{"mode",mode},{"input_ids",ids},{"teacher_forced_ids",std::vector<int>(continuation.begin(),continuation.begin()+6)},{"native_argmax_ids",winners},{"initial",initial},{"after_prefill",final},{"stages",o.stages},{"witness",o.witness},{"capture_bytes",o.bytes},{"layer_span",153},{"ffn_tile",32},{"last_layer_rows",r.rows.ffn}});return 0;
}catch(const std::exception & e){std::cerr<<"LAYER_REUSE_FAIL "<<e.what()<<'\n';return 1;}}
