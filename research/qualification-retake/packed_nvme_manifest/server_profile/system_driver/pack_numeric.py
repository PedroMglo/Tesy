"""Run C292 transport OFF/ON against the verified current C269 capture and independent C127."""

import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
N = run_path(str(HERE / "numeric.py"))
Q, REPO, SC, PF, need, sha, read, save = (
    N[k] for k in ("QUAL", "REPO", "SC", "PF", "need", "sha", "read", "save")
)
PK = run_path(str(HERE.parents[1] / "capture_numeric/profile.py"))
live = PK["live"]
grade = live.linkage.load_module(HERE.parents[1] / "capture_numeric/grade.py", "c292_current_grade")
prepare, measure = N["prepare"], N["measure"]
REFERENCE = "01303f006ce46c25b06238a4f953f3c2405ab96fae93c370d500f28b39d06741"


class Pack(N["Current"]):
    def __init__(self, a, mode, out):
        source = SimpleNamespace(
            derived_dir=a.derived,
            constructor_receipt=a.constructor,
            derived_sha256=live.DERIVED,
            constructor_sha256=live.CONSTRUCTOR,
        )
        manifest, meta = live.static.metadata(source)
        self.mode = mode
        self.data_paths = dict(
            model=Path(meta["model_path"]),
            pack=Path(meta["pack_path"]),
            manifest=manifest,
            index=a.derived / "integral-index.json",
        )
        self.data_stats = {k: meta[k + "_stat"] for k in self.data_paths}
        self.pack_seen, self.pack_observations, self.env_checked = 0, set(), False
        s = read(a.static / "receipt.json")["arms"]
        incoming = s["C270_PACK"]
        candidate = Path(incoming["closure"][SC["SONAME"]]["file"])
        exe, image, hist = live.static.historical(SimpleNamespace(bin_dir=candidate.parent))
        need(image == candidate, "wrong C291 image")
        self.backend = Path(hist["backend_root"]).resolve(strict=True)
        need(
            prepare.git(self.backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
            == [live.static.PIN, live.static.TREE]
            and not prepare.git(self.backend, "status", "--porcelain"),
            "C291 source",
        )
        self.original_exe = Path(s["C270_R0"]["binary"])
        self.original_search = os.pathsep.join(s["C270_R0"]["search"])
        super().__init__(a.static, selection="C270_PACK", capture=(exe, live.static.CAPTURE))
        self.native_search = self.search
        env = SC["OLD"]["environment"](incoming["search"])
        for label, cmd in (
            ("list", [SC["OLD"]["LOADER"], "--list", exe]),
            ("relocate", ["/usr/bin/ldd", "-r", exe]),
        ):
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=25)
            text = proc.stdout + proc.stderr
            with (out / ("C292." + label)).open("x") as f:
                f.write(text)
            need(
                proc.returncode == 0 and not re.search("undefined symbol|not found|/stubs/", text),
                "C292 " + label,
            )
            links = SC["OLD"]["interpret"](text)
            need(
                {name: str(path.resolve(strict=True)) for name, path in links.items()}
                == {name: v["file"] for name, v in incoming["closure"].items()},
                "C292 provider",
            )
        self.initial_manifest = dict(
            manifest_sha256=meta["manifest_sha256"],
            index_sha256=meta["index_sha256"],
            derived_sha256=live.DERIVED,
            constructor_sha256=live.CONSTRUCTOR,
        )

    def recheck(self):
        super().recheck()
        need(
            all(
                live.static.derive.runtime_stat(p.stat()) == self.data_stats[k]
                for k, p in self.data_paths.items()
            ),
            "GGUF/pack/metadata changed",
        )

    def live(self, pid):
        seen = super().live(pid)
        proc = Path("/proc", str(pid))
        if not self.env_checked:
            values = [
                e
                for e in (proc / "environ").read_bytes().split(b"\0")
                if e.startswith((live.STORE_ENV + "=").encode())
            ]
            expected = (
                [(live.STORE_ENV + "=" + str(self.data_paths["manifest"])).encode()]
                if self.mode == "ON"
                else []
            )
            need(values == expected, "store environment")
            self.env_checked = True
        descriptors = live.proc_pack(proc, self.data_paths["pack"], self.data_stats["pack"])
        if descriptors:
            need(self.mode == "ON", "unexpected pack FD")
            self.pack_observations.update(descriptors)
            self.pack_seen += 1
        return seen


