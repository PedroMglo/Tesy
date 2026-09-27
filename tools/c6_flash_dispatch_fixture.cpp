#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fcntl.h>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

static void check(bool ok, const char * message) {
    if (!ok) throw std::runtime_error(message);
}

static void write_new(const char * path, const void * data, size_t bytes) {
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    check(fd >= 0, "output exists or cannot be created");
    const char * p = static_cast<const char *>(data);
    while (bytes) {
        ssize_t n = write(fd, p, bytes);
        if (n <= 0) { close(fd); throw std::runtime_error("short output write"); }
        p += n;
        bytes -= static_cast<size_t>(n);
    }
    check(close(fd) == 0, "output close failed");
}

int main(int argc, char ** argv) {
    if (argc != 5 && argc != 6) {
        std::cerr << "usage: c6_flash_dispatch_fixture NQ NKV f16|f32 OUTPUT.f32 [missing-workspace]\n";
        return 2;
    }
    try {
        int nq = std::stoi(argv[1]);
        int nkv = std::stoi(argv[2]);
        std::string kvtype = argv[3];
        check(nq >= 1 && nq <= 65 && nkv >= 64 && nkv <= 640, "invalid dimensions");
        check(kvtype == "f16" || kvtype == "f32", "invalid KV dtype");
        ggml_type kt = kvtype == "f16" ? GGML_TYPE_F16 : GGML_TYPE_F32;
        ggml_init_params init = {};
        init.mem_size = 4u*1024u*1024u;
        init.no_alloc = true;
        ggml_context * ctx = ggml_init(init);
        check(ctx != nullptr, "context failed");
        ggml_tensor * qb = ggml_new_tensor_3d(ctx, GGML_TYPE_F32, 64, 64, nq);
        ggml_tensor * kb = ggml_new_tensor_3d(ctx, kt, 64, 8, nkv);
        ggml_tensor * vb = ggml_new_tensor_3d(ctx, kt, 64, 8, nkv);
        ggml_tensor * mask = ggml_new_tensor_2d(ctx, GGML_TYPE_F16, nkv, nq);
        ggml_tensor * sinks = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, 64);
        ggml_tensor * q = ggml_permute(ctx, qb, 0, 2, 1, 3);
        ggml_tensor * k = ggml_permute(ctx, kb, 0, 2, 1, 3);
        ggml_tensor * v = ggml_permute(ctx, vb, 0, 2, 1, 3);
        ggml_tensor * flash = ggml_flash_attn_ext(ctx, q, k, v, mask, 0.125f, 0.0f, 0.0f);
        ggml_flash_attn_ext_add_sinks(flash, sinks);
        ggml_flash_attn_ext_set_prec(flash, GGML_PREC_F32);
        ggml_cgraph * graph = ggml_new_graph_custom(ctx, 256, false);
        ggml_build_forward_expand(graph, flash);
        ggml_backend_t backend = ggml_backend_cpu_init();
        check(backend != nullptr, "CPU backend failed");
        ggml_backend_cpu_set_n_threads(backend, 8);
        ggml_backend_buffer_t buffer = ggml_backend_alloc_ctx_tensors(ctx, backend);
        check(buffer != nullptr, "backend allocation failed");
        std::vector<float> qdata(static_cast<size_t>(nq)*4096);
        for (size_t i = 0; i < qdata.size(); i++) qdata[i] = static_cast<float>(int(i%23)-11)*0.01f;
        std::vector<float> kvdata(static_cast<size_t>(nkv)*512);
        for (size_t i = 0; i < kvdata.size(); i++) kvdata[i] = static_cast<float>(int(i%19)-9)*0.01f;
        std::vector<uint16_t> halfdata(kvdata.size());
        if (kt == GGML_TYPE_F16) {
            for (size_t i = 0; i < kvdata.size(); i++) halfdata[i] = ggml_fp32_to_fp16(kvdata[i]);
        }
        std::vector<uint16_t> mdata(static_cast<size_t>(nq)*nkv, ggml_fp32_to_fp16(0.0f));
        std::vector<float> sdata(64, 0.0f);
        ggml_backend_tensor_set(qb, qdata.data(), 0, qdata.size()*sizeof(float));
        const void * kvptr = kt == GGML_TYPE_F16 ? static_cast<const void *>(halfdata.data()) : static_cast<const void *>(kvdata.data());
        size_t kvbytes = kt == GGML_TYPE_F16 ? halfdata.size()*sizeof(uint16_t) : kvdata.size()*sizeof(float);
        ggml_backend_tensor_set(kb, kvptr, 0, kvbytes);
        ggml_backend_tensor_set(vb, kvptr, 0, kvbytes);
        ggml_backend_tensor_set(mask, mdata.data(), 0, mdata.size()*sizeof(uint16_t));
        ggml_backend_tensor_set(sinks, sdata.data(), 0, sdata.size()*sizeof(float));
        if (argc == 6) {
            check(std::string(argv[5]) == "missing-workspace", "invalid extra argument");
            ggml_cplan plan = ggml_graph_plan(graph, 8, nullptr);
            check(plan.work_size > 0 && plan.work_data == nullptr, "workspace negative fixture invalid");
            ggml_graph_compute(graph, &plan); // GGML must reject an absent scratch allocation.
            throw std::runtime_error("missing workspace accepted");
        }
        check(ggml_backend_graph_compute(backend, graph) == GGML_STATUS_SUCCESS, "compute failed");
        std::vector<float> out(static_cast<size_t>(nq)*4096);
        check(ggml_nbytes(flash) == out.size()*sizeof(float), "output size changed");
        ggml_backend_tensor_get(flash, out.data(), 0, out.size()*sizeof(float));
        for (float x : out) check(std::isfinite(x), "non-finite output");
        write_new(argv[4], out.data(), out.size()*sizeof(float));
        std::cout << "C6_FA_FIXTURE nq=" << nq << " nkv=" << nkv << " kv=" << kvtype << " output_f32=" << out.size() << '\n';
        ggml_backend_buffer_free(buffer);
        ggml_backend_free(backend);
        ggml_free(ctx);
        return 0;
    } catch (const std::exception & e) {
        std::cerr << "C6_FA_FIXTURE_FAIL: " << e.what() << '\n';
        return 1;
    }
}
