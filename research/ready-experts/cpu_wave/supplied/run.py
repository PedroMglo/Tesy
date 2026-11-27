"""Run the C280/C293 direct clients with authenticated R0, GGUF, pack and CPU-wave arms."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
T = run_path(HERE.parent / "target.py")
need, sha, read, save, ROOT, Q = (T[k] for k in ("need", "sha", "read", "save", "ROOT", "Q"))
prepare, measure, PF, PK, live = (T[k] for k in ("prepare", "measure", "PF", "PK", "live"))
sys.path.insert(0, str(ROOT / "tools"))
import expert_store_cost_gate as cost  # noqa: E402

power = run_path(Q / "packed_nvme_manifest/server_profile/system_driver/review.py")["power"]
ORDER = "RGPWWPGR"
CASES = ("code153", "nominal153")
C280 = ROOT / "results/c280-r2-three-way-causal-cost-20261005"
C293 = ROOT / "results/c293-integrated-expert-store-native-cost-20261006"
TARGET = "c49883b5abe3085bfd5fcb899c88209da4f133f742a1a7835d7f692f0c2a3035"
HTTP = "4dc6c212c03fdc9f6fd7745bb16182ef2264181028db9187eb5a9db93e22dc78"
BASE = "390e43e4d8f1b0f55041b6f82b383d328b610615a3485c64e7692de588970487"
PACK = "dec273d164b87a033b55f73c89681a1341fbb35f0ac93c7dca8b60adbc920f56"
ORIGINAL = "1318e94fa5a6e897d84bfeff2b8b8874e120e8979181b67bde425669577aa187"
STATE = {
    "nominal153": (
        "285c14dbfb5dac28fe3c686e456987022f8b27adaca94203b3c86f449e952dcc",
        "3710c645512c1463e8de21835d780833cdea167c4b5f34bfcb79c06b38551523",
    ),
    "code153": (
        "450cd4b931eb713476ccd160d55f16c79dedc5f40e6c08abb2b3a596c88f9e6e",
        "bcf958bd5a20035d5223966936c06f41449c6a1e21c31443a283997d8b2b070a",
    ),
}


def state_hash(state):
    keys = ("layers", "pending_queue", "n_calls", "n_miss", "n_preload", "n_waves")
    data = json.dumps({k: state[k] for k in keys}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def source(case):
    for p, digest in (
        (C280 / "protocol.json", BASE),
        (C293 / "protocol.json", PACK),
        (C280 / "compact.json", ORIGINAL),
    ):
        need(sha(p) == digest, "historical authority " + p.name)
    original, store = (read(p / "protocol.json") for p in (C280, C293))
    r0 = [
        a for a in read(C280 / "compact.json")["arms"] if a["profile"] == "R0" and a["case"] == case
    ]
    expected = store["expected_full_logits_sha256"][case]
    need(
        len(r0) == 2
        and all(
            a["measurement_valid"]
            and a["full_logits_sha256"] == expected
            and a["logical_load_generations"] == r0[0]["logical_load_generations"]
            for a in r0
        ),
        "two independent original references",
    )
    info = {}
    for role, version in (("R", original), ("G", store)):
        supplied = next(
            row for row in version["runs"] if row["command"][3] == case and row["profile"] == "R0"
        )
        binary, model, ids = map(Path, supplied["command"][:3])
        backend = Path(version["backend_root"]).resolve(strict=True)
        need(
            sha(ids) == version["file_sha256"][str(ids)]
            and sha(binary) == version["file_sha256"][str(binary)]
            and prepare.git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
            == [version["backend_commit"], version["backend_tree"]]
            and not prepare.git(backend, "status", "--porcelain"),
            "frozen ELF, fixture and backend",
        )
        info[role] = dict(
            exe=binary.resolve(strict=True),
            digest=sha(binary),
            backend=backend,
            model=model,
            fixture=ids,
            backend_commit=version["backend_commit"],
            backend_tree=version["backend_tree"],
        )
    need(
        info["R"]["fixture"] == info["G"]["fixture"] and info["R"]["model"] == info["G"]["model"],
        "common fixture and model",
    )
    return info, expected, r0[0]["logical_load_generations"]


def grade(cap, fixture, case, role, logits, generations, manifest):
    row, digest = cost.inspect(cap, read(fixture)[case], "R0", case)
    need(
        read(cap / "initial.json") == row["initial"]
        and {p.name for p in cap.iterdir()} == {"initial.json", "result.json", "all33.logits.f32"}
        and digest == logits,
        "native payloads and independent full rows",
    )
    states = [state_hash(row[k]) for k in ("initial", "final")]
    need(
        tuple(states) == STATE[case] and cost.loads(row) == generations,
        "original pool state or loads",
    )
    enabled = role in "PW"
    if role != "R":
        cost.transport(row, "EXPERT_CONTIGUOUS" if enabled else "ORIGINAL")
        need(row["store_manifest_env"] == (str(manifest) if enabled else None), "pack manifest")
    else:
        need("transport" not in row and "store_loads_complete" not in row, "C269 native schema")
    return dict(
        full_logits_sha256=digest,
        states=states,
        logical_loads=generations,
        metrics={k: row[k] for k in cost.METRICS},
        store_loads=row.get("store_loads_complete"),
        store_weight_bytes=row.get("store_logical_weight_bytes"),
    )


def setup(a, cfg, out, role, build):
    mode = "ORIGINAL" if role == "R" else "PRICE"
    ctl = T["Provider"](
        a,
        out,
        mode,
        cfg["exe"],
        cfg["digest"],
        build["arms"]["PRICE"],
        selection="C270_R0" if role == "R" else "C270_PACK",
        kind="PRICE",
    )
    ctl.mode = "ON" if role in "PW" else "OFF"
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": ctl.search}
    test = subprocess.run(
        [cfg["exe"], "--self-test"], env=env, capture_output=True, text=True, timeout=20, check=True
    )
    need(test.stdout.strip() == "PASS_MODEL_FREE_R2_CAUSAL_MODE_CALLS_ROWS", "native self-test")
    return ctl


def arm(a, out, name, cfg, expected_logits, generations, build):
    role, unit = name[-1], a.unit + "-" + name.lower()
    ctl = setup(a, cfg, out, role, build)
    model, fixture, exe = (cfg[k] for k in ("model", "fixture", "exe"))
    need(model.resolve(strict=True) == ctl.data_paths["model"], "NVMe placement")
    seed = read(Q / "nvme_r0_gate/inputs/receipt.json")
    pins = {k: v for k, v in seed.items() if k not in ("status", "model_forwards")}
    base = read(prepare.BASE)
    old, old_model, old_ids = map(Path, base["runs"][0]["command"][:3])
    aux = read(a.target / "PRICE/wave-resource.json")
    need(old_model.samefile(model) and sha(old_ids) == pins["ids_sha256"], "template inputs")
    request = SimpleNamespace(
        window=a.window,
        placement=a.archive / "part-01/placement/r1/receipt.json",
        envelope="E20_R0",
        measurement_commit=a.commit,
        unit=unit,
    )
    prepare.freeze(
        request,
        out,
        pins,
        (
            old,
            model,
            old_ids,
            Path(base["backend_root"]),
            Path(base["runs"][0]["post_run_command"][-1]),
            aux["parallel_runtime"]["libraries_sha256"],
        ),
    )
    raw = out / "raw"
    cap = raw / (unit + ".native")
    monitor = T["H"]["RB"]["P"]["MONITOR"]
    dsos = {Path(v["file"]).name: v["sha256"] for v in ctl.verified["closure"].values()}
    numerical = {k: dsos[k] for k in pins["numerical_dso_sha256"]}
    selected = dict(
        pins,
        capture_sha256=cfg["digest"],
        ids_sha256=sha(fixture),
        numerical_dso_sha256=numerical,
        backend_commit=cfg["backend_commit"],
        backend_tree=cfg["backend_tree"],
        startup_dso_sha256=dsos,
        gold_full_logits_sha256={a.case: expected_logits},
    )
    protocol = read(out / "protocol.json") | dict(
        schema="tesy-supplied-wave-v1",
        pinned=selected,
        runner_sha256=sha(monitor),
        role=role,
        case=a.case,
        scientific_protocol_sha256=sha(HERE / "protocol.md"),
        expected_pool_hashes=STATE[a.case],
        placement_sha256=sha(request.placement),
        metadata=aux["metadata"],
    )
    cfgpath = out / "resource-supplied.json"
    save(cfgpath, protocol)
    loader = dict(LD_LIBRARY_PATH=ctl.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader"))
    extra = {}
    if role != "R":
        extra["TESY_NATIVE_CPU_WAVE"] = str(int(role == "W"))
    if role in "PW":
        extra[live.STORE_ENV] = str(ctl.data_paths["manifest"])
    cmd = PF["qualified_command"](read(out / "argv.json")["monitor"], Path("/usr/lib64"), loader)
    cmd[cmd.index(str(ROOT / "tools/run_bounded.py"))] = str(monitor)
    cmd[cmd.index("LimitFSIZE=8388608")] = "LimitFSIZE=41943040"
    for k, v in (
        ("--backend-root", cfg["backend"]),
        ("--workload", fixture),
        ("--variant", "supplied-R0-" + role),
        ("--resource-protocol", cfgpath),
    ):
        cmd[cmd.index(k) + 1] = str(v)
    sep = cmd.index("--", cmd.index("--env"))
    argv = list(map(str, (exe, model, fixture, a.case, cap, "R0", "v1")))
    cmd[sep:] = [word for k, v in extra.items() for word in ("--env", k + "=" + v)] + ["--", *argv]
    common = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | loader
    expected = common | extra
    save(out / "argv-supplied.json", dict(command=cmd, expected=expected))
    policy = read(out / "resource-policy.json")
    PK["PK"]["age"](policy, datetime.now(UTC))
    monitor_proof = T["AU"]["Authority"].monitor_proof(ctl.monitor)
    ident, samples, mapped, wall = PF["guarded_run"](
        cmd, out, unit, ctl, measure, T["N"]["run_bounded"]
    )
    mon, launch = (read(raw / (unit + suffix)) for suffix in (".json", ".launch.json"))
    need(
        mon["command"] == argv
        and mon["explicit_env"] == expected
        and all(mon["relevant_environment"].get(k) == v for k, v in extra.items())
        and (live.STORE_ENV in mon["relevant_environment"]) == (role in "PW")
        and mon["relevant_environment"].get("TESY_NATIVE_CPU_WAVE")
        == extra.get("TESY_NATIVE_CPU_WAVE")
        and mon["process_identity"] == launch["process_identity"] == ident
        and mon["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(cfgpath),
        "live child identity and environment",
    )
    PF["check_native_manifest"](dict(mon, explicit_env=common), protocol, selected, common, measure)
    inv = PK["PK"]["compact"].validate_inventory(
        out, unit, {"native_explicit_env": expected}, launch
    )
    age = PK["PK"]["age"](
        policy, datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
    )
    audit = ctl.audit(raw, ident["pid"])
    need({Path(p).name for p in mapped} <= audit["initialized"].keys(), "live closure")
    fd = live.CaptureAuthority.fd_evidence(ctl)
    proof = grade(
        cap, fixture, a.case, role, expected_logits, generations, ctl.data_paths["manifest"]
    )
    result = dict(
        name=name,
        role=role,
        case=a.case,
        unit=unit,
        **proof,
        scope_s=wall,
        model_s=mon["elapsed_s"],
        maxima=mon["maxima"],
        energy=power(out, {"unit": unit}),
        live_samples=samples,
        c118=inv,
        c55_age_s=age,
        pack_fd_samples=fd["positive_samples"],
        binary_sha256=cfg["digest"],
        cpu_sha256=ctl.verified["closure"][T["CPU"]]["sha256"],
        backend_commit=cfg["backend_commit"],
        argv_sha256=sha(out / "argv-supplied.json"),
        native_sha256=sha(cap / "result.json"),
        monitor_sha256=sha(raw / (unit + ".json")),
    )
    save(out / "authority.json", dict(loader=audit, monitor=monitor_proof, fd=fd))
    save(out / "checked.json", result)
    return result


def main(a, out, receipt):
    need(
        re.fullmatch(r"tesy-wave-supplied-[a-z0-9-]+", a.unit)
        and prepare.git(ROOT, "rev-parse", "HEAD") == a.commit
        and not prepare.git(ROOT, "status", "--porcelain"),
        "clean measurement source and unit",
    )
    need(
        sha(a.target / "receipt.json") == TARGET
        and sha(a.target / "PRICE/wave-resource.json")
        == "a6b428cbee4a9660466346b7659cac9ad943a3c8c8f136dddb3574dc2bca80a8"
        and sha(a.http / "receipt.json") == HTTP
        and sha(a.build_dir / "receipt.json") == T["BUILD"],
        "admitted target, client and build",
    )
    info, logits, loads = source(a.case)
    build = read(a.build_dir / "receipt.json")
    win = read(a.window / "receipt.json")
    first = json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    need(
        sha(a.window / "receipt.json") == a.window_sha256
        and win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not win["reason"]
        and win["window_sha256"] == sha(a.window / "samples.jsonl")
        and datetime.fromisoformat(first).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "C55 or protocol date",
    )
    receipt.update(
        case=a.case,
        unit=a.unit,
        commit=a.commit,
        tree=prepare.git(ROOT, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=sha(HERE / "protocol.md"),
        runner_sha256=sha(__file__),
        window_sha256=a.window_sha256,
        input_sha256=sha(info["R"]["fixture"]),
        source_protocols=[BASE, PACK],
        target_sha256=TARGET,
        client_sha256=HTTP,
        arms=[],
    )
    save(out / "provenance.json", dict(receipt, order=list(ORDER)))
    start = time.monotonic()
    for i, role in enumerate(ORDER, 1):
        name = str(i) + role
        receipt["stage"] = name
        folder = out / name
        folder.mkdir()
        row = arm(a, folder, name, info["R" if role == "R" else "G"], logits, loads, build)
        receipt["arms"].append(row)
        print(name, "PASS_FULL33", flush=True)
        need(
            time.monotonic() - start <= 46 * 60 and measure.file_bytes(out) <= 1 << 30,
            "case budget",
        )
    receipt["status"] = "COMPLETE_SUPPLIED_CASE"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("archive", "derived", "target", "http", "build-dir", "window", "new-output-dir"):
        p.add_argument("--" + key, type=lambda s: Path(s).resolve(), required=True)
    for key in ("commit", "unit", "window-sha256"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--case", choices=CASES, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    receipt = {"status": "FAIL_PRESERVED"}
    start = time.monotonic()
    try:
        with (out.parent / "tesy-wave-supplied.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            main(a, out, receipt)
    except Exception as exc:
        receipt.update(reason=str(exc), error_type=type(exc).__name__)
    receipt["elapsed_s"] = time.monotonic() - start
    save(out / "receipt.json", receipt)
    print(receipt["status"], receipt.get("reason", ""), flush=True)
    raise SystemExit(int(receipt["status"] != "COMPLETE_SUPPLIED_CASE"))
