#pragma once
// DEVELOPMENT_ONLY: immutable compact F32 expert payloads, NOT GGUF integration.
#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
#include <sys/stat.h>

namespace tesy {
struct ExpertSpec {
    std::uint64_t id;
    std::uint64_t offset;
    std::size_t width;
    std::size_t hidden;
};
struct StoreStats {
    std::uint64_t returned_source_bytes = 0;
    std::uint64_t loads = 0;
    std::uint64_t hits = 0;
    std::uint64_t evictions = 0;
    std::size_t resident_bytes = 0;
    std::size_t peak_bytes = 0;
};
struct Lease {
    ExpertSpec spec;
    std::shared_ptr<const std::vector<float>> weights;
};
class ExpertStore final {
public:
    ExpertStore(const std::string & path, std::vector<ExpertSpec> specs,
                std::size_t payload_capacity_bytes);
    ~ExpertStore();
    ExpertStore(const ExpertStore &) = delete;
    ExpertStore & operator=(const ExpertStore &) = delete;
    Lease acquire(std::uint64_t id);
    void validate();
    StoreStats stats() const;
    bool poisoned() const;
private:
    struct Entry {
        std::shared_ptr<const std::vector<float>> weights;
        std::uint64_t age;
    };
    void check_identity();
    int fd_ = -1;
    struct stat identity_{};
    std::unordered_map<std::uint64_t, ExpertSpec> specs_;
    std::unordered_map<std::uint64_t, Entry> entries_;
    std::size_t capacity_;
    std::uint64_t clock_ = 0;
    StoreStats stats_;
    bool poisoned_ = false;
    mutable std::mutex mutex_;
};
// Compact row-major gate[hidden,width], up[hidden,width], down[width,hidden].
// Caller output remains unchanged on invalid input, load or arithmetic failure.
void run_expert(ExpertStore & store, std::uint64_t id,
                const std::vector<float> & input, std::vector<float> & output);
} // namespace tesy
