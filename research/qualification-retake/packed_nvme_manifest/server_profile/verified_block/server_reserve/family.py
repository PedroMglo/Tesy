"""Run the same live target trajectory with the packed product and candidate output reserves."""

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
C = run_path(str(HERE / "client.py"))
GRAPH, RB, need, sha = (C[k] for k in ("GRAPH", "RB", "need", "sha"))
N, PF, SC, prepare, measure = (RB[k] for k in ("N", "PF", "SC", "prepare", "measure"))
PK = run_path(str(HERE.parents[1] / "system_driver/pack_numeric.py"))
read, save = prepare.load, prepare.save
CLIENT = "4922035132fd7efa01ee30ec5ac5577136228d847d075dd072791d0c7088e8e7"
CASES = {
    "HIST1": ("HIST", 1, "AR"),
    "RECOMP1": ("RECOMPILE", 1, "AR"),
    "OFF1": ("BLOCK", 1, "AR"),
    "ON3": ("BLOCK", 3, "AR"),
    "B0": ("BLOCK", 3, "R0"),
    "B1": ("BLOCK", 3, "R1"),
    "B2": ("BLOCK", 3, "R2"),
}


def capture(root, unit, case):
    return root / case / "raw" / (unit + "-" + case.lower() + ".capture")


class Authority(PK["Pack"]):
    def __init__(self, a, root, data, library):
        super().__init__(a, "ON", root)
        new = a.client / "b3-numeric"
        need(sha(new) == data["elf_sha256"], "client ELF")
        del self.stats[str(self.exe)]
        self.exe = new
        self.arm = {"executable_sha256": data["elf_sha256"]}
        self.stats[str(new)] = N["AU"]["identity"](new)
        name = "libllama.so.0"
        old = self.verified["closure"][name]["file"]
        rec = data["arms"][library]
        dso = Path(rec["image"])
        need(
            sha(dso) == rec["image_sha256"] and (dso.parent / name).resolve(strict=True) == dso,
            "selected DSO",
        )
        for table in (self.stats, self.files, self.keys):
            del table[old]
        self.files[str(dso)] = rec["image_sha256"]
        self.stats[str(dso)] = N["AU"]["identity"](dso)
        self.keys[str(dso)] = N["AU"]["reference_key"](str(dso), self.stats[str(dso)])
        self.allowed = set(self.files)
        self.initial = (self.initial - {old}) | {str(dso)}
        self.verified = self.verified | dict(
            closure=self.verified["closure"]
            | {name: dict(file=str(dso), sha256=rec["image_sha256"])}
        )
        self.search = os.pathsep.join((str(dso.parent), self.native_search))
        self.recheck()


def serial_files():
    return [
        "prefill.f32",
        "entry.kv",
        "entry.pool",
        "final.pool",
        *(f"step-{j}.f32" for j in range(5)),
        *(f"keep-{j}.{suffix}" for j in range(1, 6) for suffix in ("kv", "pool")),
    ]


def grade(cap, case, reference, gold, serial, control):
    _, reserve, mode = CASES[case]
    p = read(cap / "native.json")
    need(p["output_reserve"] == reserve, "reserve")
    counters = {k: p[k] for k in ("store_entry", "store_end")}
    for row in counters.values():
        need(
            row["loads"] > 0 and row["logical_weight_bytes"] == 13219200 * row["loads"],
            "completed store weights",
        )
    need(
        counters["store_end"]["loads"] >= counters["store_entry"]["loads"], "monotone pack counters"
    )
    ar = cap if mode == "AR" else control
    result = RB["G"]["compare"](cap, mode, gold, serial, ar, live=True)
    if mode == "AR":
        matched = {k: sha(cap / k) for k in serial_files()}
        need(
            all(v == sha(reference / k) for k, v in matched.items()),
            "serial target vs independent 173",
        )
    else:
        matched = {}
        RB["G"]["compare"](cap, mode, gold, serial, reference, live=True)
    return dict(
        grade=result,
        serial_matches=matched,
        store=counters,
        kv_coverage=RB["live_coverage"](cap, mode),
    )


