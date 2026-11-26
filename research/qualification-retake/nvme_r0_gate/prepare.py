"""Freeze a single C269 R0 selected bridge with existing clients, monitor and independent gold."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools"))
from c55_inventory import mounts  # noqa: E402
from c94_session_wave_8k_reference import tree_digest  # noqa: E402
from host_resource_policy import (  # noqa: E402
    freeze_protocol_resource_limits,
    validate_resource_protocol,
)
from parallel_runtime import parallel_environment  # noqa: E402
from run_bounded import backend_library_hashes, file_identity, sha256  # noqa: E402

BASE = REPO / "results/c270-last-use-ordered-fidelity-20261004/protocol.json"
REF = REPO / "results/c127-slots40-numeric-20260929T1654Z"
C281 = REPO / "results/c281-persistent-r0-runtime-20261005/protocols/c281-r0-persistent.json"
C281_ELF = HERE.parent / "elf-evidence/receipt.json"
MODEL_SHA = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
CAPS = {"E20_R0": 20 * 1024**3, "E18_DIAGNOSTIC_ONLY": 18 * 1024**3}
MIB = 1024**2


def load(path):
    return json.loads(path.read_bytes())


def save(path, obj):
    with path.open("x") as stream:
        json.dump(obj, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def git(root, *args):
    return subprocess.check_output(["git", "-C", root, *args], text=True).strip()


def ldd_environment(library_path=None):
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
    if library_path is not None:
        check(
            all(Path(p).is_absolute() for p in library_path.split(os.pathsep)),
            "ldd search must contain only absolute directories",
        )
        env["LD_LIBRARY_PATH"] = library_path
    return env


def seal(*, ldd_library_path=None):
    check(
        sha256(BASE) == "10ee7ec18d4b7d1d44b80eca7dbc2ff2a48ccebdd83bc2c73dadc26289f6a616",
        "C270 changed",
    )
    check(
        sha256(REF / "manifest.json")
        == "cdb9201a72809a5acc2991f4d548eb675c8a6344e2d018a2f51979393fdce581",
        "C127 changed",
    )
    p = load(BASE)
    r = p["runs"][0]
    check(
        r["id"] == "c270-r0"
        and r["env"] == {}
        and p["common_env"] == {"TESY_CPU_WAVE_SKIP_PARKED": "1"},
        "incorrect arm",
    )
    exe, model, ids = map(Path, r["command"][:3])
    backend = Path(p["backend_root"]).resolve(strict=True)
    for path in [exe, ids]:
        check(sha256(path) == p["file_sha256"][str(path)], "input identity differs")
    check(
        git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [p["backend_commit"], p["backend_tree"]]
        and git(backend, "status", "--porcelain") == "",
        "backend tree differs",
    )
    ref = Path(r["post_run_command"][-1])
    gold = tree_digest(ref)
    check(gold == load(REF / "manifest.json")["capture_trees"]["on"], "gold tree differs")
    libs = backend_library_hashes(exe, backend)
    check(libs == p["binary_libraries"], "numerical libraries differ")
    server = load(C281)
    check(
        all(server["identity"]["library_sha256"].get(k) == v for k, v in libs.items())
        and len(libs) == 5,
        "C270 numerical libraries differ from persistent server",
    )
    rows = load(C281_ELF)["selected_frozen_and_unpinned"]
    expected = {row["resolved_file"]: row["resolved_sha256"] for row in rows}
    ldd = subprocess.check_output(
        ["ldd", exe], text=True, env=ldd_environment(ldd_library_path)
    )
    check("not found" not in ldd, "missing capture DSO")
    actual = {}
    for line in ldd.splitlines():
        if "=>" in line:
            path = Path(line.split("=>")[1].split()[0]).resolve(strict=True)
            check(
                expected.get(path.name) == sha256(path),
                "current object differs from prepared server inventory",
            )
            actual[str(path)] = expected[path.name]
    gomp = {k: v for k, v in actual.items() if Path(k).name.startswith("libgomp")}
    check(len(gomp) == 1, "one OpenMP required")
    seal = {
        "capture_sha256": sha256(exe),
        "ids_sha256": sha256(ids),
        "backend_commit": p["backend_commit"],
        "backend_tree": p["backend_tree"],
        "gold": gold,
        "model_sha256": MODEL_SHA,
        "gold_full_logits_sha256": {
            f.stem.split(".")[0]: sha256(f) for f in sorted(ref.glob("*.logits.f32"))
        },
        "numerical_dso_sha256": {Path(k).name: v for k, v in libs.items()},
        "startup_dso_sha256": {Path(k).name: v for k, v in actual.items()},
        "server_sha256": server["identity"]["binary_sha256"],
        "protocol_sha256": sha256(HERE / "protocol.md"),
    }
    return seal, (exe, model, ids, backend, ref, gomp)


def admit(window, policy, policy_sha, envelope):
    cap = CAPS[envelope]
    check(
        window["status"] in ("PASS_RESOURCE_WINDOW_ONLY", "NOT_ADMITTED"), "incomplete C55 window"
    )
    allowed_reasons = (
        set()
        if envelope == "E20_R0"
        else {"C55_CAP_UNAVAILABLE", "HOST_CAP_PLUS_RESERVE_UNAVAILABLE"}
    )
    check(
        policy_sha == window["canonical_policy_sha256"],
        "C55 digest differs",
    )
    available = min(
        window["canonical_memory"]["cap_max_bytes"],
        window["memory"]["cap_max_bytes"],
        policy["memory"]["cap_max_bytes"],
    )
    check(
        not set(window["reason"]) - allowed_reasons and available >= cap,
        f"C55 did not admit {envelope} (cap {available})",
    )


def freeze(a, out, sealed, paths):
    exe, model, ids, backend, ref, gomp = paths
    check(
        git(REPO, "rev-parse", "HEAD") == a.measurement_commit
        and not git(REPO, "status", "--porcelain"),
        "measurement tree not clean",
    )
    expected_inputs = load(HERE / "inputs/receipt.json")
    check(
        expected_inputs == {"status": "PASS_INPUTS_ONLY", "model_forwards": 0, **sealed},
        "prepared input identity changed",
    )
    window = load(a.window / "receipt.json")
    policy = load(a.window / "resource-policy.json")
    cap = CAPS[a.envelope]
    admit(window, policy, sha256(a.window / "resource-policy.json"), a.envelope)
    placement = load(HERE.parent / "nvme_placement/receipt.json")
    check(sha256(a.placement) == placement["raw_receipt_sha256"], "placement receipt changed")
    live = load(a.placement)
    stat = file_identity(model)
    mounts({"model": model.resolve()})
    check(
        live["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and model.samefile(live["working_copy"])
        and live["destination_direct_reread"]["sha256"] == MODEL_SHA
        and [stat[k] for k in ("dev", "inode", "size_bytes", "mtime_ns", "ctime_ns")]
        == window["selected_stat"],
        "model identity changed",
    )
    check(shutil.disk_usage(out).free >= 10 * 1024**3 + 128 * MIB, "raw reserve unavailable")
    raw = out / "raw"
    raw.mkdir()
    shutil.copyfile(a.window / "resource-policy.json", out / "resource-policy.json")
    protocol = {
        "schema": "tesy-nvme-r0-c270-requalification-v1",
        "envelope": a.envelope,
        "limits": {},
        "execution_scope_unit": a.unit,
        "start_inventory": {
            "schema": "c120-start-inventory-v1",
            "duration_s": 60,
            "max_age_s": 3,
            "policy_sha256": sha256(out / "resource-policy.json"),
        },
        "parallel_runtime": {
            "schema": "parallel-runtime-v1",
            "environment": parallel_environment({}),
            "libraries_sha256": gomp,
        },
        "resources": freeze_protocol_resource_limits(
            policy, cgroup_memory_max_bytes=cap, start_mode="CAUSAL_AB_START"
        ),
        "pinned": sealed,
        "model_stat": stat,
        "measurement_commit": a.measurement_commit,
        "runner_sha256": sha256(REPO / "tools/run_bounded.py"),
        "gate_sha256": sha256(REPO / "tools/block_layer_reuse_gate.py"),
    }
    validate_resource_protocol(protocol)
    save(out / "protocol.json", protocol)
    capture = raw / (a.unit + ".capture")
    monitor = [
        "systemd-run",
        "--user",
        "--wait",
        "--collect",
        "--pipe",
        "--service-type=exec",
        "--unit=" + a.unit,
        "-p",
        "MemoryMax=" + str(cap),
        "-p",
        "MemoryHigh=" + str(cap),
        "-p",
        "MemorySwapMax=0",
        "-p",
        "RuntimeMaxSec=315s",
        "-p",
        "TimeoutStopSec=3s",
        "-p",
        "LimitFSIZE=8388608",
        "--",
        "/usr/bin/env",
        "-i",
        "PATH=/usr/bin:/bin",
        "LC_ALL=C",
        "HOME=" + str(Path.home()),
        "/usr/bin/python3",
        "-B",
        REPO / "tools/run_bounded.py",
        "--run-id",
        a.unit,
        "--model-id",
        "gpt-oss-120b-mxfp4-gguf",
        "--backend",
        "streaming",
        "--backend-root",
        backend,
        "--output-root",
        raw,
        "--variant",
        "C269-R0-selected189+32-" + a.envelope,
        "--workload",
        ids,
        "--cache-condition",
        "fresh-pools-uncontrolled-page-cache",
        "--timeout-s",
        "240",
        "--resource-protocol",
        out / "protocol.json",
        "--collect-start-inventory",
        "--require-telemetry",
        "--env",
        "TESY_CPU_WAVE_SKIP_PARKED=1",
        "--",
        exe,
        model,
        ids,
        capture,
        "--ngl",
        "12",
    ]
    gate = [
        sys.executable,
        "-B",
        REPO / "tools/block_layer_reuse_gate.py",
        capture,
        "--output",
        out / "selected.json",
        "--bridge-reference",
        ref,
    ]
    save(out / "argv.json", {"monitor": list(map(str, monitor)), "check": list(map(str, gate))})
    return {
        "status": "PREPARED_ONLY",
        "model_forwards": 0,
        "monitor_sha256": protocol["runner_sha256"],
        "model_stat": stat,
        "protocol_sha256": sha256(out / "protocol.json"),
        "argv_sha256": sha256(out / "argv.json"),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new-output-dir", required=True, type=Path)
    p.add_argument("--envelope", choices=tuple(CAPS))
    p.add_argument("--execute", action="store_true")
    p.add_argument("--window", type=Path)
    p.add_argument("--placement", type=Path)
    p.add_argument("--unit")
    p.add_argument("--measurement-commit")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        sealed, paths = seal()
        if a.window:
            check(
                a.envelope
                and a.placement
                and a.unit
                and a.unit.startswith("tesy-")
                and a.unit.replace("-", "").isalnum()
                and a.measurement_commit,
                "missing invocation metadata",
            )
            result = freeze(a, out, sealed, paths)
            if a.execute:
                from measure import execute

                result = execute(out, a.unit, a.envelope, sealed)
        else:
            check(not a.execute, "execution needs a fresh C55 window and explicit envelope")
            result = {"status": "PASS_INPUTS_ONLY", "model_forwards": 0, **sealed}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        result = {"status": "NOT_PREPARED", "model_forwards": 0, "reason": str(exc)}
    save(out / "receipt.json", result)
    print(result["status"], result.get("reason", ""))
    raise SystemExit(
        int(
            result["status"]
            not in {"PASS_INPUTS_ONLY", "PREPARED_ONLY", "PASS_SELECTED_C269_BRIDGE"}
        )
    )
