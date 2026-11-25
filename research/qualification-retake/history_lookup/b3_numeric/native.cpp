// The C270 executable uses the C127 numerical callback with the C210 direct reader.
#ifndef TESY_B3_PARENT_CAPTURE
#error "Point TESY_B3_PARENT_CAPTURE at the authenticated C270 capture source"
#endif
#define main c127_reference_main
#include TESY_B3_PARENT_CAPTURE
#undef main
#include "llama-model.h"

#include <chrono>
#include <memory>
#include <type_traits>

namespace {
namespace fs = std::filesystem;
constexpr size_t vocabulary = 201088;
constexpr size_t kv_limit = 32u << 20;
constexpr size_t prefix_files = 2248;
constexpr uintmax_t prefix_bytes = 81624144;

struct Observer {
    capture_state original;
    bool verifying = false;
    int ffn = 0, projection = 0;

    static bool callback(ggml_tensor *tensor, bool ask, void *userdata) {
        auto &self = *static_cast<Observer *>(userdata);
        if (!self.verifying) return capture(tensor, ask, &self.original);
        // The same callback is installed in both arms. It requests no data or split here.
        if (ask) {
            const std::string name = ggml_get_name(tensor);
            if (name == "ffn_moe_out-35") self.ffn = static_cast<int>(tensor->ne[1]);
            if (name == "result_output") self.projection = static_cast<int>(tensor->ne[1]);
        }
        return false;
    }
};

bool same_file(const fs::path &a, const fs::path &b) {
    if (!fs::is_regular_file(a) || !fs::is_regular_file(b) || fs::file_size(a)!=fs::file_size(b)) return false;
    std::ifstream one(a, std::ios::binary), two(b, std::ios::binary);
    check(one.good() && two.good(), "gold open");
    std::array<char, 32768> x{}, y{};
    do {
        one.read(x.data(), x.size());
        two.read(y.data(), y.size());
        if(one.gcount()!=two.gcount() || !std::equal(x.begin(),x.begin()+one.gcount(),y.begin())) return false;
    } while(one.good() && two.good());
    return one.eof() && two.eof() && !one.bad() && !two.bad();
}

void prefix_agreement(const fs::path &out, const fs::path &gold) {
    size_t count = 0;
    uintmax_t bytes = 0;
    std::set<fs::path> refs, observed;
    for (const auto &f : fs::directory_iterator(gold)) {
        auto name = f.path().filename();
        if (name.string().rfind("prefill",0) == 0) refs.insert(name);
    }
    for (const auto &f : fs::directory_iterator(out)) {
        auto name = f.path().filename();
        if (name.string().rfind("prefill",0) != 0) continue;
        observed.insert(name);
        check(same_file(f, gold/name), "prefill tensor differs from C270");
        ++count;
        bytes += f.file_size();
    }
    check(observed == refs && count == prefix_files && bytes == prefix_bytes, "prefill coverage");
}

bool finite_row(const float *row, size_t width) {
    return row && width == vocabulary && std::all_of(row, row+width, [](float v){return std::isfinite(v);});
}

void write_row(const fs::path &path, const float *row) {
    check(row != nullptr, "missing full logit row");
    write_new(path,row,vocabulary*sizeof(float));
    check(finite_row(row, vocabulary), "non-finite logit row preserved");
}

void snapshot_kv(llama_context *ctx, int n, const fs::path &path) {
    llama_synchronize(ctx);
    const auto mem = llama_get_memory(ctx);
    check(llama_memory_seq_pos_min(mem,0)==0 && llama_memory_seq_pos_max(mem,0)==n-1, "KV positions");
    auto size = llama_state_seq_get_size(ctx,0);
    check(size>0 && size<=kv_limit, "serialized KV bound");
    std::vector<uint8_t> payload(size);
    check(llama_state_seq_get_data(ctx,payload.data(),size,0)==size, "complete serialized KV");
    write_new(path,payload.data(),payload.size());
}

// Encode deterministic resident, policy and wave state with an explicit LE u64 per value.
// Omit process addresses, scratch from unused operations and elapsed-time counters.
void snapshot_pool(llama_model *model, const fs::path &path) {
    auto *mgr=model->moe_stream();
    check(mgr && mgr->n_slots==40 && mgr->n_io_threads==4 && mgr->layers.size()==36,
          "R0 expert pool shape");
    std::vector<uint8_t> state;
    auto number=[&](uint64_t n){ for(int i=0;i<8;++i) state.push_back(static_cast<uint8_t>(n>>(i*8))); };
    auto values=[&](const auto &xs){ number(xs.size()); for(auto n:xs) number(static_cast<uint64_t>(n)); };
    {
        std::unique_lock<std::mutex> lock(mgr->mtx);
        const auto drained=[&]{
            if (!mgr->q_demand.empty()) return false;
            for(const auto &sl:mgr->layers) {
                if(!sl) return false;
                for(size_t i=0;i<sl->slot_state.size();++i)
                    if(sl->slot_claimed[i] || sl->slot_state[i]==LLAMA_MOE_STREAM_SLOT_LOADING) return false;
            }
            return true;
        };
        check(mgr->cv_done.wait_for(lock,std::chrono::seconds(5),drained) && !mgr->load_failed,
              "undrained expert pool");
        number(mgr->n_slots); number(mgr->layers.size());
        for(const auto &sl:mgr->layers) {
            check(sl->n_slots==40 && sl->n_expert==128 && sl->slot_state.size()==40 && sl->weights.size()==3,
                  "expert layer shape");
            number(sl->il); number(sl->n_expert);
            values(sl->slot_state); values(sl->slot_expert); values(sl->slot_gen); values(sl->slot_claimed);
            values(sl->slot_last_use); values(sl->route_hotness); values(sl->seen);
            number(sl->use_counter); values(sl->keep); number(sl->plan_next_wave);
            number(sl->plan_capacity); number(sl->plan_n_waves); values(sl->expert_wave);
            size_t occupied=0;
            for(size_t i=0;i<sl->slot_expert.size();++i) {
                int e=sl->slot_expert[i];
                if(e<0) { check(sl->slot_state[i]==LLAMA_MOE_STREAM_SLOT_EMPTY,"empty slot"); continue; }
                check(e<128 && sl->slot_state[i]==LLAMA_MOE_STREAM_SLOT_RESIDENT
                      && sl->expert_slot.at(e)==static_cast<int>(i),"resident lookup");
                ++occupied;
            }
            check(occupied==sl->expert_slot.size(),"resident bijection");
        }
    }
    write_new(path,state.data(),state.size());
}

std::vector<int> batch_rows(int width, int step) {
    check((width==1 || width==3) && step>=0 && step+width<=4, "verification plan");
    std::vector<int> rows;
    for(int i=0;i<width;++i) rows.push_back(step+i);
    return rows;
}

void complete_rows(llama_context *ctx, Observer &observer, const std::vector<llama_token> &ids,
                   int step, int width, const fs::path &out) {
    const auto rows=batch_rows(width,step);
    auto batch=llama_batch_init(width,0,1);
    batch.n_tokens=width;
    for(int i=0;i<width;++i) {
        batch.token[i]=ids.at(rows[i]); batch.pos[i]=189+rows[i];
        batch.n_seq_id[i]=1; batch.seq_id[i][0]=0; batch.logits[i]=1;
    }
    observer.ffn=0; observer.projection=0;
    const int rc=llama_decode(ctx,batch);
    llama_batch_free(batch);
    check(rc==0,"native verification decode");
    llama_synchronize(ctx);
    check(observer.ffn==width && observer.projection==width,"complete FFN/vocabulary geometry");
    for(int i=0;i<width;++i) {
        // Every input requested output, so nonnegative indices address all rows.
        auto file=out/("decode"+std::to_string(rows[i])+".logits.f32");
        write_row(file,llama_get_logits_ith(ctx,i));
    }
}

void execute(const char *model_path,const char *input,const fs::path &gold,bool ar,const fs::path &out) {
    check(fs::create_directory(out),"new native directory required");
    auto prompt=ids_for(input,"log_medium",false);
    auto continuation=ids_for(input,"log_medium",true);
    const auto valid=[](llama_token t){return t>=0 && static_cast<size_t>(t)<vocabulary;};
    check(prompt.size()==189 && continuation.size()==43 && std::all_of(prompt.begin(),prompt.end(),valid)
          && std::all_of(continuation.begin(),continuation.end(),valid),"frozen token geometry");
    check(!std::getenv("LLAMA_MOE_STREAM_NO_PRELOAD") && !std::getenv("TESY_CPU_FA_PREFILL_VEC_COMPAT")
          && !std::getenv("LD_PRELOAD") && !std::getenv("TESY_C3_MUTANT") && !std::getenv("TESY_C3_ARM_READ_FAULT")
          && !std::getenv("TESY_C262_LAYER_SPAN") && !std::getenv("TESY_C269_LAST_USE_ORDER"),"profile override");
    Observer observer;
    auto &state=observer.original;
    state.root=out;
    state.chunk_by_layer.fill(-1);
    check(std::getenv("TESY_CPU_WAVE_SKIP_PARKED") && std::string(std::getenv("TESY_CPU_WAVE_SKIP_PARKED"))=="1",
          "CPU wave profile");
    prepare_canonical(state,model_path);
    llama_backend_init();
    struct BackendGuard { ~BackendGuard(){llama_backend_free();} } backend_guard;
    auto mp=llama_model_default_params();
    mp.n_gpu_layers=12; mp.use_mmap=false; mp.use_direct_io=true; mp.use_extra_bufts=false;
    mp.moe_stream=true; mp.moe_stream_slots=40; mp.moe_stream_io_threads=4; mp.moe_stream_direct=true;
    using Model=std::unique_ptr<llama_model,decltype(&llama_model_free)>;
    Model model(llama_model_load_from_file(model_path,mp),llama_model_free);
    check(model && llama_vocab_n_tokens(llama_model_get_vocab(model.get()))==vocabulary,"model or vocabulary");
    auto cp=llama_context_default_params();
    check(cp.n_outputs_max==0, "original output reserve");
    cp.n_ctx=8192; cp.n_batch=256; cp.n_ubatch=32; cp.n_seq_max=1;
    cp.n_threads=8; cp.n_threads_batch=8; cp.op_offload=false;
    cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_ENABLED; cp.type_k=GGML_TYPE_F16; cp.type_v=GGML_TYPE_F16;
    cp.swa_full=true; cp.offload_kqv=true; cp.kv_unified=true;
    cp.cb_eval=Observer::callback; cp.cb_eval_user_data=&observer;
    using Context=std::unique_ptr<llama_context,decltype(&llama_free)>;
    Context ctx(llama_init_from_model(model.get(),cp),llama_free);
    check(ctx!=nullptr,"context");
    std::cout<<"C80_CONTEXT_READY ngl=12 case=log_medium ctx=8192 preload=on kv_unified=1\n"<<std::flush;
    llama_memory_clear(llama_get_memory(ctx.get()),true);
    llama_synchronize(ctx.get());
    state.enabled=true; state.prefill=true;
    decode(ctx.get(),prompt,0,0,189);
    llama_synchronize(ctx.get());
    state.enabled=false; state.prefill=false;
    check(state.masked_count==2 && std::all_of(state.chunk_by_layer.begin(),state.chunk_by_layer.end(),
          [](int chunk){return chunk==5;}),"C127 prefill geometry");
    write_row(out/"prefill_final.logits.f32",llama_get_logits_ith(ctx.get(),-1));
    prefix_agreement(out,gold);
    snapshot_pool(model.get(),out/"initial-pool.bin");
    snapshot_kv(ctx.get(),189,out/"initial-kv.bin");
    if (!ar) {
        check(same_file(out/"initial-pool.bin",gold/"initial-pool.bin"),"pre-block pool differs from AR");
        check(same_file(out/"initial-kv.bin",gold/"initial-kv.bin"),"pre-block KV differs from AR");
    }
    observer.verifying=true;
    if(ar) {
        for(int step=0;step<3;++step) {
            complete_rows(ctx.get(),observer,continuation,step,1,out);
            if(step<2) {
                const auto name="decode"+std::to_string(step)+".logits.f32";
                check(same_file(out/name,gold/name),"AR row differs from consecutive C270 reference");
            }
        }
    } else complete_rows(ctx.get(),observer,continuation,0,3,out);
    snapshot_kv(ctx.get(),192,out/"post3-kv.bin");
    complete_rows(ctx.get(),observer,continuation,3,1,out);
}
} // namespace

