"""Run the task-boundary and short-read tests against two private copies of C269."""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
PROTOCOL = "ab6057be544b37eb830ed22af3d0c9f167af4534b3832785c0fbe4b092a234ed"
SOURCE = "584aecb73900aa1164f00ec93126bc5b8b07c4d330d0f421641331b0c278d5a0"
BASE_DSO = "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539"


def need(value, why):
    if not value:
        raise ValueError(why)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def overlay(source):
    replacements = {
        '#include "llama-moe-stream.h"': '#include "llama-moe-stream.h"\n#include "observe.h"',
        "r = pread(fd, staging, total, aoffs);": "r = phase_fd::read(fd, staging, total, aoffs);",
        "ssize_t r = pread(fd, p, left, offs);": "ssize_t r = phase_fd::read(fd, p, left, offs);",
        "sl.slot_claimed[w.slot] = 1;": (
            "sl.slot_claimed[w.slot] = 1;\n        phase_fd::begin(sl.il, w.expert, w.slot, w.gen);"
        ),
        "ggml_backend_tensor_set(wt.cache, data, (size_t) w.slot*wt.nb_expert, wt.nb_expert);": (
            "ggml_backend_tensor_set(wt.cache, data, (size_t) w.slot*wt.nb_expert, wt.nb_expert);\n"
            "            phase_fd::set_return(wt.nb_expert);"
        ),
        "        cv_done.notify_all();": (
            "        phase_fd::finish(ok);\n" + "        cv_done.notify_all();"
        ),
    }
    for old, new in replacements.items():
        need(source.count(old) == 1, "pinned source seam")
        source = source.replace(old, new)
    return source


def git(root, *args):
    return subprocess.check_output(["git", "-C", root, *args], text=True).strip()


def resources():
    record = Path("/proc/self/cgroup").read_text().strip()
    need(record.startswith("0::/") and "tesy-phase-fd" in record, "dedicated cgroup")
    cg = Path("/sys/fs/cgroup") / record[3:].lstrip("/")
    need(
        (cg / "memory.max").read_text().strip() == str(512 * 2**20)
        and (cg / "memory.swap.max").read_text().strip() == "0",
        "scope limits",
    )
    return cg


