"""Price an exact target verifier under the natural code HTTP workload."""

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
CHAT = HERE.parent
S = run_path(CHAT / "run.py")
H, T, W = S["H"], S["T"], S["W"]
need, sha, read, publish = (S[k] for k in ("need", "sha", "read", "publish"))
CUT = run_path(CHAT / "block/run.py")
TRAJ = run_path(HERE / "trajectory.py")
ORDER = ("W", "OFF", "ON", "ON", "OFF", "W")
NUMERIC = "7616d59b0f9db28b0f65f6e482e4e22386675d2bd1ec5b06f2b87c577c967138"


def inputs(a):
    S["inputs"](a)
    need(a.cuts_sha256 == NUMERIC, "independently reviewed physical two-turn gate")
    src = H["G"]["read"](a.cuts / "receipt.json", a.cuts_sha256)
    need(
        src["status"] == "PASS_TWO_CODE_CUTS"
        and [r["role"] for r in src["arms"]] == list(CUT["ORDER"])
        and all(
            r["failed"] == [] and sha(a.cuts / r["role"] / "proof.json") == r["proof_sha256"]
            for r in src["arms"]
        ),
        "sealed two-turn bitwise gate",
    )
    work = H["G"]["read"](
        a.cut_build / "work.json", read(a.cuts / "R/resource.json")["pinned"]["ids_sha256"]
    )
    need(
        read(a.cut_build / "receipt.json")["files"]["work.json"] == sha(a.cut_build / "work.json")
        and sha(a.cut_build / "receipt.json") == src["client_sha256"] == CUT["CLIENT"],
        "target fixture",
    )
    a.data = {
        "T1": dict(prompt=work["t1"], target=work["first"], cap=256),
        "T2": dict(prompt=work["t2"], target=work["target"], cap=768),
    }
    p = a.archive / "part-177/tesy-packed-causal-plan-20261126-r03"
    orig = H["G"]["read"](p / "receipt.json", H["PLAN_PIN"])
    plan0 = H["G"]["read"](p / "r0.stdout", orig["same_output_sha256"])["T1"]
    code = read(CHAT / "lookup.json")
    plan1 = H["G"]["read"](a.replay / "steps.json", code["steps_sha256"])["T2"]
    a.plan = {"T1": plan0, "T2": plan1}
    need(
        H["F"]["validate"](plan0, a.data["T1"]) == orig["turns"]["T1"]
        and H["F"]["validate"](plan1, a.data["T2"]) == code["counts"],
        "past-only native work",
    )
    a.options = orig["options"][1:9]
    need(
        a.options
        == [
            "--spec-type",
            "ngram-simple",
            "--spec-ngram-simple-size-n",
            "2",
            "--spec-ngram-simple-size-m",
            "2",
            "--spec-ngram-simple-min-hits",
            "1",
        ],
        "dispatch geometry",
    )
    need(
        not a.unit.endswith("-r") and re.fullmatch("tesy-c281-nvme-price-[a-z0-9-]+", a.unit),
        "unit",
    )
    first = json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    need(
        datetime.fromisoformat(first).timestamp()
        >= int(T["prepare"].git(HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "C55 follows price protocol",
    )


class Runtime(S["Runtime"]):
    def __init__(self, a, out, role):
        super().__init__(a, out, "W")
        self.role = role
        self.mode = role if role != "W" else "P"
        self.data = a.data
        self.plan = a.plan
        self.plan_sha256 = H["POST"].contract.source_digest(a.plan)
        if role in ("OFF", "ON"):
            checked = H["G"]["read"](a.rows / "receipt.json", CUT["ROWS"])["images"]["CPU"]
            key = "libllama.so.0"
            path = Path(checked["image"]).resolve(strict=True)
            sig = checked["image_sha256"]
            ctl = self.auth
            old = ctl.verified["closure"][key]["file"]
            need(sha(path) == sig, "repaired target")
            for table in (ctl.files, ctl.keys, ctl.stats):
                del table[old]
            ctl.files[str(path)] = sig
            ctl.stats[str(path)] = T["AU"]["identity"](path)
            ctl.keys[str(path)] = T["AU"]["reference_key"](str(path), ctl.stats[str(path)])
            ctl.allowed = set(ctl.files)
            ctl.initial = (ctl.initial - {old}) | {str(path)}
            ctl.verified["closure"][key] = dict(file=str(path), sha256=sig)
            overlay = out / "row-provider"
            overlay.mkdir()
            (overlay / key).symlink_to(path)
            ctl.search = str(overlay) + os.pathsep + ctl.search
            self.dso[key] = dict(path=str(path), sha256=sig)
            self.loader["LD_LIBRARY_PATH"] = ctl.search
        if role == "ON":
            self.command += a.options
            self.expected.update(H["S"]["RB"]["T"]["flags"]("CUDA"))
            self.expected["TESY_B3_CPU_LONG_ROWS"] = "1"
        self.native = self.native | dict(dso=self.dso, server_command=self.command)
        profile = T["H"]["SC"]["OLD"]
        expected = {k: v["file"] for k, v in self.auth.verified["closure"].items()}
        env = profile["environment"](self.auth.search.split(os.pathsep))
        for suffix, cmd in (
            ("list", [profile["LOADER"], "--list", self.auth.exe]),
            ("relocate", ["/usr/bin/ldd", "-r", self.auth.exe]),
        ):
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=25)
            log = result.stdout + result.stderr
            (out / ("combined-" + suffix + ".log")).write_text(log)
            need(
                result.returncode == 0
                and not re.search("undefined symbol|not found|/stubs/", log)
                and {k: str(v.resolve(strict=True)) for k, v in profile["interpret"](log).items()}
                == expected,
                "HTTP provider " + suffix,
            )
        self.recheck()

    def numeric(self, _):
        root = self.a.cuts / self.role
        cmd = read(root / "invocation.json")
        unit = cmd["command"][cmd["command"].index("--run-id") + 1]
        mon = read(root / "raw" / (unit + ".json"))
        family = H["G"]["read"](self.a.cuts / "receipt.json", self.a.cuts_sha256)
        row = next(x for x in family["arms"] if x["role"] == self.role)
        need(
            sha(root / "raw" / (unit + ".json")) == row["monitor_sha256"] and not row["failed"],
            "qualified cut monitor",
        )
        cfg = H["G"]["read"](root / "resource.json", mon["limits"]["resource_protocol_sha256"])
        # The direct executable includes the interpreter in its authenticated closure. The
        # server source catalogue records its interpreter separately from its DSOs.
        pins = dict(cfg["pinned"])
        libraries = dict(pins["startup_dso_sha256"])
        loader = self.auth.verified["closure"]["ld-linux-x86-64.so.2"]
        need(libraries.pop(Path(loader["file"]).name) == loader["sha256"], "shared interpreter")
        need(
            all(
                any(Path(r["path"]).name == k and r["sha256"] == h for r in self.dso.values())
                for k, h in libraries.items()
            ),
            "all numerical DSOs in server",
        )
        pins["startup_dso_sha256"] = libraries
        return cfg | dict(pinned=pins), self.a.cuts_sha256

    def first(self, pid):
        for index in (1, 2):
            label = f"T{index}"
            result = self.root / "raw" / (label + "-result.json")
            if not result.is_file() or str(index) in self.checked:
                continue
            item = read(result)
            need(
                item["accepted"] and item["official_ids"] == self.data[label]["prompt"],
                "authentic HTTP turn",
            )
            log = (self.root / "raw" / (self.a.unit + ".stderr")).read_bytes()
            self.checked[str(index)] = TRAJ["evaluate"](
                log, index, self.data[label], self.plan[label], self.mode == "ON", H["T"]
            )
        H["Runtime"].first(self, pid)


def arm(a, out, role):
    S["PK"]["PK"]["age"](read(a.window / "resource-policy.json"), datetime.now(UTC))
    result = H["arm"](
        a,
        out,
        role,
        runtime=Runtime,
        method=sha(HERE / "protocol.md"),
        protocol=HERE / "protocol.md",
    )
    if a.prepare_only:
        return result
    publish(out / "session.json", result)
    turns = result["client_rows"]
    need(
        result["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE"
        and all(t["validator"] == "PASS" and t["stop"] == "stop" for t in turns)
        and [(t["cached"], t["evaluated"]) for t in turns] == [(0, 2043), (2044, 61)],
        "client and cleanup",
    )
    raw = out / "raw"
    mon = read(raw / (a.unit + ".json"))
    inv = S["PK"]["PK"]["compact"].validate_inventory(
        out,
        a.unit,
        {"native_explicit_env": read(out / "arm-inputs.json")["env"]},
        read(raw / (a.unit + ".launch.json")),
    )
    need(T["measure"].file_bytes(raw) < 64 << 20, "arm raw bytes")
    return dict(
        status="MEASURED",
        cleanup=result["cleanup"],
        runtime_authority=result["runtime_authority"],
        preset_sha256=result["preset_sha256"],
        trial=dict(
            role=role,
            unit=a.unit,
            turns=turns,
            ids=result["runtime_authority"]["trajectories"],
            maxima=mon["maxima"],
            energy=result["energy"],
            c118_s=inv["s"],
            model_s=mon["elapsed_s"],
            session_sha256=sha(out / "session.json"),
        ),
    )


def decision(rows):
    need(tuple(r["role"] for r in rows) == ORDER, "mirrored order")
    pairs = []
    for triplet in (rows[:3], list(reversed(rows[3:]))):
        on = triplet[-1]
        for control in triplet[:2]:
            x, y = control["turns"][1], on["turns"][1]
            pairs.append(
                dict(
                    control=control["role"],
                    first_final_gain_s=x["first_final_s"] - y["first_final_s"],
                    valid_gain_s=x["valid_s"] - y["valid_s"],
                    decode_gain_s=x["decode_s"] - y["decode_s"],
                    decode_protected=y["decode_s"] <= 1.05 * x["decode_s"],
                    t1_protected=on["turns"][0]["valid_s"] <= 1.05 * control["turns"][0]["valid_s"],
                )
            )
    gain = all(
        min(p["first_final_gain_s"], p["valid_gain_s"]) > 0
        and p["decode_protected"]
        and p["t1_protected"]
        for p in pairs
    )
    loss = all(max(p["first_final_gain_s"], p["valid_gain_s"]) < 0 for p in pairs)
    return (
        "GO_CODE_COMPONENT"
        if gain
        else "NO_GO_CODE_COMPONENT"
        if loss
        else "INCONCLUSIVE_CODE_COMPONENT"
    ), pairs


def family(a, out, r):
    inputs(a)
    head, tree = H["G"]["tree"](T["ROOT"])
    need(head == a.commit, "clean price source")
    r.update(
        commit=head,
        tree=tree,
        window_sha256=a.window_sha256,
        protocol_sha256=sha(HERE / "protocol.md"),
        cut_sha256=a.cuts_sha256,
        order=ORDER,
        arms=[],
    )
    if a.role:
        r.update(arm(a, out, a.role))
        return
    publish(
        out / "provenance.json",
        r
        | dict(
            program_sha256=sha(HERE / "family.py"), trajectory_sha256=sha(HERE / "trajectory.py")
        ),
    )
    start = time.monotonic()
    for name, role, pre in [(f"preflight-{k.lower()}", k, True) for k in dict.fromkeys(ORDER)] + [
        (f"{i}{k}", k, False) for i, k in enumerate(ORDER, 1)
    ]:
        r["stage"] = name
        if r["arms"]:
            prev = r["arms"][-1]["folder"]
            S["C"]["WAIT"](out, prev, sha(out / prev / "receipt.json"))
        args = sys.argv[1:].copy()
        args[args.index("--new-output-dir") + 1] = str(out / name)
        args[args.index("--unit") + 1] = a.unit + "-" + name.lower()
        args += ["--role", role]
        if pre:
            args.append("--prepare-only")
        need(3600 - (time.monotonic() - start) >= 650, "remaining price budget")
        proc = subprocess.run([sys.executable, "-IB", __file__, *args], timeout=650)
        row = read(out / name / "receipt.json")
        need(
            proc.returncode == 0 and row["status"] == ("PREPARED_ONLY" if pre else "MEASURED"),
            name + " " + row.get("reason", row["status"]),
        )
        if not pre:
            r["arms"].append(
                row["trial"] | dict(folder=name, receipt_sha256=sha(out / name / "receipt.json"))
            )
            print(
                name,
                "first",
                row["trial"]["turns"][1]["first_final_s"],
                "valid",
                row["trial"]["turns"][1]["valid_s"],
                flush=True,
            )
        need(T["measure"].file_bytes(out) <= 400 << 20, "family raw bytes")
    r["decision"], r["pairs"] = decision(r["arms"])
    r["status"] = "COMPLETE_CODE_PRICE"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "archive",
        "derived",
        "build-dir",
        "r0",
        "target",
        "http",
        "loader-probe",
        "window",
        "cuts",
        "cut-build",
        "rows",
        "replay",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    for k in ("unit", "commit", "window-sha256", "cuts-sha256"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--role", choices=ORDER[:3])
    p.add_argument("--prepare-only", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    start = time.monotonic()
    r = dict(status="FAIL_PRESERVED")
    try:
        if a.role:
            family(a, out, r)
        else:
            with (out.parent / "tesy-code-price.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                family(a, out, r)
    except Exception as e:
        r.update(reason=str(e), error_type=type(e).__name__)
    r.update(elapsed_s=time.monotonic() - start)
    publish(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""), flush=True)
    raise SystemExit(int(r["status"] not in ("PREPARED_ONLY", "MEASURED", "COMPLETE_CODE_PRICE")))
