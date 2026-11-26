"""Admit a two-order cold RTX transfer family using the frozen C110 providers and C55/C118."""

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
P = run_path(str(HERE / "plan.py"))
G = run_path(str(HERE / "grade.py"))
D = P["A"]["TINY"]["D"]
IO, need, sha, load, save = (D[k] for k in ("IO", "need", "sha", "load", "save"))


def run(a, out, r):
    commit, tree = subprocess.check_output(
        ["git", "-C", HERE, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).splitlines()
    need(
        commit == a.commit
        and not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]),
        "changed freeze",
    )
    require_pre = bool(a.prepared and a.prepared_sha256)
    need(require_pre == a.execute, "preflight identity")
    pair = load(a.family / "receipt.json", P["PAIR"])
    prior = pair["authority"]
    ref = load(a.reference, G["REFERENCE"])
    model = Path(ref["model"])
    w = load(a.c55, a.c55_sha256)
    policy, end = D["c55"](a)
    observed = json.loads((a.c55.parent / "samples.jsonl").read_text().splitlines()[0])["utc"]
    frozen = int(
        subprocess.check_output(
            ["git", "-C", HERE, "log", "-1", "--format=%ct", "--", "protocol.md"], text=True
        )
    )
    stat = IO.stat_id(model)
    need(
        pair["status"] == "PASS_CALLBACK_OFF_TWO_CUTS"
        and ref["status"] == "SEALED_GATE_BYTES"
        and ref["pair_sha256"] == P["PAIR"]
        and ref["model_sha256"] == prior["model_sha256"]
        and ref["model_stat"] == w["selected_stat"] == prior["model_stat"] == stat
        and w["gpu_driver"] == "620.73.04"
        and w["model_fs"] == "btrfs"
        and IO.disk(model, "nvme") == Path("/sys/class/block/nvme0n1/stat")
        and datetime.fromisoformat(observed).timestamp() >= frozen,
        "model, host, disk or C55",
    )
    paths = {
        p: v
        for p, v in prior["providers"].items()
        if Path(p).name.startswith(("libnvidia-", "libcuda.", "libcudart.", "nvidia-smi"))
    }
    for p, v in paths.items():
        need(IO.stat_id(Path(p)) == v["stat"] and sha(Path(p)) == v["sha256"], "changed provider")
    (runtime,) = [p for p in paths if Path(p).name.startswith("libcudart.")]
    (driver,) = [p for p in paths if Path(p).name.startswith("libcuda.")]
    monitor, unchanged = run_path(str(D["QUAL"] / "packed_layer_service/profile.py"))[
        "monitor_provider"
    ](SimpleNamespace(token=IO.stat_id))
    need(monitor == prior["monitor"] and monitor["mode"] == "SYSTEM_NVML", "monitor")
    exe = HERE / "transfer.py"
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        CUDA_VISIBLE_DEVICES="0",
        CUDA_CACHE_DISABLE="1",
        TESY_CUDART=runtime,
    )
    r["authority"] = dict(
        commit=commit,
        tree=tree,
        reference_sha256=G["REFERENCE"],
        pair_sha256=P["PAIR"],
        c55_sha256=a.c55_sha256,
        monitor=monitor,
        providers=paths,
        environment=env,
        python_sha256=sha(Path("/usr/bin/python3").resolve()),
        model_stat=stat,
        sources={
            p.name: sha(p)
            for p in (
                exe,
                HERE / "protocol.md",
                HERE / "plan.py",
                HERE / "run.py",
                HERE / "grade.py",
            )
        },
        monitor_source_sha256=sha(HERE.parent / "device/run.py"),
    )
    if not a.execute:
        r["status"] = "PREPARED_ONLY"
        return
    pre = load(a.prepared, a.prepared_sha256)
    need(
        pre["status"] == "PREPARED_ONLY" and pre["authority"] == r["authority"], "preflight changed"
    )
    r["prepared_sha256"] = a.prepared_sha256
    IO.CAP, IO.STOPS = D["CAP"], D["STOP"]
    IO.scope()
    cg = Path("/sys/fs/cgroup") / IO.cgroup_state()["path"].lstrip("/")
    need(
        a.unit.startswith("tesy-ik-cold-gate-")
        and cg.name == a.unit + ".scope"
        and cg.parent.name == "app.slice"
        and (cg / "cgroup.procs").read_text().split() == [str(os.getpid())],
        "scope ownership",
    )
    drivers = {p for p in paths if "libnvidia-" in p and "nvidia-ml" not in p}
    orders = {}
    for order, modes in G["ORDERS"].items():
        unchanged()
        arm = r["arms"][order] = {"starts": 0}
        native = D["sample_arm"](
            order,
            out,
            a,
            policy,
            end,
            exe,
            a.reference.resolve(),
            env,
            {runtime, driver},
            drivers,
            arm,
        )
        arm["measurements"] = {m: G["one"](native / (m + ".json"), m, ref) for m in modes}
        orders[order] = arm["measurements"]
    unchanged()
    IO.scope()
    need(
        IO.stat_id(model) == stat
        and all(IO.stat_id(Path(p)) == v["stat"] for p, v in paths.items()),
        "model or provider drift",
    )
    r["decision"], r["pairs"] = G["decide"](orders)
    r["status"] = "MEASURED_COLD_GATE_TRANSFER"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("reference", "family", "c55", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    for k in ("commit", "c55-sha256"):
        parser.add_argument("--" + k, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--prepared-sha256")
    parser.add_argument("--unit", default="")
    args = parser.parse_args()
    os.umask(0o077)
    dest = args.new_output_dir.resolve()
    dest.mkdir(mode=0o700)
    result = dict(status="FAIL_PRESERVED", arms={}, model_forwards=0, requests=0, energy_J=None)
    try:
        run(args, dest, result)
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        if args.execute:
            try:
                state = IO.cgroup_state()
                scope = Path("/sys/fs/cgroup") / state["path"].lstrip("/")
                result.update(
                    memory_peak_B=state["memory_peak"],
                    swap_peak_B=int((scope / "memory.swap.peak").read_text()),
                    events=state["events_local"],
                    raw_sha256={
                        str(p.relative_to(dest)): sha(p) for p in dest.rglob("*") if p.is_file()
                    },
                )
                need(
                    scope.name == args.unit + ".scope"
                    and not result["swap_peak_B"]
                    and not any(result["events"][k] for k in ("high", "max", "oom", "oom_kill"))
                    and result["memory_peak_B"] < D["STOP"],
                    "final resource state",
                )
            except Exception as exc:
                result.update(status="FAIL_PRESERVED", final_error=str(exc))
        save(dest / "receipt.json", result)
    print(result["status"], result.get("reason", ""), result.get("final_error", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
