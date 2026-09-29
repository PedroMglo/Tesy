// One identical P12/8K 2009+192 teacher-forced call plan for C35 and C75.
#include "llama.h"
#include "ggml.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <fcntl.h>
#include <unistd.h>

using clock_type = std::chrono::steady_clock;

static void check(bool value, const char * why) {
    if (!value) throw std::runtime_error(why);
}

static double seconds(clock_type::time_point begin) {
    return std::chrono::duration<double>(clock_type::now()-begin).count();
}

static std::vector<llama_token> parse_ids(const std::string & text) {
    std::vector<llama_token> result;
    size_t start=0;
    while (start<text.size()) {
        const size_t end=text.find(',',start);
        const std::string word=text.substr(start,end==std::string::npos ? end : end-start);
        size_t used=0;
        const long value=std::stol(word,&used);
        check(used==word.size() && value>=0 && value<201088,"invalid frozen ID");
        result.push_back(static_cast<llama_token>(value));
        if (end==std::string::npos) break;
        start=end+1;
    }
    return result;
}

static std::pair<std::vector<llama_token>,std::vector<llama_token>> input(const char * path) {
    std::ifstream stream(path);
    check(bool(stream),"missing frozen IDs");
    std::string first,second,extra;
    check(bool(std::getline(stream,first)) && bool(std::getline(stream,second)) &&
          !bool(std::getline(stream,extra)),"ID row count invalid");
    check(first.rfind("prompt\t",0)==0 && second.rfind("continuation192\t",0)==0,
          "ID labels invalid");
    auto prompt=parse_ids(first.substr(7));
    auto continuation=parse_ids(second.substr(16));
    check(prompt.size()==2009 && continuation.size()==192,"ID count differs from freeze");
    return {std::move(prompt),std::move(continuation)};
}

static void write_new(const std::string & path,const void * data,size_t bytes) {
    const int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    check(fd>=0,"no-replace output open failed");
    const auto * ptr=static_cast<const unsigned char *>(data);
    while (bytes) {
        const ssize_t n=write(fd,ptr,bytes);
        check(n>0,"output write failed");
        ptr+=n;bytes-=static_cast<size_t>(n);
    }
    check(close(fd)==0,"output close failed");
}

static void decode(llama_context * ctx,const std::vector<llama_token> & ids,
                   int offset,int count,int base,int output_abs) {
    llama_batch batch=llama_batch_init(count,0,1);
    for (int i=0;i<count;++i) {
        batch.token[i]=ids[static_cast<size_t>(offset+i)];
        batch.pos[i]=base+offset+i;
        batch.n_seq_id[i]=1;
        batch.seq_id[i][0]=0;
        batch.logits[i]=(base+offset+i==output_abs);
    }
    batch.n_tokens=count;
    const int rc=llama_decode(ctx,batch);
    llama_batch_free(batch);
    check(rc==0,"llama_decode failed");
    llama_synchronize(ctx);
}

static void append_logits(llama_context * ctx,int vocab,std::vector<float> & output) {
    const float * logits=llama_get_logits(ctx);
    check(logits!=nullptr,"missing full logits");
    for (int i=0;i<vocab;++i) check(std::isfinite(logits[i]),"nonfinite full logits");
    output.insert(output.end(),logits,logits+vocab);
}

