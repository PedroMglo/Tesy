// The builder extracts these two functions verbatim from the C266 operator.
#include "pairs-finish.inc"

class UnitGraph {
    static constexpr int wave_count = 8;
    static constexpr int capacity = 18;
    static constexpr size_t positions = 32;
    static constexpr size_t lanes = 4 * positions;

    struct Observation {
        llama_moe_stream_wave *native = nullptr;
        std::array<int32_t, lanes> physical{};
        std::array<uint64_t, lanes> generation{};
        std::array<float, lanes> mask{};
        int ids_calls = 0, mask_calls = 0;
        bool owners_valid = true;
        int64_t begin = 0, end = 0;
    };
    struct WaveGold {
        std::vector<int32_t> physical;
        std::vector<uint64_t> generation;
        std::vector<float> mask;
    };

    int layer_;
    llama_moe_stream_layer *stream_;
    ggml_backend_t cpu_;
    ggml_context_ptr ctx_;
    ggml_backend_sched_ptr sched_;
    ggml_cgraph *graph_;
    ggml_tensor *x_, *logical_, *mix_, *out_;
    std::array<Observation, wave_count> waves_{};
    std::array<ggml_tensor *, wave_count> remaps_{};
    bool executed_ = false, gold_loaded_ = false;
    fs::path root_;
    std::vector<int32_t> ids_, gold_ids_;
    std::vector<float> gold_x_, gold_mix_, gold_out_;
    std::array<WaveGold, wave_count> gold_{};

    // Observe the real host op at its return, while the current wave's slots are still
    // kept. The next wave depends on consuming this wave's three GEMMs and mask.
    static void remap(ggml_tensor *dst, int ith, int nth, void *userdata) {
        auto &w = *static_cast<Observation *>(userdata);
        if (ith != 0) return;
        w.begin = now_ns();
        llama_moe_stream_wave_ids(dst, ith, nth, w.native);
        w.end = now_ns();
        ++w.ids_calls;
        std::memcpy(w.physical.data(), dst->data, sizeof(w.physical));
        const auto *logicals = static_cast<const int32_t *>(dst->src[0]->data);
        auto &s = *w.native->sl;
        std::lock_guard<std::mutex> lock(s.mgr->mtx);
        for (size_t i = 0; i < lanes; ++i) {
            int slot = w.physical[i];
            if (slot == -1) continue;
            if (slot < 0 || unsigned(slot) >= s.n_slots) {
                w.owners_valid = false;
                continue;
            }
            const auto it = s.expert_slot.find(logicals[i]);
            w.generation[i] = s.slot_gen[slot];
            if (s.slot_state[slot] != LLAMA_MOE_STREAM_SLOT_RESIDENT ||
                s.slot_claimed[slot] || s.slot_expert[slot] != logicals[i] ||
                it == s.expert_slot.end() || it->second != slot || !w.generation[i]) {
                w.owners_valid = false;
            }
        }
    }

    static void mask(ggml_tensor *dst, int ith, int nth, void *userdata) {
        auto &w = *static_cast<Observation *>(userdata);
        if (ith != 0) return;
        llama_moe_stream_wave_mask(dst, ith, nth, w.native);
        ++w.mask_calls;
        std::memcpy(w.mask.data(), dst->data, sizeof(w.mask));
    }

    template<class A, class B>
    static bool same(const A &a, const B &b) {
        static_assert(sizeof(*a.data()) == sizeof(*b.data()));
        return a.size() == b.size() &&
               std::memcmp(a.data(), b.data(), a.size() * sizeof(*a.data())) == 0;
    }

