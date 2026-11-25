"""Build the C291 CPU worker and the shape-one GGML gate from pinned source."""

import argparse
import importlib.util
import json
import os
import resource
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q = next(p for p in HERE.parents if p.name == "qualification-retake")
ROOT = Q.parents[1]
CRYPTO = "695648ac8dc5e6a2b70e5e72399940de0f84bf24fddb7dd18949ba40bc575c72"


def load(path):
    spec = importlib.util.spec_from_file_location(path.parent.name + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(args, r):
    prev = load(HERE.parent / "build.py")
    sha = prev.sha
    old = load(Q / "packed_real_layer/build.py")
    worker = old.trusted_worker(ROOT)
    need = old.need
    out = args.new_output_dir.resolve()
    libs = args.libs.resolve()
    crypto = Path("/usr/lib64/libcrypto.so.3").resolve()
    need(not worker.git(ROOT, "status", "--porcelain"), "clean checkout")
    need(all(sha(libs / n) == v for n, v in old.LIBS.items()) and sha(crypto) == CRYPTO, "runtime")
    private = out / "c291"
    r["source_blobs"] = worker.extract(args.backend.resolve(), private)
    overlay = HERE.parent.parent / "overlay.py"
    load(overlay).materialize(private)
    source = private / "src/llama-moe-stream.cpp"
    text = source.read_text()
    start = (
        "int32_t llama_moe_stream::pick_victim_locked(llama_moe_stream_layer & sl, "
        "const uint8_t * keep) const {\n    int32_t v = -1;"
    )
    need(text.count(start) == 1, "declared eligibility site")
    text = text.replace(
        start,
        start
        + """
    extern int decode_allowed_slot();
    const int constraint = decode_allowed_slot();
    uint8_t protected_slots[40];
    if (constraint >= 0) {
        GGML_ASSERT(sl.n_slots == 40 && constraint == 14);
        for (int s=0; s<40; ++s) protected_slots[s] = s!=constraint || (keep && keep[s]);
        keep = protected_slots;
    }""",
    )
    source.write_text(text)
    (out / "pairs-finish.inc").write_text(
        old.functions(ROOT / "tools/block_expert_reuse_operator.cpp")
    )
    exe = out / "decode-layer"
    argv = [
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
        "-I" + str(out),
        "-I" + str(HERE.parent.parent),
    ]
    argv += ["-I" + str(private / d) for d in ("src", "include", "ggml/include")]
    argv += [
        HERE / "decode.cpp",
        *(private / "src" / n for n in worker.BUILD_INPUTS),
        "-Wl,--gc-sections",
        *(libs / n for n in old.LIBS),
        crypto,
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
        commit=worker.git(ROOT, "rev-parse", "HEAD").decode().strip(),
        worker_commit=worker.PIN,
        worker_tree=worker.TREE,
        libs=old.LIBS,
        crypto_sha256=CRYPTO,
        source_sha256={n: sha(HERE / n) for n in ("build.py", "decode.cpp", "protocol.md")},
        shared_sha256={
            str(p.relative_to(ROOT)): sha(p)
            for p in (
                HERE.parent / "build.py",
                overlay,
                overlay.with_name("lease.h"),
                Q / "packed_real_layer/build.py",
            )
        },
        generated_worker_sha256=sha(source),
        pairs_finish_sha256=sha(out / "pairs-finish.inc"),
        compiler_sha256=sha(Path("/usr/bin/g++")),
    )
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(argv, check=True, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    linked = subprocess.check_output(["/usr/bin/ldd", exe], env=env, text=True, timeout=10)
    (out / "loader.log").write_text(linked)
    need(
        all(s not in linked for s in ("not found", "libcuda", "libggml-cuda", "libllama")), "loader"
    )
    for n in old.LIBS:
        so = n.rsplit(".", 2)[0]
        line = next(i for i in linked.splitlines() if i.strip().startswith(so + " => "))
        need(Path(line.split()[2]).samefile(libs / n), "provider path")
    r.update(status="PASS_C291_CPU0_DECODE_BUILD", executables={exe.name: sha(exe)})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("backend", "libs", "new-output-dir"):
        ap.add_argument("--" + k, type=Path, required=True)
    args = ap.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    report = {"status": "FAIL_PRESERVED"}
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
        build(args, report)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(report["status"], report.get("error", ""))
    sys.exit(report["status"] == "FAIL_PRESERVED")
