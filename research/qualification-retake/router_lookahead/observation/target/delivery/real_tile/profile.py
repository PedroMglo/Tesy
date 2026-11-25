"""Supervise a cold two-layer CPU traversal, gating all timings on both exact arms."""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q = next(p for p in HERE.parents if p.name == "qualification-retake")
ROOT = Q.parents[1]
SERVICE = "ae3e5a752d68ad0187eba0e9329e1e03fcb9e429fe5367c6f5a4258e626cf7bb"
LAYER = "3dfc12a50909fddd285143023a2edff5cd6e25b087453f21d4950649618db7cb"
ORDER = (
    ("EXACT", "OFF"),
    ("EXACT", "ON"),
    ("TIME", "OFF"),
    ("TIME", "ON"),
    ("TIME", "ON"),
    ("TIME", "OFF"),
)
OFFERS = [42, 19, 56, 113]
WINDOW = 13221888
FAMILY_S = 1200
CHILD_S = 240
OUT_LIMIT = 128 << 20
PASS = "PASS_REAL_TILE_FAMILY"


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def load_module(folder, name, expected):
    path = Q / folder / "profile.py"
    need(hashlib.sha256(path.read_bytes()).hexdigest() == expected, "supervisor dependency")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_row(row, grade, mode):
    need(
        row["status"] == "PASS_REAL_TILE" and row["grade"] == grade and row["mode"] == mode,
        "native terminal",
    )
    need(
        row["workers"] == 4 and row["drained"] is True and row["offers"] == OFFERS,
        "workers, drain or offers",
    )
    jobs = row["read_jobs"]
    need(
        type(jobs) is int
        and 125 <= jobs <= 130
        and row["pread_bytes"] == jobs * WINDOW
        and row["sets"] == 375
        and len(row["reads"]) == jobs,
        "read or SET conservation",
    )
    need(row["slab_hashes"] == (3 * jobs if grade == "EXACT" else 0), "slab hash coverage")
    keys = set()
    for layer, expert, speculative, begin, end in row["reads"]:
        need(
            layer in (0, 1)
            and 0 <= expert < 128
            and speculative in (0, 1)
            and isinstance(begin, int)
            and begin < end
            and (not speculative or mode == "ON"),
            "actual read interval",
        )
        keys.add((layer, expert))
    bindings = row["slot_bindings"]
    need(
        len(bindings) == 125 and len({(a, b) for a, b, _, _ in bindings}) == 125,
        "unique official assignments",
    )
    need(
        all((a, b) in keys and a in (0, 1) and 0 <= s < 40 and g > 0 for a, b, s, g in bindings),
        "official assignment missing a read",
    )
    need(sum(a == 0 for a, *_ in bindings) == 66, "layer counts")
    need(isinstance(row["numeric"], dict) and row["numeric"], "missing numerical proof")
    for field in ("elapsed_ns", "producer_ns", "drain_ns", "wait_ns"):
        need(type(row[field]) is int and row[field] >= 0, "native clock " + field)
    need(
        row["elapsed_ns"] > 0 and row["stage"] and row["epochs_ns"] and row["service"],
        "missing native telemetry",
    )
    return row["numeric"], bindings


def paired(arms):
    need([(x["grade"], x["mode"]) for x in arms] == list(ORDER), "incomplete paired orders")
    durations = [x["elapsed_ns"] for x in arms[2:]]
    delta = [durations[0] - durations[1], durations[3] - durations[2]]
    if min(delta) > 0:
        verdict = "GO_NEXT_PAIR_FIXTURE"
    elif max(delta) < 0:
        verdict = "NO_GO_TRAVERSAL_TIMING"
    else:
        verdict = "INCONCLUSIVE_TRAVERSAL_TIMING"
    return delta, verdict


