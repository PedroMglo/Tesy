"""Test the private CPU DSO on the sealed C266/C270 monolithic layer client."""

import argparse
import json
import os
import shutil
import statistics
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BUILD = run_path(HERE / "build.py")
ROOT, mm = BUILD["ROOT"], BUILD["mm"]
sha, need = mm.sha, mm.need
Q = ROOT / "research/qualification-retake"
P = run_path(Q / "packed_real_layer/policy/profile.py")
SOURCE = "06e2389074b4997fd460c602dae79a0ccfcef834fc47b590d8e6240928a728ae"
SEAL = "2f96cecf56ab5e949f9385343219d21741532b63ca129f0e7bc531694e6004ec"
EXE = "e002af686851172017d51bdf120d64bf8271be0c6bb6309d2fba226735c9cc56"
INPUT = "2932c529ca695657c789e9569e42f7f44cafa8aa1d165eedb17e60424338b996"
ORDER = ("ORIGINAL", "OFF", "ON")


def read(path):
    return json.loads(path.read_bytes())


def witnesses(a, out):
    manifest = a.archive_part / "manifest.json"
    need(sha(manifest) == SOURCE, "part-202 manifest")
    entries = read(manifest)["files"]

    # The archived client and numerical witnesses are immutable and never executed in place.
    def checked(name):
        p = a.archive_part / name
        seal = entries[name]
        need(
            p.is_file()
            and not p.is_symlink()
            and p.stat().st_size == seal["bytes"]
            and sha(p) == seal["sha256"],
            "part-202 file " + name,
        )
        return p

    prefix = "tesy-c269-dispatch-"
    inputs = a.archive_part / (prefix + "input-20261126-r01")
    prep = checked(inputs.name + "/receipt.json")
    need(sha(prep) == INPUT, "target inputs")
    data = read(prep)
    for name, h in data["input_sha256"].items():
        need(sha(checked(inputs.name + "/" + name)) == h, "genuine tensor")
    pack = Path(data["pack_path"])
    need(P["fd_stat"](pack.stat()) == data["pack_stat"], "sealed internal NVMe pack")
    native = checked(prefix + "build-20261126-r02/fixture")
    exe = out / "layer"
    shutil.copyfile(native, exe)
    exe.chmod(0o700)
    need(sha(exe) == EXE, "monolithic CPU0 native client")
    gold = {}
    for phase in ("exact", "price"):
        base = prefix + phase + "-20261126-r02"
        gold[phase] = read(checked(base + "/1-MONO.json"))
        for kind in ("low", "high"):
            for step in gold[phase][kind]["steps"]:
                if step["audited"]:
                    step["physical_sha256"] = sha(
                        checked(base + "/1-MONO/" + step["saved"] + "/physical")
                    )
    return inputs, data, exe, gold


def verify(native, reference, gold, folder):
    need(
        native["both_managers_joined"]
        and native["arm"] == "MONO"
        and native["phase"] == reference["phase"],
        "manager cleanup and original graph",
    )
    service = 0
    report = {}
    for kind in ("low", "high"):
        graph, expected = native[kind], reference[kind]
        for k in ("schedule_buffer_bytes", "cache_bytes", "nodes", "splits", "fingerprint"):
            need(graph[k] == expected[k], "graph geometry or memory " + k)
        need(graph["splits"] == 1 and len(graph["workers"]) == 4, "CPU workers and placement")
        times = []
        for row, old in zip(graph["steps"], expected["steps"], strict=True):
            for k in ("audited", "io", "state", "saved", "input", "expected_active"):
                need(row[k] == old[k], "conservation " + kind + "/" + k)
            service += row["io"]["returned_bytes"]
            if row["saved"]:
                dest = folder / row["saved"]
                for f in ("ffn", "logits", "biased", "ranks", "mix"):
                    need(
                        sha(dest / f) == gold["input_sha256"][row["input"] + "/" + f], "target " + f
                    )
                if row["audited"]:
                    need(
                        sha(dest / "physical") == old["physical_sha256"]
                        and sha(dest / "masks") == gold["input_sha256"][row["input"] + "/masks"],
                        "all physical bindings and masks",
                    )
            need(row["wall_ns"] > 0, "wall clock")
            times.append(row["wall_ns"])
        report[kind] = times
    return dict(wall_ns=report, returned_bytes=service)


