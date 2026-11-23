// Exercise the C84 trace writer without loading a model or touching model files.
#include "llama-moe-stream.h"

#include "ggml-backend.h"
#include "ggml.h"

#include <cstdlib>
#include <mutex>

int main(int argc, char ** argv) {
    if (argc != 2 || setenv("TESY_C84_EXPERT_TRACE_FILE", argv[1], 1) != 0) return 2;
    ggml_init_params params = { 64 * 1024, nullptr, true };
    ggml_context * ctx = ggml_init(params);
    if (ctx == nullptr) return 3;
    ggml_tensor * meta = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 1, 1, 128);
    {
        llama_moe_stream mgr(1, 32, 1, false);
        mgr.create_cache_tensor(0, ggml_backend_cpu_buffer_type(), meta, 0, 0);
        mgr.alloc_bufs(false);
#ifdef TESY_C84_EXPERT_TRACE
        std::lock_guard<std::mutex> lock(mgr.mtx);
        mgr.trace_locked("DEMAND", 0, 7, -1, -1, 1, -1, 0, 0, 100);
        mgr.trace_locked("RESERVE", 0, 7, 0, -1, 0, -1, -1, 0, 101);
        mgr.trace_locked("WAIT_BEGIN", 0, -1, -1, -1, 1, -1, -1, 0, 102);
        mgr.trace_locked("LOAD_BEGIN", 0, 7, 0, -1, 0, -1, -1, 4, 103);
        mgr.trace_locked("LOAD_END", 0, 7, 0, -1, 0, -1, -1, 4, 120);
        mgr.trace_locked("WAIT_END", 0, -1, -1, -1, 1, -1, -1, 0, 121);
        mgr.trace_locked("DEMAND", 0, 7, 0, -1, 1, -1, 2, 0, 200);
#endif
    }
    ggml_free(ctx);
    return 0;
}
