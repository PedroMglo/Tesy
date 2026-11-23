// Accepted evidence starts at the natural warm boundary. Prefix bytes are
// temporary pre-publication log data. This changes no logical cache/worker state.
static void reset_warmup_journal(llama_moe_stream * mgr) {
    std::lock_guard<std::mutex> lock(mgr->mtx);
    if(mgr->trace_overflow||mgr->snapshot_overflow)throw std::runtime_error("prefix logger overflow");
    mgr->trace_events.clear();mgr->routed_journal.clear();
    mgr->request_starts={{1,0}};
    mgr->request_event_begin=mgr->request_route_begin=0;
}
