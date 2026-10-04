// Greedy fixed-grid head integration using existing target/speculative APIs.
#include "block_eagle3_runtime.h"
#include <memory>

struct accepted_grid {
    std::vector<llama_token> tokens;
    int matched=0,feature_row=-1;
    std::string finish="CONTINUE";
};

accepted_grid accept_rows(int known,const std::vector<llama_token> & input,const std::vector<llama_token> & winners,int remaining,const llama_vocab * v){
    check(known>=1 && known<=8 && input.size()==8 && winners.size()==8 && remaining>0,"invalid complete grid acceptance");
    accepted_grid out;
    for(int row=known-1;row<8;++row){const auto token=winners[row];out.tokens.push_back(token);out.feature_row=row;
        const bool match=row<7 && token==input[row+1];if(match)++out.matched;
        if(v && llama_vocab_is_eog(v,token)){out.finish="EOS";break;}
        if(static_cast<int>(out.tokens.size())==remaining){out.finish="DIAGNOSTIC_CAP";break;}
        if(row==7 || !match)break;
    }
    return out;
}

int main(int argc,char ** argv){
    if(argc==2 && std::string(argv[1])=="--self-test"){
        try{for(int known=1;known<=8;++known){std::vector<llama_token> input{20,21,22,23,24,25,26,27},winners{21,22,23,24,25,26,27,28};
            auto all=accept_rows(known,input,winners,30,nullptr);check(static_cast<int>(all.tokens.size())==9-known && all.matched==8-known && all.feature_row==7,"all-accept/bonus accounting failed");
            for(int bad=known-1;bad<8;++bad){auto mutated=winners;mutated[bad]=99;auto rejection=accept_rows(known,input,mutated,30,nullptr);
                check(static_cast<int>(rejection.tokens.size())==bad-known+2 && rejection.feature_row==bad,"first/middle/last reject accounting failed");}
            check(accept_rows(known,input,winners,1,nullptr).tokens.size()==1,"cap counted anchor/bonus twice");}
            std::cout<<"{\"status\":\"PASS_MODEL_FREE_NATIVE_GRID_ACCEPTANCE\",\"weights_loaded\":false}\n";return 0;
        }catch(const std::exception & e){std::cerr<<e.what()<<"\n";return 1;}
    }
    if(argc!=9){std::cerr<<"usage: block_eagle3_loop TARGET HEAD FIXTURE CASE NEW_ROOT MODE(ar|head-diagnostic|head-measure) COUNT v1\n";return 2;}
    try{
        const std::string mode=argv[6];const int count=std::stoi(argv[7]);check(std::string(argv[8])=="v1" && (count==32 || count==16),"unfrozen integrated loop");
        check(mode=="ar" || mode=="head-diagnostic" || mode=="head-measure","unknown loop mode");
        std::ifstream file(argv[3]);json fixtures;file>>fixtures;check(bool(file),"loop fixture missing");const auto fixture=fixtures.at(argv[4]);
        const auto prefix=fixture.at("ids").get<std::vector<llama_token>>();check(!prefix.empty() && prefix.size()+64+8<=8192,"loop prefix/context invalid");
        for(auto token:prefix)check(token>=0 && token<vocab,"invalid official prefix ID");
        const std::filesystem::path root=argv[5];check(std::filesystem::create_directory(root),"integrated root reused");
        runtime target(argv[1]);std::unique_ptr<head_runtime> head;if(mode!="ar")head=std::make_unique<head_runtime>(target,argv[2]);
        auto calls=fixture.value("warmup_calls",std::vector<int>{});const int origin=static_cast<int>(prefix.size());
        if(calls.empty())for(int left=origin;left>0;left-=std::min(left,256))calls.push_back(std::min(left,256));
        double prefill_features=0;int position=0;std::vector<float> latest;const auto prefill_begin=clock_type::now();
        for(int n:calls){check(n>0 && n<=256 && position+n<=origin,"invalid prefill call plan");latest=target_call(target,head.get(),{prefix.begin()+position,prefix.begin()+position+n},position,false,prefill_features);position+=n;}
        check(position==origin,"prefill coverage missing");const double prefill_s=std::chrono::duration<double>(clock_type::now()-prefill_begin).count();
        if(head){common_speculative_begin(head->spec,0,prefix);}
        save(root/"initial-residency.json",target.snapshot());
        // The initial token is already validated by prefill, not counted again
        // in the measured decode-confirmed numerator.
        llama_tokens confirmed{greedy(latest.data())};json rows=json::array();const auto start=clock_type::now();int complete_rows=0,target_calls=0;
        double draft_s=0,head_process_s=0,reference_s=0;std::string finish="DIAGNOSTIC_CAP";
        while(static_cast<int>(confirmed.size())-1<count){
            const int remaining=count-static_cast<int>(confirmed.size())+1;
            if(mode=="ar"){
                double no_head=0;latest=target_call(target,nullptr,{confirmed.back()},origin+static_cast<int>(confirmed.size())-1,true,no_head);++target_calls;++complete_rows;
                const auto next=greedy(latest.data());confirmed.push_back(next);
                rows.push_back({{"B",1},{"input",confirmed[confirmed.size()-2]},{"confirmed",next}});
                if(llama_vocab_is_eog(llama_model_get_vocab(target.model),next)){finish="EOS";break;}
            }else{
                const int grid_offset=((static_cast<int>(confirmed.size())-1)/8)*8;
                const int known=static_cast<int>(confirmed.size())-grid_offset;const int grid_start=origin+grid_offset;
                check(known>=1 && known<=8 && grid_start+8<=8192,"fixed grid context/position invalid");
                llama_tokens proposed;llama_tokens history=prefix;history.insert(history.end(),confirmed.begin(),confirmed.end()-1);
                if(known<8){auto & dp=common_speculative_get_draft_params(head->spec,0);dp.drafting=true;dp.n_max=7;dp.n_past=origin+static_cast<int>(confirmed.size())-1;dp.id_last=confirmed.back();dp.prompt=&history;dp.result=&proposed;
                    const auto d0=clock_type::now();common_speculative_draft(head->spec);llama_synchronize(head->ctx);draft_s+=std::chrono::duration<double>(clock_type::now()-d0).count();
                    check(proposed.size()==7,"short head proposal changes fixed numerical shape");greedy(llama_get_logits_ith(head->ctx,-1));}
                std::vector<llama_token> input(confirmed.begin()+grid_offset,confirmed.end());input.insert(input.end(),proposed.begin(),proposed.begin()+(8-known));
                check(input.size()==8,"all-position verification missing");
                std::string diagnostic_pattern="REAL_HEAD_UNMODIFIED";
                if(mode=="head-diagnostic" && rows.size()<4 && known<8){
                    const int attempt=static_cast<int>(rows.size());
                    const int reject_index=attempt==0 ? -1 : (attempt==1 ? 0 : (attempt==2 ? std::min(3,7-known) : 7-known));
                    diagnostic_pattern=attempt==0 ? "ORACLE_ALL_ACCEPT" : "ORACLE_REJECT_"+std::to_string(reject_index);
                    const auto diagnostic_start=clock_type::now();double dummy=0;
                    for(int proposal=0;proposal<8-known;++proposal){
                        auto clean=input;std::fill(clean.begin()+known+proposal,clean.end(),0);target.trim(grid_start);
                        const auto oracle=target_call(target,nullptr,clean,grid_start,true,dummy);
                        const auto authority=greedy(oracle.data()+static_cast<size_t>(known+proposal-1)*vocab);
                        if(proposal==reject_index){input[known+proposal]=(authority+1)%vocab;break;}
                        input[known+proposal]=authority;
                    }
                    reference_s+=std::chrono::duration<double>(clock_type::now()-diagnostic_start).count();
                }
                target.trim(grid_start);
                check(llama_memory_seq_rm(llama_get_memory(head->ctx),0,grid_start,-1),"integrated head suffix trim failed");
                require_clean_head_tail(llama_memory_seq_pos_max(llama_get_memory(head->ctx),0),grid_start);
                double unused=0;auto observed=target_call(target,nullptr,input,grid_start,true,unused);++target_calls;complete_rows+=8;
                std::vector<llama_token> winners;for(int row=0;row<8;++row)winners.push_back(greedy(observed.data()+static_cast<size_t>(row)*vocab));
                auto accepted=accept_rows(known,input,winners,remaining,llama_model_get_vocab(target.model));
                int reference_checks=0;
                if(mode=="head-diagnostic")binary(root/("iter-"+std::to_string(rows.size())+"-observed.logits.f32"),observed);
                if(mode=="head-diagnostic"){
                    const auto r0=clock_type::now();
                    for(int row=known-1;row<=accepted.feature_row;++row){auto clean=input;std::fill(clean.begin()+row+1,clean.end(),0);target.trim(grid_start);
                        const auto reference=target_call(target,nullptr,clean,grid_start,true,unused);
                        binary(root/("iter-"+std::to_string(rows.size())+"-ref-known-"+std::to_string(row+1)+".logits.f32"),reference);
                        check(std::memcmp(observed.data(),reference.data(),static_cast<size_t>(row+1)*vocab*sizeof(float))==0,"integrated accepted/correction row differs from clean draft-independent R1");++reference_checks;}
                    target.trim(grid_start);auto restored=target_call(target,nullptr,input,grid_start,true,unused);
                    check(std::memcmp(restored.data(),observed.data(),observed.size()*sizeof(float))==0,"diagnostic restore changed candidate full rows");reference_s+=std::chrono::duration<double>(clock_type::now()-r0).count();
                }
                // Target feature buffers correspond to the final complete call.
                // Process exactly that same batch before releasing its arrays.
                llama_batch batch=llama_batch_init(8,0,1);batch.n_tokens=8;
                for(int row=0;row<8;++row){batch.token[row]=input[row];batch.pos[row]=grid_start+row;batch.n_seq_id[row]=1;batch.seq_id[row][0]=0;batch.logits[row]=true;}
                const auto p0=clock_type::now();check(common_speculative_process(head->spec,batch),"integrated feature process failed");llama_synchronize(head->ctx);head_process_s+=std::chrono::duration<double>(clock_type::now()-p0).count();llama_batch_free(batch);
                // Eagle3's accept argument selects the absolute feature row, not
                // the number of newly accepted proposals when a grid is partial.
                common_speculative_accept(head->spec,0,static_cast<uint16_t>(accepted.feature_row));
                rows.push_back({{"B",8},{"diagnostic_pattern",diagnostic_pattern},{"grid_start",grid_start},{"known_rows",known},{"native_proposals",proposed},{"target_inputs",input},
                    {"target_argmax",winners},{"accepted_draft_count",accepted.matched},{"new_confirmed",accepted.tokens},{"feature_row",accepted.feature_row},
                    {"clean_R1_checked_rows",reference_checks},{"head_KV_max",llama_memory_seq_pos_max(llama_get_memory(head->ctx),0)}});
                confirmed.insert(confirmed.end(),accepted.tokens.begin(),accepted.tokens.end());
                if(accepted.finish=="EOS"){finish="EOS";break;}
            }
            save(root/"progress.json",{{"status","PARTIAL_NATIVE_CONFIRMED_LOOP"},{"mode",mode},{"initial_anchor",confirmed.front()},
                {"native_confirmed_ids",confirmed},{"decode_confirmed_excluding_anchor",confirmed.size()-1},{"iterations",rows}});
        }
        const double wall=std::chrono::duration<double>(clock_type::now()-start).count();
        json result={{"status","MEASURED_NATIVE_CONFIRMED_LOOP"},{"case",argv[4]},{"mode",mode},{"count_limit",count},
            {"official_prefix_ids",prefix},{"warmup_calls",calls},{"initial_anchor",confirmed.front()},{"native_confirmed_ids",confirmed},
            {"decode_confirmed_excluding_anchor",confirmed.size()-1},{"finish",finish},{"wall_s",wall},{"prefill_total_s",prefill_s},
            {"prefill_head_processing_s",prefill_features},{"draft_total_s",draft_s},{"verification_head_processing_s",head_process_s},
            {"diagnostic_reference_s",reference_s},{"target_verification_calls",target_calls},{"target_full_logit_rows",complete_rows},
            {"iterations",rows},{"R1","Fixed origin/B8 completed grids, partial-grid confirmed prefix, deterministic causal padding reference"},
            {"throughput_convention","new target-confirmed decode tokens excluding initial prefill anchor / measured loop wall; all discarded draft, remap and partial-grid reprocessing included"},
            {"scope","Native integration development, not natural functional completion or stochastic qualification"}};
        save(root/"result.json",result);save(root/"final-residency.json",target.snapshot());std::cout<<result.dump()<<"\n";return 0;
    }catch(const std::exception & e){std::cerr<<"HEAD_LOOP_FAIL: "<<e.what()<<"\n";return 1;}
}
