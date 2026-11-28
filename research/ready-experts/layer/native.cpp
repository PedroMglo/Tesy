// Reuse the authenticated C269 router, MXFP4 FFN builder, loader and typed tensor helpers.
#define main historical_decode_entry
#include "decode.cpp"
#undef main
#include <condition_variable>
#include <thread>

namespace {
using Clock = std::chrono::steady_clock;
uint64_t tick() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
}
struct Aligned {
    uint8_t *ptr = nullptr;
    explicit Aligned(size_t bytes) {
        void *p = nullptr;
        need(posix_memalign(&p, 4096, bytes) == 0, "aligned staging");
        ptr = static_cast<uint8_t *>(p);
    }
    ~Aligned() { std::free(ptr); }
};

struct Service {
    int fd;
    const json &records;
    const std::array<ggml_tensor *,6> &tensors;
    Aligned staging{stride};
    std::mutex mutex;
    std::condition_variable work, published;
    bool stop = false, pending = false;
    int submitted = 0, completed = 0, awake = 0, owner = -1;
    std::exception_ptr failure;
    std::array<std::thread,4> workers;
    uint64_t start = 0, read_done = 0, set_start = 0, done = 0;

    Service(int f, const json &rs, const std::array<ggml_tensor *,6> &ts)
        : fd(f), records(rs), tensors(ts) {
        for (int i=0; i<4; ++i) workers[i] = std::thread([this,i]{ loop(i); });
        std::unique_lock lock(mutex);
        published.wait(lock, [this]{ return awake == 4; });
    }
    ~Service() {
        { std::lock_guard lock(mutex); stop = true; }
        work.notify_all();
        for (auto &w : workers) w.join();
    }
    void read_record(int rank, size_t bytes) {
        auto offset = records.at(rank).at("record_offset").get<off_t>();
        need(pread(fd, staging.ptr, bytes, offset) == ssize_t(bytes), "short direct read");
    }
    void set_weights(int rank) {
        for (int k=0; k<3; ++k) {
            auto *t = tensors[to_math[k]];
            need(t->nb[2] == slab, "native slot stride");
            ggml_backend_tensor_set(t, staging.ptr + k*slab, size_t(dest[rank])*slab, slab);
        }
    }
    void prepare() {
        for (int rank=0; rank<4; ++rank) {
            read_record(rank, stride);
            const auto &rec = records.at(rank);
            need(rec.at("rank")==rank && rec.at("expert")==keys[rank] &&
                 rec.at("capture_slot")==dest[rank] && rec.at("capture_generation")==gens[rank],
                 "captured generation");
            for (int k=0; k<6; ++k) {
                const auto &part = rec.at("components").at(k);
                const auto at = part.at("packed_relative_offset").get<size_t>();
                const auto size = part.at("size_bytes").get<size_t>();
                need(at <= stride && size <= stride-at && size == (k<3 ? slab : 4*width) &&
                     (k>=3 || at == k*slab) && digest(staging.ptr+at,size)==part.at("sha256"),
                     "original component fingerprint");
                if (k>=3) ggml_backend_tensor_set(tensors[3+to_math[k-3]], staging.ptr+at,
                                                   size_t(keys[rank])*size, size);
            }
            if (rank != 1) set_weights(rank);
        }
    }
    void loop(int i) {
        std::unique_lock lock(mutex);
        ++awake;
        published.notify_one();
        for (;;) {
            work.wait(lock, [this]{ return stop || pending; });
            if (stop) return;
            pending = false;
            const int request = submitted;
            lock.unlock();
            try {
                start = tick();
                read_record(1, window);
                read_done = tick();
                set_start = tick();
                set_weights(1);
                done = tick();
            } catch (...) {
                lock.lock();
                failure = std::current_exception();
                published.notify_one();
                return;
            }
            lock.lock();
            completed = request;
            owner = i;
            published.notify_one();
        }
    }
    void submit() {
        {
            std::lock_guard lock(mutex);
            need(!pending && submitted == completed && !failure, "previous generation drained");
            pending = true;
            ++submitted;
        }
        work.notify_one();
    }
    void wait() {
        std::unique_lock lock(mutex);
        published.wait(lock, [this]{ return completed == submitted || failure; });
        if (failure) std::rethrow_exception(failure);
    }
};

