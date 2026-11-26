"""Reopen a sealed tiny hybrid family without accessing a model, GPU, driver or live scope."""

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
API = run_path(str(HERE / "run.py"))
GRADE = run_path(str(HERE.parent / "client/grade.py"))
MODES = API["MODES"]
PASS = "PASS_TINY_HYBRID_GPU_FIXTURE"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(file):
    need(file.is_file() and not file.is_symlink(), "unavailable or linked " + file.name)
    with file.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def bound(file, sha):
    need(digest(file) == sha, "digest " + file.name)
    return json.loads(file.read_bytes())


def short(error):
    return re.sub(r"/[^\s,]+", "<private-path>", str(error))[:320]


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def bounds(rows):
    """Peak sensors are observations at sample instants; never integrate power."""
    obs = [v["observation"] for v in rows]
    if not rows:
        return {"sample_count": 0}
    nvme = {}
    for v in obs:
        for sensor, temp in v["thermal"]["nvme_composite_by_sensor"].items():
            nvme[sensor] = max(nvme.get(sensor, temp), temp)
    watts = [v["gpu"].get("power_w") for v in obs]
    return dict(
        sample_count=len(rows),
        cpu_tctl_c_max=max(v["thermal"]["cpu_tctl_c"] for v in obs),
        gpu_temperature_c_max=max(v["gpu"]["temperature_c"] for v in obs),
        gpu_used_mib_max=max(v["gpu"]["used_mib"] for v in obs),
        gpu_power_w_max_sampled=max((w for w in watts if w is not None), default=None),
        nvme_temperature_c_max_by_sensor=nvme,
        mem_available_bytes_min=min(v["mem_available_bytes"] for v in obs),
    )


def check_window(rows, expected, pid, policy):
    """Accept active retries while NVML learns the PID and running between handoffs."""
    need(rows and type(pid) is int and pid > 0, "empty active window or PID")
    state, t, attempt = 0, 0.0, 0
    end_steps = ("entry", "active", "finish", "after_exit")
    samples = Counter()
    peak = 0
    for row in rows:
        phase = row["phase"]
        owners = row["observation"]["gpu_owners"]
        need(owners == [] or owners == [pid], "unrelated GPU owner")
        now = row["elapsed_s"]
        need(math.isfinite(now) and 0 < now - t <= 3 and now < 30, "monitor cadence")
        t = now
        observed = row["observation"]
        API["IO"].validate_sample(
            observed, policy=policy, cap_bytes=API["CAP"], expected_power=API["INV"].POWER
        )
        gpu = observed["gpu"]
        need(gpu["used_mib"] < API["VRAM"] and row["peak_bytes"] < API["STOP"], "active cap")
        need(observed["thermal"]["cpu_tctl_c"] < policy["cpu"]["warning_c"], "active CPU warning")
        for value, warning in [
            (gpu["temperature_c"], policy["gpu"]["warning_c"]),
            *(
                (observed["thermal"]["nvme_composite_by_sensor"][r["sensor"]], r["warning_c"])
                for r in policy["nvme"]
            ),
        ]:
            need(warning is None or value < warning, "active GPU/NVMe warning")
        peak = max(peak, row["peak_bytes"])
        samples[phase] += 1
        if phase == "running":
            need(state < 4 and row["attempt"] == 1, "running after closure or retry")
            continue
        need(state < 4 and phase == end_steps[state], "marker order")
        attempt += 1
        need(attempt == row["attempt"] and attempt <= 3, "bad marker retry")
        if phase in ("entry", "after_exit"):
            need(not owners and attempt == 1, "owner at idle boundary")
        elif not owners:
            need(phase == "active" and attempt < 3, "GPU owner absent")
            if attempt == 1:
                active_start = t
            continue
        if phase == "active" and attempt > 1:
            need(t - active_start <= 2, "active retry interval")
        state += 1
        attempt = 0
    if expected:
        need(state == 4 and rows[-1]["phase"] == "after_exit", "incomplete owner boundaries")
    return dict(
        covered=min(state, 3),
        after_exit=state == 4,
        samples_by_phase=dict(samples),
        scope_peak_bytes_sampled=peak,
        last_sample_elapsed_s=t,
    )