    template<class A>
    static std::string hash(const A &v) {
        return digest(v.data(), v.size() * sizeof(*v.data()));
    }

public:
    UnitGraph(ggml_backend_t cpu, llama_moe_stream &manager, int layer,
              const std::array<ggml_tensor *, 6> &t) :
        layer_(layer), stream_(manager.layer(layer)), cpu_(cpu), ctx_(context()) {
        need(layer_ >= 0 && layer_ <= 1 && stream_ && stream_->n_slots == 40 &&
             stream_->n_expert == 128 && stream_->matches(t[0], t[1], t[2], nullptr),
             "manager cache/graph identity");
        const char *park = std::getenv("TESY_CPU_WAVE_SKIP_PARKED");
        need(park && std::strcmp(park, "1") == 0, "C47 CPU parking mode");
        auto *c = ctx_.get();
        graph_ = ggml_new_graph_custom(c, 1024, false);
        x_ = ggml_new_tensor_2d(c, GGML_TYPE_F32, width, positions);
        logical_ = ggml_new_tensor_2d(c, GGML_TYPE_I32, 4, positions);
        mix_ = ggml_new_tensor_3d(c, GGML_TYPE_F32, 1, 4, positions);
        for (auto *leaf : {x_, logical_, mix_}) ggml_set_input(leaf);
        ggml_tensor *sum = nullptr;
        for (int wave = 0; wave < wave_count; ++wave) {
            auto &w = waves_[wave];
            w.native = stream_->wave_userdata(wave, capacity);
            ggml_tensor *args[] = {logical_, sum ? ggml_view_1d(c, sum, 1, 0) : nullptr};
            auto *ids = ggml_custom_4d(c, GGML_TYPE_I32, 4, positions, 1, 1, args,
                                       sum ? 2 : 1, remap, 1, &w);
            remaps_[wave] = ids;
            auto *value = pairs(c, t, x_, logical_, ids);
            ggml_tensor *ma[] = {logical_, ids};
            auto *masked = ggml_custom_4d(c, GGML_TYPE_F32, 1, 4, positions, 1, ma, 2, mask, 1, &w);
            value = ggml_mul(c, value, masked);
            sum = sum ? ggml_add(c, sum, value) : value;
            ggml_build_forward_expand(graph_, sum);
        }
        out_ = finish(c, graph_, sum, mix_);
        sched_.reset(ggml_backend_sched_new(&cpu_, nullptr, 1, 1024, false, false));
        need(sched_ && ggml_backend_sched_alloc_graph(sched_.get(), graph_), "CPU FFN allocation");
        std::array<std::array<int, 3>, wave_count> seen{};
        int bias_nodes = 0;
        for (int i = 0; i < ggml_graph_n_nodes(graph_); ++i) {
            auto *node = ggml_graph_node(graph_, i);
            if (node->op == GGML_OP_ADD_ID) {
                need(node->src[2] == logical_ &&
                     std::find(t.begin() + 3, t.end(), node->src[1]) != t.end(), "logical expert bias");
                ++bias_nodes;
            }
            if (node->op != GGML_OP_MUL_MAT_ID) continue;
            auto pos = std::find(remaps_.begin(), remaps_.end(), node->src[2]);
            auto weight = std::find(t.begin(), t.begin() + 3, node->src[0]);
            need(pos != remaps_.end() && weight != t.begin() + 3 &&
                 ggml_backend_sched_get_tensor_backend(sched_.get(), node) == cpu_ &&
                 node->src[0]->buffer && ggml_backend_buffer_is_host(node->src[0]->buffer) &&
                 node->src[0]->type == GGML_TYPE_MXFP4, "consumer operand");
            ++seen[pos-remaps_.begin()][weight-t.begin()];
        }
        for (const auto &counts : seen) need(counts == std::array<int,3>{1,1,1}, "wave MMID coverage");
        need(bias_nodes == 24, "graph bias coverage");
    }

    UnitGraph(const UnitGraph &) = delete;
    UnitGraph &operator=(const UnitGraph &) = delete;

