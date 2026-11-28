// strong.inc is the pinned full-rank C269 reference, including its loader, router and groups.
#include "strong.inc"

namespace prefix {
using Tensors = std::array<ggml_tensor *, 6>;
using Gold = std::array<F, 8>;
using Provider = ggml_backend_t;
constexpr int narrow = 32;
constexpr size_t page = 4096;
constexpr size_t row_bytes = slab / width;
constexpr size_t align_down(size_t n) { return n / page * page; }
constexpr size_t align_up(size_t n) { return align_down(n + page - 1); }
const std::array<std::string, 6> modes{"FULL", "READY", "L32", "E32", "LALL", "EALL"};
const std::array<std::string, 8> stages{
    "gate", "up", "gate-biased", "up-biased", "swiglu", "down", "down-biased", "weighted"
};

struct Graph {
    ggml_context_ptr ctx = context();
    ggml_cgraph *graph = ggml_new_graph_custom(ctx.get(), 128, false);
    ggml_backend_sched_ptr scheduler;
    ggml_tensor *logical = ggml_new_tensor_2d(ctx.get(), GGML_TYPE_I32, 1, 1);
    ggml_tensor *physical = ggml_dup_tensor(ctx.get(), logical);
    ggml_tensor *x = ggml_new_tensor_3d(ctx.get(), GGML_TYPE_F32, width, 1, 1);
    std::vector<ggml_tensor *> outputs;

    void allocate(Provider cpu) {
        for (auto *leaf : {logical, physical, x}) ggml_set_input(leaf);
        ggml_set_output(x);
        for (auto *t : outputs) ggml_set_output(t);
        ggml_build_forward_expand(graph, outputs.back());
        scheduler.reset(ggml_backend_sched_new(&cpu, nullptr, 1, 128, false, false));
        need(scheduler && ggml_backend_sched_alloc_graph(scheduler.get(), graph), "split graph allocation");
        put(logical, I{keys[1]});
        put(physical, I{dest[1]});
    }
    void execute() {
        need(ggml_backend_sched_graph_compute(scheduler.get(), graph) == GGML_STATUS_SUCCESS, "split FFN");
        ggml_backend_sched_synchronize(scheduler.get());
    }
    void verify(const Gold &gold, int stage, int first, int count) const {
        for (auto *out : outputs) {
            const auto v = get<float>(out);
            if (int(v.size()) != count || std::memcmp(v.data(), gold.at(stage).data() + width + first, count*4))
                throw std::runtime_error("cold stage " + stages.at(stage) + " at row " + std::to_string(first));
            ++stage;
        }
    }
};

// Slice output rows; every dot still consumes all 2880 coordinates in the original order.
struct Activation : Graph {
    int first, count;
    Activation(Provider cpu, const Tensors &ts, const Input &in, int start, int n)
        : first(start), count(n) {
        auto *c = ctx.get();
        for (int k=0; k<2; ++k) {
            auto *t = ts[k];
            auto *view = ggml_view_3d(c, t, width, count, 40, t->nb[1], t->nb[2], first*t->nb[1]);
            outputs.push_back(ggml_mul_mat_id(c, view, x, physical));
        }
        for (int k=0; k<2; ++k) {
            auto *b = ts[k+3];
            auto *view = ggml_view_2d(c, b, count, 128, b->nb[1], size_t(first)*4);
            outputs.push_back(ggml_add_id(c, outputs[k], view, logical));
        }
        outputs.push_back(ggml_swiglu_oai(c, outputs[2], outputs[3], 1.702f, 7.0f));
        allocate(cpu);
        put(x, in.x);
    }
    void install(ggml_tensor *destination) const {
        ggml_backend_tensor_set(destination, outputs.back()->data, size_t(first)*4, size_t(count)*4);
    }
};
struct Down : Graph {
    Down(Provider cpu, const Tensors &ts, const Input &in) {
        auto *c = ctx.get();
        auto *mix = ggml_new_tensor_3d(c, GGML_TYPE_F32, 1, 1, 1);
        ggml_set_input(mix);
        auto *raw = ggml_mul_mat_id(c, ts[2], x, physical);
        auto *biased = ggml_add_id(c, raw, ts[5], logical);
        outputs = {raw, biased, ggml_mul(c, biased, mix)};
        allocate(cpu);
        put(mix, F{in.weights.at(1)});
    }
};

struct Interval { uint64_t a=0, b=0; };
void to_json(json &j, const Interval &i) { j = {i.a, i.b}; }
struct Epoch {
    std::string mode;
    bool narrow_cut() const { return mode == "L32" || mode == "E32"; }
    bool whole_cut() const { return mode == "LALL" || mode == "EALL"; }
    bool split() const { return narrow_cut() || whole_cut(); }
    uint64_t number=0, start=0, partial=0, full=0, end=0;
    Interval warm, activation, suffix, down, reduction;
    std::vector<Interval> reads;
    std::vector<std::array<size_t,2>> extents;
    size_t copied=0, sets=0;
};

class Delivery {
    int fd;
    off_t offset;
    const Tensors &ts;
    Activation &head;
    Aligned staging{window};
    std::mutex m;
    std::condition_variable cv;
    std::array<std::thread,4> workers;
    unsigned awake=0, issued=0, reader_done=0, head_done=0;
    bool stop=false, partial_ok=false, fault=false;
    Epoch *job=nullptr;
    std::exception_ptr failure;

