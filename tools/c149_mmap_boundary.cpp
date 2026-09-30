#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"
#include "gguf.h"
#include "llama.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <unistd.h>

namespace {
void require(bool ok, const std::string & why) { if (!ok) throw std::runtime_error(why); }
void write_new(const std::filesystem::path & path, const void * data, size_t size) {
    int fd = open(path.c_str(), O_WRONLY|O_CREAT|O_EXCL, 0600);
    require(fd >= 0, "new output required: " + path.string());
    const auto * p = static_cast<const char *>(data);
    while (size) { ssize_t n = write(fd,p,size); require(n > 0,"output write failed"); p+=n; size-=n; }
    require(close(fd)==0,"output close failed");
}
std::string dims(const int64_t * n) {
    std::string s; for (int i=0;i<4;++i) s+=(i?",":"")+std::to_string(n[i]); return s;
}
std::string strides(const size_t * n) {
    std::string s; for (int i=0;i<4;++i) s+=(i?",":"")+std::to_string(n[i]); return s;
}
struct component { size_t offset,bytes; ggml_type type; };
struct observer {
    std::filesystem::path root;
    std::array<std::array<component,6>,36> canonical{};
    std::array<int,36> chunks{};
    std::array<std::string,36> phases{};
    std::set<std::pair<int,int>> checked;
    std::array<std::set<int>,36> route;
    int fd=-1,step=-1;
    bool prefill=false,save=false;
    size_t bytes=0,count=0,checked_bytes=0;
    std::string index="phase\tlayer\tchunk\tfirst_abs\tstate_tokens\tname\ttype\tne\tnb\tbytes\tfile\n";
    std::string checks="phase\tlayer\texpert\tcomponent\toffset\tbytes\tbuffer\tstatus\n";
    std::string devices="phase\tlayer\tstage\tbuffer\n";
};
std::vector<int32_t> routed(ggml_tensor * t) {
    require(t && t->type==GGML_TYPE_I32 && t->ne[0]==4 && t->ne[1]>=1 && t->ne[1]<=32,"route shape");
    std::vector<uint8_t> data(ggml_nbytes(t));ggml_backend_tensor_get(t,data.data(),0,data.size());
    std::vector<int32_t> ids;
    for (int j=0;j<t->ne[1];++j) for(int k=0;k<4;++k) {
        int32_t id;std::memcpy(&id,data.data()+j*t->nb[1]+k*t->nb[0],4);
        require(id>=0 && id<128,"route ID outside128");ids.push_back(id);
    }
    return ids;
}
void verify_component(observer & s,int layer,int kind,ggml_tensor * t,const std::vector<int32_t> & ids) {
    require(t && ggml_backend_buffer_is_host(t->buffer),"expert component is not host compute buffer");
    const auto & c=s.canonical[layer][kind];
    require(t->type==c.type && ggml_nbytes(t)==128*c.bytes,"expert type/bytes");
    size_t stride=kind<3?t->nb[2]:t->nb[1];
    require(stride==c.bytes && (kind<3?t->ne[2]:t->ne[1])==128,"expert stride/shape");
    require(std::string(ggml_backend_buffer_name(t->buffer))=="CPU","expert buffer must be CPU default without repack/registration");
    std::set<int32_t> uniq(ids.begin(),ids.end());
    for (int id:uniq) {
        if (!s.checked.insert({layer*6+kind,id}).second)continue;
        std::vector<uint8_t> actual(c.bytes),expected(c.bytes);
        ggml_backend_tensor_get(t,actual.data(),id*stride,c.bytes);
        size_t done=0;while(done<c.bytes) {
            ssize_t n=pread(s.fd,expected.data()+done,c.bytes-done,c.offset+id*c.bytes+done);
            require(n>0,"canonical selected-expert read failed");done+=n;
        }
        require(actual==expected,"canonical expert/bias payload mismatch");s.checked_bytes+=c.bytes;
        s.checks+=s.phases[layer]+"\t"+std::to_string(layer)+"\t"+std::to_string(id)+"\t"+
                  std::to_string(kind)+"\t"+std::to_string(c.offset+id*c.bytes)+"\t"+
                  std::to_string(c.bytes)+"\tCPU\tPASS\n";
    }
}
bool callback(ggml_tensor * t,bool ask,void * userdata) {
    auto & s=*static_cast<observer *>(userdata);std::string name=t->name;auto dash=name.rfind('-');
    if(dash==std::string::npos)return false;
    std::string layer_s=name.substr(dash+1),stage=name.substr(0,dash);
    if(layer_s.empty() || !std::all_of(layer_s.begin(),layer_s.end(),[](char c){return c>='0'&&c<='9';}))return false;
    int layer=std::stoi(layer_s);if(layer<0||layer>=36)return false;
    bool selected=stage=="attn_post_norm"||stage=="ffn_moe_logits"||stage=="ffn_moe_logits_biased"||
                  stage=="ffn_moe_topk"||stage=="ffn_moe_weights_softmax"||stage=="ffn_moe_out";
    int kind=stage=="ffn_moe_gate_biased"?0:stage=="ffn_moe_up_biased"?1:stage=="ffn_moe_down_biased"?2:-1;
    if(!selected && kind<0)return false;
    if(ask)return true;
    if(stage=="attn_post_norm") {
        if(s.prefill) {
            int chunk=++s.chunks[layer];require(chunk<6,"extra prefill chunk");
            int n=chunk==5?29:32;require(t->ne[0]==2880&&t->ne[1]==n,"native prefill shape changed");
            s.phases[layer]=chunk==0?"prefill0":chunk==4?"prefill128":chunk==5?"prefill_final":"";
        } else {s.phases[layer]="decode"+std::to_string(s.step);}
    }
    if(stage=="ffn_moe_topk") {auto ids=routed(t);s.route[layer]=std::set<int>(ids.begin(),ids.end());}
    if(kind>=0) {
        require(t->op==GGML_OP_ADD_ID&&t->src[0]&&t->src[0]->op==GGML_OP_MUL_MAT_ID,"expert graph structure");
        auto ids=routed(t->src[2]);require(ids==routed(t->src[0]->src[2]),"biased/matmul routing mismatch");
        require(std::set<int>(ids.begin(),ids.end())==s.route[layer],"authoritative route mismatch");
        verify_component(s,layer,kind,t->src[0]->src[0],ids);verify_component(s,layer,kind+3,t->src[1],ids);
        s.devices+=s.phases[layer]+"\t"+std::to_string(layer)+"\t"+stage+"\t"+ggml_backend_buffer_name(t->buffer)+"\n";
    }
    if(!selected||!s.save||s.phases[layer].empty())return true;
    size_t size=ggml_nbytes(t);require(size>0&&s.bytes+size<=256*1024*1024,"capture size bound");
    std::vector<uint8_t> data(size);ggml_backend_tensor_get(t,data.data(),0,size);
    if(t->type==GGML_TYPE_F32)for(size_t i=0;i<size;i+=4){float v;std::memcpy(&v,data.data()+i,4);require(std::isfinite(v),"nonfinite selected state");}
    std::string file=s.phases[layer]+"_"+std::to_string(layer)+"_"+stage+".bin";
    write_new(s.root/file,data.data(),size);s.bytes+=size;++s.count;
    int chunk=s.prefill?s.chunks[layer]:-1;int pos=s.prefill?chunk*32:189+s.step;
    s.index+=s.phases[layer]+"\t"+std::to_string(layer)+"\t"+std::to_string(chunk)+"\t"+std::to_string(pos)+"\t"+
             std::to_string(s.prefill?(chunk==5?29:32):1)+"\t"+stage+"\t"+ggml_type_name(t->type)+"\t"+
             dims(t->ne)+"\t"+strides(t->nb)+"\t"+std::to_string(size)+"\t"+file+"\n";
    s.devices+=s.phases[layer]+"\t"+std::to_string(layer)+"\t"+stage+"\t"+ggml_backend_buffer_name(t->buffer)+"\n";
    return true;
}
std::vector<llama_token> ids(const char * file,bool continuation) {
    std::ifstream f(file);std::string line;
    while(std::getline(f,line)) {
        if(line.rfind("log_medium\t",0))continue;
        auto begin=line.find('\t')+1,middle=line.find('\t',begin);require(middle!=std::string::npos,"IDs fields");
        std::string numbers=continuation?line.substr(middle+1):line.substr(begin,middle-begin);
        std::vector<llama_token> out;size_t pos=0;
        while(pos<numbers.size()) {auto end=numbers.find(',',pos);out.push_back(std::stoi(numbers.substr(pos,end-pos)));if(end==std::string::npos)break;pos=end+1;}
        return out;
    }throw std::runtime_error("log_medium IDs missing");
}
void decode(llama_context * ctx,const std::vector<llama_token> & tokens,int pos) {
    auto b=llama_batch_init(tokens.size(),0,1);b.n_tokens=tokens.size();
    for(int i=0;i<b.n_tokens;++i){b.token[i]=tokens[i];b.pos[i]=pos+i;b.n_seq_id[i]=1;b.seq_id[i][0]=0;b.logits[i]=i==b.n_tokens-1;}
    int rc=llama_decode(ctx,b);llama_batch_free(b);require(rc==0,"forward failed");llama_synchronize(ctx);
}
}
int main(int argc,char ** argv) {
    try {
        require(argc==5,"MODEL IDS OUTPUT MODE(capacity|boundary)");
        require(std::getenv("TESY_MMAP_NO_PREFETCH") && !std::getenv("GGML_CUDA_REGISTER_HOST") && !std::getenv("LD_PRELOAD"),"frozen mmap environment");
        observer s;s.root=argv[3];s.chunks.fill(-1);require(std::filesystem::create_directory(s.root),"capture must be new");
        ggml_context * meta=nullptr;gguf_context * g=gguf_init_from_file(argv[1],{true,&meta});require(g&&meta,"canonical metadata");
        for(int l=0;l<36;++l)for(int k=0;k<6;++k) {
            std::string name="blk."+std::to_string(l)+".ffn_"+(k%3==0?"gate":k%3==1?"up":"down")+"_exps."+(k<3?"weight":"bias");
            auto i=gguf_find_tensor(g,name.c_str());require(i>=0,"missing canonical component");
            size_t n=gguf_get_tensor_size(g,i);require(n%128==0,"canonical expert split");
            s.canonical[l][k]={gguf_get_data_offset(g)+gguf_get_tensor_offset(g,i),n/128,gguf_get_tensor_type(g,i)};
        }
        gguf_free(g);ggml_free(meta);s.fd=open(argv[1],O_RDONLY|O_CLOEXEC);require(s.fd>=0,"canonical fd");
        llama_backend_init();auto mp=llama_model_default_params();
        llama_model_tensor_buft_override override[]={{R"(\.ffn_(up|down|gate|gate_up)_(ch|)exps)",ggml_backend_cpu_buffer_type()},{nullptr,nullptr}};
        mp.tensor_buft_overrides=override;mp.n_gpu_layers=12;mp.load_mode=LLAMA_LOAD_MODE_MMAP;mp.use_extra_bufts=false;mp.check_tensors=false;
        auto * model=llama_model_load_from_file(argv[1],mp);require(model,"load failed");
        auto cp=llama_context_default_params();cp.n_ctx=8192;cp.n_batch=256;cp.n_ubatch=32;cp.n_seq_max=1;cp.n_threads=8;cp.n_threads_batch=8;
        cp.op_offload=false;cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;cp.type_k=cp.type_v=GGML_TYPE_F16;cp.swa_full=true;cp.offload_kqv=true;cp.kv_unified=true;
        cp.cb_eval=callback;cp.cb_eval_user_data=&s;
        auto * ctx=llama_init_from_model(model,cp);require(ctx,"ctx8192 init failed");
        std::cout<<"C149_CONTEXT_READY ctx8192 ub32 CPU_experts no_prefetch"<<std::endl;
        auto prompt=ids(argv[2],false),cont=ids(argv[2],true);require(prompt.size()==189&&cont.size()==43,"boundary ID counts");
        if(std::string(argv[4])=="capacity") {
            s.prefill=false;s.save=false;decode(ctx,{prompt[0]},0);
            std::cout<<"C149_ONE_FORWARD_PASS"<<std::endl;
        } else {
            require(std::string(argv[4])=="boundary","unknown mode");s.prefill=true;s.save=true;decode(ctx,prompt,0);
            require(std::all_of(s.chunks.begin(),s.chunks.end(),[](int x){return x==5;}),"six prefill chunks all36");
            const int vocab=llama_vocab_n_tokens(llama_model_get_vocab(model));require(vocab==201088,"vocab changed");
            auto logits=[&](std::string name){const float * v=llama_get_logits(ctx);require(v,"missing logits");for(int i=0;i<vocab;++i)require(std::isfinite(v[i]),"logits finite");write_new(s.root/(name+".logits.f32"),v,vocab*sizeof(float));};
            logits("prefill_final");s.prefill=false;
            for(int i=0;i<32;++i){s.step=i;s.save=i==0||i==1||i==7||i==31;decode(ctx,{cont[i]},189+i);if(s.save)logits("decode"+std::to_string(i));}
            const std::string phases="prefill0\nprefill128\nprefill_final\ndecode0\ndecode1\ndecode7\ndecode31\n";
            write_new(s.root/"phases.txt",phases.data(),phases.size());write_new(s.root/"index.tsv",s.index.data(),s.index.size());
            std::cout<<"C149_BOUNDARY_PASS states="<<s.count<<" bytes="<<s.bytes<<" selected_component_bytes="<<s.checked_bytes<<std::endl;
        }
        write_new(s.root/"byte_checks.tsv",s.checks.data(),s.checks.size());write_new(s.root/"devices.tsv",s.devices.data(),s.devices.size());
        close(s.fd);llama_free(ctx);llama_model_free(model);llama_backend_free();return 0;
    }catch(const std::exception & e){std::cerr<<"C149_FAIL: "<<e.what()<<std::endl;return 1;}
}
