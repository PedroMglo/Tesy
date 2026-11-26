"""Build the pinned client or qualify it using only the sealed synthetic GGUF."""

import argparse
import hashlib
import json
import math
import os
import resource
import struct
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
TINY = HERE.parents[1] / "tiny_loader"
prior = run_path(str(TINY / "run.py"))
front = prior["FRONT"]
need, pinned, sha = prior["need"], front["pinned"], prior["sha"]
TINY_RECEIPT = "b10222365dec972020668e3e9a9874018f8af2a7170ddef2c9f97ff60018cd92"
OBSERVER = "3ac453a41a15775105d34120a93316310ba29b2dd9277d7e259d2458a00f4b21"
CAP = 256 << 20
EXE = "ik-cpu-numeric"
STOPS = {
    0: "PASS_IK_CPU_NUMERIC_ROWS",
    42: "STOP_FIRST_GREEDY",
    43: "STOP_FIRST_D0_BITS",
    44: "STOP_SECOND_D0_BITS",
}


def sources():
    return {
        p.name: sha(p) for p in (HERE / "protocol.md", HERE / "driver.cpp", HERE / "run.py")
    } | {
        "tiny_loader/probe.cpp": sha(pinned(TINY / "probe.cpp", OBSERVER)),
        "tiny_loader/run.py": sha(TINY / "run.py"),
        "frontend/run.py": sha(TINY.parent / "frontend/run.py"),
    }


def version(directory):
    def git(*args):
        return subprocess.check_output(["git", "-C", directory, *args], text=True).strip()

    return git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")


def build(a, out, result):
    src, obj = a.source.resolve(), a.objects.resolve()
    ik_commit, ik_tree = version(src)
    need((ik_commit, ik_tree) == (front["PIN"], front["TREE"]), "ik pin")
    need(not subprocess.check_output(["git", "-C", src, "status", "--porcelain"]), "dirty ik")
    cache = (obj / "CMakeCache.txt").read_text().splitlines()
    for line in (
        "GGML_CUDA:BOOL=OFF",
        "GGML_VULKAN:BOOL=OFF",
        "LLAMA_CURL:BOOL=OFF",
        "CMAKE_HOME_DIRECTORY:INTERNAL=" + str(src),
    ):
        need(line in cache, "R03 configuration")
    for name, digest in prior["BASE"].items():
        pinned(obj / name, digest)
    revision, tree = version(HERE)
    need(
        not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain", "--", "."]),
        "dirty driver",
    )
    cmd = [
        "/usr/bin/c++",
        "-std=c++17",
        "-O1",
        "-pthread",
        "-rdynamic",
        *(f"-I{src / d}" for d in ("include", "ggml/include", "ggml/src")),
        str(HERE / "driver.cpp"),
        *(str(obj / name) for name in prior["BASE"]),
        "-ldl",
        "-o",
        str(out / EXE),
    ]
    result.update(
        binary=EXE,
        libraries=prior["BASE"],
        commit=revision,
        tree=tree,
        ik_commit=ik_commit,
        ik_tree=ik_tree,
        sources=sources(),
        compile_argv=cmd,
        compiler_sha256=sha(Path(cmd[0]).resolve()),
    )
    with (out / "compile.log").open("xb") as log:
        subprocess.run(
            cmd, check=True, env=front["env"](obj), stdout=log, stderr=subprocess.STDOUT, timeout=60
        )
    result.update(binary_sha256=sha(out / EXE), closure=front["closure"](out / EXE, obj))
    return "PASS_IK_CPU_NUMERIC_BUILD"


def bounded():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))


def limits(root):
    values = {
        key: int((root / key).read_text())
        for key in ("memory.max", "memory.swap.max", "memory.peak", "memory.swap.peak")
    }
    return values | {"events": (root / "memory.events").read_text()}


def observations(text, label):
    return [line.split()[1:] for line in text.splitlines() if line.startswith(label + " ")]


