"""Build a callback wrapper around the pinned CPU0 shape-one driver."""

import argparse
import hashlib
import json
import os
import resource
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[2]
ROOT = QUAL.parents[1]
DECODE = (
    QUAL
    / "phase_fd/integrated/t1_manager_bank/policy_snapshot/natural/cpu_alias"
    / "manager/real_layer/decode"
)
OLD = "b083a55c45c4ed02e8ceea74e8fe3c47ada92204cac5a8f995511e8741960f6d"
PROFILE = "529eaf868c442fb029cc4e71e0ea5af2e676300783b8635756b7e9b925ce0ae7"


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def git(*args):
    return subprocess.check_output(
        ["git", "--no-optional-locks", "-C", ROOT, *args], text=True
    ).strip()


def sealed(path, digest):
    check(path.is_file() and sha(path) == digest, "identity " + path.name)
    return path


def build(a, r):
    check(not git("status", "--porcelain"), "clean checkout")
    base = a.old_build.resolve()
    old = json.loads(sealed(base / "receipt.json", OLD).read_bytes())
    private = base / "c291"
    source_files = old["source_blobs"]
    check(
        {str(p.relative_to(private)) for p in private.rglob("*") if p.is_file()}
        == set(source_files),
        "C291 include closure",
    )
    for name, blob in source_files.items():
        expected = (
            old["generated_worker_sha256"] if name == "src/llama-moe-stream.cpp" else blob["sha256"]
        )
        sealed(private / name, expected)
    sealed(base / "pairs-finish.inc", old["pairs_finish_sha256"])
    sealed(base / "decode-layer", old["executables"]["decode-layer"])
    for name, digest in old["source_sha256"].items():
        sealed(DECODE / name, digest)
    for name, digest in old["shared_sha256"].items():
        sealed(ROOT / name, digest)
    sealed(DECODE / "profile.py", PROFILE)
    libs = a.libs.resolve()
    gxx = sealed(Path("/usr/bin/g++"), old["compiler_sha256"])
    crypto = sealed(Path("/usr/lib64/libcrypto.so.3").resolve(), old["crypto_sha256"])
    deps = [sealed(libs / n, h) for n, h in old["libs"].items()]
    out = a.new_output_dir.resolve()
    exe = out / "decode-layer"
    includes = [
        DECODE,
        base,
        DECODE.parent.parent,
        private / "src",
        private / "include",
        private / "ggml/include",
    ]
    argv = [
        gxx,
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
        *["-I" + str(p) for p in includes],
        HERE / "native.cpp",
        *(
            private / "src" / name
            for name in ("llama-moe-stream.cpp", "llama-impl.cpp", "llama-mmap.cpp")
        ),
        "-Wl,--gc-sections",
        *reversed(deps),
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
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    linked = subprocess.check_output(["/usr/bin/ldd", exe], env=env, text=True, timeout=10)
    (out / "loader.log").write_text(linked)
    check(
        not any(
            s in linked for s in ("not found", "libcuda", "libggml-cuda", "libllama", "libvulkan")
        ),
        "CPU-only loader",
    )
    for lib in [*deps, crypto]:
        check(
            any(
                line.split()[1:2] == ["=>"] and Path(line.split()[2]).samefile(lib)
                for line in linked.splitlines()
                if "=>" in line
            ),
            "provider " + lib.name,
        )
    r.update(
        status="PASS_CPU0_E28_PROJECTION_BUILD",
        commit=git("rev-parse", "HEAD"),
        old_build_sha256=OLD,
        libs=old["libs"],
        crypto_sha256=old["crypto_sha256"],
        compiler_sha256=old["compiler_sha256"],
        source_sha256={n: sha(HERE / n) for n in ("native.cpp", "build.py", "protocol.md")},
        executables={exe.name: sha(exe)},
        compiler_log_sha256=sha(out / "compiler.log"),
        loader_log_sha256=sha(out / "loader.log"),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("old-build", "libs", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    result = {"status": "FAIL_PRESERVED"}
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
        build(args, result)
    except Exception as e:
        result["reason"] = repr(e)
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
