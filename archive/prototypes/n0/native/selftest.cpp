#include "expert_store.hpp"
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <unistd.h>
#include <fcntl.h>

namespace {
void check(bool yes, const char * why) { if (!yes) throw std::runtime_error(why); }
template<class F> void rejects(F && f) {
    bool failed = false;
    try { f(); } catch (const std::exception &) { failed = true; }
    check(failed, "expected rejection");
}
}
int main() {
    char file[] = "/tmp/tesy-native-XXXXXX";
    const int fd = ::mkstemp(file);
    if (fd < 0) return 2;
    ::close(fd);
    try {
        // width=2, hidden=2: three identity matrices per expert; distinct expert ids.
        const std::vector<float> weights = {1,0,0,1, 1,0,0,1, 1,0,0,1};
        {
            std::ofstream out(file, std::ios::binary);
            for (int i = 0; i < 3; ++i)
                out.write(reinterpret_cast<const char *>(weights.data()),
                          static_cast<std::streamsize>(weights.size() * sizeof(float)));
            out.close();
            check(bool(out), "fixture write");
        }
        const std::vector<tesy::ExpertSpec> specs = {{0,0,2,2}, {1,48,2,2}, {2,96,2,2}};
        tesy::ExpertStore store(file, specs, 96);
        std::vector<float> out{999};
        tesy::run_expert(store, 0, {1,2}, out);
        check(out.size() == 2, "output geometry");
        check(std::abs(out[0] - 1.0F/(1.0F+std::exp(-1.0F))) < 1e-6F, "reference0");
        check(std::abs(out[1] - 4.0F/(1.0F+std::exp(-2.0F))) < 1e-6F, "reference1");
        tesy::run_expert(store, 0, {1,2}, out);
        check(store.stats().loads == 1 && store.stats().hits == 1, "real cache hit");
        {
            auto a = store.acquire(0);
            auto b = store.acquire(1);
            rejects([&] { (void) store.acquire(2); });
            check(store.stats().loads == 2 && store.stats().evictions == 0, "lease pin");
            check(a.weights->size() == 12 && b.weights->size() == 12, "live payload");
        }
        (void)store.acquire(2);
        check(store.stats().evictions == 1 && store.stats().returned_source_bytes == 144,
              "bounded actual demand reads");
        check(store.stats().peak_bytes <= 96, "cache payload ceiling");
        const auto before = out;
        rejects([&] { tesy::run_expert(store, 0, {1}, out); });
        check(out == before, "unchanged output on bad geometry");
        rejects([&] { tesy::run_expert(store, 0, {std::numeric_limits<float>::infinity(),1}, out); });
        check(out == before, "unchanged output on nonfinite");
        rejects([&] { (void)store.acquire(99); });
        rejects([&] { tesy::ExpertStore bad(file, {{0,0,2,2},{0,48,2,2}},96); });
        rejects([&] { tesy::ExpertStore bad(file, {{0,0,2,2},{1,4,2,2}},96); });
        rejects([&] { tesy::ExpertStore bad(file, specs,47); });
        rejects([&] { tesy::ExpertStore bad(file, {{0,120,2,2}},96); });
        std::filesystem::resize_file(file, 100);
        rejects([&] { (void)store.acquire(2); });
        check(store.poisoned(), "mutation must poison");
        rejects([&] { (void)store.acquire(0); });
        std::filesystem::remove(file);
        std::cout << "{\"decision\":\"SYNTHETIC_NATIVE_TESTS_OK\",\"qualification\":false,"
                     "\"llm_loaded\":false,\"gpu_used\":false,\"physical_nvme_measured\":false}\n";
        return 0;
    } catch (const std::exception & e) {
        std::filesystem::remove(file);
        std::cerr << e.what() << '\n';
        return 1;
    }
}
