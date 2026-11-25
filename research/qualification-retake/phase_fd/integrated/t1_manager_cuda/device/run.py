"""Run a frozen five-process C269 CUDA family under C55/C118 and a bounded scope."""

import argparse
import json
import math
import os
import select
import signal
import struct
import subprocess
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
builder = run_path(str(HERE / "build.py"))
checker = run_path(str(HERE.parent / "check.py"))
need, sha = builder["need"], builder["sha"]
SERVICE = HERE.parent.parent / "t1_native_sink"
RAM_AUTHORITY = "2a90de37b6ae809e9de63cd47ddabac192e743a2c44b037a0f472aa626d208bb"


def save(p, obj):
    tmp = p.with_suffix(".pending")
    with tmp.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    os.link(tmp, p)
    tmp.unlink()


def parse(stdout, arm, p):
    lines = stdout.read_text().splitlines()
    projections = "PROJECTIONS 3"
    placement = "GPU_PLACEMENT 3 1 1 1"
    expected = [
        projections,
        placement,
        f"PROVIDER ggml_backend_cpu_init {p['libggml-cpu.so.0']}",
        f"PROVIDER ggml_backend_tensor_set {p['libggml-base.so.0']}",
    ]
    if arm == "event":
        expected.append("GPU_EVENT_COMPLETED")
    for line in expected:
        need(lines.count(line) == 1, "placement, event or symbols")
        lines.remove(line)
    return lines


def verify_maps(directory, paths):
    allowed = {str(p) for p in paths.values()}
    base = {str(paths[n]) for n in ("libggml-cpu.so.0", "libggml-cuda.so.0", "libggml-base.so.0")}
    cuda_active = base | {
        str(paths[n]) for n in ("libcuda.so.1", "libcudart.so.13", "libcublas.so.13")
    }
    receipts = {}
    for phase in ("start", "active", "finish", "drain"):
        src = directory / (phase + ".providers")
        seen = set(src.read_text().splitlines())
        required = cuda_active if phase in ("active", "finish") else base
        need(required <= seen <= allowed, f"incomplete providers at {phase}")
        receipts[phase] = sha(src)
    return receipts


def case(out, arm, unit, build, io, policy, cold, monitor_sample, paths):
    inv = cold["c135"]
    raw = out / "raw"
    run_id = unit + "-" + arm
    kw = dict(policy=policy, cap_bytes=io.CAP, expected_power=inv.POWER)
    inventory = inv.collect(out, run_id, **kw, sample=lambda: io.monitor(policy)["observation"])
    inv.require_inventory(out, run_id, inventory, **kw)
    save(out / (arm + "-inventory.json"), inventory)
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=str(build / "libs"),
        CUDA_VISIBLE_DEVICES="0",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        TESY_FIXTURE_MAP=str(build / "allowed.tsv"),
    )
    outlog = raw / (arm + ".stdout")
    mon = raw / (arm + ".monitor.jsonl")
    rfd, wfd = os.pipe()
    ack_r, ack_w = os.pipe()
    start = time.monotonic()
    stage = 0
    samples = 0
    last_sample = start
    try:
        with ExitStack() as stack:
            stdout = stack.enter_context(outlog.open("xb"))
            stderr = stack.enter_context((raw / (arm + ".stderr")).open("xb"))
            monitor = stack.enter_context(mon.open("x"))
            child = subprocess.Popen(
                [build / "device", arm, out / arm],
                stdout=stdout,
                stderr=stderr,
                env=env | dict(TESY_TEST_TX=str(wfd), TESY_TEST_RX=str(ack_r)),
                pass_fds=(wfd, ack_r),
            )
            os.close(wfd)
            wfd = -1
            os.close(ack_r)
            ack_r = -1
            try:

                def sample(require_owner):
                    nonlocal last_sample, samples
                    row = io.monitor(
                        policy,
                        sample=lambda: monitor_sample(
                            child.pid, policy["gpu"]["uuid"], require_owner
                        ),
                    )
                    need(row["observation"]["gpu"]["used_mib"] < 1536, "VRAM cap")
                    now = time.monotonic()
                    need(now - last_sample <= 5.0, "service monitor gap")
                    row.update(stage=stage, elapsed_s=now - start)
                    cold["append_row"](monitor, row)
                    last_sample = now
                    samples += 1

                while child.poll() is None:
                    need(time.monotonic() - start < 30, "child deadline")
                    if select.select([rfd], [], [], 0.25)[0]:
                        marker = os.read(rfd, 1)
                        if not marker:
                            break
                        need(stage < 2 and marker == (b"A", b"F")[stage], "monitor handoff order")
                        sample(True)
                        os.write(ack_w, marker)
                        stage += 1
                    elif time.monotonic() - last_sample >= 0.5:
                        sample(False)
                rc = child.wait(timeout=max(0.001, 30 - (time.monotonic() - start)))
                need(rc == 0 and stage == 2, f"{arm} closed at stage {stage} exit {rc}")
                sample(False)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=3)
    finally:
        for fd in (rfd, wfd, ack_r, ack_w):
            if fd >= 0:
                os.close(fd)
    return dict(
        wall_s=time.monotonic() - start,
        monitor_sha256=sha(mon),
        service_samples=samples,
        start_inventory_sha256=inventory["sha256"],
        inventory_samples=inventory["sample_count"],
        inventory_s=inventory["duration_s"],
        stdout_sha256=sha(outlog),
        providers=verify_maps(out / arm, paths),
        journal=parse(outlog, arm, paths),
    )


