#include "llama.h"

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
#include <vector>

#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>

struct case_ids { std::string name; std::vector<llama_token> ids; };

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

static void decode(llama_context * ctx,const std::vector<llama_token> & ids,
                   int offset,int count) {
    llama_batch batch=llama_batch_init(count,0,1);
    for (int i=0;i<count;++i) {
        batch.token[i]=ids[static_cast<size_t>(offset+i)];
        batch.pos[i]=offset+i;
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
    if (argc!=5) {
        std::cerr<<"usage: c3_prefill_probe MODEL.gguf IDS.tsv OUTPUT_PREFIX all|short\n";
        return 2;
    }
    try {
        const auto cases=read_ids(argv[2]);
        const std::string mode=argv[4];
        require(mode=="all" || mode=="short","unknown case mode");
        const size_t n_cases=mode=="short" ? 1 : cases.size();
        const std::string prefix=argv[3];
        require(!std::filesystem::exists(prefix+".f32") &&
                !std::filesystem::exists(prefix+".rows.tsv") &&
                !std::filesystem::exists(prefix+".chunks.tsv"),"no-replace outputs exist");
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
        auto cp=llama_context_default_params();
        cp.n_ctx=4096;cp.n_batch=256;cp.n_ubatch=32;cp.n_seq_max=1;
        cp.n_threads=8;cp.n_threads_batch=8;cp.op_offload=false;
        llama_context * ctx=llama_init_from_model(model,cp);
        require(ctx!=nullptr,"context init failed");
        const int vocab=llama_vocab_n_tokens(llama_model_get_vocab(model));
        require(vocab==201088,"vocabulary changed");
        using trace_phase_fn=void (*)(int);
        auto * trace_phase=reinterpret_cast<trace_phase_fn>(dlsym(RTLD_DEFAULT,"tesy_c3_trace_phase"));
        using trace_overflow_fn=int (*)();
        auto * trace_overflow=reinterpret_cast<trace_overflow_fn>(
            dlsym(RTLD_DEFAULT,"tesy_c3_trace_overflow"));
        if (std::getenv("TESY_C3_TRACE_FILE"))
            require(trace_phase!=nullptr && trace_overflow!=nullptr,"trace interposer missing");
        std::vector<float> logits(static_cast<size_t>(vocab)*n_cases);
        std::string row_index="case\trow\ttokens\n";
        std::string chunks="case\tchunk\tstart\tcount\twall_s\n";
        int trace_id=0;
        for (size_t c=0;c<n_cases;++c) {
            llama_memory_clear(llama_get_memory(ctx),true);
            const auto & item=cases[c];
            double total=0;
            for (int off=0;off<static_cast<int>(item.ids.size());off+=256) {
                const int count=std::min(256,static_cast<int>(item.ids.size())-off);
                ++trace_id;
                if (trace_phase) trace_phase(trace_id);
                const auto t0=std::chrono::steady_clock::now();
                decode(ctx,item.ids,off,count);
                const double seconds=std::chrono::duration<double>(
                    std::chrono::steady_clock::now()-t0).count();
                if (trace_phase) trace_phase(0);
                require(std::isfinite(seconds) && seconds>0,"invalid prefill timing");
                total+=seconds;
                chunks+=item.name+'\t'+std::to_string(trace_id)+'\t'+
                        std::to_string(off)+'\t'+std::to_string(count)+'\t'+
                        std::to_string(seconds)+'\n';
                std::cerr<<"C3_STATS_BEGIN "<<item.name<<' '<<trace_id<<'\n';
                llama_moe_stream_print_stats(model);
                std::cerr<<"C3_STATS_END "<<item.name<<' '<<trace_id<<'\n';
                std::cout<<"C3_CHUNK "<<item.name<<' '<<trace_id<<' '<<count<<' '
                         <<seconds<<'\n'<<std::flush;
            }
            const float * current=llama_get_logits(ctx);
            require(current!=nullptr,"final prompt logits missing");
            for (int i=0;i<vocab;++i)
                require(std::isfinite(current[i]),"nonfinite final prompt logit");
            std::memcpy(logits.data()+c*static_cast<size_t>(vocab),current,
                        static_cast<size_t>(vocab)*sizeof(float));
            row_index+=item.name+'\t'+std::to_string(c)+'\t'+
                       std::to_string(item.ids.size())+'\n';
            std::cout<<"C3_CASE "<<item.name<<" prompt_tokens="<<item.ids.size()
                     <<" prefill_wall_s="<<total<<'\n'<<std::flush;
        }
        write_new(prefix+".f32",logits.data(),logits.size()*sizeof(float));
        write_new(prefix+".rows.tsv",row_index.data(),row_index.size());
        write_new(prefix+".chunks.tsv",chunks.data(),chunks.size());
        if (trace_overflow) require(trace_overflow()==0,"trace missing/overflowed");
        llama_free(ctx);
        llama_model_free(model);
        llama_backend_free();
        return 0;
    } catch (const std::exception & error) {
        std::cerr<<"C3_PREFILL_FAIL: "<<error.what()<<'\n';
        return 1;
    }
}
