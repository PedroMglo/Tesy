"""Compile the sealed warm policy/byte restoration around the original two-layer client."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
COLD = HERE.parent
BASE = run_path(str(COLD / "build.py"))
ROOT = BASE["ROOT"]
sha, need = BASE["sha"], BASE["need"]
COLD_NATIVE = "0ad5fabbfd712a1f0da6c643947268f5d588a51d39e22948c72ebb4d77c1fd60"
COLD_GRAPH = "18a32b9976faf4a6ad5676b8ebced680b5009d3ff75d2b26122b7b7096523fa9"


def once(source, old, new):
    need(source.count(old) == 1, "changed warm extension anchor: " + old[:64])
    return source.replace(old, new)


def specialize():
    need(
        sha(COLD / "native.cpp") == COLD_NATIVE and sha(COLD / "graph.inc") == COLD_GRAPH,
        "unqualified cold parent",
    )
    s = (COLD / "native.cpp").read_text()
    # Keep all original authentication/conservation gates. Bind their known populations to tile 5.
    for old, new in (
        ("PASS_REAL_TILE_INPUT", "PASS_REAL_TILE_WARM_INPUT"),
        ('plan.at("entries").size()==125', 'plan.at("entries").size()==32'),
        ("wit.sets.size()==375", "wit.sets.size()==96"),
        (
            "queued.size()==125&&waits.empty()&&dst.size()==125&&published.size()==125",
            "queued.size()==32&&waits.empty()&&dst.size()==32&&published.size()==32",
        ),
        ("enqueues==125+promoted.size()", "enqueues==32+promoted.size()"),
        ("wit.reads.size()<=130", "wit.reads.size()<=36"),
        ("std::array<int,4>{42,19,56,113}", "std::array<int,4>{6,13,20,21}"),
        ('"PASS_REAL_TILE"', '"PASS_WARM_TILE"'),
        ("m->prediction_request(1,1,offers)", "m->prediction_request(5,1,offers)"),
        (
            'm->prediction_begin(mode=="ON");m->select_prefill_tile(1,1);',
            'm->prediction_begin(mode=="ON");',
        ),
        (
            "; std::array<int64_t,8> epochs{};",
            "; std::array<int64_t,8> epochs{};\n    restore_scoped(*m,plan,occupancy);",
        ),
        (
            "void tile_workers_joined(llama_moe_stream &m){",
            "static void warm_finished(llama_moe_stream &);\n"
            "void tile_workers_joined(llama_moe_stream &m){",
        ),
        (
            "    auto &stage=*m.prediction_stage;",
            "    warm_finished(m);\n    auto &stage=*m.prediction_stage;",
        ),
        (
            'try{need(argc==5,"real-tile INPUT_DIR PACK_PATH OFF|ON EXACT|TIME");',
            'try{if(argc==2 && std::string(argv[1])=="--self-test"){'
            'warm_selftest();std::cout<<"PASS_WARM_CONTROLS\\n";return 0;}'
            'need(argc==5,"warm-tile INPUT_DIR PACK_PATH OFF|ON EXACT|TIME");',
        ),
        ("static void traffic(json &r){", '#include "restore.inc"\nstatic void traffic(json &r){'),
        (
            "    traffic(r);return r;",
            '    traffic(r);check_offer_lifecycle(r);r["restore"]=warm.receipt;return r;',
        ),
    ):
        s = once(s, old, new)
    graph = once(
        (COLD / "graph.inc").read_text(), "need(active_waves == 4", "need(active_waves == 3"
    )
    return s, graph


def adapt(src, out, r):
    source, graph = specialize()
    (out / "warm-native.cpp").write_text(source)
    (out / "graph.inc").write_text(graph)
    (out / "restore.inc").write_bytes((HERE / "restore.inc").read_bytes())
    # Only this client accepts C292 call 1 tile 5. The old C281 coding stays in its own executable.
    h = src / "src/llama-moe-stream.h"
    h.write_text(
        once(
            h.read_text(),
            "((call==1 && tile==1) || (call==2 && tile>=1 && tile<=5))",
            "(call==1 && tile==5)",
        )
    )
    c = src / "src/llama-moe-stream.cpp"
    code = once(
        c.read_text(),
        "    std::unique_lock<std::mutex> lk(mtx);\n    while (true) {",
        "    std::unique_lock<std::mutex> lk(mtx);\n"
        "    extern void warm_worker_ready(llama_moe_stream &); warm_worker_ready(*this);\n"
        "    while (true) {",
    )
    code = once(
        code,
        "    if (sl.slot_expert[slot] >= 0) {",
        "    extern void warm_reserve(int,int,int,int,uint64_t);\n"
        "    warm_reserve(sl.il,expert,slot,sl.slot_expert[slot],sl.slot_gen[slot]+1);\n"
        "    if (sl.slot_expert[slot] >= 0) {",
    )
    c.write_text(code)
    q = BASE["QUAL"]
    project_inputs = [
        Path(__file__),
        HERE / "restore.inc",
        HERE / "protocol.md",
        COLD / "graph.inc",
        COLD / "protocol.md",
        COLD / "queue-addendum.md",
        COLD / "native.cpp",
        COLD / "build.py",
        COLD.parent / "run.py",
        COLD.parent / "overlay.py",
        COLD.parent.parent / "projector.h",
        COLD.parent.parent / "operator/operator.cpp",
        q / "packed_worker/run.py",
        q / "packed_real_layer/build.py",
        ROOT / "tools/block_expert_reuse_operator.cpp",
    ]
    r["repo_sources"] = {str(p.relative_to(ROOT)): sha(p) for p in project_inputs}
    r["warm_generated_sources"] = {
        p.name: sha(p)
        for p in (h, c, out / "warm-native.cpp", out / "graph.inc", out / "restore.inc")
    }
    return "warm-tile", "PASS_WARM_TILE_BUILD", out / "warm-native.cpp"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("backend", "libs", "blas", "new-output-dir"):
        p.add_argument("--" + flag, type=Path, required=True)
    p.add_argument("--unit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(exist_ok=False)
    receipt = {"status": "FAIL_PRESERVED"}
    try:
        unit = a.unit.removesuffix(".scope") + ".scope"
        membership = Path("/proc/self/cgroup").read_text().strip().split("::")[-1]
        group = Path("/sys/fs/cgroup") / membership.strip("/")
        need(group.name == unit and unit.startswith("tesy-warm-tile-build-"), "wrong build scope")
        need(
            (group / "memory.max").read_text().strip() == str(2 << 30)
            and (group / "memory.swap.max").read_text().strip() == "0",
            "build requires E2 with zero swap",
        )
        receipt["scope"] = {"unit": unit, "max": 2 << 30, "swap_max": 0}
        BASE["build"](a, a.new_output_dir, receipt, variant=adapt)
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "OPENBLAS_NUM_THREADS": "1",
            "LD_LIBRARY_PATH": str(a.libs) + ":" + str(a.blas.resolve().parent),
        }
        checked = subprocess.check_output(
            [a.new_output_dir / "warm-tile", "--self-test"], env=env, timeout=10
        )
        need(checked == b"PASS_WARM_CONTROLS\n", "native fault controls")
        receipt["self_test"] = checked.decode().strip()
        receipt["scope"]["memory_peak"] = int((group / "memory.peak").read_text())
        receipt["scope"]["swap_peak"] = int((group / "memory.swap.peak").read_text())
        need(receipt["scope"]["swap_peak"] == 0, "swap used in build")
    except Exception as exc:
        receipt.update(status="FAIL_PRESERVED", error=repr(exc))
        raise
    finally:
        (a.new_output_dir / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )


if __name__ == "__main__":
    main()