def arm(out, name, role, phase, env, exe, inputs, gold, ref, mon):
    raw = out / name
    command = [exe, inputs, "MONO", phase, raw]
    args = dict(env, TESY_NATIVE_CPU_WAVE=str(int(role == "ON")))
    if phase == "exact" and role != "ORIGINAL":
        args["TESY_WAVE_REPORT"] = "1"
    with (out / (name + ".json")).open("xb") as so, (out / (name + ".log")).open("xb") as se:
        child = subprocess.Popen(command, env=args, stdout=so, stderr=se, start_new_session=True)
        tic = time.monotonic()
        try:
            while child.poll() is None:
                mon.check()
                need(time.monotonic() - tic < 60, "child time")
                try:
                    child.wait(0.1)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            mon.bounded.stop_own_group(child)
    need(child.returncode == 0, "native exit " + name)
    f = out / (name + ".json")
    log = (out / (name + ".log")).read_text()
    row = verify(read(f), ref, gold, raw)
    count = [v for v in log.splitlines() if v.startswith("TESY_CPU_WAVES=")]
    want = (
        ["TESY_CPU_WAVES=" + str(20 if role == "ON" else 0)] if "TESY_WAVE_REPORT" in args else []
    )
    need(count == want, "causal reactivation coverage " + repr(count))
    return dict(name=name, role=role, phase=phase, native_sha256=sha(f), counted=count, **row)


def grade(trials):
    need([r["role"] for r in trials] == list(ORDER + ORDER[::-1]), "mirrored order")
    pairs = []
    for rows in (trials[:3], trials[3:][::-1]):
        low = [statistics.median(r["wall_ns"]["low"][2:]) for r in rows]
        high = [sum(r["wall_ns"]["high"]) for r in rows]
        pairs.append(
            dict(
                low_ns=low,
                diverse_ns=high,
                gain_ns=[v - low[2] for v in low[:2]],
                protected=[100 * high[2] <= 105 * v for v in high[:2]],
            )
        )
    passed = all(min(p["gain_ns"]) >= 1_000_000 and all(p["protected"]) for p in pairs)
    return pairs, "GO_SERVER_NUMERICAL" if passed else "NOT_PROMOTED_LAYER_COST"


