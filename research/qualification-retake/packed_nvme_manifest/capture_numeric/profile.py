"""Run the pre-registered C292 selected-numerical pair with the existing E20 supervisor."""

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live  # noqa: E402

need, sha, read = live.need, live.sha, live.read
Q, REPO = live.QUAL, live.REPO
PFJ = Q / "phase_fd/integrated/profile"
OLD = Q / "nvme_r0_gate"
up = live.linkage.load_module(OLD / "qualified_profile/profile.py", "c270_guarded_c292")
compact = live.linkage.load_module(OLD / "qualified_profile/compact.py", "c270_close_c292")
sys.path.insert(0, str(OLD))
import measure  # noqa: E402
import prepare  # noqa: E402

save = up.save
METHOD = "502ecd6f350c3bcafcd6be15877c430d7ef8ce66eb10e615e1dff9493250a814"
MIB = 1024**2


def replace_once(cmd, old, new):
    need(cmd.count(old) == 1, "missing/ambiguous original field: " + old)
    cmd[cmd.index(old)] = new


def command(base, ctl, out, mode, original_root):
    cmd = list(base)
    for old, new in (
        (str(REPO / "tools/run_bounded.py"), str(PFJ / "monitor.py")),
        ("LD_LIBRARY_PATH=" + ctl.original_search, "LD_LIBRARY_PATH=" + ctl.native_search),
        (str(out / "protocol.json"), str(out / "resource-store.json")),
        ("C269-R0-selected189+32-E20_R0", "C291-store-selected189+32-" + mode),
    ):
        replace_once(cmd, old, new)
    pos = cmd.index("--backend-root") + 1
    need(
        Path(cmd[pos]).resolve(strict=True) == original_root.resolve(strict=True),
        "unexpected original backend root",
    )
    cmd[pos] = str(ctl.backend)
    end = cmd.index("--", cmd.index("--env"))
    need(
        len(cmd[end + 1 :]) == 6
        and Path(cmd[end + 1]).resolve(strict=True) == ctl.original_exe
        and cmd[-2:] == ["--ngl", "12"]
        and Path(cmd[end + 2]).resolve(strict=True) == ctl.data_paths["model"]
        and cmd[cmd.index("--timeout-s") + 1] == "240",
        "changed C270 command",
    )
    cmd[end + 1] = str(ctl.exe)
    if mode == "ON":
        cmd[end:end] = ["--env", live.STORE_ENV + "=" + str(ctl.data_paths["manifest"])]
    else:
        need(mode == "OFF", "arm")
    return cmd


def validate_monitor(m, expected, protocol):
    need(
        expected == m["explicit_env"]
        and all(
            m["relevant_environment"].get(k) == v
            for k, v in expected.items()
            if k not in ("LD_DEBUG", "LD_DEBUG_OUTPUT")
        )
        and (live.STORE_ENV in m["relevant_environment"]) == (live.STORE_ENV in expected)
        and "LD_PRELOAD" not in m["relevant_environment"],
        "actual native capture environment",
    )
    # The C270 validator has no slot for the experimental variable. It has been checked above.
    downstream = dict(m, explicit_env={k: v for k, v in expected.items() if k != live.STORE_ENV})
    measure.check_monitor(
        downstream,
        protocol,
        protocol["pinned"],
        "E20_R0",
        loader_env={k: expected[k] for k in ("LD_LIBRARY_PATH", "LD_DEBUG", "LD_DEBUG_OUTPUT")},
    )


