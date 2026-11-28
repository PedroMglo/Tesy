"""Check a read-only, 1,252-frame CPU expert arena against the native GGML control."""

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SUPPLIED = HERE.parents[6] / "cpu_wave/supplied"
SHARED = run_path(SUPPLIED / "slot_layout.py")
mm, G, CAP = (SHARED[k] for k in ("mm", "G", "CAP"))
need, sha = mm.need, mm.sha
REFERENCE = "5d91469ac8c7866cb0b946278657253b4bed59f414ccf7facd658168c137e9d0"
SOURCE = "f8e9459e2fa8c1112a9ec6d0b1c896eb858dc590d301f8a9ad7df23c2f5e7c0e"
METHOD = "348c93e1d9078186bb29fe79c02d0736bdca976b720c780d3c2cf36da94e0e3a"
OWNERS = "7d41b3084e0051ffba6f5c65bef34b6cdd1dae0ddf89f63ef3af2acf826a7e95"
ROLES = {"PLANAR": (40, 15, 13, 0), "SWAP": (1252, 0, 1249, 1), "STALE": (1252, 0, 13, 1)}
STRIDE = 13221888
HALF = 2880 * 4 * (1 + 20 + 32) * 3 * 4


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open("x") as f:
        json.dump(data, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def reference():
    original = SUPPLIED / "slot-result.json"
    need(sha(original) == REFERENCE, "independent, earlier word reference")
    return read(original)["arms"]["A"]


def materialize():
    p = SUPPLIED / "slot_layout.cpp"
    need(sha(p) == SOURCE, "original MXFP4 graph and deterministic matrices")
    native = p.read_text()
    before, graph = native.split("void make_input(", 1)
    graph = graph.split("void calculate(", 1)[1].split("\nint run(", 1)[0]
    code = before.replace('#include "c291-direct-reader.h"\n', "") + "void calculate(" + graph
    for old, new in (
        ("FILE *output) {", "FILE *output, const std::array<int32_t, ranks> &live) {"),
        ("routing[i] = slot_ids[", "routing[i] = live["),
    ):
        need(code.count(old) == 1, "authenticated routing hook")
        code = code.replace(old, new)
    return code + (HERE / "operator.cpp.in").read_text()


def check_arm(role, arm, control):
    count, sets, frame, readonly = ROLES[role]
    need(
        (
            arm["frames"],
            arm["arena_virtual_B"],
            arm["weight_sets"],
            arm["final_rank1_frame"],
            arm["protected_read_only"],
        )
        == (count, count * STRIDE, sets, frame, readonly)
        and arm["bytes"] == 2 * HALF,
        "geometry, weight writes, protection or complete output",
    )
    first, second = control["generation_sha256"]
    need(first != second and control["bytes"] == 2 * HALF, "reference discriminates generations")
    if role == "STALE":
        need(
            arm["generation_sha256"] == [first, first] and arm["sha256"] != control["sha256"],
            "missed replacement must corrupt generation two only",
        )
    else:
        need(
            arm["generation_sha256"] == [first, second] and arm["sha256"] == control["sha256"],
            "all finite projection words must agree with historical planar control",
        )


def verify(rec):
    need(
        rec["status"] == "GO_NATIVE_CPU_FRAME_PROMOTION"
        and rec["method"] == METHOD
        and rec["owners"] == OWNERS
        and rec["reference"] == REFERENCE
        and rec["backend"] == mm.PIN
        and rec["libraries"] == {mm.CPU: mm.CPU_SHA, mm.BASE: mm.BASE_SHA}
        and rec["cmp_all_bytes"]
        and rec["swap_peak_B"] == 0
        and 0 < rec["memory_peak_B"] <= CAP
        and rec["actual_output_B"] < 128 << 20
        and rec["window_status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and rec["model_forwards"] == 0
        and rec["gpu_forwards"] == 0
        and rec["HTTP_requests"] == 0
        and set(rec["arms"]) == set(ROLES),
        "native receipt",
    )
    for role, arm in rec["arms"].items():
        check_arm(role, arm, reference())


def physical(a, out, rec):
    root = SHARED["ROOT"]
    group = SHARED["BUILD"]["cgroup"](CAP)
    gates = read(a.window / "receipt.json")
    policy = read(a.window / "resource-policy.json")
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    ownership = HERE / "evidence-frames-20261128-r01/frames.json"
    need(
        mm.git(root, "rev-parse", "HEAD") == a.commit
        and not mm.git(root, "status", "--porcelain")
        and mm.git(a.backend, "rev-parse", "HEAD") == mm.PIN
        and not mm.git(a.backend, "status", "--porcelain")
        and sha(HERE / "operator-protocol.md") == METHOD
        and sha(ownership) == OWNERS
        and read(ownership)["status"] == "GO_CPU_OPERATOR_FIXTURE",
        "clean source and admitted representation",
    )
    need(
        sha(a.window / "receipt.json") == a.window_sha256
        and gates["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "resource-policy.json") == gates["canonical_policy_sha256"]
        and sha(a.window / "samples.jsonl") == gates["window_sha256"]
        and 0 <= age < 3600
        and G["operational_session_ready"](policy)[0]
        and not G["concurrent"](),
        "authenticated, recent physical window",
    )
    control = reference()
    libs = a.backend / "build-c269-cuda/bin"
    pins = {k: sha(libs / k) for k in (mm.CPU, mm.BASE)}
    cc = "/usr/bin/g++-15"
    old = read(SUPPLIED / "slot-result.json")
    need(pins == old["libraries"] and sha(cc) == old["compiler_sha256"], "toolchain")
    source, exe = out / "frame.cpp", out / "fixture"
    with source.open("x") as f:
        f.write(materialize())
    rec.update(
        commit=a.commit,
        tree=mm.git(root, "rev-parse", "HEAD^{tree}"),
        method=METHOD,
        owners=OWNERS,
        reference=REFERENCE,
        backend=mm.PIN,
        libraries=pins,
        compiler_sha256=sha(cc),
        source_sha256=sha(source),
        original_graph_sha256=SOURCE,
        window_sha256=a.window_sha256,
        window_status=gates["status"],
        window_age_s=age,
        cpu=gates["cpu"],
        gpu=gates["gpu_name"],
        gpu_driver=gates["gpu_driver"],
        disk=G["disk"](out, "nvme").parent.name,
        host=os.uname().nodename,
        kernel=os.uname().release,
        power=policy["snapshot"]["power"],
        caps=dict(memory_B=CAP, swap_B=0, output_B=128 << 20, wall_s=180),
        model_forwards=0,
        gpu_forwards=0,
        HTTP_requests=0,
        energy_J=None,
        arms={},
    )
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        TMPDIR=str(out),
        LD_LIBRARY_PATH=str(libs),
        OMP_NUM_THREADS="8",
        OMP_DYNAMIC="FALSE",
    )
    start = time.monotonic()
    maxima = {}

    def sample():
        obs = G["live_sample"]()
        G["validate_sample"](
            obs,
            policy=policy,
            cap_bytes=CAP,
            expected_power={"source": "AC", "profile": "performance"},
        )
        need(G["host_pressure"]() < 10 and time.monotonic() - start < 180, "pressure or deadline")
        with (out / "telemetry.jsonl").open("a") as f:
            f.write(json.dumps(obs, allow_nan=False) + "\n")
        for name, value in {
            "cpu_c": obs["thermal"]["cpu_tctl_c"],
            "gpu_c": obs["gpu"]["temperature_c"],
            "nvme_c": max(obs["thermal"]["nvme_composite_by_sensor"].values()),
        }.items():
            maxima[name] = max(value, maxima.get(name, value))

    def invoke(argv, label):
        rec["stage"] = label
        with (out / (label + ".log")).open("xb") as log:
            with subprocess.Popen(
                argv, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT
            ) as proc:
                try:
                    while proc.poll() is None:
                        sample()
                        try:
                            proc.wait(0.3)
                        except subprocess.TimeoutExpired:
                            pass
                finally:
                    if proc.poll() is None:
                        proc.kill()
                need(proc.wait() == 0, "native failure in " + label)

    rec["compile_command"] = list(
        map(
            str,
            [
                cc,
                "-std=c++20",
                "-O2",
                "-pthread",
                "-I" + str(a.backend / "ggml/include"),
                source,
                libs / mm.CPU,
                libs / mm.BASE,
                "-o",
                exe,
            ],
        )
    )
    invoke(rec["compile_command"], "compile")
    rec["elf_sha256"] = sha(exe)
    rec["loaded_providers"] = mm.loader(
        exe, env, {"libggml-cpu.so.0": libs / mm.CPU, "libggml-base.so.0": libs / mm.BASE}
    )
    write(out / "provenance.json", rec)
    for role in ROLES:
        path = out / (role + ".f32")
        invoke([exe, role, path], role)
        label, count, arena, sets, frame, readonly = (out / (role + ".log")).read_text().split()
        need(label == role, "arm name")
        words = path.read_bytes()
        arm = dict(
            frames=int(count),
            arena_virtual_B=int(arena),
            weight_sets=int(sets),
            final_rank1_frame=int(frame),
            protected_read_only=int(readonly),
            bytes=len(words),
            sha256=sha(path),
            generation_sha256=[hashlib.sha256(b).hexdigest() for b in (words[:HALF], words[HALF:])],
        )
        rec["arms"][role] = arm
        check_arm(role, arm, control)
    rec["cmp_all_bytes"] = (out / "PLANAR.f32").read_bytes() == (out / "SWAP.f32").read_bytes()
    sample()
    events = dict(line.split() for line in (group / "memory.events.local").read_text().splitlines())
    need(not any(int(events[k]) for k in ("high", "max", "oom", "oom_kill")), "memory event")
    rec.update(
        status="GO_NATIVE_CPU_FRAME_PROMOTION",
        memory_peak_B=int((group / "memory.peak").read_text()),
        swap_peak_B=int((group / "memory.swap.peak").read_text()),
        maxima=maxima,
        elapsed_s=time.monotonic() - start,
        telemetry_sha256=sha(out / "telemetry.jsonl"),
        actual_output_B=sum(p.stat().st_size for p in out.iterdir()),
    )
    verify(rec)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("check").add_argument("receipt", type=Path)
    run = modes.add_parser("physical")
    for key in ("backend", "window", "new-output-dir"):
        run.add_argument("--" + key, type=Path, required=True)
    for key in ("commit", "window-sha256"):
        run.add_argument("--" + key, required=True)
    a = parser.parse_args()
    if a.mode == "check":
        verify(read(a.receipt))
        print("PASS native CPU frame receipt")
        return
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    rec = {"status": "FAIL_PRESERVED"}
    try:
        physical(a, out, rec)
    except Exception as exc:
        rec.update(status="FAIL_PRESERVED", error=repr(exc))
    write(out / ".receipt.tmp", rec)
    (out / ".receipt.tmp").rename(out / "receipt.json")
    print(rec["status"], rec.get("error", ""))
    raise SystemExit(rec["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    main()