def authorities(args, svc, prior, result):
    git = ["/usr/bin/git", "--no-optional-locks", "-C", ROOT]
    need(
        re.fullmatch("[0-9a-f]{40}", args.expect_head)
        and prior.command([*git, "rev-parse", "HEAD"]) == args.expect_head
        and not prior.command([*git, "status", "--porcelain"]),
        "clean frozen checkout",
    )
    for key in ("profile.py", "protocol.md", "build.py", "prepare.py", "native.cpp", "graph.inc"):
        result["source_sha256"][key] = svc.frozen(ROOT, HERE / key, args.expect_head)
    build = prior.sealed_json(args.build_dir / "receipt.json", args.build_sha256)
    need(build["status"] == "PASS_REAL_TILE_BUILD", "unqualified executable")
    exe = args.build_dir / "real-tile"
    prior.sealed_file(exe, build["binary_sha256"])
    need(
        build["binary"] == exe.name and re.fullmatch(r"[0-9a-f]{40}", build["commit"]),
        "binary or build commit",
    )
    subprocess.run(
        [*git, "merge-base", "--is-ancestor", build["commit"], args.expect_head],
        timeout=8,
        check=True,
    )
    for name in ("build.py", "native.cpp", "graph.inc", "protocol.md"):
        need(build["source_sha256"][name] == result["source_sha256"][name], "stale native source")
    libs = build["providers"]
    for path, digest in libs.values():
        prior.sealed_file(Path(path), digest)
    native_dirs = dict.fromkeys(
        str(Path(path).parent)
        for name, (path, _) in libs.items()
        if name.startswith(("libggml", "libscipy_openblas"))
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "CUDA_VISIBLE_DEVICES": "",
        "TESY_CPU_WAVE_SKIP_PARKED": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "LD_LIBRARY_PATH": ":".join(native_dirs),
    }
    resolved = prior.command(["/usr/bin/ldd", exe], env)
    need(
        "not found" not in resolved and not re.search(r"lib(cuda|nvidia|ggml-cuda)", resolved),
        "CPU executable dependencies",
    )
    observed = {
        line.split(" => ", 1)[0].strip(): str(
            Path(line.split(" => ")[1].split()[0]).resolve(strict=True)
        )
        for line in resolved.splitlines()
        if " => /" in line
    }
    need(observed == {k: v[0] for k, v in libs.items()}, "runtime providers differ from build")
    prep = prior.sealed_json(args.input_dir / "prepare.json", args.input_sha256)
    need(prep["status"] == "PASS_REAL_TILE_INPUT", "preparation status")
    need(
        set(prep["file_sha256"]) | {"prepare.json"} == {p.name for p in args.input_dir.iterdir()},
        "prepared file coverage",
    )
    need(prior.footprint(args.input_dir) <= 32 << 20, "input materialization")
    for name, digest in prep["file_sha256"].items():
        prior.sealed_file(args.input_dir / name, digest)
    need(
        prior.token(args.pack)
        == tuple(
            prep["pack_stat"][k] for k in ("dev", "inode", "size_bytes", "mtime_ns", "ctime_ns")
        ),
        "integral pack identity",
    )
    need(
        len(prep["entries"]) == 125 and all(len(e["hashes"]) == 3 for e in prep["entries"]),
        "archived read coverage",
    )
    result.update(
        commit=args.expect_head,
        tree=prior.command([*git, "rev-parse", "HEAD^{tree}"]),
        build_sha256=args.build_sha256,
        binary_sha256=build["binary_sha256"],
        input_sha256=args.input_sha256,
        providers=build["providers"],
        pack_stat=prior.token(args.pack),
        c55_sha256=args.c55_sha256,
    )
    return exe, env, build, prep


