"""Run the isolated L25 switch OFF and ON under the requalified four-worker target."""

import argparse
import fcntl
import json
import os
import re
import signal
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
G = run_path(str(HERE / "grade.py"))
K = run_path(str(HERE / "build.py"))
M, P, S, need, read, sha, save = (K[k] for k in ("M", "P", "S", "need", "read", "sha", "save"))
PF, R, N, SC, OLD, prepare, measure = (
    P[k] for k in ("PF", "R", "N", "SC", "OLD", "prepare", "measure")
)
BUILD = "8840e511e92f6124f6ffd619d5495c46f3419e99f600648c69dfd641c261c0af"


def targets(parent, family):
    return {
        key: parent / key / "raw" / (family["unit"] + "-" + key.lower() + ".capture")
        for key in ("AR", "B3")
    }


def audit(directory, unit, cfg, cmd, arm):
    raw = directory / "raw"
    mon, launch = (read(raw / (unit + k)) for k in (".json", ".launch.json"))
    first = cmd.index("--env")
    env = {}
    for i in range(first, cmd.index("--", first), 2):
        k, v = cmd[i + 1].split("=", 1)
        need(cmd[i] == "--env" and k not in env, "environment")
        env[k] = v
    bits = {P["B"]["ON"]: "1", M["OPTION"]: "1" if arm == "ON" else "0"}
    need(
        env == mon["explicit_env"]
        and all(env.get(k) == mon["relevant_environment"].get(k) == v for k, v in bits.items())
        and mon["command"] == cmd[-6:]
        and cmd[-2] == "B3"
        and mon["process_identity"] == launch["process_identity"]
        and sha(directory / "full-resource.json")
        == mon["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"],
        "manifest and switch",
    )
    standard = {k: v for k, v in env.items() if k not in bits}
    PF["check_native_manifest"](
        dict(mon, explicit_env=standard), cfg, cfg["pinned"], standard, measure
    )
    inv = P["G"]["probes"].load(
        S["QUAL"] / "nvme_r0_gate/qualified_profile/compact.py", "integrated_inventory"
    )
    return (
        mon,
        launch,
        inv.validate_inventory(directory, unit, {"native_explicit_env": env}, launch),
    )


