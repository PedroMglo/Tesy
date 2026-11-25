"""Apply the device-only changes to the pinned, witnessed CPU consumer."""

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
CPU = "feb6ee23a84bc673ff20ccf13eec46efe9f80c7c6b274b496a39e0ae3c527017"


def render(original):
    if hashlib.sha256(original).hexdigest() != CPU:
        raise ValueError("CPU observer source identity")
    src = original.decode()

    def replace(before, after):
        nonlocal src
        if src.count(before) != 1:
            raise ValueError("ambiguous device boundary: " + before[:50])
        src = src.replace(before, after)

    replace('#include "ggml-cpu.h"', '#include "ggml-cpu.h"\n#include "ggml-cuda.h"')
    replace("enum class Arm {", (HERE / "mapped.inc").read_text() + "\nenum class Arm {")
    replace(
        "if (dst->src[1]) std::memcpy(&s.token, dst->src[1]->data, sizeof(float));",
        """
    if (dst->src[1]) {
        auto *t = dst->src[1];
        need(t->buffer && ggml_backend_buffer_is_host(t->buffer) &&
             ggml_nbytes(t) == sizeof(float), "missing CPU scalar handoff");
        std::memcpy(&s.token, t->data, sizeof(float));
    }""",
    )
    replace(
        '    need(bool(cpu), "CPU backend");',
        """
    need(bool(cpu), "CPU backend");
    ggml_backend_ptr gpu(ggml_backend_cuda_init(0));
    need(bool(gpu) && ggml_backend_is_cuda(gpu.get()), "CUDA0 backend");
    mapped(dir, "active");
    ggml_backend_event_ptr done(ggml_backend_event_new(ggml_backend_get_device(gpu.get())));
    need(bool(done), "CUDA completion event");""",
    )
    replace(
        "for (auto &w : weights) w = ggml_new_tensor_3d(c, GGML_TYPE_MXFP4, width, width, ranks);",
        """ggml_context_ptr wc(ggml_init({1u << 16, nullptr, true}));
    need(bool(wc), "weight metadata");
    for (auto &w : weights) w = ggml_new_tensor_3d(wc.get(), GGML_TYPE_MXFP4, width, width, ranks);
    ggml_backend_buffer_ptr wb(ggml_backend_alloc_ctx_tensors(wc.get(), gpu.get()));
    need(bool(wb) && std::string(ggml_backend_buffer_name(wb.get())) == "CUDA0" &&
         !ggml_backend_buffer_is_host(wb.get()), "CUDA0 weight allocation");
    ggml_backend_buffer_set_usage(wb.get(), GGML_BACKEND_BUFFER_USAGE_WEIGHTS);""",
    )
    replace(
        """    ggml_backend_buffer_ptr buffer(ggml_backend_alloc_ctx_tensors(c, cpu.get()));
    need(bool(buffer), "operator allocation");""",
        (HERE / "scheduler.inc").read_text(),
    )
    replace(
        """    need(ggml_backend_graph_compute(cpu.get(), g) == GGML_STATUS_SUCCESS, "FFN compute");
    ggml_backend_synchronize(cpu.get());
    s.mark(s.graph_done, "GRAPH_DONE");
    if (worker.valid()) worker.get();""",
        """
    need(ggml_backend_sched_graph_compute_async(sched.get(), g) == GGML_STATUS_SUCCESS,
         "CUDA FFN submit");
    if (arm == Arm::event) {
        ggml_backend_event_record(done.get(), gpu.get());
        ggml_backend_event_synchronize(done.get());
        std::cout << "GPU_EVENT_COMPLETED\\n";
        s.mark(s.graph_done, "GRAPH_DONE");
        worker.get();
        ggml_backend_sched_synchronize(sched.get());
    } else {
        ggml_backend_sched_synchronize(sched.get());
        s.mark(s.graph_done, "GRAPH_DONE");
        if (worker.valid()) worker.get();
    }""",
    )
    start = src.index(
        '    std::ifstream maps("/proc/self/maps");', src.index('std::cout << "PROJECTIONS "')
    )
    end = src.index("\n}", start)
    src = src[:start] + '    mapped(dir, "finish");' + src[end:]
    replace(
        "        execute(static_cast<Arm>(found-names.begin()), dir);",
        """
        mapped(dir,"start");
        execute(static_cast<Arm>(found-names.begin()), dir);
        mapped(dir,"drain");""",
    )
    return src
