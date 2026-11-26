"""Compare a neutral integrated graph, the minimal L25 repair and the eleven CUDA layers."""

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
K = run_path(str(HERE / "build.py"))
D, F, S, N, P, need, read, sha, save = (
    K[k] for k in ("D", "F", "S", "N", "P", "need", "read", "sha", "save")
)
PF, SC, OLD, prepare, measure, R, G = (
    F[k] for k in ("PF", "SC", "OLD", "prepare", "measure", "R", "G")
)
PREV = run_path(str(D["ATT"] / "full_graph/review.py"))
BUILD = "9b9625d808b09e017d99f69907db2cfb4f6a0603b3ba950c1fab32d5418aede6"
ARMS = ("BASE", "D25", "CUDA")


def flags(mode):
    need(mode in ARMS, "arm")
    return {P["B"]["ON"]: "1", F["M"]["OPTION"]: "1", K["FLAG"]: mode}


def construction(log, mode):
    text = log.read_text()
    assigned = {
        int(layer)
        for layer in re.findall(r"layer\s+(\d+) assigned to device CUDA0, is_swa = [01]", text)
    }
    expected = set(range(25, 36))
    need(assigned == expected | {36}, "eleven CUDA transformer layers and output head")
    entries = re.findall(r"^tesy_b3_built (down|attention) (\d+) (\d+)$", text, re.M)
    built = {
        kind: sorted({(int(layer), int(n)) for k, layer, n in entries if k == kind})
        for kind in ("down", "attention")
    }
    downs = set() if mode == "BASE" else {25} if mode == "D25" else expected
    attns = expected if mode == "CUDA" else {25}
    need(
        built["down"] == sorted((i, 3) for i in downs)
        and {layer for layer, _ in built["attention"]} == attns
        and (25, 256) in built["attention"]
        and all(n > 0 for _, n in built["attention"]),
        "registered graph paths",
    )
    return {k: [list(pair) for pair in v] for k, v in built.items()}


def grade(directory, unit, mode, refs, baseline, gold, pins):
    raw = directory / "raw"
    cap = raw / (unit + ".capture")
    sites = construction(raw / (unit + ".stderr"), mode)
    compared = G["contrast"](cap, "ON", refs, gold, pins)
    l25 = {f: row["changed_words"] for f, row in compared["vs_serial"]["layer25"].items()}
    ffn = [l25[f"{p}.ffn_moe_out-25.bin"] for p in G["POS"]]
    if mode == "BASE":
        need(
            prepare.tree_digest(cap) == prepare.tree_digest(baseline)
            and prepare.tree_digest(cap / "boundary") == prepare.tree_digest(baseline / "boundary")
            and ffn == [33, 29, 109],
            "all files of prior ON",
        )
        status = "PASS_NEUTRAL_BASE"
    else:
        need(not any(l25.values()), "all layer-25 words match serial")
        status = (
            "GO_NUMERIC_AT_CAPTURED_CUTS"
            if compared["all_covered_equal_to_serial"]
            else "RESTORED_FFN25_PARTIAL"
        )
    compared["status"] = status
    logical = PREV["locate_kv"](refs["AR"], cap, raw / (unit + ".stderr"))
    routes = PREV["ordered_routes"](refs["AR"], cap, compared["vs_serial"]["changed_routes"])
    need(
        compared["post3_kv_equals_serial"] == (logical["changed_words"] == 0),
        "serialized and logical KV",
    )
    return dict(
        status=status,
        paths=sites,
        counts25=ffn,
        logical_kv=logical,
        routing=routes,
        grade=PREV["summarize"](compared),
    )


def audit(directory, unit, cfg, cmd, mode):
    mon, launch = (read(directory / "raw" / (unit + s)) for s in (".json", ".launch.json"))
    j = cmd.index("--env")
    env = {}
    for i in range(j, cmd.index("--", j), 2):
        key, value = cmd[i + 1].split("=", 1)
        need(cmd[i] == "--env" and key not in env, "environment duplicate")
        env[key] = value
    extra = flags(mode)
    need(
        env == mon["explicit_env"]
        and all(env.get(k) == mon["relevant_environment"].get(k) == v for k, v in extra.items())
        and mon["command"] == cmd[-6:]
        and cmd[-2] == "B3"
        and mon["process_identity"] == launch["process_identity"]
        and cfg["native_variant"] == mode
        and cfg["scientific_protocol_sha256"] == K["METHOD"]
        and sha(directory / "full-resource.json")
        == mon["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"],
        "physical manifest and switches",
    )
    standard = {k: v for k, v in env.items() if k not in extra}
    PF["check_native_manifest"](
        dict(mon, explicit_env=standard), cfg, cfg["pinned"], standard, measure
    )
    inventory = P["G"]["probes"].load(
        S["QUAL"] / "nvme_r0_gate/qualified_profile/compact.py", "ffn_c118"
    )
    return (
        mon,
        launch,
        inventory.validate_inventory(directory, unit, {"native_explicit_env": env}, launch),
    )


