"""Six independent, resource-monitored 120B processes serving the same two turns."""

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(HERE.parent / "client.py")
T, H, PK, ROOT, sha, read, need = (C[k] for k in ("T", "H", "PK", "ROOT", "sha", "read", "need"))
W = run_path(HERE / "workload.py")
NATIVE = H["T"]["V"]
ORDER = "RPWWPR"
METHOD = "7eb6ac1aa4504c13f23cf2bcce7866f41321597ac6ea8d832be0d7b8d1998be8"
SUPPLIED = "833c35540fbbe69ba0976944471204aff715958c11884eab51f61550a20e0f42"
R0 = "01303f006ce46c25b06238a4f953f3c2405ab96fae93c370d500f28b39d06741"
LOADER = "278addbce2074535fcfbd1e33b82b4eb0f9dfda2d6ba4e0c4e40ca1f74f65419"

sys.path.insert(0, str(ROOT / "tools"))
import c131_holdout_grade as grader  # noqa: E402


def publish(path, data):
    tmp = path.with_suffix(".tmp")
    with tmp.open("x") as dest:
        json.dump(data, dest, sort_keys=True, indent=2, allow_nan=False)
        dest.write("\n")
    os.link(tmp, path)
    tmp.unlink()


class Runtime(C["Runtime"]):
    def __init__(self, a, root, role):
        self.a, self.root, self.role = a, root, role
        self.mode = "R" if role == "R" else "P"
        self.base = H["historical"](a)
        self.workload = W["CodeChat"](
            a.http / "1-ORIGINAL/raw/T1-input.json", sha, grader, H["SESSION"].ids_hash
        )
        self.command = H["TRANS"]["capture"].diagnostic_args(self.base["server_command"])
        exe = Path(self.command[0]).resolve(strict=True)
        self.auth = T["Provider"](
            a,
            root,
            "ORIGINAL" if role == "R" else "PRICE",
            exe,
            self.base["binary_sha256"],
            a.price_sha,
            selection="C281_R0" if role == "R" else "C281_PACK",
            kind="PRICE",
        )
        self.auth.mode = "OFF" if role == "R" else "ON"
        self.auth.loader_cache = run_path(HERE.parent / "supplied/loader.py")["checked"](
            a.loader_probe, LOADER
        )
        self.paths, self.stats = self.auth.data_paths, self.auth.data_stats
        closure = self.auth.verified["closure"]
        self.dso = {
            k: dict(path=v["file"], sha256=v["sha256"])
            for k, v in closure.items()
            if k != "ld-linux-x86-64.so.2"
        }
        need(self.dso.keys() == self.base["dso"].keys(), "DSO set")
        for k in self.dso.keys() - {"libcuda.so.1", "libllama.so.0", T["CPU"]}:
            need(self.dso[k] == self.base["dso"][k], "unexpected provider " + k)
        self.native = self.base | dict(
            dso=self.dso,
            server_command=self.command,
            official_ids=self.workload.token_hashes,
            historical_inputs=self.workload.digests,
            historical_workload_sha256=METHOD,
        )
        self.expected = self.base["explicit_env"].copy()
        if role != "R":
            self.expected.update(
                {
                    H["LIVE"].STORE_ENV: str(self.paths["manifest"]),
                    "TESY_NATIVE_CPU_WAVE": str(int(role == "W")),
                }
            )
        self.loader = dict(
            LD_LIBRARY_PATH=self.auth.search,
            LD_DEBUG="libs",
            LD_DEBUG_OUTPUT=str(root / "raw/loader"),
        )
        self.stamp = read(a.window / "resource-policy.json")["snapshot"]["utc"]
        self.cuts, self.checked, self.signalled = [], {}, None
        self.monitor_proof = T["AU"]["Authority"].monitor_proof(self.auth.monitor)
        self.plan_sha256 = METHOD
        self.recheck()

    def numeric(self, path):
        if self.role != "R":
            return super().numeric(path)
        ref = H["G"]["read"](self.a.r0 / "receipt.json", R0)
        need(ref["status"] == "GO_C269_CURRENT_C127", "R0 numeric gate")
        cfg = H["G"]["read"](
            self.a.r0 / "current-protocol.json", ref["raw_sha256"]["current-protocol.json"]
        )
        return cfg, R0

    def first(self, pid):
        for i, cap in enumerate(self.workload.caps, 1):
            result = self.root / "raw" / f"T{i}-result.json"
            if not result.is_file() or str(i) in self.checked:
                continue
            row = read(result)
            need(row["accepted"] and row["official_ids"] == self.workload.ids[i - 1], "client turn")
            log = (self.root / "raw" / (self.a.unit + ".stderr")).read_bytes()
            observed = W["serial"](
                log, i, row["usage"]["completion_tokens"], len(row["official_ids"]), cap, NATIVE
            )
            if self.a.reference:
                reference = H["G"]["read"](self.a.reference, self.a.reference_sha256)
                need(
                    reference["status"] == "MEASURED"
                    and reference["trial"]["role"] == "R"
                    and reference["trial"]["target_ids"][str(i)] == observed,
                    "greedy trajectory differs from independent R0",
                )
            self.checked[str(i)] = observed
        super().first(pid)