int main(int argc,char **argv) {
    try {
        if(argc==2 && std::string(argv[1])=="--self-test") {
            check(batch_rows(3,0)==std::vector<int>({0,1,2}) && batch_rows(1,3)==std::vector<int>({3}),"row map");
            bool refused=false;
            try { (void)batch_rows(3,2); } catch(const std::exception &) { refused=true; }
            check(refused,"out-of-range rows");
            std::vector<float> row(vocabulary, 0.0f);
            check(finite_row(row.data(),vocabulary) && !finite_row(row.data(),vocabulary-1),
                  "vocabulary width");
            row.back()=std::numeric_limits<float>::infinity();
            check(!finite_row(row.data(),vocabulary), "non-finite last logit");
            row.back()=std::numeric_limits<float>::quiet_NaN();
            check(!finite_row(row.data(),vocabulary), "NaN in full row");
            const float positive_zero=0.0f, negative_zero=-0.0f;
            check(positive_zero==negative_zero && std::memcmp(&positive_zero,&negative_zero,sizeof(float))!=0,
                  "signed-zero bit contrast");
            std::cout<<"PASS_B3_NUMERIC_ROW_PLAN\n"; return 0;
        }
        check(argc==6,"usage: probe MODEL IDS_TSV GOLD_DIR AR|B3 NEW_OUTPUT_DIR");
        const std::string mode=argv[4];
        check(mode=="AR" || mode=="B3","unknown numeric arm");
        const fs::path out=argv[5];
        execute(argv[1],argv[2],argv[3],mode=="AR",out);
        const std::string status=std::string("{\"status\":\"PASS_B3_NUMERIC_ARM\",\"mode\":\"")+mode+
            "\",\"prefix_rows\":189,\"prefill_files\":2248,\"prefill_bytes\":81624144,"
            "\"verification_rows\":3,\"continuation_rows\":1,\"vocab\":201088,"
            "\"positions\":[189,190,191,192],\"historical_ar_rows_checked\":"+
            std::to_string(mode=="AR"?2:0)+",\"initial_state_checked_before_block\":"+
            (mode=="B3"?"true":"false")+"}\n";
        write_new(out/"native.json",status.data(),status.size());
        return 0;
    } catch(const std::exception &error) {
        // Stderr is private to the supervisor; preserve the failing gate.
        std::cerr<<"B3_NUMERIC_FAIL "<<error.what()<<'\n';
        return 1;
    }
}
