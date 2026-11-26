"""Guard the resident CPU0 rank-split geometry and conditional timing in one C118."""

import argparse
import json
import os
import signal
import sys
import threading
import time
from copy import copy
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
recipe = run_path(HERE / "build.py")
parent = recipe["parent"]
ROOT, QUAL = parent.ROOT, parent.QUAL
need = parent.check
previous = parent.sealed(
    HERE.parent / "cpu/profile.py",
    "0ab5c7a4120553f4a7dabf08aa72885004495896c1b56a9db8bb9d36bfa0720c",
)
old = run_path(previous)["old"]
PASS = "PASS_RESIDENT_RANK_SPLIT_EXACT_TIMINGS"
RANK_RECEIPT = "3ef107129e6d4c7afb755ac5836c9099b37a37f3eb3ab87f25fed3e9ba28dd53"


def run(a, r):
    p = old["prior_policy"]
    prior, svc = p["shared"]()
    svc.WALL = 360
    a.checkout = ROOT
    a.input_sha256 = p["PREP"]
    ctrl = copy(a)
    ctrl.build_dir = a.old_build
    ctrl.build_sha256 = parent.OLD
    _, env, identity = old["authority"](ctrl, prior, svc)
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_RANK_SPLIT_CPU_BUILD"
        and build["commit"] == a.commit
        and build["old_build_sha256"] == parent.OLD
        and build["recipe_sha256"] == recipe["BASE_HASH"]
        and build["libs"] == prior.LIBS
        and build["crypto_sha256"] == p["CRYPTO"],
        "rank build",
    )
    for name in recipe["FILES"]:
        need(
            svc.frozen(ROOT, HERE / name, a.commit) == build["source_sha256"][name],
            "frozen " + name,
        )
    exe = a.build_dir / "decode-layer"
    prior.sealed_file(exe, build["executables"][exe.name])
    frozen_helpers = {n: svc.frozen(ROOT, HERE / n, a.commit) for n in ("profile.py", "grade.py")}
    r.update(
        commit=a.commit,
        original=identity,
        build_sha256=a.build_sha256,
        programs=frozen_helpers,
        binary_sha256=build["executables"][exe.name],
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
        "bounded family",
    )
    ref = prior.sealed_json(a.rank_dir / "receipt.json", RANK_RECEIPT)
    need(ref["status"] == "PASS_CPU0_RANK_STAGES_REFERENCE", "four-rank CPU reference")
    weight_file = a.rank_dir / "ALIAS/rank/weighted.f32"
    digest = ref["arm"]["rank"]["files_sha256"]["weighted.f32"]
    prior.sealed_file(weight_file, digest)
    weights = weight_file.read_bytes()
    need(len(weights) == 46080 and parent.sha(weight_file) == digest, "weighted reference")
    env = dict(env, TESY_SPLIT_WEIGHTED=str(weight_file))
    r.update(weighted_sha256=digest, rank_receipt_sha256=RANK_RECEIPT)
    review = run_path(HERE / "grade.py")["grade"]
    window = run_path(QUAL / "nvme_admission/window.py")
    c55 = prior.sealed_json(a.c55_receipt, a.c55_sha256)
    frozen = prior.sealed_json(
        a.c55_receipt.with_name("resource-policy.json"), c55["canonical_policy_sha256"]
    )
    need(c55["status"] == "PASS_RESOURCE_WINDOW_ONLY" and not c55["reason"], "C55")
    p["live_admission"](frozen, window)
    r["monitor_provider"], check_provider = svc.monitor_provider(prior)
    used, check_files, gold, pack_id = old["inputs"](a, prior, r)
    arm = r["arm"] = {"mode": "ALIAS", "child_started": False}
    folder = a.new_output_dir / "ALIAS"
    folder.mkdir()
    (folder / "raw").mkdir()
    check_provider()
    check_files()
    guard, policy, bound, cgpath = svc.admit(a, prior, QUAL / "packed_real_layer", arm, folder)
    monitor = p["with_live_admission"](svc.Monitor, frozen, window)(
        guard, policy, bound, cgpath, folder / "raw/samples.jsonl", r["_tic"], elapsed_limit=360
    )
    thread = threading.Thread(target=monitor.run, daemon=True)
    thread.start()
    try:
        row = old["child"](a, "ALIAS", folder, arm, exe, env, monitor, prior, used)
        arm["native"] = row
        arm["full_ffn"] = old["verify"](row, "ALIAS", folder / "native", gold, pack_id, a, prior)
        output = folder / "split.json"
        need(
            output.is_file() and not output.is_symlink() and output.stat().st_size < 65536,
            "split report",
        )
        arm["split"] = review(json.loads(output.read_bytes()), weights, gold)
        arm["split_sha256"] = parent.sha(output)
    finally:
        monitor.end.set()
        thread.join(timeout=6)
        need(not thread.is_alive(), "monitor joined")
        monitor.check()
    check_files()
    check_provider()
    need((cgpath / "cgroup.procs").read_text().split() == [str(os.getpid())], "child cleanup")
    need(prior.footprint(a.new_output_dir) + 65536 < old["MAX_OUT"], "output cap")
    arm.update(samples=monitor.count, monitor_sha256=parent.sha(folder / "raw/samples.jsonl"))
    r.update(
        status=arm["split"]["status"],
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
        "rank-dir",
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
    r = {"status": "FAIL_PRESERVED", "_tic": time.monotonic()}

    def deadline(*_):
        raise TimeoutError("scope deadline")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(360)
    try:
        run(a, r)
    except Exception as e:
        r.update(status="FAIL_PRESERVED", reason=repr(e))
    finally:
        signal.alarm(0)
        r["elapsed_s"] = time.monotonic() - r.pop("_tic")
        (a.new_output_dir / "receipt.json").write_text(
            json.dumps(r, sort_keys=True, indent=2, allow_nan=False) + "\n"
        )
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] not in (PASS, "NO_GO_CROSS_SHAPE_EXACTNESS"))
