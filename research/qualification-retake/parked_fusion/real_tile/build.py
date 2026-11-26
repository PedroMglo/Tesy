"""Build the original DENSE CPU0 client with an out-of-graph counter receipt."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = Path("research/qualification-retake")
REF = "37f7ceec65cab37640dbf4b5b1f48bec19165d097a84adbfb956a01ea7db1f13"
LAYER = "8890faf76dacc30ff3eb1e81843a75ec0361ea02817af98b98da4f39a97967b3"
PATCHED = "1be86ed2cd190b4afaf32efc4e534bc27dce6bd3146637606abefb3a962232ae"
BUILD_INPUTS = ("llama-moe-stream.cpp", "llama-impl.cpp", "llama-mmap.cpp")


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check(path, expected):
    need(path.is_file() and not path.is_symlink() and sha(path) == expected, "input " + path.name)


def build(a, result):
    repo, source, libs, out = (
        a.repo.resolve(strict=True),
        a.reference_build.resolve(strict=True),
        a.libs.resolve(strict=True),
        a.new_output_dir.resolve(strict=True),
    )
    git = ["/usr/bin/git", "--no-optional-locks", "-C", str(repo)]

    def revision(*args):
        return subprocess.check_output([*git, *args], text=True, timeout=15).strip()

    need(HERE == repo / QUAL / "parked_fusion/real_tile", "checkout")
    need(not revision("status", "--porcelain"), "dirty checkout")
    old = source / "receipt.json"
    check(old, REF)
    prior = json.loads(old.read_text())
    need(prior["status"] == "PASS_C291_CPU0_SUFFIX_BUILD", "historical client")
    original = source / "layer.cpp"
    check(original, LAYER)
    check(source / "suffix-layer", prior["binary_sha256"])
    check(source / "pairs-finish.inc", prior["helper_sha256"])
    clock = repo / QUAL / "cpu0_suffix"
    check(clock / "suffix-clock.h", prior["sources"]["suffix-clock.h"])
    cc = Path("/usr/bin/g++").resolve(strict=True)
    check(cc, prior["compiler_sha256"])
    private = source / "src"
    manifest = prior["worker_input_manifest"]
    # The reference receipt authenticates the complete extracted C291 tree.
    # Fresh copies exclude shadow headers beside the original generated source.
    guarded = out / "src"
    for name, item in manifest.items():
        rel = Path(name)
        need(not rel.is_absolute() and ".." not in rel.parts, "source path")
        src = private / rel
        check(src, item["sha256"])
        need(src.stat().st_size == item["bytes"], "C291 source size")
        dest = guarded / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        check(dest, item["sha256"])
    for name, ident in prior["libs"].items():
        check(libs / name, ident)
    layer = out / "layer.cpp"
    shutil.copyfile(original, layer)
    shutil.copyfile(source / "pairs-finish.inc", out / "pairs-finish.inc")
    shutil.copyfile(clock / "suffix-clock.h", out / "suffix-clock.h")
    check(out / "suffix-clock.h", prior["sources"]["suffix-clock.h"])
    check(out / "pairs-finish.inc", prior["helper_sha256"])
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": str(libs)}

    def run(argv, label):
        with (out / (label + ".log")).open("xb") as log:
            subprocess.run(
                argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180
            )
        return (out / (label + ".log")).read_text()

    result.update(
        original_build_sha256=REF,
        commit=revision("rev-parse", "HEAD"),
        tree=revision("rev-parse", "HEAD^{tree}"),
        sources={n: sha(HERE / n) for n in ("build.py", "observer.patch")},
        protocol_sha256=sha(HERE / "protocol.md"),
        original_client_sha256=prior["binary_sha256"],
        reference_layer_sha256=LAYER,
        worker_commit=prior["worker_commit"],
        worker_tree=prior["worker_tree"],
        worker_input_manifest=manifest,
        compiler_sha256=prior["compiler_sha256"],
        libs=prior["libs"],
        helpers_sha256=prior["helper_sha256"],
    )
    run(
        ["/usr/bin/patch", "--batch", "--forward", "--fuzz=0", layer, HERE / "observer.patch"],
        "patch",
    )
    check(layer, PATCHED)
    result["patched_layer_sha256"] = PATCHED
    exe = out / "suffix-layer"
    run(
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
            "-I" + str(out),
            *["-I" + str(guarded / d) for d in ("src", "include", "ggml/include")],
            layer,
            *[guarded / "src" / n for n in BUILD_INPUTS],
            "-Wl,--gc-sections",
            *[libs / n for n in prior["libs"]],
            "-ldl",
            "-o",
            exe,
        ],
        "compile",
    )
    linked = run(["/usr/bin/ldd", exe], "link")
    need(
        not any(
            x in linked for x in ("not found", "libcuda", "libnvidia", "libggml-cuda", "libllama")
        ),
        "unexpected dynamic provider",
    )
    for name in prior["libs"]:
        lines = [
            s for s in linked.splitlines() if s.strip().startswith(name.rsplit(".", 2)[0] + " => ")
        ]
        need(len(lines) == 1 and Path(lines[0].split()[2]).samefile(libs / name), "loader path")
    symbols = run(["/usr/bin/nm", "-C", exe], "symbols")
    need(
        not any(
            x in symbols
            for x in (
                "__wrap_pread",
                "__wrap_ggml_backend_tensor_set",
                "ggml_backend_sched_set_eval_callback",
                "tesy_parked_fusion_count",
            )
        ),
        "unexpected linked observer or embedded region counter",
    )
    need(
        run([exe, "--self-test"], "self-test").strip() == "PASS_C291_SUFFIX_COUNTEREXAMPLES",
        "historical negative controls",
    )
    result.update(binary_sha256=sha(exe), status="PASS_C291_FUSION_COUNTER_CLIENT_BUILD")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "reference-build", "libs", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(exist_ok=False)
    result = {"status": "FAIL_PRESERVED"}
    try:
        build(a, result)
    except Exception as exc:
        result.update(
            error_type=type(exc).__name__,
            reason=str(exc) if isinstance(exc, ValueError) else "see private build log",
        )
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