def run_child(args, svc, prior, mon, exe, env, grade, mode, idx, result, reference, official):
    folder = args.new_output_dir / f"{idx:02d}-{grade}-{mode}"
    folder.mkdir()
    record = {"grade": grade, "mode": mode, "status": "FAIL_PRESERVED"}
    proc = None
    started = time.monotonic()
    try:
        mon.check()
        if idx == 0:
            age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(result["c118"]["last_utc"])
            need(0 <= age.total_seconds() <= 3, "C118 expired before spawn")
        with (folder / "stdout").open("xb") as stdout, (folder / "stderr").open("xb") as stderr:
            proc = subprocess.Popen(
                [exe, args.input_dir, args.pack, mode, grade],
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            record.update(pid=proc.pid)
            while proc.poll() is None:
                mon.check()
                need(
                    time.monotonic() - started < CHILD_S
                    and prior.footprint(args.new_output_dir) + (1 << 20) < OUT_LIMIT,
                    "native resource limit",
                )
                try:
                    proc.wait(timeout=0.15)
                except subprocess.TimeoutExpired:
                    pass
        record.update(observed_process_s=time.monotonic() - started)
        need(
            record["observed_process_s"] <= CHILD_S and proc.returncode == 0, "native child failed"
        )
        row = json.loads((folder / "stdout").read_bytes())
        compared = check_row(row, grade, mode)
        need({tuple(v) for v in compared[1]} == official, "official slot generation changed")
        need(reference is None or compared == reference, "changed numerical output or assignments")
        record.update(
            status="PASS_ARM",
            elapsed_ns=row["elapsed_ns"],
            read_jobs=row["read_jobs"],
            pread_bytes=row["pread_bytes"],
            sets=row["sets"],
            stage=row["stage"],
        )
        return compared
    finally:
        if proc is not None:
            mon.bounded.stop_own_group(proc)
            record["returncode"] = proc.returncode
        for name in ("stdout", "stderr"):
            path = folder / name
            if path.is_file():
                record[name + "_sha256"] = prior.sha(path)
        svc.save(folder / "receipt.json", record)
        result["arms"].append(record)


def family(args, result, svc, prior, start):
    exe, env, build, prep = authorities(args, svc, prior, result)
    official = {tuple(e[k] for k in ("layer", "expert", "slot", "gen")) for e in prep["entries"]}
    files = list(args.input_dir.iterdir())
    identities = {
        p: prior.token(p)
        for p in [exe, args.pack, *files, *(Path(v[0]) for v in build["providers"].values())]
    }
    result["monitor_provider"], unchanged = svc.monitor_provider(prior)
    # This imported monitor uses WALL in its live check as well as the per-instance deadline.
    svc.WALL = FAMILY_S
    c55 = prior.sealed_json(args.c55_receipt, args.c55_sha256)
    trace = args.c55_receipt.parent / "samples.jsonl"
    prior.sealed_file(trace, c55["window_sha256"])
    last = json.loads(trace.read_bytes().splitlines()[-1])
    age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(last["utc"])
    need(0 <= age.total_seconds() <= 3600, "C55 outside its hour")
    guard, policy, bounded, cg = svc.admit(
        args, prior, Q / "packed_layer_service", result, args.new_output_dir
    )
    mon = svc.Monitor(
        guard,
        policy,
        bounded,
        cg,
        args.new_output_dir / "samples.jsonl",
        start,
        elapsed_limit=FAMILY_S,
    )
    observer = threading.Thread(target=mon.run, daemon=True)
    observer.start()
    ref = None
    try:
        for i, (grade, mode) in enumerate(ORDER):
            unchanged()
            need(
                all(prior.token(p) == ident for p, ident in identities.items()), "identity changed"
            )
            if i == 2:
                need(
                    len(result["arms"]) == 2
                    and all(x["status"] == "PASS_ARM" for x in result["arms"]),
                    "exactness gate failed",
                )
            compared = run_child(
                args, svc, prior, mon, exe, env, grade, mode, i, result, ref, official
            )
            if ref is None:
                ref = compared
        unchanged()
        need(all(prior.token(p) == ident for p, ident in identities.items()), "closure identity")
    finally:
        mon.end.set()
        observer.join(timeout=6)
        need(not observer.is_alive(), "monitor did not exit")
        result.update(
            monitor_samples=mon.count,
            peak_bytes=int((cg / "memory.peak").read_text()),
            swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
            remaining_pids=(cg / "cgroup.procs").read_text().split(),
            io_stat=(cg / "io.stat").read_text(),
            final_cgroup=bounded.cgroup_state(),
        )
        mon.check()
        need(result["remaining_pids"] == [str(os.getpid())] and mon.count >= 2, "cleanup")
    result["paired_saved_ns"], result["decision"] = paired(result["arms"])
    result["status"] = PASS


def main(args):
    os.umask(0o077)
    svc = load_module("packed_layer_service", "tile_service", SERVICE)
    prior = load_module("packed_real_layer", "tile_prior", LAYER)
    args.checkout = ROOT
    out = args.new_output_dir
    out.mkdir(mode=0o700, exist_ok=False)
    start = time.monotonic()
    result = dict(
        status="FAIL_PRESERVED",
        decision="INCONCLUSIVE",
        unit=args.unit,
        arms=[],
        source_sha256={},
        started_utc=svc.clock(),
    )
    try:
        need(re.fullmatch(r"tesy-[a-z0-9][a-z0-9-]{1,110}", args.unit), "systemd unit")
        family(args, result, svc, prior, start)
    except Exception as error:
        result.update(status="FAIL_PRESERVED", decision="INCONCLUSIVE", reason=repr(error))
    result.update(closed_utc=svc.clock(), elapsed_s=time.monotonic() - start)
    svc.save(out / "receipt.json", result)
    print(result["status"], result["decision"], result.get("reason", ""), flush=True)
    return int(result["status"] != PASS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("build-dir", "input-dir", "pack", "c55-receipt", "new-output-dir"):
        parser.add_argument("--" + field, required=True, type=lambda x: Path(x).resolve())
    for field in ("unit", "expect-head", "input-sha256", "build-sha256", "c55-sha256"):
        parser.add_argument("--" + field, required=True)
    raise SystemExit(main(parser.parse_args()))
