// Small linked child for prospective run_bounded scope/mappings smoke.
#include "llama.h"
#include <chrono>
#include <thread>
#include <cstdio>

int main() {
    llama_backend_init();
    std::puts("C60_MODEL_FREE_READY");
    std::fflush(stdout);
    std::this_thread::sleep_for(std::chrono::seconds(5));
    llama_backend_free();
    return 0;
}
