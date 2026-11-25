"""Rebuild one C269 CPU object in private and qualify the synthetic GGML graphs."""

import argparse
import hashlib
import json
import os
import resource
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from kernel import materialize

HERE = Path(__file__).resolve().parent
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
SOURCE = Path("ggml/src/ggml-cpu/ggml-cpu.c")
OBJECT = "ggml/src/CMakeFiles/ggml-cpu.dir/ggml-cpu/ggml-cpu.c.o"
CPU = "libggml-cpu.so.0.15.3"
BASE = "libggml-base.so.0.15.3"
TARGET = "bin/" + CPU
CPU_SHA = "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313"
BASE_SHA = "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539"
HARNESS = "c5bdbbbd690758023535a75a74869584143941ea75ab988e34579c85c4efc0bf"
HARNESS_RECEIPT = "37f7ceec65cab37640dbf4b5b1f48bec19165d097a84adbfb956a01ea7db1f13"
LINK_SHA = "e4be5ace9a0650ba98168e2b030d7950d43287624b1aa8520cb44605a2d28830"
INPUTS_SHA = "1c1be0b7c51ac78c820666b5484f173f6f014589061a2333f9e87d1eaff07aa8"
TOOLS = {
    "/usr/bin/gcc-15": "14243f9ecbf08dfb3490eaca0c832055b8934ca0883f507cf951a5107fe7b36f",
    "/usr/bin/g++-15": "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a",
    "/usr/bin/ld": "eccfdb2b11bcae1ca6e2915a40db609299f46d7def305dab744c0da0aaf54370",
    "/usr/bin/ninja": "0108fce2fda36061dd0b1b3c35ba14f28a5034abfbaee54799abcfc9fff29826",
    "/lib64/ld-linux-x86-64.so.2": (
        "4e5d39355699e90fa29313d3100e82af4a23290028c58c364d6a249ef6a78e5e"
    ),
}
CMAKE = {
    "build.ninja": "34c0ff3554a9637e3829131a641ff799fc04b94051d9c71999a95eacb6381d21",
    "CMakeFiles/rules.ninja": "049f8d12e3b9f38440a4169cbf76753d3acd78cdd2dab53ac4bfe7ed731842ff",
    "compile_commands.json": "2582285bc2b5b7af91570e5c9f4ca326c34bdc6da2ec7aef53ce87c393f6fb6c",
}
DEPS = {"bin/" + BASE, "/usr/lib/gcc/x86_64-redhat-linux/15/libgomp.so", "/usr/lib64/libpthread.a"}
ENV = {"LC_ALL": "C", "PATH": "/usr/bin:/bin", "CUDA_VISIBLE_DEVICES": ""}


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def sha_text(data):
    return hashlib.sha256(data.encode()).hexdigest()


def manifest(inputs):
    return sha_text(json.dumps(inputs, separators=(",", ":"), sort_keys=True))


def text(command, cwd=None, env=ENV):
    return subprocess.check_output(command, cwd=cwd, env=env, timeout=30, text=True)