def arm(a, mode, out, control, reference):
    out.mkdir()
    ctl = Pack(a, mode, out)
    locks = SC["OLD"]["locks"](REPO)
    old = locks[SC["OLD"]["Q"] + "nvme_r0_gate/inputs/receipt.json"]
    sealed = {k: v for k, v in old.items() if k not in ("status", "model_forwards")}
    p = locks[SC["OLD"]["C270"]]
    run = p["runs"][0]
    exe, model, ids = map(Path, run["command"][:3])
    backend = Path(p["backend_root"]).resolve(strict=True)
    gold = Path(run["post_run_command"][-1])
    need(
        sha(ids) == sealed["ids_sha256"]
        and prepare.tree_digest(gold) == sealed["gold"]
        and prepare.tree_digest(reference) == sealed["gold"]
        and exe.resolve(strict=True) == ctl.original_exe,
        "C270 authority or C127",
    )
    unit = a.unit + "-" + mode.lower()
    b = SimpleNamespace(
        window=a.window,
        placement=a.placement,
        envelope="E20_R0",
        measurement_commit=a.commit,
        unit=unit,
    )
    prepare.freeze(b, out, sealed, (exe, model, ids, backend, gold, control["gomp"]))
    raw = out / "raw"
    cmp_env = dict(
        LD_LIBRARY_PATH=ctl.original_search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader")
    )
    base = PF["qualified_command"](read(out / "argv.json")["monitor"], Path("/usr/lib64"), cmp_env)
    cfg = read(out / "protocol.json")
    pinned = dict(sealed)
    pinned["startup_dso_sha256"] = {
        Path(v["file"]).name: v["sha256"]
        for k, v in ctl.verified["closure"].items()
        if k != SC["OLD"]["LOADER"].name
    }
    dsos = dict(sealed["numerical_dso_sha256"])
    lib = Path(ctl.verified["closure"][SC["SONAME"]]["file"]).name
    need(dsos[lib] == live.static.C269, "original numerical libllama")
    dsos[lib] = live.static.C291
    pinned.update(
        numerical_dso_sha256=dsos,
        capture_sha256=live.static.CAPTURE,
        backend_commit=live.static.PIN,
        backend_tree=live.static.TREE,
    )
    cfg.update(
        schema="tesy-system-C292-v1",
        pinned=pinned,
        original_runner_sha256=cfg["runner_sha256"],
        runner_sha256=sha(PK["PFJ"] / "monitor.py"),
        current_r0_sha256=REFERENCE,
        original_protocol_sha256=sha(out / "protocol.json"),
        metadata=ctl.initial_manifest,
    )
    cfgpath = out / "resource-store.json"
    save(cfgpath, cfg)
    cmd = PK["command"](base, ctl, out, mode, backend)
    expected = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | cmp_env | {"LD_LIBRARY_PATH": ctl.native_search}
    if mode == "ON":
        expected[live.STORE_ENV] = str(ctl.data_paths["manifest"])
    save(out / "pack-argv.json", dict(command=cmd, expected=expected))
    monitor = N["AU"]["Authority"].monitor_proof(ctl.monitor)
    policy = read(out / "resource-policy.json")
    PK["age"](policy, datetime.now(UTC))
    ident, count, seen, wall = PF["guarded_run"](cmd, out, unit, ctl, measure, N["run_bounded"])
    m = read(raw / (unit + ".json"))
    launch = read(raw / (unit + ".launch.json"))
    need(
        m["process_identity"] == launch["process_identity"] == ident
        and m["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(cfgpath)
        and measure.file_bytes(raw) <= 128 << 20,
        "arms/authority",
    )
    inventory = PK["compact"].validate_inventory(
        out, unit, {"native_explicit_env": expected}, launch
    )
    age = PK["age"](policy, datetime.fromisoformat(launch["start_inventory"]["popen_invoked_utc"]))
    PK["validate_monitor"](m, expected, cfg)
    fds = live.CaptureAuthority.fd_evidence(ctl)
    audit = ctl.audit(raw, ident["pid"])
    need({Path(f).name for f in seen} <= audit["initialized"].keys(), "live loaders")
    with (out / "c127.log").open("xb") as f:
        subprocess.run(
            read(out / "argv.json")["check"],
            stdout=f,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=45,
        )
    c127 = read(out / "selected.json")
    measure.check_gate(c127)
    cap = raw / (unit + ".capture")
    evaluation = grade.check_arm(cap, raw / (unit + ".stdout"), reference, c127)
    need(evaluation["status"] == "PASS_C292_ARM_NUMERICS", "incomplete C292 arm")
    save(out / "numerical.json", evaluation)
    return dict(
        status=evaluation["status"],
        scope_s=wall,
        model_s=m["elapsed_s"],
        maxima=m["maxima"],
        live_samples=count,
        scope_cleanup=True,
        c55_age_at_spawn_s=age,
        c118=inventory,
        pack_fd=fds,
        loader=audit,
        metadata=ctl.initial_manifest,
        monitor_provider=monitor,
        c127_sha256=sha(out / "selected.json"),
        numerical_sha256=sha(out / "numerical.json"),
    ), cap


def family(a, out, r):
    need(
        re.fullmatch("tesy-sys73-c292-[a-z0-9-]+", a.unit)
        and prepare.git(REPO, "rev-parse", "HEAD") == a.commit
        and not prepare.git(REPO, "status", "--porcelain"),
        "family revision or identity",
    )
    need(sha(a.reference / "receipt.json") == REFERENCE, "contemporary reference")
    control = read(a.reference / "receipt.json")
    need(control["status"] == "GO_C269_CURRENT_C127" and control["model_starts"] == 1, "C269 gate")
    ref = a.reference / "raw" / (control["unit"] + ".capture")
    win = read(a.window / "receipt.json")
    first = json.loads((a.window / "samples.jsonl").read_text().splitlines()[0])["utc"]
    need(
        sha(a.window / "receipt.json") == a.window_sha256
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and win["gpu_driver"] == control["kernel"]["release"]
        and datetime.fromisoformat(first).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "pack-protocol.md")),
        "C55 before protocol or changed",
    )
    r.update(
        commit=a.commit,
        tree=prepare.git(REPO, "rev-parse", "HEAD^{tree}"),
        unit=a.unit,
        window_sha256=a.window_sha256,
        static_sha256=N["STATIC"],
        reference_sha256=REFERENCE,
        protocol_sha256=sha(HERE / "pack-protocol.md"),
        implementation_sha256=sha(Path(__file__)),
        arms={},
    )
    cuts = []
    for mode in ("OFF", "ON"):
        r["last_arm"] = mode
        summary, cap = arm(a, mode, out / mode, control, ref)
        r["arms"][mode] = summary
        cuts.append(cap)
    pair = grade.check_pair(*cuts)
    save(out / "pair.json", pair)
    r.update(status=pair["status"], pair_sha256=sha(out / "pair.json"))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "static",
        "reference",
        "derived",
        "constructor",
        "window",
        "placement",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("unit", "commit", "window-sha256"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    r = dict(status="FAIL_PRESERVED", generation_requests=0, energy_J=None)

    def timeout(*_):
        raise TimeoutError("fourteen-minute family budget")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(840)
    try:
        with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            family(a, out, r)
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
    r["model_starts"] = len(list(out.glob("*/raw/*.launch.json")))
    r["raw_sha256"] = {
        str(f.relative_to(out)): sha(f) for f in sorted(out.rglob("*")) if f.is_file()
    }
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
