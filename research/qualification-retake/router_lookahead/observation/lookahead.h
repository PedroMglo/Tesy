// Observation-only extension of the qualified PFJ layout. No slot or queue mutation.
#pragma once
#include "phase-fd-integrated.h"

namespace lookahead {
constexpr auto row = static_cast<pfj::Kind>(31);
constexpr auto start = static_cast<pfj::Kind>(32);
constexpr auto available = static_cast<pfj::Kind>(33);
constexpr auto lookup = static_cast<pfj::Kind>(34);

template<class UBatch> inline void emit_tile(llama_moe_stream &manager, const UBatch &batch, int n_outputs) {
    if (!pfj::active()) return;
    std::lock_guard<std::mutex> lock(manager.mtx);
    const bool all = n_outputs == int(batch.n_tokens);
    if (!batch.pos || (!all && !batch.output) || !batch.n_seq_id || !batch.seq_id) {
        pfj::journal->invalid=true; return;
    }
    int selected = 0;
    for (int i=0; i<int(batch.n_tokens); ++i) {
        if (batch.n_seq_id[i]!=1 || !batch.seq_id[i] || batch.seq_id[i][0]!=batch.seq_id[0][0]) {
            pfj::journal->invalid=true; return;
        }
        bool output = all || batch.output[i] != 0;
        pfj::emit(row, pfj::host, i, batch.pos[i], output);
        selected += int(output);
    }
    if (n_outputs != selected) pfj::journal->invalid=true;
}

inline void begin(llama_moe_stream &manager, int target, size_t source_bytes, size_t coefficient_bytes) {
    if (!pfj::active()) return;
    std::lock_guard<std::mutex> lock(manager.mtx);
    auto site = pfj::host;
    site.layer = target;
    pfj::emit(start, site, target-1, source_bytes, coefficient_bytes);
}

inline void publish(llama_moe_stream &manager, int target, int index, int position, const int *ranks) {
    if (!pfj::active()) return;
    std::lock_guard<std::mutex> lock(manager.mtx);
    uint32_t packed = 0;
    for (int k = 0; k < 4; ++k) packed |= uint32_t(ranks[k]) << (8*k);
    auto site = pfj::host;
    site.layer = target;
    pfj::emit(available, site, packed, index, position);
}

// Both call sites already hold the manager mutex. The iterator's result is
// passed through to avoid invoking the mapping or replacement policy twice.
inline void lookup_locked(const llama_moe_stream_layer &sl, int expert, int slot) {
    if (!pfj::active()) return;
    auto site = pfj::host;
    site.expert = expert;
    site.slot = slot;
    if (slot < 0) {
        pfj::emit(lookup, site, LLAMA_MOE_STREAM_SLOT_EMPTY, 0);
    } else {
        pfj::emit(lookup, pfj::slot_site(site, sl, slot), sl.slot_state[slot], sl.slot_claimed[slot]);
    }
}
} // namespace lookahead
