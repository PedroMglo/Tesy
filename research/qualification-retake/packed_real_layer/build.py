"""Build the two pinned local worker clients. No loader, weights, or accelerator."""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORKER_RUN = "67523bc7c44d6cf1182b45008e7414d160254b62a64c1ffe142fe934ab65509e"
PATCH = "636a88a0ec71a4fc78608145e884a06132c67f45c9f23f56a9fca135f9f47684"
OPERATOR = "4ceb573da1196b7612af8c1aa4ab65a4e14f9bfe966d77303e3b6f71de32ad3e"
LIBS = {
    "libggml-cpu.so.0.15.3": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
    "libggml-base.so.0.15.3": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def functions(source):
    need(sha(source) == OPERATOR, "canonical pairs/reduction source changed")
    body = source.read_text()
    begin = body.index("ggml_tensor * pairs(")
    end = body.index("void build(graph_plan", begin)
    result = body[begin:end]
    need(
        result.count("ggml_mul_mat_id(") == 3 and result.count("ggml_add_id(") == 3,
        "three canonical projections and biases",
    )
    need(
        result.count("ggml_swiglu_oai(") == 1 and result.count("ggml_view_2d(") == 1,
        "activation and ordered reduction",
    )
    return result


def trusted_worker(project):
    path = project / "research/qualification-retake/packed_worker/run.py"
    need(sha(path) == WORKER_RUN, "worker source extraction or pinned build changed")
    spec = importlib.util.spec_from_file_location("packed_worker_build_source", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(args, receipt):
    root, repo, libs = (
        args.new_output_dir.resolve(),
        args.repo.resolve(),
        args.libs.resolve(),
    )
    head = subprocess.check_output(
        ["git", "-C", repo, "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(
        [
            "git",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            repo,
            "status",
            "--porcelain",
        ]
    )
    need(not dirty, "measurement worktree is dirty")
    need(
        all(sha(libs / name) == digest for name, digest in LIBS.items()),
        "numeric CPU/base runtime mismatch",
    )
    worker = trusted_worker(repo)
    patch = repo / "research/qualification-retake/packed_worker/arena.patch"
    need(sha(patch) == PATCH, "worker arena patch changed")
    helper = root / "pairs-finish.inc"
    helper.write_text(functions(repo / "tools/block_expert_reuse_operator.cpp"))
    receipt.update(
        commit=head,
        worker_commit=worker.PIN,
        worker_tree=worker.TREE,
        helper_source_sha256=OPERATOR,
        extracted_helpers_sha256=sha(helper),
        patch_sha256=PATCH,
        libs=LIBS,
        native_sources={
            name: sha(HERE / name)
            for name in ["layer.cpp", "slot_witness.h", "build.py"]
        },
        compiler_sha256=sha(Path("/usr/bin/g++").resolve()),
        executables={},
    )
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": str(libs)}

    def checked(argv, name):
        with (root / (name + ".log")).open("xb") as log:
            subprocess.run(
                argv,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                check=True,
                timeout=180,
            )

    for mode in ["dense", "arena"]:
        private = root / (mode + "-src")
        worker.extract(args.backend.resolve(), private)
        if mode == "arena":
            receipt["patched_files"] = worker.apply_runtime(patch, private, checked)
        binary = root / (mode + "-layer")
        cmd = [
            "/usr/bin/g++",
            "-std=c++17",
            "-O0",
            "-g0",
            "-Wall",
            "-Wextra",
            "-pthread",
            "-fPIC",
            "-pie",
            "-fno-plt",
            "-ffunction-sections",
            "-fdata-sections",
            "-DTESY_C47_CPU_SKIP_PARKED",
            "-DTESY_STORE_TESTING",
            "-I" + str(root),
            *["-I" + str(private / d) for d in ("src", "include", "ggml/include")],
            HERE / "layer.cpp",
            *[private / "src" / name for name in worker.BUILD_INPUTS],
            "-Wl,--gc-sections",
            "-Wl,--wrap=pread",
            "-Wl,--wrap=ggml_backend_tensor_set",
            *[libs / name for name in LIBS],
            "-ldl",
            "-o",
            binary,
        ]
        checked(cmd, "compile-" + mode)
        checked(["/usr/bin/ldd", binary], "link-" + mode)
        linked = (root / ("link-" + mode + ".log")).read_text()
        need(
            "not found" not in linked
            and not any(
                x in linked
                for x in ("libcuda", "libcudart", "libggml-cuda", "libllama")
            ),
            "unexpected provider",
        )
        for name in LIBS:
            soname = name.rsplit(".", 2)[0]
            line = next(
                (
                    item
                    for item in linked.splitlines()
                    if item.strip().startswith(soname + " => ")
                ),
                None,
            )
            need(
                line is not None and Path(line.split()[2]).samefile(libs / name),
                "loader resolved wrong runtime",
            )
        checked([binary, "--self-test"], "counterexample-" + mode)
        need(
            (root / ("counterexample-" + mode + ".log")).read_text().strip()
            == "PASS_C291_TILE_COUNTEREXAMPLES",
            "missing negative controls",
        )
        receipt["executables"][binary.name] = sha(binary)
    receipt["status"] = "PASS_C291_CPU_TILE_BUILD"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("repo", "backend", "libs", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(exist_ok=False)
    receipt = {"status": "FAIL_PRESERVED"}
    try:
        build(args, receipt)
    except Exception as exc:
        receipt["error_type"] = type(exc).__name__
        receipt["reason"] = (
            str(exc) if isinstance(exc, ValueError) else "see private build log"
        )
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, allow_nan=False) + "\n"
    )
    print(receipt["status"])
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    sys.exit(main())
