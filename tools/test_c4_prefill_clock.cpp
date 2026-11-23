#include "c4_prefill_clock.h"

#include <atomic>
#include <chrono>
#include <iostream>
#include <thread>

int main() {
    using namespace std::chrono_literals;
    std::atomic<bool> ready{false};
    std::thread worker;
    std::vector<double> chunks(2);
    bool quiesced = false;
    const auto result = c4_measure_prefill(5, 3,
        [&] { quiesced = true; },
        [&](int offset, int count) {
            if (!quiesced || (offset != 0 && offset != 3) ||
                (count != 3 && count != 2)) throw std::runtime_error("wrong batch schedule");
            if (offset == 3) worker = std::thread([&] {
                std::this_thread::sleep_for(40ms);
                ready.store(true, std::memory_order_release);
            });
        },
        [&] {
            worker.join();
            return ready.load(std::memory_order_acquire);
        }, chunks);
    if (!ready || result.completion_s < 0.035 || result.pending_tail_s < 0.035 ||
        result.dispatch_s >= result.completion_s || chunks.size() != 2)
        throw std::runtime_error("asynchronous tail omitted from completion");
    bool rejected = false;
    try {
        std::vector<double> one(1);
        c4_measure_prefill(1, 1, [] {}, [](int, int) {}, [] { return false; }, one);
    } catch (const std::runtime_error &) { rejected = true; }
    if (!rejected) throw std::runtime_error("missing output accepted");
    std::cout << "C4_CLOCK_MODEL_FREE_PASS\n";
}