def check_stdout(stdout, dest, expected_rc, reference, closure, mode):
    def ints(label):
        return [tuple(map(int, parts)) for parts in observations(stdout, label)]

    need(observations(stdout, "STATUS") == [[STOPS[expected_rc]]], "terminal")
    need(
        observations(stdout, "VIEW") == observations(reference, "VIEW") and len(ints("POOL")) == 1,
        "12 expert VMAs and pool",
    )
    for key in ("MAP", "MAD", "POSIX"):
        need(observations(stdout, key) == observations(reference, key), "loader " + key)
    providers = dict(observations(stdout, "PROVIDER"))
    need(
        providers == {name: closure["lib" + name + ".so"]["file"] for name in ("llama", "ggml")},
        "dladdr",
    )
    before, after, enabled = ints("POOL")[0]
    need(enabled == int(mode == "D1") and after - before == 4 * enabled, "worker delta")
    need(
        len(ints("DRAIN")) == 1 and ints("DRAIN")[0][:2] == (6, 0),
        "six weights and disabled pool at close",
    )
    phases = observations(stdout, "PHASE")
    expected_phases = [
        "load_begin",
        "load_end",
        "context_begin",
        "context_end",
        "prefill_begin",
        "prefill_end",
    ]
    with_teacher = expected_rc in (0, 44)
    if with_teacher:
        expected_phases += ["teacher_begin", "teacher_end"]
    expected_phases += ["cleanup_begin", "cleanup_end"]
    stamps = [int(stamp) for _, stamp in phases]
    need(
        [key for key, _ in phases] == expected_phases
        and all(x < y for x, y in zip(stamps[:-1], stamps[1:], strict=True)),
        "phase gates",
    )
    rows = {}
    for pos, cols, argmax, ties in ints("ROW"):
        path = dest / f"pos{pos}.f32"
        raw = path.read_bytes()
        need(cols == 32 and len(raw) == 128 and pos not in rows, "full synthetic row")
        values = struct.unpack("<32f", raw)
        need(
            all(map(math.isfinite, values)) and min(values) < max(values), "finite nonconstant row"
        )
        need(
            (argmax, ties) == (values.index(max(values)), values.count(max(values))),
            "independent argmax",
        )
        rows[pos] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "greedy": argmax,
            "ties": ties,
        }
    need(
        list(rows) == ([15, 16] if with_teacher else [15])
        and (dest / "pos16.f32").exists() == with_teacher,
        "teacher stop/row count",
    )
    (rss,) = ints("RSS")
    need(0 < rss[0] * 1024 <= CAP, "child RSS")
    return dict(
        rows=rows,
        max_rss_kib=rss[0],
        incremental_workers=after - before,
        phases=[x[0] for x in phases],
    )


