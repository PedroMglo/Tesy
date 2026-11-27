"""Qualify a CPU provider on the mixed 120B graph with an independent full-state reference."""

import argparse
import array
import json
import math
import os
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
Q = ROOT / "research/qualification-retake"
H = run_path(Q / "packed_nvme_manifest/server_profile/verified_block/server_reserve/family.py")
N, PF, PK, prepare, measure = (H[k] for k in ("N", "PF", "PK", "prepare", "measure"))
AU, live = N["AU"], PK["live"]
need, sha, read, save = H["need"], H["sha"], H["read"], H["save"]
SEALS = {
    169: "0a66a957e8154c2a94b4a7a592b333188477f6eb5245fed75c1c4ccab4de6437",
    173: "e93cfbafd832435c29948186b13ddc7e726529f2efede240e405589bba9bcab8",
    176: "eb4c70ffb238eaf04190ab3b713a73982e6fdf3b3dbd10939f933c680670bc3f",
}
BUILD = "2f96cecf56ab5e949f9385343219d21741532b63ca129f0e7bc531694e6004ec"
LAYER = "5a544db3e987960ff264ce8689072929986000ffc1e50413c5622f166a43f642"
CPU = "libggml-cpu.so.0"
MODES = ("ORIGINAL", "OFF", "ON")


def files(a, out):
    parts = {}
    for number, pin in SEALS.items():
        base = a.archive / f"part-{number}"
        manifest = base / "manifest.json"
        need(sha(manifest) == pin, "archive manifest")
        parts[number] = (base, read(manifest)["files"])

    def checked(number, relative):
        base, rows = parts[number]
        p = base / relative
        row = rows[str(relative)]
        need(
            not p.is_symlink()
            and p.is_file()
            and p.stat().st_size == row["bytes"]
            and sha(p) == row["sha256"],
            "private archive " + str(relative),
        )
        return p

    hist = Path("tesy-pack-reserve-greedy-20261126-r01/HIST1")
    family = read(checked(176, hist / "packed-resource.json"))
    grade = read(checked(176, hist / "grade.json"))
    sub = hist / "raw/tesy-pack-reserve-greedy-20261126-r01-hist1.capture"
    orig = read(checked(176, sub / "native.json"))
    indep = Path(
        "tesy-rollback-greedy-live-20261126-r01/AR/raw/tesy-rollback-greedy-live-20261126-r01-ar.capture"
    )
    names = H["serial_files"]()
    need(set(names) == set(grade["serial_matches"]), "reference file set")
    for f in names:
        need(
            sha(checked(173, indep / f))
            == sha(checked(176, sub / f))
            == grade["serial_matches"][f],
            "reference " + f,
        )
    trial = Path(
        "tesy-target-ffn-three-20261126-r01/CUDA/raw/tesy-target-ffn-three-20261126-r01-cuda.capture"
    )
    inputs = [k for k in parts[169][1] if Path(k).is_relative_to(trial)]
    need(
        inputs
        and set(parts[169][0] / k for k in inputs)
        == {p for p in (parts[169][0] / trial).rglob("*") if p.is_file()},
        "complete target fixture",
    )
    for k in inputs:
        checked(169, k)
    path = Path("tesy-pack-reserve-client-20261126-r01")
    client = read(checked(176, path / "receipt.json"))
    exe = out / "b3-numeric"
    shutil.copyfile(checked(176, path / "b3-numeric"), exe)
    exe.chmod(0o700)
    need(
        sha(exe) == client["elf_sha256"] == family["pinned"]["capture_sha256"],
        "original 120B client",
    )
    return exe, family, grade, orig, parts[169][0] / trial, parts[173][0] / indep


