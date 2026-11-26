    ggml_backend_t backends[] = {gpu.get(), cpu.get()};
    ggml_backend_sched_ptr sched(ggml_backend_sched_new(backends, nullptr, 2, 256, false, false));
    need(bool(sched), "CUDA0/CPU scheduler");
    ggml_set_input(x);
    ggml_set_input(ids);
    ggml_set_input(mask);
    ggml_set_output(sum);
    ggml_backend_sched_set_tensor_backend(sched.get(), x, cpu.get());
    ggml_backend_sched_set_tensor_backend(sched.get(), ids, cpu.get());
    ggml_backend_sched_set_tensor_backend(sched.get(), mask, gpu.get());
    for (int i = 0; i < ggml_graph_n_nodes(g); ++i) {
        auto *n = ggml_graph_node(g, i);
        auto *target = n == input || n == observer ? cpu.get() : gpu.get();
        need(ggml_backend_supports_op(target, n), "unsupported pinned node placement");
        ggml_backend_sched_set_tensor_backend(sched.get(), n, target);
    }
    need(ggml_backend_sched_alloc_graph(sched.get(), g), "mixed graph allocation");
    for (auto *n : {up, gate, down, act, pairs, sum}) {
        need(ggml_backend_sched_get_tensor_backend(sched.get(), n) == gpu.get() &&
             n->buffer && !ggml_backend_buffer_is_host(n->buffer), "GPU FFN node");
    }
    need(up->src[0] == weights[2] && gate->src[0] == weights[0] && down->src[0] == weights[1],
         "MMID operand must be the original GPU weight");
    if (!s.gold()) {
        need(ggml_backend_sched_get_tensor_backend(sched.get(), observer) == cpu.get(),
             "host observer");
    }
    std::cout << "GPU_PLACEMENT 3 1 1 1\n";