def git(directory, *args):
    options = ["--no-optional-locks", "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
    return text(["/usr/bin/git", *options, "-C", directory, *args]).strip()


def replace(args, old, new):
    need(args.count(old) == 1, "command token absent or repeated: " + old)
    args[args.index(old)] = str(new)


def linker(command, out, obj):
    need(sha_text(command) == LINK_SHA, "unknown CMake link")
    args = shlex.split(command)
    need(args[:2] == [":", "&&"] and args[-2:] == ["&&", ":"], "link shell")
    args = args[2:-2]
    need(args[0] == "/usr/bin/g++-15" and "-shared" in args, "CMake linker")
    replace(args, TARGET, out / CPU)
    replace(args, OBJECT, obj)
    dep = "-Wl,--dependency-file="
    replace(args, dep + "ggml/src/CMakeFiles/ggml-cpu.dir/link.d", dep + str(out / "link.d"))
    return args


def commands(args, cwd, out, name, result, env=ENV):
    args = list(map(str, args))
    result["commands"][name] = args
    with (out / (name + ".log")).open("xb") as log:
        subprocess.run(
            args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120
        )


def loader(executable, env, providers):
    lines = text(["/lib64/ld-linux-x86-64.so.2", "--list", executable], env=env).splitlines()
    actual = {}
    for line in lines:
        fields = line.split()
        need(
            not any(s in line for s in ("not found", "libcuda", "libnvidia", "libggml-cuda")),
            "unexpected provider",
        )
        if fields and fields[0].startswith("libggml"):
            need(len(fields) >= 3 and fields[1] == "=>" and fields[0] not in actual, "loader map")
            actual[fields[0]] = Path(fields[2]).resolve(strict=True)
    need(actual == providers, "wrong GGML provider")
    return {k: {"path": str(p), "sha256": sha(p)} for k, p in actual.items()}


def validate_graph(mode, stdout, data, gold):
    need(mode in ("r0", "off", "on"), "mode")
    skipped = 24 if mode == "on" else 0
    line = f"PASS_PARKED_MMID_GRAPH cases=192 skipped={skipped} rows_bytes=98304\n"
    need(stdout == line and len(data) == 98304, "synthetic coverage")
    need(gold is None or data == gold, "different synthetic output")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def build(a, r):
    root = a.new_output_dir.resolve()
    repo, backend = a.repo.resolve(), a.backend.resolve()
    b = backend / "build-c269-cuda"
    libs = b / "bin"
    need(HERE == repo / "research/qualification-retake/parked_mmid", "measurement checkout")
    need(not git(repo, "status", "--porcelain"), "uncommitted measurement checkout")
    need(
        git(backend, "rev-parse", "HEAD") == PIN
        and not git(backend, "status", "--porcelain", "--", "ggml"),
        "unverified GGML tree",
    )
    r.update(
        commit=git(repo, "rev-parse", "HEAD"),
        tree=git(repo, "rev-parse", "HEAD^{tree}"),
        backend_commit=PIN,
        backend_tree=git(backend, "rev-parse", "HEAD^{tree}"),
        sources={
            k: sha(HERE / k)
            for k in ("build.py", "kernel.py", "test_kernel_graph.cpp", "protocol.md")
        },
    )
    for base, pins in ((Path("/"), TOOLS), (b, CMAKE), (libs, {CPU: CPU_SHA, BASE: BASE_SHA})):
        need(all(sha(base / name) == digest for name, digest in pins.items()), "toolchain/DSO pin")
    suffix = a.suffix_build.resolve()
    need(
        sha(suffix / "receipt.json") == HARNESS_RECEIPT and sha(suffix / "suffix-layer") == HARNESS,
        "original harness",
    )
    r.update(
        toolchain=TOOLS,
        cmake=CMAKE,
        original_cpu_sha256=CPU_SHA,
        base_sha256=BASE_SHA,
        suffix_build_receipt_sha256=HARNESS_RECEIPT,
    )
    shutil.copy2(suffix / "suffix-layer", root / "suffix-layer")
    r["binary_sha256"] = sha(root / "suffix-layer")
    original = backend / SOURCE
    link = text(["/usr/bin/ninja", "-C", b, "-t", "commands", TARGET]).splitlines()[-1]
    inputs = {s: sha(b / s) for s in shlex.split(link) if s.endswith(".o") or s in DEPS}
    need(
        len(inputs) == 18 and manifest(inputs) == INPUTS_SHA and sha_text(link) == LINK_SHA,
        "CMake linker inputs",
    )
    r.update(link_inputs=inputs, link_inputs_sha256=INPUTS_SHA, original_link_command=link)
    db = json.loads((b / "compile_commands.json").read_text())
    (row,) = [x for x in db if Path(x["file"]).name == original.name]
    need(Path(row["directory"]).samefile(b) and Path(row["file"]).samefile(original), "TU path")
    cc = shlex.split(row["command"])
    need(
        cc[0] == "/usr/bin/gcc-15"
        and {"-O3", "-fPIC", "-DTESY_C47_CPU_SKIP_PARKED", "-march=native", "-std=gnu11"}.issubset(
            cc
        ),
        "C269 flags",
    )
    cand = root / "candidate"
    cand.mkdir()
    new = cand / original.name
    obj = cand / original.with_suffix(".c.o").name
    r["source_sha256"] = sha(original)
    r["generated_source_sha256"] = materialize(original, new)
    r["original_compile_command"] = row["command"]
    replace(cc, OBJECT, obj)
    replace(cc, row["file"], new)
    cc.extend(
        [
            "-iquote",
            str(Path(row["file"]).parent),
            f"-fmacro-prefix-map={cand}={Path(row['file']).parent}",
        ]
    )
    commands(cc, b, root, "compile", r)
    commands(linker(link, cand, obj), b, root, "link", r)
    r["candidate_cpu_sha256"] = sha(cand / CPU)
    need(r["candidate_cpu_sha256"] != CPU_SHA, "candidate equals original")
    (cand / "libggml-cpu.so.0").symlink_to(CPU)
    gold = root / "relink"
    gold.mkdir()
    commands(linker(link, gold, OBJECT), b, root, "reference-relink", r)
    r["reference_relink_sha256"] = sha(gold / CPU)
    r["reference_relink_identical"] = r["reference_relink_sha256"] == CPU_SHA
    need(
        all(sha(b / p) == expected for p, expected in inputs.items()), "original link input changed"
    )
    exe = root / "test-kernel-graph"
    commands(
        [
            "/usr/bin/g++-15",
            "-O2",
            "-std=c++17",
            "-pthread",
            "-I",
            backend / "ggml/include",
            HERE / "test_kernel_graph.cpp",
            libs / CPU,
            libs / BASE,
            "-o",
            exe,
        ],
        root,
        root,
        "fixture-compile",
        r,
    )
    r["fixture_executable_sha256"] = sha(exe)
    r.update(fixture_stdout={}, synthetic_rows={}, resolved_providers={})
    original_rows = None
    for mode in ("r0", "off", "on"):
        cpu = libs if mode == "r0" else cand
        env = ENV | {
            "LD_LIBRARY_PATH": f"{cpu}:{libs}",
            "OMP_NUM_THREADS": "8",
            "TESY_CPU_WAVE_SKIP_PARKED": "1",
        }
        if mode != "r0":
            env["TESY_CPU_MMX_ALL_PARKED"] = str(int(mode == "on"))
        expected = {
            "libggml-cpu.so.0": (cpu / CPU).resolve(),
            "libggml-base.so.0": (libs / BASE).resolve(),
        }
        r["resolved_providers"][mode] = {
            x.name: loader(x, env, expected) for x in (exe, root / "suffix-layer")
        }
        dest = root / ("fixture-" + mode + ".bin")
        commands([exe, mode, dest], root, root, "test-" + mode, r, env)
        stdout = (root / ("test-" + mode + ".log")).read_text()
        r["fixture_stdout"][mode] = stdout
        data = dest.read_bytes()
        r["synthetic_rows"][mode] = validate_graph(mode, stdout, data, original_rows)
        if mode == "r0":
            original_rows = data
    r["numerical_fixture_sha256"] = r["synthetic_rows"]["r0"]["sha256"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "backend", "suffix-build", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    start = time.monotonic()
    r = {"status": "FAIL_PRESERVED", "commands": {}, "model_forwards": 0, "gpu_compute": False}
    try:
        build(a, r)
        r["status"] = "PASS_C269_PARKED_MMID_BUILD"
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    r["elapsed_s"] = time.monotonic() - start
    r["max_child_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    dest = a.new_output_dir / "receipt.json"
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(r, indent=2) + "\n")
    tmp.rename(dest)
    print(r["status"], sha(dest))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
