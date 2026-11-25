int main(int argc,char **argv) try {
    check(argc==3 && std::string(argv[1])=="alias", "expected alias OUTPUT");
    const fs::path out(argv[2]);
    check(fs::is_directory(out) && fs::is_empty(out), "output must be empty");
    mapped(out,"start");
    check(ggml_backend_cuda_get_device_count()==1,"expected a single CUDA device");
    {
        ggml_backend_ptr cpu(ggml_backend_cpu_init()), gpu(ggml_backend_cuda_init(0));
        check(cpu && gpu && ggml_backend_is_cuda(gpu.get()),"mixed backends");
        ggml_backend_cpu_set_n_threads(cpu.get(),2);
        // Establish a real CUDA context before the NVML owner handshake.
        ggml_context_ptr init(ggml_init({1u << 16, nullptr, true}));
        check(bool(init), "bootstrap metadata");
        auto *token = ggml_new_tensor_1d(init.get(), GGML_TYPE_F32, 1);
        ggml_backend_buffer_ptr bootstrap(ggml_backend_alloc_ctx_tensors(init.get(),gpu.get()));
        check(bool(bootstrap), "CUDA bootstrap buffer");
        const float sentinel = 7.0f;
        float observed = 0.0f;
        ggml_backend_tensor_set(token,&sentinel,0,sizeof(sentinel));
        ggml_backend_tensor_get(token,&observed,0,sizeof(observed));
        check(observed==sentinel,"CUDA context bootstrap");
        mapped(out,"active");
        std::ofstream journal(out/"boundary.tsv");
        journal.exceptions(std::ios::failbit|std::ios::badbit);
        auto a=mixed::graph(cpu.get(),gpu.get(),3,false,39,journal).at(0);
        auto b=mixed::graph(cpu.get(),gpu.get(),3,false,38,journal).at(0);
        auto candidate=mixed::graph(cpu.get(),gpu.get(),3,true,39,journal);
        check(candidate.size()==4 && !mixed::equal(a.unmasked,b.unmasked) &&
              !mixed::equal(a.masked,b.masked), "negative control cannot distinguish A/B");
        auto save=[&](const mixed::Outputs &row, const std::string &label) {
            check(row.masked.size()==size_t(3*3*ranks*width) && row.unmasked.size()==row.masked.size(),
                  "incomplete endpoint");
            std::ofstream f(out/(label+".f32"),std::ios::binary);
            f.exceptions(std::ios::badbit|std::ios::failbit);
            for(auto *v : {&row.unmasked,&row.masked})
                f.write(reinterpret_cast<const char *>(v->data()), v->size()*sizeof(float));
            f.close();
        };
        save(a,"dense_A"); save(b,"dense_B");
        for(size_t i=0;i<candidate.size();++i) {
            const auto &gold=i%2 ? b : a;
            check(mixed::equal(gold.unmasked,candidate[i].unmasked) &&
                  mixed::equal(gold.masked,candidate[i].masked), "mixed generation bits");
            save(candidate[i],"stage"+std::to_string(i+1));
            std::cout<<"EPOCH "<<i+1<<' '<<(i%2)<<' '<<candidate[i].splits<<' '
                     <<(i!=0)<<' '<<candidate[i].masked.size()<<'\n';
        }
        mapped(out,"finish");
    }
    mapped(out,"drain");
    return 0;
} catch (const std::exception &e) {
    std::cerr<<e.what()<<'\n';
    return 1;
}
