// Logical copy under the existing state mutex. File writes occur after unlocking.
// Integers use native little endian, explicitly declared and rejected on other hosts.
void llama_moe_stream::journal_request(int64_t request) {
    std::lock_guard<std::mutex> lock(mtx);
    if (snapshot_bytes.empty()) return;
    if (request <= snapshot_request) throw std::runtime_error("C152 request order");
    snapshot_request = request; snapshot_count=0;
    request_starts.emplace_back(request,trace_events.size());
    request_event_begin = trace_events.size(); request_route_begin = routed_journal.size();
}

void llama_moe_stream::route_locked(const llama_moe_stream_layer & sl,
                                   const int32_t * ids, int64_t n, int32_t mode) {
    if (snapshot_bytes.empty()) return;
    const size_t after = routed_journal.size() + 8 + n;
    if (n < 1 || n > 4*32 || after*sizeof(int64_t) > 8*1024*1024 ||
        (trace_events.size()-request_event_begin)*sizeof(trace_event) +
        (after-request_route_begin)*sizeof(int64_t) > 32*1024*1024) {
        snapshot_overflow = trace_overflow = true; return;
    }
    const int64_t header[]={snapshot_request,int64_t(trace_call_id),sl.il,mode,
                            stats.n_calls+1,n,ggml_time_us(),int64_t(trace_events.size())};
    routed_journal.insert(routed_journal.end(),std::begin(header),std::end(header));
    for (int64_t i=0;i<n;++i) routed_journal.push_back(ids[i]);
}

void llama_moe_stream::snapshot(const char * path,int64_t sequence,int32_t phase,
                               int32_t first_pos,int32_t last_pos) {
    if (snapshot_bytes.empty()) throw std::runtime_error("C152 snapshot not enabled");
    size_t used=0;
    {
        std::lock_guard<std::mutex> lock(mtx);
        if(snapshot_count++>=3){snapshot_overflow=true;throw std::runtime_error("C156 snapshot count overflow");}
        auto bytes=[&](const void * p,size_t n) {
            if (used+n>snapshot_bytes.size()) { snapshot_overflow=true; throw std::runtime_error("C152 snapshot overflow"); }
            std::memcpy(snapshot_bytes.data()+used,p,n);used+=n;
        };
        auto put=[&](int64_t x){bytes(&x,sizeof(x));};
        auto vector=[&](const auto & v){put(v.size());for (const auto x:v)put(x);};
        const char magic[8]={'T','E','S','Y','S','1','5','2'}; bytes(magic,8);
        const uint32_t endian=0x01020304;bytes(&endian,4);put(1);
        for (const char * name : {"TESY_C152_MODEL_HASH","TESY_C152_SOURCE_HASH",
                                 "TESY_C152_BUILD_HASH","TESY_C152_PROFILE_HASH"}) {
            const char * hash=std::getenv(name);
            if (!hash || std::strlen(hash)!=64) throw std::runtime_error("C152 identity hash required");
            for (int i=0;i<64;++i)if (!std::isxdigit(static_cast<unsigned char>(hash[i]))) throw std::runtime_error("C152 nonhex hash");
            bytes(hash,64);
        }
        put(snapshot_request);put(sequence);put(trace_call_id);put(phase);
        put(first_pos);put(last_pos);put(trace_events.size());put(ggml_time_us());
        put(stats.n_calls);put(hot_decay_interval);put(n_io_threads);put(load_failed);put(shutting_down);
        put(snapshot_work_id);put(trace_overflow||snapshot_overflow);put(layers.size());
        for (const auto & owner:layers) {
            put(bool(owner));if (!owner)continue;const auto & sl=*owner;
            put(sl.il);put(sl.n_expert);put(sl.n_slots);put(sl.use_counter);
            put(sl.plan_capacity);put(sl.plan_n_waves);put(sl.plan_next_wave);
            put(sl.weights.size());
            for (const auto & wt:sl.weights) {
                put(wt.file_idx);put(wt.offs);put(wt.nb_expert);put(wt.cache->type);
                for (auto x:wt.cache->ne)put(x);for (auto x:wt.cache->nb)put(x);
                const char * device=wt.cache->buffer?ggml_backend_buffer_name(wt.cache->buffer):"UNALLOCATED";
                char name[64]{};if(std::strlen(device)>=64)throw std::runtime_error("C152 device name");
                std::memcpy(name,device,std::strlen(device));bytes(name,64);
            }
            vector(sl.slot_expert);vector(sl.slot_state);vector(sl.slot_claimed);
            vector(sl.slot_gen);vector(sl.slot_last_use);vector(sl.route_hotness);vector(sl.seen);
            put(sl.n_expert);for(uint32_t e=0;e<sl.n_expert;++e){auto it=sl.expert_slot.find(e);put(it==sl.expert_slot.end()?-1:it->second);}
            vector(sl.uniq);vector(sl.touched);vector(sl.keep);vector(sl.demand_slots);
            vector(sl.expert_wave);vector(sl.plan_pool);vector(sl.pool_used);
        }
        auto work=[&](const llama_moe_stream_work & w) {
            put(w.sl?w.sl->il:-1);put(w.expert);put(w.slot);put(w.gen);
            put(w.trace_call_id);put(w.enqueue_us);put(w.snapshot_work_id);
        };
        put(q_demand.size());for(const auto & w:q_demand)work(w);
        put(n_io_threads);for(int i=0;i<n_io_threads;++i) {
            put(i);put(owned_phase[i].load(std::memory_order_acquire));work(owned_work[i]);
        }
    }
    FILE * out=c156_open_output(path);
    if(!out)throw std::runtime_error("C152 new snapshot output required");
    const bool failed=std::fwrite(snapshot_bytes.data(),1,used,out)!=used || std::ferror(out);
    if(!c156_finish_output(out,path,!failed&&!snapshot_overflow&&!trace_overflow&&!load_failed))
        throw std::runtime_error("C156 snapshot write/publication failed");
}