class Provider(PK["Pack"]):
    def __init__(self, a, out, mode, exe, expected_elf, audit):
        constructor = a.archive / "part-52/tesy-pack-manifest-constructor-20261125-r02/receipt.json"
        manifest, meta = live.static.metadata(
            SimpleNamespace(
                derived_dir=a.derived,
                constructor_receipt=constructor,
                derived_sha256=live.DERIVED,
                constructor_sha256=live.CONSTRUCTOR,
            )
        )
        self.mode = "ON"  # pack transport is on for every CPU arm
        self.data_paths = dict(
            model=Path(meta["model_path"]),
            pack=Path(meta["pack_path"]),
            manifest=manifest,
            index=a.derived / "integral-index.json",
        )
        self.data_stats = {k: meta[k + "_stat"] for k in self.data_paths}
        self.pack_seen, self.pack_observations, self.env_checked = 0, set(), False
        path = a.archive / "part-161/tesy-pack-sys73-static-files-20261126-r01"
        N["Current"].__init__(self, path, selection="C270_PACK", capture=(exe, expected_elf))
        closure = self.verified["closure"].copy()
        old = closure[CPU]["file"]
        new = Path(old) if mode == "ORIGINAL" else a.build_dir / "AUDIT" / Path(old).name
        image = closure[CPU]["sha256"] if mode == "ORIGINAL" else audit
        need(sha(new) == image, "numerical CPU identity")
        self.initial.remove(old)
        for table in (self.files, self.stats, self.keys):
            del table[old]
        self.files[str(new)] = image
        self.stats[str(new)] = AU["identity"](new)
        self.keys[str(new)] = AU["reference_key"](str(new), self.stats[str(new)])
        self.initial.add(str(new))
        self.allowed = set(self.files)
        closure[CPU] = dict(file=str(new), sha256=image)
        self.verified = self.verified | dict(closure=closure)
        overlay = out / "providers"
        overlay.mkdir()
        for k in (CPU, "libllama.so.0"):
            (overlay / k).symlink_to(closure[k]["file"])
        self.search = os.pathsep.join(map(str, (overlay, Path(old).parent)))
        env = H["SC"]["OLD"]["environment"]([overlay, Path(old).parent])
        for label, command in (
            ("list", [H["SC"]["OLD"]["LOADER"], "--list", exe]),
            ("relocate", ["/usr/bin/ldd", "-r", exe]),
        ):
            proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=25)
            log = proc.stdout + proc.stderr
            (out / (label + ".log")).write_text(log)
            actual = H["SC"]["OLD"]["interpret"](log)
            need(
                proc.returncode == 0
                and not re.search("undefined symbol|not found|/stubs/", log)
                and {k: str(p.resolve(strict=True)) for k, p in actual.items()}
                == {k: v["file"] for k, v in closure.items()},
                "native closure " + label,
            )
        self.recheck()


def numerical(cap, grade, original):
    native = read(cap / "native.json")
    need(
        native == original and not native["callback_installed"] and native["single_calls"] == 5,
        "target decisions/service",
    )
    need(
        {p.name for p in cap.iterdir()} == set(grade["serial_matches"]) | {"native.json"},
        "output names",
    )
    for name, h in grade["serial_matches"].items():
        need(sha(cap / name) == h, "numerical divergence " + name)
        if name.endswith(".f32"):
            row = array.array("f")
            row.frombytes((cap / name).read_bytes())
            need(
                row.itemsize == 4 and len(row) == 201088 and all(map(math.isfinite, row)),
                "complete finite logits",
            )
    need(H["RB"]["live_coverage"](cap, "AR") == grade["kv_coverage"], "base and SWA KV coverage")
    return native


