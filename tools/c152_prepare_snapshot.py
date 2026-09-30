"""Apply audited logical-state instrumentation to the pinned C122 descendant of C75."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
B=ROOT/'backends/c152-slots44-snapshot'
def replace(path,old,new,count=1):
    p=B/path;s=p.read_text()
    if s.count(old)!=count:raise RuntimeError(f'non-unique source anchor {path}: {old[:70]}')
    p.write_text(s.replace(old,new))

def main():
    h='src/llama-moe-stream.h';c='src/llama-moe-stream.cpp'
    replace(h,'struct llama_moe_stream;','#include <array>\n#include <atomic>\n\nstruct llama_moe_stream;')
    replace(h,'    uint64_t trace_call_id = 0;\n    std::string trace_trigger;','    uint64_t trace_call_id = 0;\n    std::string trace_trigger;')
    replace(h,'    uint32_t n_slots      = 0; // expert cache slots per streamed layer','    uint32_t n_slots      = 0; // expert cache slots per streamed layer\n    uint64_t snapshot_work_id = 0;')
    replace(h,'    void worker_loop();','    void worker_loop(int32_t worker_id);')
    replace(h,'    static constexpr size_t trace_cap = 300000;', '''    static constexpr size_t trace_cap = 600000;
    std::vector<uint8_t> snapshot_bytes;
    std::vector<int64_t> routed_journal;
    std::array<llama_moe_stream_work,64> owned_work{};
    std::array<std::atomic<uint8_t>,64> owned_phase{};
    int64_t snapshot_request = 0;
    size_t request_event_begin = 0, request_route_begin = 0;
    bool snapshot_overflow = false;
    void journal_request(int64_t request);
    void route_locked(const llama_moe_stream_layer & sl, const int32_t * ids, int64_t n, int32_t mode);
    void snapshot(const char * path, int64_t sequence, int32_t phase, int32_t first_pos, int32_t last_pos);
''')
    replace(h,'    int64_t  enqueue_us = 0;','    int64_t  enqueue_us = 0;\n    uint64_t snapshot_work_id = 0;')
    replace(h,'        int32_t component;','        int32_t component;\n        uint64_t work_id;')
    replace(h,'uint64_t generation = 0, int32_t component = -1);','uint64_t generation = 0, int32_t component = -1, uint64_t work_id = 0);')
    replace(c,'        trace_events.reserve(8192);','''        trace_events.reserve(trace_cap);
        if (std::getenv("TESY_C152_SNAPSHOT_ENABLED")) {
            snapshot_bytes.resize(1024*1024);
            routed_journal.reserve(1024*1024);
            for (auto & phase : owned_phase) phase.store(0);
        }''')
    replace(c,'workers.emplace_back([this]() { worker_loop(); });','workers.emplace_back([this,i]() { worker_loop(i); });')
    replace(c,'void llama_moe_stream::worker_loop() {','void llama_moe_stream::worker_loop(int32_t worker_id) {')
    replace(c,'call_id, now });','call_id, now, ++snapshot_work_id });')
    replace(c,'now, call_id, sl->slot_gen[slot]);','now, call_id, sl->slot_gen[slot], -1, snapshot_work_id);')
    replace(c,'int32_t component) {','int32_t component, uint64_t work_id) {')
    replace(c,'generation, component });','generation, component, work_id });')
    replace(c,'    if (trace_events.size() >= trace_cap) {','''    if (!snapshot_bytes.empty() &&
        (trace_events.size()-request_event_begin)*sizeof(trace_event) +
        (routed_journal.size()-request_route_begin)*sizeof(int64_t) >= 32*1024*1024) {
        trace_overflow = snapshot_overflow = true; return;
    }
    if (trace_events.size() >= trace_cap) {''')
    replace(c,'            continue; // stale or duplicate item','''#ifdef TESY_C84_EXPERT_TRACE
            trace_locked("STALE_WORK", sl.il, w.expert, w.slot, -1, 0, -1, -1, 0,
                         -1, w.trace_call_id, w.gen, -1, w.snapshot_work_id);
#endif
            continue; // stale or duplicate item''')
    replace(c,'        sl.slot_claimed[w.slot] = 1;','''        sl.slot_claimed[w.slot] = 1;
#ifdef TESY_C84_EXPERT_TRACE
        if (!snapshot_bytes.empty()) { owned_work[worker_id] = w; owned_phase[worker_id].store(1); }
#endif''')
    replace(c,'0, ggml_time_us(), w.trace_call_id, w.gen);','0, ggml_time_us(), w.trace_call_id, w.gen, -1, w.snapshot_work_id);')
    replace(c,'        lk.lock();\n\n#ifdef TESY_C84_EXPERT_TRACE','''#ifdef TESY_C84_EXPERT_TRACE
        if (!snapshot_bytes.empty()) owned_phase[worker_id].store(2,std::memory_order_release);
#endif
        lk.lock();

#ifdef TESY_C84_EXPERT_TRACE''')
    replace(c,'        cv_done.notify_all();','''#ifdef TESY_C84_EXPERT_TRACE
        trace_locked(ok ? "RESIDENT_COMMIT" : "COMMIT_ERROR", sl.il, w.expert,
                     w.slot, -1, 0, -1, sl.slot_state[w.slot], 0,
                     ggml_time_us(), w.trace_call_id, w.gen, -1, w.snapshot_work_id);
        if (!snapshot_bytes.empty()) { owned_phase[worker_id].store(0); owned_work[worker_id] = {}; }
#endif
        cv_done.notify_all();''')
    replace(c,'    mgr->stats.n_calls++;','''    #ifdef TESY_C84_EXPERT_TRACE
    mgr->route_locked(*sl, ids, n, 0);
    #endif
    mgr->stats.n_calls++;''')
    replace(c,'    stats.n_calls++;\n    start_workers_locked();','''    #ifdef TESY_C84_EXPERT_TRACE
    route_locked(sl, ids, n, 1);
    #endif
    stats.n_calls++;
    start_workers_locked();''')
    replace(c,'w.trace_call_id, w.gen, -1, w.snapshot_work_id);','w.trace_call_id, w.gen, worker_id, w.snapshot_work_id);',count=3)
    replace(c,'        out[i] = s;\n    }\n}\n\n// stable per-wave', '        out[i] = s;\n    }\n#ifdef TESY_C84_EXPERT_TRACE\n    mgr->trace_locked("REMAP_DONE", sl->il, -1, -1, -1, a->ne[1]);\n#endif\n}\n\n// stable per-wave')
    replace(c,'    mgr->emit_wave_slots(*sl, ids, out, w, n_ids, a->ne[1]);','    mgr->emit_wave_slots(*sl, ids, out, w, n_ids, a->ne[1]);\n#ifdef TESY_C84_EXPERT_TRACE\n    mgr->trace_locked("WAVE_DONE", sl->il, -1, -1, -1, a->ne[1], w);\n#endif')
    replace(c,'    trace_locked("RESERVE", sl.il, expert, slot);','    trace_locked("RESERVE", sl.il, expert, slot, -1, 0, -1, sl.slot_state[slot], 0, -1, 0, sl.slot_gen[slot]);')
    replace(c,'        mgr->trace_locked("WAIT_BEGIN", sl->il, -1, -1, -1, a->ne[1], -1,','        for (int32_t slot : sl->demand_slots) mgr->trace_locked("BARRIER_SLOT", sl->il,\n            sl->slot_expert[slot],slot,-1,a->ne[1],-1,sl->slot_state[slot],0,-1,0,sl->slot_gen[slot]);\n        mgr->trace_locked("WAIT_BEGIN", sl->il, -1, -1, -1, a->ne[1], -1,')
    replace(c,'        trace_locked("WAIT_BEGIN", sl.il, -1, -1, -1, n_tokens, w, -1, 0, t0);','        for (int32_t slot : sl.demand_slots) trace_locked("BARRIER_SLOT", sl.il,\n            sl.slot_expert[slot],slot,-1,n_tokens,w,sl.slot_state[slot],0,-1,0,sl.slot_gen[slot]);\n        trace_locked("WAIT_BEGIN", sl.il, -1, -1, -1, n_tokens, w, -1, 0, t0);')
    # Schema changes only the new backend's output, never historical trace files.
    replace(c,'#c122-expert-decode-v1','#c152-expert-snapshot-v1')
    replace(c,'generation\\tcomponent\\n','generation\\tcomponent\\twork_id\\n')
    replace(c,'\\t%d\\n",\n                         e.kind','\\t%d\\t%" PRIu64 "\\n",\n                         e.kind')
    replace(c,'e.call_id, e.generation, e.component);','e.call_id, e.generation, e.component, e.work_id);')
    replace(c,'        trace_file = nullptr;','''        trace_file = nullptr;
        if (!snapshot_bytes.empty()) {
            if (const char * route_path = std::getenv("TESY_C152_ROUTE_FILE")) {
                FILE * out = std::fopen(route_path,"wx");
                if (!out || std::fwrite(routed_journal.data(),sizeof(int64_t),routed_journal.size(),out) != routed_journal.size() || std::fclose(out)) {
                    LLAMA_LOG_ERROR("C152 route journal write failed\\n");
                }
            }
        }''')
    with (B/c).open('a') as f:f.write('\n#ifdef TESY_C84_EXPERT_TRACE\n#include "c152-snapshot.inl"\n#endif\n')
    (B/'src/c152-snapshot.inl').write_bytes((ROOT/'tools/c152_snapshot.inl').read_bytes())

if __name__=='__main__':main()
