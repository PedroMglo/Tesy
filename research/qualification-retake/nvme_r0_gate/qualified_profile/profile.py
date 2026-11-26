"""One opt-in E20 C270 numerical bridge using a qualified per-process loader profile."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from authority import Authority, need, read, sha  # noqa: E402

Q = Path("research/qualification-retake")
R0 = Q / "nvme_r0_gate"
PREPARE = "fd051495eb89cd3513db3a29871237e809342bccd6495fab7fffab3cd561537c"
MEASURE = "75acd6348ce27051c1d73305c2fba00d785120a2bc37caaee0e903c70652a3d4"
MIB = 1 << 20
GIB = 1 << 30


def save(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def qualified_command(original, monitor_dir, child_env):
    result = original.copy()
    clean = result.index("/usr/bin/env")
    need(
        result[clean + 1 : clean + 4] == ["-i", "PATH=/usr/bin:/bin", "LC_ALL=C"],
        "clean monitor invocation",
    )
    result.insert(clean + 4, "LD_LIBRARY_PATH=" + str(monitor_dir))
    end = result.index("--", result.index("--env"))
    need(
        result[end - 2 : end] == ["--env", "TESY_CPU_WAVE_SKIP_PARKED=1"],
        "unexpected C270 environment",
    )
    result[end:end] = [
        word for key, value in child_env.items() for word in ("--env", key + "=" + value)
    ]
    return result


def check_native_manifest(manifest, protocol, sealed, expected, measure):
    # All new explicit env fields must exactly match the frozen physical invocation.
    need(manifest["explicit_env"] == expected, "native loader environment")
    need(
        manifest["relevant_environment"].get("LD_LIBRARY_PATH") == expected["LD_LIBRARY_PATH"]
        and "LD_PRELOAD" not in manifest["relevant_environment"],
        "native search or interposition",
    )
    loader_env = {k: expected[k] for k in ("LD_LIBRARY_PATH", "LD_DEBUG", "LD_DEBUG_OUTPUT")}
    measure.check_monitor(manifest, protocol, sealed, "E20_R0", loader_env=loader_env)


def completed_launch(path):
    if not path.is_file():
        return None
    blob = path.read_bytes()
    return json.loads(blob) if blob.endswith(b"\n") else None


def stop_owned_scope(unit, raw):
    try:
        pid = int(
            subprocess.check_output(
                ["systemctl", "--user", "show", unit + ".service", "--property=MainPID", "--value"],
                text=True,
                timeout=5,
            ).strip()
        )
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        need(str(raw).encode() in argv and unit.encode() in argv, "stop refused: foreign monitor")
    except FileNotFoundError:
        return
    subprocess.run(["systemctl", "--user", "stop", unit + ".service"], timeout=10, check=True)


def scope_active(unit):
    result = subprocess.run(
        ["systemctl", "--user", "is-active", unit + ".service"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip()


def guarded_run(cmd, out, unit, authority, measure, run_bounded):
    raw = out / "raw"
    launch = raw / (unit + ".launch.json")
    seen = set()
    count = 0
    id0 = None
    started = time.monotonic()
    need(scope_active(unit) in {"inactive", "unknown"}, "scope unit already exists")
    with (
        (out / "scope.log").open("xb") as log,
        subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT) as scope,
    ):
        try:
            while scope.poll() is None:
                need(
                    time.monotonic() - started <= 320 and measure.file_bytes(raw) <= 128 * MIB,
                    "wall or raw budget",
                )
                authority.recheck()
                if (receipt := completed_launch(launch)) is not None:
                    current = receipt["process_identity"]
                    if id0 is None:
                        id0 = current
                    need(
                        current == id0
                        and current["cgroup_path"].endswith("/" + unit + ".service")
                        and receipt["binary_sha256"] == authority.arm["executable_sha256"]
                        and Path(receipt["executable"]).resolve(strict=True) == authority.exe,
                        "foreign launch",
                    )
                    pid = current["pid"]
                    try:
                        before = run_bounded.process_identity(pid)
                        need(before == id0, "reused child PID")
                        sample = authority.live(pid)
                        need(run_bounded.process_identity(pid) == before, "PID changed during maps")
                        if sample:
                            seen.update(sample)
                            count += 1
                    except (FileNotFoundError, ProcessLookupError):
                        # A natural exit can race a /proc read; there must already be live evidence.
                        stat_path = Path("/proc", str(pid), "stat")
                        try:
                            active = stat_path.read_text().rsplit(")", 1)[1].split()[0] != "Z"
                        except FileNotFoundError:
                            active = False
                        if active:
                            raise
                time.sleep(0.25)
        except BaseException:
            if scope.poll() is None and scope_active(unit) != "inactive":
                stop_owned_scope(unit, raw)
            raise
        need(scope.returncode == 0, "bounded supervisor failed")
    need(
        id0 and count > 0 and authority.initial <= seen, "incomplete startup/lifetime VMA evidence"
    )
    need(
        not Path("/proc", str(id0["pid"])).exists()
        and scope_active(unit) in {"inactive", "unknown"},
        "scope or child still present",
    )
    return id0, count, seen, time.monotonic() - started


def prepare_campaign(a, out):
    r = a.checkout.resolve(strict=True)
    need(HERE.is_relative_to(r), "run the frozen source from the measurement checkout")
    pg = r / R0
    for path, pin in ((pg / "prepare.py", PREPARE), (pg / "measure.py", MEASURE)):
        need(sha(path) == pin, "upstream control changed")
    sys.path.insert(0, str(pg))
    import measure
    import prepare
    import run_bounded

    need(
        prepare.git(r, "rev-parse", "HEAD") == a.measurement_commit
        and not prepare.git(r, "status", "--porcelain"),
        "measurement checkout is not clean at the supplied commit",
    )
    need(re.fullmatch(r"tesy-[a-z0-9-]+", a.unit) and a.unit == Path(a.unit).name, "unit")
    authority = Authority(r, a.preflight_dir, a.preflight_sha256, "C270")
    window = a.window / "receipt.json"
    need(sha(window) == a.window_sha256, "C55 receipt")
    w = read(window)
    pol = read(a.window / "resource-policy.json")
    src = r / Q / "nvme_admission"
    need(
        w["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not w["reason"]
        and w["span_s"] >= 60
        and w["gpu_driver"] == authority.pre["kernel"]["release"]
        and sha(src / "window.py") == w["runner_sha256"]
        and sha(src / "protocolo.md") == w["protocol_sha256"]
        and sha(a.window / "samples.jsonl") == w["window_sha256"],
        "C55 provenance or admission",
    )
    from host_resource_policy import derive_policy, operational_session_ready

    need(
        pol == derive_policy(snapshot=pol["snapshot"]) and operational_session_ready(pol)[0],
        "C55 policy/launch",
    )
    need(
        w["memory"]["available_min_bytes"] >= 20 * GIB + pol["memory"]["reserve_bytes"],
        "E20 reserve",
    )
    a.envelope = "E20_R0"
    sealed, paths = prepare.seal(ldd_library_path=authority.native_search)
    need(
        Path(paths[0]).resolve(strict=True) == authority.exe
        and sealed["capture_sha256"] == authority.arm["executable_sha256"],
        "preflight not for this C270 binary",
    )
    prepared = prepare.freeze(a, out, sealed, paths)
    raw = out / "raw"
    raw.chmod(0o700)
    spec = read(out / "argv.json")
    protocol = read(out / "protocol.json")
    prefix = raw / "loader"
    expected = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | authority.child_env(prefix)
    cmd = qualified_command(spec["monitor"], authority.monitor_dir, authority.child_env(prefix))
    qualified = {
        "schema": "qualified-C270-E20-driver-v1",
        "envelope": "E20_R0",
        "measurement_commit": a.measurement_commit,
        "program_sha256": sha(__file__),
        "authority_program_sha256": sha(HERE / "authority.py"),
        "preflight_sha256": a.preflight_sha256,
        "static_map_sha256": authority.pre["static_map_sha256"],
        "c55_sha256": a.window_sha256,
        "base_protocol_sha256": prepared["protocol_sha256"],
        "base_argv_sha256": prepared["argv_sha256"],
        "monitor": cmd,
        "native_explicit_env": expected,
        "check": spec["check"],
        "driver_deployment": authority.pre["deployment_commit"],
        "kernel": authority.pre["kernel"],
    }
    save(out / "qualified-protocol.json", qualified)
    summary = {
        "status": "PREPARED_ONLY",
        "envelope": "E20_R0",
        "preflight_sha256": a.preflight_sha256,
        "protocol_sha256": prepared["protocol_sha256"],
        "qualified_protocol_sha256": sha(out / "qualified-protocol.json"),
        "model_launch_receipts": 0,
        "numerical_gate": "NOT_RUN",
        "capture_sha256": sealed["capture_sha256"],
    }
    if not a.execute:
        return summary
    summary["status"] = "FAIL_PRESERVED"
    try:
        need(
            prepare.file_identity(paths[1]) == protocol["model_stat"], "changed target before spawn"
        )
        summary["monitor_provider"] = authority.monitor_proof()
        ident, n, seen, wall = guarded_run(cmd, out, a.unit, authority, measure, run_bounded)
        mp = raw / (a.unit + ".json")
        lp = raw / (a.unit + ".launch.json")
        m = read(mp)
        need(
            m["process_identity"] == ident == read(lp)["process_identity"],
            "native journal identity",
        )
        check_native_manifest(m, protocol, sealed, expected, measure)
        audit = authority.audit(prefix, ident["pid"])
        need(
            set(audit["initialized_sha256"]) >= {Path(p).name for p in seen},
            "live ELF absent in journal",
        )
        summary.update(
            launch_sha256=sha(lp),
            monitor_sha256=sha(mp),
            scope_returncode=0,
            model_launch_receipts=1,
            elapsed_model_s=m["elapsed_s"],
            maxima=m["maxima"],
            monitor_stop=m["stop_reason"],
            authority=audit
            | {
                "status": "PASS_LIVE_AND_LOADER_C270",
                "live_samples": n,
                "kernel": authority.pre["kernel"],
                "static_map_sha256": authority.pre["static_map_sha256"],
                "deployment_commit": authority.pre["deployment_commit"],
            },
        )
        need(measure.file_bytes(raw) <= 128 * MIB, "raw output limit")
        summary["numerical_gate"] = "STARTED"
        with (out / "gate.log").open("xb") as log:
            subprocess.run(
                spec["check"], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=45
            )
        grade = read(out / "selected.json")
        measure.check_gate(grade)
        summary.update(
            status="PASS_SELECTED_C269_BRIDGE",
            numerical_gate=grade,
            selected_sha256=sha(out / "selected.json"),
            raw_bytes=measure.file_bytes(raw),
            wall_scoped_s=round(wall, 3),
        )
    except Exception as exc:
        summary.update(
            error=str(exc),
            error_type=type(exc).__name__,
            raw_bytes=measure.file_bytes(raw),
            model_launch_receipts=int((raw / (a.unit + ".launch.json")).is_file()),
        )
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("checkout", "preflight-dir", "window", "placement", "new-output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    for name in ("preflight-sha256", "window-sha256", "measurement-commit", "unit"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        data = prepare_campaign(a, out)
    except Exception as exc:
        data = {
            "status": "FAIL_PRESERVED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "model_launch_receipts": int((out / "raw" / (a.unit + ".launch.json")).is_file()),
        }
    save(out / "receipt.json", data)
    print(data["status"])
    return int(data["status"] not in ("PREPARED_ONLY", "PASS_SELECTED_C269_BRIDGE"))


if __name__ == "__main__":
    raise SystemExit(main())
