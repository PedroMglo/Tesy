#include "tesy_static_residency.h"

#include <array>
#include <cstdio>
#include <cstring>
#include <stdexcept>

namespace {

void require(bool value, const char * message) {
    if (!value) throw std::runtime_error(message);
}

template <typename F>
void rejects(F fn, const char * message) {
    try {
        fn();
    } catch (const std::invalid_argument &) {
        return;
    }
    throw std::runtime_error(message);
}

} // namespace

int main() {
    try {
        const std::vector<int32_t> selected{1, 7, 3, 9};
        const std::vector<float> weights{0.125f, 0.375f, 0.25f, 0.25f};
        for (int h = 0; h <= 4; ++h) {
            std::vector<int32_t> resident(selected.begin(), selected.begin() + h);
            const auto p = tesy_partition_route(selected, weights, resident, 32);
            require(p.gpu_global_ids.size() == static_cast<size_t>(h) &&
                    p.cpu_global_ids.size() == static_cast<size_t>(4 - h),
                    "h0..4 count mismatch");
            for (int i = 0; i < h; ++i) {
                require(p.gpu_global_ids[i] == selected[i] &&
                        p.gpu_local_ids[i] == i &&
                        std::memcmp(&p.gpu_weights[i], &weights[i], sizeof(float)) == 0,
                        "GPU order, local mapping or weight changed");
            }
            for (int i = h; i < 4; ++i) {
                require(p.cpu_global_ids[i - h] == selected[i] &&
                        std::memcmp(&p.cpu_weights[i - h], &weights[i], sizeof(float)) == 0,
                        "CPU order or weight changed");
            }
        }
        const auto changed = tesy_partition_route(
            {9, 1, 11, 7}, weights, {7, 9}, 32);
        require(changed.gpu_global_ids == std::vector<int32_t>({9, 7}) &&
                changed.gpu_local_ids == std::vector<int32_t>({1, 0}) &&
                changed.cpu_global_ids == std::vector<int32_t>({1, 11}),
                "route change reused stale slot mapping");
        rejects([&] { tesy_partition_route({1, 1, 3, 4}, weights, {1}, 32); },
                "duplicate selected expert accepted");
        rejects([&] { tesy_partition_route(selected, weights, {7, 7}, 32); },
                "duplicate resident expert accepted");
        rejects([&] { tesy_partition_route(selected, weights, {33}, 32); },
                "out-of-range resident expert accepted");
        std::puts("STATIC_RESIDENCY_H0_H4_ROUTE_CHANGE_PASS");
        return 0;
    } catch (const std::exception & error) {
        std::fprintf(stderr, "STATIC_RESIDENCY_MODEL_FREE_FAIL: %s\n", error.what());
        return 1;
    }
}