def main(a, r):
    cg = resources()
    start = time.monotonic()
    r["limits"] = {
        "memory_max": 512 * 2**20,
        "swap_max": 0,
        "seconds": 120,
        "output_bytes": 32 * 2**20,
    }
    out = a.new_output_dir
    backend = a.backend.resolve(strict=True)
    repo = HERE.parents[2]
    need(
        git(repo, "status", "--porcelain") == ""
        and git(repo, "rev-parse", "HEAD") == a.expect_head,
        "frozen checkout",
    )
    need(git(backend, "rev-parse", "HEAD") == PIN, "C269 pin")
    r.update(
        checkout=a.expect_head,
        tree=git(repo, "rev-parse", "HEAD^{tree}"),
        backend=PIN,
        program_sha256=sha(Path(__file__)),
        fixture_sha256=sha(HERE / "fixture.cpp"),
        observer_sha256=sha(HERE / "observe.h"),
        protocol_sha256=sha(HERE / "protocol.md"),
    )
    need(r["protocol_sha256"] == PROTOCOL, "protocol")
    source = backend / "src/llama-moe-stream.cpp"
    need(sha(source) == SOURCE, "manager and reader pin")
    r["reference_source_sha256"] = SOURCE
    variant = out / "llama-moe-stream.cpp"
    variant.write_text(overlay(source.read_text()))
    r["instrumented_source_sha256"] = sha(variant)
    libs = backend / "build-c269-cuda/bin"
    base = (libs / "libggml-base.so").resolve(strict=True)
    need(sha(base) == BASE_DSO, "CPU buffer implementation")
    r["ggml_base_sha256"] = BASE_DSO
    r["compiler_sha256"] = sha(Path("/usr/bin/g++"))
    env = {
        "PATH": "/usr/bin:/bin",
        "TMPDIR": str(out),
        "LD_LIBRARY_PATH": str(libs),
        "LC_ALL": "C",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "CUDA_VISIBLE_DEVICES": "",
    }

    def run(cmd, label):
        with (
            (out / (label + ".stderr")).open("xb") as stderr,
            (out / (label + ".stdout")).open("xb") as stdout,
        ):
            p = subprocess.run(
                cmd,
                stdout=stdout,
                stderr=stderr,
                env=env,
                timeout=max(0, 115 - (time.monotonic() - start)),
                stdin=subprocess.DEVNULL,
                check=False,
            )
        need(p.returncode == 0, label)
        return (out / (label + ".stdout")).read_text()

    flags = [
        "/usr/bin/g++",
        "-std=c++17",
        "-O0",
        "-g0",
        "-fPIC",
        "-pthread",
        "-ffunction-sections",
        "-fdata-sections",
        "-I" + str(HERE),
    ]
    flags.extend("-I" + str(backend / inc) for inc in ("src", "include", "ggml/include"))
    headers = {}

    def compile(src, label):
        dep = out / (label + ".d")
        obj = out / (label + ".o")
        run([*flags, "-MMD", "-MF", dep, "-c", src, "-o", obj], label)
        deps = shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1])
        for file in deps:
            p = Path(file).resolve()
            if p.is_relative_to(backend):
                key = p.relative_to(backend).as_posix()
                if key not in headers:
                    sealed = subprocess.check_output(
                        ["git", "-C", backend, "show", PIN + ":" + key]
                    )
                    need(
                        hashlib.sha256(sealed).hexdigest() == sha(p), "dependency differs from pin"
                    )
                    headers[key] = sha(p)
        return obj

    common = [compile(HERE / "fixture.cpp", "fixture")]
    for src in ["llama-impl.cpp", "llama-mmap.cpp"]:
        common.append(compile(backend / "src" / src, src.split(".")[0]))
    r["arms"] = {}
    r["executables_sha256"] = {}
    prefix = "phase-fd-"
    for arm, src in (("OFF", source), ("ON", variant)):
        mgr = compile(src, "manager-" + arm)
        exe = out / (prefix + arm)
        run(
            [
                "/usr/bin/g++",
                "-pthread",
                "-pie",
                *common,
                mgr,
                "-Wl,--gc-sections",
                "-Wl,--wrap=pread",
                base,
                "-o",
                exe,
            ],
            "link-" + arm,
        )
        mappings = run(["/usr/bin/ldd", exe], "loader-" + arm)
        actual = {Path(s.split()[2]).resolve() for s in mappings.splitlines() if " => /" in s}
        need(
            base in actual
            and all(not x.name.startswith(("libcuda", "libggml-cuda", "libllama")) for x in actual),
            "loader",
        )
        r["executables_sha256"][arm] = sha(exe)
        for case in ("SHORT_OK", "SHORT_INVALID"):
            row = json.loads(run([exe, arm, case], arm + "-" + case))
            jobs = 2 if case == "SHORT_OK" else 1
            expected = jobs * (2 * 4096 + (352 if jobs == 2 else 223))
            need(
                row["status"] == "PASS"
                and row["returned_bytes"] == expected
                and row["requested_bytes"] == jobs * 3 * 4096
                and row["calls"] == jobs * 3
                and row["pending_at_A_return"] == 1
                and row["workers_joined"] == 4
                and row["drained_terminal"] is True,
                "independent totals",
            )
            r["arms"][arm + "-" + case] = row
    for case in ("SHORT_OK", "SHORT_INVALID"):
        need(r["arms"]["OFF-" + case] == r["arms"]["ON-" + case], "OFF/ON work or state")
    r["pinned_dependencies_sha256"] = headers
    r["elapsed_s"] = round(time.monotonic() - start, 3)
    r["cgroup_peak_bytes"] = int((cg / "memory.peak").read_text())
    r["cgroup_events_local"] = {
        k: int(n)
        for k, n in (line.split() for line in (cg / "memory.events.local").read_text().splitlines())
    }
    need(
        not any(r["cgroup_events_local"][key] for key in ("oom", "oom_kill", "max")),
        "memory boundary",
    )
    need(sum(p.stat().st_size for p in out.iterdir()) < 32 * 2**20 - 16384, "output boundary")
    r["status"] = "PASS_C269_SYSCALL_ATTRIBUTION_FIXTURE"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("backend", "new-output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--expect-head", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(mode=0o700)
    report = {"status": "FAIL_PRESERVED", "model_forwards": 0}
    try:
        main(args, report)
    except Exception as exc:
        report["failure"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(report["status"])
    raise SystemExit(report["status"] == "FAIL_PRESERVED")
