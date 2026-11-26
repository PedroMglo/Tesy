"""Attach current, checked providers and the native token witness to the unchanged C281 session."""

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from runpy import run_path
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent
T = run_path(str(HERE / "trajectory.py"))
F = T["PLAN"]
Q, need, sha, save, G = (F[k] for k in ("QUAL", "need", "sha", "save", "GRAPH"))
S = run_path(str(HERE.parents[1] / "family.py"))
N, PK, AU = S["N"], S["PK"], S["N"]["AU"]
TRANS = run_path(str(Q / "packed_nvme_manifest/server_profile/conversation/transport_profile.py"))
SESSION, POST = TRANS["session"], TRANS["post"]
LIVE = PK["live"]
METHOD = "30bc452406d7de76b3743edb366b8913485b5616c9e1c0c5212099dd7b102588"
PLAN_PIN = "51644c12d221fd72e6e36bec6000ed3f3cbda2b63d1154a8cfd97bb99fe9d570"
MODES = ("ON", "OFF", "P", "R")
HIST_KEYS = (
    "official_ids historical_inputs server_command binary_sha256 explicit_env backend dso "
    "parallel_runtime model_sha256 session_date port cap_bytes protocol_sha256 "
    "historical_workload_sha256"
).split()
read = SESSION.load


def historical(a):
    r = G["read"](a.capture / "receipt.json", F["OLD"]["CAPTURE"])
    old = G["read"](a.capture / "preset.json", r["preset_sha256"])
    base = POST.projection({k: old[k] for k in HIST_KEYS})
    authority = read(POST.SESSION / "inputs.json")
    need(
        POST.contract.source_digest(base) == authority["actual_inputs_sha256"]
        and sha(G["REPO"] / "tools/optin_integration_client.py") == POST.contract.CLIENT_SHA
        and sha(POST.contract.C281 / "protocol.json") == base["historical_workload_sha256"],
        "independent C281 input authority",
    )
    for key, h in TRANS["capture"].SOURCES.items():
        need(sha(Path(base["backend"]) / key) == h, "original sampling implementation")
    return base


