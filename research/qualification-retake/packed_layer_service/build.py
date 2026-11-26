"""Rebuild the qualified C291 layouts with the bounded service-only timing client."""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_BUILD = "a781699f893a8b323c0879578e4f61f27c64423dfeaba6559c43b81e466f0e2a"
CRYPTO_SHA = "695648ac8dc5e6a2b70e5e72399940de0f84bf24fddb7dd18949ba40bc575c72"
WRAP = (
    "pread",
    "ggml_backend_tensor_set",
    "_ZNSt18condition_variable10notify_oneEv",
    "_ZNSt18condition_variable10notify_allEv",
    "_ZNSt18condition_variable4waitERSt11unique_lockISt5mutexE",
)
sys.dont_write_bytecode = True


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def build(args, receipt):
    repo, out, libs = (p.resolve() for p in (args.repo, args.new_output_dir, args.libs))
    prev = repo / "research/qualification-retake/packed_real_layer/build.py"
    need(sha(prev) == BASE_BUILD, "C291 layer build changed")
    spec = importlib.util.spec_from_file_location("qualified_layer_build", prev)
    layer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layer)
    worker = layer.trusted_worker(repo)
    need(not worker.git(repo, "status", "--porcelain"), "measurement tree dirty")
    patch = repo / "research/qualification-retake/packed_worker/arena.patch"
    crypto = Path("/usr/lib64/libcrypto.so.3").resolve()
    need(sha(patch) == layer.PATCH and sha(crypto) == CRYPTO_SHA, "worker or crypto changed")
    need(all(sha(libs / n) == h for n, h in layer.LIBS.items()), "GGML provider mismatch")
    receipt.update(
        commit=worker.git(repo, "rev-parse", "HEAD").decode().strip(),
        worker_commit=worker.PIN,
        worker_tree=worker.TREE,
        patch_sha256=layer.PATCH,
        libs=layer.LIBS,
        crypto_sha256=CRYPTO_SHA,
        wrappers=list(WRAP),
        compiler_sha256=sha(Path("/usr/bin/g++").resolve()),
        native_sources={n: sha(HERE / n) for n in ("build.py", "service.cpp")},
        executables={},
    )
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": str(libs)}

    def checked(argv, label):
        with (out / (label + ".log")).open("xb") as log:
            subprocess.run(
                argv, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=True
            )

    for mode in ("dense", "arena"):
        src = out / (mode + "-src")
        worker.extract(args.backend.resolve(), src)
        if mode == "arena":
            receipt["patched_files"] = worker.apply_runtime(patch, src, checked)
        binary = out / (mode + "-service")
        checked(
            [
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
                *["-I" + str(src / d) for d in ("src", "include", "ggml/include")],
                HERE / "service.cpp",
                *[src / "src" / f for f in worker.BUILD_INPUTS],
                "-Wl,--gc-sections",
                *["-Wl,--wrap=" + s for s in WRAP],
                *[libs / n for n in layer.LIBS],
                crypto,
                "-ldl",
                "-o",
                binary,
            ],
            "build-" + mode,
        )
        checked(["/usr/bin/ldd", binary], "loader-" + mode)
        deps = (out / ("loader-" + mode + ".log")).read_text()
        need(
            not any(
                s in deps for s in ("not found", "libggml-cuda", "libcuda", "libllama", "libcudart")
            ),
            "unexpected mapping",
        )
        for name, physical in [(k.rsplit(".", 2)[0], libs / k) for k in layer.LIBS] + [
            ("libcrypto.so.3", crypto)
        ]:
            matches = [
                e.split()[2] for e in deps.splitlines() if e.strip().startswith(name + " => ")
            ]
            need(
                len(matches) == 1 and Path(matches[0]).samefile(physical),
                "dynamic provider mismatch",
            )
        checked([binary, "--self-test"], "link-test-" + mode)
        need(
            (out / ("link-test-" + mode + ".log")).read_text().strip()
            == "PASS_C291_SERVICE_CV_LINK",
            "CV hooks unreachable",
        )
        receipt["executables"][binary.name] = sha(binary)
    receipt["status"] = "PASS_C291_FIVE_MISS_SERVICE_BUILD"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "backend", "libs", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(exist_ok=False)
    receipt = {"status": "FAIL_PRESERVED"}
    try:
        build(args, receipt)
    except Exception as e:
        receipt["error_type"] = type(e).__name__
        receipt["reason"] = str(e) if isinstance(e, ValueError) else "see private build log"
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, allow_nan=False) + "\n"
    )
    print(receipt["status"])
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    sys.exit(main())
