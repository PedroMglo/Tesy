#pragma once

#include <algorithm>
#include <cstdint>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <tuple>
#include <utility>
#include <vector>

namespace retained {
using Key = std::pair<int, int>;
using Data = std::vector<uint8_t>;
using Lease = std::shared_ptr<const Data>;

struct Entry {
    uint64_t last;
    Lease bytes;
};

// All mutations and lookups belong to the manager mutex. A claim owns its immutable lease.
struct Selector {
    explicit Selector(size_t limit, bool use_counts) : capacity(limit), frequency(use_counts) {
        if (!capacity) throw std::invalid_argument("zero capacity");
    }
    const size_t capacity;
    const bool frequency;
    std::map<Key, uint64_t> counts;
    std::map<Key, Entry> held;
    std::set<Key> offered;
    uint64_t offers = 0, repeated = 0, rejected = 0, evictions = 0, copies[2] = {};

    void ranks(int layer, const int32_t *ids, size_t n) {
        if (n % 4 || layer < 0 || layer >= 36) throw std::invalid_argument("rank shape");
        for (size_t i = 0; i < n; ++i) {
            if (ids[i] < 0 || ids[i] >= 128 ||
                std::find(ids + i - i % 4, ids + i, ids[i]) != ids + i)
                throw std::invalid_argument("rank IDs");
            if (frequency) ++counts[{layer, ids[i]}];
        }
    }
    auto priority(const Key &key, uint64_t last) const {
        auto it = counts.find(key);
        return std::make_tuple(it == counts.end() ? uint64_t{0} : it->second, last, key);
    }
    template<class Capture> void offer(Key key, Capture capture) {
        ++offers;
        offered.insert(key);
        auto existing = held.find(key);
        if (existing != held.end()) {
            existing->second.last = offers;
            ++repeated;
            return;
        }
        if (held.size() == capacity) {
            auto worst = std::min_element(held.begin(), held.end(), [&](const auto &a, const auto &b) {
                return priority(a.first, a.second.last) < priority(b.first, b.second.last);
            });
            if (priority(key, offers) < priority(worst->first, worst->second.last)) {
                ++rejected;
                return;
            }
            held.erase(worst);
            ++evictions;
        }
        held.emplace(key, Entry{offers, capture()});
        ++copies[key.first >= 25];
    }
    Lease lookup(Key key) const {
        auto it = held.find(key);
        return it == held.end() ? nullptr : it->second.bytes;
    }
    std::vector<Key> ordered() const {
        std::vector<std::pair<uint64_t, Key>> ages;
        for (const auto &e : held) ages.emplace_back(e.second.last, e.first);
        std::sort(ages.begin(), ages.end());
        std::vector<Key> keys;
        for (const auto &p : ages) keys.push_back(p.second);
        return keys;
    }
};
} // namespace retained
