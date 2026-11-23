#include "llama-moe-stream.h"
#include "ggml.h"
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>

#include "residency_journal_window.inl"

static void check(bool x,const char * why){if(!x)throw std::runtime_error(why);}
int main(int argc,char ** argv) {
    try {
        check(argc==3,"OUTPUT MODE");std::filesystem::path root=argv[1];
        check(std::filesystem::create_directory(root),"fixture output must be new");
        setenv("TESY_C84_EXPERT_TRACE_FILE",(root/"journal.trace").c_str(),1);
        setenv("TESY_C152_ROUTE_FILE",(root/"routes.bin").c_str(),1);
        setenv("TESY_C152_SNAPSHOT_ENABLED","1",1);
        const char * zeros="0000000000000000000000000000000000000000000000000000000000000000";
        for(auto k:{"TESY_C152_MODEL_HASH","TESY_C152_SOURCE_HASH","TESY_C152_BUILD_HASH","TESY_C152_PROFILE_HASH"})setenv(k,zeros,1);
        llama_moe_stream mgr(1,4,1,false);
        mgr.layers[0]=std::make_unique<llama_moe_stream_layer>();auto & sl=*mgr.layers[0];
        sl.mgr=&mgr;sl.il=0;sl.n_expert=128;sl.n_slots=4;
        sl.slot_expert={0,1,2,3};sl.slot_state.assign(4,2);sl.slot_claimed.assign(4,0);
        sl.slot_gen.assign(4,1);sl.slot_last_use={1,2,3,4};sl.keep.assign(4,0);
        sl.route_hotness.assign(128,1);sl.seen.assign(128,0);sl.use_counter=4;
        for(int i=0;i<4;++i){sl.expert_slot[i]=i;sl.seen[i]=1;}
        std::string mode=argv[2];
        if(mode=="remap") {mgr.hot_decay_interval=64;mgr.stats.n_calls=63;sl.route_hotness[0]=std::numeric_limits<uint32_t>::max();}
        mgr.journal_request(1);mgr.trace_begin_call(2,0,1);
        mgr.snapshot((root/"before.snap").c_str(),0,0,0,1);
        if(mode=="remap") {
            int32_t ids[]={0,1,4,5,0,1,4,5},out[8]{};
            ggml_init_params p{ggml_tensor_overhead()*2,nullptr,true};auto * c=ggml_init(p);
            auto * a=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,2);auto * b=ggml_new_tensor_2d(c,GGML_TYPE_I32,4,2);
            a->data=ids;b->data=out;
            llama_moe_stream_remap(b,a,0,1,&sl);
            check(sl.route_hotness[0]==std::numeric_limits<uint32_t>::max()/2,"saturating distinct hotness/decay");
            check(out[0]==out[4]&&out[2]==out[6],"multiplicity stable");
            check(sl.uniq==std::vector<int32_t>({0,1,4,5}),"first use order");ggml_free(c);
        } else if(mode=="loading"||mode=="window") {
            sl.keep[0]=1;sl.slot_state[1]=1;sl.slot_claimed[1]=1;
            mgr.snapshot_work_id=7;mgr.owned_work[0]={&sl,1,1,1,1,123,7};mgr.owned_phase[0].store(2);
            check(mgr.pick_victim_locked(sl,sl.keep.data())==2,"keep/loading excluded");
            mgr.reserve_slot_locked(sl,4,2);mgr.queue_load_locked(&sl,4,2);
            mgr.queue_load_locked(&sl,4,2); // legal promotion duplicate, unique work IDs
            check(mgr.q_demand[0].snapshot_work_id!=mgr.q_demand[1].snapshot_work_id,"unique queue identity");
            if(mode=="window") {
                mgr.trace_end_call(2,0,1);
                mgr.snapshot((root/"pending-before.snap").c_str(),1,1,0,1);
                reset_warmup_journal(&mgr);mgr.journal_request(2);
                mgr.snapshot((root/"pending-after.snap").c_str(),0,1,0,1);
                std::cout<<"NATIVE_WARM_WINDOW_PENDING_PASS no drain or state mutation\n";return 0;
            }
        } else if(mode=="wave") {
            sl.plan_capacity=3;int32_t ids[]={0,1,2,3,4,5,0,1};
            mgr.plan_waves_locked(sl,ids,8);
            check(sl.route_hotness[0]==1,"wave planning must not remap hotness");
            check(sl.plan_n_waves==2&&sl.expert_wave[5]==1,"source wave assignment");
        } else throw std::runtime_error("unknown fixture");
        mgr.trace_end_call(2,0,1);mgr.snapshot((root/"after.snap").c_str(),1,2,0,1);
        std::cout<<"C152_NATIVE_LOGICAL_FIXTURE_PASS mode="<<mode<<" (no tensor weights, no model)\n";
        return 0;
    }catch(const std::exception & e){std::cerr<<e.what()<<'\n';return 1;}
}
