"""Exercise the two natural verification cuts under the existing C55/C118 numerical supervisor."""

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
WAVE = HERE.parents[1]
T = run_path(WAVE / "target.py")
need, sha, read, save, prepare, measure, PF, PK, live = (
    T[k] for k in ("need", "sha", "read", "save", "prepare", "measure", "PF", "PK", "live")
)
Q, ROOT = T["Q"], T["ROOT"]
PLACE = run_path(Q / "nvme_conversation/contract.py")["placement"]
RESOURCE = run_path(ROOT / "tools/host_resource_policy.py")
POWER = run_path(Q / "packed_nvme_manifest/server_profile/system_driver/review.py")["power"]
GRADE = run_path(HERE / "grade.py")
CLIENT = "d8c39a975aea3fe9022c371f4bf13ad9b908d94f9647838d81babc7b99845745"
ROWS = "26de4923c71a3051352c4648059786ee52f0c3dc16d6d14a9806828663ecd7be"
LOADER = "278addbce2074535fcfbd1e33b82b4eb0f9dfda2d6ba4e0c4e40ca1f74f65419"
INVOCATION = "74569a2e670e8419b6e1be10f4a75a4259d5636672836b63c086401074ebbfb2"
RESOURCE_TEMPLATE = "568ba6e9acb3492383f53391065e2900538acecc0444ee870c3b0b305b16fba0"
ORDER = ("R", "W", "OFF", "ON")


def checked(path, h):
    need(sha(path) == h, "seal " + path.name)
    return read(path)


def provider(a, out, role, build, client):
    exe = a.client / "code-cut"
    ctl = T["Provider"](
        a,
        out,
        "ORIGINAL" if role == "R" else "PRICE",
        exe,
        client["files"]["code-cut"],
        build["arms"]["PRICE"],
        selection="C270_R0" if role == "R" else "C270_PACK",
        kind="PRICE",
    )
    ctl.mode = "OFF" if role == "R" else "ON"
    ctl.loader_cache = run_path(WAVE / "supplied/loader.py")["checked"](a.loader_probe, LOADER)
    if role in ("OFF", "ON"):
        img = checked(a.rows / "receipt.json", ROWS)["images"]["CPU"]
        key = "libllama.so.0"
        path = Path(img["image"]).resolve(strict=True)
        old = ctl.verified["closure"][key]["file"]
        need(sha(path) == img["image_sha256"], "row provider image")
        for table in (ctl.files, ctl.stats, ctl.keys):
            del table[old]
        ctl.initial.remove(old)
        ctl.files[str(path)] = img["image_sha256"]
        ctl.stats[str(path)] = T["AU"]["identity"](path)
        ctl.keys[str(path)] = T["AU"]["reference_key"](str(path), ctl.stats[str(path)])
        ctl.initial.add(str(path))
        ctl.allowed = set(ctl.files)
        ctl.verified["closure"][key] = dict(file=str(path), sha256=img["image_sha256"])
        overlay = out / "rows"
        overlay.mkdir()
        (overlay / key).symlink_to(path)
        ctl.search = str(overlay) + os.pathsep + ctl.search
    env = T["H"]["SC"]["OLD"]["environment"](ctl.search.split(os.pathsep))
    expected = {k: v["file"] for k, v in ctl.verified["closure"].items()}
    for label, cmd in (
        ("list", [T["H"]["SC"]["OLD"]["LOADER"], "--list", exe]),
        ("relocate", ["/usr/bin/ldd", "-r", exe]),
    ):
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=25)
        log = proc.stdout + proc.stderr
        (out / ("selected-" + label + ".log")).write_text(log)
        need(
            proc.returncode == 0
            and not re.search("undefined symbol|not found|/stubs/", log)
            and {
                k: str(v.resolve(strict=True))
                for k, v in T["H"]["SC"]["OLD"]["interpret"](log).items()
            }
            == expected,
            "selected " + label,
        )
    ctl.recheck()
    test = subprocess.run(
        [exe, "--self-test"], env=env, capture_output=True, text=True, check=True, timeout=20
    )
    need(test.stdout.strip() == "PASS_CODE_CUT_HASH", "actual closure self-test")
    return ctl


