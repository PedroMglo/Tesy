"""Build or run the CPU-only parked-down arithmetic experiment at the sealed pins."""

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").is_file())
ROW = run_path(
    str(ROOT / "research/qualification-retake/history_lookup/b3_numeric/cpu_row_geometry/run.py")
)
METHOD = "f7e6eb695095f2c8dfb4e4d90f2949be0312c2ee16ccaecc3ddfa1f1a0e7ce75"
DATA = {
    "prepare.json": "a3a6028b45719ee0a1c63f689a2e6896b5a401ee394d5aa9d3188d98e72dc269",
    "down.bias": "c3ccfe57f0606669a9f2860083f95ef6e0234583ad44144f6b010480a8e59dbe",
    "ffn_moe_topk-0.bin": "14ada9ecbfe77401ff5d40955e9b491c6ebc82f34787737c2e4c8910ffa6cd96",
}
need, git, sha = (ROW[k] for k in ("need", "git", "sha"))


def run(a, out, record):
    need(
        sha(HERE / "protocol.md") == METHOD
        and git(ROOT, "rev-parse", "HEAD") == a.commit
        and not git(ROOT, "status", "--porcelain"),
        "clean method",
    )
    need(
        git(a.backend, "rev-parse", "HEAD") == ROW["COMMIT"]
        and not git(a.backend, "status", "--porcelain"),
        "backend pin",
    )
    libs = a.backend / "build-c269-cuda/bin"
    for f, h in ROW["PINS"].items():
        need(sha(a.backend / f) == h, "source " + f)
    for f, h in ROW["LIBS"].items():
        need(sha(libs / f) == h, "provider " + f)
    group = (
        Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::/", 1)[1]
    )
    limits = {
        f: int((group / f).read_text()) for f in ("memory.max", "memory.swap.max", "pids.max")
    }
    need(
        limits == {"memory.max": 768 << 20, "memory.swap.max": 0, "pids.max": 24},
        "resource envelope",
    )
    cpu = next(
        line.split(":", 1)[1].strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines()
        if line.startswith("model name")
    )
    need(
        "Ryzen AI 9 HX 370" in cpu
        and Path("/sys/class/power_supply/AC0/online").read_text().strip() == "1",
        "target CPU on mains",
    )
    record.update(
        commit=a.commit,
        tree=git(ROOT, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=METHOD,
        backend_commit=ROW["COMMIT"],
        libs=ROW["LIBS"],
        host=socket.gethostname(),
        cpu=cpu,
        kernel=platform.release(),
        limits=limits,
        model_starts=0,
        requests=0,
        fixture_sha256=sha(HERE / "fixture.cpp"),
        runner_sha256=sha(HERE / "run.py"),
    )
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=str(libs),
        OMP_DYNAMIC="FALSE",
        OMP_THREAD_LIMIT="8",
        OMP_NUM_THREADS="8",
        TMPDIR=str(out),
    )
    if a.phase == "build":
        exe = out / "fixture"
        compiler = "/usr/bin/g++"
        command = [
            compiler,
            "-std=c++20",
            "-O2",
            "-fno-fast-math",
            "-frounding-math",
            "-ffp-contract=off",
            "-fopenmp",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(a.backend / "ggml/include"),
            "-I",
            str(a.backend / "vendor"),
            str(HERE / "fixture.cpp"),
            "-L",
            str(libs),
            "-lggml-cpu",
            "-lggml-base",
            "-lcrypto",
            "-o",
            str(exe),
        ]
        record.update(command=command, compiler_sha256=sha(Path(compiler)))
        with (out / "compiler.log").open("xb") as f:
            subprocess.run(
                command, env=env, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=70
            )
        record.update(status="BUILT_PARKED_DOWN_FIXTURE", binary_sha256=sha(exe))
        return
    need(a.build and a.build_sha256 and a.input, "sealed build and input required")
    need(sha(a.build / "receipt.json") == a.build_sha256, "build seal")
    build = json.loads((a.build / "receipt.json").read_bytes())
    exe = a.build / "fixture"
    need(
        build["commit"] == a.commit
        and build["status"] == "BUILT_PARKED_DOWN_FIXTURE"
        and sha(exe) == build["binary_sha256"],
        "built ELF",
    )
    linkage = subprocess.check_output(["ldd", str(exe)], env=env, text=True)
    (out / "ldd.txt").write_text(linkage)
    for soname in ROW["LIBS"]:
        prefix = soname.split(".so")[0] + ".so"
        targets = [
            Path(line.split("=>", 1)[1].strip().split()[0])
            for line in linkage.splitlines()
            if "=>" in line and line.strip().startswith(prefix)
        ]
        need(len(targets) == 1 and targets[0].samefile(libs / soname), "runtime provider " + soname)
    for f, h in DATA.items():
        need(sha(a.input / f) == h, "capture " + f)
    record.update(
        input_sha256=DATA, binary_sha256=build["binary_sha256"], build_sha256=a.build_sha256
    )
    with (out / "native.json").open("xb") as f, (out / "stderr.log").open("xb") as e:
        subprocess.run(
            [str(exe), str(a.input)], env=env, stdout=f, stderr=e, check=True, timeout=50
        )
    tests = json.loads((out / "native.json").read_bytes())
    record.update(tests=tests, native_sha256=sha(out / "native.json"))
    need(
        set(tests) == {"C266_bias", "adversarial_bias"}
        and all(
            t["candidate_differences"] == 0
            and t["reference_sha256"] == t["candidate_sha256"]
            and t["values"] == t["parked_positive_zeros"] == 368640
            for t in tests.values()
        ),
        "independent bitwise comparison",
    )
    record.update(status="PASS_PARKED_DOWN_ARITHMETIC")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("build", "run"))
    for k in ("backend", "new-output-dir", "input", "build"):
        p.add_argument("--" + k, type=Path, required=k in ("backend", "new-output-dir"))
    p.add_argument("--build-sha256")
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    record = dict(status="FAIL_PRESERVED", phase=a.phase)
    try:
        run(a, out, record)
    except Exception as e:
        record["exception"] = str(e)
    with (out / "receipt.json").open("x") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    if record["status"] == "FAIL_PRESERVED":
        print(record["exception"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
