"""Run the sealed C281 two-turn HTTP client against original, CPU OFF and CPU ON."""

import argparse
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
T = run_path(HERE / "target.py")
Q, ROOT, sha, need, read, save, PK = (
    T[k] for k in ("Q", "ROOT", "sha", "need", "read", "save", "PK")
)
HTTP = Q / "packed_nvme_manifest/server_profile/verified_block/server_reserve/causal_server/http"
H = run_path(HTTP / "family.py")
WAIT = run_path(HTTP / "kv_width/natural/cpu_attention/target/http/serve.py")["wait_port"]
ORDER = ("ORIGINAL", "OFF", "ON", "ON", "OFF", "ORIGINAL")


class Runtime(H["Runtime"]):
    def __init__(self, a, root, role):
        self.a, self.root, self.role = a, root, role
        self.mode = "P"  # all arms use the serial C291 pack transport
        self.base = H["historical"](a)
        self.data = H["F"]["inputs"](a)
        self.plan = {}
        self.command = H["TRANS"]["capture"].diagnostic_args(self.base["server_command"])
        exe = Path(self.command[0]).resolve(strict=True)
        self.auth = T["Provider"](
            a,
            root,
            role,
            exe,
            self.base["binary_sha256"],
            a.price_sha,
            selection="C281_PACK",
            kind="PRICE",
        )
        self.paths, self.stats = self.auth.data_paths, self.auth.data_stats
        self.closure = self.auth.verified["closure"]
        self.dso = {
            k: dict(path=v["file"], sha256=v["sha256"])
            for k, v in self.closure.items()
            if k != "ld-linux-x86-64.so.2"
        }
        need(self.dso.keys() == self.base["dso"].keys(), "server closure inventory")
        for k in self.dso.keys() - {"libcuda.so.1", "libllama.so.0", T["CPU"]}:
            need(self.dso[k] == self.base["dso"][k], "unchanged provider " + k)
        self.native = self.base | dict(dso=self.dso, server_command=self.command)
        self.expected = self.base["explicit_env"] | {
            H["LIVE"].STORE_ENV: str(self.paths["manifest"])
        }
        if role != "ORIGINAL":
            self.expected["TESY_NATIVE_CPU_WAVE"] = str(int(role == "ON"))
        self.loader = dict(
            LD_LIBRARY_PATH=self.auth.search,
            LD_DEBUG="libs",
            LD_DEBUG_OUTPUT=str(root / "raw/loader"),
        )
        self.stamp = read(a.window / "resource-policy.json")["snapshot"]["utc"]
        self.cuts, self.checked, self.signalled = [], {}, None
        self.monitor_proof = T["AU"]["Authority"].monitor_proof(self.auth.monitor)
        self.plan_sha256 = sha(HERE / "http.md")
        self.recheck()

    def numeric(self, _path):
        if self.role == "ORIGINAL":
            folder = self.a.controls / "ORIGINAL"
        else:
            folder = self.a.target / "PRICE"
        cfg = read(folder / "wave-resource.json")
        closed = read(folder / "checked.json")
        cpu = self.dso[T["CPU"]]
        pins = cfg["pinned"]
        need(
            closed["cpu_sha256"]
            == cpu["sha256"]
            == pins["numerical_dso_sha256"][Path(cpu["path"]).name]
            and closed["files"] == self.a.files
            and closed["native"] == self.a.genuine,
            "numerical cut identity",
        )
        return cfg, sha(folder / "checked.json")

    def bind_c270(self, a, cfg, digest):
        need(
            cfg["pinned"]["model_sha256"] == self.base["model_sha256"]
            and cfg["pinned"]["server_sha256"] == self.base["binary_sha256"]
            and digest == self.numeric(a.c270)[1],
            "model and server proof",
        )
        self.recheck()

    def monitor_command(self, cmd, out):
        cmd = super().monitor_command(cmd, out)
        cmd[cmd.index("--variant") + 1] = "C281-native-wave-" + self.role
        point = cmd.index("--")
        cmd[point:point] = ["-p", "LimitCORE=0", "-p", "CoredumpFilter=0x0"]
        return cmd


