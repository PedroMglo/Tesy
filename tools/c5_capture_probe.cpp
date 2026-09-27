#include "llama.h"
#include "c4_prefill_clock.h"
#include "ggml-backend.h"
#include "ggml.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <set>
#include <vector>

#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>

struct case_ids { std::string name; std::vector<llama_token> ids; };

struct capture_state {
    std::filesystem::path root;
    int ubatch = 0;
    int next_offset = 0;
    int chunk = -1;
    int chunk_offset = -1;
    int chunk_tokens = 0;
    size_t saved_bytes = 0;
    size_t saved_rows = 0;
    std::set<std::string> seen;
    std::string index = "chunk\tstage\tlayer\tfirst_abs\tn_tokens\ttype\tne\tnb\tbytes\tfile\n";
};

static void require(bool ok, const std::string & message) {
    if (!ok) throw std::runtime_error(message);
}

static std::vector<case_ids> read_ids(const char * path) {
    std::ifstream in(path);
    require(bool(in),"token ID TSV missing");
    std::vector<case_ids> cases;
    std::string line;
    const std::vector<std::string> names{"latency-short","latency-medium","latency-long"};
    const std::vector<size_t> lengths{113,496,1522};
    while (std::getline(in,line)) {
        const auto tab=line.find('\t');
        require(tab!=std::string::npos && cases.size()<3 &&
                line.substr(0,tab)==names[cases.size()],"case order/ID changed");
        case_ids item{line.substr(0,tab),{}};
        size_t first=tab+1;
        while (first<line.size()) {
            const auto comma=line.find(',',first);
            const auto text=line.substr(first,comma==std::string::npos ? comma : comma-first);
            size_t used=0;
            const auto id=std::stol(text,&used);
            require(used==text.size() && id>=0 && id<=INT32_MAX,"bad token ID");
            item.ids.push_back(static_cast<llama_token>(id));
            if (comma==std::string::npos) break;
            first=comma+1;
        }
        require(item.ids.size()==lengths[cases.size()],"frozen token count changed");
        cases.push_back(std::move(item));
    }
    require(cases.size()==3,"three frozen cases required");
    return cases;
}

static void write_new(const std::string & path, const void * data, size_t size) {
    const int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    require(fd>=0,"output exists or cannot be created: "+path);
    const auto * p=static_cast<const uint8_t *>(data);
    while (size) {
        const auto n=write(fd,p,size);
        if (n<=0) {close(fd);throw std::runtime_error("output write failed");}
        p+=n;size-=static_cast<size_t>(n);
    }
    require(close(fd)==0,"output close failed");
}

static std::string dims(const int64_t * values) {
    std::string out;
    for (int i=0;i<GGML_MAX_DIMS;++i) {
        if (i) out+=',';
        out+=std::to_string(values[i]);
    }
    return out;
}

static std::string strides(const size_t * values) {
    std::string out;
    for (int i=0;i<GGML_MAX_DIMS;++i) {
        if (i) out+=',';
        out+=std::to_string(values[i]);
    }
    return out;
}

