"""Two resource-qualified C270 runs of one private libllama, gating PFJ1 before a chat."""

import argparse
import os
import signal
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path

from linkage import (
    HERE,
    ORIGINAL,
    PROTOCOL,
    REPO,
    LibraryAuthority,
    Q,
    load_module,
    need,
    read,
    run_bounded,
    sha,
)
from smoke import save

OLD = Q / "nvme_r0_gate"
REFERENCE = "1f332ad437d90c24adf3b88b87ddf0dac8e13b7e87e818d93461ffd281c801b6"
STARTUP = "0d7d2dbd7993c1e16e1bbd7d77a4d1955754658e0b4fabe10819ad5fc026cb6a"
CAP = 64 + 262144 * 96
QUALIFIED = "776007768d490c7ce7c96774d35443567e933080b564295e433442383d98161a"
QUAL_PATH = OLD / "qualified_profile/profile.py"


def adjust_command(original, old_search, new_search, output, mode):
    need(mode in ("OFF", "ON"), "observer mode")
    cmd = list(original)
    for old, new in [
        (str(REPO / "tools/run_bounded.py"), str(HERE / "monitor.py")),
        ("LimitFSIZE=8388608", "LimitFSIZE=33554432"),
        ("LD_LIBRARY_PATH=" + old_search, "LD_LIBRARY_PATH=" + new_search),
        (str(output / "protocol.json"), str(output / "resource-phase.json")),
        ("C269-R0-selected189+32-E20_R0", "C269-phase-fd-selected189+32-" + mode),
    ]:
        need(cmd.count(old) == 1, "missing or repeated original field: " + old)
        cmd[cmd.index(old)] = new
    end = cmd.index("--", cmd.index("--env"))
    if mode == "ON":
        cmd[end:end] = ["--env", "TESY_PHASE_FD_FILE=" + str(output / "raw/phase.pfj1")]
    return cmd


def require_journal(grade):
    need(grade["status"] == "PASS", "PFJ1 failed conservation")
    calls = grade["calls"]
    need([row["tokens"] for row in calls] == [189] + [1] * 32, "incomplete C270 calls")
    need(
        [row["positions"] for row in calls] == [[0, 188]] + [[i, i] for i in range(189, 221)],
        "different C270 positions",
    )
    need(
        [row["tiles"] for row in calls] == [[32] * 5 + [29]] + [[1]] * 32, "different C270 ubatches"
    )


def check_evidence(a, measure):
    need(
        sha(HERE / "protocol.md") == PROTOCOL and sha(QUAL_PATH) == QUALIFIED, "pinned methodology"
    )
    pre = read(a.startup_dir / "receipt.json")
    need(
        sha(a.startup_dir / "receipt.json") == STARTUP
        and pre["status"] == "PASS_C270_C281_ONE_PROVIDER_STARTUP"
        and pre["preflight_sha256"] == a.preflight_sha256
        and pre["build_sha256"] == a.build_sha256
        and pre["finished_processes"] == 6
        and pre["model_launches"] == 0,
        "startup/build",
    )
    fixture = read(a.fixture_dir / "receipt.json")
    need(
        sha(a.fixture_dir / "receipt.json") == a.fixture_sha256
        and fixture["status"] == "PASS_C269_PHASE_FD_MANAGER_AND_BOUNDARIES"
        and fixture["context_proof"] == "pinned_source_markers_in_fixture"
        and fixture["build_sha256"] == a.build_sha256
        and fixture["candidate_sha256"] == read(a.build_dir / "receipt.json")["candidate_sha256"]
        and set(fixture["arms"]) == {"off-ok", "on-ok", "off-short", "on-short", "on-inherited"},
        "manager, overlapping work and failure fixture",
    )
    ref = a.r0_dir
    r = read(ref / "receipt.json")
    need(
        sha(ref / "receipt.json") == REFERENCE
        and r["status"] == "PASS_SELECTED_C269_BRIDGE"
        and r["preflight_sha256"] == a.preflight_sha256
        and r["monitor_stop"] is None
        and r["model_launch_receipts"] == 1
        and sha(ref / "selected.json") == r["selected_sha256"],
        "independent R0",
    )
    measure.check_gate(r["numerical_gate"])


