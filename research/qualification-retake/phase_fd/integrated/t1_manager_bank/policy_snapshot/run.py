"""Qualify an opt-in policy sidecar using the real C269 manager with synthetic descriptors."""

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PFJ = HERE.parents[1]
ARMS = ("off", "heat-a", "heat-b", "age-a", "age-b", "pending", "missing", "duplicate")
PROTOCOL = "5f1eb0dca4a844dab6a9045dd2e089773d0326fa80b9769a6837b890349e71b1"
PRIOR = "e5042bfb23527a1763b28ca2098c0a00700383d07ff403a97d52da4bcdf422a6"
CORE = "8b9dfdbef77c3c882cf4a759cf90a7d4c7ad517cb9a946abe8a54e3fb7f61e23"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def git(repo, *args):
    return subprocess.check_output(["git", "-C", repo, *args], text=True).strip()


def overlay(private, prior, source_hashes):
    private.mkdir()
    for name, digest in source_hashes.items():
        path = prior / "overlay" / name
        require(sha(path) == digest, "PFJ1 source " + name)
        (private / path.name).write_bytes(path.read_bytes())
    path = private / "phase-fd-integrated.h"
    src = path.read_text()
    changes = (
        ('#include "llama-moe-stream.h"', '#include "llama-moe-stream.h"\n#include "snapshot.h"'),
        ("    journal=j.release();", "    policy::install();\n    journal=j.release();"),
        (
            "    if(first) snapshot(*mgr,host);",
            "    policy::capture_locked(*mgr,host.call,n,p0,p1);\n"
            "    if(first) snapshot(*mgr,host);",
        ),
        ("    delete journal;", "    policy::finish();\n    delete journal;"),
    )
    for before, after in changes:
        require(src.count(before) == 1, "private PFJ1 injection point")
        src = src.replace(before, after)
    path.write_text(src)
    (private / "snapshot.h").write_bytes((HERE / "snapshot.h").read_bytes())
    return path


def run(args, out, r, start):
    require(
        sha(HERE / "protocol.md") == PROTOCOL and sha(PFJ / "native_fixture.py") == CORE, "source"
    )
    old = run_path(PFJ / "native_fixture.py")
    prior, native = args.pfj_build.resolve(strict=True), args.backend.resolve(strict=True)
    build = json.loads(old["pinned"](prior / "receipt.json", PRIOR).read_bytes())
    require(
        git(HERE, "rev-parse", "HEAD") == args.commit
        and not git(HERE, "status", "--porcelain")
        and git(native, "rev-parse", "HEAD") == "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
        and not git(native, "diff", "HEAD", "--", "src", "include", "ggml/include")
        and build["status"] == "PASS_C269_PHASE_FD_PRIVATE_BUILD",
        "clean qualification and C269 input identity",
    )
    cg = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().removeprefix("0::/")
    require(
        cg.name == args.unit + ".scope"
        and (cg / "memory.max").read_text().strip() == str(2**30)
        and (cg / "memory.swap.max").read_text().strip() == "0",
        "dedicated CPU scope",
    )
    initial = (cg / "memory.events").read_text()
    manifest = old["read_manifest"](prior / "inputs.json", build["inputs_sha256"])
    support = []
    for name in (
        "src/CMakeFiles/llama.dir/llama-mmap.cpp.o",
        "src/CMakeFiles/llama.dir/llama-impl.cpp.o",
        "bin/libggml-base.so.0.15.3",
    ):
        support.append(old["pinned"](native / "build-c269-cuda" / name, manifest[name]))
    compiler = old["pinned"](Path("/usr/bin/g++-15"), build["compiler_sha256"])
    private = out / "private"
    header = overlay(private, prior, build["overlay_sha256"])
    exe = out / "policy-cpu"
    r.update(
        commit=args.commit,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=PROTOCOL,
        prior_build_sha256=PRIOR,
        compiler_sha256=build["compiler_sha256"],
        inputs={p.name: sha(p) for p in support},
        header_sha256=sha(header),
        sources={
            name: sha(HERE / name) for name in ("fixture.cpp", "snapshot.h", "run.py", "review.py")
        },
        arms={},
        gpu_calls=0,
        model_forwards=0,
    )
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        TMPDIR=str(out),
        LD_LIBRARY_PATH=str(support[-1].parent),
        CUDA_VISIBLE_DEVICES="",
        OMP_NUM_THREADS="1",
    )

    def command(argv, stdout, stderr, extra=None):
        with stdout.open("xb") as f, stderr.open("xb") as e:
            subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=f,
                stderr=e,
                env=env | (extra or {}),
                check=True,
                timeout=max(0.01, start + 115 - time.monotonic()),
            )

    r["stage"] = "build"
    options = ["-std=c++17", "-O1", "-g0", "-fPIC", "-pthread", "-DTESY_C47_CPU_SKIP_PARKED"]
    headers = [private, *(native / k for k in ("src", "include", "ggml/include"))]
    argv = [
        compiler,
        *options,
        *("-I" + str(x) for x in headers),
        HERE / "fixture.cpp",
        private / "llama-moe-stream.cpp",
        *support,
        "-o",
        exe,
    ]
    command(argv, out / "build.stdout", out / "build.stderr")
    command(["/usr/bin/ldd", exe], out / "loader.txt", out / "loader.stderr")
    loader = (out / "loader.txt").read_text()
    sonames = [line.strip().split()[0] for line in loader.splitlines() if line.strip()]
    require(
        "not found" not in loader
        and "libggml-base.so.0" in sonames
        and not any(
            x in lib.lower() for x in ("cuda", "nvidia", "cublas", "llama") for lib in sonames
        ),
        "unexpected linked runtime",
    )
    r.update(binary_sha256=sha(exe), build_s=time.monotonic() - start)
    for arm in ARMS:
        r["stage"] = arm
        d = out / arm
        d.mkdir()
        extra = {"TESY_PHASE_FD_FILE": str(d / "journal.pfj")}
        if arm != "off":
            extra["TESY_PFJ_POLICY_SNAPSHOT"] = str(d / "policy.bin")
        command([exe, arm, d / "empty.bin"], d / "native.json", d / "stderr", extra)
        r["arms"][arm] = {p.name: sha(p) for p in d.iterdir()}
    r["stage"] = "independent_integer_oracle"
    r["verified"] = run_path(HERE / "review.py")["family"](out)
    r["scope_peak"] = int((cg / "memory.peak").read_text())
    r["output_bytes"] = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    require(
        r["scope_peak"] <= 2**30
        and r["output_bytes"] + 131072 <= 128 * 2**20
        and initial == (cg / "memory.events").read_text()
        and int((cg / "memory.swap.current").read_text()) == 0,
        "CPU or output budget",
    )
    r["status"] = "PASS_C269_POLICY_SNAPSHOT_FIXTURE_ONLY"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("commit", "unit"):
        p.add_argument("--" + name, required=True)
    for name in ("backend", "pfj-build", "new-output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    args = p.parse_args()
    os.umask(0o077)
    out = args.new_output_dir.resolve()
    out.mkdir()
    start = time.monotonic()
    result = {"stage": "admit"}
    try:
        run(args, out, result, start)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as err:
        result.update(status="FAIL_PRESERVED", reason=str(err))
    result["wall_s"] = time.monotonic() - start
    tmp = out / "receipt.tmp"
    tmp.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.rename(out / "receipt.json")
    print(result["status"], result.get("reason", ""))
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
