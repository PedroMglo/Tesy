#include "llama-moe-stream.h"

#include <chrono>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <vector>

static void require(bool ok, const char * message) {
    if (!ok) throw std::runtime_error(message);
}

int main() {
    try {
        llama_moe_stream mgr(1,12,1,false);
        mgr.layers[0] = std::make_unique<llama_moe_stream_layer>();
        auto & sl = *mgr.layers[0];
        sl.mgr = &mgr;
        sl.il = 0;
        sl.n_slots = 12;
        sl.n_expert = 128;
        sl.slot_expert.assign(12,-1);
        sl.slot_state.assign(12,LLAMA_MOE_STREAM_SLOT_EMPTY);
        sl.slot_claimed.assign(12,0);
        sl.slot_gen.assign(12,0);
        sl.slot_last_use.assign(12,0);
        sl.route_hotness.assign(128,0);
        sl.seen.assign(128,0);
        // The same pinned worker is used, with no file-backed weights. This targets
        // reservation/generation publication, not byte transfer or GPU completion.
        std::unique_lock<std::mutex> lock(mgr.mtx);
        mgr.reserve_slot_locked(sl,3,0);
        const auto old_generation = sl.slot_gen[0];
        mgr.q_demand.push_back({&sl,3,0,old_generation});
        mgr.reserve_slot_locked(sl,4,0); // deliberate stale queued work
        const auto new_generation = sl.slot_gen[0];
        require(new_generation == old_generation+1,"reservation did not advance generation");
        mgr.reserve_slot_locked(sl,5,1);
        mgr.q_demand.push_back({&sl,5,1,sl.slot_gen[1]}); // completion fence
        mgr.start_workers_locked();
        mgr.cv_work.notify_all();
        const bool sentinel_ready = mgr.cv_done.wait_for(lock,std::chrono::seconds(2),[&] {
            return sl.slot_state[1] == LLAMA_MOE_STREAM_SLOT_RESIDENT;
        });
        require(sentinel_ready,"worker did not process completion fence");
        require(sl.slot_state[0] == LLAMA_MOE_STREAM_SLOT_LOADING &&
                sl.slot_expert[0] == 4 && sl.slot_gen[0] == new_generation &&
                !sl.slot_claimed[0],"stale work published or corrupted a reused slot");
        for (int slot=2; slot<12; ++slot) {
            sl.slot_expert[slot] = slot+4;
            sl.slot_state[slot] = LLAMA_MOE_STREAM_SLOT_RESIDENT;
        }
        const int victim = mgr.pick_victim_locked(sl,nullptr);
        require(victim >= 1 && victim < 12,"LOADING slot selected as eviction victim");
        mgr.q_demand.push_back({&sl,4,0,new_generation});
        mgr.cv_work.notify_all();
        const bool current_ready = mgr.cv_done.wait_for(lock,std::chrono::seconds(2),[&] {
            return sl.slot_state[0] == LLAMA_MOE_STREAM_SLOT_RESIDENT;
        });
        require(current_ready && sl.slot_expert[0] == 4 &&
                sl.slot_gen[0] == new_generation && !mgr.load_failed,
                "current generation failed to publish");
        lock.unlock();
        std::cout << "{\"schema\":\"c3-actual-worker-lifetime-test-v1\","
                  << "\"stale_queued_work_skipped\":true,"
                  << "\"loading_slot_victim_excluded\":true,"
                  << "\"current_generation_published\":true,"
                  << "\"transfer_or_upload_tested\":false,"
                  << "\"old_generation\":" << old_generation << ','
                  << "\"new_generation\":" << new_generation << "}\n";
        return 0;
    } catch (const std::exception & error) {
        std::cerr << "C3_LIFETIME_FAIL: " << error.what() << '\n';
        return 1;
    }
}
