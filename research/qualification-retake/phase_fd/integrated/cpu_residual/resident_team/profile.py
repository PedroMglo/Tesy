"""E4 family, using the qualified C55/C118, sensors and cleanup of cpu0_suffix."""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUFFIX = HERE.parents[3] / "cpu0_suffix"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if (
    hashlib.sha256((SUFFIX / "profile.py").read_bytes()).hexdigest()
    != "64c526583837b485564003eb92f398117e99dcd9f5304788aa0a4d1bebb2745e"
):
    raise ValueError("historical E4 supervisor changed")
parent = load("resident_parent", SUFFIX / "profile.py")
grade = load("resident_grade", HERE / "grade.py")
builder = load("resident_builder", HERE / "build.py")
need = parent.need
PASS = "PASS_C266_RESIDENT_TEAM_FAMILY"


def topology():
    paths = Path("/sys/devices/system/cpu")
    result = []
    for core in range(12):
        cpu = paths / f"cpu{core}"
        sib = (cpu / "topology/thread_siblings_list").read_text().strip()
        group = (cpu / "cache/index3/shared_cpu_list").read_text().strip()
        speed = int((cpu / "cpufreq/cpuinfo_max_freq").read_text())
        need(
            sib == f"{core},{core + 12}" and group == ("0-3,12-15" if core < 4 else "4-11,16-23"),
            "topology changed",
        )
        result.append(dict(core=core, smt=sib, l3=group, max_khz=speed))
    need(
        min(v["max_khz"] for v in result[:4]) > max(v["max_khz"] for v in result[4:]),
        "core classes",
    )
    return result


def age(stamp, limit, why):
    seconds = (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(stamp)).total_seconds()
    need(0 <= seconds < limit, why)


