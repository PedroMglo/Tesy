// Exercise the exact share-zero hook's pinned policy. No model, backend or device.
#include "llama-moe-cache-policy.h"
#include <iostream>
#include <stdexcept>

namespace policy = llama_moe_cache_policy_detail;

static void guard(bool ok, const char *what) {
    if (!ok) throw std::runtime_error(what);
}

int main() try {
    int cap, initial, groups;
    guard(bool(std::cin >> cap >> initial >> groups) && cap > 0 && initial >= 0 &&
          initial <= cap && groups > 0, "header");
    policy::state cache;
    cache.init(36, 128, cap, policy::kind::lru);
    std::vector<std::vector<int32_t>> maps(36, std::vector<int32_t>(128, -1));
    for (int i = 0; i < 36; ++i) cache.slot_map[i] = maps[i].data();
    std::vector<policy::state::fill> fills;
    size_t hits = 0, evictions = 0;
    for (int i = 0; i < initial; ++i) {
        int32_t key;
        guard(bool(std::cin >> key) && 0 <= key && key < 36*128, "seed");
        const int32_t expert = key % 128;
        guard(cache.plan(key/128, &expert, 1, 1, fills, hits, evictions) && fills.size() == 1 &&
              hits == 0 && evictions == 0, "duplicate or evicted seed");
    }
    for (int i = 0; i < groups; ++i) {
        int layer, width;
        guard(bool(std::cin >> layer >> width) && 0 <= layer && layer < 36 &&
              policy::slot_map_eligible(width, 4, 128, cap, 32), "geometry");
        std::vector<int32_t> ids(4 * width);
        for (auto &id : ids) guard(bool(std::cin >> id) && 0 <= id && id < 128, "ranks");
        // LRU's hook leaves n_tokens at 1. The contiguous vector still contains all rows.
        guard(cache.plan(layer, ids.data(), ids.size(), 1, fills, hits, evictions), "plan");
        std::cout << hits << ' ' << fills.size() << ' ' << evictions << ' ';
        for (int s = cache.head; s >= 0; s = cache.next[s]) {
            if (cache.key_of[s] >= 0) std::cout << cache.key_of[s] << ' ';
        }
        std::cout << '\n';
    }
    std::string excess;
    guard(!(std::cin >> excess), "extra input");
    return 0;
} catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
}