def arm(a, out, case, data, src, history):
    serial, target, ctrl, gold, pins, spec = src
    library, reserve, mode = CASES[case]
    root = out / case
    root.mkdir()
    unit = a.unit + "-" + case.lower()
    ctl = Authority(a, root, data, library)
    exe, model, ids = map(Path, spec["runs"][0]["command"][:3])
    backend = Path(spec["backend_root"]).resolve(strict=True)
    need(
        model.resolve(strict=True) == ctl.data_paths["model"] and sha(ids) == pins["ids_sha256"],
        "target inputs",
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
    lib = data["arms"][library]["image_sha256"]
    sealed = pins | dict(
        capture_sha256=data["elf_sha256"],
        backend_commit=PK["live"].static.PIN,
        backend_tree=PK["live"].static.TREE,
        numerical_dso_sha256=pins["numerical_dso_sha256"] | {GRAPH["IMAGE"]: lib},
        startup_dso_sha256={
            Path(v["file"]).name: v["sha256"]
            for k, v in ctl.verified["closure"].items()
            if k != SC["OLD"]["LOADER"].name
        },
    )
    cfg = read(root / "protocol.json") | dict(
        schema="tesy-packed-server-reserve-v1",
        pinned=sealed,
        case=case,
        mode=mode,
        output_reserve=reserve,
        metadata=ctl.initial_manifest,
        runner_sha256=sha(RB["P"]["MONITOR"]),
        scientific_protocol_sha256=C["METHOD"],
    )
    config = root / "packed-resource.json"
    save(config, cfg)
    loader = dict(LD_LIBRARY_PATH=ctl.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader"))
    base = PF["qualified_command"](read(root / "argv.json")["monitor"], Path("/usr/lib64"), loader)
    cmd = RB["OLD"].derivative_command(
        base, exe.resolve(strict=True), ctl.exe, target, "B3", unit, config
    )
    cmd[-2] = mode
    label = "C291-packed-reserve-" + case
    cmd[cmd.index("--variant") + 1] = label
    j = cmd.index("--backend-root") + 1
    need(Path(cmd[j]).resolve(strict=True) == backend, "upstream command")
    cmd[j] = str(ctl.backend)
    cmd[cmd.index(str(N["REPO"] / "tools/run_bounded.py"))] = str(RB["P"]["MONITOR"])
    current = capture(out, a.unit, case)
    ar = current if mode == "AR" else capture(out, a.unit, "ON3")
    extra = {
        PK["live"].STORE_ENV: str(ctl.data_paths["manifest"]),
        "TESY_TEST_OUTPUT_RESERVE": str(reserve),
        "TESY_ROLLBACK_AR": str(ar),
    }
    if reserve == 3:
        extra.update(RB["T"]["flags"]("CUDA"))
    j = cmd.index("--", cmd.index("--env"))
    cmd[j:j] = [s for k, v in extra.items() for s in ("--env", k + "=" + v)]
    expected = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | loader | extra
    save(root / "argv-packed.json", dict(command=cmd, expected=expected))
    policy = read(root / "resource-policy.json")
    PK["PK"]["age"](policy, datetime.now(UTC))
    monitor = N["AU"]["Authority"].monitor_proof(ctl.monitor)
    ident, samples, mapped, wall = PF["guarded_run"](
        cmd, root, unit, ctl, measure, N["run_bounded"]
    )
    m, launch = (read(raw / (unit + s)) for s in (".json", ".launch.json"))
    need(
        m["explicit_env"] == expected
        and all(m["relevant_environment"].get(k) == v for k, v in extra.items())
        and m["command"] == cmd[-6:]
        and m["variant"] == label
        and m["process_identity"] == launch["process_identity"] == ident
        and m["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(config)
        and wall <= 320
        and measure.file_bytes(raw) <= 128 << 20,
        "process, authority and cap",
    )
    standard = {k: v for k, v in expected.items() if k not in extra}
    PF["check_native_manifest"](dict(m, explicit_env=standard), cfg, sealed, standard, measure)
    inv = PK["PK"]["compact"].validate_inventory(
        root, unit, {"native_explicit_env": expected}, launch
    )
    age = PK["PK"]["age"](
        policy, datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"])
    )
    fds = PK["live"].CaptureAuthority.fd_evidence(ctl)
    linked = ctl.audit(raw, ident["pid"])
    need({Path(v).name for v in mapped} <= linked["initialized"].keys(), "runtime providers")
    actual = re.findall(
        r"llama_context: n_outputs_max\s*=\s*(\d+)", (raw / (unit + ".stderr")).read_text()
    )
    need(actual == [str(reserve)], "logged output reserve")
    g = grade(current, case, history, target, serial, ar)
    if mode != "AR":
        RB["G"]["compare"](current, mode, target, serial, capture(out, a.unit, "HIST1"), live=True)
    save(root / "grade.json", g)
    return dict(
        status=g["grade"]["status"],
        grade_sha256=sha(root / "grade.json"),
        image_sha256=lib,
        mode=mode,
        reserve=reserve,
        store=g["store"],
        fd=fds,
        loader=linked,
        monitor=monitor,
        inventory=inv,
        c55_age_s=age,
        scope_s=wall,
        scope_cleanup=True,
        model_s=m["elapsed_s"],
        maxima=m["maxima"],
        samples=samples,
    )


def run(a, out, r):
    root = GRAPH["tree"](N["REPO"])
    need(
        root[0] == a.commit
        and sha(HERE / "protocol.md") == C["METHOD"]
        and re.fullmatch("tesy-pack-reserve-[a-z0-9-]+", a.unit),
        "clean source and protocol",
    )
    data = GRAPH["read"](a.client / "receipt.json", CLIENT)
    need(
        data["status"] == "GO_PACKED_CONTROL_CLIENT"
        and data["combo_sha256"] == C["COMBO"]
        and sha(a.client / "reserve.cpp") == data["source_sha256"]
        and (a.client / "reserve.cpp").read_text() == C["source"]()
        and all(sha(Path(p)) == v for p, v in data["headers"].items()),
        "client",
    )
    prior = RB["R"]["reopen"](a.history, GRAPH["NUMERIC"])
    need(prior["status"] == "GO_GREEDY_ROLLBACK_AND_CONTINUATION", "trajectory")
    win = GRAPH["read"](a.window / "receipt.json", a.window_sha256)
    first = json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    need(
        win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and datetime.fromisoformat(first).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "fresh resource window",
    )
    src = RB["sources"](a)
    history = RB["capture"](a.history, prior["unit"], "AR")
    r.update(
        commit=a.commit,
        tree=root[1],
        unit=a.unit,
        protocol_sha256=C["METHOD"],
        client_sha256=CLIENT,
        history_sha256=GRAPH["NUMERIC"],
        window_sha256=a.window_sha256,
        combo_sha256=C["COMBO"],
        arms={},
    )
    for case in CASES:
        r["stage"] = case
        r["arms"][case] = arm(a, out, case, data, src, history)
    r["status"] = "GO_PACKED_SERVER_RESERVE_GREEDY"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "static",
        "client",
        "window",
        "placement",
        "history",
        "target",
        "serial",
        "reference",
        "derived",
        "constructor",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("commit", "unit", "window-sha256"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", generation_requests=0)

    def expire(*_):
        raise TimeoutError("family time cap")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(35 * 60)
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
    print(r["status"], r.get("stage", ""), r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
