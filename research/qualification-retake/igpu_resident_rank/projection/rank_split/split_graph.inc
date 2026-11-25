// The parent keeps the four verified slot-generation bindings and six weight/bias tensors alive.
struct SplitGraph {
    ggml_tensor *free_input = nullptr;
    ggml_context_ptr ctx = context();
    ggml_backend_sched_ptr sched;
    ggml_cgraph *graph;
    ggml_tensor *x, *logical, *physical_ids, *mix, *sum = nullptr;
    std::array<ggml_tensor *,4> rows{};

    ggml_tensor *id_view(ggml_tensor *ids, int first, int count) {
        return ggml_view_2d(ctx.get(), ids, count, 1, ids->nb[1], first * ids->nb[0]);
    }

    void append_group(int first, int count) {
        auto *c = ctx.get();
        // The full arm retains the exact operand geometry of the four-rank reference.
        auto *ids = count == 4 ? logical : id_view(logical, first, count);
        auto *slots = count == 4 ? physical_ids : id_view(physical_ids, first, count);
        auto *weights = count == 4 ? mix : ggml_view_3d(
            c, mix, 1, count, 1, mix->nb[1], mix->nb[2], first * mix->nb[1]);
        auto *biased = pairs(c, state.tensors, x, ids, slots);
        auto *weighted = ggml_mul(c, biased, weights);
        need(weighted->type == GGML_TYPE_F32 && weighted->ne[0] == width &&
             weighted->ne[1] == count && weighted->ne[2] == 1 &&
             weighted->nb[1] == width * sizeof(float), "weighted rank geometry");
        // A post-clock read must still see these words after the ordered reduction has run.
        ggml_set_output(weighted);
        ggml_build_forward_expand(graph, weighted);
        for (int i = 0; i < count; ++i) {
            rows[first+i] = ggml_view_2d(c, weighted, width, 1, weighted->nb[2], i * weighted->nb[1]);
        }
    }

    SplitGraph(ggml_backend_t cpu, const std::string &mode, const Input &in,
               const I &physical, const F &weighted_gold) {
        need(mode == "Full" || mode == "Serial" || mode == "Free", "unknown rank geometry");
        need(cpu && in.x.size() == width && in.weights.size() == 4 &&
             in.ids == I(keys.begin(), keys.end()) && physical == I(dest.begin(), dest.end()),
             "split graph requires the authoritative 189 route and slot order");
        auto *c = ctx.get();
        graph = ggml_new_graph_custom(c, 256, false);
        x = ggml_new_tensor_2d(c, GGML_TYPE_F32, width, 1);
        logical = ggml_new_tensor_2d(c, GGML_TYPE_I32, 4, 1);
        physical_ids = ggml_new_tensor_2d(c, GGML_TYPE_I32, 4, 1);
        mix = ggml_new_tensor_3d(c, GGML_TYPE_F32, 1, 4, 1);
        for (auto *v : {x, logical, physical_ids, mix}) {
            ggml_set_input(v);
            // GGML can repurpose an INPUT after its last consumer in a single run. These
            // repeated resident graphs must retain the same four leaves across executions.
            ggml_set_output(v);
        }

        if (mode == "Full") {
            append_group(0, 4);
        } else {
            // Process the same trailing three experts first in both split arms.
            append_group(1, 3);
            if (mode == "Serial") {
                append_group(0, 1);
            } else {
                need(weighted_gold.size() == width || weighted_gold.size() == 4 * width, "e28 oracle shape");
                rows[0] = ggml_new_tensor_2d(c, GGML_TYPE_F32, width, 1);
                free_input = rows[0];
                ggml_set_input(rows[0]);
                // GGML can reuse a parent for ADD. Keep this pre-resident contribution across calls.
                ggml_set_output(rows[0]);
            }
        }
        for (auto *v : rows) {
            ggml_build_forward_expand(graph, v);
            sum = sum ? ggml_add(c, sum, v) : v;
            ggml_build_forward_expand(graph, sum);
        }
        ggml_set_output(sum);
        // Same one-backend scheduler and no observer on any timed graph.
        sched.reset(ggml_backend_sched_new(&cpu, nullptr, 1, 256, false, false));
        need(sched && ggml_backend_sched_alloc_graph(sched.get(), graph), "split CPU scheduler");
        put(x, in.x);
        put(logical, in.ids);
        put(physical_ids, physical);
        put(mix, in.weights);
        if (mode == "Free") {
            ggml_backend_tensor_set(rows[0], weighted_gold.data(), 0, width * sizeof(float));
        }
    }

    void execute() {
        need(ggml_backend_sched_graph_compute(sched.get(), graph) == GGML_STATUS_SUCCESS,
             "split graph compute");
        ggml_backend_sched_synchronize(sched.get());
    }

    // Read only from the controller, outside the measured execution interval.
    json input_sha256() const {
        auto hash = [](const auto &v) {
            return digest(v.data(), v.size() * sizeof(v[0]));
        };
        json seals = {{"x", hash(get<float>(x))}, {"logical", hash(get<int>(logical))},
                      {"physical", hash(get<int>(physical_ids))}, {"mix", hash(get<float>(mix))}};
        if (free_input) seals["free_e28"] = hash(get<float>(free_input));
        return seals;
    }

    std::array<F,4> contributions() {
        return {get<float>(rows[0]), get<float>(rows[1]), get<float>(rows[2]), get<float>(rows[3])};
    }

    F output() { return get<float>(sum); }
};
