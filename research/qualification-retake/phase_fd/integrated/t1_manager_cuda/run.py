"""Opt-in CPU integration. Build from authenticated C269 headers and use CPU/base only."""

import argparse
import json
import os
import resource
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
check = run_path(str(HERE / "check.py"))
digest, need = check["digest"], check["require"]
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
MAP_SHA = "7e9d0efb4c9bac6ef88d0de0003e8643fc14f4f9942c72a8101e2c166b8b1729"
PROTOCOL = "373781acc68e98fbf9094c30c887e61df219c2a5a027a45335fb71ef9f478fcc"


def elapsed(cmd, env, log, deadline):
    start = time.monotonic_ns()
    with log.open("xb") as f:
        p = subprocess.run(
            cmd, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=deadline, check=False
        )
    need(p.returncode == 0, f"{log.name}: exit {p.returncode}")
    return (time.monotonic_ns() - start) / 1e9


def load_optional(p):
    return p.read_bytes() if p.exists() else None


def execute(a, out, r):
    def git(*args):
        return subprocess.check_output(["git", "-C", a.backend, *args], timeout=10)

    need(digest((HERE / "protocol.md").read_bytes()) == PROTOCOL, "frozen protocol")
    need(git("rev-parse", "HEAD").decode().strip() == PIN, "backend HEAD")
    raw = a.map.read_bytes()
    need(digest(raw) == MAP_SHA, "static map")
    m = json.loads(raw)
    libs = {}
    for lib in ("libggml-base.so.0", "libggml-cpu.so.0"):
        src = Path(m["arms"]["C270"]["links"][lib][1])
        expected = m["files"][str(src)]["sha256"]
        need(digest(src.read_bytes()) == expected, lib)
        libs[lib] = src
    # Compile against exclusively pinned headers, even if other source files are dirty.
    includes = out / "include"
    includes.mkdir()
    for h in ("ggml.h", "ggml-alloc.h", "ggml-backend.h", "ggml-cpu.h", "ggml-cpp.h", "gguf.h"):
        (includes / h).write_bytes(git("show", f"{PIN}:ggml/include/{h}"))
    need(len({p.parent for p in libs.values()}) == 1, "library directory")
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=str(next(iter(libs.values())).parent),
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        CUDA_VISIBLE_DEVICES="",
    )
    compiler = Path("/usr/bin/g++-15")
    binary = out / "consumer"
    source = HERE / "consumer.cpp"
    r.update(
        backend=PIN,
        protocol_sha256=PROTOCOL,
        cpu_map_sha256=MAP_SHA,
        source_sha256=digest(source.read_bytes()),
        verifier_sha256=digest((HERE / "check.py").read_bytes()),
        compiler_sha256=digest(compiler.read_bytes()),
        cpu_libraries={n: digest(p.read_bytes()) for n, p in libs.items()},
    )
    r["build_s"] = elapsed(
        [
            compiler,
            "-std=c++17",
            "-O2",
            "-pthread",
            "-I",
            includes,
            source,
            *libs.values(),
            "-ldl",
            "-o",
            binary,
        ],
        env,
        out / "build.log",
        60,
    )
    r["binary_sha256"] = digest(binary.read_bytes())
    r["arms"] = {}
    for arm in check["ARMS"]:
        root = out / arm
        log = out / (arm + ".log")
        wall = elapsed([binary, arm, root], env, log, 30)
        providers = {}
        journal = []
        for line in log.read_text().splitlines():
            if line.startswith("PROVIDER "):
                _, name, path = line.split(" ", 2)
                providers[name] = Path(path)
            elif line != "PROJECTIONS 3":
                journal.append(line)
        need(
            log.read_text().splitlines().count("PROJECTIONS 3") == 1
            and providers
            == {
                "ggml_backend_cpu_init": libs["libggml-cpu.so.0"],
                "ggml_backend_tensor_set": libs["libggml-base.so.0"],
            },
            "native graph/provider",
        )
        r["arms"][arm] = {"wall_s": wall, "journal": journal}
    old = (out / "old/out.f32").read_bytes()
    new = (out / "new/out.f32").read_bytes()
    for arm, arm_receipt in r["arms"].items():
        root = out / arm
        result = check["verify_arm"](
            arm,
            (root / "slots.mxfp4").read_bytes(),
            load_optional(root / "bank.mxfp4"),
            (root / "out.f32").read_bytes(),
            load_optional(root / "token.f32"),
            arm_receipt["journal"],
            old,
            new,
        )
        arm_receipt.update(result)
    need(
        all(digest(p.read_bytes()) == r["cpu_libraries"][n] for n, p in libs.items()),
        "unchanged libraries",
    )
    r.update(
        status="PASS_CPU_OPERATOR_ONLY",
        gpu="NOT_RUN",
        model_forwards=0,
        peak_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "map", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = {}
    try:
        execute(a, out, r)
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    with (out / "receipt.json").open("x") as f:
        json.dump(r, f, allow_nan=False, indent=2, sort_keys=True)
        f.write("\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
