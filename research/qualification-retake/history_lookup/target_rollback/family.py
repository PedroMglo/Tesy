"""Run four fresh native processes with one calibrated DSO and a common restored prefix."""

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
B, need, read, sha = (G[k] for k in ("B", "need", "read", "sha"))
T, K, P, R, F, save = (B[k] for k in ("T", "K", "P", "R", "F", "save"))
N, SC, PF, OLD, prepare, measure = (T[k] for k in ("N", "SC", "PF", "OLD", "prepare", "measure"))
BUILD = "8c662cb41b24b675ef28acfd5b1f0938897b09b185ea7949811d62cee636a053"
SWA_BUILD = "68d0e701b7698a07d7a70f810303e8a47613f24dafac611ab34e02c6f2279669"
LIVE_BUILD = "e62c3d6470ddd7cb53e971d56b08028a175ee46ced547540b83e2f24af0255a4"
COLD_IMPORT = "d3d6cdd5a26ffcc26be4097bf7db627a658f3b1fbac126e914345af0ebbd2ed6"
SWA = run_path(str(HERE / "swa.py"))


def capture(root, unit, mode):
    return root / mode / "raw" / (unit + "-" + mode.lower() + ".capture")


def sources(a):
    prior = R["reopen"](a.target, B["PARENT"])
    reference = R["reopen"](a.serial, K["D"]["SERIAL"])
    ctrl = R["reopen"](a.reference, R["NUMERIC"])
    serial = F["targets"](a.serial, reference)["AR"]
    target = capture(a.target, prior["unit"], "CUDA")
    gold = a.reference / "raw" / (ctrl["unit"] + ".capture")
    cfg = SC["OLD"]["locks"](N["REPO"])
    pins = {
        k: v
        for k, v in cfg[SC["OLD"]["Q"] + "nvme_r0_gate/inputs/receipt.json"].items()
        if k not in ("model_forwards", "status")
    }
    need(
        prior["status"] == "GO_NUMERIC_AT_CAPTURED_CUTS"
        and prepare.tree_digest(gold) == pins["gold"]
        and all(
            sha(serial / name) == sha(target / name)
            for name in ("initial-kv.bin", "post3-kv.bin", "prefill_final.logits.f32")
        ),
        "independent AR, CUDA and C127",
    )
    return serial, target, ctrl, gold, pins, cfg[SC["OLD"]["C270"]]


def audit(root, unit, mode, cfg, cmd):
    m, launch = (read(root / "raw" / (unit + s)) for s in (".json", ".launch.json"))
    i = cmd.index("--env")
    vars = {}
    for j in range(i, cmd.index("--", i), 2):
        key, value = cmd[j + 1].split("=", 1)
        need(cmd[j] == "--env" and key not in vars, "explicit environment")
        vars[key] = value
    run_unit = unit.rsplit("-", 1)[0]
    label = "C269-live189-" if cfg["schema"] == "tesy-live-prefix-v1" else "C269-rollback189-"
    original_root = Path(cmd[-1]).parents[2]
    extra = T["flags"]("CUDA") | {"TESY_ROLLBACK_AR": str(capture(original_root, run_unit, "AR"))}
    need(
        vars == m["explicit_env"]
        and all(vars.get(k) == m["relevant_environment"].get(k) == v for k, v in extra.items())
        and m["command"] == cmd[-6:]
        and cmd[-2] == mode
        and cfg["native_variant"] == mode
        and m["variant"] == label + mode
        and m["process_identity"] == launch["process_identity"]
        and sha(root / "rollback-resource.json")
        == m["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"],
        "runtime and arm",
    )
    standard = {k: v for k, v in vars.items() if k not in extra}
    PF["check_native_manifest"](
        dict(m, explicit_env=standard), cfg, cfg["pinned"], standard, measure
    )
    inv = P["G"]["probes"].load(
        T["S"]["QUAL"] / "nvme_r0_gate/qualified_profile/compact.py", "rollback_inventory"
    )
    return m, launch, inv.validate_inventory(root, unit, {"native_explicit_env": vars}, launch)