def synthetic(a, out, result):
    obj = a.objects.resolve()
    b = json.loads(pinned(a.build / "receipt.json", a.build_sha256).read_bytes())
    need(b["status"] == "PASS_IK_CPU_NUMERIC_BUILD" and b["sources"] == sources(), "build sources")
    exe = pinned(a.build / EXE, b["binary_sha256"])
    need(
        b["closure"] == front["closure"](exe, obj) and b["libraries"] == prior["BASE"],
        "build providers",
    )
    old = json.loads(pinned(a.tiny_dir / "receipt.json", TINY_RECEIPT).read_bytes())
    need(old["status"] == "PASS_TINY_IK_DEFERRED_GPT_OSS_LOGITS", "tiny admission")
    model = pinned(a.tiny_dir / "synthetic.gguf", old["gguf_sha256"])
    need(model.stat().st_size == old["gguf_bytes"] == 3390592, "tiny GGUF")
    ref = pinned(a.tiny_dir / "DEFER/stdout", old["arms"]["DEFER"]["stdout_sha256"]).read_text()
    scope = Path("/proc/self/cgroup").read_text().strip().split("::", 1)
    need(
        scope[0] == "0"
        and Path(scope[1]).name == a.scope + ".scope"
        and a.scope.startswith("tesy-ik-numeric-"),
        "resident scope",
    )
    cg = Path("/sys/fs/cgroup") / scope[1].lstrip("/")
    baseline = limits(cg)
    need(
        (baseline["memory.max"], baseline["memory.swap.max"], baseline["memory.swap.peak"])
        == (CAP, 0, 0),
        "scope limits",
    )
    ids = out / "synthetic.i32"
    ids.write_bytes(struct.pack("<17i", *range(4, 20), 6))
    result.update(
        build_sha256=a.build_sha256,
        binary_sha256=b["binary_sha256"],
        tiny_loader_sha256=TINY_RECEIPT,
        model_sha256=old["gguf_sha256"],
        input_sha256=sha(ids),
        cgroup_before=baseline,
        arms={},
        original_model_loads=0,
        scope=a.scope,
    )
    env = front["env"](obj) | {
        "GGML_MOE_PREFETCH_AHEAD": "0",
        "OMP_NUM_THREADS": "8",
        "OMP_STACKSIZE": "512K",
        "MALLOC_ARENA_MAX": "1",
    }

    def arm(label, mode, expected, rc=0, d0=None):
        case = out / label
        case.mkdir()
        args = [exe, "synthetic", mode, model, ids, str(expected), case / "native"]
        if d0 is not None:
            args.append(d0)
        with (case / "stdout").open("xb") as log, (case / "stderr").open("xb") as err:
            child = subprocess.run(
                args, env=env, stdout=log, stderr=err, preexec_fn=bounded, timeout=30
            )
        record = result["arms"][label] = {
            "returncode": child.returncode,
            "stdout_sha256": sha(case / "stdout"),
            "stderr_sha256": sha(case / "stderr"),
        }
        need(child.returncode == rc, f"{label} return {child.returncode} expected {rc}")
        record.update(
            check_stdout(
                (case / "stdout").read_text(), case / "native", rc, ref, b["closure"], mode
            )
        )
        return record["rows"]

    try:
        calibration = arm("calibration", "CAL", -1)
        best = calibration[15]["greedy"]
        d0 = arm("D0", "D0", best)
        d0_raw = out / "D0/native"
        d1 = arm("D1", "D1", best, d0=d0_raw)
        need(calibration == d0 == d1, "full two-row bitwise contrast")
        for pos in (15, 16):
            name = f"pos{pos}.f32"
            need(
                (d0_raw / name).read_bytes() == (out / "D1/native" / name).read_bytes(),
                "raw D0/D1 bytes",
            )
        arm("wrong-greedy", "D0", (best + 1) % 32, 42)
        for pos, rc in ((15, 43), (16, 44)):
            changed = out / f"changed-reference-{pos}"
            changed.mkdir()
            for p in (15, 16):
                name = f"pos{p}.f32"
                raw = bytearray((d0_raw / name).read_bytes())
                if p == pos:
                    raw[0] ^= 1
                (changed / name).write_bytes(raw)
            arm("wrong-bits-" + str(pos), "D1", best, rc, changed)
        result["same_rows"] = True
    finally:
        after = result["cgroup_after"] = limits(cg)
    need(
        after["events"] == baseline["events"]
        and after["memory.peak"] <= CAP
        and after["memory.swap.peak"] == 0,
        "transient resource event",
    )
    return "PASS_IK_CPU_NUMERIC_SYNTHETIC"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    compile_cli = modes.add_parser("build")
    compile_cli.add_argument("--source", type=Path, required=True)
    test_cli = modes.add_parser("synthetic")
    for key in ("build", "tiny-dir"):
        test_cli.add_argument("--" + key, type=Path, required=True)
    for key in ("build-sha256", "scope"):
        test_cli.add_argument("--" + key, required=True)
    for cli in (compile_cli, test_cli):
        for key in ("objects", "new-output-dir"):
            cli.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    result = {}
    try:
        result["status"] = (build if a.mode == "build" else synthetic)(a, out, result)
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", error=str(exc))
    tmp = out / ".receipt.tmp"
    with tmp.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.rename(tmp, out / "receipt.json")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