def scoped(a, base, prior, r, start):
    git = ["/usr/bin/git", "--no-optional-locks", "-C", a.checkout]
    need(
        prior.command([*git, "rev-parse", "HEAD"]) == a.expect_head
        and not prior.command([*git, "status", "--porcelain"])
        and (a.checkout / a.study) == HERE,
        "clean frozen checkout",
    )
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_C266_RESIDENT_TEAM_BUILD"
        and build["libs"] == builder.LIBS
        and build["parent_build_sha256"] == builder.OLD,
        "build authority",
    )
    subprocess.run(
        [*git, "merge-base", "--is-ancestor", build["commit"], a.expect_head], check=True, timeout=6
    )
    need(
        build["source_sha256"] == {n: prior.sha(HERE / n) for n in builder.FILES}, "compiled inputs"
    )
    providers = {}
    for k, n in prior.LIB_CODES.items():
        f = (a.libs / n).resolve(strict=True)
        prior.sealed_file(f, builder.LIBS[n])
        providers[k] = str(f)
    for mode in ("stock", "observed"):
        exe = a.build_dir / mode
        prior.sealed_file(exe, build["executables"][mode])
        closure = prior.command(["/usr/bin/ldd", exe], prior.child_env(a, "DENSE"))
        need(
            not any(
                x in closure
                for x in ("not found", "libcuda", "libggml-cuda", "libllama", "libnvidia")
            ),
            "CPU provider closure",
        )
        for n in builder.LIBS:
            matches = [
                line.split()[2]
                for line in closure.splitlines()
                if line.strip().startswith(n.rsplit(".", 2)[0] + " => ")
            ]
            need(
                len(matches) == 1 and Path(matches[0]).samefile(a.libs / n),
                "wrong loader selection",
            )
    _, files = base.inputs(a, prior, r)
    with (a.input_dir / "ffn_moe_out-0.bin").open("rb") as f:
        f.seek(32 * 2880 * 4)
        gold = f.read(32 * 2880 * 4)
    need(hashlib.sha256(gold).hexdigest() == parent.GOLD, "C266 tile digest")
    r.update(
        build_sha256=a.build_sha256,
        commit=a.expect_head,
        topology=topology(),
        gold_sha256=parent.GOLD,
    )
    r["monitor_provider"], unchanged = base.monitor_provider(prior)
    c55 = prior.sealed_json(a.c55_receipt, a.c55_sha256)
    snapshot = prior.sealed_json(
        a.c55_receipt.parent / "resource-policy.json", c55["canonical_policy_sha256"]
    )["snapshot"]["utc"]
    root = a.new_output_dir
    (root / "raw").mkdir()
    age(snapshot, 55 * 60, "C55 expired")
    guard, policy, bounded, cg = base.admit(a, prior, SUFFIX, r, root)
    monitor = base.Monitor(guard, policy, bounded, cg, root / "raw/samples.jsonl", start, 720)
    thread = threading.Thread(target=monitor.run, daemon=True)
    thread.start()
    try:
        for idx, mode in enumerate("RRABBAR"):
            age(snapshot, 55 * 60, "C55 expired")
            unchanged()
            monitor.check()
            need(files == {p.name: prior.token(p) for p in a.input_dir.iterdir()}, "input changed")
            stock = idx == 0
            name = "stock" if stock else "observed"
            exe = a.build_dir / name
            prior.sealed_file(exe, build["executables"][name])
            dest = root / f"{idx:02d}-{mode}"
            dest.mkdir()
            item = dict(team=mode, stock=stock, status="FAIL_PRESERVED", child_started=False)
            r["arms"].append(item)
            proc = None
            try:
                if idx == 0:
                    age(r["c118"]["last_utc"], 3, "C118 expired")
                tic = time.monotonic()
                with (dest / "stdout").open("xb") as so, (dest / "stderr").open("xb") as se:
                    proc = subprocess.Popen(
                        [exe, a.input_dir, mode, dest / "native"],
                        cwd=a.checkout,
                        env=prior.child_env(a, "DENSE"),
                        stdout=so,
                        stderr=se,
                        start_new_session=True,
                    )
                    item.update(pid=proc.pid, child_started=True)
                    while proc.poll() is None:
                        monitor.check()
                        need(
                            time.monotonic() - tic < 90 and prior.footprint(root) < 32 << 20,
                            "native time/output",
                        )
                        try:
                            proc.wait(timeout=0.1)
                        except subprocess.TimeoutExpired:
                            pass
                need(proc.returncode == 0, "native failed; see stderr")
                row = json.loads((dest / "stdout").read_bytes())
                need((dest / "native/tile.f32").read_bytes() == gold, "independent gold")
                item.update(grade.verify(row, mode, stock, providers))
                item["status"] = "PASS_ARM"
                monitor.check()
            finally:
                if proc is not None:
                    bounded.stop_own_group(proc)
                    item["returncode"] = proc.returncode
                for path in ("stdout", "stderr", "native/tile.f32"):
                    if (dest / path).is_file():
                        item[path + "_sha256"] = prior.sha(dest / path)
                prior.put(dest / "receipt.json", item)
        unchanged()
        need(
            files == {p.name: prior.token(p) for p in a.input_dir.iterdir()}
            and prior.sha(a.input_dir / "pack.bin") == r["pack_sha256"],
            "pack changed",
        )
    finally:
        monitor.end.set()
        thread.join(timeout=6)
        monitor.check()
        need(not thread.is_alive(), "resource monitor did not exit")
    need(
        (cg / "cgroup.procs").read_text().split() == [str(os.getpid())] and monitor.count >= 2,
        "cleanup",
    )
    r.update(
        assessment=grade.decision(r["arms"]),
        peak_bytes=int((cg / "memory.peak").read_text()),
        swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
        monitor_samples=monitor.count,
        monitors_sha256=prior.sha(monitor.raw),
        children_after_cleanup=0,
    )
    need(
        r["swap_peak_bytes"] == 0 and prior.footprint(root) + len(json.dumps(r)) * 3 < 32 << 20,
        "terminal budget",
    )
    r["status"] = PASS


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("checkout", "build-dir", "input-dir", "libs", "c55-receipt", "new-output-dir"):
        ap.add_argument("--" + k, type=lambda x: Path(x).absolute(), required=True)
    for k in ("expect-head", "unit", "build-sha256", "input-sha256", "c55-sha256"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--in-scope", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    args.study = str(HERE.relative_to(args.checkout))
    # The inherited entrypoint starts the original E4 scope and writes both success and failure.
    parent.SELF = Path(__file__).resolve()
    parent.PASS = PASS
    parent.scoped = scoped
    sys.exit(parent.main(args))
