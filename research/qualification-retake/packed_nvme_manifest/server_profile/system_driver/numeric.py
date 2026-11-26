"""Run the original C269 witness against C127 with the current system driver."""

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SC = run_path(str(HERE / "screen.py"))
QUAL, REPO, need, sha = (SC[k] for k in ("QUAL", "REPO", "need", "sha"))
R0 = QUAL / "nvme_r0_gate"
sys.path.insert(0, str(R0))
import measure  # noqa: E402
import prepare  # noqa: E402
import run_bounded  # noqa: E402

PF = run_path(str(R0 / "qualified_profile/profile.py"))
AU = run_path(str(R0 / "qualified_profile/authority.py"))
L = run_path(str(R0 / "driver_pair/profile.py"))
STATIC = "0c50a2657aa1dd5ba53a862e0e3e5cf4c2e366eb4663109ce2f2c03c2557df3b"
read, save = prepare.load, prepare.save


class Current:
    def __init__(self, static, *, selection="C270_R0", capture=None):
        need(sha(static / "receipt.json") == STATIC, "preflight digest")
        s = read(static / "receipt.json")
        need(
            s["status"] == "GO_CURRENT_NUMERICAL_GATE"
            and sha(HERE / "screen.py") == s["source_sha256"],
            "preflight program",
        )
        self.kernel = s["kernel"]
        self.loader_cache = None
        nvml = str(Path("/usr/lib64/libnvidia-ml.so.1").resolve(strict=True))
        self.monitor = SimpleNamespace(
            pre=dict(
                kernel=self.kernel,
                nvml_sha256=s["driver_files"][nvml],
                monitor_cli_sha256=s["driver_files"]["/usr/bin/nvidia-smi"],
            ),
            data=dict(
                monitor_environment=SC["OLD"]["environment"]([Path("/usr/lib64")]),
                monitor_aliases={"libnvidia-ml.so.1": nvml},
            ),
            recheck=self.recheck,
        )
        self.verified = s["arms"][selection]
        self.exe, binary_sha = capture or (
            Path(self.verified["binary"]),
            self.verified["binary_sha256"],
        )
        self.arm = dict(executable_sha256=binary_sha)
        self.search = os.pathsep.join(self.verified["search"])
        self.initial = {v["file"] for v in self.verified["closure"].values()}
        self.files = {v["file"]: v["sha256"] for v in self.verified["closure"].values()}
        self.drivers = {
            p: h
            for p, h in s["driver_files"].items()
            if p.startswith("/usr/lib64/") and "nvidia-ml." not in p
        }
        self.files.update(self.drivers)
        self.allowed = set(self.files)
        self.stats = {p: AU["identity"](p) for p in [*self.files, str(self.exe)]}
        self.keys = {p: AU["reference_key"](p, self.stats[p]) for p in self.files}
        need(
            all(sha(Path(p)) == h for p, h in self.files.items())
            and sha(self.exe) == self.arm["executable_sha256"],
            "current providers",
        )
        self.recheck()

    def recheck(self):
        need(
            SC["ORIGIN"]["kernel"]() == self.kernel
            and all(AU["identity"](p) == v for p, v in self.stats.items()),
            "changed system or ELF",
        )

    def live(self, pid):
        root = Path("/proc", str(pid))
        need((root / "exe").resolve(strict=True) == self.exe, "foreign executable")
        mappings = (root / "maps").read_text()
        if self.loader_cache is not None:
            mappings = self.loader_cache.providers(mappings)
        return AU["check_maps"](mappings, self.allowed, self.keys)

    def audit(self, raw, pid):
        self.recheck()
        path = raw / ("loader." + str(pid))
        need(
            list(raw.glob("loader.*")) == [path] and 0 < path.stat().st_size <= 8 << 20,
            "loader cardinality or size",
        )
        text = path.read_text()
        need(
            all(
                (m := re.match(r"\s*(\d+):", line)) and int(m[1]) == pid
                for line in text.splitlines()
                if line.strip()
            ),
            "foreign loader PID",
        )
        loaded = L["initialized"](text, pid)
        need(self.initial <= loaded <= self.allowed, "late provider or missing initialization")
        requested = SC["ORIGIN"]["all_requests"](text, pid)
        names = set(self.verified["closure"]) | {
            "libnvidia-ptxjitcompiler.so.1",
            "libnvidia-gpucomp.so." + self.kernel["release"],
            "libnvidia-nvvm70.so.4",
            "libnvidia-nvvm.so.4",
        }
        optional = "libnvcuextend.so." + self.kernel["release"]
        need(
            requested <= names | {optional},
            "unexpected late search: " + str(sorted(requested - names)),
        )
        for n in requested & (names - set(self.verified["closure"])):
            need(str((Path("/usr/lib64") / n).resolve(strict=True)) in loaded, "unserved " + n)
        return dict(
            loader_sha256=sha(path),
            requests=sorted(requested),
            initialized={Path(p).name: self.files[p] for p in sorted(loaded)},
        )


