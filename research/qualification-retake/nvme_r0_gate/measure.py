"""Execute one already frozen selected bridge and its independent post-run gate."""

import os
import subprocess
import time
from pathlib import Path

from prepare import CAPS, MIB, check, file_identity, load, sha256


def file_bytes(root):
    total = 0
    for directory, _, files in os.walk(root):
        for name in files:
            try:
                total += (Path(directory) / name).stat().st_size
            except FileNotFoundError:
                continue
    return total


def check_monitor(manifest, protocol, sealed, envelope):
    cap = CAPS[envelope]
    check(
        manifest["returncode"] == 0 and manifest["stop_reason"] is None, "runtime monitor refused"
    )
    check(
        manifest["limits"]["require_telemetry"]
        and manifest["backend_sha"] == sealed["backend_commit"]
        and manifest["workload_sha256"] == sealed["ids_sha256"]
        and manifest["binary_sha256"] == sealed["capture_sha256"],
        "runtime provenance mismatch",
    )
    check(
        manifest["explicit_env"] == {"TESY_CPU_WAVE_SKIP_PARKED": "1"}
        and manifest["resource_authority"] == protocol["resources"]
        and manifest["artifact_identity"]["stat_at_launch"]
        == manifest["artifact_identity"]["stat_at_end"]
        == protocol["model_stat"],
        "model or resource authority changed",
    )
    check(
        manifest["mapped_libraries_match_ldd"]
        and {Path(k).name: v for k, v in manifest["mapped_backend_libraries_sha256"].items()}
        == sealed["numerical_dso_sha256"]
        and manifest["parallel_runtime"]["libraries_sha256"]
        == protocol["parallel_runtime"]["libraries_sha256"],
        "mapped numerical libraries or GNU OpenMP differ",
    )
    for key in ["cgroup_start", "cgroup_end"]:
        cg = manifest[key]
        check(
            cg["memory_max"] == cg["memory_high"] == cap and cg["swap_max"] == 0,
            "cgroup enforcement changed",
        )
    check(
        manifest["maxima"]["swap_bytes"] == 0 and manifest["maxima"]["direct_model_fds"] > 0,
        "swap or missing direct GGUF I/O",
    )


def check_gate(grade):
    w = grade["prospective_witness"]
    check(
        grade["status"] == "PASS_PRIVATE_R0_SELECTED_BRIDGE"
        and grade["core_payloads"] == 1500
        and grade["full_logits"] == 5
        and w["status"] == "PASS_PROSPECTIVE_WITNESS"
        and w["combinations"] == 166
        and w["components"] == 996,
        "incomplete selected numerical proof",
    )


def execute(out, unit, envelope, sealed):
    spec = load(out / "argv.json")
    protocol = load(out / "protocol.json")
    raw = out / "raw"
    summary = {
        "status": "FAIL_PRESERVED",
        "envelope": envelope,
        "model_launch_receipts": 0,
        "numerical_gate": "NOT_RUN",
        "capture_sha256": sealed["capture_sha256"],
    }
    try:
        model = Path(spec["monitor"][-5])
        check(
            file_identity(model) == protocol["model_stat"],
            "model changed before launching supervisor",
        )
        start = time.monotonic()
        with (
            (out / "scope.log").open("xb") as log,
            subprocess.Popen(spec["monitor"], stdout=log, stderr=subprocess.STDOUT) as proc,
        ):
            while proc.poll() is None:
                if file_bytes(raw) > 128 * MIB or time.monotonic() - start > 320:
                    subprocess.run(
                        ["systemctl", "--user", "stop", unit + ".service"], timeout=10, check=False
                    )
                    raise ValueError("raw or wall limit exceeded")
                time.sleep(0.5)
            code = proc.returncode
        summary["scope_returncode"] = code
        launch = raw / (unit + ".launch.json")
        summary["model_launch_receipts"] = int(launch.is_file())
        if launch.exists():
            summary["launch_sha256"] = sha256(launch)
        mpath = raw / (unit + ".json")
        if mpath.exists():
            manifest = load(mpath)
            summary.update(
                monitor_sha256=sha256(mpath),
                monitor_stop=manifest["stop_reason"],
                elapsed_model_s=manifest["elapsed_s"],
                maxima=manifest["maxima"],
            )
        check(
            code == 0 and mpath.is_file() and launch.is_file(),
            "incomplete launch or failed monitor",
        )
        check_monitor(manifest, protocol, sealed, envelope)
        check(file_bytes(raw) <= 128 * MIB, "raw limit exceeded")
        summary["numerical_gate"] = "STARTED"
        with (out / "gate.log").open("xb") as log:
            proc = subprocess.run(
                spec["check"], stdout=log, stderr=subprocess.STDOUT, timeout=45, check=False
            )
        check(proc.returncode == 0, "independent comparison failed")
        grade = load(out / "selected.json")
        check_gate(grade)
        summary.update(
            status="PASS_SELECTED_C269_BRIDGE",
            numerical_gate=grade,
            raw_bytes=file_bytes(raw),
            wall_after_prepare_s=round(time.monotonic() - start, 3),
        )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        summary.update(
            error=str(exc),
            raw_bytes=file_bytes(raw),
            model_launch_receipts=int((raw / (unit + ".launch.json")).exists()),
        )
    return summary