def execute(a, out, r):
    r.update(commit=a.commit, tree=builder["freeze"](a.commit), protocol_sha256=builder["PROTOCOL"])
    cold = run_path(str(SERVICE.parent / "cold_read_fixture/runner.py"))
    io = cold["io"]
    io.CAP, io.STOPS = 2**31, 1856 * 2**20
    io.scope()
    need(io.cgroup_state()["path"].endswith("/" + a.unit + ".scope"), "scope name")
    prior = cold["load"](a.ram_receipt, RAM_AUTHORITY)
    profile = run_path(str(cold["QUAL"] / "packed_layer_service/profile.py"))
    provider, unchanged = profile["monitor_provider"](SimpleNamespace(token=io.stat_id))
    need(
        provider == prior["monitor_provider"]
        and Path("/sys/module/nvidia/version").read_text().strip() == "620.70.06",
        "NVML/driver identity",
    )
    load = cold["load"]
    gate = load(a.c55, a.c55_sha256)
    policy = load(a.c55.with_name("resource-policy.json"), gate["canonical_policy_sha256"])
    need(
        gate["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not gate["reason"]
        and policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0],
        "C55",
    )
    build = a.build_dir.resolve()
    receipt = load(build / "receipt.json", a.build_sha256)
    need(
        receipt["status"] == "PASS_DEVICE_BUILD_ONLY"
        and receipt["commit"] == a.commit
        and receipt["tree"] == r["tree"]
        and receipt["protocol_sha256"] == builder["PROTOCOL"]
        and receipt["source_sha256"] == builder["digest"](builder["source"]()),
        "frozen build",
    )
    paths, files = builder["providers"](a.map)

    def authenticated():
        need(
            sha(build / "device") == receipt["binary_sha256"]
            and sha(build / "allowed.tsv") == receipt["allow_sha256"]
            and {p.name: p.resolve(strict=True) for p in (build / "libs").iterdir()} == paths,
            "fixture executable/aliases",
        )
        builder["verify_files"](paths, files)
        unchanged()

    authenticated()
    active = run_path(str(SERVICE / "measure.py"))["active_sample"]
    r.update(
        unit=a.unit,
        build_sha256=a.build_sha256,
        c55_sha256=a.c55_sha256,
        provider=provider,
        arms={},
    )
    (out / "raw").mkdir()
    for name in checker["ARMS"]:
        age = (
            datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])
        ).total_seconds()
        need(0 <= age < 3300 - 65, "fresh C55 through next C118")
        s = case(out, name, a.unit, build, io, policy, cold, active, paths)
        r["arms"][name] = s
        # Validate OLD before investing in NEW. After NEW, the isolated pair
        # supplies the bitwise references for all three interleavings.
        root = out / name
        ffn = (root / "out.f32").read_bytes()
        if name == "old":
            old = ffn
            need(
                not (root / "bank.mxfp4").exists() and not (root / "token.f32").exists(),
                "unexpected isolated witness",
            )
            values = struct.unpack("<32f", ffn)
            need(
                all(math.isfinite(v) and abs(v - checker["scalar"](1)) <= 0.0001 for v in values),
                "old isolated scalar reference",
            )
        else:
            if name == "new":
                new = ffn
                old_root = out / "old"
                r["arms"]["old"].update(
                    checker["verify_arm"](
                        "old",
                        (old_root / "slots.mxfp4").read_bytes(),
                        None,
                        old,
                        None,
                        r["arms"]["old"]["journal"],
                        old,
                        new,
                    )
                )
            bank = root / "bank.mxfp4"
            token = root / "token.f32"
            s.update(
                checker["verify_arm"](
                    name,
                    (root / "slots.mxfp4").read_bytes(),
                    bank.read_bytes() if bank.exists() else None,
                    ffn,
                    token.read_bytes() if token.exists() else None,
                    s["journal"],
                    old,
                    new,
                )
            )
        unchanged()
    authenticated()
    r.update(
        status="PASS_CUDA_WAVE_FIXTURE_ONLY",
        peak_bytes=io.scope(),
        model_forwards=0,
        scope_cap=io.CAP,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("commit", "unit", "build-sha256", "c55-sha256"):
        p.add_argument("--" + k, required=True)
    for k in ("build-dir", "c55", "ram-receipt", "map", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = {}

    def timeout(*_):
        raise TimeoutError("family deadline")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(480)
    try:
        execute(a, out, r)
    except (ValueError, KeyError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