def identity_tree(family, r):
    actual = {}
    for p in family.rglob("*"):
        need(not p.is_symlink(), "symlink in family")
        if p.is_file() and p != family / "receipt.json":
            actual[p.relative_to(family).as_posix()] = digest(p)
    listed = r.get("raw_sha256")
    if listed is None:
        need(r["status"] == "FAIL_PRESERVED" and not actual, "family raw inventory absent")
    else:
        need(actual == listed, "family raw inventory")
    return actual


def mapped_names(folder, s, b, ident):
    needed = {v["file"] for v in b["closure"].values() if API["relevant"](Path(v["file"]).name)}
    allowed = {p for p in ident if API["relevant"](Path(p).name)}
    exe = [
        p
        for p, v in ident.items()
        if Path(p).name == b["binary"] and v["sha256"] == b["binary_sha256"]
    ]
    need(len(exe) == 1 and needed <= allowed, "prepared ELF identity")
    raw = set()
    for line in (folder / "maps").read_text().splitlines():
        parts = line.split(None, 5)
        if len(parts) != 6 or not parts[5].startswith("/"):
            continue
        path = parts[5]
        if path == exe[0] or API["relevant"](Path(path).name):
            need(path in ident and " (deleted)" not in path and "/stubs/" not in path, "alien VMA")
            need(int(parts[4]) == ident[path]["stat"][1], "ELF VMA inode")
            raw.add(path)
    need(exe[0] in raw, "client ELF VMA absent")
    raw.remove(exe[0])
    for observed in (raw, *[set(s[k]) for k in ("A_providers", "F_providers")]):
        need(needed <= observed <= allowed, "provider census")
    return {
        cut: sorted(Path(p).name for p in paths)
        for cut, paths in (("A", s["A_providers"]), ("F", s["F_providers"]), ("native", raw))
    }


def inspect_field(out, required, field, action, *args):
    try:
        out[field] = action(*args)
    except (ValueError, RuntimeError, KeyError, OSError, IndexError, TypeError) as exc:
        if required:
            raise
        out["issues"].append(field + ": " + short(exc))


def native_grade(mode, folder):
    return GRADE["check_arm"](
        mode, (folder.parent / "stdout").read_text(), (folder.parent / "stderr").read_text(), folder
    )


