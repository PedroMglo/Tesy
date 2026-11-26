"""Qualify both bank inputs against the resident GGML CUDA graph, without product timing."""

import argparse
import fcntl
import os
import time
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SYS73 = run_path(str(HERE.parents[2] / "driver_62073/run.py"))
D, G, SYS, IO, need, sha, load, save = (
    SYS73[k] for k in ("D", "G", "SYS", "IO", "need", "sha", "load", "save")
)
B = run_path(str(HERE / "build.py"))
A = run_path(str(HERE / "grade.py"))
HIST = "2e335fc94cbd2c07c05958890e481db70b882e2ec71a34d29b0be3db775a15ea"


def freeze(a):
    need(
        B["git"](HERE, "rev-parse", "HEAD") == a.commit
        and not B["git"](HERE, "status", "--porcelain"),
        "unfrozen checkout",
    )
    hist = load(a.historical / "receipt.json", HIST)
    need(hist["status"] == "PASS_SYSTEM_TINY_BANKS", "previous numerical reference")
    past = {}
    for mode in ("RESIDENT", "BANK9"):
        path = a.historical / mode
        for name in ("stdout", "stderr", "native/prefill.f32", "native/teacher.f32"):
            need(sha(path / name) == hist["raw_sha256"][mode + "/" + name], "reference raw")
        past[mode] = SYS73["arm_grade"](mode, path)
        need(past[mode] == hist["arms"][mode]["grade"], "reference grading")
    old = load(a.client / "receipt.json", SYS73["CLIENT"])
    libs = load(a.dso / "receipt.json", SYS73["LIBS"])
    build = load(a.build / "receipt.json", a.build_sha256)
    ref, candidate = a.client / "hybrid-client", a.build / "bank-graph"
    need(
        build["status"] == "PASS_GRAPH_CLIENT_BUILD"
        and build["original_build"] == SYS73["CLIENT"]
        and build["commit"] == a.commit
        and libs["status"] == "PASS_IK_SM89_LINK_ONLY",
        "client builds",
    )
    files = {ref: old["binary_sha256"], candidate: build["binary_sha256"], a.tiny: D["TINY"]}
    need(
        all(sha(p) == h for p, h in files.items()) and a.tiny.stat().st_size == 3390592,
        "executables/GGUF",
    )
    obj = a.dso.resolve() / "objects"
    env, paths, drivers = SYS["system_loader"](candidate, old, obj)
    need((env, paths, drivers) == SYS["system_loader"](ref, old, obj), "different ELF providers")
    for p, h in (paths | drivers | {str(ref): files[ref], str(a.tiny): D["TINY"]}).items():
        need(hist["authority"]["providers"][p]["sha256"] == h, "historical provider " + p)
    profile = run_path(str(D["QUAL"] / "packed_layer_service/profile.py"))
    monitor, unchanged = profile["monitor_provider"](SimpleNamespace(token=IO.stat_id))
    need(monitor == hist["authority"]["monitor"], "monitor or loaded driver changed")
    allowed = {
        p
        for p in drivers
        if Path(p).name.startswith(("libcuda.", "libnvidia-")) and "nvidia-ml" not in p
    }
    policy, end = D["c55"](a)
    need(
        end.timestamp() > int(B["git"](HERE, "log", "-1", "--format=%ct", "--", "protocol.md")),
        "C55 predates protocol",
    )
    hashes = paths | drivers | {str(p): h for p, h in files.items()}
    state = dict(
        commit=a.commit,
        tree=B["git"](HERE, "rev-parse", "HEAD^{tree}"),
        c55_sha256=a.c55_sha256,
        build_sha256=a.build_sha256,
        historical_sha256=HIST,
        child_env=env,
        monitor=monitor,
        files={k: dict(sha256=v, stat=IO.stat_id(Path(k))) for k, v in hashes.items()},
        sources={
            p.name: sha(p) for p in (HERE / "run.py", HERE / "grade.py", HERE / "protocol.md")
        },
    )
    return state, (policy, end, env, set(paths), allowed), (ref, candidate), past, unchanged


def scope(a):
    IO.CAP, IO.STOPS = D["CAP"], D["STOP"]
    IO.scope()
    cg = Path("/sys/fs/cgroup") / IO.cgroup_state()["path"].lstrip("/")
    need(
        a.unit.startswith("tesy-ik-graph-input-")
        and cg.name == a.unit + ".scope"
        and cg.parent.name == "app.slice"
        and (cg / "cgroup.procs").read_text().split() == [str(os.getpid())],
        "unexpected cgroup or owner",
    )
    return cg