def arm(a, directory, mode, auth, build, spec, pins, ctrl, gold, refs, baseline):
    directory.mkdir()
    unit = a.unit + "-" + mode.lower()
    exe, model, ids = map(Path, spec["runs"][0]["command"][:3])
    backend = Path(spec["backend_root"]).resolve(strict=True)
    need(
        sha(ids) == pins["ids_sha256"]
        and prepare.git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [pins["backend_commit"], pins["backend_tree"]]
        and not prepare.git(backend, "status", "--porcelain"),
        "native IDs and backend",
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
    sealed = pins | dict(
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
        schema="tesy-ffn-target-v1",
        pinned=sealed,
        runner_sha256=sha(P["MONITOR"]),
        native_variant=mode,
        original_sha256=sha(directory / "protocol.json"),
        scientific_protocol_sha256=K["METHOD"],
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
    j = cmd.index("--", cmd.index("--env"))
    cmd[j:j] = [word for k, v in flags(mode).items() for word in ("--env", k + "=" + v)]
    cmd[cmd.index(str(N["REPO"] / "tools/run_bounded.py"))] = str(P["MONITOR"])
    save(directory / "full-argv.json", cmd)
    t0 = datetime.fromisoformat(read(directory / "resource-policy.json")["snapshot"]["utc"])
    need(0 <= (datetime.now(UTC) - t0).total_seconds() < 3600, "fresh C55 before launch")
    proof = N["AU"]["Authority"].monitor_proof(auth.monitor)
    identity, n, mapped, wall = PF["guarded_run"](
        cmd, directory, unit, auth, measure, N["run_bounded"]
    )
    mon, launch, inv = audit(directory, unit, cfg, cmd, mode)
    age = (
        datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"]) - t0
    ).total_seconds()
    need(
        0 <= age < 3600
        and mon["process_identity"] == identity
        and wall <= 320
        and measure.file_bytes(raw) <= 128 << 20,
        "scope and resource bounds",
    )
    linkage = auth.audit(raw, identity["pid"])
    need({Path(path).name for path in mapped} <= linkage["initialized"].keys(), "provider coverage")
    report = grade(directory, unit, mode, refs, baseline, gold, pins)
    save(directory / "grade.json", report)
    return dict(
        status=report["status"],
        grade_sha256=sha(directory / "grade.json"),
        model_s=mon["elapsed_s"],
        scope_s=wall,
        c55_age_s=age,
        c118=inv,
        maxima=mon["maxima"],
        samples_live=n,
        scope_cleanup=True,
        monitor_proof=proof,
        loaded=linkage,
    )


def inputs(a):
    refs = F["targets"](a.serial, R["reopen"](a.serial, D["SERIAL"]))
    prev = R["reopen"](a.block, D["BLOCK"])
    ctrl = R["reopen"](a.reference, R["NUMERIC"])
    gold = a.reference / "raw" / (ctrl["unit"] + ".capture")
    cfg = SC["OLD"]["locks"](N["REPO"])
    pins = {
        k: v
        for k, v in cfg[SC["OLD"]["Q"] + "nvme_r0_gate/inputs/receipt.json"].items()
        if k not in ("model_forwards", "status")
    }
    need(
        prepare.tree_digest(gold) == pins["gold"] and prev["parent_sha256"] == D["SERIAL"],
        "C127/C270 and AR/B3 authorities",
    )
    return (
        refs,
        a.block / "ON/raw" / (prev["unit"] + "-on.capture"),
        ctrl,
        gold,
        pins,
        cfg[SC["OLD"]["C270"]],
    )


def run(a, out, r):
    need(
        sha(a.build / "receipt.json") == BUILD
        and re.fullmatch(r"tesy-target-ffn-[a-z0-9-]+", a.unit)
        and prepare.git(HERE, "rev-parse", "HEAD") == a.commit
        and not prepare.git(HERE, "status", "--porcelain"),
        "campaign authority",
    )
    b = read(a.build / "receipt.json")
    need(
        b["status"] == "GO_TARGET_FFN_FAMILY"
        and sha(HERE / "protocol.md") == b["protocol_sha256"] == K["METHOD"]
        and all(sha(HERE / k) == v for k, v in b["method_sources"].items())
        and sha(a.build / "llama-graph.cpp") == b["graph_source_sha256"],
        "impl identity",
    )
    auth = K["OLD"]["Authority"](a.static, a.build, b["elf_sha256"], b["image_sha256"])
    win = read(a.window / "receipt.json")
    t0 = json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    need(
        b["current_providers"] == auth.verified["closure"]
        and sha(a.window / "receipt.json") == a.window_sha256
        and win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and datetime.fromisoformat(t0).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "protocol.md"))
        and win["gpu_driver"] == auth.kernel["release"],
        "current runtime and C55",
    )
    refs, baseline, ctrl, gold, pins, spec = inputs(a)
    r.update(
        commit=a.commit,
        tree=prepare.git(HERE, "rev-parse", "HEAD^{tree}"),
        unit=a.unit,
        build_sha256=BUILD,
        protocol_sha256=K["METHOD"],
        runner_sha256=sha(Path(__file__)),
        serial_sha256=D["SERIAL"],
        block_sha256=D["BLOCK"],
        window_sha256=a.window_sha256,
        model_sha256=pins["model_sha256"],
        driver=auth.kernel,
        arms={},
    )
    for mode in ARMS:
        r["stage"] = mode
        r["arms"][mode] = arm(a, out / mode, mode, auth, b, spec, pins, ctrl, gold, refs, baseline)
    r["status"] = r["arms"]["CUDA"]["status"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "static",
        "build",
        "reference",
        "serial",
        "block",
        "window",
        "placement",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("unit", "window-sha256", "commit"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", generation_requests=0)

    def expire(*_):
        raise TimeoutError("20 minute family cap")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(1200)
    try:
        with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(a, out, r)
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
    r["model_starts"] = len(list(out.glob("*/raw/*.launch.json")))
    r["raw_sha256"] = {
        str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()
    }
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