def process(a, out, mode, data, build):
    exe, family, grade, original, target, independent = data
    ctl = Provider(a, out, mode, exe, family["pinned"]["capture_sha256"], build["arms"]["AUDIT"])
    unit = a.unit + "-" + mode.lower()
    req = SimpleNamespace(
        window=a.window,
        placement=a.archive / "part-01/placement/r1/receipt.json",
        envelope="E20_R0",
        measurement_commit=a.commit,
        unit=unit,
    )
    pins = read(Q / "nvme_r0_gate/inputs/receipt.json")
    pins = {k: v for k, v in pins.items() if k not in ("status", "model_forwards")}
    spec = read(prepare.BASE)
    old, model, ids = map(Path, spec["runs"][0]["command"][:3])
    backend = Path(spec["backend_root"]).resolve(strict=True)
    packed_backend = Path(
        live.static.historical(
            SimpleNamespace(bin_dir=Path(ctl.verified["closure"]["libllama.so.0"]["file"]).parent)
        )[2]["backend_root"]
    ).resolve(strict=True)
    need(
        model.resolve(strict=True) == ctl.data_paths["model"]
        and sha(ids) == pins["ids_sha256"]
        and prepare.git(packed_backend, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        == [live.static.PIN, live.static.TREE]
        and not prepare.git(packed_backend, "status", "--porcelain"),
        "model, workload and backend pin",
    )
    prepare.freeze(
        req,
        out,
        pins,
        (old, model, ids, backend, independent, family["parallel_runtime"]["libraries_sha256"]),
    )
    raw = out / "raw"
    cap = raw / (unit + ".capture")
    monitor = H["RB"]["P"]["MONITOR"]
    selected = family["pinned"].copy()
    closure = ctl.verified["closure"]
    cpu = closure[CPU]
    selected["numerical_dso_sha256"] = selected["numerical_dso_sha256"] | {
        Path(cpu["file"]).name: cpu["sha256"]
    }
    selected["startup_dso_sha256"] = selected["startup_dso_sha256"] | {
        Path(cpu["file"]).name: cpu["sha256"]
    }
    conf = read(out / "protocol.json") | dict(
        schema="tesy-parked-wave-target-v1",
        pinned=selected,
        scientific_protocol_sha256=sha(HERE / "target.md"),
        runner_sha256=sha(monitor),
        case=mode,
        metadata=family["metadata"],
        output_reserve=1,
    )
    config = out / "wave-resource.json"
    save(config, conf)
    loader = dict(LD_LIBRARY_PATH=ctl.search, LD_DEBUG="libs", LD_DEBUG_OUTPUT=str(raw / "loader"))
    extra = {
        live.STORE_ENV: str(ctl.data_paths["manifest"]),
        "TESY_TEST_OUTPUT_RESERVE": "1",
        "TESY_ROLLBACK_AR": str(cap),
    }
    if mode != "ORIGINAL":
        extra.update(TESY_NATIVE_CPU_WAVE=str(int(mode == "ON")), TESY_WAVE_REPORT="1")
    cmd = PF["qualified_command"](read(out / "argv.json")["monitor"], Path("/usr/lib64"), loader)
    cmd[cmd.index(str(ROOT / "tools/run_bounded.py"))] = str(monitor)
    cmd[cmd.index("LimitFSIZE=8388608")] = "LimitFSIZE=41943040"
    for key, value in (
        ("--backend-root", packed_backend),
        ("--variant", "C291-native-wave-" + mode),
        ("--resource-protocol", config),
    ):
        cmd[cmd.index(key) + 1] = str(value)
    sep = cmd.index("--", cmd.index("--env"))
    need(
        cmd[sep + 1 :] == list(map(str, (old, model, ids, cap, "--ngl", "12"))),
        "original invocation",
    )
    cmd[sep:] = [s for k, v in extra.items() for s in ("--env", k + "=" + v)] + list(
        map(str, ("--", exe, model, ids, target, "AR", cap))
    )
    expected = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | loader | extra
    save(out / "argv-target.json", dict(command=cmd, expected=expected))
    PK["PK"]["age"](read(out / "resource-policy.json"), datetime.now(UTC))
    monitor_proof = AU["Authority"].monitor_proof(ctl.monitor)
    ident, samples, mapped, wall = PF["guarded_run"](cmd, out, unit, ctl, measure, N["run_bounded"])
    m, launch = (read(raw / (unit + s)) for s in (".json", ".launch.json"))
    need(
        m["explicit_env"] == expected
        and m["command"] == cmd[-6:]
        and m["process_identity"] == launch["process_identity"] == ident
        and all(m["relevant_environment"].get(k) == v for k, v in extra.items())
        and m["limits"]["resource_protocol_sha256"]
        == launch["resource_protocol_sha256"]
        == sha(config),
        "process authority",
    )
    standard = {"TESY_CPU_WAVE_SKIP_PARKED": "1"} | loader
    PF["check_native_manifest"](dict(m, explicit_env=standard), conf, selected, standard, measure)
    inv = PK["PK"]["compact"].validate_inventory(
        out, unit, {"native_explicit_env": expected}, launch
    )
    links = ctl.audit(raw, ident["pid"])
    need({Path(p).name for p in mapped} <= links["initialized"].keys(), "loaded providers")
    log = (raw / (unit + ".stderr")).read_text()
    need(re.findall(r"llama_context: n_outputs_max\s*=\s*(\d+)", log) == ["1"], "one server output")
    counts = [int(v) for v in re.findall(r"(?m)^TESY_CPU_WAVES=(\d+)$", log)]
    native = numerical(cap, grade, original)
    fd = live.CaptureAuthority.fd_evidence(ctl)
    result = dict(
        mode=mode,
        counts=counts,
        native=native,
        files=grade["serial_matches"],
        kv=grade["kv_coverage"],
        fd=fd,
        samples=samples,
        scope_s=wall,
        model_s=m["elapsed_s"],
        maxima=m["maxima"],
        loader=links,
        inventory=inv,
        monitor=monitor_proof,
        unit=unit,
        cpu_sha256=cpu["sha256"],
    )
    save(out / "checked.json", result)
    if mode == "ON":
        need(len(counts) == 1, "one process fusion count")
    else:
        need(counts == ([] if mode == "ORIGINAL" else [0]), "control fusion count")
    return result


def run(a, out, r):
    need(
        prepare.git(ROOT, "rev-parse", "HEAD") == a.commit
        and not prepare.git(ROOT, "status", "--porcelain"),
        "clean source",
    )
    need(
        sha(a.build_dir / "receipt.json") == BUILD and sha(a.layer / "receipt.json") == LAYER,
        "build/layer gate seals",
    )
    build = read(a.build_dir / "receipt.json")
    need(read(a.layer / "receipt.json")["decision"] == "GO_SERVER_NUMERICAL", "CPU0 gate")
    win = read(a.window / "receipt.json")
    need(
        sha(a.window / "receipt.json") == a.window_sha256
        and win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not win["reason"]
        and sha(a.window / "samples.jsonl") == win["window_sha256"],
        "C55",
    )
    first = json.loads((a.window / "samples.jsonl").read_bytes().splitlines()[0])["utc"]
    need(
        datetime.fromisoformat(first).timestamp()
        >= int(prepare.git(HERE, "log", "-1", "--format=%ct", "--", "target.md")),
        "C55 after protocol",
    )
    data = files(a, out)
    r.update(
        commit=a.commit,
        tree=prepare.git(ROOT, "rev-parse", "HEAD^{tree}"),
        protocol=sha(HERE / "target.md"),
        layer_sha256=LAYER,
        build_sha256=BUILD,
        window_sha256=a.window_sha256,
        archive_manifests=SEALS,
        arms=[],
    )
    for mode in MODES:
        r["stage"] = mode
        folder = out / mode
        folder.mkdir()
        result = process(a, folder, mode, data, build)
        r["arms"].append(
            {
                k: v
                for k, v in result.items()
                if k not in ("files", "kv", "loader", "monitor", "inventory")
            }
        )
    active = r["arms"][-1]["counts"][0]
    r.update(
        status="MEASURED", decision="GO_NATURAL_CLIENT" if active else "INCONCLUSIVE_ZERO_FUSIONS"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "build-dir", "layer", "window", "derived", "new-output-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    for k in ("commit", "unit", "window-sha256"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    need(re.fullmatch(r"tesy-native-wave-target-[a-z0-9-]+", a.unit), "unit identity")
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    result = {"status": "FAIL_PRESERVED"}
    start = time.monotonic()
    try:
        run(a, out, result)
    except Exception as exc:
        result.update(reason=str(exc), error_type=type(exc).__name__)
    result["elapsed_s"] = time.monotonic() - start
    save(out / "receipt.json", result)
    print(result["status"], result.get("decision", result.get("reason", "")))
    raise SystemExit(int(result["status"] != "MEASURED"))