def capture(a, out, rec):
    auth = Current(a.static)
    need(
        re.fullmatch("tesy-sys73-c270-[a-z0-9-]+", a.unit)
        and prepare.git(REPO, "rev-parse", "HEAD") == a.commit
        and not prepare.git(REPO, "status", "--porcelain"),
        "fresh unit or clean revision",
    )
    need(
        sha(R0 / "prepare.py") == PF["PREPARE"] and sha(R0 / "measure.py") == PF["MEASURE"],
        "historical gates",
    )
    locks = SC["OLD"]["locks"](REPO)
    old = locks[SC["OLD"]["Q"] + "nvme_r0_gate/inputs/receipt.json"]
    sealed = {k: v for k, v in old.items() if k not in ("status", "model_forwards")}
    p = locks[SC["OLD"]["C270"]]
    source = p["runs"][0]
    exe, model, ids = map(Path, source["command"][:3])
    backend = Path(p["backend_root"]).resolve(strict=True)
    ref = Path(source["post_run_command"][-1])
    gomp = {p: h for p, h in auth.files.items() if Path(p).name.startswith("libgomp.")}
    need(
        len(gomp) == 1
        and exe.resolve(strict=True) == auth.exe
        and sha(ids) == sealed["ids_sha256"]
        and prepare.tree_digest(ref) == sealed["gold"]
        and prepare.git(backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [sealed["backend_commit"], sealed["backend_tree"]]
        and not prepare.git(backend, "status", "--porcelain"),
        "numerical inputs, reference or backend",
    )
    win = read(a.window / "receipt.json")
    first = json.loads((a.window / "samples.jsonl").read_text().splitlines()[0])["utc"]
    need(
        sha(a.window / "receipt.json") == a.window_sha256
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and win["gpu_driver"] == auth.kernel["release"]
        and datetime.fromisoformat(first).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "numeric-protocol.md")),
        "C55 chronology, samples or driver",
    )
    a.envelope, a.measurement_commit = "E20_R0", a.commit
    prepare.freeze(a, out, sealed, (exe, model, ids, backend, ref, gomp))
    spec, base = read(out / "argv.json"), read(out / "protocol.json")
    actual = {
        Path(v["file"]).name: v["sha256"]
        for k, v in auth.verified["closure"].items()
        if k != SC["OLD"]["LOADER"].name
    }
    before = dict(sealed["startup_dso_sha256"])
    del before["libcuda.so.620.70.06"]
    need(
        actual == before | {"libcuda.so." + auth.kernel["release"]: SC["SYS"]["DRIVER"]},
        "unexpected numerical closure delta",
    )
    pinned = sealed | dict(startup_dso_sha256=actual)
    protocol = base | dict(
        schema="tesy-system-driver-c270-v1",
        pinned=pinned,
        static_sha256=STATIC,
        historical_protocol_sha256=sha(out / "protocol.json"),
    )
    cfg = out / "current-protocol.json"
    save(cfg, protocol)
    raw = out / "raw"
    child = dict(LD_LIBRARY_PATH=auth.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader"))
    cmd = PF["qualified_command"](spec["monitor"], Path("/usr/lib64"), child)
    cmd[cmd.index("--resource-protocol") + 1] = str(cfg)
    save(out / "current-argv.json", cmd)
    rec.update(
        commit=a.commit,
        tree=prepare.git(HERE, "rev-parse", "HEAD^{tree}"),
        unit=a.unit,
        protocol_sha256=sha(cfg),
        argv_sha256=sha(out / "current-argv.json"),
        static_sha256=STATIC,
        window_sha256=a.window_sha256,
        model_sha256=pinned["model_sha256"],
        kernel=auth.kernel,
    )
    rec["monitor_provider"] = AU["Authority"].monitor_proof(auth.monitor)
    ident, count, seen, wall = PF["guarded_run"](cmd, out, a.unit, auth, measure, run_bounded)
    mon = read(raw / (a.unit + ".json"))
    need(
        mon["process_identity"]
        == read(raw / (a.unit + ".launch.json"))["process_identity"]
        == ident
        and sha(cfg) == mon["limits"]["resource_protocol_sha256"],
        "identity at launch",
    )
    expected = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | child
    PF["check_native_manifest"](mon, protocol, pinned, expected, measure)
    audit = auth.audit(raw, ident["pid"])
    need({Path(p).name for p in seen} <= audit["initialized"].keys(), "loaded/VMA discrepancy")
    rec.update(
        loader=audit,
        samples_live=count,
        monitor_elapsed_s=mon["elapsed_s"],
        maxima=mon["maxima"],
        start_inventory=mon.get("start_inventory"),
        wall_scoped_s=wall,
        monitor_reason=mon["stop_reason"],
        native_inputs_sha256=sealed["ids_sha256"],
        gomp=gomp,
    )
    with (out / "gate.log").open("xb") as log:
        subprocess.run(spec["check"], stdout=log, stderr=subprocess.STDOUT, timeout=45, check=True)
    grade = read(out / "selected.json")
    measure.check_gate(grade)
    rec.update(
        status="GO_C269_CURRENT_C127",
        selected_sha256=sha(out / "selected.json"),
        core_payloads=grade["core_payloads"],
        full_logits=grade["full_logits"],
        combinations=grade["prospective_witness"]["combinations"],
        components=grade["prospective_witness"]["components"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("window", "placement", "static", "new-output-dir"):
        parser.add_argument("--" + k, required=True, type=Path)
    for k in ("unit", "commit", "window-sha256"):
        parser.add_argument("--" + k, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.new_output_dir.resolve()
    out.mkdir()
    rec = dict(status="FAIL_PRESERVED", generation_requests=0, energy_J=None)
    try:
        with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            capture(args, out, rec)
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    rec["model_starts"] = int((out / "raw" / (args.unit + ".launch.json")).is_file())
    rec["raw_sha256"] = {
        str(f.relative_to(out)): sha(f) for f in sorted(out.rglob("*")) if f.is_file()
    }
    save(out / "receipt.json", rec)
    print(rec["status"], rec.get("error", ""))
    raise SystemExit(rec["status"] == "FAIL_PRESERVED")
