#include "boundary_i.h"
#include <future>
#include <iostream>
#include <thread>

template<typename Function>
void rejects(Function operation, const std::string &expected) {
    try {
        operation();
    } catch (const std::runtime_error &err) {
        if (err.what() == expected) return;
        throw;
    }
    throw std::runtime_error("boundary fault was accepted");
}

int main() {
    llama_moe_stream manager(36, 40, 4, false);
    for (int layer = 0; layer < 36; ++layer) {
        auto pool = std::make_unique<llama_moe_stream_layer>();
        pool->il = layer;
        for (int i = 0; i < 40; ++i) {
            bool empty = layer == 35 && i < 29;
            pool->slot_expert.push_back(empty ? -1 : i);
            pool->slot_gen.push_back(100 + layer + i);
            pool->slot_state.push_back(empty ? 0 : 2);
            pool->slot_claimed.push_back(0);
        }
        manager.layers[layer] = std::move(pool);
    }
    boundary_i captured;
    captured.capture(manager);
    const auto original = captured.report();
    manager.layers[0]->slot_gen[0]++;
    if (captured.report() != original || original["slot_vector"][0][0] !=
            nlohmann::json::array({0, 100, 2, 0})) {
        throw std::runtime_error("boundary does not own a four-field snapshot");
    }
    boundary_i changed;
    changed.capture(manager);
    if (changed.report()["slot_vector"] == original["slot_vector"]) {
        throw std::runtime_error("lost generation change");
    }
    manager.q_demand.push_back({});
    rejects([&] { changed.capture(manager); }, "WARM40_I_SERVICE_PENDING_OR_FAILED");
    manager.q_demand.clear();
    manager.layers[0]->slot_claimed[0] = 1;
    rejects([&] { changed.capture(manager); }, "WARM40_I_SLOT_IN_FLIGHT");
    manager.layers[0]->slot_claimed[0] = 0;

    std::promise<void> locked, release;
    auto go = release.get_future();
    std::thread owner([&] {
        std::lock_guard<std::mutex> lock(manager.mtx);
        locked.set_value();
        go.wait();
    });
    locked.get_future().wait();
    rejects([&] { changed.capture(manager); }, "WARM40_I_MUTEX_BUSY");
    release.set_value();
    owner.join();
    if (!manager.workers.empty() || !manager.files.empty()) return 1;
    std::cout << original.dump() << "\n";
}