def arm(a, directory, which, auth, build, spec, pins, ctrl, gold, refs):
    directory.mkdir()
    unit = a.unit + "-" + which.lower()
    exe, model, ids = map(Path, spec["runs"][0]["command"][:3])
    backend = Path(spec["backend_root"]).resolve(strict=True)
    need(
        sha(ids) == pins["ids_sha256"]
        and prepare.git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [pins["backend_commit"], pins["backend_tree"]]
        and not prepare.git(backend, "status", "--porcelain"),
        "target backend/IDs",
    )
    req = SimpleNamespace(
        window=a.window,
        placement=a.placement,
        envelope="E20_R0",
        measurement_commit=a.commit,
        unit=unit,
    )
    prepare.freeze(req, directory, pins, (exe, model, ids, backend, gold, ctrl["gomp"]))
    raw = directory / "raw"
    sealed = dict(
        pins,
        capture_sha256=build["elf_sha256"],
        numerical_dso_sha256=pins["numerical_dso_sha256"]
        | {"libllama.so.0.0.9884": build["image_sha256"]},
        startup_dso_sha256={
            Path(v["file"]).name: v["sha256"]
            for k, v in auth.verified["closure"].items()
            if k != SC["OLD"]["LOADER"].name
        },
    )
    cfg = read(directory / "protocol.json") | dict(
        schema="tesy-full-l25-attention-ablation-v1",
        pinned=sealed,
        runner_sha256=sha(P["MONITOR"]),
        native_variant=which,
        original_sha256=sha(directory / "protocol.json"),
        scientific_protocol_sha256=M["METHOD"],
    )
    config = directory / "full-resource.json"
    save(config, cfg)
    loader = dict(LD_LIBRARY_PATH=auth.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader"))
    base = PF["qualified_command"](
        read(directory / "argv.json")["monitor"], Path("/usr/lib64"), loader
    )
    cmd = OLD.derivative_command(
        base, exe.resolve(strict=True), auth.exe, refs["AR"], "B3", unit, config
    )
    idx = cmd.index("--", cmd.index("--env"))
    cmd[idx:idx] = [
        "--env",
        P["B"]["ON"] + "=1",
        "--env",
        M["OPTION"] + ("=1" if which == "ON" else "=0"),
    ]
    idx = cmd.index(str(N["REPO"] / "tools/run_bounded.py"))
    cmd[idx] = str(P["MONITOR"])
    save(directory / "full-argv.json", cmd)
    snapshot = datetime.fromisoformat(read(directory / "resource-policy.json")["snapshot"]["utc"])
    need(0 <= (datetime.now(UTC) - snapshot).total_seconds() < 3600, "C55 age")
    mon_proof = N["AU"]["Authority"].monitor_proof(auth.monitor)
    identity, n, mapped, wall = PF["guarded_run"](
        cmd, directory, unit, auth, measure, N["run_bounded"]
    )
    mon, launch, inventory = audit(directory, unit, cfg, cmd, which)
    age = (
        datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"]) - snapshot
    ).total_seconds()
    need(
        0 <= age < 3600
        and mon["process_identity"] == identity
        and wall <= 320
        and measure.file_bytes(raw) <= 128 << 20,
        "scope or output budget",
    )
    linkage = auth.audit(raw, identity["pid"])
    need({Path(p).name for p in mapped} <= linkage["initialized"].keys(), "provider coverage")
    report = G["contrast"](raw / (unit + ".capture"), which, refs, gold, pins)
    save(directory / "grade.json", report)
    return dict(
        status=report["status"],
        grade_sha256=sha(directory / "grade.json"),
        scope_s=wall,
        model_s=mon["elapsed_s"],
        maxima=mon["maxima"],
        c118=inventory,
        c55_age_s=age,
        samples_live=n,
        scope_cleanup=True,
        monitor_proof=mon_proof,
        loaded=linkage,
    )


def run(a, out, r):
    need(
        sha(a.build / "receipt.json") == BUILD
        and prepare.git(HERE, "rev-parse", "HEAD") == a.commit
        and not prepare.git(HERE, "status", "--porcelain")
        and re.fullmatch(r"tesy-full-attn-[a-z0-9-]+", a.unit),
        "campaign source",
    )
    build = read(a.build / "receipt.json")
    need(
        build["status"] == "GO_INTEGRATED_ATTENTION_PAIR"
        and build["protocol_sha256"] == sha(HERE / "protocol.md") == M["METHOD"]
        and build["client_source_sha256"] == sha(a.build / "boundary.cpp")
        and (a.build / "boundary.cpp").read_bytes() == M["observer"](),
        "observer and method",
    )
    auth = K["Authority"](a.static, a.build, build["elf_sha256"], build["image_sha256"])
    need(build["current_providers"] == auth.verified["closure"], "current ELF providers")
    refs = targets(a.parent, R["reopen"](a.parent, G["PARENT"]))
    ctrl = R["reopen"](a.reference, R["NUMERIC"])
    gold = a.reference / "raw" / (ctrl["unit"] + ".capture")
    src = SC["OLD"]["locks"](N["REPO"])
    pins = {
        k: v
        for k, v in src[SC["OLD"]["Q"] + "nvme_r0_gate/inputs/receipt.json"].items()
        if k not in ("model_forwards", "status")
    }
    win = read(a.window / "receipt.json")
    t0 = json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    need(
        prepare.tree_digest(gold) == pins["gold"]
        and sha(a.window / "receipt.json") == a.window_sha256
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and datetime.fromisoformat(t0).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "protocol.md"))
        and win["gpu_driver"] == auth.kernel["release"],
        "independent reference and prospective C55",
    )
    r.update(
        commit=a.commit,
        tree=prepare.git(HERE, "rev-parse", "HEAD^{tree}"),
        unit=a.unit,
        build_sha256=BUILD,
        protocol_sha256=M["METHOD"],
        runner_sha256=sha(Path(__file__)),
        grade_source_sha256=sha(HERE / "grade.py"),
        parent_sha256=G["PARENT"],
        window_sha256=a.window_sha256,
        model_sha256=pins["model_sha256"],
        driver=auth.kernel,
        arms={},
    )
    for which in ("OFF", "ON"):
        r["stage"] = which
        r["arms"][which] = arm(
            a, out / which, which, auth, build, src[SC["OLD"]["C270"]], pins, ctrl, gold, refs
        )
    r["status"] = r["arms"]["ON"]["status"]


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for k in ("static", "build", "reference", "parent", "window", "placement", "new-output-dir"):
        cli.add_argument("--" + k, type=Path, required=True)
    for k in ("unit", "window-sha256", "commit"):
        cli.add_argument("--" + k, required=True)
    a = cli.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", generation_requests=0)

    def expire(*_):
        raise TimeoutError("family wall cap")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(900)
    try:
        with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(a, out, r)
    except Exception as e:
        r["error"] = f"{type(e).__name__}: {e}"
    finally:
        signal.alarm(0)
    r["model_starts"] = len(list(out.glob("*/raw/*.launch.json")))
    r["raw_sha256"] = {
        str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()
    }
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
