    const auto build_ns = monotonic_ns() - build_start;
    const auto input_x = tile(in.activation,width), input_mix = tile(in.weights,4);
    const auto gold = tile(read<float>(p/"ffn_moe_out-0.bin",all*width),width);
    io_counts.fd = store.data.descriptor();
    io_counts.weights = observed.weights;
    const auto inherited = allowed_cpus(0);
    auto publish = [&]{put(x,input_x); put(r,ids); put(mix,input_mix);};
    auto compute = [&]{
        need(ggml_backend_sched_graph_compute(scheduler.get(),g)==GGML_STATUS_SUCCESS,"FFN compute");
        ggml_backend_sched_synchronize(scheduler.get());
        need(!invalid_tail,"tail precondition or finite value");
    };
    capture_wave=true;
    publish(); compute();
    capture_wave=false;
    equal(values<float>(out),gold,"cold independent FFN");
    const auto cold = manager_state(manager,observed.layer);
    const auto cold_io = io_evidence();
    need(cold_io==json{{"reads",5},{"sets",15},{"returned_bytes",5*window},{"set_bytes",15*slab}}, "cold service");
    save_wave_maps(output,ids,observed.layer);
    const auto original_workers=workers(inherited);
    auto params=ggml_threadpool_params_default(8);
    std::unique_ptr<ggml_threadpool,decltype(&ggml_threadpool_free)> pool(ggml_threadpool_new(&params),ggml_threadpool_free);
    need(bool(pool),"compute team");
    ggml_backend_cpu_set_threadpool(cpu,pool.get());
    const int measured = timing ? 7 : 0;
    std::vector<int64_t> times;
    for (int i=0; i<=measured; ++i) {
        const auto start=monotonic_ns();
        publish(); compute();
        const auto end=monotonic_ns();
        const auto actual=values<float>(out);
        equal(actual,gold,"resident independent FFN");
        need(manager_state(manager,observed.layer)==cold && io_evidence()==cold_io &&
             workers(inherited)==original_workers && manager.stats.n_hit==5*(i+1) &&
             manager.stats.n_wave_calls==8*(i+2) && manager.stats.n_waves_run==i+2,
             "service, workers and residency");
        if (i>0) times.push_back(end-start);
        if (i==measured) {
            std::ofstream f(output/"tile.f32",std::ios::binary);
            need(bool(f.write(reinterpret_cast<const char*>(actual.data()),actual.size()*sizeof(float))),"output");
        }
    }
    ggml_backend_cpu_set_threadpool(cpu,nullptr);
    return {{"mode",mode},{"times_ns",times},{"build_ns",build_ns},{"active_waves",active_count},
            {"cold",cold_io},{"slots",cold},{"graph_nodes",graph_nodes},{"mmids",observed.mmids.size()},
            {"graph_fingerprint",graph_signature},{"backend_splits",ggml_backend_sched_get_n_splits(scheduler.get())},
            {"workers_before_destructor",manager.workers.size()},{"full_ffn_values",gold.size()}};
