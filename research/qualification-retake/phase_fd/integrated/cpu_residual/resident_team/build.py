"""Build a separate C266 client with the authenticated C291 manager and stock GGML DSO."""

import argparse
import hashlib
import json
import os
import resource
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUFFIX = HERE.parents[3] / "cpu0_suffix"
OLD = "37f7ceec65cab37640dbf4b5b1f48bec19165d097a84adbfb956a01ea7db1f13"
LIBS = {
    "libggml-cpu.so.0.15.3": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
    "libggml-base.so.0.15.3": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
}
FILES = ("build.py", "protocol.md", "execute.inc", "team.h", "observe.c", "smoke.cpp")
EXPORTS = ("ggml_cpu_extra_compute_forward", "ggml_barrier")


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def replace(source, old, new):
    need(source.count(old) == 1, "anchored source changed: " + old[:55])
    return source.replace(old, new)


def materialize(source):
    source = replace(
        source, '#include "suffix-clock.h"', '#include "suffix-clock.h"\n#include "team.h"'
    )
    a = source.index('    need(mode=="OFF"')
    b = source.index('    need(std::getenv("TESY_PACKED_CPU_SLOTS")', a)
    source = (
        source[:a]
        + """    need(mode=="R" || mode=="A" || mode=="B","team selection");
#ifdef TEAM_ORIGINAL
    const bool stock=true;need(mode=="R","independent R control");
#else
    const bool stock=false;
#endif
"""
        + source[b:]
    )
    source = replace(
        source,
        "marked && w==0 ? timed_wave_ids : llama_moe_stream_wave_ids",
        "llama_moe_stream_wave_ids",
    )
    a = source.index("    put(x,tile(in.activation,width))")
    b = source.index("\n}\nint main(", a)
    source = source[:a] + '#include "execute.inc"' + source[b:]
    return replace(
        source,
        'receipt["status"]="PASS_C291_CPU0_SUFFIX"',
        'receipt["status"]="PASS_C266_RESIDENT_TEAM_ARM"',
    )


