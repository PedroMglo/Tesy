"""Run the C270 real CPU0 handoff with the same C55, C118 and runtime guard as its reference."""

import argparse
import json
import os
import signal
import subprocess
import threading
import time
from copy import copy
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
Q = HERE.parents[1] / "qualification-retake"
S = run_path(Q / "igpu_resident_rank/projection/rank_split/profile.py")
old, parent, need = (S[k] for k in ("old", "parent", "need"))
MODES = ("FULL", "WAIT", "READY")


def grade(row):
    need(
        (row["request_bytes"], row["set_bytes"], row["setup_bytes"])
        == (13221888, 13219200, 4 * 13258752)
        and row["workers_joined"] == row["workers"] == 4
        and row["cpu_threads"] == 8
        and row["order"] == [28, 24, 8, 16]
        and 0 < row["mutant_unequal_ffn"] <= 2880,
        "transfer, routing or fault control",
    )
    need([r["mode"] for r in row["parity"]] == list(MODES) and len(row["trials"]) == 42, "design")
    times = {}
    for gen, r in enumerate(row["parity"] + row["trials"], 1):
        mode = r["mode"]
        a, b, c, d = (r[k] for k in ("read_start", "read_end", "set_start", "set_end"))
        u, v = r["group_start"], r["group_end"]
        need(
            r["start"] <= a < b <= c < d <= r["end"]
            and r["start"] <= u < v <= r["end"]
            and (mode == "READY" or d <= u)
            and r["generation"] == gen
            and 0 <= r["worker"] < 4
            and (r["checked_weighted"], r["checked_ffn"]) == (11520, 2880),
            "service or numerical proof",
        )
        if gen <= 3:
            continue
        block, within = divmod(gen - 4, 21)
        rep, index = divmod(within, 3)
        need(
            (block, rep, MODES[index if block == 0 else 2 - index]) == (r["block"], r["rep"], mode),
            "order of paired triples",
        )
        times[block, rep, mode] = (r["end"] - r["start"], max(0, min(b, v) - max(a, u)))
    blocks = []
    for block in (0, 1):
        elapsed = {k: [times[block, i, k][0] for i in range(7)] for k in MODES}
        diffs = {
            k: [a - b for a, b in zip(elapsed[k], elapsed["READY"], strict=True)] for k in MODES[:2]
        }
        overlap = [times[block, i, "READY"][1] for i in range(7)]
        blocks.append(
            dict(
                block=block,
                elapsed_ns=elapsed,
                paired_saving_ns=diffs,
                median_saving_ns={k: median(v) for k, v in diffs.items()},
                ready_read_group_overlap_ns=overlap,
            )
        )
    favorable = [
        all(x > 0 for x in b["median_saving_ns"].values())
        and median(b["ready_read_group_overlap_ns"]) > 0
        for b in blocks
    ]
    return dict(
        blocks=blocks,
        decision="GO_LOCAL"
        if all(favorable)
        else "INCONCLUSIVE"
        if any(favorable)
        else "NO_GO_LOCAL",
        finite_exact_words_per_arm=14400,
        exact_arms=45,
        mutant_unequal_ffn=row["mutant_unequal_ffn"],
        pack_read_bytes=row["setup_bytes"] + 45 * row["request_bytes"],
        timed_set_bytes=42 * row["set_bytes"],
        storage_bytes=row["storage_bytes"],
    )


def run(a, r):
    p = old["prior_policy"]
    prior, svc = p["shared"]()
    svc.WALL = 360
    a.checkout = parent.ROOT
    ctrl = copy(a)
    ctrl.build_dir, ctrl.build_sha256 = a.old_build, parent.OLD
    _, env, identity = old["authority"](ctrl, prior, svc)
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_READY_LAYER_BUILD"
        and build["commit"] == a.commit
        and build["tree"] == identity["tree"]
        and build["libs"] == prior.LIBS,
        "frozen build",
    )
    exe = a.build_dir / "decode-layer"
    prior.sealed_file(exe, build["executables"]["decode-layer"])
    for name, h in build["source_sha256"].items():
        need(svc.frozen(parent.ROOT, HERE / name, a.commit) == h, "build source " + name)
    weighted = a.rank_dir / "ALIAS/rank/weighted.f32"
    rank = prior.sealed_json(a.rank_dir / "receipt.json", S["RANK_RECEIPT"])
    prior.sealed_file(weighted, rank["arm"]["rank"]["files_sha256"]["weighted.f32"])
    used, check_inputs, _, _ = old["inputs"](a, prior, r)
    r.update(
        commit=a.commit,
        tree=identity["tree"],
        binary_sha256=build["executables"]["decode-layer"],
        build_sha256=a.build_sha256,
        source_sha256=parent.sha(HERE / "physical.py"),
        protocol_sha256=build["source_sha256"]["protocol.md"],
        rank_receipt_sha256=S["RANK_RECEIPT"],
    )
    r["monitor_provider"], check_provider = svc.monitor_provider(prior)
    window = run_path(Q / "nvme_admission/window.py")
    c55 = prior.sealed_json(a.c55_receipt, a.c55_sha256)
    frozen = prior.sealed_json(
        a.c55_receipt.with_name("resource-policy.json"), c55["canonical_policy_sha256"]
    )
    p["live_admission"](frozen, window)
    folder = a.new_output_dir
    (folder / "raw").mkdir()
    check_provider()
    check_inputs()
    guard, policy, bounded, cg = svc.admit(a, prior, Q / "packed_real_layer", r, folder)
    mon = p["with_live_admission"](svc.Monitor, frozen, window)(
        guard, policy, bounded, cg, folder / "raw/samples.jsonl", r["_tic"], elapsed_limit=360
    )
    need(bounded.cgroup_state()["memory_high"] == svc.CAP, "scope high watermark")
    thread = threading.Thread(target=mon.run, daemon=True)
    thread.start()
    try:
        row = old["child"](
            a,
            "LAYER",
            folder,
            r,
            exe,
            dict(env, TESY_READY_WEIGHTED=str(weighted)),
            mon,
            prior,
            used,
        )
        r["result"] = grade(row)
    finally:
        mon.end.set()
        thread.join(timeout=6)
        need(not thread.is_alive(), "monitor joined")
        mon.check()
    check_inputs()
    check_provider()
    need(
        (cg / "cgroup.procs").read_text().split() == [str(os.getpid())]
        and int((cg / "memory.swap.peak").read_text()) == 0
        and bounded.cgroup_state()["memory_peak"] < svc.STOP,
        "worker drain, peak or swap",
    )
    r.update(
        status="MEASURED",
        final_cgroup=bounded.cgroup_state(),
        samples=mon.count,
        monitor_sha256=parent.sha(folder / "raw/samples.jsonl"),
        full_model_requests=0,
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
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    result = {"status": "FAIL_PRESERVED", "_tic": time.monotonic()}

    def expire(*_):
        raise TimeoutError("scope deadline")

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(360)
    try:
        run(args, result)
    except (
        ValueError,
        KeyError,
        OSError,
        RuntimeError,
        AssertionError,
        subprocess.SubprocessError,
    ) as exc:
        result["reason"] = repr(exc)
    finally:
        signal.alarm(0)
        result["elapsed_s"] = time.monotonic() - result.pop("_tic")
        (args.new_output_dir / "receipt.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] != "MEASURED")
