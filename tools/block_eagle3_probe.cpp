#include "block_eagle3_runtime.h"

int main(int argc,char ** argv){
    if(argc==2 && std::string(argv[1])=="--self-test"){
        try{for(int start:{1,189,2044}){
            require_clean_head_tail(start-1,start);
            bool failed=false;try{require_clean_head_tail(start+5,start);}catch(const std::exception&){failed=true;}
            check(failed,"stale draft KV was accepted");}
            std::cout<<"{\"status\":\"PASS_MODEL_FREE_HEAD_KV_BOUNDARY\",\"weights_loaded\":false}\n";return 0;
        }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
    }
    if(argc!=7){std::cerr<<"usage: block_eagle3_probe TARGET HEAD FIXTURE CASE NEW_ROOT v1\n";return 2;}
    try{
        check(std::string(argv[6])=="v1","unfrozen head boundary");
        std::ifstream file(argv[3]);json fixture;file>>fixture;check(bool(file),"head input fixture missing");
        const auto row=fixture.at(argv[4]);const auto prefix=row.at("ids").get<std::vector<llama_token>>();
        const auto historical=row.at("continuation_ids").get<std::vector<llama_token>>();
        check(prefix.size()==189 && historical.size()>=8,"selected head boundary differs from freeze");
        for(auto token:prefix)check(token>=0&&token<vocab,"invalid official input ID");
        for(auto token:historical)check(token>=0&&token<vocab,"invalid historical input ID");
        const std::filesystem::path root=argv[5];check(std::filesystem::create_directory(root),"head root reused");
        runtime target(argv[1]);head_runtime head(target,argv[2]);
        double prefill_features_s=0,verification_features_s=0;
        const auto prefill_begin=clock_type::now();auto latest=target_call(target,&head,prefix,0,false,prefill_features_s);
        const double prefill_total=std::chrono::duration<double>(clock_type::now()-prefill_begin).count();
        common_speculative_begin(head.spec,0,prefix);save(root/"initial-residency.json",target.snapshot());
        // Feature extraction must not alter target arithmetic. Historical same-B
        // rows are written for an independent bitwise gate before economic use.
        double unused=0;
        auto neutral=target_call(target,nullptr,{historical.begin(),historical.begin()+8},189,true,unused);
        binary(root/"feature-enabled-historical.logits.f32",neutral);target.trim(189);
        const auto anchor=greedy(latest.data());llama_tokens proposals;
        auto & dp=common_speculative_get_draft_params(head.spec,0);
        dp.drafting=true;dp.n_max=7;dp.n_past=189;dp.id_last=anchor;dp.prompt=&prefix;dp.result=&proposals;
        const auto draft_begin=clock_type::now();common_speculative_draft(head.spec);llama_synchronize(head.ctx);
        const double draft_s=std::chrono::duration<double>(clock_type::now()-draft_begin).count();
        check(proposals.size()==7,"head did not produce frozen seven proposals");
        greedy(llama_get_logits_ith(head.ctx,-1)); // finite complete last native head logit row
        for(auto token:proposals)check(token>=0&&token<vocab,"head proposed invalid ID");
        std::vector<llama_token> block{anchor};block.insert(block.end(),proposals.begin(),proposals.end());
        const int head_pos_before=llama_memory_seq_pos_max(llama_get_memory(head.ctx),0);
        check(llama_memory_seq_rm(llama_get_memory(head.ctx),0,189,-1),"head KV suffix removal failed");
        const int head_pos_after=llama_memory_seq_pos_max(llama_get_memory(head.ctx),0);
        require_clean_head_tail(head_pos_after,189);
        save(root/"progress.json",{{"status","HEAD_DRAFT_COMPLETE_BEFORE_VERIFICATION"},{"native_proposed_ids",proposals},
            {"anchor_known_input",anchor},{"draft_seven_s",draft_s},{"head_KV_before_trim",head_pos_before},{"head_KV_after_trim",head_pos_after},
            {"prefill_total_s",prefill_total},{"prefill_head_processing_s",prefill_features_s}});
        const auto verification_begin=clock_type::now();const auto observed=target_call(target,&head,block,189,true,verification_features_s);
        const double verification_total=std::chrono::duration<double>(clock_type::now()-verification_begin).count();
        binary(root/"head-verification.logits.f32",observed);
        json causal=json::array();int accepted=0;
        for(int known=1;known<=8;++known){auto padded=block;std::fill(padded.begin()+known,padded.end(),0);target.trim(189);
            auto reference=target_call(target,nullptr,padded,189,true,unused);
            const bool equal=std::memcmp(observed.data(),reference.data(),static_cast<size_t>(known)*vocab*sizeof(float))==0;
            causal.push_back({{"known",known},{"prefix_only_inputs",padded},{"preceding_rows_bitwise",equal}});
            check(equal,"head proposed future changes prefix-only R1 target");
            if(known<=7 && accepted==known-1 && greedy(observed.data()+static_cast<size_t>(known-1)*vocab)==proposals[known-1])++accepted;
        }
        json winners=json::array();for(int i=0;i<8;++i)winners.push_back(greedy(observed.data()+static_cast<size_t>(i)*vocab));
        const auto correction=greedy(observed.data()+static_cast<size_t>(accepted)*vocab);
        common_speculative_accept(head.spec,0,accepted);
        json result={{"status","PASS_SELECTED_HEAD_BOUNDARY"},{"case",argv[4]},{"B",8},{"K",7},
            {"anchor_known_input",anchor},{"native_proposed_ids",proposals},{"accepted_draft_count",accepted},
            {"new_confirmable_tokens",accepted+1},{"correction_or_bonus",correction},{"target_native_argmax",winners},
            {"official_prefix_ids",prefix},{"head_target_layers",{2,18,33}},{"head_ngl",1},{"head_sampling","top-k10 sorted first; p_min0, no backend sampling"},
            {"target_profile","C75/P12/slots40/ub32/ctx8192/GOMPunset"},{"prefill_total_s",prefill_total},
            {"prefill_head_processing_s",prefill_features_s},{"draft_seven_s",draft_s},
            {"verify_plus_head_process_s",verification_total},{"verification_head_processing_s",verification_features_s},
            {"R1_causal_checks",causal},{"head_KV_before_trim",head_pos_before},{"head_KV_after_trim",head_pos_after},{"head_KV_pos_max",llama_memory_seq_pos_max(llama_get_memory(head.ctx),0)},
            {"scope","Selected one-grid head/feature boundary; no integrated throughput, continuity, rollback or product gain claim"}};
        save(root/"result.json",result);save(root/"final-residency.json",target.snapshot());std::cout<<result.dump()<<"\n";return 0;
    }catch(const std::exception & e){std::cerr<<"HEAD_BOUNDARY_FAIL: "<<e.what()<<"\n";return 1;}
}
