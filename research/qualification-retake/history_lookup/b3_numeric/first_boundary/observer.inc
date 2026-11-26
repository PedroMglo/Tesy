// Embedded only in the derived main executable. Read in the scheduler's synchronized post callback.
struct Cut {
    int axis, d0, d1;
    ggml_type type;
    ggml_op op, alt;
};

struct Boundary {
    std::map<std::string, Cut> cuts = { CUT_TABLE };
    std::set<std::string> observed;
    fs::path root;
    int start = -1, width = 0;

    void begin(int step, int n, const fs::path &out) {
        start = step < 3 ? 189 + step : -1;
        width = n;
        observed.clear();
        root = out / "boundary";
        if (step == 0) check(fs::create_directory(root), "exclusive observer directory");
    }

    static void validate(const ggml_tensor *t, const Cut &c, int n) {
        const int64_t want[] = {c.d0, c.axis == 1 ? n : c.d1, c.axis == 1 ? 1 : n, 1};
        check(t->type == c.type && std::equal(want, want+4, t->ne), "boundary dtype/shape");
        check(t->nb[0] == 4 && t->nb[1] >= size_t(c.d0)*4, "boundary row stride");
        if (c.axis == 2 && n > 1)
            check(t->nb[2] >= size_t(c.d1-1)*t->nb[1] + size_t(c.d0)*4, "boundary position stride");
    }

    static std::vector<uint32_t> copy(const ggml_tensor *t, const Cut &c, int pos) {
        std::vector<uint32_t> values(size_t(c.d0)*c.d1);
        for (int j = 0; j < c.d1; ++j) {
            const size_t offset = size_t(pos)*t->nb[c.axis] + size_t(j)*t->nb[1];
            const size_t bytes = size_t(c.d0)*4;
            check(offset <= ggml_nbytes(t) && bytes <= ggml_nbytes(t)-offset, "boundary span");
            ggml_backend_tensor_get(t, values.data()+size_t(j)*c.d0, offset, bytes);
        }
        return values;
    }

    bool sample(ggml_tensor *t, bool ask) {
        if (start < 0) return false;
        const std::string name = ggml_get_name(t);
        const auto found = cuts.find(name);
        if (found == cuts.end()) return false;
        const auto &c = found->second;
        // Earlier Q/K projections use the same names as post-RoPE. V has pre-reshape names too.
        if (t->op != c.op && t->op != c.alt) {
            const bool qkv = name.rfind("Qcur-",0)==0 || name.rfind("Kcur-",0)==0 || name.rfind("Vcur-",0)==0;
            check(qkv && ask, "unexpected boundary operator");
            return false;
        }
        validate(t, c, width);
        if (ask) return true;
        check(observed.insert(name).second, "duplicate synchronized tensor");
        for (int i=0; i<width; ++i) {
            auto v = copy(t, c, i);
            const auto path = root/(std::to_string(start+i)+"."+name+".bin");
            write_new(path, v.data(), v.size()*sizeof(v[0]));
        }
        std::ofstream meta(root/"geometry.tsv", std::ios::app);
        meta << start << '\t' << width << '\t' << name << '\t' << ggml_op_name(t->op);
        for (auto n : t->ne) meta << '\t' << n;
        for (auto b : t->nb) meta << '\t' << b;
        meta << '\n';
        meta.close();
        check(meta.good(), "write boundary geometry");
        // A false POST response terminates this scheduler split prematurely.
        return true;
    }

    void finish() const {
        if (start >= 0) check(observed.size()==cuts.size(), "incomplete graph boundary coverage");
    }
};

// The top-k is a view with stride from all experts. Exercise ordinary ggml buffer reads with padding.
void test_boundary_stride() {
    ggml_init_params p{1024*1024,nullptr,true};
    auto *ctx = ggml_init(p);
    check(ctx != nullptr, "synthetic context");
    auto *base = ggml_new_tensor_2d(ctx, GGML_TYPE_I32, 128, 3);
    auto *view = ggml_view_2d(ctx, base, 4, 3, base->nb[1], 0);
    auto *buffer = ggml_backend_alloc_ctx_tensors_from_buft(ctx, ggml_backend_cpu_buffer_type());
    check(buffer != nullptr, "synthetic buffer");
    std::array<int32_t,384> v{};
    for (int j=0;j<3;++j) for(int i=0;i<128;++i) v[128*j+i]=j*1000+i;
    ggml_backend_tensor_set(base,v.data(),0,sizeof(v));
    Cut c{1,4,1,GGML_TYPE_I32,GGML_OP_VIEW,GGML_OP_VIEW};
    Boundary::validate(view,c,3);
    for(int j=0;j<3;++j) {
        auto got=Boundary::copy(view,c,j);
        for(int i=0;i<4;++i) check(got.at(i)==uint32_t(1000*j+i),"strided position/rank");
    }
    bool rejected=false;
    try { Boundary::validate(view,c,1); } catch(const std::exception &) { rejected=true; }
    check(rejected,"wrong synthetic geometry accepted");
    ggml_backend_buffer_free(buffer);
    ggml_free(ctx);
}
