"""Assemble the frozen C266 native client and gate its paid CPU tile comparisons."""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(str(HERE.parent / "run.py"))
ROOT, ROW, need, sha, git = (P[k] for k in ("ROOT", "ROW", "need", "sha", "git"))
Q = ROOT / "research/qualification-retake"
TEAM = Q / "phase_fd/integrated/cpu_residual/resident_team"
ARCH = run_path(str(Q / "private_archive/verify.py"))
METHOD = "42b7ce7838df20c02e239f3f7b2c5912c27cac9033e509847bb0e930fa682b28"
ORDERS = {"exact": ("STOCK", "OFF", "ON"), "price": ("OFF", "ON", "ON", "OFF")}


def read(path):
    return json.loads(path.read_bytes())


def replace(text, old, new):
    need(text.count(old) == 1, "source anchor " + old[:70])
    return text.replace(old, new)


def make_client(source):
    a = source.index('    need(mode=="R"')
    b = source.index('    need(std::getenv("TESY_PACKED_CPU_SLOTS")', a)
    source = (
        source[:a]
        + """    const bool timing = mode=="OFF_TIME" || mode=="ON_TIME";
    const bool enabled = mode=="ON" || mode=="ON_TIME";
    need(timing || mode=="OFF" || mode=="ON","fixture mode");
    need(std::fegetround()==FE_TONEAREST,"host rounding");
"""
        + source[b:]
    )
    source = replace(source, '#include "team.h"', '#include "team.h"\n#include "tail.h"')
    source = replace(
        source,
        "    auto ctx=context();auto *c=ctx.get();auto *g=ggml_new_graph_custom",
        """    const auto build_start = monotonic_ns();
    std::array<bool,128> routed{};
    for (int id : ids) { need(id>=0 && id<128,"router range"); routed[id]=true; }
    const int active_count = (std::count(routed.begin(),routed.end(),true)+17)/18;
    auto ctx=context();auto *c=ctx.get();auto *g=ggml_new_graph_custom""",
    )
    source = replace(source, "auto remap = llama_moe_stream_wave_ids;", "auto remap = capture_ids;")
    source = replace(
        source,
        "auto *value=pairs(c,t,x,r,physical);",
        "const bool empty = enabled && w>=active_count && sum;\n"
        "        auto *value=empty ? nullptr : pairs(c,t,x,r,physical);",
    )
    source = replace(source, "mo,2,llama_moe_stream_wave_mask,1,ud", "mo,2,capture_mask,1,ud")
    source = replace(
        source,
        "value=ggml_mul(c,value,mask);sum=sum?ggml_add(c,sum,value):value;",
        "if (empty) sum=tail_node(c,sum,physical,mask,r,t[5]);\n"
        "        else {value=ggml_mul(c,value,mask);sum=sum?ggml_add(c,sum,value):value;}",
    )
    source = replace(
        source,
        "need(observed.mmids.size()==24,",
        "need(observed.mmids.size()==size_t(3*(enabled?active_count:8)),",
    )
    source = replace(source, '#include "execute.inc"', '#include "run-tile.inc"')
    return replace(source, "PASS_C266_RESIDENT_TEAM_ARM", "PASS_C266_PARKED_TILE")


def verify_input(root):
    need(sha(root / "prepare.json") == P["DATA"]["prepare.json"], "C266 preparation")
    prep = read(root / "prepare.json")
    for f, h in prep["file_sha256"].items():
        need(Path(f).name == f and sha(root / f) == h, "prepared input " + f)
    need(
        (root / "pack.bin").stat().st_size == prep["pack_size_bytes"]
        and "pack.bin" in prep["file_sha256"],
        "partial pack",
    )