    void read(Epoch &e, size_t a, size_t b) {
        need(b>a && a%page==0 && b%page==0 && b<=window, "direct extent");
        const auto begin = tick();
        need(pread(fd, staging.ptr+a, b-a, offset+a) == ssize_t(b-a), "short direct extent");
        e.reads.push_back({begin, tick()});
        e.extents.push_back({a, b});
    }
    void copy(Epoch &e, int matrix, size_t a, size_t b) {
        auto *t = ts[to_math[matrix]];
        need(a<b && b<=slab && t->nb[2]==slab, "slot extent");
        ggml_backend_tensor_set(t, staging.ptr+matrix*slab+a, size_t(dest[1])*slab+a, b-a);
        e.copied += b-a;
        ++e.sets;
    }
    void deliver(Epoch &e) {
        if (!e.split()) {
            read(e, 0, window);
            for (int k=0; k<3; ++k) copy(e, k, 0, slab);
            return;
        }
        const size_t useful = e.narrow_cut() ? narrow*row_bytes : slab;
        const size_t gate_end=align_up(useful), up_start=align_down(2*slab);
        const size_t up_end=align_up(2*slab+useful);
        read(e, 0, gate_end);
        read(e, up_start, up_end);
        copy(e, 0, 0, useful);
        copy(e, 2, 0, useful);
        {
            std::lock_guard lock(m);
            e.partial=tick();
            partial_ok=true;
        }
        cv.notify_all();
        if (fault) throw std::runtime_error("injected tail failure");
        read(e, gate_end, up_start);
        if (up_end<window) read(e, up_end, window);
        if (useful<slab) {
            copy(e, 0, useful, slab);
            copy(e, 2, useful, slab);
        }
        copy(e, 1, 0, slab);
    }
    void loop(int role) {
        std::unique_lock lock(m);
        ++awake;
        cv.notify_all();
        unsigned previous=0;
        for (;;) {
            cv.wait(lock, [&]{
                if (stop) return true;
                if (!job || issued==previous || failure) return false;
                if (role==0) return true;
                return role==1 && job->narrow_cut() &&
                       (job->mode=="E32" ? partial_ok : reader_done==issued);
            });
            if (stop) return;
            previous=issued;
            auto &e=*job;
            lock.unlock();
            try {
                if (role==0) deliver(e);
                else {
                    e.activation.a=tick();
                    head.execute();
                    e.activation.b=tick();
                }
            } catch (...) {
                lock.lock();
                failure=std::current_exception();
                cv.notify_all();
                return;
            }
            lock.lock();
            if (role==0) { e.full=tick(); reader_done=previous; }
            else head_done=previous;
            cv.notify_all();
        }
    }
    void wait(bool partial, bool include_head) {
        std::unique_lock lock(m);
        cv.wait(lock,[&] {
            return failure || (partial ? partial_ok :
                reader_done==issued && (!include_head || !job->narrow_cut() || head_done==issued));
        });
        if (failure) std::rethrow_exception(failure);
    }
public:
    Delivery(int file, off_t off, const Tensors &t, Activation &h)
        : fd(file), offset(off), ts(t), head(h) {
        for (int i=0; i<4; ++i) workers[i]=std::thread([this,i]{loop(i);});
        std::unique_lock lock(m);
        cv.wait(lock,[&]{return awake==4;});
    }
    ~Delivery() {
        { std::lock_guard lock(m); stop=true; }
        cv.notify_all();
        for (auto &w:workers) w.join();
    }
    void submit(Epoch &e, bool inject=false) {
        std::lock_guard lock(m);
        need(!job && !failure && reader_done==issued, "previous epoch still live");
        e.number=++issued;
        job=&e;
        fault=inject;
        partial_ok=false;
        cv.notify_all();
    }
    void partial() { wait(true,false); }
    void full() { wait(false,false); }
    void drain() {
        wait(false,true);
        std::lock_guard lock(m);
        job=nullptr;
    }
};

json experiment(const fs::path &input, const fs::path &ref, const fs::path &pack, const fs::path &rank) {
    json plan;
    std::ifstream(ref/"plan.json") >> plan;
    need(plan.at("position")==189 && plan.at("layer")==0 && plan.at("rows")==1, "C270 row");
    ggml_backend_ptr cpu(ggml_backend_cpu_init()), helper(ggml_backend_cpu_init());
    need(cpu && helper, "CPU providers");
    ggml_backend_cpu_set_n_threads(cpu.get(),8);
    ggml_backend_cpu_set_n_threads(helper.get(),1);
    const auto in=route(input,ref,cpu.get());
    equal(read<int>(ref/"ffn_moe_topk_stream.bin",4),I(dest.begin(),dest.end()));
    const auto final=read<float>(ref/"ffn_moe_out.bin",width);
    Gold gold;
    for (size_t k=0;k<stages.size();++k) {
        gold[k]=read<float>(rank/(stages[k]+".f32"),4*width);
        need(std::all_of(gold[k].begin(),gold[k].end(),[](float v){return std::isfinite(v);}),"finite stage");
    }
    need(digest(final.data(),width*4)=="6bc70d200ac08db00f6c3fa34098bd660d2ba4bc4c02368de319cbadf6167333" &&
         digest(gold.back().data(),4*width*4)=="d80c7ba29c304d76099cf7dd28cfe58f365f919cc494ea247507614097c44a4b",
         "target anchors");
    auto meta=context();
    Tensors ts;
    for (int i=0;i<3;++i) {
        ts[i]=ggml_new_tensor_3d(meta.get(),GGML_TYPE_MXFP4,width,width,40);
        ts[3+i]=ggml_new_tensor_2d(meta.get(),GGML_TYPE_F32,width,128);
    }
    ggml_backend_buffer_ptr storage(ggml_backend_alloc_ctx_tensors(meta.get(),cpu.get()));
    need(bool(storage),"primary slots");
    Group full(cpu.get(),ts,in,{0,1,2,3}),warm(cpu.get(),ts,in,{0,2,3}),cold(cpu.get(),ts,in,{1});
    Activation head(helper.get(),ts,in,0,narrow),rest(cpu.get(),ts,in,narrow,width-narrow);
    Activation entire(cpu.get(),ts,in,0,width);
    Down down(cpu.get(),ts,in);
    const int fd=open(pack.c_str(),O_RDONLY|O_DIRECT|O_CLOEXEC);
    need(fd>=0 && (fcntl(fd,F_GETFL)&O_DIRECT) && fstat_id(fd)==plan.at("pack_stat"),"pack inode");
    { Service prepare(fd,plan.at("records"),ts); prepare.prepare(); }
    const auto off=plan.at("records").at(1).at("record_offset").get<off_t>();
    json output={{"parity",json::array()},{"trials",json::array()},{"order",in.ids},
                 {"generations",gens},{"slots",dest},{"setup_bytes",4*stride},
                 {"storage_bytes",ggml_backend_buffer_get_size(storage.get())}};
    auto poison=[&] {
        for (int i=0;i<3;++i) std::memset(static_cast<uint8_t *>(ts[i]->data)+dest[1]*slab,0,slab);
        std::memset(down.x->data,0xff,width*4);
    };
    // A consumer can see gate/up but the failed tail can never authorize down. Join before reuse.
    Epoch rejected;
    rejected.mode="E32";
    {
        poison();
        Delivery negative(fd,off,ts,head);
        negative.submit(rejected,true);
        bool caught=false;
        try { negative.drain(); }
        catch (const std::runtime_error &e) { caught=std::string(e.what())=="injected tail failure"; }
        need(caught,"failure did not reach request");
    }
    need(rejected.partial && !rejected.full && rejected.extents.size()==2,"partial failure publication");
    output["injected_tail"]={{"extents",rejected.extents},{"full_published",false},{"down_entered",false}};

    {
        Delivery service(fd,off,ts,head);
        auto run=[&](const std::string &mode, int block, int rep) {
            Epoch e;
            e.mode=mode;
            poison();
            Weighted w;
            e.start=tick();
            service.submit(e);
            if (mode=="FULL") service.full();
            e.warm.a=tick();
            if (mode=="FULL") full.execute(w); else warm.execute(w);
            e.warm.b=tick();
            if (e.whole_cut()) {
                if (mode=="EALL") service.partial(); else service.full();
                e.activation.a=tick();
                entire.execute();
                e.activation.b=tick();
                entire.install(down.x);
            }
            service.drain();
            if (e.narrow_cut()) {
                e.suffix.a=tick();
                head.install(down.x);
                rest.execute();
                rest.install(down.x);
                e.suffix.b=tick();
            }
            if (e.split()) {
                e.down.a=tick();
                down.execute();
                ggml_backend_tensor_get(down.outputs.back(),w[1].data(),0,width*4);
                e.down.b=tick();
            } else if (mode=="READY") {
                e.down.a=tick();
                cold.execute(w);
                e.down.b=tick();
            }
            e.reduction.a=tick();
            const auto result=reduce(w);
            e.reduction.b=tick();
            e.end=tick();
            if (std::memcmp(w.data(),gold.back().data(),sizeof(w)) ||
                std::memcmp(result.data(),final.data(),sizeof(result))) throw std::runtime_error("ranks/FFN differed in "+mode);
            if (e.split()) {
                if (e.narrow_cut()) { head.verify(gold,0,0,narrow); rest.verify(gold,0,narrow,width-narrow); }
                else entire.verify(gold,0,0,width);
                down.verify(gold,5,0,width);
                need(!std::memcmp(down.x->data,gold[4].data()+width,width*4),"down consumed wrong activation");
            }
            if (block==-1 && mode=="FULL") {
                std::swap(w[0],w[2]);
                const auto mutant=reduce(w);
                int wrong=0;
                for (int k=0;k<width;++k) wrong+=bool(std::memcmp(&mutant[k],&final[k],4));
                need(wrong>0,"order mutant survived");
                output["mutant_unequal_ffn"]=wrong;
            }
            return json{{"mode",mode},{"block",block},{"rep",rep},{"epoch",e.number},{"start",e.start},
                        {"end",e.end},{"reads",e.reads},{"extents",e.extents},{"partial",e.partial},
                        {"full",e.full},{"resident",e.warm},{"activation",e.activation},{"suffix",e.suffix},
                        {"down",e.down},{"reduction",e.reduction},{"copied",e.copied},{"sets",e.sets},
                        {"checked_stage_words",e.split()?8*width:0},{"checked_weighted",4*width},{"checked_ffn",width}};
        };
        for (const auto &m:modes) output["parity"].push_back(run(m,-1,-1));
        for (int b=0;b<2;++b)
            for (int r=0;r<5;++r)
                for (int i=0;i<6;++i) output["trials"].push_back(run(modes[b ? 5-i : i],b,r));
    }
    need(fstat_id(fd)==plan.at("pack_stat") && close(fd)==0,"pack drain");
    output["workers_joined"]=4;
    output["ggml_threads"]=8;
    return output;
}
}

int main(int argc,char **argv) {
    try {
        const char *weighted=std::getenv("TESY_READY_WEIGHTED");
        need(argc==6 && std::string(argv[4])=="LAYER" && weighted,"sealed supervisor");
        std::cout<<prefix::experiment(argv[1],argv[2],argv[3],fs::path(weighted).parent_path()).dump()<<'\n';
        return 0;
    } catch (const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
