// One routed FFN over the three live C291 tensors. No copied expert table.
constexpr int hidden = 2880;
ggml_backend_ptr gpu, cpu;
fs::path destination;
json operators = json::object();
bool b_published = false;

enum class Order { gold, view, event, broken };

struct Probe {
    Order order;
    bool got_view = false;
    float scalar = 0.0f;
};

void signal_dependency() {
    std::lock_guard<std::mutex> lock(r.gate);
    check(!r.reader_done, "duplicate consumer dependency");
    r.reader_done = true;
    r.cv.notify_all();
}

void activation_gate(ggml_tensor *dst, const ggml_tensor *src, int ith, int, void *arg) {
    if (ith)
        return;
    auto &probe = *static_cast<Probe *>(arg);
    if (probe.order == Order::broken) {
        std::unique_lock<std::mutex> lock(r.gate);
        check(r.cv.wait_for(lock, 15s, [] { return b_published; }),
              "B must overwrite before broken FFN");
    }
    std::memcpy(dst->data, src->data, ggml_nbytes(src));
}

void observe_view(ggml_tensor *dst, int ith, int, void *arg) {
    if (ith)
        return;
    auto &probe = *static_cast<Probe *>(arg);
    if (dst->src[1]) {
        check(dst->src[1]->type == GGML_TYPE_F32 && ggml_nbytes(dst->src[1]) == 4, "scalar edge");
        std::memcpy(&probe.scalar, dst->src[1]->data, sizeof(float));
        check(std::isfinite(probe.scalar), "non-finite order witness");
        probe.got_view = true;
    }
    std::memcpy(dst->data, dst->src[0]->data, ggml_nbytes(dst->src[0]));
    if (probe.order == Order::view || probe.order == Order::broken)
        signal_dependency();
}

Ranks last_wave_values(const json &wave, const char *field) {
    const auto values = wave.at(field).get<Eight>();
    Ranks result;
    std::copy(values.begin() + 4, values.end(), result.begin());
    return result;
}

