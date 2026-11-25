"""Build only the small client against sealed stock headers and existing ELF dependencies."""

import argparse
import hashlib
import json
import os
import re
import resource
import subprocess
import time
from pathlib import Path

from evaluate import HERE, dump, inputs, require

PIN = "e95426f16982054c379ca7bdc8186996dd22f0fe"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def prepare(a):
    os.umask(0o077)
    a.new_private.mkdir(exist_ok=False)
    a.new_output.mkdir(exist_ok=False)
    r = {
        "status": "FAIL",
        "source_sha256": sha(HERE / "client.cpp"),
        "protocol_sha256": sha(HERE / "protocol.md"),
    }
    start = time.monotonic()
    try:
        source = a.stock / "source"
        libs = a.stock / "build/bin"
        code = subprocess.check_output(
            ["git", "-C", source, "rev-parse", "HEAD"], text=True
        ).strip()
        require(
            code == PIN
            and not subprocess.check_output(["git", "-C", source, "status", "--porcelain"]),
            "stock_source",
        )
        receipt = json.loads(a.stock_receipt.read_text())
        require(
            receipt["pin"] == PIN and receipt["decision"] == "PASS_STOCK_BUILD_AND_MODEL_FREE_CLI",
            "stock_build",
        )
        compiler = Path("/usr/bin/g++-15")
        require(sha(compiler) == receipt["toolchain"]["cxx"]["sha256"], "compiler")
        ids, _, _ = inputs(a.raw_parent)
        exe = a.new_private / "stock-numeric"
        cmd = [compiler, "-std=c++17", "-O2", "-DNDEBUG", "-Wall", "-Wextra", "-Werror"]
        cmd.extend("-I" + str(source / p) for p in ("common", "include", "ggml/include", "vendor"))
        cmd.extend(
            [
                "-DGGML_BACKEND_SHARED",
                "-DGGML_SHARED",
                "-DGGML_USE_CPU",
                "-DGGML_USE_CUDA",
                "-DLLAMA_SHARED",
                HERE / "client.cpp",
                "-L" + str(libs),
                "-Wl,-rpath," + str(libs),
                "-lllama-common",
                "-lllama",
                "-o",
                exe,
            ]
        )

        def clamp():
            resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
            resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 2**20, 16 * 2**20))

        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "CUDA_VISIBLE_DEVICES": "",
            "TMPDIR": str(a.new_private),
        }
        with (a.new_private / "build.log").open("xb") as log:
            subprocess.run(
                cmd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=60,
                preexec_fn=clamp,
                check=True,
            )
        mapped = {}
        ld = subprocess.check_output(["ldd", exe], env=env, text=True, timeout=10)
        require("not found" not in ld, "unresolved_lib")
        for name, path in re.findall(r"^\s*(\S+) => (\S+) \(", ld, re.M):
            if name.startswith(("libllama", "libggml", "libmtmd")):
                actual = Path(path).resolve()
                require(
                    actual.parent == libs.resolve()
                    and sha(actual) == receipt["own_libs_sha256"][name],
                    "external_stock_lib",
                )
                mapped[name] = sha(actual)
        require(len(mapped) >= 6 and "libggml-cuda.so.0" in mapped, "incomplete_backend")
        for packed, expected in (
            (ids, 0),
            (ids[:-4], 1),
            (ids + ids[:4], 1),
            (b"\xff" * 4 + ids[4:], 1),
        ):
            proc = subprocess.run(
                [exe, "--check-input"], env=env, input=packed, capture_output=True, timeout=5
            )
            require(proc.returncode == expected, "directed_input")
        r.update(
            status="PASS_STOCK_NUMERIC_CLIENT_MODEL_FREE",
            executable_sha256=sha(exe),
            compiler_sha256=sha(compiler),
            own_libraries=mapped,
            stock_build_receipt_sha256=sha(a.stock_receipt),
            pin=PIN,
            elapsed_s=round(time.monotonic() - start, 3),
            peak_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        )
    except Exception as exc:
        r["reason"] = type(exc).__name__
        dump(a.new_output, r)
        raise
    dump(a.new_output, r)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for t in ("stock", "stock-receipt", "raw-parent", "new-private", "new-output"):
        p.add_argument("--" + t, type=Path, required=True)
    prepare(p.parse_args())
