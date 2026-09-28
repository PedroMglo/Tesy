#include "llama.h"
#include "ggml.h"
#include "c4_prefill_clock.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <unistd.h>

namespace {

struct input_case {
    std::string name;
    std::vector<llama_token> conditioning;
    std::vector<llama_token> prompt;
    std::vector<llama_token> continuation;
};

void check(bool yes, const std::string & why) {
    if (!yes) throw std::runtime_error(why);
}

std::vector<llama_token> ids(const std::string & text) {
    std::vector<llama_token> out;
    size_t begin=0;
    while (begin<text.size()) {
        const size_t comma=text.find(',',begin);
        const auto part=text.substr(begin,comma==std::string::npos ? comma : comma-begin);
        size_t used=0;
        const long id=std::stol(part,&used);
        check(used==part.size() && id>=0 && id<=INT32_MAX,"invalid frozen token ID");
        out.push_back(static_cast<llama_token>(id));
        if (comma==std::string::npos) break;
        begin=comma+1;
    }
    check(!out.empty(),"empty frozen IDs");
    return out;
}

input_case workload(const char * path, const std::string & name) {
    std::ifstream in(path);
    check(bool(in),"C73 frozen IDs missing");
    std::string line;
    std::vector<std::pair<std::string,std::vector<llama_token>>> rows;
    while (std::getline(in,line)) {
        const auto tab=line.find('\t');
        check(tab!=std::string::npos && line.find('\t',tab+1)==std::string::npos,
              "C73 ID TSV schema changed");
        rows.emplace_back(line.substr(0,tab),ids(line.substr(tab+1)));
    }
    check(rows.size()==4 && rows[0].first=="cold513" && rows[0].second.size()==513 &&
          rows[1].first=="warm_prefix2043" && rows[1].second.size()==2043 &&
          rows[2].first=="warm_tail154" && rows[2].second.size()==154 &&
          rows[3].first=="continuation32" && rows[3].second.size()==32,
          "C73 ID names/order/count changed");
    check(std::equal(rows[0].second.begin(),rows[0].second.end(),rows[1].second.begin()),
          "cold513 differs from warm prefix");
    if (name=="cold513") return {name,{},std::move(rows[0].second),std::move(rows[3].second)};
    if (name=="warm154") return {name,std::move(rows[1].second),
                                  std::move(rows[2].second),std::move(rows[3].second)};
    throw std::runtime_error("C73 case outside frozen workload");
}

void write_new(const std::string & path,const void * data,size_t bytes) {
    const int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    check(fd>=0,"output exists or cannot be created: "+path);
    const auto * ptr=static_cast<const unsigned char *>(data);
    while (bytes) {
        const ssize_t n=write(fd,ptr,bytes);
        if (n<=0) {close(fd);throw std::runtime_error("output write failed");}
        ptr+=n;bytes-=static_cast<size_t>(n);
    }
    check(close(fd)==0,"output close failed");
}

void decode(llama_context * ctx,const std::vector<llama_token> & tokens,
            int offset,int count,int base) {
    llama_batch batch=llama_batch_init(count,0,1);
    for (int i=0;i<count;++i) {
        batch.token[i]=tokens[static_cast<size_t>(offset+i)];
        batch.pos[i]=base+offset+i;
        batch.n_seq_id[i]=1;
        batch.seq_id[i][0]=0;
        batch.logits[i]=i==count-1;
    }
    batch.n_tokens=count;
    const int rc=llama_decode(ctx,batch);
    llama_batch_free(batch);
    check(rc==0,"llama_decode failed");
}

void validate_logits(const float * logits,int vocab) {
    check(logits!=nullptr,"logits unavailable after completion fence");
    for (int i=0;i<vocab;++i) check(std::isfinite(logits[i]),"nonfinite logit");
}

} // namespace

