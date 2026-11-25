#pragma once
// Validated at the syscall boundary and again at each executed GGML node.
struct Audit {
    llama_moe_stream * manager = nullptr;
    llama_moe_stream_layer * layer = nullptr;
    std::array<ggml_tensor *,3> weights{}; // native model registration order: gate, down, up
    std::array<ggml_backend_buffer_t,3> buffers{};
    std::array<uint8_t *,3> addresses{};
    std::array<int,128> reads{}, copies{};
    std::array<uintptr_t,128> destinations{};
    uint64_t pread_bytes = 0;
    std::array<int,128> slots{};
    std::array<uint64_t,128> generations{};
    std::map<ggml_tensor *, std::pair<int,int>> mmids;
    std::map<ggml_tensor *,int> wave_ids, masks;
    std::array<int32_t, 128> logical{};
    std::array<std::array<int32_t,128>,8> physical{};
    std::array<int,8> seen_ids{}, seen_masks{};
    std::array<std::array<int,3>,8> seen_mm{};
    ggml_backend_sched_t sched = nullptr;
    ggml_backend_t cpu = nullptr;
    int fd = -1;
    size_t slot_stride = 0;
    bool direct = false;
    std::atomic<bool> invalid{false};
};
static Audit * audit = nullptr;
static thread_local int serving = -1;
static thread_local uint8_t * read_base = nullptr;
template<class T> static bool same_operand(T actual, T expected, const void * data, const void * expected_data,
                                          const void * buffer, const void * expected_buffer, size_t pitch, size_t expected_pitch) {
    return actual==expected && data==expected_data && buffer==expected_buffer && pitch==expected_pitch;
}
static bool complete(const Audit &a) {
    for(int w=0;w<8;++w) {
        if(a.seen_ids[w]!=1 || a.seen_masks[w]!=1) return false;
        for(int k=0;k<3;++k) if(a.seen_mm[w][k]!=1) return false;
    }
    return true;
}
extern "C" ssize_t __real_pread(int,void *,size_t,off_t);
extern "C" void __real_ggml_backend_tensor_set(ggml_tensor *,const void *,size_t,size_t);
extern "C" ssize_t __wrap_pread(int fd, void * dst, size_t bytes, off_t off) {
    Audit *a = audit;
    if (!a || fd!=a->fd) return __real_pread(fd,dst,bytes,off);
    auto & l = *a->layer;
    const size_t disk_index = size_t(off)/stride;
    if (off<0 || size_t(off)%stride || disk_index>=selected.size()) {
        a->invalid=true; errno=EIO; return -1;
    }
    const int e=selected[disk_index];
    serving=e; read_base=static_cast<uint8_t *>(dst);
    {
        std::lock_guard<std::mutex> lock(a->manager->mtx);
        auto it=l.expert_slot.find(e);
        if (it==l.expert_slot.end()) { a->invalid=true; errno=EIO; return -1; }
        const int s=it->second;
        const size_t alignment=a->manager->expert_store->data.offset_alignment();
        const size_t expected=a->slot_stride==slab ? (3*slab+alignment-1)/alignment*alignment : window;
        if (bytes!=expected || a->reads[e]++!=0 || l.slot_state[s]!=LLAMA_MOE_STREAM_SLOT_LOADING ||
            !l.slot_claimed[s] || l.slot_expert[s]!=e || l.slot_gen[s]!=1) a->invalid=true;
        a->pread_bytes+=bytes;
        if (a->direct!=(read_base==a->addresses[0]+size_t(s)*a->slot_stride)) a->invalid=true;
        if (!a->direct) {
            const auto first=uintptr_t(dst),last=first+bytes;
            for(int k=0;k<3;++k) {
                const auto lo=uintptr_t(a->addresses[k]),hi=lo+ggml_nbytes(a->weights[k]);
                if(first<hi && lo<last) a->invalid=true;
            }
        }
        a->destinations[e]=uintptr_t(dst); a->slots[e]=s; a->generations[e]=l.slot_gen[s];
    }
    return __real_pread(fd,dst,bytes,off);
}
extern "C" void __wrap_ggml_backend_tensor_set(ggml_tensor *t,const void *src,size_t off,size_t bytes) {
    Audit *a=audit;
    if(a) for(int k=0;k<3;++k) if(t==a->weights[k]) {
        std::lock_guard<std::mutex> lock(a->manager->mtx);
        if(serving<0 || a->direct || bytes!=slab || off!=size_t(a->slots[serving])*a->slot_stride ||
           src!=read_base+k*slab || a->copies[serving]++!=k) a->invalid=true;
    }
    __real_ggml_backend_tensor_set(t,src,off,bytes);
}
static bool observe(ggml_tensor * t,bool ask,void * opaque) {
    auto &a=*static_cast<Audit *>(opaque);
    auto id=a.wave_ids.find(t),mask=a.masks.find(t); auto mm=a.mmids.find(t);
    if(id==a.wave_ids.end() && mask==a.masks.end() && mm==a.mmids.end()) return false;
    if(ask) return true;
    if(ggml_backend_sched_get_tensor_backend(a.sched,t)!=a.cpu) a.invalid=true;
    if(id!=a.wave_ids.end()) {
        const int w=id->second; auto &p=a.physical[w];
        ggml_backend_tensor_get(t,p.data(),0,sizeof(p));
        std::lock_guard<std::mutex> lock(a.manager->mtx);
        for(size_t i=0;i<p.size();++i) {
            int e=a.logical[i],s=p[i];
            if(w!=0) { if(s!=-1) a.invalid=true; continue; }
            if(s!=a.slots[e] || s<0 || s>=40 || a.layer->slot_state[s]!=LLAMA_MOE_STREAM_SLOT_RESIDENT ||
               a.layer->slot_claimed[s] || a.layer->slot_expert[s]!=e || a.layer->slot_gen[s]!=a.generations[e]) a.invalid=true;
        }
        ++a.seen_ids[w];
    } else if(mask!=a.masks.end()) {
        std::array<float,128> values{}; ggml_backend_tensor_get(t,values.data(),0,sizeof(values));
        const int w=mask->second;
        if(!std::all_of(values.begin(),values.end(),[w](float v){return v==(w==0?1.0f:0.0f);})) a.invalid=true;
        ++a.seen_masks[w];
    } else {
        auto [w,k]=mm->second; auto *src=t->src[0];
        if(!same_operand(src,a.weights[k],src->data,a.addresses[k],src->buffer,a.buffers[k],src->nb[2],a.slot_stride) ||
           ggml_backend_buffer_get_usage(src->buffer)!=GGML_BACKEND_BUFFER_USAGE_WEIGHTS ||
           ggml_backend_buffer_get_type(src->buffer)!=ggml_backend_cpu_buffer_type()) a.invalid=true;
        auto it=a.wave_ids.find(t->src[2]); if(it==a.wave_ids.end() || it->second!=w || a.seen_ids[w]!=1) a.invalid=true;
        if(a.direct && w==0) for(int e:selected)
            if(uintptr_t(a.addresses[k]+size_t(a.slots[e])*a.slot_stride)!=a.destinations[e]+size_t(k)*slab) a.invalid=true;
        ++a.seen_mm[w][k];
    }
    return true;
}