static void save_logical(capture_state & state, ggml_tensor * t,
                         const std::string & stage, int layer) {
    require(state.chunk >= 0 && state.chunk_offset >= 0, "tensor before chunk anchor");
    require(t->type==GGML_TYPE_F32 && t->ne[0]==2880 && t->ne[1]>=1 &&
            t->ne[1]<=state.chunk_tokens && t->ne[2]==1 && t->ne[3]==1 &&
            t->nb[0]==sizeof(float) && t->nb[1]>=2880*sizeof(float),
            "unexpected activation dtype/shape/strides");
    if (stage=="attn_norm" || layer<35)
        require(t->ne[1]==state.chunk_tokens, "normal layer has missing token outputs");
    int first_abs=state.chunk_offset;
    if (layer==35 && t->ne[1]==1) first_abs+=state.chunk_tokens-1;
    const std::string key=std::to_string(state.chunk)+":"+stage+":"+std::to_string(layer);
    require(state.seen.insert(key).second, "duplicate capture state ID");
    const size_t nbytes=ggml_nbytes(t);
    require(nbytes>0 && nbytes<=2u*1024u*1024u, "activation tensor outside size bound");
    std::vector<uint8_t> raw(nbytes);
    ggml_backend_tensor_get(t,raw.data(),0,raw.size());
    const size_t row_bytes=2880*sizeof(float);
    std::vector<uint8_t> logical(static_cast<size_t>(t->ne[1])*row_bytes);
    for (int64_t token=0;token<t->ne[1];++token) {
        const size_t off=static_cast<size_t>(token)*t->nb[1];
        require(off+row_bytes<=raw.size(), "logical row outside tensor storage");
        std::memcpy(logical.data()+static_cast<size_t>(token)*row_bytes,
                    raw.data()+off,row_bytes);
    }
    for (size_t i=0;i<logical.size();i+=sizeof(float)) {
        float v;
        std::memcpy(&v,logical.data()+i,sizeof(v));
        require(std::isfinite(v), "non-finite activation");
    }
    state.saved_bytes+=logical.size();
    require(state.saved_bytes<=128u*1024u*1024u,"capture volume bound");
    const std::string file="chunk"+std::to_string(state.chunk)+"_"+stage+"_"+
                           std::to_string(layer)+".f32";
    write_new((state.root/file).string(),logical.data(),logical.size());
    state.index+=std::to_string(state.chunk)+'\t'+stage+'\t'+std::to_string(layer)+'\t'+
                 std::to_string(first_abs)+'\t'+std::to_string(t->ne[1])+'\t'+
                 ggml_type_name(t->type)+'\t'+dims(t->ne)+'\t'+strides(t->nb)+'\t'+
                 std::to_string(logical.size())+'\t'+file+'\n';
    ++state.saved_rows;
}

static bool capture(ggml_tensor * t,bool ask,void * user) {
    auto & state=*static_cast<capture_state *>(user);
    const std::string name=t->name;
    const bool anchor=name=="attn_norm-0";
    const bool layer_out=name.rfind("l_out-",0)==0;
    if (!anchor && !layer_out) return false;
    if (ask) return true;
    if (anchor) {
        require(state.next_offset<113,"extra internal microbatch");
        state.chunk++;
        state.chunk_offset=state.next_offset;
        state.chunk_tokens=std::min(state.ubatch,113-state.next_offset);
        state.next_offset+=state.chunk_tokens;
        save_logical(state,t,"attn_norm",0);
        return true;
    }
    const std::string tail=name.substr(6);
    require(!tail.empty() && std::all_of(tail.begin(),tail.end(),
           [](char c){return c>='0'&&c<='9';}),"bad l_out layer name");
    const int layer=std::stoi(tail);
    require(layer>=0 && layer<36,"l_out layer outside target");
    save_logical(state,t,"l_out",layer);
    return true;
}

static void decode(llama_context * ctx,const std::vector<llama_token> & ids,
                   int offset,int count,int position_base=0) {
    llama_batch batch=llama_batch_init(count,0,1);
    for (int i=0;i<count;++i) {
        batch.token[i]=ids[static_cast<size_t>(offset+i)];
        batch.pos[i]=position_base+offset+i;
        batch.n_seq_id[i]=1;
        batch.seq_id[i][0]=0;
        batch.logits[i]=i==count-1;
    }
    batch.n_tokens=count;
    const int rc=llama_decode(ctx,batch);
    llama_batch_free(batch);
    require(rc==0,"llama_decode failed");
}