def compare(rows):
    need([v["role"] for v in rows] == list(ORDER), "six mirrored arms")
    mapped = [
        dict(role={"R": "ORIGINAL", "P": "OFF", "W": "ON"}[v["role"]], turns=v["turns"])
        for v in rows
    ]
    pairs, decision = C["compare"](mapped)
    for p in pairs:
        p["control"] = {"ORIGINAL": "R", "OFF": "P"}[p["control"]]

    def positive(p):
        return (
            min(p["first_final_gain_s"], p["valid_gain_s"]) > 0
            and p["decode_protected"]
            and p["t1_protected"]
        )

    return dict(
        pairs=pairs,
        decision=decision.replace("NOMINAL", "CODE_CHAT"),
        combined_positive_both_orders=all(positive(p) for p in pairs if p["control"] == "R"),
    )


def inputs(a):
    a.capture = a.archive / "part-29/tesy-natural-ids-capture-20261125-r01"
    a.placement = a.archive / "part-01/placement/r1/receipt.json"
    a.c270 = a.target
    target = H["G"]["read"](
        a.target / "receipt.json",
        "c49883b5abe3085bfd5fcb899c88209da4f133f742a1a7835d7f692f0c2a3035",
    )
    H["G"]["read"](
        a.http / "receipt.json", "4dc6c212c03fdc9f6fd7745bb16182ef2264181028db9187eb5a9db93e22dc78"
    )
    supplied = H["G"]["read"](HERE.parent / "supplied/decision.json", SUPPLIED)
    need(
        target["decision"] == "GO_UNCOUNTED_CLIENT"
        and supplied["decision"]["status"] == "GO_SUPPLIED_COMBINATION"
        and [x["role"] for x in supplied["cases"]["code153"]["arms"]] == list("RGPWWPGR")
        and {x["full_logits_sha256"] for x in supplied["cases"]["code153"]["arms"]}
        == {"6e5223faff42fdb9ff60a1b07ece78dae5b9e191f52c66cc98bcdf008b5e6115"},
        "numeric and supplied-work prerequisites",
    )
    arm = read(a.target / "ON/checked.json")
    a.files, a.genuine = arm["files"], arm["native"]
    a.price_sha = H["G"]["read"](a.build_dir / "receipt.json", T["BUILD"])["arms"]["PRICE"]
    need(
        sha(ROOT / "tools/c131_holdout_grade.py")
        == "a5442ad3dfe5bbef120db2c0736c93cbbf1940802f5e2c994374b74fcbd5190f"
        and sha(ROOT / "tools/grade_tasks.py")
        == "98734fafb6b6be6e1c12c5c15149ded95d32369026ba1d1e9ee315e5efe9000a",
        "functional validator identity",
    )
    win = H["G"]["read"](a.window / "receipt.json", a.window_sha256)
    start = json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    need(
        win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not win["reason"]
        and win["window_sha256"] == sha(a.window / "samples.jsonl")
        and win["canonical_policy_sha256"] == sha(a.window / "resource-policy.json")
        and datetime.fromisoformat(start).timestamp()
        >= int(T["prepare"].git(HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "fresh C55",
    )


def arm(a, out):
    PK["PK"]["age"](read(a.window / "resource-policy.json"), datetime.now(UTC))
    result = H["arm"](a, out, a.role, runtime=Runtime, method=METHOD, protocol=HERE / "protocol.md")
    if a.prepare_only:
        need(result["status"] == "PREPARED_ONLY", "no model in provider preflight")
        return result
    publish(out / "session.json", result)
    turns = result["client_rows"]
    need(
        [t["evaluated"] for t in turns] == [2043, 61]
        and [t["cached"] for t in turns] == [0, 2044]
        and all(t["validator"] == "PASS" and t["stop"] == "stop" for t in turns)
        and result["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE",
        "two valid turns or cleanup",
    )
    raw = out / "raw"
    size = sum(p.stat().st_size for p in raw.rglob("*") if p.is_file() and not p.is_symlink())
    need(size <= 64 << 20, "raw budget")
    mon = read(raw / (a.unit + ".json"))
    inv = PK["PK"]["compact"].validate_inventory(
        out,
        a.unit,
        {"native_explicit_env": read(out / "arm-inputs.json")["env"]},
        read(raw / (a.unit + ".launch.json")),
    )
    return dict(
        status="MEASURED",
        cleanup=result["cleanup"],
        preset_sha256=result["preset_sha256"],
        runtime_authority=result["runtime_authority"],
        trial=dict(
            role=a.role,
            unit=a.unit,
            turns=turns,
            target_ids=result["runtime_authority"]["trajectories"],
            session_sha256=sha(out / "session.json"),
            model_s=mon["elapsed_s"],
            maxima=mon["maxima"],
            energy=result["energy"],
            raw_bytes=size,
            c118_s=inv["s"],
        ),
    )


def family(a, out, r):
    need(
        re.fullmatch(r"tesy-c281-nvme-code-[a-z0-9-]+", a.unit)
        and sha(HERE / "protocol.md") == METHOD
        and T["prepare"].git(ROOT, "rev-parse", "HEAD") == a.commit
        and not T["prepare"].git(ROOT, "status", "--porcelain"),
        "clean study or unit identity",
    )
    r.update(
        commit=a.commit,
        tree=T["prepare"].git(ROOT, "rev-parse", "HEAD^{tree}"),
        order=list(ORDER),
        protocol_sha256=METHOD,
        program_sha256=sha(Path(__file__)),
        workload_sha256=sha(HERE / "workload.py"),
        window_sha256=a.window_sha256,
    )
    publish(out / "provenance.json", r.copy())
    inputs(a)
    if a.role:
        r.update(arm(a, out))
        return
    for candidate, expected in (
        (grader.CODE_GOLD[W["GRADER"]], "PASS"),
        (grader.CODE_MUTANT[W["GRADER"]], "FAIL"),
    ):
        need(grader.grade(W["GRADER"], candidate)["status"] == expected, "isolated functional gate")
    start = time.monotonic()
    r["arms"] = []

    def launch(label, role, prepare):
        r["stage"] = label
        args = sys.argv[1:].copy()
        args[args.index("--unit") + 1] = a.unit + "-" + label.lower()
        args[args.index("--new-output-dir") + 1] = str(out / label)
        args.extend(["--role", role])
        if prepare:
            args.append("--prepare-only")
        elif r["arms"]:
            ref = out / "1R/receipt.json"
            args.extend(["--reference", str(ref), "--reference-sha256", sha(ref)])
        need(3900 - (time.monotonic() - start) >= 650, "family budget")
        done = subprocess.run([sys.executable, "-IB", __file__, *args], timeout=650)
        row = read(out / label / "receipt.json")
        need(
            done.returncode == 0 and row["status"] == ("PREPARED_ONLY" if prepare else "MEASURED"),
            label + " " + row.get("reason", row["status"]),
        )
        return row

    for role in dict.fromkeys(ORDER):
        launch("preflight-" + role, role, True)
    for i, role in enumerate(ORDER, 1):
        if r["arms"]:
            prev = f"{i - 1}{ORDER[i - 2]}"
            C["WAIT"](out, prev, sha(out / prev / "receipt.json"))
        row = launch(str(i) + role, role, False)
        r["arms"].append(row["trial"] | dict(scope_s=row["elapsed_s"]))
        print(
            i,
            role,
            [(v["first_final_s"], v["decode_tok_s"]) for v in row["trial"]["turns"]],
            flush=True,
        )
    need(T["measure"].file_bytes(out) <= 400 << 20, "family output budget")
    r.update(compare(r["arms"]), status="COMPLETE_CODE_CHAT")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "archive",
        "build-dir",
        "r0",
        "target",
        "http",
        "derived",
        "loader-probe",
        "window",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=lambda v: Path(v).resolve(), required=True)
    for k in ("commit", "unit", "window-sha256"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--role", choices=list("RPW"))
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--reference", type=Path)
    p.add_argument("--reference-sha256")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    r = dict(status="FAIL_PRESERVED")
    tic = time.monotonic()
    try:
        if a.role:
            family(a, out, r)
        else:
            with (out.parent / "tesy-code-chat.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                family(a, out, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=str(exc), error_type=type(exc).__name__)
    r["elapsed_s"] = time.monotonic() - tic
    publish(out / "receipt.json", r)
    print(r["status"], r.get("reason", r.get("decision", "")), flush=True)
    raise SystemExit(r["status"] not in {"PREPARED_ONLY", "MEASURED", "COMPLETE_CODE_CHAT"})