def compare(rows):
    need([r["role"] for r in rows] == list(ORDER), "mirrored order")
    pairs = []
    for order in (rows[:3], rows[3:][::-1]):
        target = order[2]["turns"]
        for control in order[:2]:
            c = control["turns"]
            pairs.append(
                dict(
                    control=control["role"],
                    first_final_gain_s=c[1]["first_final_s"] - target[1]["first_final_s"],
                    valid_gain_s=c[1]["valid_s"] - target[1]["valid_s"],
                    prefill_gain_s=c[1]["prefill_s"] - target[1]["prefill_s"],
                    decode_gain_s=c[1]["decode_s"] - target[1]["decode_s"],
                    decode_protected=target[1]["decode_s"] <= 1.05 * c[1]["decode_s"],
                    t1_protected=target[0]["valid_s"] <= 1.05 * c[0]["valid_s"],
                )
            )
    paid = all(
        min(p["first_final_gain_s"], p["valid_gain_s"]) > 0
        and p["decode_protected"]
        and p["t1_protected"]
        for p in pairs
    )
    closed = all(p["first_final_gain_s"] <= 0 and p["valid_gain_s"] <= 0 for p in pairs)
    return (
        pairs,
        "GO_COMPONENT_NOMINAL"
        if paid
        else "NO_GO_COMPONENT_NOMINAL"
        if closed
        else "INCONCLUSIVE_NOMINAL",
    )


