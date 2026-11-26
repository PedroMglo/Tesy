    // This is the same allocated scheduler and weight tensor for every alias generation.
    std::vector<Outputs> result;
    const std::array<const char *,4> labels{"original", "replacement", "restore", "wrong_pages"};
    for (int epoch = 0; epoch < (packed ? 4 : 1); ++epoch) {
        if (packed) {
            if (epoch) {
                check(!arena->rebind(epoch - 1, epoch + 1, 1), "accepted stale publication");
                check(arena->rebind(epoch, epoch + 1, epoch % 2), "lost current generation");
            }
            state.layout = labels[epoch];
            state.slot39_tag = epoch % 2 ? 38 : 39;
        }
        state.unmasked.clear();
        state.masked.clear();
        state.sorts = 0;
        for (auto &stage : state.stages) {
            stage.completed = {};
            stage.pre.clear();
        }
        refill(epoch != 0, epoch);
        check(ggml_backend_sched_graph_compute(sched.get(),g)==GGML_STATUS_SUCCESS,"graph compute");
        ggml_backend_sched_synchronize(sched.get());
        if(!state.error.empty()) throw std::runtime_error(state.error);
        check(state.sorts==1,"missing CUDA argsort");
        for(auto &s:state.stages) check(s.completed==std::array<unsigned,3>{1,1,1},"missing split node");
        check(ggml_backend_sched_get_n_splits(sched.get()) == splits, "changed split plan");
        result.push_back({std::move(state.unmasked),std::move(state.masked),splits});
    }
    return result;
