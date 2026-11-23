// Free greedy replies on fixed provided history, existing native C-API runtime.
#define main previous_native_entrypoint
#include "block_native_run.cpp"
#undef main
#include "chat.h"
#include "common.h"
#include <ctime>

struct chat_input {common_chat_params chat;std::vector<llama_token> ids;};
chat_input render(llama_model * model,const json & task){
    auto templates=common_chat_templates_init(model,"","","");
    common_chat_templates_inputs input;
    input.messages=common_chat_msgs_parse_oaicompat(task.at("messages"));
    input.reasoning_format=COMMON_REASONING_FORMAT_AUTO;
    input.chat_template_kwargs["reasoning_effort"]=R"("medium")";
    input.chat_template_kwargs["tesy_template_date"]=R"("2026-09-30")";
    std::tm date{};date.tm_year=126;date.tm_mon=8;date.tm_mday=30;
    input.now=std::chrono::system_clock::from_time_t(timegm(&date));
    auto chat=common_chat_templates_apply(templates.get(),input);
    check(chat.prompt.find("2026-09-30")!=std::string::npos&&chat.prompt.find("Reasoning: medium")!=std::string::npos,"template date/medium missing");
    std::vector<llama_token> ids(chat.prompt.size()+4096);
    const int n=llama_tokenize(llama_model_get_vocab(model),chat.prompt.data(),chat.prompt.size(),ids.data(),ids.size(),false,true);
    check(n>0&&n<=static_cast<int>(ids.size()),"official input tokenization failed");ids.resize(n);
    return {std::move(chat),std::move(ids)};
}

