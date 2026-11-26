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
    layer = a.study == "layer"
    range_reads = a.study != "scratch"
    ref_sha = G["LAYER_REFERENCE"] if layer else G["REFERENCE"]
    ref = load(a.reference, ref_sha)
    protocol = (
        HERE
        / {"scratch": "protocol.md", "pread": "read-protocol.md", "layer": "layer-protocol.md"}[
            a.study
        ]
    )
    need(
        bool(a.previous) == range_reads and bool(a.gate_reference) == layer, "previous study inputs"
    )
    if layer:
        diagnostic_hash = "859f7566ceb2e61886ef238dae0ae0bc20531aba59fea92a0978664b9966cc2c"
        diagnostic = load(a.cache_diagnostic, diagnostic_hash)
        need(
            diagnostic["status"] == "DIAGNOSTIC_ONLY"
            and diagnostic["admits_new_family"]
            and diagnostic["reference_sha256"] == ref_sha
            and diagnostic["stat"] == ref["model_stat"],
            "cache preparation diagnostic",
        )
        old_hash = "5e352cfbcc56e1e7978e798384e9a8f1c7d18a366ab81e787540e3d2937d27a3"
        old = G["reopen"](a.previous, old_hash, a.gate_reference)
        need(
            old["decision"] == "GO" and ref["gate_reference_sha256"] == G["REFERENCE"],
            "single gate was not admitted",
        )
    elif range_reads:
        old_hash = "232be642acd7b72e7ef50f86753410b33ac36d44304120e8548e59748aa60f97"
        old = G["reopen"](a.previous, old_hash, a.reference)
        need(old["decision"] == "NO_GO", "previous cold service")
    model = Path(ref["model"])
    w = load(a.c55, a.c55_sha256)
    cap = (4 << 30) if layer else D["CAP"]
    stop = (3584 << 20) if layer else D["STOP"]
    policy, end = D["c55"](a, cap_bytes=cap)
    observed = json.loads((a.c55.parent / "samples.jsonl").read_text().splitlines()[0])["utc"]
    frozen = int(
        subprocess.check_output(
            [
                "git",
                "-C",
                HERE,
                "log",
                "-1",
                "--format=%ct",
                "--",
                protocol.name,
                *(["layer-diagnostic.md"] if layer else []),
            ],
            text=True,
        )
    )
    stat = IO.stat_id(model)
    need(
        pair["status"] == "PASS_CALLBACK_OFF_TWO_CUTS"
        and ref["status"] == ("SEALED_LAYER_BYTES" if layer else "SEALED_GATE_BYTES")
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
        study=a.study,
        reference_sha256=ref_sha,
        scope_cap_B=cap,
        scope_stop_B=stop,
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
                protocol,
            )
        },
        monitor_source_sha256=sha(HERE.parent / "device/run.py"),
    )
    if range_reads:
        r["authority"]["previous_sha256"] = old_hash
    if layer:
        r["authority"]["sources"]["layer_plan.py"] = sha(HERE / "layer_plan.py")
        r["authority"]["sources"]["layer-diagnostic.md"] = sha(HERE / "layer-diagnostic.md")
        r["authority"]["cache_diagnostic_sha256"] = diagnostic_hash
        r["authority"]["cold_eviction_alignment_B"] = 2 << 20
    if not a.execute:
        r["status"] = "PREPARED_ONLY"
        return
    pre = load(a.prepared, a.prepared_sha256)
    need(
        pre["status"] == "PREPARED_ONLY" and pre["authority"] == r["authority"], "preflight changed"
    )
    r["prepared_sha256"] = a.prepared_sha256
    IO.CAP, IO.STOPS = cap, stop
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
    sequence = G["SEQUENCES"][a.study]
    for order, modes in sequence.items():
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
            cap_bytes=cap,
        )
        arm["measurements"] = {
            m: G["one"](native / (m + ".json"), m, ref, late_cut=range_reads) for m in modes
        }
        orders[order] = arm["measurements"]
    unchanged()
    IO.scope()
    need(
        IO.stat_id(model) == stat
        and all(IO.stat_id(Path(p)) == v["stat"] for p, v in paths.items()),
        "model or provider drift",
    )
    if layer:
        r["decision"], r["pairs"] = G["decide"](
            orders, "DIRECT", "PREAD_RANDOM", minimum_bytes_saved=1
        )
    elif range_reads:
        r["contrasts"] = G["read_contrasts"](orders)
        primary = r["contrasts"]["DIRECT_to_PREAD_RANDOM"]
        r["decision"], r["pairs"] = primary["decision"], primary["pairs"]
    else:
        r["decision"], r["pairs"] = G["decide"](orders)
    r["status"] = G["STATUS"][a.study]


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
    parser.add_argument("--study", choices=G["SEQUENCES"], default="scratch")
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--gate-reference", type=Path)
    parser.add_argument("--cache-diagnostic", type=Path)
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
                    and result["memory_peak_B"] < IO.STOPS,
                    "final resource state",
                )
            except Exception as exc:
                result.update(status="FAIL_PRESERVED", final_error=str(exc))
        save(dest / "receipt.json", result)
    print(result["status"], result.get("reason", ""), result.get("final_error", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
