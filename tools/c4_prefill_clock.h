#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <stdexcept>
#include <vector>

struct c4_prefill_timing {
    double dispatch_s;
    double completion_s;
    double pending_tail_s;
};

template <typename Quiesce, typename Decode, typename Complete>
c4_prefill_timing c4_measure_prefill(int n_tokens, int batch_size,
                                    Quiesce quiesce, Decode decode,
                                    Complete complete,
                                    std::vector<double> & chunk_dispatch_s) {
    if (n_tokens <= 0 || batch_size <= 0) throw std::runtime_error("invalid prefill shape");
    const int n_chunks = (n_tokens + batch_size - 1) / batch_size;
    if (chunk_dispatch_s.size() != static_cast<size_t>(n_chunks))
        throw std::runtime_error("chunk timing shape mismatch");
    quiesce();
    const auto start = std::chrono::steady_clock::now();
    for (int chunk = 0; chunk < n_chunks; ++chunk) {
        const int offset = chunk * batch_size;
        const int count = std::min(batch_size, n_tokens - offset);
        const auto dispatch_start = std::chrono::steady_clock::now();
        decode(offset, count);
        chunk_dispatch_s[static_cast<size_t>(chunk)] =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - dispatch_start).count();
    }
    const auto dispatched = std::chrono::steady_clock::now();
    if (!complete()) throw std::runtime_error("prefill output unavailable after fence");
    const auto finished = std::chrono::steady_clock::now();
    const auto dispatch_s = std::chrono::duration<double>(dispatched - start).count();
    const auto completion_s = std::chrono::duration<double>(finished - start).count();
    const auto tail_s = std::chrono::duration<double>(finished - dispatched).count();
    if (!std::isfinite(dispatch_s) || !std::isfinite(completion_s) ||
        !std::isfinite(tail_s) || dispatch_s <= 0 || completion_s < dispatch_s || tail_s < 0)
        throw std::runtime_error("invalid prefill timing");
    return {dispatch_s, completion_s, tail_s};
}
