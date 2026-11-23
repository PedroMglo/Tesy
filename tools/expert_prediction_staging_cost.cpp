// R0 native service: original numerical/call profile, private store toggle only.
#define main original_native_entrypoint
#include "block_native_run.cpp"
#undef main
#include "llama-context.h"
#include "c305-cpu-stage.h"

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
#include "expert_activation_estimator.h"
struct window_observer {runtime * r=nullptr; bool on=false,predict=false,stage=false;activation_bank *bank=nullptr;};
bool observe_window(ggml_tensor *t,bool ask,void *opaque) {
    auto &o=*static_cast<window_observer *>(opaque);
    if(o.r)observe_rows(t,ask,&o.r->rows);
    int layer=-1;
    const std::string name=ggml_get_name(t);
    const bool selected=sscanf(name.c_str(),"attn_norm-%d",&layer)==1 && name=="attn_norm-"+std::to_string(layer) && layer>=0 && layer<=24 && (o.on || (o.predict && layer<=22 && o.r && o.r->model->moe_stream()->window.call.load()>0));
    int label_layer=-1;
    const bool label=o.on && sscanf(name.c_str(),"ffn_moe_probs-%d",&label_layer)==1 && name=="ffn_moe_probs-"+std::to_string(label_layer) && label_layer>=2&&label_layer<=24;
    if(ask)return selected||label;
    if(label&&o.r->model->moe_stream()->window.call.load()>0)o.bank->label(t,label_layer,(int)o.r->model->moe_stream()->window.call.load());
    if(selected){
        auto &window=o.r->model->moe_stream()->window;window.record(1,layer,-1,-1,0,0,-1,0,(int)t->ne[1]);
        if(o.predict&&layer<=22&&window.call.load()>0){
            o.bank->observe(*o.r,t,layer,(int)window.call.load());
            if(o.stage){const auto &receipt=o.bank->records[o.bank->count-1];o.r->model->moe_stream()->prediction_request(receipt.call,receipt.target,receipt.ids);}
        }
    }
    return true;
}
int main(int argc,char ** argv){try{
    if(argc==2&&std::string(argv[1])=="--self-test") {
        check(chosen_mode("R0")==0&&chosen_mode("T")==1&&chosen_mode("E")==2,"mode selection changed");
        bool bad=false;try{chosen_mode("B");}catch(const std::exception&){bad=true;}check(bad,"unknown mode accepted");
        check(prefix_plan(2044)==std::vector<int>({256,256,256,256,256,256,256,252}),"nominal plan changed");
        check(prefix_plan(1952)==std::vector<int>({256,256,256,256,256,256,256,160}),"code plan changed");
        check(logit_index(false,0)==-1,"last output index changed");
        c294_window w;w.record(1);check(w.count.load()==0,"disabled trace emitted event");
        w.enabled.store(true);w.call.store(9);std::vector<std::thread> threads;
        for(int k=0;k<4;k++)threads.emplace_back([&w,k]{for(int i=0;i<1000;i++)w.record(10,k,i,0,1,2);});
        for(auto &t:threads)t.join();check(w.count.load()==4000&&!w.overflow,"threaded trace accounting");
        for(size_t i=0;i<4000;i++)check(w.events[i].call==9&&w.events[i].kind==10&&w.events[i].us>0,"threaded payload incomplete");
        w.count.store(w.capacity);w.record(1);check(w.overflow,"overflow not fail closed");
        ggml_tensor tensor{};ggml_set_name(&tensor,"attn_norm-24");window_observer o;o.on=true;
        check(observe_window(&tensor,true,&o),"feature point not selected");
        ggml_set_name(&tensor,"attn_norm-25");check(!observe_window(&tensor,true,&o),"GPU point accidentally selected");
        ggml_set_name(&tensor,"attn_norm-0-future");check(!observe_window(&tensor,true,&o),"noncanonical feature name accepted");
        ggml_set_name(&tensor,"ffn_moe_probs-2");check(observe_window(&tensor,true,&o),"actual original biased routing score alias not selected");
        ggml_set_name(&tensor,"ffn_moe_probs-24");check(observe_window(&tensor,true,&o),"last CPU true label not selected");
        ggml_set_name(&tensor,"ffn_moe_probs-25");check(!observe_window(&tensor,true,&o),"GPU true label selected");
        ggml_set_name(&tensor,"ffn_moe_logits_biased-2");check(!observe_window(&tensor,true,&o),"obsolete graph alias selected");
        o.on=false;ggml_set_name(&tensor,"attn_norm-0");check(!observe_window(&tensor,true,&o),"OFF feature callback requests tensor");
        auto cpu=ggml_backend_cpu_init();check(cpu,"estimator synthetic CPU backend");ggml_backend_cpu_set_n_threads(cpu,8);
        auto ctx=ggml_init({4*1024*1024,nullptr,true});check(ctx,"synthetic gate metadata");
        auto *norm=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,2880);
        auto *gate=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,2880,128);
        auto *bias=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,128);
        auto buffer=ggml_backend_alloc_ctx_tensors(ctx,cpu);check(buffer,"synthetic gate buffer");
        std::vector<float> nm(2880,1),gm(2880*128,0),bs(128,0),x(2880,1);
        for(int k=0;k<128;k++){gm[k*2880]=k+1;bs[k]=-.01f*k;}
        ggml_backend_tensor_set(norm,nm.data(),0,nm.size()*4);ggml_backend_tensor_set(gate,gm.data(),0,gm.size()*4);ggml_backend_tensor_set(bias,bs.data(),0,bs.size()*4);
        {activation_estimator estimator(norm,gate,bias,1e-5f,2,cpu);auto scores=estimator.score(x.data());
         for(int k=0;k<128;k++)check(std::abs(scores[k]-((k+1)/std::sqrt(1.00001f)-.01f*k))<.0001f,"independent synthetic norm/gate/bias score");
         for(int k=1;k<128;k++)check(scores[k]>scores[k-1],"synthetic prediction ranking");}
        // Keep the tested native backend alive for real /proc runtime and resource observation.
        std::this_thread::sleep_for(std::chrono::seconds(5));
        ggml_backend_buffer_free(buffer);ggml_free(ctx);ggml_backend_free(cpu);
        std::cout<<"PASS_MODEL_FREE_WINDOW_AND_NATIVE_APPROXIMATION_FIXTURE\n";return 0;
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
    const std::string profile=argv[5];const int mode=chosen_mode(profile);check(mode==0,"transport benchmark permits R0 only");check_env(mode);
    std::ifstream f(argv[2]);json fixtures;f>>fixtures;check(bool(f),"frozen fixture absent");
    const auto spec=fixtures.at(argv[3]);const auto ids=spec.at("ids").get<std::vector<llama_token>>();
    const auto tokens=spec.at("continuation_ids").get<std::vector<llama_token>>();
    check((ids.size()==2197||ids.size()==2105)&&tokens.size()==32,"exact development inputs changed");
    for(int id:ids)check(id>=0&&id<vocab,"input ID invalid");for(int id:tokens)check(id>=0&&id<vocab,"teacher ID invalid");
    const int prefix=static_cast<int>(ids.size())-153;const auto plan=prefix_plan(prefix);
    const std::filesystem::path root=argv[4];check(std::filesystem::create_directory(root),"output root reused");
    window_observer observer;runtime r(argv[1],observe_window,&observer);observer.r=&r;
    const bool trace=getenv("TESY_C294_WINDOW")!=nullptr;
    // Trace OFF keeps only actual movement feature dependencies, not true labels.
    check(getenv("TESY_C305_ARENA")&&std::string(getenv("TESY_C305_ARENA"))=="128","common arena identity absent");
    observer.stage=getenv("TESY_C305_STAGE")!=nullptr;
    check(!observer.stage||std::string(getenv("TESY_C305_STAGE"))=="1","stage flag value");
    activation_bank bank(r.model);observer.bank=&bank;observer.predict=getenv("TESY_C296_ESTIMATOR")!=nullptr;
    check(!observer.predict||std::string(getenv("TESY_C296_ESTIMATOR"))=="1","estimator toggle value changed");
    check(!observer.stage||observer.predict,"stage enabled without actual estimator");
    check(!getenv("TESY_EXPERT_STORE_MANIFEST"),"C294 original byte service only");check(r.ctx->get_cparams().c262_layer_mode==0,"warmup mode not original");
    check(r.ctx->get_cparams().c262_layer_span==(mode?153:0),"reserve span differs from frozen profile");
    const bool packed=bool(getenv("TESY_EXPERT_STORE_MANIFEST"));
    const auto load_before_prefix=r.model->moe_stream()->stats.n_store_loads;
    const auto prepare_begin=clock_type::now();int pos=0;
    for(int n:plan){r.call({ids.begin()+pos,ids.begin()+pos+n},pos,false);pos+=n;}
    const auto prepare_end=clock_type::now();const auto initial=r.snapshot();save(root/"initial.json",initial);
    std::vector<float> complete_rows(static_cast<size_t>(33)*vocab);std::vector<int> winners;winners.reserve(33);
    auto &window=r.model->moe_stream()->window;observer.on=trace;window.enabled.store(trace);window.call.store(0);
    window.record(15);
    const auto begin=clock_type::now();
    if(mode)check(llama_c262_set_layer_mode(r.ctx,mode),"mode/reset graph refused");
    check(r.ctx->get_cparams().c262_layer_mode==mode,"mode did not reach real context");
    auto row=r.call({ids.begin()+prefix,ids.end()},prefix,false);
    std::copy(row.begin(),row.end(),complete_rows.begin());winners.push_back(greedy(row.data()));
    const auto prefill_end=clock_type::now();window.record(16);
    r.model->moe_stream()->prediction_begin(observer.stage);
    for(int i=0;i<32;++i) {
        window.call.store(i+1);window.record(15);
        row=r.call({tokens[i]},static_cast<int>(ids.size())+i,false);
        std::copy(row.begin(),row.end(),complete_rows.begin()+static_cast<size_t>(i+1)*vocab);
        winners.push_back(greedy(row.data()));window.record(16);
    }
    const auto forward_end=clock_type::now();
    r.model->moe_stream()->prediction_finish();
    const auto end=clock_type::now();const auto final=r.snapshot();
    window.enabled.store(false);observer.on=false;
    check(!window.overflow.load(),"bounded event overflow");
    std::ofstream journal(root/"events.tsv");
    journal<<"kind us call route layer expert slot gen component bytes rows\n";
    for(size_t i=0;i<window.count.load();++i){const auto &e=window.events[i];journal<<e.kind<<" "<<e.us<<" "<<e.call<<" "<<e.route<<" "<<e.layer<<" "<<e.expert<<" "<<e.slot<<" "<<e.gen<<" "<<e.component<<" "<<e.bytes<<" "<<e.rows<<"\n";}
    journal.close();check(bool(journal),"journal write failed");
    json estimated=json::array();
    for(size_t i=0;i<bank.count;i++){
        const auto &e=bank.records[i];json states=json::array();
        for(int k=0;k<4;k++)states.push_back({{"expert",e.ids[k]},{"slot",e.slots[k]},{"state",e.states[k]},{"generation",e.generations[k]}});
        estimated.push_back({{"call",e.call},{"source_layer",e.source},{"target_layer",e.target},{"prediction_ids",e.ids},{"available_primary_state",states},{"complete_predictor_us",e.predictor_us}});
    }
    save(root/"estimator.json",{{"schema","original-destination-gate-on-earlier-residual-v1"},{"enabled",observer.predict},{"true_gate_capture",trace},{"records",estimated},{"training",false},{"source_horizon",2},{"capture_bytes",bank.inputs.size()*4+bank.scores.size()*4+bank.true_scores.size()*4},{"CPU_backend_threads",8},{"claims","Movement estimator only; true routing unchanged; staging_enabled and staging.json explicitly report whether originalbytes were actually anticipated"}});
    check(bank.true_count==(trace?32*23:0),"exact true gate label coverage");if(trace)binary(root/"true-routing-scores.f32",bank.true_scores);
    if(observer.predict){check(bank.count==32*23,"exact estimator call/layer coverage");binary(root/"earlier-input.f32",bank.inputs);binary(root/"prediction-scores.f32",bank.scores);}
    if(observer.predict){
        json weights=json::array();
        for(int layer=2;layer<=24;layer++) {
            const auto &l=r.model->layers[layer];
            for(auto *tensor:{l.attn_post_norm,l.ffn_gate_inp,l.ffn_gate_inp_b}) {
                check(tensor->type==GGML_TYPE_F32&&ggml_is_contiguous(tensor)&&ggml_nbytes(tensor)<=1474560,"bounded original auxiliary tensor");
                std::vector<float> data(ggml_nelements(tensor));ggml_backend_tensor_get(tensor,data.data(),0,ggml_nbytes(tensor));
                const std::string name=std::string(ggml_get_name(tensor))+".f32";binary(root/name,data);
                weights.push_back({{"layer",layer},{"name",ggml_get_name(tensor)},{"ne",{tensor->ne[0],tensor->ne[1]}},{"type","F32"},{"bytes",ggml_nbytes(tensor)},{"file",name}});
            }
        }
        save(root/"original-auxiliary-tensors.json",{{"weights",weights},{"f_norm_rms_eps",r.model->hparams.f_norm_rms_eps},{"source","Original resident model tensors, selected norm/gate/bias, no fine tuning or duplicate target experts"}});
    }
    auto *mgr=r.model->moe_stream();
    const auto &stage=*mgr->prediction_stage;check(stage.idle()&&stage.stats.errors==0,"stage lifetime/error cleanup");
    const auto &st=stage.stats;
    json journal_events=json::array();
    for(size_t i=0;i<stage.journal_count;i++){const auto &e=stage.journal[i];journal_events.push_back({{"us",e.us},{"scope",e.scope},{"ticket",e.ticket},{"generation",e.generation},{"kind",e.kind},{"call",e.call},{"layer",e.layer},{"expert",e.expert},{"slot",e.slot},{"component",e.component}});}
    save(root/"staging.json",{{"enabled",observer.stage},{"journal_enabled",stage.journal_enabled},{"idle",stage.idle()},{"arena_bytes",stage.entry_stride*stage.slots},{"metadata_bytes",sizeof(stage)},{"journal_capacity",stage.journal_capacity},{"DIO_memory_alignment",stage.reader.memory_alignment()},{"DIO_offset_alignment",stage.reader.offset_alignment()},{"fd_O_DIRECT",bool(fcntl(stage.reader.descriptor(),F_GETFL)&O_DIRECT)},
      {"stats",{{"issued",st.issued},{"deduplicated",st.deduplicated},{"no_capacity",st.no_capacity},{"reads",st.reads},{"completed_reads",st.completed_reads},{"logical_read_weight_bytes",st.read_bytes},{"expired_queued",st.expired_queued},{"expired_ready",st.expired_ready},{"expired_running",st.expired_running},{"consumed",st.consumed},{"waits",st.waits},{"errors",st.errors},{"peak_running_spec",st.peak_running_spec},{"validation_claims",st.validation_claims},{"validation_components",st.validation_components}}},{"journal",journal_events}});
    check(bool(mgr->expert_store)==packed,"store mode did not reach worker");
    const auto store_loads=mgr->stats.n_store_loads,store_bytes=mgr->stats.n_store_read_bytes;
    check(packed?store_loads>load_before_prefix:store_loads==0,"store actual authoritative loads missing/unexpected");
    // No intermediate drain/writes/witness. Every full row is retained equally;
    // all payload files and heavy hashing are outside the measured window.
    binary(root/"all33.logits.f32",complete_rows);
    const auto seconds=[](auto a,auto b){return std::chrono::duration<double>(b-a).count();};
    auto calls=plan;calls.push_back(153);
    save(root/"result.json",{{"status","COMPLETE_NATIVE_R2_CAUSAL_WORK"},{"trace",trace},{"trace_events",window.count.load()},{"trace_capacity",window.capacity},{"trace_bytes_reserved",window.events.size()*sizeof(c294_event)},{"transport",packed?"EXPERT_CONTIGUOUS":"ORIGINAL"},{"store_loads_complete",store_loads},{"store_logical_weight_bytes",store_bytes},{"store_manifest_env",packed?json(getenv("TESY_EXPERT_STORE_MANIFEST")):json(nullptr)},{"profile",profile},{"case",argv[3]},{"staging_enabled",observer.stage},{"estimator_enabled",observer.predict},{"diagnostic_byte_witness",stage.validate},
      {"official_input_ids",ids},{"teacher_forced_ids",tokens},{"native_argmax_ids",winners},{"initial",initial},{"final",final},
      {"prefix_s",seconds(prepare_begin,prepare_end)},{"prefill153_s",seconds(begin,prefill_end)},
      {"decode32_s",seconds(prefill_end,end)},{"decode_forward_s",seconds(prefill_end,forward_end)},{"stage_cleanup_s",seconds(forward_end,end)},{"total_s",seconds(begin,end)},
      {"external_prefill_calls",calls},{"decode_calls",32},{"decode_positions",{ids.size(),ids.size()+31}},
      {"output_rows",33},{"vocab",vocab},{"FFN_last_layer_rows_per_call",1},{"mode",mode},{"layerspan",mode?153:32},
      {"numerical_FFN_tiles",{32,32,32,32,25}},{"last_use_order_env",mode?json("1"):json(nullptr)},
      {"initial_prefix_mode",0},{"full_row_retention_bytes",complete_rows.size()*sizeof(float)},
      {"timing","Synchronized calls/full-row copy/greedy/predictor/stageissue and stage-only pending-read cancellation cleanup included. Trace and canonical byte checks flags define observation scope. No witness for production cost. No between-prefill/decode drain/file/hash; final primary drain and payload dump excluded"},
      {"teacher_forcing","Published native IDs supplied, not generated or confirmed throughput"}});
    return 0;
}catch(const std::exception & e){std::cerr<<"R2_CAUSAL_FAIL "<<e.what()<<'\n';return 1;}}