def run(a, out, r):
    state, params, exes, past, unchanged = freeze(a)
    r["authority"] = state
    if a.prepared is None:
        r["status"] = "PREPARED_ONLY"
        return
    prep = load(a.prepared / "receipt.json", a.prepared_sha256)
    need(prep["status"] == "PREPARED_ONLY" and prep["authority"] == state, "changed preparation")
    r["prepared_sha256"] = a.prepared_sha256
    policy, end, env, paths, drivers = params
    cg = scope(a)
    deadline = time.monotonic() + 600
    resident = resident_grade = None
    for mode in ("RESIDENT", "DIRECT", "PREAD_RANDOM"):
        unchanged()
        r["arms"][mode] = arm = dict(starts=0)
        ref = mode == "RESIDENT"
        native = D["sample_arm"](
            mode, out, a, policy, end, exes[0 if ref else 1], a.tiny, env, paths, drivers, arm
        )
        original = "RESIDENT" if ref else "BANK9"
        parent = native.parent
        raw = (parent / "stdout").read_text()
        if ref:
            grade = SYS73["arm_grade"](original, parent)
        else:
            logical, arm["physical_source"] = A["audit"](raw, mode, native, a.tiny)
            grade = G["check_arm"](original, logical, (parent / "stderr").read_text(), native)
        arm["grade"] = grade
        previous = a.historical / original
        need(
            grade == past[original]
            and A["schedule"](raw) == A["schedule"]((previous / "stdout").read_text())
            and SYS73["placement"](parent / "stdout") == SYS73["placement"](previous / "stdout"),
            "historic bank or resident execution differs",
        )
        if ref:
            resident, resident_grade = native, grade
        arm["reference"] = G["compare_arms"](resident, resident_grade, native, grade)
        arm["historical"] = G["compare_arms"](previous / "native", past[original], native, grade)
        need(
            all(
                arm[key]["bitwise"] and arm[key]["routes_equal"]
                for key in ("reference", "historical")
            ),
            "logits or ordered IDs differ",
        )
        if mode == "PREAD_RANDOM":
            arm["direct"] = G["compare_arms"](
                out / "DIRECT/native", r["arms"]["DIRECT"]["grade"], native, grade
            )
            need(arm["direct"]["bitwise"] and arm["direct"]["routes_equal"], "ablation differs")
        need(
            time.monotonic() < deadline and int((cg / "memory.peak").read_text()) < D["STOP"],
            "family deadline or scope stop",
        )
    unchanged()
    need(all(IO.stat_id(Path(k)) == v["stat"] for k, v in state["files"].items()), "provider drift")
    r["status"] = "PASS_TINY_GRAPH_BANK_INPUT"


def main(run_family=run, extra_paths=()):
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "client",
        "dso",
        "tiny",
        "historical",
        "build",
        "c55",
        "new-output-dir",
        *extra_paths,
    ):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("c55-sha256", "build-sha256", "commit"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--prepared", type=Path)
    p.add_argument("--prepared-sha256")
    p.add_argument("--unit")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", arms={}, product_requests=0, energy_j=None)
    try:
        need(bool(a.prepared) == bool(a.prepared_sha256) == bool(a.unit), "preflight or execute")
        if a.unit:
            with (Path("/run/user") / str(os.getuid()) / "tesy-c110-callback.lock").open(
                "a"
            ) as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                run_family(a, out, r)
        else:
            run_family(a, out, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        if a.unit:
            try:
                cg = scope(a)
                r.update(
                    memory_peak_B=int((cg / "memory.peak").read_text()),
                    swap_peak_B=int((cg / "memory.swap.peak").read_text()),
                    events=IO.cgroup_state()["events_local"],
                    raw_sha256={
                        str(f.relative_to(out)): sha(f) for f in out.rglob("*") if f.is_file()
                    },
                )
                need(
                    not r["swap_peak_B"]
                    and not r["events"]["oom"]
                    and not r["events"]["oom_kill"]
                    and r["memory_peak_B"] < D["STOP"],
                    "final resource counters",
                )
            except Exception as exc:
                r.update(status="FAIL_PRESERVED", final_error=str(exc))
        save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""), r.get("final_error", ""))
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
