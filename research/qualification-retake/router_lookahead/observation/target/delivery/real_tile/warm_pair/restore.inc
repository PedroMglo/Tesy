// Compiled only in the warm child. All per-generation witnesses remain enabled in the shared client.
struct WarmWitness {
    const json *plan=nullptr;
    size_t next_reservation=0;
    std::set<std::thread::id> acks;
    json receipt,records=json::array(),sets=json::array();
} warm;

void warm_worker_ready(llama_moe_stream &m) {
    // Caller holds m.mtx after memset(staging, 0, 16 MiB). Its next wait releases m.mtx.
    need(isworker && warm.acks.insert(std::this_thread::get_id()).second,"duplicate scoped readiness");
    m.cv_done.notify_all();
}
void warm_reserve(int layer,int expert,int slot,int previous,uint64_t gen) {
    const auto &r=warm.plan->at("entries").at(warm.next_reservation++);
    need(r.at("layer")==layer && r.at("expert")==expert && r.at("slot")==slot &&
         r.at("previous")==previous && r.at("gen")==gen, "observed victim/order/slot/epoch differs");
}
static std::vector<int> seen_ids(const llama_moe_stream_layer &sl){
    std::vector<int> seen;
    for(size_t i=0;i<sl.seen.size();i++)if(sl.seen[i])seen.push_back(int(i));
    return seen;
}
static void verify_policy(llama_moe_stream &m,const json &p){
    need(p.at("loading").empty()&&p.at("fifo").empty()&&p.at("claims").empty()&&
         p.at("productive_workers")==std::vector<int>({0,1,2,3})&&m.q_demand.empty()&&m.workers.size()==4&&
         warm.acks.size()==4&&m.stats.n_calls==p.at("manager_calls").get<int64_t>()&&
         m.hot_decay_interval==p.at("hot_decay_interval").get<int64_t>(),"unverified cut, FIFO or scheduler");
    for(int l=0;l<2;l++){
        const auto &pool=p.at("pools").at(std::to_string(l));
        const auto &s=*m.layer(l);
        need(pool.at("slots").size()==40 && s.expert_slot.size()==40 &&
             s.use_counter==pool.at("use_counter").get<int64_t>() &&
             json(s.route_hotness)==pool.at("route_hotness") && json(seen_ids(s))==pool.at("seen") &&
             json(s.plan_pool)==pool.at("plan_pool") && json(s.demand_slots)==pool.at("last_demand") &&
             json(s.uniq)==pool.at("uniq") && s.plan_next_wave==pool.at("plan_next_wave").get<int>() &&
             s.plan_n_waves==pool.at("plan_n_waves").get<unsigned>() &&
             s.plan_capacity==pool.at("plan_capacity").get<unsigned>(),"layer policy clock/plan");
        for(int k=0;k<40;k++){
            const auto &b=pool.at("slots").at(k); int e=b.at("expert");
            need(b.at("slot")==k && b.at("state")==2 && b.at("claim").is_null() && s.slot_expert[k]==e &&
                 s.expert_slot.at(e)==k&&s.slot_gen[k]==b.at("generation").get<uint64_t>() &&
                 s.slot_last_use[k]==b.at("slot_last_use").get<int64_t>() &&
                 s.slot_state[k]==LLAMA_MOE_STREAM_SLOT_RESIDENT && !s.slot_claimed[k],"resident member/gen/age");
        }
    }
}
static void warm_finished(llama_moe_stream &m){
    if(std::uncaught_exceptions() || !warm.plan)return;
    verify_policy(m,warm.plan->at("terminal_policy"));
    need(warm.next_reservation==32,"terminal reservation census");
    warm.receipt["terminal_policy_verified"]=true;
}
static void register_record(tesy_expert_store &store,const json &row){
    int l=row.at("layer"),e=row.at("expert"); need(l>=0 && l<2 && e>=0 && e<128,"pack key");
    uint64_t off=row.at("pack_offset");
    need(off==stride*uint64_t(128*l+e),"invalid shared record offset");
    store.data.validate_range(off,window_bytes);
    auto hashes=row.at("hashes").get<std::array<std::string,3>>();
    auto [it,unused]=wit.hashes.emplace(Key{l,e},hashes);
    need(it->second==hashes,"inconsistent SHA for same pack record");
    store.entries[l][e]={off,{0,slab,2*slab}};
}
static void restore_scoped(llama_moe_stream &m,const json &plan,std::array<uint8_t,128>& occupied) {
    warm.plan=&plan;
    auto start=now_ns();
    {
        std::unique_lock<std::mutex> lock(m.mtx);m.start_workers_locked();
        need(m.cv_done.wait_for(lock,std::chrono::seconds(5),[]{return warm.acks.size()==4;}),"worker ACK timeout");
    }
    need(m.prediction_stage->idle(),"nonempty shadow stage before restore");
    const auto &cut=plan.at("initial_policy");
    need(cut.at("manager_calls")==140 && cut.at("hot_decay_interval")==2304 &&
         plan.at("terminal_policy").at("manager_calls")==142,"independent global scheduler count");
    need(plan.at("warm_records").size()==80 && plan.at("offer_records").size()==4 &&
         plan.at("false_records").size()==3,"authentic steady-state slices");
    for(const auto &r:plan.at("offer_records"))register_record(*m.expert_store,r);
    void *raw=nullptr; need(posix_memalign(&raw,4096,window_bytes)==0&&raw,"aligned preparation staging");
    std::unique_ptr<uint8_t,decltype(&std::free)> staging(static_cast<uint8_t*>(raw),std::free);
    std::set<Key> slots,keys;
    for(const auto &r:plan.at("warm_records")){
        int l=r.at("layer"),e=r.at("expert"),s=r.at("slot"),g=r.at("gen");
        need(slots.emplace(l,s).second && keys.emplace(l,e).second && s>=0&&s<40&&g>0,"warm record bijection");
        register_record(*m.expert_store,r);
        const auto &b=cut.at("pools").at(std::to_string(l)).at("slots").at(s);
        need(b.at("expert")==e && b.at("generation")==g && b.at("slot_last_use")==r.at("slot_last_use"),"wrong warm bytes");
        auto t0=now_ns();auto n=__real_pread(wit.fd,staging.get(),window_bytes,r.at("pack_offset").get<off_t>());
        auto t1=now_ns();need(n==ssize_t(window_bytes),"restore read failed, short or EINTR");warm.records.push_back({l,e,s,g,t0,t1});
        auto &sl=*m.layer(l);
        for(int k=0;k<3;k++){
            auto *src=staging.get()+k*slab;
            auto *t=sl.weights.at(k).cache;size_t off=size_t(s)*slab;
            need(r.at("hashes").at(k)==digest(src,slab),"restored slab SHA");
            auto begin=now_ns();__real_ggml_backend_tensor_set(t,src,off,slab);auto end=now_ns();
            need(!std::memcmp(static_cast<uint8_t*>(t->data)+off,src,slab),"post-SET restored bytes");
            warm.sets.push_back({l,e,s,g,k,begin,end});
        }
        // No public map exposes the slot until all three authenticated SETs have completed.
        std::lock_guard<std::mutex> lock(m.mtx);
        need(sl.slot_state[s]==LLAMA_MOE_STREAM_SLOT_EMPTY&&sl.expert_slot.emplace(e,s).second,"warm primary occupied");
        sl.slot_expert[s]=e;sl.slot_gen[s]=g;sl.slot_last_use[s]=r.at("slot_last_use");
        sl.slot_state[s]=LLAMA_MOE_STREAM_SLOT_RESIDENT;
        if(l==1)occupied[e]=1;
    }
    {
        std::lock_guard<std::mutex> lock(m.mtx);
        m.hot_decay_interval=cut.at("hot_decay_interval");m.stats.n_calls=cut.at("manager_calls");
        m.window.next_route=m.stats.n_calls;
        for(int l=0;l<2;l++) {
            auto &s=*m.layer(l);const auto &pool=cut.at("pools").at(std::to_string(l));
            s.use_counter=pool.at("use_counter");s.route_hotness=pool.at("route_hotness").get<std::vector<uint32_t>>();
            for(int e:pool.at("seen"))s.seen.at(e)=1;
            s.uniq=pool.at("uniq").get<I>();s.plan_pool=pool.at("plan_pool").get<I>();
            s.demand_slots=pool.at("last_demand").get<I>();s.plan_next_wave=pool.at("plan_next_wave");
            s.plan_n_waves=pool.at("plan_n_waves");s.plan_capacity=pool.at("plan_capacity");
        }
        verify_policy(m,cut);
    }
    need(std::count(occupied.begin(),occupied.end(),1)==40,"warm destination occupancy");
    // Only (1,5) is admitted in this executable; tile-local offers cannot be reused in another cut.
    bool old=false,repeated=false;
    try { m.select_prefill_tile(2,1); } catch (const std::runtime_error &) {old=true;}
    m.select_prefill_tile(1,5);
    try { m.select_prefill_tile(1,5); } catch (const std::runtime_error &) {repeated=true;}
    need(old&&repeated&&m.stage_site==5,"stale or foreign tile accepted");
    auto end=now_ns();
    warm.receipt={{"preads",warm.records.size()},{"pread_bytes",warm.records.size()*window_bytes},
        {"sets",warm.sets.size()},{"set_bytes",warm.sets.size()*slab},{"slab_hashes",240},
        {"postset_checks",240},{"worker_acks",warm.acks.size()},{"initial_policy_verified",true},
        {"terminal_policy_verified",false},{"elapsed_ns",end-start},{"records",std::move(warm.records)},
        {"set_intervals",std::move(warm.sets)},{"stale_tile_rejected",true}};
}
static void check_offer_lifecycle(const json &r){
    const bool on=r.at("mode")=="ON";
    std::set<int> selected{6,13,20,21},true_jobs{20};
    std::map<int,int> dispatched,completed,consumed;
    for(const auto &e:r.at("stage_events")){
        int kind=e.at(0),expert=e.at(1);
        need(on&&selected.count(expert),"foreign stage key");
        if(kind==2)++dispatched[expert];
        if(kind==3)++completed[expert];
        if(kind==11){need(true_jobs.count(expert),"false proposal published");++consumed[expert];}
    }
    need(dispatched==completed && r.at("stage").at("issued")==int(on?4:0),"undrained stage reads");
    size_t completed_records=0,used=0;
    for(const auto &[e,n]:completed){need(n==1,"duplicate proposal read");completed_records+=n;}
    for(const auto &[e,n]:consumed){need(n==1&&completed.count(e),"duplicate/absent consumption");used+=n;}
    std::set<int> spec_reads;
    for(const auto &read:r.at("reads"))if(read.at(2).get<int64_t>())
        need(read.at(0)==1&&spec_reads.insert(read.at(1).get<int>()).second,"wrong speculative read");
    for(int e:spec_reads)need(completed.count(e),"speculative READ without stage completion");
    need(spec_reads.size()==completed_records && r.at("read_jobs")==32+completed_records-used,"service bytes not conserved");
    need(warm.receipt.at("terminal_policy_verified")==true,"incomplete warm audit");
}

