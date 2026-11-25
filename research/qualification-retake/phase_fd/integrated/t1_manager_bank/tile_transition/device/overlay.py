"""Specialize the frozen CPU transition at the device allocation and consumer hooks only."""

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parents[2] / "t1_manager_cuda/device"
CPU_SHA = "477dd0d58eb2b82fc5158acc6ee6279860559af7e6ddd57f5a673d5c237c368b"


def render():
    base = (HERE.parent / "fixture.cpp").read_bytes()
    if hashlib.sha256(base).hexdigest() != CPU_SHA:
        raise ValueError("CPU transition pin")
    s = base.decode()

    def replace(old, new):
        nonlocal s
        if s.count(old) != 1:
            raise ValueError("CUDA specialization: " + old[:70])
        s = s.replace(old, new)

    replace(
        'extern "C" ssize_t __real_pread',
        """
#include "ggml-cpu.h"
#include "ggml-cuda.h"
#include <cmath>
#include <filesystem>
#include <iostream>
namespace fs=std::filesystem;
void need(bool value,const char *message) { if (!value) throw std::runtime_error(message); }
"""
        + (PRIOR / "mapped.inc").read_text()
        + '\nextern "C" ssize_t __real_pread',
    )
    replace("void transition_reader(", (HERE / "ffn.inc").read_text() + "\nvoid transition_reader(")
    replace(
        "    json seen;\n    std::thread observer",
        """    json seen;
    const Ranks old_ids=last_wave_values(waves.at(1), "ids");
    const Ranks old_mask=last_wave_values(waves.at(1), "mask");
    auto read_hashes=[&]{seen["6"]=hashes(copy_slot(6)); seen["4"]=hashes(copy_slot(4));};
    std::thread observer""",
    )
    start = s.index("        // The same two physical indices")
    end = s.index("\n    });", start)
    replace(
        s[start:end],
        """        if (r.arm!="broken") read_hashes();
        auto order=r.arm=="broken"?Order::broken:(r.arm=="disk"?Order::event:Order::view);
        run_ffn("reader",old_ids,old_mask,order);
        if (r.arm=="broken") read_hashes();""",
    )
    replace('    if (r.arm != "broken")\n        release_reader();', "    release_reader();")
    replace(
        '    if (r.arm == "broken")\n        release_reader();',
        "    {std::lock_guard<std::mutex> lk(r.gate);b_published=true;r.cv.notify_all();}",
    )
    replace(
        "        llama_moe_stream mgr(1, 40, 4, true);",
        """        gpu.reset(ggml_backend_cuda_init(0)); cpu.reset(ggml_backend_cpu_init());
        check(gpu && cpu, "C269 CUDA0/CPU initialization");
        ggml_backend_cpu_set_n_threads(cpu.get(),1);
        llama_moe_stream mgr(1, 40, 4, true);""",
    )
    replace("ggml_backend_cpu_buffer_type()", "ggml_backend_cuda_buffer_type(0)")
    replace(
        '        r.phase = "A";', '        mapped(destination,"active");\n        r.phase = "A";'
    )
    replace(
        '        r.phase = "B";',
        """        if(r.arm=="reference")
            run_ffn("old-gold",last_wave_values(out["waves"].at(1),"ids"),last_wave_values(out["waves"].at(1),"mask"),Order::gold);
        r.phase = "B";""",
    )
    replace(
        '        out["before_restore"] = state();',
        """        out["before_restore"] = state();
        if(r.arm=="reference"){
            const auto &mapping=r.layer->expert_slot;
            run_ffn("new-gold",{mapping.at(3),mapping.at(5),mapping.at(43),mapping.at(42)},{0,0,1,1},Order::gold);
        }""",
    )
    replace(
        "        auto terminal = state();",
        """        run_ffn("decode",out["decode_ids"].get<Ranks>(),{1,1,1,1},Order::gold);
        auto terminal = state();""",
    )
    replace(
        "    r.layer = nullptr;",
        """    mapped(destination,"finish");
    gpu.reset();cpu.reset();
    out["operator_rows"]=operators;
    r.layer = nullptr;""",
    )
    replace("PASS_C291_TILE_TRANSITION_CPU", "PASS_C291_TILE_TRANSITION_CUDA")
    replace(
        "        const auto output = execute(argv[2]).dump();",
        """        destination=fs::path(argv[4]).parent_path();
        mapped(destination,"start");
        const auto output = execute(argv[2]).dump();
        mapped(destination,"drain");""",
    )
    return s.encode()