def monitor_result(manifest, protocol, expected, measure):
    need(manifest["explicit_env"] == expected, "unexpected explicit observer or loader environment")
    actual = manifest["relevant_environment"]
    need(
        all(
            actual.get(k) == v
            for k, v in expected.items()
            if k not in {"LD_DEBUG_OUTPUT", "LD_DEBUG"}
        )
        and "LD_PRELOAD" not in actual
        and "TESY_PHASE_FD_TRIGGER" not in actual
        and ("TESY_PHASE_FD_FILE" in actual) == ("TESY_PHASE_FD_FILE" in expected),
        "different effective env",
    )
    # The legacy audit knows only the historical environment and the three qualified loader fields.
    # Validate the complete actual record above before projecting the single experimental addition.
    old = dict(
        manifest, explicit_env={k: v for k, v in expected.items() if k != "TESY_PHASE_FD_FILE"}
    )
    loader = {k: expected[k] for k in ("LD_LIBRARY_PATH", "LD_DEBUG", "LD_DEBUG_OUTPUT")}
    measure.check_monitor(old, protocol, protocol["pinned"], "E20_R0", loader_env=loader)


def run_arm(a, out, mode, up, measure, prepare):
    unit = a.unit + "-" + mode.lower()
    res = {"mode": mode, "unit": unit, "status": "FAIL_PRESERVED", "model_launch_receipts": 0}
    raw = out / "raw"
    mono = time.monotonic()
    try:
        b = Namespace(**vars(a))
        b.execute = False
        b.unit = unit
        b.envelope = "E20_R0"
        baseline = up.prepare_campaign(b, out)
        need(baseline["status"] == "PREPARED_ONLY", "C270 original preparation")
        ctl = LibraryAuthority(
            a.preflight_dir, a.preflight_sha256, a.build_dir, a.build_sha256, "C270", "candidate"
        )
        base = read(out / "qualified-protocol.json")
        schema = read(out / "protocol.json")
        for label in ("numerical_dso_sha256", "startup_dso_sha256"):
            hashes = schema["pinned"][label]
            need(hashes[ctl.image.name] == ORIGINAL, "original provider changed")
            hashes[ctl.image.name] = ctl.image_sha
        schema.update(
            phase_fd_observer=mode,
            phase_fd_original_protocol_sha256=sha(out / "protocol.json"),
            phase_fd_monitor_adapter_sha256=sha(HERE / "monitor.py"),
        )
        save(out / "resource-phase.json", schema)
        prefix = raw / "loader"
        expected = dict(base["native_explicit_env"], **ctl.child_env(prefix))
        journal = raw / "phase.pfj1"
        need(not journal.exists() and not journal.is_symlink(), "prior journal path")
        if mode == "ON":
            expected["TESY_PHASE_FD_FILE"] = str(journal)
        cmd = adjust_command(base["monitor"], ctl.original_search, ctl.native_search, out, mode)
        save(
            out / "phase-control.json",
            {
                "monitor": cmd,
                "env": expected,
                "build_sha256": a.build_sha256,
                "fixture_sha256": a.fixture_sha256,
                "image_sha256": ctl.image_sha,
                "original_sha256": ORIGINAL,
                "profile_sha256": sha(__file__),
                "smoke_sha256": STARTUP,
                "reference_sha256": REFERENCE,
                "resource_sha256": sha(out / "resource-phase.json"),
                "c55_sha256": a.window_sha256,
                "commit": a.measurement_commit,
            },
        )
        res["phase_control_sha256"] = sha(out / "phase-control.json")
        if not a.execute:
            res["status"] = "PREPARED_ONLY"
            return res
        need(
            prepare.file_identity(Path(cmd[-5])) == schema["model_stat"], "target identity at spawn"
        )
        res["monitor_provider"] = ctl.monitor_proof()
        ident, n, seen, wall = up.guarded_run(cmd, out, unit, ctl, measure, run_bounded)
        lp = raw / (unit + ".launch.json")
        mp = raw / (unit + ".json")
        manifest = read(mp)
        need(
            manifest["process_identity"] == ident == read(lp)["process_identity"]
            and manifest["limits"]["resource_protocol_sha256"] == sha(out / "resource-phase.json"),
            "process/contract mismatch",
        )
        monitor_result(manifest, schema, expected, measure)
        audit = ctl.audit(prefix, ident["pid"])
        need(
            set(audit["initialized_sha256"]) >= {Path(v).name for v in seen}
            and audit["initialized_sha256"][ctl.image.name] == ctl.image_sha,
            "loader/live mismatch",
        )
        res.update(
            launch_sha256=sha(lp),
            monitor_sha256=sha(mp),
            live_samples=n,
            authority=audit,
            scoped_wall_s=wall,
            elapsed_model_s=manifest["elapsed_s"],
            maxima=manifest["maxima"],
            monitor_stop=manifest["stop_reason"],
        )
        need(measure.file_bytes(raw) <= 128 * 2**20, "raw budget")
        with (out / "gate.log").open("xb") as log:
            subprocess.run(
                base["check"], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=45
            )
        grade = read(out / "selected.json")
        measure.check_gate(grade)
        res.update(selected_sha256=sha(out / "selected.json"), numerical_gate=grade)
        if mode == "OFF":
            need(not journal.exists() and not journal.is_symlink(), "journal appeared in OFF")
        else:
            need(
                journal.is_file()
                and not journal.is_symlink()
                and 64 < journal.stat().st_size <= CAP
                and journal.stat().st_mode & 0o777 == 0o600,
                "private PFJ1",
            )
            inspector = load_module(HERE.parent / "analyse.py", "phase_fd_frozen_audit")
            records, header = inspector.read_journal(journal)
            grade = inspector.audit(records, header, Path(cmd[-5]))
            save(out / "journal-audit.json", grade)
            res.update(
                journal_audit_sha256=sha(out / "journal-audit.json"),
                journal_sha256=sha(journal),
                journal_bytes=journal.stat().st_size,
            )
            require_journal(grade)
        res["status"] = "PASS_C270_" + mode
    except Exception as exc:
        res.update(error=str(exc), error_type=type(exc).__name__)
    finally:
        res.update(
            model_launch_receipts=int((raw / (unit + ".launch.json")).is_file()),
            raw_bytes=measure.file_bytes(raw),
            elapsed_arm_s=time.monotonic() - mono,
        )
        save(out / "receipt.json", res)
    return res


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "build-dir",
        "fixture-dir",
        "preflight-dir",
        "r0-dir",
        "startup-dir",
        "window",
        "placement",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in (
        "build-sha256",
        "fixture-sha256",
        "preflight-sha256",
        "window-sha256",
        "measurement-commit",
        "unit",
    ):
        p.add_argument("--" + k, required=True)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    a.checkout = REPO
    out = a.new_output_dir.resolve()
    os.umask(0o077)
    out.mkdir(mode=0o700)
    res = {
        "status": "FAIL_PRESERVED",
        "commit": a.measurement_commit,
        "arms": [],
        "model_launch_receipts": 0,
        "workload": "C270 log_medium 189+32 teacher-forced",
        "conversation": "NOT_RUN",
    }
    start = time.monotonic()

    def wall_limit(*_):
        raise TimeoutError("720 s family limit")

    signal.signal(signal.SIGALRM, wall_limit)
    signal.alarm(720)
    try:
        sys.path.insert(0, str(OLD))
        import measure
        import prepare

        check_evidence(a, measure)
        up = load_module(QUAL_PATH, "phase_qualified_c270")
        for mode in ("OFF", "ON"):
            need(time.monotonic() - start < 720, "family wall")
            d = out / mode
            d.mkdir()
            arm = run_arm(a, d, mode, up, measure, prepare)
            res["arms"].append(
                {
                    "mode": mode,
                    "status": arm["status"],
                    "receipt_sha256": sha(d / "receipt.json"),
                    "model_launch_receipts": arm["model_launch_receipts"],
                }
            )
            res["model_launch_receipts"] += arm["model_launch_receipts"]
            need(arm["status"] in {"PREPARED_ONLY", "PASS_C270_" + mode}, "arm stopped: " + mode)
        need(time.monotonic() - start <= 720, "family wall")
        res["status"] = "PASS_C270_PAIRED_NUMERIC_AND_JOURNAL" if a.execute else "PREPARED_ONLY"
    except Exception as exc:
        res.update(error=str(exc), error_type=type(exc).__name__)
    res.update(
        elapsed_s=time.monotonic() - start,
        build_sha256=a.build_sha256,
        fixture_sha256=a.fixture_sha256,
        smoke_sha256=STARTUP,
        reference_r0_sha256=REFERENCE,
        c55_sha256=a.window_sha256,
    )
    signal.alarm(0)
    save(out / "receipt.json", res)
    print(res["status"])
    return int(res["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
