// Native controlled service screen, using the existing C-API client/supervisor.
#define main previous_native_main
#include "block_native_run.cpp"
#undef main

int main(int argc,char ** argv){try{
    check(argc==7&&std::string(argv[6])=="v1","usage MODEL FIXTURE CASE NEWROOT A|B v1");
    const std::string profile=argv[5];check(profile=="A"||profile=="B","profile invalid");
    const char * span=getenv("TESY_C262_LAYER_SPAN");
    check(profile=="A"?!span:(span&&std::string(span)=="153"),"production profile environment mismatch");
    std::ifstream f(argv[2]);json fixtures;f>>fixtures;check(bool(f),"fixture missing");
    const auto ids=fixtures.at(argv[3]).at("ids").get<std::vector<llama_token>>();
    const auto tokens=fixtures.at(argv[3]).at("continuation_ids").get<std::vector<llama_token>>();
    check(ids.size()==2197&&tokens.size()>=32,"frozen2197+32 input contract absent");
    const std::filesystem::path root=argv[4];check(std::filesystem::create_directory(root),"native root reused");
    runtime r(argv[1]);const auto prepare_begin=clock_type::now();
    for(int pos=0;pos<2044;pos+=256){const int n=std::min(256,2044-pos);r.call({ids.begin()+pos,ids.begin()+pos+n},pos,false);}
    const auto prepare_end=clock_type::now();const auto initial=r.snapshot();
    if(profile=="B")check(llama_c262_set_layer_mode(r.ctx,2),"shared layer mode rejected");
    save(root/"initial.json",initial);
    const auto begin=clock_type::now();auto logits=r.call({ids.begin()+2044,ids.end()},2044,false);
    const auto prefill_end=clock_type::now();const auto prefill_logits=logits;
    std::vector<int> winners={greedy(logits.data())};
    for(int i=0;i<32;++i){logits=r.call({tokens[i]},2197+i,false);winners.push_back(greedy(logits.data()));}
    const auto end=clock_type::now();const auto final=r.snapshot();
    // No intermediate expert drain, tensor capture, dump, witness or file write
    // between begin/end. Output-row materialization/greedy is common and counted.
    binary(root/"prefill.logits.f32",prefill_logits);binary(root/"last-decode.logits.f32",logits);
    const auto seconds=[](auto a,auto b){return std::chrono::duration<double>(b-a).count();};
    save(root/"result.json",{{"status","COMPLETE_CONTROLLED_WARM153_NATIVE_SERVICE"},{"profile",profile},
      {"official_input_ids",ids},{"teacher_forced_ids",std::vector<int>(tokens.begin(),tokens.begin()+32)},
      {"native_argmax_ids",winners},{"initial",initial},{"final",final},
      {"prefix2044_s",seconds(prepare_begin,prepare_end)},{"prefill153_s",seconds(begin,prefill_end)},
      {"decode32_s",seconds(prefill_end,end)},{"total_s",seconds(begin,end)},
      {"external_prefill_calls",{256,256,256,256,256,256,256,252,153}},
      {"decode_calls",32},{"decode_positions",{2197,2228}},
      {"output_rows",33},{"FFN_last_layer_rows_per_call",1},{"layerspan",profile=="A"?32:153},
      {"numerical_FFN_tiles",profile=="A"?json{32,32,32,32,25}:json{32,32,32,32,25}},
      {"teacher_forcing","Fixed native published inputs; not generated/committed throughput"},
      {"timing","Synchronized C-API full-row materialization; prefill then32n1 with no intermediate dump/drain; final drain outside clock"}});
    return 0;
}catch(const std::exception & e){std::cerr<<"PREFILL_SERVICE_FAIL "<<e.what()<<'\n';return 1;}}
