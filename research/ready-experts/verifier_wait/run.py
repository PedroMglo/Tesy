"""Run the nominal A/B barrier probe using the previously qualified numerical supervisor."""

import argparse
import fcntl
import os
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(HERE.parent / "cpu_wave/code_chat/block/run.py")
T, PF, PK, live, need, read, save, sha, checked = (
    B[k] for k in ("T", "PF", "PK", "live", "need", "read", "save", "sha", "checked")
)
G = run_path(HERE / "grade.py")
ORDER = ("S", "B0a", "B1", "B0b")
PREVIOUS = "7616d59b0f9db28b0f65f6e482e4e22386675d2bd1ec5b06f2b87c577c967138"


def arm(a, folder, role, client, build, policy, model_id, past):
    folder.mkdir()
    mode = "OFF" if role == "S" else "ON"
    ctl = B["provider"](a, folder, mode, build, client)
    source = next(r for r in past["arms"] if r["role"] == mode)
    ref = a.template / mode
    template = checked(ref / "invocation.json", source["argv_sha256"])
    old_mon = checked(ref / "raw" / (source["unit"] + ".json"), source["monitor_sha256"])
    old = checked(ref / "resource.json", old_mon["limits"]["resource_protocol_sha256"])
    original = template["command"]
    unit = a.unit + "-" + role.lower()
    work = a.client / "work.json"
    model = ctl.data_paths["model"]
    backend = Path(original[original.index("--backend-root") + 1])
    ids = B["prepare"].git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
    need(
        ids == [old["pinned"]["backend_commit"], old["pinned"]["backend_tree"]]
        and not B["prepare"].git(backend, "status", "--porcelain")
        and model == Path(old_mon["command"][1]).resolve(strict=True)
        and model_id == old["model_stat"],
        "physical source and NVMe identity",
    )
    dsos = {Path(v["file"]).name: v["sha256"] for v in ctl.verified["closure"].values()}
    need(dsos == old["pinned"]["startup_dso_sha256"], "numerical ELF closure")
    pinned = old["pinned"] | dict(
        capture_sha256=client["files"]["code-cut"], ids_sha256=client["files"]["work.json"]
    )
    shutil.copyfile(a.window / "resource-policy.json", folder / "resource-policy.json")
    policy_sha = sha(folder / "resource-policy.json")
    pro = old | dict(
        schema="tesy-verifier-wait-v1",
        case=role,
        mode=mode,
        execution_scope_unit=unit,
        pinned=pinned,
        measurement_commit=a.commit,
        scientific_protocol_sha256=sha(HERE / "protocol.md"),
        resources=B["RESOURCE"]["freeze_protocol_resource_limits"](
            policy, cgroup_memory_max_bytes=20 << 30
        ),
        start_inventory=old["start_inventory"] | dict(policy_sha256=policy_sha),
    )
    B["RESOURCE"]["validate_resource_protocol"](pro)
    config = folder / "resource.json"
    save(config, pro)
    raw = folder / "raw"
    raw.mkdir()
    cap = raw / (unit + ".capture")
    cmd = original[: original.index("--env")]
    monitor = T["H"]["RB"]["P"]["MONITOR"]
    need(sha(monitor) == old["runner_sha256"], "resource monitor")
    cmd[cmd.index("-B") + 1] = str(monitor)
    cmd[cmd.index("--unit=" + source["unit"])] = "--unit=" + unit
    for flag, path in (
        ("--run-id", unit),
        ("--output-root", raw),
        ("--variant", "verifier-wait-" + role),
        ("--workload", work),
        ("--resource-protocol", config),
    ):
        cmd[cmd.index(flag) + 1] = str(path)
    expected = template["expected"] | dict(
        LD_LIBRARY_PATH=ctl.search, LD_DEBUG_OUTPUT=str(raw / "loader")
    )
    need(expected[live.STORE_ENV] == str(ctl.data_paths["manifest"]), "store manifest")
    common = {
        k: expected[k]
        for k in ("LD_LIBRARY_PATH", "LD_DEBUG_OUTPUT", "LD_DEBUG", "TESY_CPU_WAVE_SKIP_PARKED")
    }
    cmd.extend(s for k, v in expected.items() for s in ("--env", k + "=" + v))
    argv = list(map(str, (ctl.exe, model, work, role, cap)))
    cmd.extend(["--", *argv])
    save(folder / "invocation.json", dict(command=cmd, expected=expected))
    if a.prepare_only:
        return dict(role=role, status="PREPARED")
    PK["PK"]["age"](policy, datetime.now(UTC))
    driver = T["AU"]["Authority"].monitor_proof(ctl.monitor)
    ident, samples, mapped, wall = PF["guarded_run"](
        cmd, folder, unit, ctl, B["measure"], T["N"]["run_bounded"]
    )
    mon, launch = (read(raw / (unit + s)) for s in (".json", ".launch.json"))
    need(
        mon["explicit_env"] == expected
        and mon["command"] == argv
        and mon["process_identity"] == launch["process_identity"] == ident
        and launch["resource_protocol_sha256"]
        == mon["limits"]["resource_protocol_sha256"]
        == sha(config),
        "actual process, argv or limits",
    )
    relevant = mon["relevant_environment"]
    need(
        all(
            relevant.get(k) == v
            for k, v in expected.items()
            if k not in ("LD_DEBUG", "LD_DEBUG_OUTPUT")
        )
        and {k for k in relevant if k.startswith("TESY_")}
        == {k for k in expected if k.startswith("TESY_")},
        "live environment",
    )
    PF["check_native_manifest"](dict(mon, explicit_env=common), pro, pinned, common, B["measure"])
    inv = PK["PK"]["compact"].validate_inventory(
        folder, unit, dict(native_explicit_env=expected), launch
    )
    age = PK["PK"]["age"](
        policy, datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
    )
    fds = live.CaptureAuthority.fd_evidence(ctl)
    audit = ctl.audit(raw, ident["pid"])
    need({Path(p).name for p in mapped} <= audit["initialized"].keys(), "mapped libraries")
    save(
        folder / "authority.json",
        dict(loader=audit, driver=driver, fd=fds, data=ctl.loader_cache.receipt()),
    )
    log = (raw / (unit + ".stderr")).read_text()
    layers = set(map(int, re.findall(r"^tesy_b3_built attention (\d+) \d+$", log, re.M)))
    need(
        layers == (set() if mode == "OFF" else set(range(36)))
        and re.findall(r"llama_context: n_outputs_max\s*=\s*(\d+)", log)
        == [expected["TESY_TEST_OUTPUT_RESERVE"]],
        "executed graph",
    )
    return dict(
        role=role,
        unit=unit,
        native_sha256=sha(cap / "native.json"),
        scope_s=wall,
        model_s=mon["elapsed_s"],
        samples=samples,
        c118=inv,
        c55_age_s=age,
        maxima=mon["maxima"],
        energy=B["POWER"](folder, dict(unit=unit)),
        fd_samples=fds["positive_samples"],
        monitor_sha256=sha(raw / (unit + ".json")),
        argv_sha256=sha(folder / "invocation.json"),
    )