int main(int argc,char ** argv){try{
    if(argc==5&&std::string(argv[4])=="--render"){
        std::ifstream f(argv[2]);json tasks;f>>tasks;check(bool(f),"render tasks missing");
        llama_backend_init();auto mp=llama_model_default_params();mp.vocab_only=true;mp.n_gpu_layers=0;mp.use_extra_bufts=false;
        auto * model=llama_model_load_from_file(argv[1],mp);check(model,"vocabulary-only metadata load failed");
        json fixture=json::object();for(const auto & task:tasks){const auto v=render(model,task);
            common_chat_parser_params test(v.chat);test.parser.load(v.chat.parser);test.reasoning_format=COMMON_REASONING_FORMAT_AUTO;
            const auto example=common_chat_parse("<|channel|>analysis<|message|>hidden<|end|><|start|>assistant<|channel|>final<|message|>done",false,test);
            check(example.reasoning_content=="hidden"&&example.content=="done","native parser reasoning/final isolation failed");
            const auto partial=common_chat_parse("<|channel|>analysis<|message|>hidden",true,test);
            check(partial.content.empty()&&partial.reasoning_content=="hidden","incomplete reasoning became final");
            fixture[task.at("id").get<std::string>()]={{"ids",v.ids},{"rendered_prompt",v.chat.prompt},{"task",task},{"template_date","2026-09-30"},{"reasoning_effort","medium"},{"weights_loaded",false},{"native_parser_counterproofs","PASS reasoning/final, analysis-only partial"}};}
        check(!std::filesystem::exists(argv[3]),"render output reused");save(argv[3],fixture);llama_model_free(model);llama_backend_free();return 0;
    }
    check(argc==7&&std::string(argv[6])=="v1","usage MODEL FIXTURE CASE NEWROOT A|B v1");
    const std::string profile=argv[5];check(profile=="A"||profile=="B","profile invalid");
    const char * span=getenv("TESY_C262_LAYER_SPAN"),*order=getenv("TESY_C269_LAST_USE_ORDER");
    check(profile=="A"?(!span&&!order):(span&&order&&std::string(span)=="153"&&std::string(order)=="1"),"unfrozen numerical/residency environment");
    std::ifstream f(argv[2]);json fixture;f>>fixture;check(bool(f),"utility fixture missing");const auto spec=fixture.at(argv[3]);
    const auto ids=spec.at("ids").get<std::vector<llama_token>>();const auto task=spec.at("task");
    check(ids.size()>=2000&&ids.size()<=2600&&task.at("cap")==768&&task.at("deadline_s")==360,"frozen2K utility contract changed");
    const std::filesystem::path root=argv[4];check(std::filesystem::create_directory(root),"utility output root reused");
    runtime r(argv[1]);const auto rendered=render(r.model,task);check(ids==rendered.ids&&spec.at("rendered_prompt")==rendered.chat.prompt,"official rendered input mismatch");
    const int cached=static_cast<int>(ids.size())-153;
    const auto prefix_begin=clock_type::now();for(int pos=0;pos<cached;pos+=256){const int n=std::min(256,cached-pos);r.call({ids.begin()+pos,ids.begin()+pos+n},pos,false);}
    const auto prefix_end=clock_type::now();const auto initial=r.snapshot();save(root/"initial.json",initial);
    common_chat_parser_params parser(rendered.chat);parser.parser.load(rendered.chat.parser);parser.reasoning_format=COMMON_REASONING_FORMAT_AUTO;
    const auto start=clock_type::now();if(profile=="B")check(llama_c262_set_layer_mode(r.ctx,2),"shared layer mode rejected");
    auto latest=r.call({ids.begin()+cached,ids.end()},cached,false);const auto prefill_end=clock_type::now();
    const auto elapsed=[&]{return std::chrono::duration<double>(clock_type::now()-start).count();};
    std::vector<llama_token> output;std::string text,finish="length",parse_error;int calls=0;
    const auto parse=[&](bool partial){try{return common_chat_parse(text,partial,parser);}catch(const std::runtime_error & e){
        const std::string reason=e.what();check(reason.find("The model produced output that does not match the expected ")==0,"unexpected native parser failure");parse_error=reason;return common_chat_msg{};}};
    double first_reasoning=-1,first_final=-1;json events=json::array();
    for(int i=0;i<768;++i){
        const auto token=greedy(latest.data());if(elapsed()>=360){finish="deadline";break;}
        output.push_back(token);const bool terminal=llama_vocab_is_eog(llama_model_get_vocab(r.model),token);
        if(!terminal)text+=common_token_to_piece(r.ctx,token,true);
        const auto message=parse(!terminal);const double observed=elapsed();
        if(first_reasoning<0&&!message.reasoning_content.empty())first_reasoning=observed;
        if(first_final<0&&text.find("<|channel|>final<|message|>")!=std::string::npos&&!message.content.empty())first_final=observed;
        events.push_back({{"native_id",token},{"observed_s",observed},{"terminal_eog",terminal}});
        if(terminal){finish="stop";break;}
        if(i==767)break;
        if(elapsed()>=360){finish="deadline";break;}
        latest=r.call({token},static_cast<int>(ids.size())+i,false);++calls;
        if(i%16==0)save(root/"progress.json",{{"status","PARTIAL_FREE_NATIVE_UTILITY"},{"profile",profile},{"official_input_ids",ids},{"native_output_ids",output},{"raw_generated_text",text},{"elapsed_s",elapsed()}});
    }
    const auto end=clock_type::now();const auto message=parse(finish!="stop");
    const auto seconds=[](auto a,auto b){return std::chrono::duration<double>(b-a).count();};
    save(root/"result.json",{{"status","COMPLETE_FREE_NATIVE_UTILITY_OBSERVATION"},{"profile",profile},{"case",argv[3]},
        {"official_input_ids",ids},{"provided_messages",task.at("messages")},{"cache_prefix_n",cached},{"evaluated_n",153},
        {"native_output_ids",output},{"output_count_including_eog",output.size()},{"decode_forward_calls",calls},{"finish_reason",finish},
        {"raw_generated_text",text},{"native_parser_error",parse_error},{"reasoning",message.reasoning_content},{"final",message.content},{"events",events},
        {"first_reasoning_s",first_reasoning<0?json(nullptr):json(first_reasoning)},{"first_final_s",first_final<0?json(nullptr):json(first_final)},
        {"prefix_preparation_s",seconds(prefix_begin,prefix_end)},
        {"cold_first_final_s",first_final<0?json(nullptr):json(seconds(prefix_begin,start)+first_final)},{"incremental_prefill_s",seconds(start,prefill_end)},
        {"cold_prefill_s",seconds(prefix_begin,prefix_end)+seconds(start,prefill_end)},
        {"decode_s",seconds(prefill_end,end)},{"completion_s",seconds(start,end)},
        {"decode_seconds_per_native_output",output.empty()?json(nullptr):json(seconds(prefill_end,end)/output.size())},
        {"request_start_monotonic_s",std::chrono::duration<double>(start.time_since_epoch()).count()},
        {"completion_monotonic_s",std::chrono::duration<double>(end.time_since_epoch()).count()},
        {"deadline_s",360},{"cap",768},{"initial",initial},{"final_state",r.snapshot()},
        {"sampling","Native deterministic greedy, temperature0/seed42, no stochastic claim"},
        {"count_convention","Native greedy output IDs including EOG, not generated-text retokenization; decode forwards counted separately, initial output comes from prefill"},
        {"scope","Constructed native warm153 from fixed provided published history near2K. Prewarm/drain/tokenization/model loading outside incremental request. Not C143 server cache reuse or cold end-to-end latency"}});
    return 0;
}catch(const std::exception & e){std::cerr<<"FREE_LAYER_UTILITY_FAIL "<<e.what()<<'\n';return 1;}}
