// The graph, tensor placement, native strided reads and operator order are shared with C269.
#define main historical_three_row_fixture
#include TESY_ROUTER_ROW_FIXTURE
#undef main

int main(int argc, char **argv) {
    try {
        need(argc == 4, "fixture WEIGHT BIAS NEW_OUTPUT; stdin is 32 activation rows");
        fs::path out = argv[3];
        need(fs::create_directory(out), "exclusive output");
        const auto w = read_input(argv[1], width * experts);
        const auto b = read_input(argv[2], experts);
        std::vector<float> x(32 * width);
        need(bool(std::cin.read(reinterpret_cast<char *>(x.data()), x.size() * sizeof(float)))
                 && std::cin.peek() == EOF, "32 input rows");
        auto *cpu = ggml_backend_cpu_init();
        need(cpu, "CPU backend");
        ggml_backend_cpu_set_n_threads(cpu, 8);
        std::cout << "cpu " << provider(reinterpret_cast<void *>(&ggml_backend_cpu_init)).string()
                  << "\nbase " << provider(reinterpret_cast<void *>(&ggml_mul_mat)).string() << "\n";
        graph(cpu, "w32", out, w, b, x.data(), 32);
        graph(cpu, "w5", out, w, b, x.data(), 5);
        graph(cpu, "w20", out, w, b, x.data() + 12 * width, 20);
        ggml_backend_free(cpu);
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << "\n";
        return 1;
    }
}