def run(a, out, r):
    git = B["prepare"].git
    head, tree = git(HERE, "rev-parse", "HEAD", "HEAD^{tree}").split()
    need(
        a.commit == head
        and not git(HERE, "status", "--porcelain")
        and re.fullmatch(r"tesy-verifier-wait-[a-z0-9-]+", a.unit),
        "clean identity",
    )
    client = checked(a.client / "receipt.json", a.client_sha256)
    need(
        client["protocol_sha256"] == sha(HERE / "protocol.md")
        and client["native_source_sha256"] == sha(HERE / "probe.cpp.in")
        and all(sha(a.client / k) == h for k, h in client["files"].items()),
        "frozen probe",
    )
    previous = checked(a.template / "receipt.json", PREVIOUS)
    build = checked(a.build_dir / "receipt.json", T["BUILD"])
    win = checked(a.window / "receipt.json", a.window_sha256)
    need(
        win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not win["reason"]
        and win["window_sha256"] == sha(a.window / "samples.jsonl")
        and win["span_s"] >= 60,
        "C55",
    )
    policy, model_id = B["PLACE"](a.window, a.archive / "part-01/placement/r1/receipt.json")
    r.update(
        commit=head, tree=tree, unit=a.unit, protocol_sha256=sha(HERE / "protocol.md"), arms=[]
    )
    save(
        out / "provenance.json",
        dict(
            **r,
            order=ORDER,
            args=sys.argv,
            source_sha256={
                n: sha(HERE / n)
                for n in ("protocol.md", "probe.cpp.in", "build.py", "run.py", "grade.py")
            },
            client_sha256=a.client_sha256,
            backend_build_sha256=T["BUILD"],
            window_sha256=a.window_sha256,
            previous=PREVIOUS,
        ),
    )
    original = read(a.client / "work.json")
    data = {}
    started = time.monotonic()
    for role in ORDER:
        r["stage"] = role
        f = out / role
        receipt = arm(a, f, role, client, build, policy, model_id, previous)
        r["arms"].append(receipt)
        if not a.prepare_only:
            native = next((f / "raw").glob("*.capture/native.json"))
            data[role] = checked(native, receipt["native_sha256"])
            G["verify"](data, original)
        print(role, "PREPARED" if a.prepare_only else "PASS", flush=True)
        need(
            time.monotonic() - started < 1500 and B["measure"].file_bytes(out) < 512 << 20,
            "family budget",
        )
    r["status"] = "PREPARED_ONLY" if a.prepare_only else "MEASURED_VERIFIER_WAIT"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "archive",
        "derived",
        "client",
        "build-dir",
        "rows",
        "template",
        "loader-probe",
        "window",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    for k in ("commit", "unit", "client-sha256", "window-sha256"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--prepare-only", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    result = dict(status="FAIL_PRESERVED")
    start = time.monotonic()
    try:
        with (out.parent / "tesy-verifier-wait.lock").open("a") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(a, out, result)
    except Exception as exc:
        result.update(reason=str(exc), error_type=type(exc).__name__)
    result["elapsed_s"] = time.monotonic() - start
    save(out / "receipt.json", result)
    print(result["status"], result.get("reason", ""), flush=True)
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