def build(a, out, record, libs, env):
    for part in ("part-24", "part-122"):
        ARCH["verify"](a.archive, read(Q / "private_archive" / (part + ".json")))
    parent = a.archive / "part-122/tesy-resident-team-build-20261125-r01"
    old = a.archive / "part-24/tesy-cpu0-suffix-build-20261125-r01"
    proof = read(parent / "receipt.json")
    need(
        proof["status"] == "PASS_C266_RESIDENT_TEAM_BUILD"
        and proof["libs"] == ROW["LIBS"]
        and sha(parent / "client.cpp") == proof["rendered_sha256"],
        "parent client",
    )
    previous = HERE.parent / "fixture.cpp"
    ref = read(a.archive / "part-200/tesy-c269-parked-run-20261126-r02/receipt.json")
    need(
        ref["status"] == "PASS_PARKED_DOWN_ARITHMETIC"
        and sha(previous) == ref["fixture_sha256"]
        and sha(a.archive / "part-200/tesy-c269-parked-run-20261126-r02/receipt.json")
        == "c0f684b606255244b4b558b6cb10cb3e7b9cb8402b066f04531b1eea8478b921",
        "tested scalar code",
    )
    helper = previous.read_text()
    (out / "parked-arithmetic.inc").write_text(
        helper[helper.index("static float empty_add(") : helper.index("static json run(")]
    )
    (out / "client.cpp").write_text(make_client((parent / "client.cpp").read_text()))
    objects = [parent / f for f in ("manager.o", "llama-impl.o", "llama-mmap.o")]
    src = old / "src"
    compiler = Path("/usr/bin/g++")
    need(sha(compiler) == proof["compiler_sha256"], "compiler")
    command = [
        compiler,
        "-std=c++20",
        "-O2",
        "-g0",
        "-fno-fast-math",
        "-ffp-contract=off",
        "-frounding-math",
        "-pthread",
        "-fPIC",
        "-fno-plt",
        "-ffunction-sections",
        "-fdata-sections",
        "-DTESY_C47_CPU_SKIP_PARKED",
        "-DTESY_STORE_TESTING",
        "-DTEAM_ORIGINAL",
        *[
            "-I" + str(f)
            for f in (
                HERE,
                out,
                TEAM,
                Q / "cpu0_suffix",
                old,
                src / "src",
                src / "include",
                src / "ggml/include",
            )
        ],
        out / "client.cpp",
        *objects,
        "-pie",
        "-Wl,--gc-sections",
        "-Wl,--wrap=pread",
        "-Wl,--wrap=ggml_backend_tensor_set",
        *[libs / f for f in ROW["LIBS"]],
        "-ldl",
        "-o",
        out / "fixture",
    ]
    record.update(
        command=list(map(str, command)),
        compiler_sha256=sha(compiler),
        objects={p.name: sha(p) for p in objects},
    )
    with (out / "compile.log").open("xb") as f:
        subprocess.run(
            command, env=env, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=120
        )
    subprocess.run([out / "fixture", "--self-test"], env=env, check=True, timeout=5)
    record.update(
        binary_sha256=sha(out / "fixture"),
        stock_sha256=proof["executables"]["stock"],
        status="BUILT_C266_PARKED_TILE",
    )


def check_exact(folder, arms):
    need([r["arm"] for r in arms] == list(ORDERS["exact"]), "exact family")
    for r in arms:
        leaf = folder / r["name"]
        need(
            sha(leaf / "tile.f32") == r["output_sha256"] == arms[0]["output_sha256"]
            and (leaf / "tile.f32").stat().st_size == 92160 * 4,
            "complete gold",
        )
        native = read(folder / (r["name"] + ".json"))
        need(
            sha(folder / (r["name"] + ".json")) == r["native_sha256"]
            and native["slots"] == read(folder / (arms[0]["name"] + ".json"))["slots"],
            "complete slot parity",
        )
        if r["arm"] != "STOCK":
            need(
                sha(leaf / "wave-maps.bin") == arms[1]["maps_sha256"] == r["maps_sha256"]
                and (leaf / "wave-maps.bin").stat().st_size == 8192,
                "eight waves of IDs and masks",
            )
    return arms