def arm(a, folder, role, client, build, policy, model_id):
    folder.mkdir()
    unit = a.unit + "-" + role.lower()
    ctl = provider(a, folder, role, build, client)
    template = checked(a.template / "invocation.json", INVOCATION)
    old = checked(a.template / "natural-resource.json", RESOURCE_TEMPLATE)
    template_cmd = template["command"]
    model = Path(template_cmd[-4])
    work = a.client / "work.json"
    need(
        model.resolve(strict=True) == ctl.data_paths["model"] and model_id == old["model_stat"],
        "internal model",
    )
    backend = Path(template_cmd[template_cmd.index("--backend-root") + 1])
    if role == "R":
        backend = Path(read(prepare.BASE)["backend_root"])
    source = prepare.git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
    locks = read(Q / "nvme_r0_gate/inputs/receipt.json") if role == "R" else old["pinned"]
    need(
        source == [locks["backend_commit"], locks["backend_tree"]]
        and not prepare.git(backend, "status", "--porcelain"),
        "backend source",
    )
    dsos = {Path(v["file"]).name: v["sha256"] for v in ctl.verified["closure"].values()}
    pinned = old["pinned"] | dict(
        capture_sha256=client["files"]["code-cut"],
        ids_sha256=client["files"]["work.json"],
        startup_dso_sha256=dsos,
        numerical_dso_sha256={k: dsos[k] for k in old["pinned"]["numerical_dso_sha256"]},
        backend_commit=source[0],
        backend_tree=source[1],
    )
    shutil.copyfile(a.window / "resource-policy.json", folder / "resource-policy.json")
    reserve = 3 if role == "ON" else 1
    pro = old | dict(
        schema="tesy-code-cut-v1",
        case=role,
        mode=role,
        execution_scope_unit=unit,
        pinned=pinned,
        measurement_commit=a.commit,
        output_reserve=reserve,
        scientific_protocol_sha256=sha(HERE / "protocol.md"),
        resources=RESOURCE["freeze_protocol_resource_limits"](
            policy, cgroup_memory_max_bytes=20 << 30
        ),
        start_inventory=old["start_inventory"]
        | dict(policy_sha256=sha(folder / "resource-policy.json")),
    )
    RESOURCE["validate_resource_protocol"](pro)
    config = folder / "resource.json"
    save(config, pro)
    raw = folder / "raw"
    raw.mkdir()
    cap = raw / (unit + ".capture")
    monitor = T["H"]["RB"]["P"]["MONITOR"]
    need(sha(monitor) == old["runner_sha256"], "resource monitor")
    cmd = template_cmd[: template_cmd.index("--env")]
    cmd[cmd.index("--unit=" + old["execution_scope_unit"])] = "--unit=" + unit
    cmd[cmd.index("-B") + 1] = str(monitor)
    for flag, value in (
        ("--run-id", unit),
        ("--output-root", raw),
        ("--backend-root", backend),
        ("--variant", "code-cut-" + role),
        ("--workload", work),
        ("--resource-protocol", config),
    ):
        cmd[cmd.index(flag) + 1] = str(value)
    common = dict(
        TESY_CPU_WAVE_SKIP_PARKED="1",
        LD_LIBRARY_PATH=ctl.search,
        LD_DEBUG="libs",
        LD_DEBUG_OUTPUT=str(raw / "loader"),
    )
    expected = common | dict(TESY_TEST_OUTPUT_RESERVE=str(reserve))
    if role != "R":
        expected.update(
            {live.STORE_ENV: str(ctl.data_paths["manifest"]), "TESY_NATIVE_CPU_WAVE": "1"}
        )
    if role == "ON":
        expected.update({k: v for k, v in template["expected"].items() if k.startswith("TESY_B3_")})
    argv = list(map(str, (ctl.exe, model, work, role, cap)))
    cmd.extend(k for pair in expected.items() for k in ("--env", "=".join(pair)))
    cmd += ["--", *argv]
    save(folder / "invocation.json", dict(command=cmd, expected=expected))
    if a.prepare_only:
        return dict(role=role, status="PREFLIGHT_ONLY")
    PK["PK"]["age"](policy, datetime.now(UTC))
    driver = T["AU"]["Authority"].monitor_proof(ctl.monitor)
    ident, samples, mapped, wall = PF["guarded_run"](
        cmd, folder, unit, ctl, measure, T["N"]["run_bounded"]
    )
    mon, launch = (read(raw / (unit + s)) for s in (".json", ".launch.json"))
    need(
        mon["explicit_env"] == expected
        and mon["command"] == argv
        and all(
            mon["relevant_environment"].get(k) == v
            for k, v in expected.items()
            if k not in ("LD_DEBUG", "LD_DEBUG_OUTPUT")
        )
        and {k for k in mon["relevant_environment"] if k.startswith("TESY_")}
        == {k for k in expected if k.startswith("TESY_")}
        and mon["process_identity"] == launch["process_identity"] == ident
        and mon["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(config),
        "live process, environment or resource identity",
    )
    PF["check_native_manifest"](dict(mon, explicit_env=common), pro, pinned, common, measure)
    inventory = PK["PK"]["compact"].validate_inventory(
        folder, unit, dict(native_explicit_env=expected), launch
    )
    age = PK["PK"]["age"](
        policy, datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
    )
    fds = live.CaptureAuthority.fd_evidence(ctl)
    audit = ctl.audit(raw, ident["pid"])
    need({Path(p).name for p in mapped} <= audit["initialized"].keys(), "mapped closure")
    save(
        folder / "authority.json",
        dict(loader=audit, driver=driver, fd=fds, data=ctl.loader_cache.receipt()),
    )
    log = (raw / (unit + ".stderr")).read_text()
    need(
        re.findall(r"llama_context: n_outputs_max\s*=\s*(\d+)", log) == [str(reserve)],
        "live reserve",
    )
    layers = [int(n) for n in re.findall(r"^tesy_b3_built attention (\d+) \d+$", log, re.M)]
    need(
        (bool(layers) == (role == "ON")) and (not layers or set(layers) == set(range(36))),
        "block graph coverage",
    )
    proof = GRADE["inspect"](cap, role)
    save(folder / "proof.json", proof)
    return dict(
        role=role,
        unit=unit,
        proof_sha256=sha(folder / "proof.json"),
        scope_s=wall,
        model_s=mon["elapsed_s"],
        maxima=mon["maxima"],
        energy=POWER(folder, dict(unit=unit)),
        samples=samples,
        c118=inventory,
        c55_age_s=age,
        pack_fd_samples=fds["positive_samples"],
        layers=sorted(set(layers)),
        monitor_sha256=sha(raw / (unit + ".json")),
        argv_sha256=sha(folder / "invocation.json"),
    )


def main(a, out, r):
    head, tree = prepare.git(ROOT, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
    need(
        head == a.commit
        and not prepare.git(ROOT, "status", "--porcelain")
        and re.fullmatch("tesy-code-cut-[a-z0-9-]+", a.unit),
        "clean measurement identity",
    )
    client = checked(a.client / "receipt.json", CLIENT)
    need(
        client["protocol_sha256"] == sha(HERE / "protocol.md")
        and all(sha(a.client / p) == d for p, d in client["files"].items()),
        "build files",
    )
    build = checked(a.build_dir / "receipt.json", T["BUILD"])
    win = checked(a.window / "receipt.json", a.window_sha256)
    start = json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    need(
        win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not win["reason"]
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and datetime.fromisoformat(start).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "C55",
    )
    policy, model_id = PLACE(a.window, a.archive / "part-01/placement/r1/receipt.json")
    r.update(
        commit=head,
        tree=tree,
        window_sha256=a.window_sha256,
        client_sha256=CLIENT,
        protocol_sha256=sha(HERE / "protocol.md"),
        unit=a.unit,
        arms=[],
    )
    save(
        out / "provenance.json",
        r
        | dict(
            order=ORDER, runner_sha256=sha(HERE / "run.py"), grader_sha256=sha(HERE / "grade.py")
        ),
    )
    proofs = {}
    started = time.monotonic()
    for role in ORDER:
        r["stage"] = role
        f = out / role
        result = arm(a, f, role, client, build, policy, model_id)
        r["arms"].append(result)
        if not a.prepare_only:
            proofs[role] = read(f / "proof.json")
            comparison = GRADE["compare"](proofs, role)
            save(f / "comparison.json", comparison)
            failed = [k for k, v in comparison.items() if not v]
            result.update(comparisons=len(comparison), failed=failed)
            need(not failed, "numerical mismatch " + str(failed))
        print(role, "PREPARED" if a.prepare_only else "PASS", flush=True)
        need(
            time.monotonic() - started <= 25 * 60 and measure.file_bytes(out) <= 600 << 20,
            "family budget",
        )
    r["status"] = "PREPARED_ONLY" if a.prepare_only else "PASS_TWO_CODE_CUTS"


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for key in (
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
        cli.add_argument("--" + key, type=lambda s: Path(s).resolve(), required=True)
    for key in ("unit", "commit", "window-sha256"):
        cli.add_argument("--" + key, required=True)
    cli.add_argument("--prepare-only", action="store_true")
    a = cli.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    r = dict(status="FAIL_PRESERVED")
    started = time.monotonic()
    try:
        with (out.parent / "tesy-code-cut.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            main(a, out, r)
    except Exception as exc:
        r.update(reason=str(exc), error_type=type(exc).__name__)
    r["elapsed_s"] = time.monotonic() - started
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""), flush=True)
    raise SystemExit(int(r["status"] not in ("PREPARED_ONLY", "PASS_TWO_CODE_CUTS")))
