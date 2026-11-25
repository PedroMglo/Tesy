    const auto inherited = allowed_cpus(0);
    for(int i=0;i<12;++i) need(std::find(inherited.begin(),inherited.end(),i)!=inherited.end(), "target cores unavailable");
    io_counts.fd=store.data.descriptor();
    io_counts.weights=observed.weights;
    const auto input_x=tile(in.activation,width), input_mix=tile(in.weights,4);
    const auto gold=tile(read<float>(p/"ffn_moe_out-0.bin",all*width),width);
    auto publish=[&]{put(x,input_x);put(r,ids);put(mix,input_mix);};
    auto compute=[&]{
        need(ggml_backend_sched_graph_compute(scheduler.get(),g)==GGML_STATUS_SUCCESS,"FFN compute");
        ggml_backend_sched_synchronize(scheduler.get());
    };
    publish();
    compute();                         // Cold demand, before assigning compute masks.
    equal(values<float>(out),gold,"cold FFN gold");
    const auto cold=manager_state(manager,observed.layer);
    const auto cold_io=io_evidence();
    need(cold_io==json{{"reads",5},{"sets",15},{"returned_bytes",5*window},{"set_bytes",15*slab}},
         "cold syscall or SET conservation");
    const auto initial_workers=workers(inherited);
    need(team_observe_init()==0,"observer provider or callsite");
    for(auto &node:observed.mmids) {
        auto [wave,role]=node.second;
        need(team_observe_add(node.first,wave,role)==0,"MMID registration");
    }
    auto params=ggml_threadpool_params_default(8);
    if (mode!="R") {
        params.strict_cpu=true;
        for(int i=0;i<8;++i) params.cpumask[(mode=="A"?4:0)+i]=true;
    }
    const auto pool_start=monotonic_ns();
    std::unique_ptr<ggml_threadpool,decltype(&ggml_threadpool_free)> team(
            ggml_threadpool_new(&params),ggml_threadpool_free);
    need(bool(team),"native threadpool allocation");
    ggml_backend_cpu_set_threadpool(cpu,team.get());
    const auto pool_ns=monotonic_ns()-pool_start;
    json runs=json::array();
    for (int i=-1;i<4;++i) {
#ifdef TEAM_ORIGINAL
        bool mark=false;
#else
        bool mark=i==1 || i==2;
#endif
        auto before_workers=workers(inherited);
        const auto pub0=monotonic_ns();
        publish();
        const auto pub1=monotonic_ns();
        team_observe_begin(mark?1:0);
        const auto start=monotonic_ns();
        compute();
        const auto end=monotonic_ns();
        const auto num=team_observe_end();
        need(num==(mark?192:0),"MMID endpoint population");
        const auto data=values<float>(out);
        equal(data,gold,"resident C266 FFN");
        need(manager_state(manager,observed.layer)==cold && io_evidence()==cold_io,
             "nonresident path: I/O or assignment changed");
        need(workers(inherited)==initial_workers && before_workers==initial_workers, "worker churn");
        const int hot_done=i+2;
        need(manager.stats.n_wave_calls==8*(hot_done+1) && manager.stats.n_waves_run==hot_done+1 &&
             manager.stats.n_hit==5*hot_done && manager.stats.n_store_loads==5,
             "manager calls, hits or loads");
        auto audit=read_rows(num,start,end,mode,inherited);
        if (i>=0) {
            audit.update({{"on",mark},{"start_ns",start},{"end_ns",end},
                          {"publish_ns",pub1-pub0},{"fresh_hits",5},{"hot_reads",0},{"hot_sets",0}});
            runs.push_back(std::move(audit));
        }
        if (i==3) {
            std::ofstream f(output/"tile.f32",std::ios::binary);
            need(bool(f.write(reinterpret_cast<const char*>(data.data()),data.size()*sizeof(float))),"tile write");
        }
    }
    ggml_backend_cpu_set_threadpool(cpu,nullptr);
    return {{"team",mode},{"stock",stock},{"runs",runs},{"pool_setup_ns",pool_ns},{"inherited",inherited},
            {"io_workers",initial_workers},{"slots",cold},{"cold",cold_io},{"graph_nodes",graph_nodes},
            {"graph_fingerprint",graph_signature},{"backend_splits",ggml_backend_sched_get_n_splits(scheduler.get())},
            {"router_positions",153},{"mmids",24},{"active_waves",1},{"finite_ffn_values_per_call",92160},
            {"workers_before_destructor",manager.workers.size()},
            {"providers",{{"cpu",provider(reinterpret_cast<void *>(&ggml_backend_cpu_init))},
                          {"base",provider(reinterpret_cast<void *>(&ggml_backend_sched_graph_compute))}}}};