class Runtime:
    def __init__(self, a, root, mode):
        self.a, self.root, self.mode = a, root, mode
        self.base = historical(a)
        self.gate = G["read"](a.physical / "receipt.json", F["GATE"])
        plan = G["read"](a.plan / "receipt.json", PLAN_PIN)
        need(
            plan["status"] == "GO_CAUSAL_SERVER_PLAN" and self.gate["model_starts"] == 7,
            "prerequisites",
        )
        self.data = F["inputs"](a)
        self.plan = G["read"](a.plan / "r0.stdout", plan["same_output_sha256"])
        for k, v in self.data.items():
            need(F["validate"](self.plan[k], v) == plan["turns"][k], "verified proposal schedule")
        self.auth = N["Current"](a.static, selection="C281_R0" if mode == "R" else "C281_PACK")
        ctl = self.auth
        self.command = TRANS["capture"].diagnostic_args(self.base["server_command"])
        if mode == "ON":
            self.command += plan["options"][1:9]
            need(
                self.command[-8:]
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
                "exact proposal CLI",
            )
        need(
            Path(self.command[0]).resolve(strict=True) == ctl.exe
            and sha(ctl.exe) == self.base["binary_sha256"],
            "current C281 executable",
        )
        metadata = SimpleNamespace(
            derived_dir=a.derived,
            constructor_receipt=a.constructor,
            derived_sha256=LIVE.DERIVED,
            constructor_sha256=LIVE.CONSTRUCTOR,
        )
        manifest, meta = LIVE.static.metadata(metadata)
        self.paths = dict(
            model=Path(meta["model_path"]),
            pack=Path(meta["pack_path"]),
            index=a.derived / "integral-index.json",
            manifest=manifest,
        )
        self.stats = {k: meta[k + "_stat"] for k in self.paths}
        need(Path(self.command[self.command.index("-m") + 1]).samefile(self.paths["model"]), "GGUF")
        self.closure = dict(ctl.verified["closure"])
        if mode in {"ON", "OFF"}:
            built = self.block_image()
            name = "libllama.so.0"
            path, h = built["image"], built["image_sha256"]
            image = Path(path)
            need(
                sha(image) == h and (image.parent / name).resolve(strict=True) == image, "block ELF"
            )
            original = self.closure[name]["file"]
            for table in (ctl.stats, ctl.files, ctl.keys):
                del table[original]
            ctl.stats[path] = AU["identity"](path)
            ctl.files[path] = h
            ctl.keys[path] = AU["reference_key"](path, ctl.stats[path])
            ctl.allowed = set(ctl.files)
            ctl.initial = (ctl.initial - {original}) | {path}
            self.closure[name] = dict(file=path, sha256=h)
            ctl.search = str(image.parent) + os.pathsep + ctl.search
        self.expected = dict(self.base["explicit_env"])
        if mode != "R":
            self.expected[LIVE.STORE_ENV] = str(manifest)
        if mode == "ON":
            self.expected.update(self.block_flags())
        self.loader = dict(
            LD_LIBRARY_PATH=ctl.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(root / "raw/loader")
        )
        self.dso = {
            k: dict(path=v["file"], sha256=v["sha256"])
            for k, v in self.closure.items()
            if k != "ld-linux-x86-64.so.2"
        }
        need(self.dso.keys() == self.base["dso"].keys(), "server sonames")
        for key in self.dso.keys() - {"libcuda.so.1", "libllama.so.0"}:
            need(self.dso[key] == self.base["dso"][key], "unexpected provider change " + key)
        self.native = self.base | dict(dso=self.dso, server_command=self.command)
        self.stamp = G["read"](
            a.window / "resource-policy.json",
            read(a.window / "receipt.json")["canonical_policy_sha256"],
        )["snapshot"]["utc"]
        self.cuts, self.checked = [], {}
        self.signalled = None
        self.monitor_proof = AU["Authority"].monitor_proof(ctl.monitor)
        self.recheck()

    def block_image(self):
        return G["read"](self.a.client / "receipt.json", S["CLIENT"])["arms"]["BLOCK"]

    def block_flags(self):
        return S["RB"]["T"]["flags"]("CUDA")

    def recheck(self):
        self.auth.recheck()
        need(
            all(
                LIVE.static.derive.runtime_stat(v.stat()) == self.stats[k]
                for k, v in self.paths.items()
            ),
            "transport changed",
        )

    def selection(self, _):
        raise ValueError("unexpected implicit selection")

    def sources(self, selector):
        need(selector == self.selection, "controlled selection")
        return self.native

    def historical_projection(self, frozen):
        need(frozen == self.native, "runtime input changed")
        return self.base

    def numeric(self, path):
        if self.mode == "R":
            r = G["read"](path / "receipt.json", PK["REFERENCE"])
            need(r["status"] == "GO_C269_CURRENT_C127", "original C127 witness")
            return G["read"](
                path / "current-protocol.json", r["raw_sha256"]["current-protocol.json"]
            ), PK["REFERENCE"]
        case = {"ON": "ON3", "OFF": "OFF1", "P": "HIST1"}[self.mode]
        key = case + "/packed-resource.json"
        need(self.gate["arms"][case]["status"] == "PASS_ROLLBACK_AR", "serial geometry witness")
        return G["read"](self.a.physical / key, self.gate["raw_sha256"][key]), F["GATE"]

    def bind_c270(self, _a, cfg, h):
        need(
            h == (PK["REFERENCE"] if self.mode == "R" else F["GATE"])
            and cfg["pinned"]["model_sha256"] == self.base["model_sha256"]
            and cfg["pinned"]["startup_dso_sha256"][Path(self.dso["libllama.so.0"]["path"]).name]
            == self.dso["libllama.so.0"]["sha256"],
            "current numerical provider",
        )
        self.recheck()

    def monitor_command(self, cmd, out):
        cmd = POST.monitor_argv(cmd, Path("/usr/lib64"), self.loader)
        start = cmd.index(str(G["REPO"] / "tools/run_bounded.py"))
        cmd[start : start + 1] = [
            TRANS["__file__"],
            "--c55-launch-policy",
            str(out / "resource-policy.json"),
            sha(out / "resource-policy.json"),
        ]
        cmd[cmd.index("--variant") + 1] = "C281-block-http-" + self.mode
        sep = cmd.index("--", start)
        need(cmd[sep + 1 :] == self.command, "server CLI changed")
        for k, v in self.expected.items():
            if k not in self.base["explicit_env"]:
                cmd[sep:sep] = ["--env", k + "=" + v]
                sep += 2
        return cmd

    def owner_stop(self, pid, sig):
        before = time.monotonic_ns()
        os.killpg(pid, sig)
        self.signalled = dict(
            pid=pid, signal=int(sig), before_ns=before, after_ns=time.monotonic_ns()
        )

    def first(self, pid):
        self.recheck()
        proc = Path("/proc", str(pid))
        need(
            (proc / "cmdline").read_bytes() == TRANS["capture"].argv_image(self.command),
            "live argv",
        )
        need(self.auth.initial <= self.auth.live(pid), "server maps")
        uuid = read(self.root / "resource-policy.json")["gpu"]["uuid"]
        apps = subprocess.check_output(
            [
                "/usr/bin/nvidia-smi",
                "--query-compute-apps=pid,gpu_uuid",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=8,
            env=self.auth.monitor.data["monitor_environment"],
        ).splitlines()
        need(apps == [f"{pid}, {uuid}"], "exclusive target GPU ownership")
        descriptors = TRANS["cut"](proc, self.paths, self.stats, "R" if self.mode == "R" else "P")
        env = dict(x.split(b"=", 1) for x in (proc / "environ").read_bytes().split(b"\0") if x)
        need(
            all(env.get(k.encode()) == v.encode() for k, v in (self.expected | self.loader).items())
            and {k.decode() for k in env if k.startswith(b"TESY_")} == set(self.expected),
            "native flags",
        )
        self.cuts.append(
            dict(pid=pid, gpu_uuid=uuid, fds=descriptors, monotonic_ns=time.monotonic_ns())
        )
        for i in (1, 2):
            if (self.root / "raw" / f"T{i}-result.json").is_file() and str(i) not in self.checked:
                log = self.root / "raw" / (self.a.unit + ".stderr")
                self.checked[str(i)] = T["grade"](
                    log.read_bytes(), i, self.data, self.plan, self.mode
                )

    def last(self, _pid):
        need(set(self.checked) == {"1", "2"}, "both target trajectories")

    def finish(self, ident, monitor, out, rid):
        self.recheck()
        self.closed_ns = time.monotonic_ns()
        need(
            self.signalled
            and self.signalled["pid"] == ident["pid"]
            and self.signalled["signal"] == signal.SIGINT
            and self.cuts[-1]["monotonic_ns"] <= self.signalled["before_ns"] <= self.closed_ns,
            "monitor stop ordering",
        )
        need(
            monitor["command"] == self.command
            and monitor["explicit_env"] == self.expected | self.loader
            and monitor["start_inventory"]["popen_invoked_utc"],
            "native monitor provenance",
        )
        return dict(
            trajectories=self.checked,
            cuts=self.cuts,
            driver=self.monitor_proof,
            c55_age_at_spawn_s=TRANS["c55_age"](
                self.stamp, datetime.fromisoformat(monitor["start_inventory"]["popen_invoked_utc"])
            ),
            loader=self.auth.audit(out / "raw", ident["pid"]),
            signal=self.signalled,
            verified_cleanup_ns=self.closed_ns,
        )


def arm(
    a, out, mode, *, runtime=Runtime, method=METHOD, protocol=HERE / "protocol.md", input_check=None
):
    rt = runtime(a, out, mode)
    cfg, h = rt.numeric(a.c270)
    rt.bind_c270(a, cfg, h)
    _, model = POST.contract.placement(a.window, a.placement)
    need(cfg["model_stat"] == model, "model placement")
    need(
        sha(HERE / "protocol.md") == METHOD
        and sha(protocol) == method
        and G["tree"](G["REPO"])[0] == a.commit,
        "frozen study",
    )
    record = dict(
        mode=mode,
        commit=a.commit,
        server_source=G["tree"](Path(rt.base["backend"])),
        pack_source=[LIVE.static.PIN, LIVE.static.TREE],
        binary_sha256=rt.base["binary_sha256"],
        argv=rt.command,
        dso=rt.dso,
        env=rt.expected | rt.loader,
        numerical_gate=h,
        protocol_sha256=method,
        driver=rt.monitor_proof,
        plan_sha256=PLAN_PIN,
        window_sha256=a.window_sha256,
    )
    save(out / "arm-inputs.json", record)
    if input_check is not None:
        input_check(record)
    if a.prepare_only:
        return dict(status="PREPARED_ONLY", mode=mode, model_starts=0)
    orig = SESSION.campaign
    scoped = FunctionType(
        orig.__code__,
        orig.__globals__
        | {
            "sources": rt.sources,
            "validate_c270": rt.numeric,
            "os": SimpleNamespace(environ=os.environ, fstat=os.fstat, killpg=rt.owner_stop),
        },
        orig.__name__,
        orig.__defaults__,
        orig.__closure__,
    )
    result = scoped(a, out, rt)
    reader = run_path(str(Q / "ik_mapped_experts/frontend/server/session.py"))["summarize"]
    rows = [
        reader(row, out / "raw", i)
        for i, row in enumerate(read(out / "client-receipt.json")["rows"], 1)
    ]
    for i, row in enumerate(rows, 1):
        ids = rt.checked[str(i)]
        need(row["output"] == row["predicted"] == ids["sampled"], "client output denominator")
        timing = read(out / "raw" / f"T{i}-timings-observed.json")
        need(
            timing.get("draft_n", 0) == ids["proposed"]
            and timing.get("draft_n_accepted", 0) == ids["accepted"],
            "server draft accounting",
        )
    energy = run_path(str(Q / "packed_nvme_manifest/server_profile/system_driver/review.py"))[
        "power"
    ]
    return result | dict(mode=mode, client_rows=rows, energy=energy(out, dict(unit=a.unit)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "static",
        "capture",
        "verified",
        "physical",
        "plan",
        "client",
        "derived",
        "constructor",
        "window",
        "placement",
        "c270",
        "new-output-dir",
    ):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("commit", "window-sha256", "unit"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--prepare-only", action="store_true")
    a = parser.parse_args()
    os.umask(0o077)
    root = a.new_output_dir.resolve()
    root.mkdir()
    started = time.monotonic()
    r = dict(status="FAIL_PRESERVED", commit=a.commit, protocol_sha256=METHOD, arms={})
    try:
        G["read"](a.window / "receipt.json", a.window_sha256)
        if a.mode:
            r = arm(a, root, a.mode)
        else:
            for mode in MODES:
                args = sys.argv[1:].copy()
                args[args.index("--new-output-dir") + 1] = str(root / mode)
                args[args.index("--unit") + 1] = a.unit + "-" + mode.lower()
                cmd = [sys.executable, "-IB", __file__, *args, "--mode", mode]
                p = subprocess.run(cmd, timeout=650)
                child = read(root / mode / "receipt.json")
                r["arms"][mode] = dict(
                    status=child["status"], sha256=sha(root / mode / "receipt.json")
                )
                need(p.returncode == 0, mode + ": " + child.get("error", child["status"]))
            r["status"] = "PREPARED_FOUR_ARMS" if a.prepare_only else "GO_FOUR_NATURAL_DIAGNOSTICS"
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", error=f"{type(exc).__name__}: {exc}")
    r.update(
        wall_s=time.monotonic() - started,
        model_starts=len(list(root.rglob("*.launch.json"))),
        started_requests=len(list(root.rglob("T*-request.jsonl"))),
    )
    r["raw_sha256"] = {
        str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*")) if p.is_file()
    }
    save(root / "receipt.json", r)
    print(r["status"], r.get("error", ""), flush=True)
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
