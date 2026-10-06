// Bounded R0/T/E ablation: reuse the qualified C-API, no server implementation.
#define main original_native_entrypoint
#include "block_native_run.cpp"
#undef main
#include "llama-context.h"

int chosen_mode(const std::string & profile) {
    if(profile=="R0")return 0;
    if(profile=="T")return 1;
    if(profile=="E")return 2;
    throw std::runtime_error("unknown causal profile");
}
std::vector<int> prefix_plan(int count) {
    check(count>0&&count<=7936,"prefix size invalid");
    std::vector<int> out;
    for(int pos=0;pos<count;pos+=256)out.push_back(std::min(256,count-pos));
    return out;
}
void check_env(int mode) {
    const char * span=getenv("TESY_C262_LAYER_SPAN"),*order=getenv("TESY_C269_LAST_USE_ORDER");
    check(mode==0?(!span&&!order):(span&&order&&std::string(span)=="153"&&std::string(order)=="1"),"causal profile env changed");
}
int main(int argc,char ** argv){try{
    if(argc==2&&std::string(argv[1])=="--self-test") {
        check(chosen_mode("R0")==0&&chosen_mode("T")==1&&chosen_mode("E")==2,"mode selection changed");
        bool bad=false;try{chosen_mode("B");}catch(const std::exception&){bad=true;}check(bad,"unknown mode accepted");
        check(prefix_plan(2044)==std::vector<int>({256,256,256,256,256,256,256,252}),"nominal plan changed");
        check(prefix_plan(1952)==std::vector<int>({256,256,256,256,256,256,256,160}),"code plan changed");
        check(logit_index(false,0)==-1,"last output index changed");
        std::cout<<"PASS_MODEL_FREE_R2_CAUSAL_MODE_CALLS_ROWS\n";return 0;
    }
    if(argc==5&&std::string(argv[1])=="--pieces") {
        std::ifstream f(argv[3]);json ids;f>>ids;check(bool(f)&&ids.is_array(),"piece ID fixture invalid");
        llama_backend_init();auto mp=llama_model_default_params();mp.vocab_only=true;mp.n_gpu_layers=0;mp.use_extra_bufts=false;
        auto * model=llama_model_load_from_file(argv[2],mp);check(model,"vocab-only model absent");
        json pieces=json::array();for(int id:ids.get<std::vector<int>>()) {
            check(id>=0&&id<vocab,"piece ID outside vocab");char buf[256];
            int n=llama_token_to_piece(llama_model_get_vocab(model),id,buf,sizeof(buf),0,true);
            check(n>=0&&n<=static_cast<int>(sizeof(buf)),"bounded token piece failed");
            pieces.push_back({{"id",id},{"piece",std::string(buf,n)}});
        }
        check(!std::filesystem::exists(argv[4]),"piece output reused");save(argv[4],{{"pieces",pieces},{"weights_loaded",false},{"forwards",0}});
        llama_model_free(model);llama_backend_free();return 0;
    }
    check(argc==7&&std::string(argv[6])=="v1","usage MODEL FIXTURE CASE NEWROOT R0|T|E v1");
    const std::string profile=argv[5];const int mode=chosen_mode(profile);check_env(mode);
    std::ifstream f(argv[2]);json fixtures;f>>fixtures;check(bool(f),"frozen fixture absent");
    const auto spec=fixtures.at(argv[3]);const auto ids=spec.at("ids").get<std::vector<llama_token>>();
    const auto tokens=spec.at("continuation_ids").get<std::vector<llama_token>>();
    check((ids.size()==2197||ids.size()==2105)&&tokens.size()==32,"exact development inputs changed");
    for(int id:ids)check(id>=0&&id<vocab,"input ID invalid");for(int id:tokens)check(id>=0&&id<vocab,"teacher ID invalid");
    const int prefix=static_cast<int>(ids.size())-153;const auto plan=prefix_plan(prefix);
    const std::filesystem::path root=argv[4];check(std::filesystem::create_directory(root),"output root reused");
    runtime r(argv[1]);check(r.ctx->get_cparams().c262_layer_mode==0,"warmup mode not original");
    check(r.ctx->get_cparams().c262_layer_span==(mode?153:0),"reserve span differs from frozen profile");
    const auto prepare_begin=clock_type::now();int pos=0;
    for(int n:plan){r.call({ids.begin()+pos,ids.begin()+pos+n},pos,false);pos+=n;}
    const auto prepare_end=clock_type::now();const auto initial=r.snapshot();save(root/"initial.json",initial);
    std::vector<float> complete_rows(static_cast<size_t>(33)*vocab);std::vector<int> winners;winners.reserve(33);
    const auto begin=clock_type::now();
    if(mode)check(llama_c262_set_layer_mode(r.ctx,mode),"mode/reset graph refused");
    check(r.ctx->get_cparams().c262_layer_mode==mode,"mode did not reach real context");
    auto row=r.call({ids.begin()+prefix,ids.end()},prefix,false);
    std::copy(row.begin(),row.end(),complete_rows.begin());winners.push_back(greedy(row.data()));
    const auto prefill_end=clock_type::now();
    for(int i=0;i<32;++i) {
        row=r.call({tokens[i]},static_cast<int>(ids.size())+i,false);
        std::copy(row.begin(),row.end(),complete_rows.begin()+static_cast<size_t>(i+1)*vocab);
        winners.push_back(greedy(row.data()));
    }
    const auto end=clock_type::now();const auto final=r.snapshot();
    json logical=json::array();auto * mgr=r.model->moe_stream();
    {std::lock_guard<std::mutex> lk(mgr->mtx);for(const auto & sl:mgr->layers)if(sl) {
        const auto & c=sl->logical_route;
        check(!mgr->logical_route_v1||c.cursor==c.positions.size(),"last logical event incomplete");
        logical.push_back({{"layer",sl->il},{"rows",c.rows},{"decay_epoch",c.decay_epoch},{"lifecycle",c.lifecycle},{"event_serial",c.event},{"sequence",c.sequence},{"last_positions",c.positions},{"accounted_rows",c.cursor}});
    }}
    save(root/"logical-policy.json",{{"enabled",mgr->logical_route_v1},{"layers",logical},{"last_event_serial",mgr->logical_event_serial},{"scope","single context/sequence0; actual ubatch/output positions; no snapshot import; own-policy full prefix"}});
    // No intermediate drain/writes/witness. Every full row is retained equally;
    // all payload files and heavy hashing are outside the measured window.
    binary(root/"all33.logits.f32",complete_rows);
    const auto seconds=[](auto a,auto b){return std::chrono::duration<double>(b-a).count();};
    auto calls=plan;calls.push_back(153);
    save(root/"result.json",{{"status","COMPLETE_NATIVE_R2_CAUSAL_WORK"},{"profile",profile},{"case",argv[3]},
      {"official_input_ids",ids},{"teacher_forced_ids",tokens},{"native_argmax_ids",winners},{"initial",initial},{"final",final},
      {"prefix_s",seconds(prepare_begin,prepare_end)},{"prefill153_s",seconds(begin,prefill_end)},
      {"decode32_s",seconds(prefill_end,end)},{"total_s",seconds(begin,end)},
      {"external_prefill_calls",calls},{"decode_calls",32},{"decode_positions",{ids.size(),ids.size()+31}},
      {"output_rows",33},{"vocab",vocab},{"FFN_last_layer_rows_per_call",1},{"mode",mode},{"layerspan",mode?153:32},
      {"numerical_FFN_tiles",{32,32,32,32,25}},{"last_use_order_env",mode?json("1"):json(nullptr)},
      {"initial_prefix_mode",0},{"full_row_retention_bytes",complete_rows.size()*sizeof(float)},
      {"timing","Synchronized calls/full-row copy/greedy included; no intermediate drain, file IO or heavy hash; final drain and payload dump excluded"},
      {"teacher_forcing","Published native IDs supplied, not generated or confirmed throughput"}});
    return 0;
}catch(const std::exception & e){std::cerr<<"LOGICAL_ROUTE_FAIL "<<e.what()<<'\n';return 1;}}
