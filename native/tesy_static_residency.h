#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <unordered_set>
#include <vector>

struct tesy_route_partition {
    std::vector<int32_t> gpu_global_ids;
    std::vector<int32_t> gpu_local_ids;
    std::vector<float> gpu_weights;
    std::vector<int32_t> cpu_global_ids;
    std::vector<float> cpu_weights;
};

inline tesy_route_partition tesy_partition_route(
        const std::vector<int32_t> & selected,
        const std::vector<float> & weights,
        const std::vector<int32_t> & gpu_resident,
        int32_t expert_count) {
    if (selected.empty() || selected.size() != weights.size() ||
        expert_count <= 0) {
        throw std::invalid_argument("route shape invalid");
    }
    std::unordered_set<int32_t> seen_resident;
    for (int32_t expert : gpu_resident) {
        if (expert < 0 || expert >= expert_count ||
            !seen_resident.insert(expert).second) {
            throw std::invalid_argument("GPU resident identity invalid");
        }
    }
    std::unordered_set<int32_t> seen_selected;
    tesy_route_partition result;
    for (size_t slot = 0; slot < selected.size(); ++slot) {
        const int32_t expert = selected[slot];
        const float weight = weights[slot];
        if (expert < 0 || expert >= expert_count ||
            !seen_selected.insert(expert).second ||
            !std::isfinite(weight) || weight < 0.0f) {
            throw std::invalid_argument("selected route identity/weight invalid");
        }
        const auto found = std::find(gpu_resident.begin(), gpu_resident.end(), expert);
        if (found == gpu_resident.end()) {
            result.cpu_global_ids.push_back(expert);
            result.cpu_weights.push_back(weight);
        } else {
            result.gpu_global_ids.push_back(expert);
            result.gpu_local_ids.push_back(
                static_cast<int32_t>(found - gpu_resident.begin()));
            result.gpu_weights.push_back(weight);
        }
    }
    return result;
}