int main(int argc,char ** argv) {
    if (argc==3 && std::strcmp(argv[1],"--check-input")==0) {
        try {
            const auto [prompt,continuation]=input(argv[2]);
            std::cout << "C109_INPUT_PASS prompt=" << prompt.size()
                      << " continuation=" << continuation.size() << '\n';
            return 0;
        } catch (const std::exception & error) {
            std::cerr << "C109_INPUT_FAIL " << error.what() << '\n';
            return 1;
        }
    }
    if ((argc!=6 && argc!=7) || std::strcmp(argv[4],"--arm")!=0 ||
        (argc==7 && std::strcmp(argv[6],"--canary")!=0)) {
        std::cerr << "usage: c109_probe MODEL IDS_TSV OUTPUT_PREFIX --arm A|B|C [--canary]\n";
        return 2;
    }
    try {
        const std::string arm=argv[5];
        check(arm=="A" || arm=="B" || arm=="C","invalid arm");
        check(std::getenv("LLAMA_MOE_STREAM_NO_PRELOAD")==nullptr &&
              std::getenv("TESY_CPU_FA_PREFILL_VEC_COMPAT")==nullptr &&
              std::getenv("LD_PRELOAD")==nullptr,"profile environment differs from freeze");
        const char * flag=std::getenv("TESY_CPU_WAVE_SKIP_PARKED");
        check((arm=="C" && flag && std::strcmp(flag,"1")==0) ||
              (arm!="C" && !flag),"wave flag/arm mismatch");
        auto [prompt,continuation]=input(argv[2]);
        const bool canary=argc==7;
        if (canary) {
            prompt.resize(16);
            continuation.resize(2);
        }
        const std::string prefix=argv[3];
        const auto started=clock_type::now();
        llama_backend_init();
        auto mp=llama_model_default_params();
        mp.n_gpu_layers=12;mp.use_mmap=false;mp.use_direct_io=true;
        mp.use_extra_bufts=false;mp.moe_stream=true;mp.moe_stream_slots=32;
        mp.moe_stream_io_threads=4;mp.moe_stream_direct=true;
        llama_model * model=llama_model_load_from_file(argv[1],mp);
        check(model!=nullptr,"model load failed");
        const double model_load_s=seconds(started);
        const auto ctx_started=clock_type::now();
        auto cp=llama_context_default_params();
        cp.n_ctx=8192;cp.n_batch=256;cp.n_ubatch=32;cp.n_seq_max=1;
        cp.n_threads=8;cp.n_threads_batch=8;cp.op_offload=false;
        cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;
        cp.type_k=GGML_TYPE_F16;cp.type_v=GGML_TYPE_F16;
        cp.swa_full=true;cp.offload_kqv=true;cp.kv_unified=true;
        llama_context * ctx=llama_init_from_model(model,cp);
        check(ctx!=nullptr,"context init failed");
        const double context_init_s=seconds(ctx_started);
        const int vocab=llama_vocab_n_tokens(llama_model_get_vocab(model));
        check(vocab==201088,"vocab differs from freeze");
        std::cout << "C109_READY arm=" << arm << " prompt=" << prompt.size()
                  << " continuation=" << continuation.size() << '\n' << std::flush;
        llama_memory_clear(llama_get_memory(ctx),true);
        llama_synchronize(ctx);
        std::vector<float> full_logits;
        full_logits.reserve((1+continuation.size())*static_cast<size_t>(vocab));
        const auto prefill_started=clock_type::now();
        for (int offset=0;offset<static_cast<int>(prompt.size());offset+=256) {
            const int count=std::min(256,static_cast<int>(prompt.size())-offset);
            decode(ctx,prompt,offset,count,0,static_cast<int>(prompt.size())-1);
        }
        const double prefill_s=seconds(prefill_started);
        append_logits(ctx,vocab,full_logits);
        std::string steps="step\tposition\ttoken_id\tcompletion_s\n";
        std::vector<double> durations;
        durations.reserve(continuation.size());
        for (int step=0;step<static_cast<int>(continuation.size());++step) {
            const auto begin=clock_type::now();
            decode(ctx,continuation,step,1,static_cast<int>(prompt.size()),
                   static_cast<int>(prompt.size())+step);
            const double elapsed=seconds(begin);
            check(elapsed>0 && std::isfinite(elapsed),"invalid step duration");
            durations.push_back(elapsed);
            append_logits(ctx,vocab,full_logits);
            steps+=std::to_string(step)+'\t'+std::to_string(prompt.size()+step)+'\t'+
                   std::to_string(continuation[static_cast<size_t>(step)])+'\t'+
                   std::to_string(elapsed)+'\n';
        }
        const auto sum=[](const std::vector<double> & a,int begin,int end) {
            double value=0;for (int i=begin;i<end;++i)value+=a[static_cast<size_t>(i)];return value;
        };
        const int total=static_cast<int>(durations.size());
        const std::string ops="arm\tprompt_tokens\tcontinuation_tokens\tmodel_load_s\tcontext_init_s\tprefill_s\tdecode_s\tstep1_64_s\tstep65_192_s\tstep1_77_s\tlogit_rows\n"+
            arm+'\t'+std::to_string(prompt.size())+'\t'+std::to_string(continuation.size())+'\t'+
            std::to_string(model_load_s)+'\t'+std::to_string(context_init_s)+'\t'+
            std::to_string(prefill_s)+'\t'+std::to_string(sum(durations,0,total))+'\t'+
            std::to_string(sum(durations,0,std::min(64,total)))+'\t'+
            std::to_string(sum(durations,std::min(64,total),total))+'\t'+
            std::to_string(sum(durations,0,std::min(77,total)))+'\t'+
            std::to_string(1+total)+'\n';
        write_new(prefix+".steps.tsv",steps.data(),steps.size());
        write_new(prefix+".ops.tsv",ops.data(),ops.size());
        write_new(prefix+".logits.f32",full_logits.data(),full_logits.size()*sizeof(float));
        llama_free(ctx);llama_model_free(model);llama_backend_free();
        std::cout << "C109_DONE arm=" << arm << " prefill_s=" << prefill_s
                  << " decode_s=" << sum(durations,0,total) << '\n' << std::flush;
    } catch (const std::exception & error) {
        std::cerr << "C109_FAIL " << error.what() << '\n';
        return 1;
    }
    return 0;
}
