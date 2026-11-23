// Selected native R1 multigrid reference and cancellation continuity.
// Uses original production C75 calls without tensor delivery or backend edits.
#define main historical_native_main
#include "block_native_run.cpp"
#undef main
namespace {
bool cancel_native(void * data) { ++*static_cast<int *>(data); return true; }
void warmup(runtime & run,const std::vector<llama_token> & prefix,const std::vector<int> & plan) {
    int p=0;for(int n:plan){run.call({prefix.begin()+p,prefix.begin()+p+n},p,false);p+=n;}
    check(p==static_cast<int>(prefix.size()),"continuity prefill coverage invalid");
}
}
int main(int argc,char ** argv) {
    if(argc!=6){std::cerr<<"usage: block_continuity MODEL FIXTURE CASE ROOT B\n";return 2;}
    try {
        json fixtures;std::ifstream in(argv[2]);in>>fixtures;check(bool(in),"continuity fixture unavailable");
        const std::string id=argv[3];const int B=std::stoi(argv[5]);check(B==2||B==4||B==8,"continuity shape invalid");
        auto fixture=fixtures.at(id);const auto prefix=fixture.at("ids").get<std::vector<llama_token>>();
        const auto ids=fixture.at("continuation_ids").get<std::vector<llama_token>>();
        check(!prefix.empty()&&prefix.size()+3*B<=8192&&ids.size()>=static_cast<size_t>(3*B),"continuity input plan invalid");
        for(auto x:prefix)check(x>=0&&x<vocab,"invalid official prefix ID");
        for(auto x:ids)check(x>=0&&x<vocab,"invalid native continuation ID");
        auto plan=fixture.value("warmup_calls",std::vector<int>{});
        if(plan.empty())for(int n=static_cast<int>(prefix.size());n>0;n-=std::min(n,256))plan.push_back(std::min(n,256));
        int n=0;for(int x:plan){check(x>0&&x<=256&&n+x<=static_cast<int>(prefix.size()),"continuity warmup invalid");n+=x;}check(n==static_cast<int>(prefix.size()),"incomplete warmup");
        const std::filesystem::path root=argv[4];check(std::filesystem::create_directory(root),"continuity root reused");
        runtime run(argv[1]);warmup(run,prefix,plan);save(root/"initial-residency.json",run.snapshot());
        const int origin=static_cast<int>(prefix.size());std::vector<std::vector<float>> bases;json checks=json::array();
        for(int grid=0;grid<3;++grid){
            const int position=origin+grid*B;
            const std::vector<llama_token> actual(ids.begin()+grid*B,ids.begin()+(grid+1)*B);
            auto base=run.call(actual,position,true);bases.push_back(base);binary(root/("grid-"+std::to_string(grid)+".base.f32"),base);
            for(int known=1;known<=B;++known){
                // Rebuild completed grids from confirmed native inputs, never
                // use a speculative/rejected suffix in the clean R1 reference.
                run.trim(origin);
                for(int previous=0;previous<grid;++previous){
                    const auto clean=run.call({ids.begin()+previous*B,ids.begin()+(previous+1)*B},origin+previous*B,true);
                    check(std::memcmp(clean.data(),bases[previous].data(),clean.size()*4)==0,"completed grid rollback changed full logits");
                }
                auto padded=actual;std::fill(padded.begin()+known,padded.end(),0);
                const auto ref=run.call(padded,position,true);
                const bool same=std::memcmp(base.data(),ref.data(),static_cast<size_t>(known)*vocab*4)==0;
                binary(root/("grid-"+std::to_string(grid)+".known-"+std::to_string(known)+".f32"),ref);
                checks.push_back({{"grid",grid},{"position",position},{"known",known},{"fixed_padding",0},{"inputs",padded},{"complete_preceding_rows_bitwise",same}});
                save(root/"progress.json",{{"checks",checks},{"status",same?"PARTIAL_CONTINUITY":"FAIL_FUTURE_DEPENDENCE"}});
                check(same,"R1 future/rollback contamination");
            }
        }
        // Actual CPU executor cancellation with the native context and loaded
        // model, followed by a clean request on the same context.
        run.trim(origin);int abort_calls=0;llama_set_abort_callback(run.ctx,cancel_native,&abort_calls);
        auto batch=llama_batch_init(B,0,1);batch.n_tokens=B;
        for(int i=0;i<B;++i){batch.token[i]=ids[i];batch.pos[i]=origin+i;batch.n_seq_id[i]=1;batch.seq_id[i][0]=0;batch.logits[i]=true;}
        const int rc=llama_decode(run.ctx,batch);llama_batch_free(batch);llama_synchronize(run.ctx);
        llama_set_abort_callback(run.ctx,nullptr,nullptr);
        check(rc==2&&abort_calls>0,"native cancellation not witnessed as abort2");
        run.trim(origin);const auto clean=run.call({ids.begin(),ids.begin()+B},origin,true);
        check(std::memcmp(clean.data(),bases[0].data(),clean.size()*4)==0,"cancellation contaminated clean full-grid reference");
        save(root/"result.json",{{"status","PASS_SELECTED_MULTIGRID_R1_AND_NATIVE_CANCEL"},{"case",id},{"B",B},{"official_prefix_ids",prefix},
            {"native_continuation_ids",std::vector<llama_token>(ids.begin(),ids.begin()+3*B)},{"warmup_calls",plan},{"checks",checks},
            {"abort_rc",rc},{"abort_callback_calls",abort_calls},{"cancel_then_clean_full_logits_bitwise",true},
            {"scope","Three selected complete fixed grids, all partial prefixes, clean replay after rollback and native cancel. No universal causal or stochastic claim."}});
        save(root/"final-residency.json",run.snapshot());return 0;
    }catch(const std::exception & e){std::cerr<<"BLOCK_CONTINUITY_FAIL: "<<e.what()<<'\n';return 1;}
}
