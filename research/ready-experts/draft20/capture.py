"""Guard one independent 20B process on the laptop and retain all raw output."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import c118_start_inventory as inv  # noqa: E402
import host_resource_policy as hp  # noqa: E402
import run_bounded as rb  # noqa: E402

INPUT = run_path(HERE / "inputs.py")
need, sha, read, publish = (INPUT[k] for k in ("need", "sha", "read", "publish"))
W = run_path(ROOT / "research/qualification-retake/nvme_admission/window.py")
CAP = 16 * 2**30
PROVIDERS = {
    "libllama.so.0": "717a7e3dc18ae58585c6df1af2454c5b441c171258b7100ae7e11530e02265b8",
    "libggml.so.0": "13765192ba66ecd55305167bd37fcfb8070843318a6a05aa00e738e9d6fe15ea",
    "libggml-cpu.so.0": "8e05100cf1a6711d4a3ef86e0d4a2551cd96269735e46851eb83f7b39bcc3ad5",
    "libggml-base.so.0": "c58db87a08edfe5d499f24c1bdbd3efd844c40368f030282ef750c4e56b52c4d",
    "libggml-cuda.so.0": "7f8c73e8e038a444a96252a1b79f1b83484fadadc2371c118c65f36d44ccd835",
}
PLACEMENT = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
HASH_SCRIPT = """import hashlib, os, sys
with open(sys.argv[1], 'rb', buffering=0) as f:
    h = hashlib.sha256()
    at = 0
    while block := f.read(4 * 2**20):
        h.update(block)
        os.posix_fadvise(f.fileno(), at, len(block), os.POSIX_FADV_DONTNEED)
        at += len(block)
    print(h.hexdigest())