def family(a, out, r):
    need(
        T["prepare"].git(ROOT, "rev-parse", "HEAD") == a.commit
        and not T["prepare"].git(ROOT, "status", "--porcelain"),
        "clean experimental tree",
    )
    gate = read(a.target / "receipt.json")
    need(
        sha(a.target / "receipt.json") == a.target_sha256
        and gate["decision"] == "GO_UNCOUNTED_CLIENT"
        and gate["prior_sha256"] == sha(a.controls / "receipt.json") == T["STOPPED"]
        and all(
            sha(a.controls / role / "checked.json") == digest
            for role, digest in gate["prior_controls"].items()
        )
        and [(b["mode"], b["counts"]) for b in gate["arms"]]
        == [("ON", read(a.target / "ON/checked.json")["counts"]), ("PRICE", [])]
        and gate["arms"][0]["counts"][0] > 0,
        "mixed-graph numerical gate and selected controls",
    )
    a.files = read(a.target / "ON/checked.json")["files"]
    a.genuine = read(a.target / "ON/checked.json")["native"]
    build = read(a.build_dir / "receipt.json")
    need(sha(a.build_dir / "receipt.json") == T["BUILD"], "build")
    a.price_sha = build["arms"]["PRICE"]
    a.capture = a.archive / "part-29/tesy-natural-ids-capture-20261125-r01"
    a.verified = a.archive / "part-29/tesy-natural-ids-verified-20261125-r01"
    a.placement = a.archive / "part-01/placement/r1/receipt.json"
    a.c270 = a.target
    c55 = read(a.window / "receipt.json")
    need(
        sha(a.window / "receipt.json") == a.window_sha256
        and c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c55["reason"]
        and sha(a.window / "samples.jsonl") == c55["window_sha256"]
        and sha(a.window / "resource-policy.json") == c55["canonical_policy_sha256"],
        "C55",
    )
    stamp = datetime.fromisoformat(
        json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    ).timestamp()
    need(
        stamp >= int(T["prepare"].git(HERE, "log", "-1", "--format=%ct", "--", "http.md")),
        "fresh HTTP C55",
    )
    protocol = HERE / "http.md"
    r.update(
        commit=a.commit,
        tree=T["prepare"].git(ROOT, "rev-parse", "HEAD^{tree}"),
        method=sha(protocol),
        target_sha256=a.target_sha256,
        window_sha256=a.window_sha256,
        arms=[],
    )
    prefix = a.unit
    # Preflight each provider and its numerical certificate before starting the model.
    if a.role:
        role = a.role
        PK["PK"]["age"](read(a.window / "resource-policy.json"), datetime.now(UTC))
        row = H["arm"](a, out, role, runtime=Runtime, method=r["method"], protocol=protocol)
        if a.prepare_only:
            need(row["model_starts"] == 0 and row["status"] == "PREPARED_ONLY", "static admission")
            r.update(row)
            return
        save(out / "session.json", row)
        turns = row["client_rows"]
        need(
            len(turns) == 2
            and [t["cached"] for t in turns] == [0, 2044]
            and [t["evaluated"] for t in turns] == [2043, 153]
            and [t["output"] for t in turns] == [78, 47]
            and all(t["stop"] == "stop" for t in turns)
            and row["cleanup"] == "SERVER_EXIT_0_OWNER_STOP_UNIT_CLOSED_PORT_AVAILABLE",
            "natural work and cleanup",
        )
        raw = out / "raw"
        size = sum(f.stat().st_size for f in raw.rglob("*") if f.is_file() and not f.is_symlink())
        need(size <= 64 * 2**20, "raw budget")
        inv = PK["PK"]["compact"].validate_inventory(
            out,
            a.unit,
            {"native_explicit_env": read(out / "arm-inputs.json")["env"]},
            read(raw / (a.unit + ".launch.json")),
        )
        mon = read(raw / (a.unit + ".json"))
        trials = dict(
            role=role,
            unit=a.unit,
            turns=turns,
            energy=row["energy"],
            maxima=mon["maxima"],
            raw_bytes=size,
            c118_s=inv["s"],
            native_sha256=sha(out / "session.json"),
            target_ids=row["runtime_authority"]["trajectories"],
            model_s=mon["elapsed_s"],
        )
        r.update(row, status="MEASURED", trial=trials)
        return
    deadline = time.monotonic() + 3900

    def launch(label, role, prepare):
        need(deadline - time.monotonic() > 650, "remaining supervised family budget")
        argv = list(sys.argv[1:])
        argv[argv.index("--unit") + 1] = prefix + "-" + label.lower()
        argv[argv.index("--new-output-dir") + 1] = str(out / label)
        argv += ["--role", role]
        if prepare:
            argv += ["--prepare-only"]
        r["stage"] = label
        done = subprocess.run([sys.executable, "-IB", __file__, *argv], timeout=650)
        record = read(out / label / "receipt.json")
        need(
            done.returncode == 0
            and record["status"] == ("PREPARED_ONLY" if prepare else "MEASURED"),
            label + " " + record.get("reason", record["status"]),
        )
        return record

    for role in dict.fromkeys(ORDER):
        launch("preflight-" + role, role, True)
    previous = None
    for index, role in enumerate(ORDER, 1):
        if previous:
            WAIT(out, previous, sha(out / previous / "receipt.json"))
        label = f"{index}-{role}"
        record = launch(label, role, False)
        r["arms"].append(record["trial"])
        previous = label
    r["pairs"], r["decision"] = compare(r["arms"])
    r["status"] = "MEASURED"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "build-dir", "target", "controls", "window", "derived", "new-output-dir"):
        p.add_argument("--" + k, type=lambda v: Path(v).resolve(), required=True)
    for k in ("commit", "unit", "target-sha256", "window-sha256"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--role", choices=("ORIGINAL", "OFF", "ON"))
    p.add_argument("--prepare-only", action="store_true")
    a = p.parse_args()
    need(re.fullmatch(r"tesy-c281-nvme-wave-[a-z0-9-]+", a.unit), "HTTP unit identity")
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    r = {"status": "FAIL_PRESERVED"}
    tic = time.monotonic()
    try:
        family(a, out, r)
    except Exception as exc:
        r.update(reason=str(exc), error_type=type(exc).__name__)
    r["elapsed_s"] = time.monotonic() - tic
    save(out / "receipt.json", r)
    print(r["status"], r.get("decision", r.get("reason", "")))
    raise SystemExit(int(r["status"] not in ("MEASURED", "PREPARED_ONLY")))
