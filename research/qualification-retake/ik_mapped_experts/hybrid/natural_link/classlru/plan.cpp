// One actual share-zero policy state from the first site of T1 through the last site of T2.
#include "llama-moe-cache-policy.h"
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

namespace policy = llama_moe_cache_policy_detail;
static void require(bool condition, const char *error) {
    if (!condition) throw std::runtime_error(error);
}
int main(int argc, char **argv) try {
    require(argc == 3, "expected policy and real slot count");
    const std::string name(argv[1]);
    require(name == "lru" || name == "classlru", "unknown planner");
    const bool classes = name == "classlru";
    const int cap = std::stoi(argv[2]);
    require(cap == 128 || cap == 161, "unexpected real slot count");
    policy::state cache;
    cache.init(36, 128, cap, classes ? policy::kind::classlru : policy::kind::lru);
    std::vector<std::vector<int32_t>> map(36, std::vector<int32_t>(128, -1));
    for (int il = 0; il < 36; ++il) cache.slot_map[il] = map[il].data();
    int sites;
    require(bool(std::cin >> sites) && sites > 0, "site count");
    for (int i = 0; i < sites; ++i) {
        int il, width;
        require(bool(std::cin >> il >> width) && il >= 0 && il < 36 &&
                policy::slot_map_eligible(width, 4, 128, cap, 32), "site geometry");
        std::vector<int32_t> ids(4*width);
        std::set<int32_t> demand;
        for (int row = 0; row < width; ++row) {
            std::set<int32_t> unique;
            for (int k = 0; k < 4; ++k) {
                auto &id = ids[4*row + k];
                require(bool(std::cin >> id) && id >= 0 && id < 128 && unique.insert(id).second, "top four");
                demand.insert(id);
            }
        }
        const size_t before = cache.filled_real_slots;
        std::set<int32_t> absent;
        for (int e : demand) if (map[il][e] < 0) absent.insert(e);
        std::vector<policy::state::fill> fills;
        size_t hits, evictions;
        const int64_t clock = classes ? cache.clock[il] : 0;
        require(cache.plan(il, ids.data(), ids.size(), classes ? width : 1, fills, hits, evictions),
                "planner refused site");
        require(hits+fills.size() == demand.size() && fills.size() == absent.size() &&
                cache.filled_real_slots+evictions == before+fills.size() &&
                (!classes || cache.clock[il] == clock+width), "conservation/clock");
        for (auto f : fills)
            require(absent.erase(f.expert) == 1 && map[il][f.expert] == f.slot, "filled wrong key");
        for (int e : demand) {
            const int slot = map[il][e];
            require(slot >= 0 && slot < cap && cache.key_of[slot] == il*128+e, "active key invalid");
        }
        size_t resident = 0;
        for (int s = 0; s < cap; ++s) {
            const int key = cache.key_of[s];
            if (key < 0) continue;
            require(key < 36*128 && map[key/128][key%128] == s, "resident inverse");
            ++resident;
        }
        require(resident == cache.filled_real_slots, "wrong occupancy");
        std::cout << hits << ' ' << fills.size() << ' ' << evictions << '\n';
    }
    std::string extra;
    require(!(std::cin >> extra), "extra input");
    return 0;
} catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
}
