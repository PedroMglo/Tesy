#include "llama.h"
#include <chrono>
#include <iostream>
#include <thread>
int main() {
    llama_backend_init();
    std::cout << "C147_DUMMY_READY_NO_MODEL" << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(5));
    llama_backend_free();
}