def run(a, out, r, start):
    need(
        mm.git(ROOT, "rev-parse", "HEAD") == a.commit and not mm.git(ROOT, "status", "--porcelain"),
        "clean execution tree",
    )
    source = a.build_dir / "receipt.json"
    need(sha(source) == SEAL, "synthetic gate")
    build = read(source)
    need(
        build["status"] == "PASS_NATIVE_WAVE_FIXTURE"
        and all(sha(HERE / k) == v for k, v in build["sources"].items()),
        "qualified build source",
    )
    inputs, gold, exe, reference = witnesses(a, out)
    pack = Path(gold["pack_path"])
    need(sha(a.libs / mm.CPU) == mm.CPU_SHA and sha(a.libs / mm.BASE) == mm.BASE_SHA, "native DSOs")
    provider = {}
    for name in ("ORIGINAL", "AUDIT", "PRICE"):
        d = a.libs if name == "ORIGINAL" else a.build_dir / name
        image = mm.CPU_SHA if name == "ORIGINAL" else build["arms"][name]
        need(sha(d / mm.CPU) == image, "frozen CPU provider")
        env = mm.ENV | dict(
            OMP_NUM_THREADS="8",
            OMP_DYNAMIC="FALSE",
            TESY_CPU_WAVE_SKIP_PARKED="1",
            LD_LIBRARY_PATH=os.pathsep.join(map(str, (d, a.libs))),
            TMPDIR=str(out),
        )
        mm.loader(exe, env, {"libggml-cpu.so.0": d / mm.CPU, "libggml-base.so.0": a.libs / mm.BASE})
        provider[name] = env
    r.update(
        commit=a.commit,
        tree=mm.git(ROOT, "rev-parse", "HEAD^{tree}"),
        build_sha256=SEAL,
        client_sha256=EXE,
        archive_manifest_sha256=SOURCE,
        inputs_sha256=INPUT,
        pack_stat=gold["pack_stat"],
        protocol_sha256=sha(HERE / "protocol.md"),
        arms=[],
    )
    prior, svc = P["shared"]()
    svc.WALL = 360
    a.checkout = ROOT
    r["monitor_provider"], check_provider = svc.monitor_provider(prior)
    window = run_path(Q / "nvme_admission/window.py")
    c55 = prior.sealed_json(a.c55_receipt, a.c55_sha256)
    policy = prior.sealed_json(
        a.c55_receipt.with_name("resource-policy.json"), c55["canonical_policy_sha256"]
    )
    P["live_admission"](policy, window)
    check_provider()
    guard, dynamic, bounded, group = svc.admit(a, prior, Q / "packed_real_layer", r, out)
    mon = P["with_live_admission"](svc.Monitor, policy, window)(
        guard, dynamic, bounded, group, out / "monitor.jsonl", start, elapsed_limit=360
    )
    need(bounded.cgroup_state()["memory_high"] == svc.CAP, "scope cap")
    worker = threading.Thread(target=mon.run, daemon=True)
    worker.start()
    try:
        for phase, roles in (("exact", ORDER), ("price", ORDER + ORDER[::-1])):
            for i, role in enumerate(roles):
                if not r["arms"]:
                    age = (
                        datetime.now(UTC) - datetime.fromisoformat(r["c118"]["last_utc"])
                    ).total_seconds()
                    need(0 <= age <= 3, "fresh C118")
                name = f"{phase}-{i + 1}-{role}"
                image = (
                    "ORIGINAL" if role == "ORIGINAL" else "AUDIT" if phase == "exact" else "PRICE"
                )
                mon.check()
                row = arm(
                    out,
                    name,
                    role,
                    phase,
                    provider[image],
                    exe,
                    inputs,
                    gold,
                    reference[phase],
                    mon,
                )
                r["arms"].append(row)
                need(sum(x["returned_bytes"] for x in r["arms"]) <= 32 << 30, "pack budget")
    finally:
        mon.end.set()
        worker.join(6)
        need(not worker.is_alive(), "monitor drain")
        mon.check()
        r.update(
            samples=mon.count,
            final_cgroup=bounded.cgroup_state(),
            monitor_sha256=sha(out / "monitor.jsonl"),
        )
    check_provider()
    need(
        P["fd_stat"](pack.stat()) == gold["pack_stat"]
        and (group / "cgroup.procs").read_text().split() == [str(os.getpid())]
        and int((group / "memory.swap.peak").read_text()) == 0
        and prior.footprint(out) < 128 << 20,
        "cleanup and resources",
    )
    r["pairs"], r["decision"] = grade(r["arms"][3:])
    r.update(status="MEASURED", gpu_compute=0, full_model_starts=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("build-dir", "archive-part", "libs", "c55-receipt", "new-output-dir"):
        parser.add_argument("--" + key, type=lambda v: Path(v).resolve(), required=True)
    for key in ("commit", "unit", "c55-sha256"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.new_output_dir
    out.mkdir()
    rec = {"status": "FAIL_PRESERVED"}
    start = time.monotonic()
    try:
        run(args, out, rec, start)
    except Exception as exc:
        rec.update(reason=str(exc), error_type=type(exc).__name__)
    rec["elapsed_s"] = time.monotonic() - start
    (out / "receipt.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(rec["status"], rec.get("decision", rec.get("reason", "")))
    raise SystemExit(int(rec["status"] != "MEASURED"))