using Weighted = std::array<std::array<float,width>,4>;
using Result = std::array<float,width>;
struct Group {
    ggml_context_ptr ctx = context();
    ggml_backend_sched_ptr scheduler;
    ggml_cgraph *graph;
    ggml_tensor *output;
    std::vector<int> ranks;
    Group(ggml_backend_t cpu, const std::array<ggml_tensor *,6> &ts, const Input &in,
          std::vector<int> logical_ranks) : ranks(std::move(logical_ranks)) {
        auto *c = ctx.get();
        graph = ggml_new_graph_custom(c, 256, false);
        auto *x = ggml_new_tensor_2d(c, GGML_TYPE_F32, width, 1);
        auto *ids = ggml_new_tensor_2d(c, GGML_TYPE_I32, ranks.size(), 1);
        auto *slots = ggml_dup_tensor(c, ids);
        auto *mix = ggml_new_tensor_3d(c, GGML_TYPE_F32, 1, ranks.size(), 1);
        for (auto *leaf : {x, ids, slots, mix}) { ggml_set_input(leaf); ggml_set_output(leaf); }
        output = ggml_mul(c, pairs(c, ts, x, ids, slots), mix);
        ggml_set_output(output);
        ggml_build_forward_expand(graph, output);
        scheduler.reset(ggml_backend_sched_new(&cpu, nullptr, 1, 256, false, false));
        need(scheduler && ggml_backend_sched_alloc_graph(scheduler.get(),graph), "group allocation");
        I logical, physical;
        F weights;
        for (auto r : ranks) {
            logical.push_back(in.ids.at(r)); physical.push_back(dest.at(r));
            weights.push_back(in.weights.at(r));
        }
        put(x,in.x); put(ids,logical); put(slots,physical); put(mix,weights);
    }
    void execute(Weighted &rows) {
        need(ggml_backend_sched_graph_compute(scheduler.get(),graph)==GGML_STATUS_SUCCESS, "FFN");
        ggml_backend_sched_synchronize(scheduler.get());
        for (size_t i=0; i<ranks.size(); ++i)
            ggml_backend_tensor_get(output, rows.at(ranks[i]).data(), i*width*4, width*4);
    }
};

Result reduce(const Weighted &w) {
    Result result;
    for (int i=0; i<width; ++i) result[i] = ((w[0][i]+w[1][i])+w[2][i])+w[3][i];
    return result;
}

