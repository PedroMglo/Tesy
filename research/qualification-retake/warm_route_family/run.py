"""Prepare or execute the four frozen 40-slot route-witness arms, stopping at first failure."""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from grade import FIXTURE, MANIFEST, ORDER, QUAL, ROOT, inputs, load, require, sha256, validate

sys.path.insert(0, str(QUAL / "nvme_prefix_gate"))
import run_pair as host  # noqa: E402

WR = QUAL / "warm_routes40"
BUILD = WR / "build-attempt-02/receipt.json"
BUILD_SHA = "3e8fc021efce022d4133e53790f89a59f40acb984fe0ff501ff8376e4f5b3946"
MODEL_BYTES = 63387346208
CAP = 20 * 1024**3
BYTE_BUDGET = 256 * 1024**2
REF_ROUTES = "507b70db15461ab9217d593dc92c6113557bfdb6c99cfc7806ca85c20e1e707a"


def check_canary(private, compact):
    require(
        compact.resolve().parent == WR / "canary" and compact.name.startswith("physical-"),
        "short physical seal must come from this checkout",
    )
    published = load(compact)
    receipt = private / "receipt.json"
    require(sha256(receipt) == published["raw_receipt_sha256"], "short family not sealed")
    short_build = WR / "canary/build-attempt-02/receipt.json"
    require(
        sha256(short_build) == "86b953e2ce7d82e02009e1a513815e574fcd99a254e3db40d3dcd8e12fc4d642",
        "short client build receipt changed",
    )
    short = load(short_build)
    require(
        short["executable_sha256"] == published["binary_sha256"]
        and short["common_header_sha256"] == load(BUILD)["source_hashes"]["routed_witness.h"],
        "short and long callback identities",
    )
    r = load(receipt)
    require(r["status"] == "PASS_PAIRED_SLOTS32_NUMERICAL", "short family failed")
    require([a["mode"] for a in r["arms"]] == ["OFF", "ON"], "short pair incomplete")
    hashes = []
    for a in r["arms"]:
        g = short_coverage(a)
        matches = list((private / "raw").glob("*-" + a["mode"].lower() + ".witness.bin"))
        require(len(matches) == 1 and sha256(matches[0]) == g["sha256"], "short WRT changed")
        base = matches[0].name.removesuffix(".witness.bin")
        monitor = private / "raw" / (base + ".json")
        launch = private / "raw" / (base + ".launch.json")
        require(
            sha256(monitor) == a["manifest_sha256"]
            and load(launch)["binary_sha256"]
            == load(monitor)["binary_sha256"]
            == published["binary_sha256"],
            "short process identity",
        )
        if a["mode"] == "ON":
            require(
                sha256(private / "raw" / (base + ".routes.bin")) == REF_ROUTES, "short TPR changed"
            )
        hashes.append(g["sha256"])
    require(hashes[0] == hashes[1], "short OFF/ON graphs differ")
    return sha256(receipt)


def short_coverage(a):
    n = a["numerical"]
    g = n.get("common_graph")
    require(isinstance(g, dict), "missing common graph in short canary")
    require(
        n["status"] == "PASS_NUMERICAL_CANARY"
        and n["mode"] == a["mode"]
        and n["logit_rows"] == 3
        and n["vocab"] == 201088
        and n["logits_sha256"] == "1fb158e3fa6bd7ec2e48d4c85c1f0a79b8d3575e9ca58d8a696b5c3ea8f4e613"
        and a["scope_returncode"] == a["monitor_returncode"] == 0
        and a["monitor_stop"] is None
        and (g["graphs"], g["rows"], g["logical_ids"], g["reference_tpr_sha256"])
        == (3, 633, 2532, REF_ROUTES),
        "short numerical or common graph coverage",
    )
    return g


