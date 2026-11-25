#pragma once

#include "llama-moe-stream.h"

#include <algorithm>
#include <array>
#include "json.hpp"
#include <chrono>
#include <cstdint>
#include <mutex>
#include <stdexcept>

// Fixed storage is allocated before the timed workload. Only primitive reads
// occur under the manager mutex. The JSON is constructed after the final drain.
class boundary_i {
    struct slot_record {
        uint64_t generation;
        int32_t expert;
        uint8_t state;
        uint8_t claimed;
    };

    std::array<std::array<slot_record, 40>, 36> slots{};
    uint64_t copy_ns = 0;
    size_t queue_size = 0;
    bool captured = false;

public:
    void capture(llama_moe_stream &manager) {
        using clock = std::chrono::steady_clock;
        const auto start = clock::now();
        {
            std::unique_lock<std::mutex> lock(manager.mtx, std::try_to_lock);
            if (!lock.owns_lock()) {
                throw std::runtime_error("WARM40_I_MUTEX_BUSY");
            }
            queue_size = manager.q_demand.size();
            if (queue_size || manager.load_failed) {
                throw std::runtime_error("WARM40_I_SERVICE_PENDING_OR_FAILED");
            }
            std::array<bool, 36> seen{};
            for (const auto &layer : manager.layers) {
                if (!layer) {
                    continue;
                }
                const int index = layer->il;
                if (index < 0 || index >= 36 || seen[index] ||
                    layer->slot_expert.size() != 40 || layer->slot_gen.size() != 40 ||
                    layer->slot_state.size() != 40 || layer->slot_claimed.size() != 40) {
                    throw std::runtime_error("WARM40_I_UNEXPECTED_POOL");
                }
                seen[index] = true;
                for (size_t i = 0; i < 40; ++i) {
                    const auto state = layer->slot_state[i];
                    const auto claimed = layer->slot_claimed[i];
                    if (claimed || (state != LLAMA_MOE_STREAM_SLOT_EMPTY &&
                                    state != LLAMA_MOE_STREAM_SLOT_RESIDENT)) {
                        throw std::runtime_error("WARM40_I_SLOT_IN_FLIGHT");
                    }
                    slots[index][i] = {layer->slot_gen[i], layer->slot_expert[i], state, claimed};
                }
            }
            if (!std::all_of(seen.begin(), seen.end(), [](bool flag) { return flag; })) {
                throw std::runtime_error("WARM40_I_MISSING_LAYER");
            }
        }
        copy_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(clock::now() - start).count();
        captured = true;
    }

    nlohmann::json report() const {
        if (!captured) {
            throw std::runtime_error("WARM40_I_SNAPSHOT_MISSING");
        }
        auto layers = nlohmann::json::array();
        for (const auto &layer : slots) {
            auto pool = nlohmann::json::array();
            for (const auto &entry : layer) {
                pool.push_back({entry.expert, entry.generation, static_cast<int>(entry.state),
                                static_cast<int>(entry.claimed)});
            }
            layers.push_back(std::move(pool));
        }
        return {{"schema", "routed-cache-boundary-i-v1"}, {"pending_queue", queue_size},
                {"copy_ns", copy_ns}, {"reserved_object_bytes", sizeof(*this)},
                {"slot_vector", std::move(layers)}};
    }
};
