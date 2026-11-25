"""Build one CPU-only test client using the authenticated C291 worker and C266 graph helpers."""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q = next(p for p in HERE.parents if p.name == "qualification-retake")
LAYER = Q / "packed_real_layer"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load(p):
    spec = importlib.util.spec_from_file_location(p.parent.name + p.stem, p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(args, r):
    root = args.new_output_dir.resolve()
    repo = Q.parents[1]
    backend = args.backend.resolve()
    libs = args.libs.resolve()
    original = LAYER / "build.py"
    if sha(original) != "a781699f893a8b323c0879578e4f61f27c64423dfeaba6559c43b81e466f0e2a":
        raise ValueError("canonical build module")
    old = load(original)
    worker = old.trusted_worker(repo)
    old.need(not worker.git(repo, "status", "--porcelain"), "dirty build checkout")
    commit = worker.git(repo, "rev-parse", "HEAD").decode().strip()
    old.need(all(sha(libs / n) == h for n, h in old.LIBS.items()), "CPU/base DSOs")
    source = root / "c291"
    r["blobs"] = worker.extract(backend, source)
    load(HERE.parent / "overlay.py").materialize(source)
    (root / "pairs-finish.inc").write_text(
        old.functions(repo / "tools/block_expert_reuse_operator.cpp")
    )
    load(HERE / "source.py").generate(LAYER, HERE, root)
    exe = root / "alias-layer"
    cmd = [
        "/usr/bin/g++",
        "-std=c++17",
        "-O1",
        "-g0",
        "-pthread",
        "-fPIC",
        "-pie",
        "-fno-plt",
        "-ffunction-sections",
        "-fdata-sections",
        "-DTESY_C47_CPU_SKIP_PARKED",
        "-DTESY_STORE_TESTING",
        "-I" + str(root),
        "-I" + str(HERE),
        "-I" + str(HERE.parent),
    ]
    cmd += ["-I" + str(source / d) for d in ("src", "include", "ggml/include")]
    cmd += [
        root / "layer.cpp",
        *(source / "src" / n for n in worker.BUILD_INPUTS),
        "-Wl,--gc-sections",
        *(libs / n for n in old.LIBS),
        "-ldl",
        "-o",
        exe,
    ]
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LD_LIBRARY_PATH": str(libs),
        "CUDA_VISIBLE_DEVICES": "",
    }
    r.update(
        commit=commit,
        worker_commit=worker.PIN,
        worker_tree=worker.TREE,
        libs=old.LIBS,
        source_sha256={
            n: sha(HERE / n)
            for n in ("protocol.md", "source.py", "build.py", "real.h", "layer.inc")
        },
        shared_sha256={
            str(p.relative_to(repo)): sha(p)
            for p in (
                original,
                LAYER / "layer.cpp",
                LAYER / "slot_witness.h",
                HERE.parent / "overlay.py",
                HERE.parent / "lease.h",
            )
        },
        generated_sha256={
            n: sha(root / n)
            for n in ("pairs-finish.inc", "layer.cpp", "c291/src/llama-moe-stream.cpp")
        },
        compiler_sha256=sha(Path("/usr/bin/g++")),
    )
    with (root / "compiler.log").open("xb") as f:
        subprocess.run(cmd, check=True, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=120)
    linked = subprocess.check_output(["/usr/bin/ldd", exe], env=env, timeout=10, text=True)
    (root / "loader.log").write_text(linked)
    old.need(
        "not found" not in linked
        and all(x not in linked for x in ("libcuda", "libcudart", "libggml-cuda", "libllama")),
        "unexpected loader",
    )
    for n in old.LIBS:
        soname = n.rsplit(".", 2)[0]
        line = next(i.strip() for i in linked.splitlines() if i.strip().startswith(soname + " => "))
        old.need(Path(line.split()[2]).samefile(libs / n), "CPU/base origin")
    r.update(status="PASS_C291_ALIAS_REAL_LAYER_BUILD", executables={exe.name: sha(exe)})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("backend", "libs", "new-output-dir"):
        ap.add_argument("--" + key, type=Path, required=True)
    args = ap.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    r = {"status": "FAIL_PRESERVED"}
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
        build(args, r)
    except Exception as error:
        r["error"] = f"{type(error).__name__}: {error}"
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(r, sort_keys=True, indent=2) + "\n"
    )
    print(r["status"], r.get("error", ""))
    sys.exit(r["status"] == "FAIL_PRESERVED")
