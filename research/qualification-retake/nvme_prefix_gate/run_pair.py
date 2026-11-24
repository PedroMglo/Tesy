"""Run the separate, bounded NVMe canary only after a qualified C55 window."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

from gate import C110, DIGEST, HERE, IDS, REPO, SIZE, compare_rows, numerical, reference, require
from prepare import sha

sys.path.insert(0, str(REPO / "tools"))
from c55_inventory import mounts  # noqa: E402
from host_resource_policy import freeze_protocol_resource_limits  # noqa: E402
from parallel_runtime import parallel_environment  # noqa: E402
from run_bounded import backend_library_hashes, file_identity  # noqa: E402

MODEL_ID = "gpt-oss-120b-mxfp4-gguf"
MODEL_SHA = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
CAP = 27 * (1024**3) // 2
MAX_BYTES = 64 * 1024**2
RECEIPT = HERE / "attempt-02/receipt.json"
PREPARED = "56d6db87ac18b40407b0b6c55bac3898e5c65aaefc623d233e803ac14297878a"
PIN = "237e3b8789650fd68b97641c5b8e259d198ed3b1"


class Profile(NamedTuple):
    slots: int
    cap: int
    directory: Path
    build_receipt: Path
    receipt_sha256: str


SLOTS32 = Profile(32, CAP, HERE, RECEIPT, PREPARED)


def load(path):
    return json.loads(path.read_bytes())


def publish(path, data):
    tmp = path.parent / (path.name + ".part")
    with tmp.open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    tmp.replace(path)


def git(root, *args):
    return subprocess.check_output(["git", "-C", root, *args], text=True).strip()


class NotAdmitted(ValueError):
    pass


def admit_window(window, policy, policy_digest, cap=CAP):
    require(
        window["status"] in ("NOT_ADMITTED", "PASS_RESOURCE_WINDOW_ONLY"),
        "incomplete C55 inventory",
    )
    require(policy_digest == window["canonical_policy_sha256"], "policy digest mismatch")
    reasons = set(window["reason"]) - {"C55_CAP_UNAVAILABLE", "HOST_CAP_PLUS_RESERVE_UNAVAILABLE"}
    available = min(
        window["memory"]["cap_max_bytes"],
        window["canonical_memory"]["cap_max_bytes"],
        policy["memory"]["cap_max_bytes"],
    )
    if reasons or available < cap:
        raise NotAdmitted(f"cap={available} required={cap} other_reasons={sorted(reasons)}")


def checked(a, profile):
    require(
        git(REPO, "rev-parse", "HEAD") == a.measurement_commit
        and not git(REPO, "status", "--porcelain"),
        "clean measurement checkout required",
    )
    require(git(a.backend, "rev-parse", "HEAD") == PIN, "incorrect backend")
    require(sha(profile.build_receipt) == profile.receipt_sha256, "unknown prepared client receipt")
    prepared = load(profile.build_receipt)
    require(prepared.get("pool_slots", 32) == profile.slots, "prepared pool geometry changed")
    require(sha(a.executable) == prepared["executable_sha256"], "canary digest changed")
    w = load(a.window / "receipt.json")
    policy = load(a.window / "resource-policy.json")
    admit_window(w, policy, sha(a.window / "resource-policy.json"), profile.cap)
    placement = load(HERE.parent / "nvme_placement/receipt.json")
    require(sha(a.placement) == placement["raw_receipt_sha256"], "NVMe placement receipt mismatch")
    physical = load(a.placement)
    model = Path(physical["launcher_path"]).resolve(strict=True)
    require(
        physical["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and model.samefile(physical["working_copy"])
        and physical["destination_direct_reread"]["sha256"] == MODEL_SHA
        and physical["destination_direct_reread"]["size_bytes"] == 63387346208,
        "NVMe provenance absent",
    )
    mounts({"model": model})
    identity = file_identity(model)
    require(
        [identity[k] for k in ("dev", "inode", "size_bytes", "mtime_ns", "ctime_ns")]
        == w["selected_stat"],
        "NVMe stat diverged from C55 window",
    )
    lock = next(
        entry for entry in load(REPO / "models.lock.json")["models"] if entry["id"] == MODEL_ID
    )
    require(
        Path(lock["path"]).samefile(model) and lock["sha256_verified"] == MODEL_SHA,
        "model path/lock mismatch",
    )
    raw = a.raw_parent / C110.name / "raw"
    reference(raw)
    ids = raw / "fixture_v2.ids.tsv"
    expected = prepared["mapped_objects_sha256"]
    ldd = subprocess.check_output(["ldd", a.executable], text=True)
    require("not found" not in ldd, "loader failed")
    paths = [
        Path(line.split("=>")[1].split()[0]).resolve(strict=True)
        for line in ldd.splitlines()
        if "=>" in line
    ]
    actual = {p.name: sha(p) for p in paths}
    require(actual == expected, "startup library set changed")
    gomp = [p for p in paths if p.name.startswith("libgomp")]
    require(len(gomp) == 1, "OpenMP mapping missing")
    env_contract = {
        "schema": "parallel-runtime-v1",
        "environment": parallel_environment({}),
        "libraries_sha256": {str(gomp[0]): actual[gomp[0].name]},
    }
    resources = freeze_protocol_resource_limits(
        policy, cgroup_memory_max_bytes=profile.cap, start_mode="CAUSAL_AB_START"
    )
    return model, identity, raw, ids, env_contract, resources


def run(a, out, profile):
    model, identity, raw, ids, omp, resources = checked(a, profile)
    parent = a.new_output_dir.resolve()
    (parent / "raw").mkdir()
    shutil.copyfile(a.window / "resource-policy.json", parent / "resource-policy.json")
    proto = {
        "resources": resources,
        "parallel_runtime": omp,
        "start_inventory": {
            "schema": "c120-start-inventory-v1",
            "duration_s": 60,
            "max_age_s": 3,
            "policy_sha256": sha(parent / "resource-policy.json"),
        },
        "measurement_commit": a.measurement_commit,
        "source_protocol_sha256": sha(profile.directory / "protocol.md"),
        "model_sha256": MODEL_SHA,
        "model_stat": identity,
        "supplied_fixture_sha256": IDS,
        "gold_sha256": DIGEST,
        "executable_sha256": sha(a.executable),
        "monitor_sha256": sha(REPO / "tools/run_bounded.py"),
        "new_unit": a.unit,
    }
    proto["pool_slots"] = profile.slots
    publish(parent / "protocol.json", proto)
    if a.prepare_only:
        out["status"] = "PASS_PRELAUNCH_ONLY"
        return
    for mode in ["OFF", "ON"]:
        require(
            file_identity(model) == identity
            and sha(a.executable) == proto["executable_sha256"]
            and sha(ids) == IDS,
            "artifact changed before arm",
        )
        arm = a.unit + "-" + mode.lower()
        stem = parent / "raw" / arm
        protocol = dict(proto, execution_scope_unit=arm)
        locked = parent / (arm + ".json")
        publish(locked, protocol)
        cmd = [
            "systemd-run",
            "--user",
            "--wait",
            "--collect",
            "--pipe",
            "--service-type=exec",
            "--unit=" + arm,
            "-p",
            "MemoryHigh=" + str(profile.cap),
            "-p",
            "MemoryMax=" + str(profile.cap),
            "-p",
            "MemorySwapMax=0",
            "-p",
            "LimitFSIZE=4194304",
            "-p",
            "RuntimeMaxSec=195s",
            "-p",
            "TimeoutStopSec=3s",
            "--",
            "/usr/bin/env",
            "-i",
            "PATH=/usr/bin:/bin",
            "LC_ALL=C",
            "HOME=" + str(Path.home()),
            "/usr/bin/python3",
            "-B",
            str(REPO / "tools/run_bounded.py"),
            "--run-id",
            arm,
            "--model-id",
            MODEL_ID,
            "--backend",
            "streaming",
            "--backend-root",
            str(a.backend),
            "--output-root",
            str(parent / "raw"),
            "--variant",
            f"C294-prefix-canary{profile.slots}-{mode}",
            "--workload",
            str(ids),
            "--cache-condition",
            "fresh-pools-uncontrolled-page-cache",
            "--timeout-s",
            "120",
            "--resource-protocol",
            str(locked),
            "--collect-start-inventory",
            "--require-telemetry",
            "--ready-marker",
            "C109_READY",
            "--env",
            "TESY_CPU_WAVE_SKIP_PARKED=1",
        ]
        if mode == "ON":
            cmd.extend(["--env", "TESY_PREFIX_ROUTE_AUDIT=1"])
        cmd += ["--", str(a.executable), str(model), str(ids), str(stem), "--arm", "C", "--canary"]
        started = time.monotonic()
        # A new transient service also cleans its entire cgroup on timeout or monitor failure.
        with (parent / (arm + ".scope.log")).open("xb") as log:
            proc = subprocess.run(
                cmd, stdout=log, stderr=subprocess.STDOUT, timeout=210, check=False
            )
        exit_s = time.monotonic() - started
        summary = {
            "mode": mode,
            "scope_returncode": proc.returncode,
            "wall_with_admission_s": round(exit_s, 3),
        }
        out["arms"].append(summary)
        manifest = Path(str(stem) + ".json")
        if manifest.exists():
            measured = load(manifest)
            summary.update(
                monitor_returncode=measured["returncode"],
                monitor_stop=measured["stop_reason"],
                maxima=measured["maxima"],
                manifest_sha256=sha(manifest),
            )
        require(
            proc.returncode == 0 and manifest.exists(), "incomplete arm or failed per-arm admission"
        )
        measured = load(manifest)
        require(
            measured["mapped_libraries_match_ldd"]
            and measured["stop_reason"] is None
            and measured["returncode"] == 0
            and measured["backend_sha"] == PIN
            and measured["binary_sha256"] == proto["executable_sha256"]
            and measured["workload_sha256"] == IDS
            and measured["resource_authority"] == resources
            and measured["cgroup_limit_enforced"]
            and measured["cgroup_start"]["memory_high"] == profile.cap
            and measured["cgroup_end"]["memory_high"] == profile.cap
            and measured["artifact_identity"]["stat_at_end"] == identity
            and measured["artifact_identity"]["stat_at_launch"] == identity
            and measured["mapped_backend_libraries_sha256"]
            == backend_library_hashes(a.executable, a.backend)
            and measured["parallel_runtime"]["libraries_sha256"] == omp["libraries_sha256"]
            and measured["maxima"]["direct_model_fds"] > 0
            and measured["maxima"]["buffered_model_fds"] == 0
            and measured["maxima"]["swap_bytes"] == 0,
            "resource or identity mismatch",
        )
        require(
            sum(p.stat().st_size for p in (parent / "raw").glob(arm + "*")) <= MAX_BYTES,
            "private output limit",
        )
        if profile.slots == 28:
            path = Path(str(stem) + ".logits.f32")
            require(path.stat().st_size == SIZE, "incomplete numerical trajectory")
            summary["row_comparison"] = compare_rows(path.read_bytes(), reference(raw)[1])
        summary["numerical"] = numerical(raw, stem, mode)
        if profile.slots == 28 and mode == "ON":
            counts = summary["numerical"]["routing"]["counts_by_path"]
            require(counts["S"] > 0 and counts["M"] > 0, "both route paths required")
    out["status"] = f"PASS_PAIRED_SLOTS{profile.slots}_NUMERICAL"


def main(profile=SLOTS32):
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ["window", "placement", "backend", "executable", "raw-parent", "new-output-dir"]:
        ap.add_argument("--" + key, required=True, type=Path)
    ap.add_argument("--measurement-commit", required=True)
    ap.add_argument("--unit", required=True, help="New lowercase systemd service stem")
    ap.add_argument("--prepare-only", action="store_true")
    a = ap.parse_args()
    require(
        a.unit.startswith("tesy-")
        and a.unit.replace("-", "").isalnum()
        and a.unit.islower()
        and len(a.unit) <= 48,
        "invalid unit",
    )
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    out = {"status": "FAIL_PRESERVED", "arms": []}
    try:
        run(a, out, profile)
    except NotAdmitted as exc:
        out.update(status="NOT_RUN_PHYSICAL_ADMISSION_REQUIRED", error=str(exc))
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        out["error"] = str(exc)
    publish(a.new_output_dir / "receipt.json", out)
    print(json.dumps(out, indent=2))
    raise SystemExit(int(not out["status"].startswith("PASS")))


if __name__ == "__main__":
    main()
