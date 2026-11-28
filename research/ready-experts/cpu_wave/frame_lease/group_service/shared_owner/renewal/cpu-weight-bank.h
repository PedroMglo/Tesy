// The manager mutex serializes ownership changes. Published weights may have multiple readers.
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <utility>

class CpuWeightBank {
public:
    static constexpr int layers = 25, slots = 40, capacity = 252;
    static constexpr int primary = layers * slots, count = primary + capacity;
    enum class Mode { disk, copy, reference };
    struct Transfer {
        int source = -1, target = -1;
        int logical = -1;
        uint64_t admission = 0;
        bool write = true;
        bool from_pack() const { return source < 0; }
        bool out_of_place() const { return write && source >= 0 && source != target; }
    };
    struct Loan {
        uint64_t ticket = 0, epoch = 0;
        int frame = -1;
        bool operator==(const Loan &) const = default;
    };
    struct Counters {
        uint64_t reservations = 0, hits = 0, captures = 0, copies = 0, staged_hits = 0;
        uint64_t loans = 0, releases = 0;
    } stats;
    explicit CpuWeightBank(Mode mode) : mode_(mode) {
        for (int i = 0; i < capacity; ++i) secondary_[i].frame = primary + i;
    }
    static int key(int layer, int expert) {
        require(layer >= 0 && layer < layers && expert >= 0 && expert < 128, "bank expert key");
        return 128 * layer + expert;
    }
    void initial_resident(int frame,int expert_key) {
        require(!stats.reservations && frame >= 0 && frame < primary && frames_[frame].key < 0 &&
                expert_key >= 0 && expert_key < layers*128, "invalid initial CPU snapshot");
        frames_[frame].key = expert_key;
        frames_[frame].epoch = 1;
    }

    Transfer reserve(int layer, int slot, int expert, int old, int &physical) {
        const int k = key(layer, expert);
        require(slot >= 0 && slot < slots && physical >= 0 && physical < count, "bank slot");
        const int logical = layer * slots + slot;
        require(!pending_[logical].admission, "overlapping primary admissions");
        const int victim = old < 0 ? -1 : key(layer, old);
        require(victim < 0 || (victim != k && frames_[physical].key == victim), "unpublished victim");
        ++stats.reservations;
        ++frequency_[k];
        int source = -1, dest = -1, free = -1, low = -1;
        if (mode_ != Mode::disk) {
            for (int i = 0; i < capacity; ++i) {
                const auto &s = secondary_[i];
                if (s.key == k) source = i;
                if (s.key == -1 && free < 0) free = i;
                if (s.key >= 0 && (low < 0 || s.rank < secondary_[low].rank)) low = i;
            }
            if (source >= 0) {
                require(frames_[secondary_[source].frame].key == k, "wrong bank generation");
                secondary_[source].key = -1;
                if (free < 0 || source < free) free = source;
                ++stats.hits;
            }
            if (victim >= 0) {
                const auto rank = std::make_pair(frequency_[victim], stats.reservations);
                if (free >= 0) dest = free;
                else if (low >= 0 && secondary_[low].rank < rank) dest = low;
                if (dest >= 0) {
                    secondary_[dest].rank = rank;
                    secondary_[dest].key = victim;
                    ++stats.captures;
                }
            }
        }

        if (source >= 0) {
            std::swap(physical, secondary_[source].frame);
            if (dest >= 0 && dest != source) std::swap(secondary_[source].frame,secondary_[dest].frame);
        } else if (dest >= 0) {
            std::swap(physical, secondary_[dest].frame);
        }

        Transfer t;
        if (source >= 0) {
            t.source = physical;
            t.write = mode_ == Mode::copy;
            if (t.write) {
                ++stats.copies;
                // Borrow the physical location of a logically empty bank entry, then return the
                // source there. Another writer cannot recycle it until this copy is complete.
                auto spare = std::find_if(secondary_.begin(),secondary_.end(),[&](const Entry &e) {
                    return e.key == -1 && idle(e.frame);
                });
                if (spare != secondary_.end()) {
                    ++frames_[t.source].source_holds;
                    std::swap(physical,spare->frame);
                } else {
                    ++stats.staged_hits;
                }
            }
        }
        t.target = physical;
        t.logical = logical;
        t.admission = stats.reservations;
        pending_[logical] = t;
        return t;
    }
    Transfer transfer(int layer, int slot) const { return pending_.at(layer*slots+slot); }
    bool eligible(const Transfer &t) const { return !t.write || idle(t.target); }
    void cancel_queued(const Transfer &t) {
        if (!t.admission) return;
        require(pending_.at(t.logical).admission == t.admission, "stale cancellation");
        if (t.out_of_place()) {
            auto &f = frames_.at(t.source);
            require(f.source_holds, "missing cancelled source");
            --f.source_holds;
        }
        pending_[t.logical] = {};
    }
    void complete(const Transfer &t, int expected_key, bool success) {
        require(t.admission && pending_.at(t.logical).admission == t.admission, "stale completion");
        if (t.out_of_place()) {
            auto &s = frames_.at(t.source);
            require(s.source_holds && s.key == expected_key, "source released or overwritten");
            --s.source_holds;
        }
        auto &f = frames_.at(t.target);
        if (t.write) {
            require(idle(t.target), "writing during a physical lease");
            f.key = success ? expected_key : -1;
            ++f.epoch;
        } else if (success) {
            require(f.key == expected_key, "promoted the wrong physical content");
        }
        pending_[t.logical] = {};
    }
    Loan acquire(int frame, int expected_key) {
        auto &f = frames_.at(frame);
        require(f.epoch && f.key == expected_key, "acquire unknown content");
        require(next_ticket_ != std::numeric_limits<uint64_t>::max(), "lease ticket overflow");
        Loan loan{++next_ticket_, f.epoch, frame};
        loans_.emplace(loan.ticket,loan);
        ++f.readers;
        ++stats.loans;
        return loan;
    }
    bool release(Loan loan) {
        auto it = loans_.find(loan.ticket);
        if (it == loans_.end() || !(it->second == loan)) return false;
        auto &f = frames_.at(loan.frame);
        require(f.epoch == loan.epoch && f.readers, "stale physical epoch");
        loans_.erase(it);
        --f.readers;
        ++stats.releases;
        return true;
    }
    bool drained() const {
        return loans_.empty() && std::none_of(pending_.begin(),pending_.end(),
            [](const Transfer &t){ return t.admission != 0; }) &&
            std::all_of(frames_.begin(),frames_.end(),[](const Frame &f) {
            return !f.readers && !f.source_holds;
        });
    }
    int occupied() const {
        return std::count_if(secondary_.begin(),secondary_.end(),[](const Entry &e){return e.key>=0;});
    }
private:
    struct Entry { int frame=-1, key=-1; std::pair<uint64_t,uint64_t> rank{}; };
    struct Frame { int key=-1; uint64_t epoch=0; unsigned readers=0, source_holds=0; };
    static void require(bool v,const char *reason) { if (!v) throw std::logic_error(reason); }
    bool idle(int frame) const {
        const auto &f = frames_.at(frame);
        return !f.readers && !f.source_holds;
    }
    Mode mode_;
    uint64_t next_ticket_ = 0;
    std::array<Entry,capacity> secondary_{};
    std::array<Frame,count> frames_{};
    std::array<Transfer,primary> pending_{};
    std::array<uint64_t,layers*128> frequency_{};
    std::unordered_map<uint64_t,Loan> loans_;
};