json measure(const fs::path &prefill, const fs::path &ref, const fs::path &pack, const fs::path &weighted_file) {
    json plan; std::ifstream(ref/"plan.json") >> plan;
    need(plan.at("position")==189 && plan.at("layer")==0 && plan.at("rows")==1, "reference row");
    ggml_backend_ptr cpu(ggml_backend_cpu_init());
    need(bool(cpu),"CPU provider");
    ggml_backend_cpu_set_n_threads(cpu.get(),8);
    auto in = route(prefill,ref,cpu.get());
    equal(read<int>(ref/"ffn_moe_topk_stream.bin",4), I(dest.begin(),dest.end()));
    const auto gold = read<float>(ref/"ffn_moe_out.bin",width);
    const auto weighted = read<float>(weighted_file,4*width);
    for (const auto *v : {&gold,&weighted})
        need(std::all_of(v->begin(),v->end(),[](float f){return std::isfinite(f);}),"finite gold");
    need(digest(gold.data(),width*4)=="6bc70d200ac08db00f6c3fa34098bd660d2ba4bc4c02368de319cbadf6167333" &&
         digest(weighted.data(),4*width*4)=="d80c7ba29c304d76099cf7dd28cfe58f365f919cc494ea247507614097c44a4b",
         "independent anchors");
    auto meta=context();
    std::array<ggml_tensor *,6> ts;
    for (int i=0;i<3;++i) {
        ts[i]=ggml_new_tensor_3d(meta.get(),GGML_TYPE_MXFP4,width,width,40);
        ts[3+i]=ggml_new_tensor_2d(meta.get(),GGML_TYPE_F32,width,128);
    }
    ggml_backend_buffer_ptr storage(ggml_backend_alloc_ctx_tensors(meta.get(),cpu.get()));
    need(bool(storage),"40 primary slots");
    Group full(cpu.get(),ts,in,{0,1,2,3}), warm(cpu.get(),ts,in,{0,2,3}), cold(cpu.get(),ts,in,{1});
    const int fd = open(pack.c_str(),O_RDONLY|O_DIRECT|O_CLOEXEC);
    need(fd >= 0 && (fcntl(fd,F_GETFL)&O_DIRECT) && fstat_id(fd)==plan.at("pack_stat"),"NVMe inode");
    json out = {{"trials",json::array()},{"parity",json::array()},{"workers",4},{"cpu_threads",8},
                {"request_bytes",window},{"set_bytes",3*slab},{"setup_bytes",4*stride},
                {"storage_bytes",ggml_backend_buffer_get_size(storage.get())},{"order",in.ids}};
    {
        Service service(fd,plan.at("records"),ts);
        service.prepare();
        auto run = [&](const std::string &mode, bool parity) {
            // Invalidate and poison the previous cold destination outside the request. A stale
            // use must change the gold. All arms restore it from the same READ and three SETs.
            for(int i=0;i<3;++i) std::memset(static_cast<uint8_t *>(ts[i]->data)+dest[1]*slab,0,slab);
            Weighted rows;
            const auto start=tick();
            service.submit();
            if (mode!="READY") service.wait();
            const auto begin_graph=tick();
            if (mode=="FULL") full.execute(rows); else warm.execute(rows);
            const auto end_graph=tick();
            if (mode=="READY") service.wait();
            if (mode!="FULL") cold.execute(rows);
            const auto result=reduce(rows);
            const auto end=tick();
            need(std::memcmp(rows.data(),weighted.data(),sizeof(rows))==0 &&
                 std::memcmp(result.data(),gold.data(),sizeof(result))==0,"independent ranks or FFN differ");
            if (parity && mode=="READY") {
                std::swap(rows[0],rows[2]);
                const auto wrong=reduce(rows);
                int different=0;
                for(int i=0;i<width;++i) different+=std::memcmp(&wrong[i],&gold[i],4)!=0;
                need(different>0 && std::memcmp(rows.data(),weighted.data(),sizeof(rows))!=0,"negative control");
                out["mutant_unequal_ffn"]=different;
            }
            return json{{"mode",mode},{"start",start},{"end",end},{"read_start",service.start},
                        {"read_end",service.read_done},{"set_start",service.set_start},{"set_end",service.done},
                        {"group_start",begin_graph},{"group_end",end_graph},{"worker",service.owner},
                        {"generation",service.completed},{"checked_weighted",4*width},{"checked_ffn",width}};
        };
        const std::array<std::string,3> modes{"FULL","WAIT","READY"};
        for (auto &mode:modes) out["parity"].push_back(run(mode,true));
        for(int block=0;block<2;++block)
            for(int rep=0;rep<7;++rep)
                for(int j=0;j<3;++j) {
                    auto row=run(modes[block ? 2-j : j],false);
                    row.update(json{{"block",block},{"rep",rep}});
                    out["trials"].push_back(std::move(row));
                }
        need(service.completed==45 && service.submitted==45,"drain and generation count");
    }
    need(fstat_id(fd)==plan.at("pack_stat") && close(fd)==0,"pack or close");
    out["workers_joined"]=4;
    return out;
}
}

int main(int argc,char **argv) {
    try {
        const char *weighted = std::getenv("TESY_READY_WEIGHTED");
        need(argc==6 && std::string(argv[4])=="LAYER" && weighted,"sealed supervisor inputs");
        std::cout<<measure(argv[1],argv[2],argv[3],weighted).dump()<<'\n';
        return 0;
    } catch(const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
