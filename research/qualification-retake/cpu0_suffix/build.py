"""Build only the DENSE C291 tile client from the frozen packed_real_layer inputs."""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PRIOR = Path("research/qualification-retake/packed_real_layer")
BUILD = "a781699f893a8b323c0879578e4f61f27c64423dfeaba6559c43b81e466f0e2a"
LAYER = "e1240b2981b49163efa9156ac9bc15f7865770f7c1016e26a8ea61ad9d97c14a"
PROTOCOL = "c3a6101ae9c1c058b0a8488a7b4c4e18b8e99f093cce00fb606a271ce48cf155"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def need(condition, why):
    if not condition:
        raise ValueError(why)


def apply_layer(original, dest, patch):
    need(digest(original) == LAYER, "historical tile changed")
    shutil.copyfile(original, dest)
    subprocess.run(
        ["/usr/bin/patch", "--fuzz=0", "--batch", "--forward", str(dest), str(patch)],
        check=True,
        capture_output=True,
        timeout=5,
    )
    body = dest.read_text()
    for forbidden in ("set_eval_callback", '"slot_witness.h"', "__wrap_", "audit="):
        need(forbidden not in body, "active graph or I/O observer")
    need(
        body.count("marked && w==0 ? timed_wave_ids : llama_moe_stream_wave_ids") == 1,
        "wave-zero-only hook",
    )
    return digest(dest)


def build(a, result):
    root = a.new_output_dir.resolve()
    project, libs = a.repo.resolve(), a.libs.resolve()
    git = ["/usr/bin/git", "--no-optional-locks", "-C", str(project)]

    def revision(*args):
        return subprocess.check_output([*git, *args], text=True, timeout=15).strip()

    need(HERE == project / PRIOR.parent / "cpu0_suffix", "builder must be in measured checkout")
    need(not revision("status", "--porcelain"), "uncommitted measurement tree")
    result.update(commit=revision("rev-parse", "HEAD"), tree=revision("rev-parse", "HEAD^{tree}"))
    old = project / PRIOR
    need(
        digest(old / "build.py") == BUILD and digest(HERE / "protocol.md") == PROTOCOL,
        "frozen sources",
    )
    spec = importlib.util.spec_from_file_location("c291_historical_builder", old / "build.py")
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    worker = prior.trusted_worker(project)
    need(all(digest(libs / name) == sha for name, sha in prior.LIBS.items()), "CPU/base mismatch")
    src = root / "src"
    inputs = worker.extract(a.backend.resolve(), src)
    helper = root / "pairs-finish.inc"
    helper.write_text(prior.functions(project / "tools/block_expert_reuse_operator.cpp"))
    layer = root / "layer.cpp"
    result.update(
        layer_original_sha256=LAYER,
        layer_patched_sha256=apply_layer(old / "layer.cpp", layer, HERE / "operator.patch"),
        protocol_sha256=PROTOCOL,
        historical_builder_sha256=BUILD,
        libs=prior.LIBS,
        worker_commit=worker.PIN,
        worker_tree=worker.TREE,
        worker_input_manifest=inputs,
        compiler_sha256=digest(Path("/usr/bin/g++").resolve()),
        helper_sha256=digest(helper),
        sources={
            name: digest(HERE / name) for name in ("build.py", "operator.patch", "suffix-clock.h")
        },
    )
    exe = root / "suffix-layer"
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": str(libs)}

    def run(argv, label):
        with (root / (label + ".log")).open("xb") as log:
            subprocess.run(
                argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180
            )
        return (root / (label + ".log")).read_text()

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
        "-I" + str(HERE),
        *["-I" + str(src / p) for p in ("src", "include", "ggml/include")],
        layer,
        *[src / "src" / name for name in worker.BUILD_INPUTS],
        "-Wl,--gc-sections",
        *[libs / name for name in prior.LIBS],
        "-ldl",
        "-o",
        exe,
    ]
    run(cmd, "compile")
    linked = run(["/usr/bin/ldd", exe], "link")
    need(
        not any(
            s in linked for s in ("not found", "libcuda", "libnvidia", "libllama", "libggml-cuda")
        ),
        "unexpected provider",
    )
    for name in prior.LIBS:
        matches = [
            line.split()[2]
            for line in linked.splitlines()
            if line.strip().startswith(name.rsplit(".", 2)[0] + " => ")
        ]
        need(len(matches) == 1 and Path(matches[0]).samefile(libs / name), "provider resolution")
    symbols = run(["/usr/bin/nm", "-C", exe], "symbols")
    need(
        "timed_wave_ids(" in symbols and "llama_moe_stream_wave_ids(" in symbols, "missing callback"
    )
    need(
        not any(
            symbol in symbols
            for symbol in (
                "__wrap_pread",
                "__wrap_ggml_backend_tensor_set",
                "ggml_backend_sched_set_eval_callback",
            )
        ),
        "observer linked",
    )
    need(
        run([exe, "--self-test"], "self-test").strip() == "PASS_C291_SUFFIX_COUNTEREXAMPLES",
        "boundary controls",
    )
    result.update(status="PASS_C291_CPU0_SUFFIX_BUILD", binary_sha256=digest(exe))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "backend", "libs", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(exist_ok=False)
    result = {"status": "FAIL_PRESERVED"}
    try:
        build(a, result)
    except Exception as error:
        result.update(
            error_type=type(error).__name__,
            reason=str(error) if isinstance(error, ValueError) else "see private build log",
        )
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
