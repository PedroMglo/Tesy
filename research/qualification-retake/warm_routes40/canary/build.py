"""Rebuild only the previously qualified C110 client with the common GGML callback."""

import argparse
import hashlib
import json
import resource
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "nvme_prefix_gate/attempt-02/receipt.json"
PRIOR = "56d6db87ac18b40407b0b6c55bac3898e5c65aaefc623d233e803ac14297878a"


def sha(p):
    with p.open("rb") as fp:
        return hashlib.file_digest(fp, "sha256").hexdigest()


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


def compile_client(a):
    dest = a.new_workspace.resolve()
    dest.mkdir(mode=0o700)
    a.new_receipt.mkdir()
    out = {"status": "FAIL", "forward_passes": 0, "pool_slots": 32, "stages": []}
    start = time.monotonic()

    def run(label, args, expected=0):
        def cap():
            resource.setrlimit(resource.RLIMIT_AS, (1536 * 2**20, 1536 * 2**20))

        r = subprocess.run(
            args,
            cwd=dest,
            capture_output=True,
            env={"PATH": "/usr/bin:/bin", "CUDA_VISIBLE_DEVICES": "", "LC_ALL": "C"},
            timeout=90,
            preexec_fn=cap,
        )
        logfile = dest / (label + ".log")
        logfile.write_bytes(r.stdout + r.stderr)
        out["stages"].append(dict(name=label, returncode=r.returncode, log_sha256=sha(logfile)))
        check(r.returncode == expected, label)
        return r.stdout

    try:
        check(sha(SOURCE) == PRIOR, "parent receipt")
        parent = json.loads(SOURCE.read_bytes())
        probe = a.canary_parent / "probe.cpp"
        check(
            sha(probe) == parent["patched_source_sha256"]
            and sha(a.canary_parent / "nvme-prefix-canary") == parent["executable_sha256"],
            "previous canary source/ELF",
        )
        shutil.copyfile(probe, dest / "probe.cpp")
        shutil.copyfile(HERE.parent / "routed_witness.h", dest / "routed_witness.h")
        run(
            "overlay", ["/usr/bin/patch", "--fuzz=0", "--batch", "-p1", "-i", HERE / "client.patch"]
        )
        prev = a.prefix_build.resolve()
        inc = prev / "source"
        libs = prev / "cmake/bin"
        ggml = a.ggml_bin.resolve()
        for soname, h in parent["mapped_objects_sha256"].items():
            if soname.startswith(("libggml", "libllama")):
                check(sha((libs if soname.startswith("libllama") else ggml) / soname) == h, soname)
        exe = dest / "routed-c110-canary"
        run(
            "compile",
            [
                "/usr/bin/c++",
                "-DGGML_BACKEND_SHARED",
                "-DGGML_SHARED",
                "-DGGML_USE_CPU",
                "-DGGML_USE_CUDA",
                "-DLLAMA_SHARED",
                f"-I{inc}/src",
                f"-I{inc}/vendor/nlohmann",
                f"-I{inc}/include",
                f"-I{inc}/ggml/include",
                f"-ffile-prefix-map={dest}=/tesy-canary",
                f"-ffile-prefix-map={prev}=/tesy-prefix-build",
                "-pipe",
                "-O3",
                "-DNDEBUG",
                "-std=gnu++17",
                "probe.cpp",
                "-o",
                exe,
                f"-L{libs}",
                f"-L{ggml}",
                f"-Wl,-rpath,{libs}:{ggml}",
                "-lllama",
                "-lggml",
                "-lggml-base",
                "-lggml-cpu",
                "-lggml-cuda",
                "-pthread",
            ],
        )
        ldd = run("ldd", ["/usr/bin/ldd", exe]).decode()
        paths = [
            Path(line.split("=>")[1].split()[0]).resolve(strict=True)
            for line in ldd.splitlines()
            if "=>" in line
        ]
        mapped = {p.name: sha(p) for p in paths}
        check(mapped == parent["mapped_objects_sha256"], "mapped DSOs")
        run("reject-long", [exe, "none", "none", "none", "--arm", "C"], 2)
        run("exclusive", [exe, "--check-exclusive-output", dest / "no-replace"])
        run("reject-duplicate", [exe, "--check-exclusive-output", dest / "no-replace"], 1)
        out.update(
            status="PASS_MODEL_FREE_CANARY_BUILD",
            executable_sha256=sha(exe),
            mapped_objects_sha256=mapped,
            common_header_sha256=sha(HERE.parent / "routed_witness.h"),
            client_patch_sha256=sha(HERE / "client.patch"),
            original_canary_receipt_sha256=PRIOR,
            protocol_sha256=sha(HERE / "protocol.md"),
        )
    except Exception as exc:
        out["error"] = str(exc)
        raise
    finally:
        out["elapsed_s"] = round(time.monotonic() - start, 3)
        out["max_child_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        with (a.new_receipt / "receipt.json").open("x") as f:
            json.dump(out, f, sort_keys=True, indent=2)
            f.write("\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("canary-parent", "prefix-build", "ggml-bin", "new-workspace", "new-receipt"):
        p.add_argument("--" + name, type=Path, required=True)
    compile_client(p.parse_args())