int main(int argc,char ** argv) {
    if (argc!=7) {
        std::cerr<<"usage: c5_capture_probe MODEL.gguf IDS.tsv OUTPUT_PREFIX short --ubatch 32|64\n";
        return 2;
    }
    try {
        const auto cases=read_ids(argv[2]);
        const std::string mode=argv[4];
        require(mode=="short" && std::string(argv[5])=="--ubatch", "unknown capture mode");
        const int ubatch=std::stoi(argv[6]);
        require(ubatch==32 || ubatch==64,"ubatch outside frozen 32/64 gate");
        capture_state state;
        state.root=std::string(argv[3])+".raw";
        state.ubatch=ubatch;
        const size_t first_case=mode=="long" ? 2 : 0;
        const size_t selected_cases=mode=="all" ? 3 : 1;
        const std::string prefix=argv[3];
        require(!std::filesystem::exists(prefix+".f32") &&
                !std::filesystem::exists(prefix+".rows.tsv") &&
                !std::filesystem::exists(prefix+".chunks.tsv") &&
                !std::filesystem::exists(prefix+".cases.tsv") &&
                !std::filesystem::exists(prefix+".ops.tsv") &&
                !std::filesystem::exists(state.root),"no-replace outputs exist");
        require(std::filesystem::create_directory(state.root),"capture root creation failed");
        const auto load_start=std::chrono::steady_clock::now();
        llama_backend_init();
        auto mp=llama_model_default_params();
        mp.n_gpu_layers=8;
        mp.use_mmap=false;
        mp.use_direct_io=true;
        mp.use_extra_bufts=false;
        mp.moe_stream=true;
        mp.moe_stream_slots=32;
        mp.moe_stream_io_threads=4;
        mp.moe_stream_direct=true;
        llama_model * model=llama_model_load_from_file(argv[1],mp);
        require(model!=nullptr,"model load failed");
        const double model_load_s=std::chrono::duration<double>(
            std::chrono::steady_clock::now()-load_start).count();
        const auto context_start=std::chrono::steady_clock::now();
        auto cp=llama_context_default_params();
        cp.n_ctx=4096;cp.n_batch=256;cp.n_ubatch=ubatch;cp.n_seq_max=1;
        cp.n_threads=8;cp.n_threads_batch=8;cp.op_offload=false;
        cp.cb_eval=capture;cp.cb_eval_user_data=&state;
        llama_context * ctx=llama_init_from_model(model,cp);
        require(ctx!=nullptr,"context init failed");
        const double context_init_s=std::chrono::duration<double>(
            std::chrono::steady_clock::now()-context_start).count();
        const int vocab=llama_vocab_n_tokens(llama_model_get_vocab(model));
        require(vocab==201088,"vocabulary changed");
        using trace_phase_fn=void (*)(int);
        auto * trace_phase=reinterpret_cast<trace_phase_fn>(dlsym(RTLD_DEFAULT,"tesy_c3_trace_phase"));
        using trace_overflow_fn=int (*)();
        auto * trace_overflow=reinterpret_cast<trace_overflow_fn>(
            dlsym(RTLD_DEFAULT,"tesy_c3_trace_overflow"));
        if (std::getenv("TESY_C3_TRACE_FILE"))
            require(trace_phase!=nullptr && trace_overflow!=nullptr,"trace interposer missing");
        const std::vector<llama_token> continuation = mode=="long" ?
            std::vector<llama_token>{16681,353,1302,2570} : std::vector<llama_token>{};
        std::vector<float> logits(static_cast<size_t>(vocab)*(selected_cases+continuation.size()));
        std::string row_index="case\trow\ttokens\n";
        std::string chunks="case\tchunk\tstart\tcount\tdispatch_s\n";
        std::string case_times="case\ttokens\tdispatch_s\tcompletion_s\tpending_tail_s\tclear_and_quiesce_s\n";
        int trace_id=0;
        for (size_t c=0;c<selected_cases;++c) {
            const auto & item=cases[first_case+c];
            const int count=static_cast<int>(item.ids.size());
            std::vector<double> chunk_dispatch_s(static_cast<size_t>((count+255)/256));
            const float * current=nullptr;
            double quiesce_s=0;
            ++trace_id;
            if (trace_phase) trace_phase(trace_id);
            const auto timing=c4_measure_prefill(count,256,
                [&] {
                    const auto start=std::chrono::steady_clock::now();
                    llama_memory_clear(llama_get_memory(ctx),true);
                    llama_synchronize(ctx);
                    quiesce_s=std::chrono::duration<double>(
                        std::chrono::steady_clock::now()-start).count();
                },
                [&](int offset,int n) { decode(ctx,item.ids,offset,n); },
                [&] { current=llama_get_logits(ctx); return current!=nullptr; },
                chunk_dispatch_s);
            if (trace_phase) trace_phase(0);
            for (size_t chunk=0;chunk<chunk_dispatch_s.size();++chunk) {
                const int off=static_cast<int>(chunk)*256;
                const int n=std::min(256,count-off);
                chunks+=item.name+'\t'+std::to_string(chunk)+'\t'+
                        std::to_string(off)+'\t'+std::to_string(n)+'\t'+
                        std::to_string(chunk_dispatch_s[chunk])+'\n';
            }
            case_times+=item.name+'\t'+std::to_string(count)+'\t'+
                std::to_string(timing.dispatch_s)+'\t'+
                std::to_string(timing.completion_s)+'\t'+
                std::to_string(timing.pending_tail_s)+'\t'+
                std::to_string(quiesce_s)+'\n';
            std::cerr<<"C5_STATS_BEGIN "<<item.name<<'\n';
            llama_moe_stream_print_stats(model);
            std::cerr<<"C5_STATS_END "<<item.name<<'\n';
            for (int i=0;i<vocab;++i)
                require(std::isfinite(current[i]),"nonfinite final prompt logit");
            std::memcpy(logits.data()+c*static_cast<size_t>(vocab),current,
                        static_cast<size_t>(vocab)*sizeof(float));
            row_index+=item.name+'\t'+std::to_string(c)+'\t'+
                       std::to_string(item.ids.size())+'\n';
            if (mode=="long") {
                for (size_t i=0;i<continuation.size();++i) {
                    decode(ctx,continuation,static_cast<int>(i),1,count);
                    current=llama_get_logits(ctx);
                    require(current!=nullptr,"teacher-forced logits missing");
                    for (int j=0;j<vocab;++j)
                        require(std::isfinite(current[j]),"nonfinite teacher-forced logit");
                    std::memcpy(logits.data()+(i+1)*static_cast<size_t>(vocab),current,
                                static_cast<size_t>(vocab)*sizeof(float));
                    row_index+=item.name+"-tf"+std::to_string(i+1)+"-id"+
                        std::to_string(continuation[i])+'\t'+std::to_string(i+1)+'\t'+
                        std::to_string(count+i+1)+'\n';
                }
            }
            std::cout<<"C5_CASE "<<item.name<<" prompt_tokens="<<item.ids.size()
                     <<" dispatch_s="<<timing.dispatch_s
                     <<" completion_s="<<timing.completion_s
                     <<" pending_tail_s="<<timing.pending_tail_s<<'\n'<<std::flush;
        }
        require(state.next_offset==113 && state.chunk+1==(113+ubatch-1)/ubatch,
                "missing internal microbatch anchor");
        for (int chunk=0;chunk<=state.chunk;++chunk)
            for (int layer=0;layer<35;++layer)
                require(state.seen.count(std::to_string(chunk)+":l_out:"+
                                         std::to_string(layer))==1,
                        "missing normal-layer output");
        write_new((state.root/"index.tsv").string(),state.index.data(),state.index.size());
        std::cout<<"C5_CAPTURE rows="<<state.saved_rows<<" bytes="<<state.saved_bytes
                 <<" chunks="<<state.chunk+1<<'\n';
        const auto export_start=std::chrono::steady_clock::now();
        write_new(prefix+".f32",logits.data(),logits.size()*sizeof(float));
        write_new(prefix+".rows.tsv",row_index.data(),row_index.size());
        write_new(prefix+".chunks.tsv",chunks.data(),chunks.size());
        write_new(prefix+".cases.tsv",case_times.data(),case_times.size());
        const double export_s=std::chrono::duration<double>(
            std::chrono::steady_clock::now()-export_start).count();
        const std::string ops="model_load_s\tcontext_init_s\texport_s\n"+
            std::to_string(model_load_s)+'\t'+std::to_string(context_init_s)+'\t'+
            std::to_string(export_s)+'\n';
        write_new(prefix+".ops.tsv",ops.data(),ops.size());
        if (trace_overflow) require(trace_overflow()==0,"trace missing/overflowed");
        llama_free(ctx);
        llama_model_free(model);
        llama_backend_free();
        return 0;
    } catch (const std::exception & error) {
        std::cerr<<"C5_CAPTURE_FAIL: "<<error.what()<<'\n';
        return 1;
    }
}