int main(int argc,char ** argv) {
    // MODEL INPUT_TSV OUTPUT_PREFIX --ngl 12 --case cold513|warm154
    if (argc!=8) {
        std::cerr<<"usage: c73_wave_probe MODEL INPUT_TSV PREFIX --ngl 12 --case cold513|warm154\n";
        return 2;
    }
    try {
        check(std::strcmp(argv[4],"--ngl")==0 && std::strcmp(argv[6],"--case")==0,
              "unknown probe arguments");
        const int ngl=std::stoi(argv[5]);
        check(ngl==12,"ngl outside frozen P12 profile");
        check(std::getenv("LLAMA_MOE_STREAM_NO_PRELOAD") &&
              std::strcmp(std::getenv("LLAMA_MOE_STREAM_NO_PRELOAD"),"1")==0 &&
              !std::getenv("TESY_CPU_FA_PREFILL_VEC_COMPAT") && !std::getenv("LD_PRELOAD"),
              "probe environment differs from frozen no-preload profile");
        const std::string case_name=argv[7];
        const auto item=workload(argv[2],case_name);
        const std::string prefix=argv[3];
        for (const auto & suffix:{".f32",".rows.tsv",".chunks.tsv",".steps.tsv",".ops.tsv"})
            check(!std::filesystem::exists(prefix+suffix),"no-replace output exists");

        const auto load_start=std::chrono::steady_clock::now();
        llama_backend_init();
        auto mp=llama_model_default_params();
        mp.n_gpu_layers=ngl;
        mp.use_mmap=false;
        mp.use_direct_io=true;
        mp.use_extra_bufts=false;
        mp.moe_stream=true;
        mp.moe_stream_slots=32;
        mp.moe_stream_io_threads=4;
        mp.moe_stream_direct=true;
        llama_model * model=llama_model_load_from_file(argv[1],mp);
        check(model!=nullptr,"model load failed");
        const double model_load_s=std::chrono::duration<double>(
            std::chrono::steady_clock::now()-load_start).count();
        const auto context_start=std::chrono::steady_clock::now();
        auto cp=llama_context_default_params();
        cp.n_ctx=4096;cp.n_batch=256;cp.n_ubatch=32;cp.n_seq_max=1;
        cp.n_threads=8;cp.n_threads_batch=8;cp.op_offload=false;
        cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED;
        cp.type_k=GGML_TYPE_F16;cp.type_v=GGML_TYPE_F16;
        cp.swa_full=true;cp.offload_kqv=true;cp.kv_unified=false;
        llama_context * ctx=llama_init_from_model(model,cp);
        check(ctx!=nullptr,"context init failed");
        const double context_init_s=std::chrono::duration<double>(
            std::chrono::steady_clock::now()-context_start).count();
        const int vocab=llama_vocab_n_tokens(llama_model_get_vocab(model));
        check(vocab==201088,"target vocab changed");
        std::cout<<"C73_CONTEXT_READY ngl="<<ngl<<" case="<<case_name<<'\n'<<std::flush;
        std::vector<float> all;
        std::string rows="phase\tposition\trow\ttoken_id\n";
        std::string chunks="chunk\tstart\tcount\tdispatch_s\n";
        std::string steps="step\ttoken_id\tcompletion_s\n";
        double prefill_s=0,work_s=0,conditioning_s=0;
        {
            llama_memory_clear(llama_get_memory(ctx),true);llama_synchronize(ctx);
            if (!item.conditioning.empty()) {
                const auto begin=std::chrono::steady_clock::now();
                for (int offset=0;offset<static_cast<int>(item.conditioning.size());offset+=256) {
                    const int n=std::min(256,static_cast<int>(item.conditioning.size())-offset);
                    decode(ctx,item.conditioning,offset,n,0);
                }
                validate_logits(llama_get_logits(ctx),vocab);
                conditioning_s=std::chrono::duration<double>(
                    std::chrono::steady_clock::now()-begin).count();
            }
            const int count=static_cast<int>(item.prompt.size());
            const size_t n_chunks=(item.prompt.size()+255)/256;
            std::vector<double> chunk_s(n_chunks);
            const float * current=nullptr;
            const int base=static_cast<int>(item.conditioning.size());
            const auto measured=c4_measure_prefill(count,256,
                [] {},
                [&](int offset,int n) {decode(ctx,item.prompt,offset,n,base);},
                [&] {current=llama_get_logits(ctx);return current!=nullptr;},chunk_s);
            prefill_s=measured.completion_s;
            work_s=prefill_s;
            validate_logits(current,vocab);
            all.insert(all.end(),current,current+vocab);
            rows+="prefill\t"+std::to_string(base+count-1)+"\t0\t"+
                  std::to_string(item.prompt.back())+'\n';
            for (size_t c=0;c<n_chunks;++c) {
                const int offset=static_cast<int>(c)*256;
                chunks+=std::to_string(c)+'\t'+std::to_string(offset)+'\t'+
                        std::to_string(std::min(256,count-offset))+'\t'+
                        std::to_string(chunk_s[c])+'\n';
            }
            {
                for (int i=0;i<32;++i) {
                    const auto begin=std::chrono::steady_clock::now();
                    decode(ctx,item.continuation,i,1,base+count);
                    current=llama_get_logits(ctx);
                    validate_logits(current,vocab);
                    const double elapsed=std::chrono::duration<double>(
                        std::chrono::steady_clock::now()-begin).count();
                    check(elapsed>0 && std::isfinite(elapsed),"invalid decode timing");
                    work_s+=elapsed;
                    all.insert(all.end(),current,current+vocab);
                    steps+=std::to_string(i)+'\t'+std::to_string(item.continuation[i])+'\t'+
                           std::to_string(elapsed)+'\n';
                    rows+="decode\t"+std::to_string(base+count+i)+"\t"+std::to_string(i+1)+'\t'+
                          std::to_string(item.continuation[i])+'\n';
                }
            }
            std::cerr<<"C73_STATS_BEGIN\n";
            llama_moe_stream_print_stats(model);
            std::cerr<<"C73_STATS_END\n";
            write_new(prefix+".f32",all.data(),all.size()*sizeof(float));
            write_new(prefix+".rows.tsv",rows.data(),rows.size());
            write_new(prefix+".chunks.tsv",chunks.data(),chunks.size());
            write_new(prefix+".steps.tsv",steps.data(),steps.size());
        }
        const std::string ops="ngl\tcase\tconditioning_s\tmodel_load_s\tcontext_init_s\tprefill_completion_s\twork_s\toutput_rows\n"+
            std::to_string(ngl)+'\t'+case_name+'\t'+std::to_string(conditioning_s)+'\t'+
            std::to_string(model_load_s)+'\t'+std::to_string(context_init_s)+'\t'+std::to_string(prefill_s)+'\t'+
            std::to_string(work_s)+'\t'+std::to_string(all.size()/static_cast<size_t>(vocab))+'\n';
        write_new(prefix+".ops.tsv",ops.data(),ops.size());
        llama_free(ctx);llama_model_free(model);llama_backend_free();
        return 0;
    } catch (const std::exception & exc) {
        std::cerr<<"C73_PROFILE_FAIL: "<<exc.what()<<'\n';
        return 1;
    }
}