def age(policy, timestamp):
    delta = (timestamp - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    need(0 <= delta < 3600, "C55 older than one hour or from the future")
    return delta


def arm(a, out, mode, gold):
    import grade

    unit = a.unit + "-" + mode.lower()
    csv_root = out / "raw"
    receipt = {"status": "FAIL_PRESERVED", "unit": unit, "mode": mode, "model_launch_receipts": 0}
    try:
        ctl = live.CaptureAuthority(a, mode)
        args = argparse.Namespace(**(vars(a) | dict(unit=unit, execute=False)))
        established = up.prepare_campaign(args, out)
        need(established["status"] == "PREPARED_ONLY", "independent C270/C127 preflight")
        baseline = read(out / "qualified-protocol.json")
        protocol = read(out / "protocol.json")
        pinned = protocol["pinned"]
        original = prepare.load(prepare.BASE)
        source_root = Path(original["backend_root"])
        need(
            pinned["backend_commit"] == live.linkage.WORKER
            and prepare.git(ctl.backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
            == [live.static.PIN, live.static.TREE]
            and not prepare.git(ctl.backend, "status", "--porcelain"),
            "C291 source",
        )
        for key in ("numerical_dso_sha256", "startup_dso_sha256"):
            image = Path(ctl.links[live.static.SONAME][1]).name
            need(pinned[key][image] == live.static.C269, "unexpected control libllama digest")
            pinned[key][image] = live.static.C291
        pinned.update(
            backend_commit=live.static.PIN,
            backend_tree=live.static.TREE,
            capture_sha256=live.static.CAPTURE,
        )
        protocol.update(
            schema="tesy-c292-nvme-numerical-v1",
            original_protocol_sha256=sha(out / "protocol.json"),
            method_sha256=METHOD,
            metadata_sha256=live.DERIVED,
            static_receipt_sha256=live.CLOSURE,
            runner_sha256=sha(PFJ / "monitor.py"),
            original_runner_sha256=sha(REPO / "tools/run_bounded.py"),
            gate_sha256=sha(REPO / "tools/expert_store_numeric_gate.py"),
        )
        save(out / "resource-store.json", protocol)
        fds = ctl.data_paths
        need(protocol["model_stat"] == ctl.data_stats["model"], "model across authorities")
        spec = command(baseline["monitor"], ctl, out, mode, source_root)
        env = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | ctl.child_env(csv_root / "loader")
        if mode == "ON":
            env[live.STORE_ENV] = str(fds["manifest"])
        capture = csv_root / (unit + ".capture")
        need(
            Path(spec[-3]) == capture and not capture.exists() and not capture.is_symlink(),
            "fresh capture destination",
        )
        save(
            out / "store-argv.json",
            dict(
                argv=spec,
                explicit=env,
                mode=mode,
                metadata=ctl.data_stats,
                resource_sha256=sha(out / "resource-store.json"),
                control_sha256=sha(out / "qualified-protocol.json"),
                c55_sha256=a.window_sha256,
                closure_sha256=live.CLOSURE,
                method_sha256=METHOD,
            ),
        )
        receipt.update(
            contract_sha256=sha(out / "store-argv.json"),
            resource_sha256=sha(out / "resource-store.json"),
            historical_protocol_sha256=live.static.C292,
        )
        if not a.execute:
            receipt["status"] = "PREPARED_ONLY"
            return receipt
        # NVML uses only the monitor selection; CUDA libraries are selected in the child.
        receipt["monitor_provider"] = ctl.monitor_proof()
        policy = read(out / "resource-policy.json")
        ctl.check_c55_before_first_live = lambda: age(policy, datetime.now(UTC))
        ctl.check_c55_before_first_live()
        ident, n, seen, wall = up.guarded_run(
            spec, out, unit, ctl, measure, live.linkage.run_bounded
        )
        manifest_path = csv_root / (unit + ".json")
        launch_path = csv_root / (unit + ".launch.json")
        m, launch = read(manifest_path), read(launch_path)
        need(
            ident == m["process_identity"] == launch["process_identity"]
            and m["limits"]["resource_protocol_sha256"]
            == launch["resource_protocol_sha256"]
            == receipt["resource_sha256"],
            "PID and resource closure",
        )
        validate_monitor(m, env, protocol)
        receipt["c55_age_at_spawn_s"] = age(
            policy, datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
        )
        receipt["c118"] = compact.validate_inventory(
            out, unit, {"native_explicit_env": env}, launch
        )
        audit = ctl.audit(csv_root / "loader", ident["pid"])
        need(
            {Path(path).name for path in seen} <= set(audit["initialized_sha256"])
            and audit["initialized_sha256"][image] == live.static.C291,
            "startup/runtime census",
        )
        receipt.update(
            pack=ctl.fd_evidence(),
            loader=audit,
            live_samples=n,
            monitor_sha256=sha(manifest_path),
            launch_sha256=sha(launch_path),
            maxima=m["maxima"],
            kernel=ctl.pre["kernel"],
            child_exit=m["returncode"],
            monitor_stop=m["stop_reason"],
            scope_cleanup=True,
            scoped_wall_s=wall,
            model_s=m["elapsed_s"],
        )
        need(measure.file_bytes(csv_root) <= 128 * MIB, "raw budget")
        with (out / "c127-check.log").open("xb") as log:
            subprocess.run(
                baseline["check"], stdout=log, stderr=subprocess.STDOUT, timeout=45, check=True
            )
        c127 = read(out / "selected.json")
        measure.check_gate(c127)
        numeric = grade.check_arm(capture, csv_root / (unit + ".stdout"), gold, c127)
        need(numeric["status"] == "PASS_C292_ARM_NUMERICS", "incomplete C292 arm grade")
        save(out / "numerical.json", numeric)
        receipt.update(
            status="PASS_C292_" + mode,
            numerical=numeric,
            numerical_sha256=sha(out / "numerical.json"),
            c127_sha256=sha(out / "selected.json"),
        )
        return receipt
    except Exception as exc:
        receipt["reason"] = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, grade.FidelityMismatch):
            receipt["fidelity"] = "FAIL_SELECTED_FIDELITY"
        raise
    finally:
        receipt.update(
            raw_bytes=measure.file_bytes(csv_root),
            model_launch_receipts=int((csv_root / (unit + ".launch.json")).is_file()),
        )
        # Exception text and unsuccessful partial data belong in the parent closure as well.
        save(out / "receipt.json", receipt)


def campaign(a, out, r):
    import grade

    need(
        sha(HERE / "protocol.md") == METHOD
        and sha(PFJ / "monitor.py")
        == "0d83807c24f650829becd8b2060b2058bfa624c8656e3d4dc1819ada3adef86e"
        and sha(PFJ / "linkage.py")
        == "e63827c6e57517da4e80f61fe0e9db38b513ba9114ab2395a6fdb7783e65c9af"
        and prepare.git(REPO, "rev-parse", "HEAD") == a.measurement_commit
        and not prepare.git(REPO, "status", "--porcelain"),
        "clean freeze and source",
    )
    a.checkout = REPO
    a.preflight_sha256 = live.static.PREFLIGHT
    gold = grade.reference(a.r0_dir)
    a.closure_dir = a.closure_dir.resolve(strict=True)
    for name in ("OFF", "ON"):
        d = out / name
        d.mkdir()
        try:
            row = arm(a, d, name, gold)
            need(
                row["status"] == ("PASS_C292_" + name if a.execute else "PREPARED_ONLY"),
                "incomplete arm",
            )
        finally:
            if (d / "receipt.json").is_file():
                evidence = read(d / "receipt.json")
                r["arms"].append(
                    {
                        "mode": name,
                        "status": evidence["status"],
                        "receipt_sha256": sha(d / "receipt.json"),
                    }
                )
                r["model_launch_receipts"] += evidence["model_launch_receipts"]
    if a.execute:
        paths = [out / m / "raw" / (a.unit + "-" + m.lower() + ".capture") for m in ("OFF", "ON")]
        pair = grade.check_pair(*paths)
        need(pair["status"] == "PASS_C292_OFF_ON_SELECTED", "incomplete OFF/ON grade")
        save(out / "pair.json", pair)
        r["pair_sha256"] = sha(out / "pair.json")
    r["status"] = "PASS_SELECTED_C292_NVME_PAIR" if a.execute else "PREPARED_ONLY"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "closure-dir",
        "preflight-dir",
        "r0-dir",
        "derived-dir",
        "constructor-receipt",
        "window",
        "placement",
        "new-output-dir",
    ):
        p.add_argument("--" + arg, type=Path, required=True)
    for arg in ("window-sha256", "measurement-commit", "unit"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    result = dict(
        status="FAIL_PRESERVED",
        arms=[],
        model_launch_receipts=0,
        commit=a.measurement_commit,
        c55_sha256=a.window_sha256,
        closure_sha256=live.CLOSURE,
    )

    def timeout(*_):
        raise TimeoutError("720 s family budget")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(720)
    try:
        campaign(a, out, result)
    except Exception as exc:
        result.update(reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    result["elapsed_s"] = time.monotonic() - start
    result["unexecuted_arms"] = [
        m for m in ("OFF", "ON") if m not in {x["mode"] for x in result["arms"]}
    ]
    save(out / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