def run(a, out, record):
    need(
        not git(ROOT, "status", "--porcelain")
        and git(ROOT, "rev-parse", "HEAD") == a.commit
        and sha(HERE / "protocol.md") == METHOD,
        "method",
    )
    need(
        git(a.backend, "rev-parse", "HEAD") == ROW["COMMIT"]
        and not git(a.backend, "status", "--porcelain"),
        "clean backend",
    )
    group = (
        Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::/", 1)[1]
    )
    need(
        [(group / f).read_text().strip() for f in ("memory.max", "memory.swap.max", "pids.max")]
        == [str(1 << 30), "0", "24"],
        "resource caps",
    )
    need(
        Path("/sys/class/power_supply/AC0/online").read_text().strip() == "1"
        and "Ryzen AI 9 HX 370" in Path("/proc/cpuinfo").read_text(),
        "target on AC",
    )
    libs = a.backend / "build-c269-cuda/bin"
    need(all(sha(libs / f) == h for f, h in ROW["LIBS"].items()), "physical providers")
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=str(libs),
        CUDA_VISIBLE_DEVICES="",
        OMP_NUM_THREADS="8",
        OMP_DYNAMIC="FALSE",
        TESY_CPU_WAVE_SKIP_PARKED="1",
        TMPDIR=str(out),
    )
    record.update(
        commit=a.commit,
        tree=git(ROOT, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=METHOD,
        libs=ROW["LIBS"],
        kernel=platform.release(),
        new_requests=0,
        full_model_starts=0,
    )
    if a.phase == "build":
        build(a, out, record, libs, env)
        return
    verify_input(a.input)
    receipt = a.build / "receipt.json"
    need(sha(receipt) == a.build_sha256, "fixture build seal")
    frozen = read(receipt)
    need(
        frozen["commit"] == a.commit and frozen["status"] == "BUILT_C266_PARKED_TILE",
        "fixture build",
    )
    stock = a.archive / "part-122/tesy-resident-team-build-20261125-r01/stock"
    exe = a.build / "fixture"
    need(sha(stock) == frozen["stock_sha256"] and sha(exe) == frozen["binary_sha256"], "exact ELF")
    for label, binary in (("stock", stock), ("fixture", exe)):
        trace = subprocess.check_output(["ldd", binary], env=env, text=True)
        (out / (label + "-ldd.txt")).write_text(trace)
        for f in ROW["LIBS"]:
            prefix = f.split(".so")[0] + ".so"
            paths = [
                Path(line.split()[2])
                for line in trace.splitlines()
                if line.strip().startswith(prefix) and "=>" in line
            ]
            need(len(paths) == 1 and paths[0].samefile(libs / f), "selected CPU library")
        need("not found" not in trace and "libcuda" not in trace, "CPU-only executable")
    expected = None
    if a.phase == "price":
        need(
            sha(a.exact / "receipt.json") == a.exact_sha256
            and read(a.exact / "receipt.json")["status"] == "PASS_EXACT_C266_PARKED_TILE",
            "exactness before pricing",
        )
        expected = check_exact(a.exact, read(a.exact / "receipt.json")["arms"])[1]
    record.update(arms=[], build_sha256=a.build_sha256)
    for i, arm in enumerate(ORDERS[a.phase]):
        name = f"{i + 1}-{arm}"
        leaf = out / name
        mode = "R" if arm == "STOCK" else arm + ("_TIME" if a.phase == "price" else "")
        with (out / (name + ".json")).open("xb") as f, (out / (name + ".log")).open("xb") as e:
            subprocess.run(
                [stock if arm == "STOCK" else exe, a.input, mode, leaf],
                env=env,
                stdout=f,
                stderr=e,
                check=True,
                timeout=50,
            )
        native = read(out / (name + ".json"))
        need(
            native["manager_destructor_returned"]
            and native["joined_workers"] == 4
            and native["active_waves"] == 1,
            "routed service",
        )
        output = sha(leaf / "tile.f32")
        row = dict(
            arm=arm, name=name, output_sha256=output, native_sha256=sha(out / (name + ".json"))
        )
        if arm != "STOCK":
            need(
                native["status"] == "PASS_C266_PARKED_TILE"
                and native["mmids"] == (24 if arm == "OFF" else 3),
                "native graph",
            )
            row.update(
                maps_sha256=sha(leaf / "wave-maps.bin"),
                build_ns=native["build_ns"],
                nodes=native["graph_nodes"],
                mmids=native["mmids"],
                times_ns=native["times_ns"],
            )
        if expected:
            need(
                output == expected["output_sha256"]
                and row["maps_sha256"] == expected["maps_sha256"]
                and native["slots"] == read(a.exact / (expected["name"] + ".json"))["slots"]
                and len(row["times_ns"]) == 7,
                "unchanged exact inputs and outputs",
            )
            row["median_ns"] = statistics.median(row["times_ns"])
        record["arms"].append(row)
    if a.phase == "price":
        pairs = []
        for before, after in ((0, 1), (3, 2)):
            off, on = record["arms"][before], record["arms"][after]
            gain = off["median_ns"] - on["median_ns"]
            pairs.append(
                dict(hot_gain_ns=gain, with_build_gain_ns=gain + off["build_ns"] - on["build_ns"])
            )
        record.update(pairs=pairs, status="MEASURED_C266_PARKED_TILE")
    else:
        # Reopen exact outputs through the same verifier used to admit timing.
        check_exact(out, record["arms"])
        record["status"] = "PASS_EXACT_C266_PARKED_TILE"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("build", "exact", "price"))
    for k in ("archive", "backend", "build", "input", "exact", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=k in ("archive", "backend", "new-output-dir"))
    for k in ("commit", "build-sha256", "exact-sha256"):
        p.add_argument("--" + k, required=k == "commit")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    record = dict(status="FAIL_PRESERVED", phase=a.phase)
    try:
        run(a, out, record)
    except Exception as e:
        record["exception"] = str(e)
    tmp = out / "closed.tmp"
    with tmp.open("x") as f:
        json.dump(record, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    tmp.replace(out / "receipt.json")
    return int(record["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    sys.exit(main())
