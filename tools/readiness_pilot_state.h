#pragma once
// Isolated request pin/witness. Original C75 worker and collective wait remain untouched.
#include "llama-moe-stream.h"
#include <array>
#include <atomic>
#include <chrono>
#include <stdexcept>

struct readiness_request {
    llama_moe_stream_layer * layer=nullptr;
    std::array<int32_t,4> experts{}, slots{};
    std::array<uint64_t,4> generations{};
    std::array<std::atomic<bool>,4> published{};
    std::atomic<uint64_t> checks{0},slow_checks{0};
    std::atomic<bool> cancelled{false};
    bool identity_locked(int index) const {
        auto & l=*layer;const int slot=slots[index];
        return slot>=0 && static_cast<unsigned>(slot)<l.n_slots && l.keep[slot] &&
            l.slot_expert[slot]==experts[index] && generations[index]>0 && l.slot_gen[slot]==generations[index];
    }
    bool wait(int slot) {
        ++checks;
        int k=-1;for(int i=0;i<4;i++)if(slots[i]==slot)k=i;
        if(k<0 || cancelled.load(std::memory_order_acquire))return false;
        // Immutable request identity + keep pin establish lifetime. Published payload follows
        // mutex-protected native commit and release-store; consumers acquire it before reading.
        if(published[k].load(std::memory_order_acquire))return true;
        ++slow_checks;
        auto & mgr=*layer->mgr;std::unique_lock<std::mutex> lock(mgr.mtx);
        if(!identity_locked(k))return false;
        mgr.cv_done.wait(lock,[&]{return cancelled.load(std::memory_order_acquire)||mgr.shutting_down||mgr.load_failed||
            !identity_locked(k)||layer->slot_state[slot]==LLAMA_MOE_STREAM_SLOT_RESIDENT;});
        if(cancelled.load(std::memory_order_acquire)||mgr.shutting_down||mgr.load_failed||!identity_locked(k)||
           layer->slot_state[slot]!=LLAMA_MOE_STREAM_SLOT_RESIDENT)return false;
        published[k].store(true,std::memory_order_release);return true;
    }
};
