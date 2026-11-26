"""Admit one ALIAS graph using the existing C55/C118 and shape-one validator."""

import argparse
import hashlib
import json
import os
import signal
import struct
import sys
import threading
import time
from copy import copy
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
support = run_path(HERE / "build.py")
ROOT, QUAL, DECODE = (support[n] for n in ("ROOT", "QUAL", "DECODE"))
need, sha = support["check"], support["sha"]
support["sealed"](DECODE / "profile.py", support["PROFILE"])
old = run_path(DECODE / "profile.py")
PASS = "PASS_CPU0_E28_PROJECTION_REFERENCE"
X = "f4b7b1fc1595244c263e292a8cd2d6c1d3c939e00b56e151c5c5d48fc403092e"
WEIGHT = "3a76d368a4c215dafd9d39e740d1db137709d8bac6df70084c918656ec31cc50"


def verify_projection(folder, row):
    proof = json.loads((folder / "gate.json").read_bytes())
    expected = dict(
        status="PASS_CPU0_E28_GATE_AND_SINGLE_RANK",
        source="original_gate_mmid_before_add_id",
        shape=[2880, 4, 1, 1],
        positions=1,
        rank=0,
        expert=28,
        slot=3,
        generation=6,
        gate_observations=1,
        bias_edges=1,
        finite_values=2880,
        unequal_single=0,
        x_sha256=X,
        weight_sha256=WEIGHT,
    )
    for key, value in expected.items():
        need(type(proof.get(key)) is type(value) and proof[key] == value, "projection field " + key)
    for tag in ("cpu", "base"):
        need(
            Path(proof["provider_" + tag]).samefile(row["providers"][tag]),
            "live projection provider",
        )
    data = {}
    for name, key, size in (
        ("gate-rank0.f32", "gate_sha256", 11520),
        ("single-rank0.f32", "single_sha256", 11520),
        ("activation.q8", "q8_sha256", 3060),
    ):
        path = folder / name
        need(
            path.is_file() and not path.is_symlink() and path.stat().st_size == size,
            "projection size " + name,
        )
        data[name] = path.read_bytes()
        need(hashlib.sha256(data[name]).hexdigest() == proof[key], "projection digest " + name)
    need(set(p.name for p in folder.iterdir()) == {"gate.json", *data}, "projection outputs")
    need(data["gate-rank0.f32"] == data["single-rank0.f32"], "independent bitwise comparison")
    need(
        all(
            (u & 0x7F800000) != 0x7F800000
            for (u,) in struct.iter_unpack("<I", data["gate-rank0.f32"])
        ),
        "nonfinite row",
    )
    return proof


def run(a, r):
    policy = old["prior_policy"]
    prior, svc = policy["shared"]()
    svc.WALL = 360
    a.checkout = ROOT
    a.input_sha256 = policy["PREP"]
    old_args = copy(a)
    old_args.build_dir = a.old_build
    old_args.build_sha256 = support["OLD"]
    _, env, identity = old["authority"](old_args, prior, svc)
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_CPU0_E28_PROJECTION_BUILD"
        and build["commit"] == a.commit
        and build["old_build_sha256"] == support["OLD"]
        and build["libs"] == prior.LIBS
        and build["crypto_sha256"] == policy["CRYPTO"],
        "new build authority",
    )
    for name in ("native.cpp", "build.py", "protocol.md"):
        need(
            svc.frozen(ROOT, HERE / name, a.commit) == build["source_sha256"][name],
            "frozen new source " + name,
        )
    exe = a.build_dir / "decode-layer"
    prior.sealed_file(exe, build["executables"][exe.name])
    r.update(
        commit=a.commit,
        original=identity,
        build_sha256=a.build_sha256,
        executable_sha256=build["executables"][exe.name],
        protocol_sha256=build["source_sha256"]["protocol.md"],
        supervisor_sha256=svc.frozen(ROOT, HERE / "profile.py", a.commit),
        c55_sha256=a.c55_sha256,
    )
    sys.path.insert(0, str(ROOT / "tools"))
    import run_bounded as bounded

    cg = bounded.cgroup_state()
    need(
        cg
        and cg["path"].endswith("/" + a.unit + ".scope")
        and cg["memory_max"] == cg["memory_high"] == svc.CAP
        and cg["swap_max"] == cg["swap_current"] == 0
        and cg["memory_peak"] < svc.STOP,
        "bounded scope",
    )
    window = run_path(QUAL / "nvme_admission/window.py")
    gate = prior.sealed_json(a.c55_receipt, a.c55_sha256)
    frozen = prior.sealed_json(
        a.c55_receipt.with_name("resource-policy.json"), gate["canonical_policy_sha256"]
    )
    need(gate["status"] == "PASS_RESOURCE_WINDOW_ONLY" and not gate["reason"], "C55 rejected")
    policy["live_admission"](frozen, window)
    r["monitor_provider"], check_provider = svc.monitor_provider(prior)
    used, check_files, gold, packid = old["inputs"](a, prior, r)
    arm = r["arm"] = {"mode": "ALIAS", "child_started": False}
    folder = a.new_output_dir / "ALIAS"
    folder.mkdir()
    (folder / "raw").mkdir()
    check_provider()
    check_files()
    guard, policy_data, bound, cgpath = svc.admit(a, prior, QUAL / "packed_real_layer", arm, folder)
    monitor = policy["with_live_admission"](svc.Monitor, frozen, window)(
        guard,
        policy_data,
        bound,
        cgpath,
        folder / "raw/samples.jsonl",
        r["_tic"],
        elapsed_limit=360,
    )
    thread = threading.Thread(target=monitor.run, daemon=True)
    thread.start()
    try:
        row = old["child"](a, "ALIAS", folder, arm, exe, env, monitor, prior, used)
        arm["full_ffn"] = old["verify"](row, "ALIAS", folder / "native", gold, packid, a, prior)
        arm["native"] = row
        arm["projection"] = verify_projection(folder / "projection", row)
    finally:
        monitor.end.set()
        thread.join(timeout=6)
        need(not thread.is_alive(), "monitor joined")
        monitor.check()
    check_files()
    check_provider()
    need((cgpath / "cgroup.procs").read_text().split() == [str(os.getpid())], "children reaped")
    need(prior.footprint(a.new_output_dir) + 65536 < old["MAX_OUT"], "output cap")
    arm.update(samples=monitor.count, monitor_sha256=sha(folder / "raw/samples.jsonl"))
    r.update(
        status=PASS,
        final_cgroup=bounded.cgroup_state(),
        logical_read_upper_bytes=used + arm["rchar_bytes"],
        full_model_forwards=0,
        gpu_compute=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "old-build",
        "build-dir",
        "input-dir",
        "reference-dir",
        "placement-receipt",
        "prestate-receipt",
        "libs",
        "c55-receipt",
        "new-output-dir",
    ):
        parser.add_argument("--" + key, type=lambda s: Path(s).resolve(), required=True)
    for key in ("commit", "unit", "build-sha256", "c55-sha256"):
        parser.add_argument("--" + key, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    report = {"status": "FAIL_PRESERVED", "_tic": time.monotonic()}

    def deadline(*_):
        raise TimeoutError("scope deadline")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(360)
    try:
        run(a, report)
    except Exception as exc:
        report.update(status="FAIL_PRESERVED", reason=repr(exc))
    finally:
        signal.alarm(0)
        report["elapsed_s"] = time.monotonic() - report.pop("_tic")
        (a.new_output_dir / "receipt.json").write_text(
            json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
        )
    print(report["status"], report.get("reason", ""))
    raise SystemExit(report["status"] != PASS)