static void warm_selftest(){
    // Faults affect the same gates as the arm, without opening the pack or creating any workers.
    auto manager=std::make_unique<llama_moe_stream>(2,40,4,true);
    auto rejected=[](auto op) {try {op();}catch(const std::runtime_error &){return true;}return false;};
    need(rejected([&]{manager->select_prefill_tile(1,1);}) &&
         rejected([&]{manager->select_prefill_tile(2,1);}),"foreign cold scope accepted");
    manager->select_prefill_tile(1,5);
    need(rejected([&]{manager->select_prefill_tile(1,5);}),"reused offer epoch accepted");
    json reservation={{"layer",1},{"expert",20},{"slot",3},{"previous",79},{"gen",2}};
    json plan={{"entries",json::array({reservation})}};
    warm.plan=&plan;
    warm_reserve(1,20,3,79,2);
    warm.next_reservation=0;
    need(rejected([]{warm_reserve(1,20,3,70,2);}),"wrong victim accepted");
    warm.next_reservation=0;
    need(rejected([]{warm_reserve(1,20,3,79,3);}),"stale generation accepted");
    warm.plan=nullptr;
    warm.receipt={{"terminal_policy_verified",true}};
    auto kind=[](int k,int e){return json::array({k,e});};
    json r={{"mode","ON"},{"stage",{{"issued",4}}},{"stage_events",json::array({
        kind(2,6),kind(3,6),kind(2,20),kind(3,20),kind(11,20)})},
        {"reads",json::array({json::array({1,6,1}),json::array({1,20,1})})},{"read_jobs",33}};
    check_offer_lifecycle(r);
    auto false_publish=r;false_publish["stage_events"].back()[1]=6;
    need(rejected([&]{check_offer_lifecycle(false_publish);}),"unused proposal published");
    auto stale=r;stale["stage_events"][1][1]=13;
    need(rejected([&]{check_offer_lifecycle(stale);}),"completion of nonexistent read accepted");
    r["read_jobs"]=32;
    need(rejected([&]{check_offer_lifecycle(r);}),"false load erased from service census");
}
