#include "expert_store.hpp"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <filesystem>
#include <limits>
#include <stdexcept>
#include <utility>
#include <fcntl.h>
#include <unistd.h>

namespace tesy {
namespace {
void require(bool value, const char * message) {
    if (!value) throw std::runtime_error(message);
}
std::size_t bytes(const ExpertSpec & spec) {
    require(spec.width > 0 && spec.width <= 65536 && spec.hidden > 0 && spec.hidden <= 65536,
            "invalid expert geometry");
    require(spec.width <= std::numeric_limits<std::size_t>::max() / spec.hidden / 12,
            "expert byte overflow");
    return spec.width * spec.hidden * 12;
}
bool same(const struct stat & a, const struct stat & b) {
    return a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_size == b.st_size &&
           a.st_mtim.tv_sec == b.st_mtim.tv_sec && a.st_mtim.tv_nsec == b.st_mtim.tv_nsec &&
           a.st_ctim.tv_sec == b.st_ctim.tv_sec && a.st_ctim.tv_nsec == b.st_ctim.tv_nsec;
}
void finite(const std::vector<float> & v) {
    require(std::all_of(v.begin(), v.end(), [](float x) { return std::isfinite(x); }),
            "non-finite input/weights/output");
}
}

ExpertStore::ExpertStore(const std::string & path, std::vector<ExpertSpec> specs,
                         std::size_t payload_capacity_bytes) : capacity_(payload_capacity_bytes) {
    static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);
    require(capacity_ > 0 && !specs.empty(), "empty cache/specs");
    const auto absolute = std::filesystem::absolute(path).lexically_normal();
    require(std::filesystem::canonical(path) == absolute, "noncanonical expert file");
    fd_ = ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    require(fd_ >= 0, "cannot open expert store");
    try {
        require(::fstat(fd_, &identity_) == 0 && S_ISREG(identity_.st_mode), "not a regular file");
        std::sort(specs.begin(), specs.end(), [](const auto & a, const auto & b) { return a.offset < b.offset; });
        std::uint64_t end = 0;
        for (const auto & spec : specs) {
            const auto count = bytes(spec);
            const auto size = static_cast<std::uint64_t>(identity_.st_size);
            require(spec.offset % 4 == 0 && spec.offset >= end && spec.offset <= size &&
                    count <= size - spec.offset, "invalid/overlapping expert span");
            require(count <= capacity_, "expert exceeds payload cache capacity");
            require(specs_.emplace(spec.id, spec).second, "duplicate expert id");
            end = spec.offset + count;
        }
    } catch (...) { ::close(fd_); fd_ = -1; throw; }
}
ExpertStore::~ExpertStore() { if (fd_ >= 0) ::close(fd_); }

void ExpertStore::check_identity() {
    struct stat current{};
    if (::fstat(fd_, &current) != 0 || !same(current, identity_)) {
        poisoned_ = true;
        throw std::runtime_error("expert store changed; poisoned");
    }
}

Lease ExpertStore::acquire(std::uint64_t id) {
    std::lock_guard<std::mutex> lock(mutex_);
    require(!poisoned_, "store poisoned");
    check_identity();
    const auto spec_it = specs_.find(id);
    require(spec_it != specs_.end(), "unknown expert id");
    const auto spec = spec_it->second;
    auto hit = entries_.find(id);
    if (hit != entries_.end()) {
        hit->second.age = ++clock_;
        ++stats_.hits;
        return {spec, hit->second.weights};
    }
    const auto count = bytes(spec);
    // Plan all evictions before mutating; active leases cannot be evicted.
    std::vector<std::pair<std::uint64_t, std::uint64_t>> victims;
    std::size_t available = capacity_ - stats_.resident_bytes;
    for (const auto & [key, value] : entries_)
        if (value.weights.use_count() == 1) victims.emplace_back(value.age, key);
    std::sort(victims.begin(), victims.end());
    std::size_t needed = 0;
    while (available < count && needed < victims.size()) {
        available += entries_.at(victims[needed].second).weights->size() * sizeof(float);
        ++needed;
    }
    require(available >= count, "capacity blocked by active leases");
    for (std::size_t i = 0; i < needed; ++i) {
        const auto key = victims[i].second;
        stats_.resident_bytes -= entries_.at(key).weights->size() * sizeof(float);
        entries_.erase(key);
        ++stats_.evictions;
    }
    try {
        auto payload = std::make_shared<std::vector<float>>(count / sizeof(float));
        auto * raw = reinterpret_cast<unsigned char *>(payload->data());
        std::size_t done = 0;
        while (done < count) {
            const auto n = ::pread(fd_, raw + done, std::min(count - done, std::size_t{1 << 20}),
                                   static_cast<off_t>(spec.offset + done));
            if (n < 0 && errno == EINTR) continue; // interrupted syscall, not a campaign retry
            require(n > 0, "short/failed expert read");
            done += static_cast<std::size_t>(n);
            stats_.returned_source_bytes += static_cast<std::uint64_t>(n);
        }
        check_identity();
        finite(*payload);
        entries_.emplace(id, Entry{payload, ++clock_});
        stats_.resident_bytes += count;
        stats_.peak_bytes = std::max(stats_.peak_bytes, stats_.resident_bytes);
        ++stats_.loads;
        return {spec, payload};
    } catch (...) { poisoned_ = true; throw; }
}
void ExpertStore::validate() {
    std::lock_guard<std::mutex> lock(mutex_);
    require(!poisoned_, "store poisoned");
    check_identity();
}
StoreStats ExpertStore::stats() const { std::lock_guard<std::mutex> lock(mutex_); return stats_; }
bool ExpertStore::poisoned() const { std::lock_guard<std::mutex> lock(mutex_); return poisoned_; }

void run_expert(ExpertStore & store, std::uint64_t id,
                const std::vector<float> & input, std::vector<float> & output) {
    finite(input);
    const auto lease = store.acquire(id);
    const auto w = lease.spec.width, h = lease.spec.hidden;
    require(input.size() == w, "activation width differs");
    const auto & weights = *lease.weights;
    std::vector<float> intermediate(h), result(w, 0.0F);
    for (std::size_t row = 0; row < h; ++row) {
        float gate = 0.0F, up = 0.0F;
        for (std::size_t col = 0; col < w; ++col) {
            gate += weights[row * w + col] * input[col];
            up += weights[h * w + row * w + col] * input[col];
        }
        require(std::isfinite(gate) && std::isfinite(up), "projection overflow");
        const float e = std::exp(-std::abs(gate));
        const float sigmoid = gate >= 0 ? 1.0F / (1.0F + e) : e / (1.0F + e);
        intermediate[row] = gate * sigmoid * up;
    }
    finite(intermediate);
    for (std::size_t row = 0; row < w; ++row)
        for (std::size_t col = 0; col < h; ++col)
            result[row] += weights[2 * h * w + row * h + col] * intermediate[col];
    finite(result);
    store.validate();
    output.swap(result); // sole caller-visible publication
}
} // namespace tesy
