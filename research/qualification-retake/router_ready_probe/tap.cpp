#include "tap.h"
#include "ggml-cpu-impl.h"
#include "ggml-backend.h"
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>

using Kernel = void (*)(const ggml_compute_params *, ggml_tensor *);
static Kernel original;
static Probe *active;

extern "C" void *ready_probe_arm(Probe *probe) {
    original = reinterpret_cast<Kernel>(dlsym(RTLD_NEXT, "ggml_compute_forward_get_rows"));
    active = probe;
    return reinterpret_cast<void *>(original);
}

extern "C" void ggml_compute_forward_get_rows(const ggml_compute_params *params, ggml_tensor *dst) {
    if (!original || !active) std::abort();
    auto &p = *active;
    if (params->ith == 0) {
        ++p.entries;
        p.threads = params->nth;
        auto *ids = dst->src[1];
        p.kernel_identity = dst == p.target && ids == p.ids && ids->op == GGML_OP_VIEW &&
            ids->src[0] && ids->src[0]->op == GGML_OP_ARGSORT && ids->view_src == ids->src[0] &&
            ids->view_offs == 0 && ids->data == ids->view_src->data && ids->type == GGML_TYPE_I32 &&
            ids->ne[0] == 4 && ids->ne[1] <= 32 && ids->nb[0] == 4 && ids->nb[1] == 512 &&
            ids->view_src->buffer && ggml_backend_buffer_is_host(ids->view_src->buffer);
        if (!p.kernel_identity) std::abort();
        if (p.mode) {
            const auto *data = static_cast<const char *>(ids->data);
            const size_t pitch = p.mode == 2 ? 16 : ids->nb[1];
            p.start = clock_now();
            for (int row = 0; row < ids->ne[1]; ++row)
                std::memcpy(p.snapshot + 4*row, data + row*pitch, 4*sizeof(int32_t));
            p.ready = clock_now();
        }
    }
    original(params, dst);
    if (params->ith == 0) ++p.forwarded;
}