def build(a, receipt):
    out, old, libs = a.new_output_dir, a.old_build, a.libs
    need(sha(old / "receipt.json") == OLD, "parent build")
    authority = json.loads((old / "receipt.json").read_text())
    need(
        authority["status"] == "PASS_C291_CPU0_SUFFIX_BUILD" and authority["libs"] == LIBS,
        "historical numeric build",
    )
    for name, h in LIBS.items():
        need(sha(libs / name) == h, "original provider")
    pins = {
        old / "layer.cpp": authority["layer_patched_sha256"],
        old / "pairs-finish.inc": authority["helper_sha256"],
        SUFFIX / "suffix-clock.h": authority["sources"]["suffix-clock.h"],
    }
    src = old / "src"
    for name, info in authority["worker_input_manifest"].items():
        pins[src / name] = info["sha256"]
    need(all(sha(path) == h for path, h in pins.items()), "parent source/header changed")
    git = ["/usr/bin/git", "--no-optional-locks", "-C", HERE]

    def rev(*args):
        return subprocess.check_output([*git, *args], text=True, timeout=15).strip()

    need(not rev("status", "--porcelain"), "build from clean worktree")
    receipt.update(
        commit=rev("rev-parse", "HEAD"),
        tree=rev("rev-parse", "HEAD^{tree}"),
        source_sha256={p: sha(HERE / p) for p in FILES},
        libs=LIBS,
        parent_build_sha256=OLD,
    )
    cxx = Path("/usr/bin/g++").resolve()
    cc = Path("/usr/bin/gcc").resolve()
    need(sha(cxx) == authority["compiler_sha256"], "C291 fixture compiler")
    manager = src / "src/llama-moe-stream.cpp"
    patched = replace(
        manager.read_text(),
        "void llama_moe_stream::worker_loop() {",
        'extern "C" void team_io_started();\n'
        "void llama_moe_stream::worker_loop() {\n    team_io_started();",
    )
    (out / "manager.cpp").write_text(patched)
    (out / "client.cpp").write_text(materialize((old / "layer.cpp").read_text()))
    env = {
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "LD_LIBRARY_PATH": str(libs),
        "CUDA_VISIBLE_DEVICES": "",
    }

    def run(argv, label):
        with (out / (label + ".log")).open("xb") as log:
            subprocess.run(
                argv, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=135, check=True
            )

    flags = [
        "-std=c++17",
        "-O0",
        "-g0",
        "-Wall",
        "-Wextra",
        "-pthread",
        "-fPIC",
        "-fno-plt",
        "-ffunction-sections",
        "-fdata-sections",
        "-DTESY_C47_CPU_SKIP_PARKED",
        "-DTESY_STORE_TESTING",
        *[
            "-I" + str(p)
            for p in (HERE, SUFFIX, old, src / "src", src / "include", src / "ggml/include")
        ],
    ]
    run(
        [
            cc,
            "-std=gnu11",
            "-O2",
            "-fPIC",
            "-I" + str(src / "ggml/include"),
            "-c",
            HERE / "observe.c",
            "-o",
            out / "observe.o",
        ],
        "observer",
    )
    exports = ["-Wl,--export-dynamic-symbol=" + s for s in EXPORTS]
    run(
        [
            cxx,
            *flags,
            *exports,
            HERE / "smoke.cpp",
            out / "observe.o",
            *[libs / s for s in LIBS],
            "-pie",
            "-ldl",
            "-o",
            out / "smoke",
        ],
        "smoke-build",
    )
    env.update(OMP_NUM_THREADS="8", OMP_DYNAMIC="FALSE", TESY_CPU_WAVE_SKIP_PARKED="1")
    run([out / "smoke"], "smoke-check")
    need(
        (out / "smoke-check.log")
        .read_text()
        .strip()
        .endswith("PASS_C269_RESIDENT_TEAM_SYNTHETIC_24X8"),
        "real GGML handshakes without weights",
    )
    receipt["small_ggml_sha256"] = sha(out / "smoke-check.log")
    objects = []
    for p in [out / "manager.cpp", src / "src/llama-impl.cpp", src / "src/llama-mmap.cpp"]:
        obj = out / (p.stem + ".o")
        run([cxx, *flags, "-c", p, "-o", obj], p.stem)
        objects.append(obj)
    receipt["executables"] = {}
    for name in ("stock", "observed"):
        optional = (
            ["-DTEAM_ORIGINAL"]
            if name == "stock"
            else [out / "observe.o", *["-Wl,--export-dynamic-symbol=" + s for s in EXPORTS]]
        )
        exe = out / name
        run(
            [
                cxx,
                *flags,
                *optional,
                out / "client.cpp",
                *objects,
                "-pie",
                "-Wl,--gc-sections",
                "-Wl,--wrap=pread",
                "-Wl,--wrap=ggml_backend_tensor_set",
                *[libs / s for s in LIBS],
                "-ldl",
                "-o",
                exe,
            ],
            name + "-link",
        )
        syms = subprocess.check_output(["/usr/bin/nm", "--defined-only", "-D", exe], text=True)
        need(
            all(
                (s in [line.split()[-1] for line in syms.splitlines() if line.split()])
                == (name == "observed")
                for s in EXPORTS
            ),
            "observer symbol separation",
        )
        linked = subprocess.check_output(["/usr/bin/ldd", exe], env=env, text=True)
        need(
            not any(
                n in linked
                for n in ("libcuda", "libnvidia", "libllama", "not found", "libggml-cuda")
            ),
            "CPU-only",
        )
        for lib in LIBS:
            resolved = [
                Path(line.split()[2])
                for line in linked.splitlines()
                if line.strip().startswith(lib.rsplit(".", 2)[0] + " => ")
            ]
            need(
                len(resolved) == 1 and resolved[0].samefile(libs / lib), "loader-selected provider"
            )
        run([exe, "--self-test"], name + "-self-test")
        receipt["executables"][name] = sha(exe)
    receipt.update(
        status="PASS_C266_RESIDENT_TEAM_BUILD",
        compiler_sha256=sha(cxx),
        c_compiler_sha256=sha(cc),
        rendered_sha256=sha(out / "client.cpp"),
        manager_sha256=sha(out / "manager.cpp"),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("old-build", "libs", "new-output-dir"):
        ap.add_argument("--" + name, type=lambda s: Path(s).resolve(), required=True)
    args = ap.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    result = {"status": "FAIL_PRESERVED"}
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
        build(args, result)
    except Exception as err:
        result["reason"] = str(err)
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