def prepare(a, out):
    require(
        host.git(ROOT, "rev-parse", "HEAD") == a.measurement_commit
        and not host.git(ROOT, "status", "--porcelain"),
        "clean measurement checkout required",
    )
    require(sha256(BUILD) == BUILD_SHA, "long client receipt changed")
    built = load(BUILD)
    require(
        built["status"] == "PASS_GGML_CPU_FIXTURE_AND_CLIENT_ONLY"
        and built["boundary_fixture"]["slots"] == 1440
        and sha256(a.executable) == built["client_sha256"],
        "unknown client or missing cut I",
    )
    require(
        host.git(a.backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [host.PIN, "149078c009a40b2c69ee126cdb84091fe3e95606"]
        and not host.git(a.backend, "status", "--porcelain"),
        "C294 provenance",
    )
    placement = load(QUAL / "nvme_placement/receipt.json")
    require(sha256(a.placement) == placement["raw_receipt_sha256"], "placement unknown")
    copy = load(a.placement)
    model = Path(copy["launcher_path"]).resolve(strict=True)
    policy_path = a.window / "resource-policy.json"
    window = load(a.window / "receipt.json")
    policy = load(policy_path)
    host.admit_window(window, policy, sha256(policy_path), CAP)
    require(window["status"] == "PASS_RESOURCE_WINDOW_ONLY" and not window["reason"], "C55 E20")
    lock = next(x for x in load(ROOT / "models.lock.json")["models"] if x["id"] == host.MODEL_ID)
    ident = host.file_identity(model)
    require(
        copy["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and model.samefile(copy["working_copy"])
        and model.samefile(lock["path"])
        and ident["size_bytes"] == copy["destination_direct_reread"]["size_bytes"] == MODEL_BYTES
        and copy["destination_direct_reread"]["sha256"] == lock["sha256_verified"] == host.MODEL_SHA
        and [ident[k] for k in ("dev", "inode", "size_bytes", "mtime_ns", "ctime_ns")]
        == window["selected_stat"],
        "model identity differs from admitted NVMe placement",
    )
    host.mounts({"model": model})
    host.git(ROOT, "ls-files", "--error-unmatch", str(a.canary_seal.relative_to(ROOT)))
    check_short = check_canary(a.canary_root, a.canary_seal)
    fixture, specs, refs = inputs(a.raw_parent)
    require(sha256(host.RECEIPT) == host.PREPARED, "loader inventory changed")
    expected = load(host.RECEIPT)["mapped_objects_sha256"]
    loader = subprocess.check_output(
        ["ldd", a.executable], env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, text=True, timeout=15
    )
    require("not found" not in loader, "unresolved library")
    paths = [
        Path(line.split("=>")[1].split()[0]).resolve(strict=True)
        for line in loader.splitlines()
        if "=>" in line
    ]
    require({p.name: sha256(p) for p in paths} == expected, "startup libraries differ")
    gomp = {str(p): expected[p.name] for p in paths if p.name.startswith("libgomp")}
    libs = host.backend_library_hashes(a.executable, a.backend)
    require(
        len(gomp) == 1
        and {Path(k).name: v for k, v in libs.items()} == built["common_libs_sha256"],
        "numerical DSOs",
    )
    require(
        shutil.disk_usage(out).free >= 10 * 1024**3 + BYTE_BUDGET, "insufficient output reserve"
    )
    (out / "raw").mkdir()
    shutil.copyfile(policy_path, out / "resource-policy.json")
    p = {
        "schema": "tesy-warm-route-family-v1",
        "limits": {},
        "resources": host.freeze_protocol_resource_limits(
            policy, cgroup_memory_max_bytes=CAP, start_mode="CAUSAL_AB_START"
        ),
        "parallel_runtime": {
            "schema": "parallel-runtime-v1",
            "environment": host.parallel_environment({}),
            "libraries_sha256": gomp,
        },
        "start_inventory": {
            "schema": "c120-start-inventory-v1",
            "duration_s": 60,
            "max_age_s": 3,
            "policy_sha256": sha256(policy_path),
        },
        "measurement_commit": a.measurement_commit,
        "model_sha256": host.MODEL_SHA,
        "model_stat": ident,
        "short_receipt_sha256": check_short,
        "build_receipt_sha256": BUILD_SHA,
        "executable_sha256": built["client_sha256"],
        "library_sha256": libs,
        "supplied_ids_sha256": FIXTURE,
        "c280_manifest_sha256": MANIFEST,
        "unit_stem": a.unit,
        "independent_reference": refs,
        "long_protocol_sha256": sha256(WR / "protocol.md"),
        "cut_protocol_sha256": sha256(WR / "boundary-protocol.md"),
        "monitor_sha256": sha256(ROOT / "tools/run_bounded.py"),
        "order": ORDER,
    }
    host.validate_resource_protocol(p)
    host.publish(out / "protocol.json", p)
    return model, fixture, specs, refs, p


def environment(mode):
    result = {"TESY_CPU_WAVE_SKIP_PARKED": "1", "TESY_ROUTE_GRAPH_WITNESS": "1"}
    if mode == "ON":
        result["TESY_PREFIX_ROUTE_AUDIT"] = "1"
    return result


def command(a, unit, case, mode, model, fixture, native, locked):
    args = [
        "systemd-run",
        "--user",
        "--wait",
        "--collect",
        "--pipe",
        "--service-type=exec",
        "--unit=" + unit,
    ]
    for value in [
        f"MemoryHigh={CAP}",
        f"MemoryMax={CAP}",
        "MemorySwapMax=0",
        "LimitFSIZE=33554432",
        "RuntimeMaxSec=315s",
        "TimeoutStopSec=3s",
    ]:
        args.extend(["-p", value])
    args += [
        "--",
        "/usr/bin/env",
        "-i",
        "PATH=/usr/bin:/bin",
        "LC_ALL=C",
        "HOME=" + str(Path.home()),
        "/usr/bin/python3",
        "-B",
        ROOT / "tools/run_bounded.py",
        "--run-id",
        unit,
        "--model-id",
        host.MODEL_ID,
        "--backend",
        "streaming",
        "--backend-root",
        a.backend,
        "--output-root",
        native.parent,
        "--variant",
        "C294-warm40-" + case + "-" + mode,
        "--workload",
        fixture,
        "--cache-condition",
        "fresh-pools-uncontrolled-page-cache",
        "--timeout-s",
        "250",
        "--resource-protocol",
        locked,
        "--collect-start-inventory",
        "--require-telemetry",
    ]
    for key, value in environment(mode).items():
        args.extend(["--env", key + "=" + value])
    args += ["--", a.executable, model, fixture, case, native, "R0", "v1"]
    return list(map(str, args))


def file_bytes(path):
    size = 0
    for parent, _, names in os.walk(path):
        for name in names:
            try:
                size += (Path(parent) / name).stat().st_size
            except FileNotFoundError:  # Client just renamed a completed .partial journal.
                continue
    return size


def check_closure(pid, unit):
    cg = Path(pid["cgroup_path"])
    require(cg.is_absolute() and cg.name == unit + ".service", "unrelated cgroup")
    group = Path("/sys/fs/cgroup") / cg.relative_to("/")
    proc = Path("/proc") / str(pid["pid"]) / "stat"
    for _ in range(20):
        try:
            stat = proc.read_text()
            same = int(stat[stat.rfind(")") + 2 :].split()[19]) == pid["start_ticks"]
        except FileNotFoundError:
            same = False
        if not same and not group.exists():
            return
        time.sleep(0.1)
    raise ValueError("process or cgroup survives")


def measure(cmd, out, unit, deadline):
    with (
        (out / (unit + ".scope.log")).open("xb") as log,
        subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT) as proc,
    ):
        try:
            while proc.poll() is None:
                require(file_bytes(out) <= BYTE_BUDGET, "family output exceeded")
                require(time.monotonic() < deadline, "arm or family deadline")
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                subprocess.run(
                    ["systemctl", "--user", "stop", unit + ".service"], timeout=12, check=True
                )
        return proc.returncode


def monitor(raw, unit, mode, p, locked, summary):
    launch = raw / (unit + ".launch.json")
    record = raw / (unit + ".json")
    require(launch.is_file() and record.is_file(), "arm incomplete; consult C118 and scope")
    m = load(record)
    launch_data = load(launch)
    pid = launch_data["process_identity"]
    check_closure(pid, unit)
    summary.update(
        launch_sha256=sha256(launch),
        monitor_sha256=sha256(record),
        monitor_stop=m.get("stop_reason"),
        process_and_scope_closed=True,
        model_wall_s=m.get("elapsed_s"),
        maxima=m.get("maxima"),
    )
    inventory = raw / (unit + ".start-inventory.receipt.json")
    require(
        launch_data["run_id"] == m["run_id"] == unit
        and m["process_identity"] == pid
        and m["start_inventory"] == launch_data["start_inventory"]
        and sha256(inventory) == m["start_inventory"]["receipt_sha256"],
        "launch or C118 identity",
    )
    summary["inventory_sha256"] = sha256(inventory)
    require(
        m["returncode"] == 0
        and m["stop_reason"] is None
        and m["limits"]["require_telemetry"]
        and m["limits"]["timeout_s"] == 250
        and m["backend_sha"] == host.PIN
        and m["limits"]["resource_protocol_sha256"]
        == launch_data["resource_protocol_sha256"]
        == sha256(locked)
        and m["workload_sha256"] == FIXTURE
        and m["explicit_env"] == environment(mode)
        and m["binary_sha256"] == launch_data["binary_sha256"] == p["executable_sha256"]
        and m["resource_authority"] == p["resources"]
        and m["cgroup_limit_enforced"]
        and m["mapped_libraries_match_ldd"]
        and m["mapped_backend_libraries_sha256"] == p["library_sha256"]
        and m["parallel_runtime"]["libraries_sha256"] == p["parallel_runtime"]["libraries_sha256"]
        and m["artifact_identity"]["stat_at_end"]
        == m["artifact_identity"]["stat_at_launch"]
        == p["model_stat"],
        "monitor reported failure or changed runtime/identities",
    )
    for endpoint in ("cgroup_start", "cgroup_end"):
        cg = m[endpoint]
        require(
            cg["memory_max"] == cg["memory_high"] == CAP and cg["swap_max"] == 0, "scope bounds"
        )
    maxima = m["maxima"]
    require(
        maxima["direct_model_fds"] > 0
        and maxima["buffered_model_fds"] == maxima["swap_bytes"] == 0,
        "model FD or swap contract",
    )


def run(a, out, result):
    model, fixture, specs, references, plan = prepare(a, out)
    result["plan_sha256"] = sha256(out / "protocol.json")
    arms = []
    for n, (case, mode) in enumerate(ORDER, 1):
        unit = f"{a.unit}-{n}-{case}-{mode.lower()}"
        native = out / "raw" / (unit + ".native")
        locked = out / (unit + ".json")
        p = dict(plan, execution_scope_unit=unit)
        host.validate_resource_protocol(p)
        host.publish(locked, p)
        cmd = command(a, unit, case, mode, model, fixture, native, locked)
        arms.append((case, mode, unit, native, locked, cmd))
    host.publish(out / "commands.json", [arm[-1] for arm in arms])
    if not a.execute:
        result["status"] = "PASS_PRELAUNCH_ONLY"
        return
    start = time.monotonic()
    for case, mode, unit, native, locked, cmd in arms:
        row = {
            "case": case,
            "mode": mode,
            "run_id": unit,
            "native_dir": str(native.relative_to(out)),
            "status": "FAIL_PRESERVED",
        }
        result["arms"].append(row)
        require(
            host.file_identity(model) == plan["model_stat"]
            and sha256(a.executable) == plan["executable_sha256"]
            and sha256(fixture) == FIXTURE,
            "pre-spawn identity changed",
        )
        now = time.monotonic()
        code = measure(cmd, out, unit, min(start + 1320, now + 325))
        row.update(scope_returncode=code, wall_with_admission_s=round(time.monotonic() - now, 3))
        monitor(native.parent, unit, mode, plan, locked, row)
        require(code == 0 and file_bytes(out) <= BYTE_BUDGET, "scope or disk budget")
        prior = next((x for x in result["arms"][:-1] if x["case"] == case), None)
        row.update(validate(native, case, mode, specs[case], references[case], prior))
        require(time.monotonic() < start + 1320, "family deadline")
        host.publish(out / "progress.json", result)
    result["status"] = "PASS_WARM_ROUTE_FAMILY"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "window",
        "placement",
        "backend",
        "executable",
        "raw-parent",
        "canary-root",
        "canary-seal",
        "new-output-dir",
    ):
        parser.add_argument("--" + key, required=True, type=lambda p: Path(p).resolve())
    parser.add_argument("--measurement-commit", required=True)
    parser.add_argument("--unit", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate inputs and write plan with zero model processes (default)",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Launch the four diagnostic arms after explicit physical admission",
    )
    args = parser.parse_args()
    require(re.fullmatch(r"tesy-[a-z0-9][a-z0-9-]{0,40}", args.unit), "invalid private unit stem")
    os.umask(0o077)
    output = args.new_output_dir
    output.mkdir(mode=0o700)
    result = {"status": "FAIL_PRESERVED", "measurement_commit": args.measurement_commit, "arms": []}
    try:
        run(args, output, result)
    except host.NotAdmitted as exc:
        result.update(status="NOT_RUN_PHYSICAL_ADMISSION_REQUIRED", error=str(exc))
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        StopIteration,
        subprocess.SubprocessError,
    ) as exc:
        result["error"] = str(exc)
    result["raw_bytes"] = file_bytes(output)
    result["model_launch_receipts"] = len(list((output / "raw").glob("*.launch.json")))
    result["not_run"] = ORDER[len(result["arms"]) :]
    host.publish(output / "receipt.json", result)
    print(result["status"], result.get("error", ""))
    raise SystemExit(int(not result["status"].startswith("PASS")))
