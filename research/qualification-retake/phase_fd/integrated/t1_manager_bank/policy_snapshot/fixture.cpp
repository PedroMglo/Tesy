// Exercise the unchanged C269 victim selector. Only integer metadata and CPU tensor headers exist.
#include "phase-fd-integrated.h"

#include <iostream>
#include <string>

using Mode = std::string;

void require(bool value, const char *why) {
    if (!value) throw std::runtime_error(why);
}

int main(int argc, char **argv) {
    try {
        require(argc == 3, "usage: fixture MODE NEW_FILE");
        const Mode mode = argv[1];
        const int fd = ::open(argv[2], O_CREAT | O_EXCL | O_RDONLY | O_DIRECT | O_CLOEXEC, 0600);
        require(fd >= 0, "new empty synthetic direct FD");
        std::unique_ptr<FILE, decltype(&fclose)> file(fdopen(fd, "rb"), fclose);
        require(bool(file), "synthetic FD");
        std::array<ggml_tensor, 36 * 3> tensors{};
        llama_moe_stream m(36, 40, 4, true);
        m.files.emplace_back(new llama_file(file.get()));
        m.hot_decay_interval = 2304;
        m.stats.n_calls = 2303;
        const char *roles[] = {"gate", "down", "up"};
        for (int i = 0; i < 36; ++i) {
            auto &ptr = m.layers[i] = std::make_unique<llama_moe_stream_layer>();
            auto &sl = *ptr;
            sl.mgr = &m;
            sl.il = i;
            sl.n_expert = 128;
            sl.n_slots = 40;
            sl.use_counter = 40;
            sl.route_hotness.assign(128, 20);
            sl.route_hotness[0] = 0;
            sl.route_hotness[1] = 5;
            sl.route_hotness[2] = 7;
            sl.slot_state.assign(40, LLAMA_MOE_STREAM_SLOT_RESIDENT);
            sl.slot_claimed.assign(40, 0);
            sl.slot_gen.assign(40, 1);
            sl.keep.assign(40, 0);
            for (int s = 0; s < 40; ++s) {
                sl.slot_expert.push_back(s);
                sl.expert_slot[s] = s;
                sl.slot_last_use.push_back(s + 1);
            }
            for (int k = 0; k < 3; ++k) {
                auto &t = tensors[3 * i + k];
                ggml_format_name(&t, "blk.%d.ffn_%s_exps.weight.stream_cache", i, roles[k]);
                sl.weights.push_back({&t, 0, static_cast<size_t>(k) * 4096, 32});
            }
        }
        auto &sl = *m.layer(0);
        if (mode == "heat-b") sl.route_hotness[1] = 9;
        if (mode == "age-a" || mode == "age-b") sl.route_hotness[1] = 7;
        if (mode == "age-b") std::swap(sl.slot_last_use[1], sl.slot_last_use[2]);
        if (mode == "pending") {
            sl.slot_state[1] = sl.slot_state[2] = LLAMA_MOE_STREAM_SLOT_LOADING;
            sl.slot_claimed[2] = 1;
            for (int i = 0; i < 2; ++i) m.q_demand.push_back({&sl, 1, 1, sl.slot_gen[1]});
        }
        const int n = mode == "missing" ? 1 : 5;
        pfj::enter(&m, n, 2044, 2044 + n - 1);
        int r0, backed;
        {
            std::lock_guard<std::mutex> lock(m.mtx);
            r0 = m.pick_victim_locked(sl, sl.keep.data());
            // Among the two recoverable residents use exactly the native ranking and exclusions.
            std::array<uint8_t, 40> keep;
            keep.fill(1);
            keep[1] = keep[2] = 0;
            backed = m.pick_victim_locked(sl, keep.data());
            if (backed < 0) backed = r0;
        }
        pfj::returned(&m, 0);
        if (mode == "duplicate") {
            pfj::enter(&m, 5, 2044, 2048);
            pfj::returned(&m, 0);
        }
        if (mode == "pending") {
            // Injected descriptors never own real reads. Release after RETURN for the destructor.
            std::lock_guard<std::mutex> lock(m.mtx);
            m.q_demand.clear();
            sl.slot_claimed[2] = 0;
            sl.slot_state[1] = sl.slot_state[2] = LLAMA_MOE_STREAM_SLOT_RESIDENT;
        }
        std::cout << "{\"r0\":" << r0 << ",\"backed\":" << backed << "}\n";
        return 0;
    } catch (const std::exception &err) {
        std::cerr << err.what() << '\n';
        return 1;
    }
}