void run_ffn(const char *label, const Ranks &slots, const Ranks &active, Order order) {
    ggml_context_ptr meta(ggml_init({2u << 20, nullptr, true}));
    auto *c = meta.get();
    check(c, "FFN metadata");
    Probe probe{order};
    auto *ids = ggml_new_tensor_2d(c, GGML_TYPE_I32, 4, 1);
    auto *x = ggml_new_tensor_3d(c, GGML_TYPE_F32, hidden, 1, 1);
    auto *mask = ggml_new_tensor_3d(c, GGML_TYPE_F32, 1, 4, 1);
    auto *input = ggml_map_custom1(c, x, activation_gate, 1, &probe);
    auto &w = r.layer->weights;
    auto *up = ggml_mul_mat_id(c, w[2].cache, input, ids);
    auto *gate = ggml_mul_mat_id(c, w[0].cache, input, ids);
    auto *act = ggml_swiglu_oai(c, gate, up, 1.702f, 7.0f);
    auto *down = ggml_mul_mat_id(c, w[1].cache, act, ids);
    auto *pairs = ggml_mul(c, down, mask);
    auto *sum = ggml_view_1d(c, pairs, hidden, 0);
    for (int k = 1; k < 4; ++k)
        sum = ggml_add(c, sum, ggml_view_1d(c, pairs, hidden, size_t(k) * pairs->nb[1]));
    auto *view = ggml_view_1d(c, pairs, 1, 0);
    ggml_tensor *args[] = {ids, view};
    auto *observer = ggml_custom_4d(c, GGML_TYPE_I32, 4, 1, 1, 1, args,
                                    order == Order::view ? 2 : 1, observe_view, 1, &probe);
    auto *g = ggml_new_graph_custom(c, 64, false);
    if (order != Order::gold)
        ggml_build_forward_expand(g, observer);
    ggml_build_forward_expand(g, sum);
    ggml_set_input(x);
    ggml_set_input(ids);
    ggml_set_input(mask);
    ggml_set_output(sum);
    ggml_backend_t devices[] = {gpu.get(), cpu.get()};
    ggml_backend_sched_ptr sched(ggml_backend_sched_new(devices, nullptr, 2, 256, false, false));
    check(bool(sched), "scheduler");
    ggml_backend_sched_set_tensor_backend(sched.get(), x, cpu.get());
    ggml_backend_sched_set_tensor_backend(sched.get(), ids, cpu.get());
    ggml_backend_sched_set_tensor_backend(sched.get(), mask, gpu.get());
    int mmid = 0;
    for (int i = 0; i < ggml_graph_n_nodes(g); ++i) {
        auto *n = ggml_graph_node(g, i);
        mmid += n->op == GGML_OP_MUL_MAT_ID;
        auto *target = n == input || n == observer ? cpu.get() : gpu.get();
        check(ggml_backend_supports_op(target, n), "FFN operation placement");
        ggml_backend_sched_set_tensor_backend(sched.get(), n, target);
    }
    check(mmid == 3 && ggml_backend_sched_alloc_graph(sched.get(), g), "allocate three MMID");
    for (auto *n : {up, gate, act, down, pairs, sum}) {
        check(ggml_backend_sched_get_tensor_backend(sched.get(), n) == gpu.get() && n->buffer &&
                  !ggml_backend_buffer_is_host(n->buffer),
              "real CUDA FFN node");
    }
    for (const auto &wt : w)
        check(wt.cache->buffer &&
                  std::string(ggml_backend_buffer_name(wt.cache->buffer)) == "CUDA0" &&
                  ggml_backend_buffer_get_usage(wt.cache->buffer) ==
                      GGML_BACKEND_BUFFER_USAGE_WEIGHTS,
              "manager CUDA0 weight buffer");
    check(up->src[0] == w[2].cache && gate->src[0] == w[0].cache && down->src[0] == w[1].cache,
          "live manager operand");
    check(order == Order::gold ||
              ggml_backend_sched_get_tensor_backend(sched.get(), observer) == cpu.get(),
          "observer on CPU");
    std::array<float, hidden> values;
    for (int i = 0; i < hidden; ++i)
        values[i] = float((i * 13) % 31 - 15) / 1024.0f;
    std::array<float, 4> masks;
    for (int i = 0; i < 4; ++i)
        masks[i] = float(active[i]);
    ggml_backend_tensor_set(x, values.data(), 0, sizeof(values));
    ggml_backend_tensor_set(ids, slots.data(), 0, sizeof(slots));
    ggml_backend_tensor_set(mask, masks.data(), 0, sizeof(masks));
    ggml_backend_event_ptr done(order == Order::event
                                    ? ggml_backend_event_new(ggml_backend_get_device(gpu.get()))
                                    : nullptr);
    check(order != Order::event || bool(done), "CUDA event");
    check(ggml_backend_sched_graph_compute_async(sched.get(), g) == GGML_STATUS_SUCCESS,
          "CUDA FFN submit");
    if (order == Order::event) {
        ggml_backend_event_record(done.get(), gpu.get());
        ggml_backend_event_synchronize(done.get());
        signal_dependency();
    }
    ggml_backend_sched_synchronize(sched.get());
    check(probe.got_view == (order == Order::view), "actual scalar dependency");
    ggml_backend_tensor_get(sum, values.data(), 0, sizeof(values));
    check(std::all_of(values.begin(), values.end(), [](float x) { return std::isfinite(x); }),
          "finite FFN");
    std::ofstream out(destination / (std::string(label) + ".f32"), std::ios::binary);
    out.write(reinterpret_cast<const char *>(values.data()), sizeof(values));
    out.flush();
    check(bool(out), "FFN output");
    operators[label] = {{"floats", hidden},
                        {"sha256", hash(values.data(), sizeof(values))},
                        {"ids", slots},
                        {"mask", active},
                        {"mmid", mmid},
                        {"original_operands", 3},
                        {"device", "CUDA0"},
                        {"view", probe.got_view},
                        {"event", order == Order::event}};
}
