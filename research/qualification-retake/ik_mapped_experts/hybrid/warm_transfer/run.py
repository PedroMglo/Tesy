"""Admit two inverse-order hot transfer processes using the closed tiny fixture supervisor."""

import argparse
import os
import subprocess
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
TINY = run_path(str(HERE.parent / "device/run.py"))
BUILD = run_path(str(HERE / "build.py"))
GRADE = run_path(str(HERE / "grade.py"))
need, load, sha, save, IO = (TINY[k] for k in ("need", "load", "sha", "save", "IO"))
MODES = ("FILE_FIRST", "ANON_FIRST")


def seal(a, pre):
    tiny = load(a.tiny_family, a.tiny_sha256)
    need(
        tiny["status"] == "PASS_TINY_HYBRID_GPU_FIXTURE"
        and tiny["dso_sha256"] == a.dso_sha256
        and tiny["swap_peak_bytes"] == 0
        and set(tiny["arms"]) == set(TINY["MODES"])
        and all(
            r["child_gone"] and r["returncode"] == 0 and r["observed_handoffs"] == 3
            for r in tiny["arms"].values()
        ),
        "tiny GPU prerequisite",
    )
    dso = load(a.dso / "receipt.json", a.dso_sha256)
    b = load(a.build / "receipt.json", a.build_sha256)
    need(
        dso["status"] == "PASS_IK_SM89_LINK_ONLY"
        and b["status"] == "PASS_HOT_TRANSFER_BUILD"
        and b["dso_sha256"] == a.dso_sha256
        and b["source_sha256"] == BUILD["sources"]()
        and b["geometry_sha256"] == BUILD["COMPACT"],
        "build/geometry sources",
    )
    small = load(a.env49, TINY["ENV49"])
    expected = {str((a.dso / n).resolve(strict=True)): h for n, h in dso["libraries"].items()}
    paths = {r["file"]: r["sha256"] for r in b["loader"].values()}
    need(all(paths.get(k) == v for k, v in expected.items()), "wrong ik DSOs")
    for row in dso["closure"].values():
        need(all(paths.get(p) == h for p, h in row.items()), "unrecognised CUDA closure")
    cfg = BUILD["CONFIG"]
    dirs = [
        a.dso / "objects/ggml/src",
        a.dso / "objects/src",
        Path(small["driver_dir"]),
        cfg["TOOLKIT"] / "lib64",
    ]
    need(b["search"] == list(map(str, dirs)), "search path")
    for name, target in small["driver_aliases"].items():
        need(str((dirs[2] / name).resolve(strict=True)) == target, "driver alias")
    inputs = dict(paths)
    drivers = set(small["driver_aliases"].values())
    for p in drivers:
        inputs[p] = small["files"][p]["sha256"]
    exe = a.build / "warm-transfer"
    inputs[str(exe)] = b["binary_sha256"]
    geometry = BUILD["GEOMETRY"]
    inputs[str(geometry)] = BUILD["COMPACT"]
    sealed = {}
    for k, h in inputs.items():
        p = Path(k)
        witness = dict(stat=IO.stat_id(p), sha256=h)
        if pre is None:
            need(sha(p) == h and IO.stat_id(p) == witness["stat"], "provider/geometry changed")
        else:
            need(pre["sealed"].get(k) == witness, "provider changed since preflight")
        sealed[k] = witness
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=os.pathsep.join(b["search"]),
        CUDA_VISIBLE_DEVICES="0",
        CUDA_CACHE_DISABLE="1",
        OMP_NUM_THREADS="1",
    )
    return exe, geometry, env, set(paths), drivers, sealed


def run(a, out, r):
    need(
        subprocess.check_output(["git", "-C", HERE, "rev-parse", "HEAD"], text=True).strip()
        == a.commit
        and not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]),
        "freeze mismatch",
    )
    identity = dict(
        commit=a.commit,
        build_sha256=a.build_sha256,
        tiny_sha256=a.tiny_sha256,
        dso_sha256=a.dso_sha256,
        c55_sha256=a.c55_sha256,
    )
    pre = None
    if a.execute:
        need(a.prepared and a.prepared_sha256, "preflight required")
        pre = load(a.prepared, a.prepared_sha256)
        need(pre["status"] == "PREPARED_ONLY" and pre["identity"] == identity, "preflight changed")
    exe, geometry, env, paths, drivers, sealed = seal(a, pre)
    policy, end = TINY["c55"](a)
    r.update(identity=identity, sealed=sealed, model_loads=0, energy_j=None, arms={})
    if not a.execute:
        r["status"] = "PREPARED_ONLY"
        return
    need(a.unit.startswith("tesy-ik-warm-transfer-"), "scope prefix")
    IO.CAP, IO.STOPS = TINY["CAP"], TINY["STOP"]
    IO.scope()
    cg = Path("/sys/fs/cgroup") / IO.cgroup_state()["path"].lstrip("/")
    need(
        cg.name == a.unit + ".scope"
        and cg.parent.name == "app.slice"
        and set((cg / "cgroup.procs").read_text().split()) == {str(os.getpid())},
        "scope ownership",
    )
    profile = run_path(str(TINY["QUAL"] / "packed_layer_service/profile.py"))
    r["monitor_provider"], unchanged = profile["monitor_provider"](
        SimpleNamespace(token=IO.stat_id)
    )
    for mode in MODES:
        unchanged()
        arm = r["arms"][mode] = {"starts": 0}
        folder = TINY["sample_arm"](
            mode, out, a, policy, end, exe, geometry, env, paths, drivers, arm
        )
        arm["grade"] = GRADE["reopen"](folder.parent)
        arm["samples_sha256"] = sha(folder / "samples.json")
        arm["maps_sha256"] = sha(folder / "maps")
        save(folder.parent / "grade.json", arm)
    unchanged()
    need(all(IO.stat_id(Path(k)) == v["stat"] for k, v in sealed.items()), "provider drift")
    r.update(max_scope_bytes=IO.scope(), swap_peak_bytes=int((cg / "memory.swap.peak").read_text()))
    need(r["swap_peak_bytes"] == 0, "peak swap")
    r["status"] = "MEASURED_HOT_SHMEM_TO_IK_CUDA"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("dso", "build", "tiny-family", "env49", "c55", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("commit", "dso-sha256", "build-sha256", "tiny-sha256", "c55-sha256"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--unit", default="")
    p.add_argument("--prepared", type=Path)
    p.add_argument("--prepared-sha256")
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = {"status": "FAIL_PRESERVED"}
    try:
        run(a, out, r)
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