def arm(a, out, mode, b, auth, serial, target, ctrl, gold, pins, spec):
    root = out / mode
    root.mkdir()
    unit = a.unit + "-" + mode.lower()
    exe, model, ids = map(Path, spec["runs"][0]["command"][:3])
    backend = Path(spec["backend_root"]).resolve(strict=True)
    need(
        sha(ids) == pins["ids_sha256"]
        and prepare.git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [pins["backend_commit"], pins["backend_tree"]]
        and not prepare.git(backend, "status", "--porcelain"),
        "backend and token file",
    )
    req = SimpleNamespace(
        window=a.window,
        placement=a.placement,
        envelope="E20_R0",
        measurement_commit=a.commit,
        unit=unit,
    )
    prepare.freeze(req, root, pins, (exe, model, ids, backend, gold, ctrl["gomp"]))
    raw = root / "raw"
    sealed = pins | dict(
        capture_sha256=b["elf_sha256"],
        numerical_dso_sha256=pins["numerical_dso_sha256"]
        | {"libllama.so.0.0.9884": b["image_sha256"]},
        startup_dso_sha256={
            Path(v["file"]).name: v["sha256"]
            for k, v in auth.verified["closure"].items()
            if k != SC["OLD"]["LOADER"].name
        },
    )
    cfg = read(root / "protocol.json") | dict(
        schema="tesy-live-prefix-v1" if a.live_prefix else "tesy-rollback-restored-v1",
        pinned=sealed,
        native_variant=mode,
        runner_sha256=sha(P["MONITOR"]),
        original_sha256=sha(root / "protocol.json"),
        scientific_protocol_sha256=b["protocol_sha256"],
    )
    config = root / "rollback-resource.json"
    save(config, cfg)
    loader = dict(LD_LIBRARY_PATH=auth.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader"))
    base = PF["qualified_command"](read(root / "argv.json")["monitor"], Path("/usr/lib64"), loader)
    cmd = OLD.derivative_command(
        base, exe.resolve(strict=True), auth.exe, target, "B3", unit, config
    )
    cmd[-2] = mode
    label = "C269-live189-" if a.live_prefix else "C269-rollback189-"
    cmd[cmd.index("--variant") + 1] = label + mode
    ar = capture(out, a.unit, "AR")
    extra = T["flags"]("CUDA") | {"TESY_ROLLBACK_AR": str(ar)}
    j = cmd.index("--", cmd.index("--env"))
    cmd[j:j] = [word for key, value in extra.items() for word in ("--env", key + "=" + value)]
    cmd[cmd.index(str(N["REPO"] / "tools/run_bounded.py"))] = str(P["MONITOR"])
    save(root / "rollback-argv.json", cmd)
    t0 = datetime.fromisoformat(read(root / "resource-policy.json")["snapshot"]["utc"])
    need(0 <= (datetime.now(UTC) - t0).total_seconds() < 3600, "fresh C55")
    proof = N["AU"]["Authority"].monitor_proof(auth.monitor)
    identity, n, mapped, wall = PF["guarded_run"](cmd, root, unit, auth, measure, N["run_bounded"])
    m, launch, inv = audit(root, unit, mode, cfg, cmd)
    age = (
        datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"]) - t0
    ).total_seconds()
    need(
        0 <= age < 3600
        and m["process_identity"] == identity
        and wall <= 320
        and measure.file_bytes(raw) <= 128 << 20,
        "scope",
    )
    linkage = auth.audit(raw, identity["pid"])
    need({Path(path).name for path in mapped} <= linkage["initialized"].keys(), "observed runtime")
    cap = capture(out, a.unit, mode)
    if a.live_prefix:
        grade = run_path(str(HERE / "live_prefix/grade.py"))["grade"]
        g = grade(cap, mode, target, ar, a.cold_import)
    else:
        g = G["compare"](cap, mode, target, serial, ar)
    if a.swa_restore:
        g["kv_ranges"] = SWA["snapshots"](capture(out, a.unit, mode), mode)
    save(root / "grade.json", g)
    return dict(
        status=g["status"],
        grade_sha256=sha(root / "grade.json"),
        model_s=m["elapsed_s"],
        scope_s=wall,
        c55_age_s=age,
        c118=inv,
        maxima=m["maxima"],
        samples_live=n,
        scope_cleanup=True,
        monitor_proof=proof,
        loaded=linkage,
    )


def run(a, out, r):
    protocol, method = B["contract"](a.swa_restore, a.live_prefix)
    build = LIVE_BUILD if a.live_prefix else SWA_BUILD if a.swa_restore else BUILD
    need(
        sha(a.build / "receipt.json") == build
        and re.fullmatch(r"tesy-rollback-[a-z0-9-]+", a.unit)
        and prepare.git(HERE, "rev-parse", "HEAD") == a.commit
        and not prepare.git(HERE, "status", "--porcelain"),
        "campaign source",
    )
    b = read(a.build / "receipt.json")
    need(
        b["status"] == ("GO_LIVE_AR_CONTROL" if a.live_prefix else "GO_ROLLBACK_AR_CONTROL")
        and b["protocol_sha256"] == method == sha(HERE / protocol)
        and all(sha(Path(k)) == v for k, v in b["headers_sha256"].items())
        and sha(a.build / "rollback.cpp") == b["source_sha256"]
        and (a.build / "rollback.cpp").read_text() == B["source"](a.swa_restore, a.live_prefix),
        "exact client/header closure",
    )
    auth = K["OLD"]["Authority"](a.static, a.build, b["elf_sha256"], b["image_sha256"])
    win = read(a.window / "receipt.json")
    initial = json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    need(
        b["current_providers"] == auth.verified["closure"]
        and sha(a.window / "receipt.json") == a.window_sha256
        and win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and datetime.fromisoformat(initial).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", protocol))
        and win["gpu_driver"] == auth.kernel["release"],
        "runtime and C55",
    )
    src = sources(a)
    if a.live_prefix:
        cold = R["reopen"](a.cold_import, COLD_IMPORT)
        need(cold["status"] == "FAIL_PRESERVED" and cold["model_starts"] == 1, "cold contrast")
        r["cold_import_sha256"] = COLD_IMPORT
    if a.swa_restore:
        target = src[1]
        r["input_KV"] = SWA["contents"](target / "initial-kv.bin", 189, SWA["banks"](target))
    r.update(
        commit=a.commit,
        tree=prepare.git(HERE, "rev-parse", "HEAD^{tree}"),
        unit=a.unit,
        build_sha256=build,
        protocol_sha256=method,
        runner_sha256=sha(Path(__file__)),
        grader_sha256=sha(HERE / ("live_prefix/grade.py" if a.live_prefix else "grade.py")),
        target_sha256=B["PARENT"],
        serial_sha256=K["D"]["SERIAL"],
        window_sha256=a.window_sha256,
        model_sha256=src[4]["model_sha256"],
        driver=auth.kernel,
        arms={},
    )
    for mode in ("AR", "B3", "RESTORE") if a.live_prefix else G["CASES"]:
        r["stage"] = mode
        r["arms"][mode] = arm(a, out, mode, b, auth, *src)
        outcome = r["arms"][mode]["status"]
        if outcome.startswith("NO_GO_"):
            r["status"] = outcome
            return
    r["status"] = (
        "GO_LIVE_AND_WARM_CALIBRATION" if a.live_prefix else "GO_GREEDY_ROLLBACK_AND_CONTINUATION"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "target",
        "serial",
        "reference",
        "static",
        "build",
        "window",
        "placement",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("unit", "window-sha256", "commit"):
        p.add_argument("--" + k, required=True)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--swa-restore", action="store_true")
    modes.add_argument("--live-prefix", action="store_true")
    p.add_argument("--cold-import", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", generation_requests=0)

    def expire(*_):
        raise TimeoutError("family time cap")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(1080 if a.live_prefix else 1500)
    try:
        with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