    void load_gold(const fs::path &input) {
        need(!gold_loaded_, "repeated FFN gold load");
        root_ = input;
        const auto prefix = "L" + std::to_string(layer_) + ".";
        gold_x_ = read<float>(input / (prefix + "x.f32"), width * positions);
        gold_out_ = read<float>(input / (prefix + "ffn.f32"), width * positions);
        gold_ids_ = read<int32_t>(input / (prefix + "ids.i32"), lanes);
        gold_mix_ = read<float>(input / (prefix + "mix.f32"), lanes);
        for (int w = 0; w < wave_count; ++w) {
            const auto stem = prefix + "w" + std::to_string(w) + ".";
            gold_[w].physical = read<int32_t>(input / (stem + "ids.i32"), lanes);
            gold_[w].mask = read<float>(input / (stem + "mask.f32"), lanes);
            gold_[w].generation = read<uint64_t>(input / (stem + "gen.u64"), lanes);
        }
        gold_loaded_ = true;
    }

    void execute(const std::vector<float> &x, const std::vector<int32_t> &ids,
                 const std::vector<float> &mix) {
        need(!executed_ && gold_loaded_ && same(x, gold_x_) &&
             same(ids, gold_ids_) && same(mix, gold_mix_), "single use, logical ranks and mixing");
        ids_ = ids;
        put(x_, x);
        put(logical_, ids);
        put(mix_, mix);
        need(ggml_backend_sched_graph_compute(sched_.get(), graph_) == GGML_STATUS_SUCCESS,
             "CPU FFN compute");
        ggml_backend_sched_synchronize(sched_.get());
        executed_ = true;
    }

    json check(const fs::path &input) const {
        need(executed_ && gold_loaded_ && input == root_, "FFN boundary");
        const auto result = values<float>(out_);
        need(same(result, gold_out_) &&
             std::all_of(result.begin(), result.end(), [](float f) { return std::isfinite(f); }),
             "bitwise finite FFN gold");
        json records = json::array();
        std::array<int, lanes> visits{};
        int active_waves = 0;
        for (int j = 0; j < wave_count; ++j) {
            const auto &w = waves_[j];
            const auto &expected = gold_[j];
            need(w.ids_calls == 1 && w.mask_calls == 1 && w.owners_valid && w.end >= w.begin &&
                 (j == 0 || waves_[j-1].end <= w.begin), "wave execution and current owner");
            need(same(w.mask, expected.mask), "bitwise native wave mask");
            int active = 0, different_parking = 0;
            for (size_t i = 0; i < lanes; ++i) {
                if (w.mask[i] == 1.f) {
                    need(w.physical[i] >= 0 && w.physical[i] == expected.physical[i] &&
                         w.generation[i] == expected.generation[i] && w.generation[i] > 0,
                         "active slot or generation");
                    ++visits[i];
                    ++active;
                } else {
                    need(w.mask[i] == 0.f && w.physical[i] == -1 &&
                         !w.generation[i] && !expected.generation[i], "CPU parked lane");
                    different_parking += (w.physical[i] != expected.physical[i]);
                }
            }
            need(different_parking == 0, "archived parked remap");
            active_waves += (active != 0);
            records.push_back({{"wave", j}, {"active", active}, {"physical_sha256", hash(w.physical)},
                               {"mask_sha256", hash(w.mask)}, {"generation_sha256", hash(w.generation)},
                               {"parking_differences", different_parking}});
        }
        need(active_waves == 4 &&
             std::all_of(visits.begin(), visits.end(), [](int n) { return n == 1; }),
             "one active wave for every routed lane");
        return {{"layer", layer_}, {"ffn_words", result.size()}, {"ffn_sha256", hash(result)},
                {"logical_sha256", hash(ids_)}, {"mix_sha256", hash(gold_mix_)}, {"x_sha256", hash(gold_x_)},
                {"active_waves", active_waves}, {"mmid_nodes", 24}, {"bias_nodes", 24},
                {"waves", records}};
    }

    json remap_intervals() const {
        need(executed_, "FFN has not executed");
        json r = json::array();
        for (const auto &w : waves_) r.push_back({w.begin,w.end});
        return r;
    }
};