"""


def identify(exe, env):
    log = subprocess.check_output(["/usr/bin/ldd", "-r", exe], env=env, text=True)
    need("not found" not in log and "undefined symbol" not in log, "incomplete dynamic loader")
    paths = dict(re.findall(r"^\s*(\S+) => (/\S+) \(", log, re.M))
    closure = {}
    for name, path in paths.items():
        resolved = Path(path).resolve(strict=True)
        with resolved.open("rb") as f:
            closure[name] = {
                "path": str(resolved),
                "sha256": hashlib.file_digest(f, "sha256").hexdigest(),
            }
    need(all(closure[k]["sha256"] == h for k, h in PROVIDERS.items()), "stock providers")
    return closure


def measure_child(argv, env, out, label, resources, closure=None):
    baseline = rb.cgroup_state()
    guard = hp.RuntimeGuard({"limits": {"max_gap_s": 3}, "resources": resources}, baseline)
    start = time.monotonic()
    rows, mapped = [], False
    with (
        (out / (label + ".stdout")).open("xb") as so,
        (out / (label + ".stderr")).open("xb") as se,
        (out / (label + ".samples.jsonl")).open("x") as telem,
    ):
        child = subprocess.Popen(argv, env=env, stdout=so, stderr=se)
        try:
            ident = rb.process_identity(child.pid)
            need(ident["cgroup_path"] == baseline["path"], "child cgroup")
            while child.poll() is None:
                now = time.monotonic() - start
                if closure and not mapped:
                    maps = Path(f"/proc/{child.pid}/maps").read_text()
                    mapped = all(closure[k]["path"] in maps for k in PROVIDERS)
                gpu = rb.gpu_state(prospective=True)
                thermal = rb.thermal_state(prospective=True)
                cg = rb.cgroup_state()
                proc = rb.proc_status(child.pid)
                if child.poll() is not None:
                    break
                need(proc and gpu and thermal and cg, "required telemetry")
                obs = dict(
                    elapsed_s=now,
                    gpu=gpu,
                    thermal=thermal,
                    cgroup=cg,
                    proc=proc,
                    mem_available_bytes=rb.mem_available(),
                    resource_observation={
                        "host_psi_full_avg10": hp.host_pressure(),
                        "power": hp.live_power(),
                    },
                )
                telem.write(json.dumps(obs, allow_nan=False) + "\n")
                telem.flush()
                reason = guard.check(obs)
                need(reason is None, reason or "resource guard")
                if label == "draft":
                    need(not W["concurrent"](), "competing model, transfer or build")
                need(not rows or 0 < now - rows[-1]["elapsed_s"] <= 3, "monitor cadence")
                rows.append(obs)
                time.sleep(max(0, 0.7 - (time.monotonic() - start - now)))
            need(child.wait() == 0, f"{label} exited {child.returncode}")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
    wall = time.monotonic() - start
    need(
        rows and rows[0]["elapsed_s"] < 3 and wall - rows[-1]["elapsed_s"] < 3, "uncovered process"
    )
    need(closure is None or mapped, "unobserved live providers")
    return dict(
        argv=[str(v) for v in argv],
        process=ident,
        wall_s=wall,
        samples=len(rows),
        live_providers=mapped,
        stdout_sha256=sha(out / (label + ".stdout")),
        stderr_sha256=sha(out / (label + ".stderr")),
        samples_sha256=sha(out / (label + ".samples.jsonl")),
        peak_B=rb.cgroup_state()["memory_peak"],
        max_swap_B=max(r["cgroup"]["swap_current"] for r in rows),
        max_cpu_C=max(r["thermal"]["cpu_tctl_c"] for r in rows),
        max_gpu_C=max(r["gpu"]["temperature_c"] for r in rows),
        max_gpu_MiB=max(r["gpu"]["used_mib"] for r in rows),
        max_nvme_C=max(max(r["thermal"]["nvme_composite_by_sensor"].values()) for r in rows),
        min_available_B=min(r["mem_available_bytes"] for r in rows),
        gpu_sampled_J=sum(
            (b["elapsed_s"] - a["elapsed_s"]) * (b["gpu"]["power_w"] + a["gpu"]["power_w"]) / 2
            for a, b in zip(rows[:-1], rows[1:], strict=True)
        ),
        gpu_covered_s=rows[-1]["elapsed_s"] - rows[0]["elapsed_s"],
    )


def run(a, out):
    need(not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT), "dirty worktree")
    git = subprocess.check_output(
        ["git", "rev-parse", "HEAD", "HEAD^{tree}"], text=True, cwd=ROOT
    ).split()
    assert_inputs = read(a.inputs / "receipt.json")
    need(
        sha(a.inputs / "receipt.json") == a.inputs_sha256
        and all(sha(a.inputs / k) == h for k, h in assert_inputs["files"].items()),
        "input identity",
    )
    window = read(a.c55 / "receipt.json")
    policy = read(a.c55 / "resource-policy.json")
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(
        sha(a.c55 / "receipt.json") == a.c55_sha256
        and window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not window["reason"]
        and window["span_s"] >= 60
        and 0 <= age < 3600
        and sha(a.c55 / "resource-policy.json") == window["canonical_policy_sha256"]
        and sha(a.c55 / "samples.jsonl") == window["window_sha256"]
        and hp.derive_policy(snapshot=policy["snapshot"]) == policy
        and hp.operational_session_ready(policy)[0],
        "fresh C55",
    )
    resources = hp.freeze_protocol_resource_limits(policy, cgroup_memory_max_bytes=CAP)
    cg = rb.cgroup_state()
    need(
        (cg["memory_high"], cg["memory_max"], cg["swap_max"], cg["swap_current"])
        == (CAP, CAP, 0, 0),
        "unexpected resource scope",
    )
    env = dict(
        PATH="/usr/bin:/bin", LANG="C", LC_ALL="C", CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="8"
    )
    need(
        sha(a.exe) == a.exe_sha256 and sha(a.placement) == PLACEMENT, "binary or placement changed"
    )
    providers = identify(a.exe, env)
    locked = {m["id"]: m for m in read(ROOT / "models.lock.json")["models"]}
    small, large = (
        locked[k]["sha256_verified"] for k in ("gpt-oss-20b-mxfp4-gguf", "gpt-oss-120b-mxfp4-gguf")
    )
    target, draft = W["stat_id"](a.target), W["stat_id"](a.draft)
    placement = read(a.placement)
    original = [
        placement["model_stat"][k] for k in ("dev", "inode", "size_bytes", "mtime_ns", "ctime_ns")
    ]
    need(
        target == window["selected_stat"] == original
        and placement["model_sha256"] == large
        and draft[2] == locked["gpt-oss-20b-mxfp4-gguf"]["bytes"],
        "GGUF identities",
    )
    proof = dict(
        commit=git[0],
        tree=git[1],
        input_sha256=a.inputs_sha256,
        c55_sha256=a.c55_sha256,
        binary_sha256=a.exe_sha256,
        providers=providers,
        scope=cg["path"],
        c55_age_s=age,
        model_sha256={"draft": small, "target": large},
        stats={"draft": draft, "target": target},
        mounts={"draft": W["mount"](a.draft), "target": W["mount"](a.target)},
        protocol_sha256=sha(HERE / ("joint/protocol.md" if a.terminal_code else "protocol.md")),
        argv=sys.argv,
        env=env,
    )
    publish(out / "provenance.json", proof)
    (out / "raw").mkdir()
    hashed = measure_child(
        ["/usr/bin/python3", "-IB", "-c", HASH_SCRIPT, a.draft], env, out, "hash", resources
    )
    need(
        (out / "hash.stdout").read_text().strip() == small and W["stat_id"](a.draft) == draft,
        "20B full digest",
    )
    power = {"source": "AC", "profile": "performance"}
    inventory = inv.collect(out, out.name, policy=policy, cap_bytes=CAP, expected_power=power)
    publish(out / "inventory.json", inventory)
    need(not W["concurrent"](), "competing work at launch")
    inv.require_inventory(
        out, out.name, inventory, policy=policy, cap_bytes=CAP, expected_power=power
    )
    cmd = [a.exe, a.target, a.draft, a.inputs]
    if a.terminal_code:
        cmd.append("--terminal-code")
    execution = measure_child(cmd, env, out, "draft", resources, providers)
    need(
        W["stat_id"](a.target) == target
        and W["stat_id"](a.draft) == draft
        and (out / "draft.stdout").read_text().endswith("done\n"),
        "incomplete capture",
    )
    return dict(
        status="MEASURED_20B_TERMINAL" if a.terminal_code else "MEASURED_20B_STANDALONE",
        hash=hashed,
        execution=execution,
        c118_s=inventory["duration_s"],
        provenance_sha256=sha(out / "provenance.json"),
        forwards_120b=0,
        gpu_forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("exe", "target", "draft", "placement", "inputs", "c55", "new-output-dir"):
        p.add_argument("--" + arg, type=Path, required=True)
    for arg in ("exe", "inputs", "c55"):
        p.add_argument("--" + arg + "-sha256", required=True)
    p.add_argument("--terminal-code", action="store_true")
    a = p.parse_args()
    out = a.new_output_dir
    os.umask(0o077)
    out.mkdir()
    try:
        with (out.parent / "tesy-draft20.lock").open("a") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = run(a, out)
    except Exception as exc:
        publish(out / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    raw_bytes = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    if raw_bytes >= 32 * 2**20:
        publish(out / "failure.json", dict(status="FAIL_PRESERVED", reason="output limit"))
        raise ValueError("output limit")
    publish(out / "receipt.json", result | dict(raw_bytes=raw_bytes))
    print(result["status"])