def review(a):
    f = bound(a.family / "receipt.json", a.family_sha256)
    terminal = f["status"]
    need(terminal in (PASS, "FAIL_PRESERVED"), "family not terminal")
    raw = identity_tree(a.family, f)
    arms = f.get("arms", {})
    seen = [name for name in MODES if name in arms]
    need(set(arms) == set(seen) and seen == list(MODES[: len(seen)]), "out-of-order or foreign arm")
    report = dict(
        reviewer_sha256=digest(HERE / "review.py"),
        family_status=terminal,
        family_sha256=a.family_sha256,
        raw_files=len(raw),
        raw_bytes=sum((a.family / path).stat().st_size for path in raw),
        status="REPRODUCED_TINY_HYBRID_GPU_FIXTURE"
        if terminal == PASS
        else "REVIEWED_PRESERVED_FAILURE",
        reason=short(f.get("reason", f.get("final_inventory_error", ""))) or None,
        launches=sum(s["starts"] for s in arms.values()),
        arms={},
        energy_j=None,
        family_scope={
            key: f.get(key) for key in ("max_scope_bytes", "swap_peak_bytes", "memory_events_local")
        },
        unit=f.get("unit"),
        commit=f.get("commit"),
        tree=f.get("tree"),
    )
    if not seen and terminal != PASS:
        need(not raw and not report["launches"], "pre-arm failure has unassigned artifacts")
        report["arms"] = {k: {"status": "NOT_RUN", "launches": 0} for k in MODES}
        return report
    need(terminal != PASS or len(seen) == 3, "passing family lacks three arms")
    p = bound(a.prepared / "receipt.json", f["prepared_sha256"])
    b = bound(a.client / "receipt.json", f["client_sha256"])
    c = bound(a.cpu / "receipt.json", f["cpu_sha256"])
    need(
        p["status"] == "PREPARED_ONLY"
        and c["status"] == "PASS_TINY_HYBRID_CPU_REFERENCE"
        and b["status"] == "PASS_TINY_HYBRID_CLIENT_BUILD"
        and b["variant"] == "cuda",
        "dependencies",
    )
    for key in (
        "client_sha256",
        "cpu_sha256",
        "dso_sha256",
        "c55_sha256",
        "model_sha256",
        "commit",
        "tree",
        "supervisor_sha256",
        "protocol_sha256",
        "provider_identity",
    ):
        need(p[key] == f[key], "prepared identity " + key)
    need(
        b["dso_build_sha256"] == f["dso_sha256"]
        and f["model_sha256"] == c["model_sha256"] == API["TINY"]
        and b["sources"]["grade.py"] == digest(HERE.parent / "client/grade.py")
        and f["supervisor_sha256"] == digest(HERE / "run.py")
        and f["protocol_sha256"] == digest(HERE / "protocol.md"),
        "source or fixture",
    )
    report["inputs"] = {
        k: f[k]
        for k in (
            "prepared_sha256",
            "client_sha256",
            "dso_sha256",
            "cpu_sha256",
            "c55_sha256",
            "model_sha256",
            "supervisor_sha256",
            "protocol_sha256",
        )
    }
    need(
        digest(a.cpu / "stdout") == c["stdout_sha256"]
        and digest(a.cpu / "stderr") == c["stderr_sha256"],
        "CPU logs",
    )
    cpu_native = a.cpu / "native"
    cpu_grade = GRADE["check_arm"](
        "CPU", (a.cpu / "stdout").read_text(), (a.cpu / "stderr").read_text(), cpu_native
    )
    need(cpu_grade == c["grade"], "CPU reference")
    policy, end = API["c55"](
        SimpleNamespace(c55=a.c55 / "receipt.json", c55_sha256=f["c55_sha256"])
    )
    resident = None
    trouble = False
    for mode in MODES:
        rec = arms.get(mode)
        if rec is None:
            report["arms"][mode] = {"launches": 0, "status": "NOT_RUN"}
            need(not (a.family / mode).exists(), "raw of skipped arm")
            continue
        starts = rec["starts"]
        need(starts in (0, 1) and not trouble, "unadmitted launch")
        arm_complete = (a.family / mode / "grade.json").is_file()
        if arm_complete:
            need(
                json.loads((a.family / mode / "grade.json").read_bytes()) == rec, "saved arm grade"
            )
        required = terminal == PASS or arm_complete
        out = dict(
            launches=starts,
            returncode=rec.get("returncode"),
            child_gone=rec.get("child_gone"),
            wall_s_including_handoffs=rec.get("wall_s"),
            issues=[],
            status="PENDING",
        )
        report["arms"][mode] = out
        rid = f["unit"] + "-" + mode.lower()
        ip = a.family / "raw" / (rid + ".start-inventory.jsonl")
        if ip.exists():
            ir = lines(ip)
            out["C118"] = bounds(ir)
            out["C118"]["sha256"] = digest(ip)
            inv = rec.get("admission")
            if inv:
                need(Path(inv["path"]).parts[-2:] == ("raw", ip.name), "published C118 path")
                # Rebase only the archive root; use the original policy for every observation.
                API["INV"].require_inventory(
                    a.family,
                    rid,
                    inv | {"path": str(ip)},
                    policy=policy,
                    cap_bytes=API["CAP"],
                    expected_power=API["INV"].POWER,
                    now=datetime.fromisoformat(inv["last_utc"]),
                )
                need(
                    all(row["observation"]["gpu"]["used_mib"] < API["VRAM"] for row in ir),
                    "C118 VRAM",
                )
                out["C118"].update(
                    complete=True,
                    duration_s=inv["duration_s"],
                    first_sample_after_c55_end_s=(
                        datetime.fromisoformat(ir[0]["utc"]) - end
                    ).total_seconds(),
                )
            else:
                out["C118"]["complete"] = False
        need(
            not (starts or required) or out.get("C118", {}).get("complete"),
            "missing admission before native",
        )
        mp = a.family / mode / "monitor.jsonl"

        if mp.is_file():
            need(digest(mp) == rec.get("monitor_sha256"), "arm monitor identity")
            rows = lines(mp)
            out["monitor"] = bounds(rows) | {"sha256": digest(mp)}
            inspect_field(
                out, required, "coverage", check_window, rows, required, rec.get("pid"), policy
            )
            if rows:
                need(
                    rec.get("sampled_vram_mib_max") == out["monitor"]["gpu_used_mib_max"],
                    "peak VRAM disagreement",
                )
            if required:
                need(
                    rec.get("observed_handoffs") == 3
                    and out["coverage"]["last_sample_elapsed_s"] <= rec["wall_s"],
                    "supervisor handoffs",
                )
        elif required:
            raise ValueError("missing monitor")
        nd = a.family / mode / "native"
        if nd.is_dir() and (nd / "maps").is_file():
            inspect_field(
                out, required, "VMA_providers", mapped_names, nd, rec, b, f["provider_identity"]
            )
        elif required:
            raise ValueError("missing native map")
        if starts:
            for name in ("stdout", "stderr"):
                need(digest(nd.parent / name) == rec[name + "_sha256"], "arm " + name)
            inspect_field(out, required, "grade", native_grade, mode, nd)
            if "grade" in rec:
                need(rec["grade"] == out.get("grade"), "native grade differs from receipt")
        if required:
            need(
                starts == 1
                and rec.get("child_gone") is True
                and rec["returncode"] == 0
                and "grade" in out,
                "incomplete successful arm",
            )
        if "grade" in out:
            if mode == "RESIDENT":
                resident = (nd, out["grade"])
                cmp = GRADE["compare_arms"](cpu_native, cpu_grade, nd, out["grade"])
                contrast = "cpu_comparison"
            else:
                need(resident is not None, "missing baseline")
                cmp = GRADE["compare_arms"](*resident, nd, out["grade"])
                contrast = "resident_comparison"
            out[contrast] = cmp
            if contrast in rec:
                need(rec[contrast] == cmp, "stored contrast differs")
            if mode == "BANK9" and not (cmp["bitwise"] and cmp["routes_equal"]):
                need(not required, "successful bank with wrong output")
                out["issues"].append("nine-slot numerical or routing divergence")
        trouble = not arm_complete
        out["status"] = (
            "REPRODUCED_ARM"
            if arm_complete
            else ("STARTED_BEFORE_FAIL" if starts else "NO_NATIVE_START")
        )
    if terminal == PASS:
        need(
            report["launches"] == 3
            and not trouble
            and f["max_scope_bytes"] < API["STOP"]
            and f["swap_peak_bytes"] == 0
            and not any(f["memory_events_local"][k] for k in ("high", "max", "oom", "oom_kill")),
            "family closure",
        )
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("family", "prepared", "cpu", "client", "c55", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = review(a)
    except Exception as exc:
        r = {"status": "REVIEW_FAILED", "family_sha256": a.family_sha256, "reason": short(exc)}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(r, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    print(r["status"])
    return int(r["status"] == "REVIEW_FAILED")


if __name__ == "__main__":
    raise SystemExit(main())
