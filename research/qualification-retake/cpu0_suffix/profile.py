"""One process per C291 CPU tile; compare OFF/ON inside one qualified E4 scope."""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

Q = Path("research/qualification-retake")
SELF = Path(__file__).resolve()
SCHEDULE = ("OFF", "ON", "ON", "OFF", "ON", "OFF", "OFF", "ON")
PASS = "PASS_CPU0_SUFFIX_TIMING_FAMILY"
WORKER = "c89c88b342054223e3f27a17fbfd0954803147ac"
TREE = "3962daa588dfa89971c60c95ce4c5054bc27fd3f"
SERVICE = "ae3e5a752d68ad0187eba0e9329e1e03fcb9e429fe5367c6f5a4258e626cf7bb"
LAYER = "3dfc12a50909fddd285143023a2edff5cd6e25b087453f21d4950649618db7cb"
GOLD = "bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24"
MIB = 1 << 20
CAP = 4096 * MIB
STOP = 3584 * MIB


def need(ok, why):
    if not ok:
        raise ValueError(why)


def module(path, name, expected=None):
    if expected:
        need(
            not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            "controller identity " + path.name,
        )
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def source_contract(a, base, prior):
    root = a.checkout
    here = root / a.study
    need(SELF == here / "profile.py" and here.parent == root / Q, "supervisor checkout/study")
    git = ["/usr/bin/git", "--no-optional-locks", "-C", root]
    need(
        re.fullmatch("[0-9a-f]{40}", a.expect_head)
        and prior.command([*git, "rev-parse", "HEAD"]) == a.expect_head
        and not prior.command([*git, "status", "--porcelain"]),
        "clean checkout",
    )
    tree = prior.command([*git, "rev-parse", "HEAD^{tree}"])
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_C291_CPU0_SUFFIX_BUILD"
        and build["worker_commit"] == WORKER
        and build["worker_tree"] == TREE
        and build["libs"] == prior.LIBS,
        "build authority",
    )
    need(re.fullmatch("[0-9a-f]{40}", build["commit"]), "build commit")
    subprocess.run(
        [*git, "merge-base", "--is-ancestor", build["commit"], a.expect_head], check=True, timeout=8
    )
    native = build["sources"]
    need(set(native) == {"build.py", "operator.patch", "suffix-clock.h"}, "build sources")
    for name, digest in native.items():
        need(
            Path(name).name == name
            and base.frozen(root, here / name, build["commit"]) == digest
            and base.frozen(root, here / name, a.expect_head) == digest,
            "compiled source differs",
        )
    sources = {
        p: base.frozen(root, here / p, a.expect_head)
        for p in ("decision.py", "profile.py", "protocol.md")
    }
    exe = a.build_dir / "suffix-layer"
    prior.sealed_file(exe, build["binary_sha256"])
    linked = prior.command(["/usr/bin/ldd", exe], prior.child_env(a, "DENSE"))
    need(
        "not found" not in linked and not re.search(r"lib(cuda|nvidia|llama|ggml-cuda)", linked),
        "CPU-only loader",
    )
    seen = {}
    for line in linked.splitlines():
        parts = line.split()
        if parts[0].startswith("libggml"):
            need(len(parts) >= 3 and parts[1] == "=>", "ambiguous GGML selection")
            path = Path(parts[2]).resolve(strict=True)
            need(path.name in prior.LIBS and path.samefile(a.libs / path.name), "wrong GGML path")
            prior.sealed_file(path, prior.LIBS[path.name])
            seen[path.name] = prior.LIBS[path.name]
    need(seen == prior.LIBS, "missing native providers")
    return dict(
        commit=a.expect_head,
        tree=tree,
        source_sha256=sources,
        build_sha256=a.build_sha256,
        build_commit=build["commit"],
        native_sources=native,
        executable_sha256=build["binary_sha256"],
        provider_sha256=seen,
    )


def clocks(row, mode):
    need(mode in ("OFF", "ON") and row.get("mode") == mode, "observer assignment")
    start, end = row["graph_start_ns"], row["graph_end_ns"]
    elapsed = row["graph_ns"]
    need(
        all(type(v) is int for v in (start, end, elapsed))
        and 0 < start < end
        and elapsed == end - start,
        "graph wall endpoints",
    )
    mark, suffix = row["wave_return_ns"], row["suffix_ns"]
    if mode == "OFF":
        need(
            mark is None
            and suffix is None
            and type(row["wave_markers"]) is int
            and row["wave_markers"] == 0,
            "OFF control marked",
        )
    else:
        need(
            type(mark) is int
            and type(suffix) is int
            and start < mark < end
            and suffix == end - mark
            and type(row["wave_markers"]) is int
            and row["wave_markers"] == 1,
            "ON marker count/chronology",
        )
    return dict(graph_ns=elapsed, suffix_ns=suffix, start_ns=start, return_ns=mark, end_ns=end)


def verify(a, prior, row, mode, directory, gold):
    expected = dict(
        status="PASS_C291_CPU0_SUFFIX",
        arm="DENSE",
        compute_backend="CPU",
        router_positions=153,
        ffn_positions=32,
        full_ffn_values=92160,
        graph_waves=8,
        roles=["gate", "down", "up"],
        cb_eval_registered=False,
        graph_mmid_nodes=24,
        wave_calls=8,
        active_waves=1,
        unique_loads=5,
        logical_weight_bytes=66096000,
        expected_pread_bytes=66109440,
        expected_weight_sets=15,
        workers_before_destructor=4,
        joined_workers=4,
        manager_destructor_returned=True,
    )
    for key, value in expected.items():
        need(type(row.get(key)) is type(value) and row[key] == value, "native witness:" + key)
    alignment = row["dio_offset_alignment"]
    need(
        type(alignment) is int
        and alignment > 0
        and alignment & (alignment - 1) == 0
        and 5 * ((13219200 + alignment - 1) // alignment) * alignment
        == row["expected_pread_bytes"],
        "alignment/transport",
    )
    info = clocks(row, mode)
    need(
        type(row["graph_nodes"]) is int
        and row["graph_nodes"] >= 24
        and type(row["backend_splits"]) is int
        and row["backend_splits"] > 0
        and isinstance(row["graph_fingerprint"], str)
        and re.fullmatch("[0-9a-f]{16}", row["graph_fingerprint"]),
        "graph topology",
    )
    need(set(row["providers"]) == set(prior.LIB_CODES), "native providers")
    for kind, soname in prior.LIB_CODES.items():
        path = Path(row["providers"][kind])
        need(
            path.is_absolute()
            and path.samefile(a.libs / soname)
            and prior.sha(path) == prior.LIBS[soname],
            "native provider:" + kind,
        )
    tile = directory / "tile.f32"
    need(
        {v.name for v in directory.iterdir()} == {"tile.f32"}
        and not tile.is_symlink()
        and tile.stat().st_size == len(gold) == 92160 * 4
        and tile.read_bytes() == gold,
        "C266 bitwise tile",
    )
    return (
        info
        | {
            k: row[k]
            for k in (
                "graph_nodes",
                "graph_fingerprint",
                "backend_splits",
                "expected_weight_sets",
                "expected_pread_bytes",
                "logical_weight_bytes",
                "active_waves",
                "wave_calls",
                "unique_loads",
                "joined_workers",
            )
        }
        | {"tile_sha256": GOLD}
    )


def arm(a, base, prior, monitor, rec, seq, mode, gold):
    folder = a.new_output_dir / f"{seq:02d}-{mode}"
    folder.mkdir()
    exe = a.build_dir / "suffix-layer"
    prior.sealed_file(exe, rec["executable_sha256"])
    env = prior.child_env(a, "DENSE") | {"TESY_CPU_SUFFIX": mode}
    need(
        set(env)
        == {
            "PATH",
            "LC_ALL",
            "LD_LIBRARY_PATH",
            "CUDA_VISIBLE_DEVICES",
            "OMP_NUM_THREADS",
            "OMP_DYNAMIC",
            "TESY_CPU_WAVE_SKIP_PARKED",
            "TESY_CPU_SUFFIX",
        }
        and env["OMP_NUM_THREADS"] == "8"
        and env["CUDA_VISIBLE_DEVICES"] == "",
        "native environment",
    )
    native = folder / "native"
    argv = [exe, a.input_dir, mode, native]
    result = dict(
        run_index=seq,
        observer=mode,
        status="FAIL_PRESERVED",
        child_started=False,
        started_utc=base.clock(),
    )
    rec["arms"].append(result)
    proc = None
    try:
        monitor.check()
        if seq == 0:
            age = (
                dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(rec["c118"]["last_utc"])
            ).total_seconds()
            need(0 <= age <= 3, "stale C118")
        tic = time.monotonic()
        with (folder / "stdout").open("xb") as stdout, (folder / "stderr").open("xb") as stderr:
            proc = subprocess.Popen(
                argv, cwd=a.checkout, env=env, stdout=stdout, stderr=stderr, start_new_session=True
            )
            result.update(pid=proc.pid, child_started=True)
            while proc.poll() is None:
                monitor.check()
                need(
                    time.monotonic() - tic < 180 and prior.footprint(a.new_output_dir) < 32 * MIB,
                    "child budget",
                )
                try:
                    proc.wait(timeout=0.15)
                except subprocess.TimeoutExpired:
                    pass
            result["spawn_to_observed_exit_s"] = time.monotonic() - tic
        need(proc.returncode == 0 and result["spawn_to_observed_exit_s"] < 180, "native exit/time")
        native_row = json.loads((folder / "stdout").read_bytes())
        result.update(verify(a, prior, native_row, mode, native, gold))
        result["status"] = "PASS_C291_CPU0_SUFFIX_ARM"
        monitor.check()
    finally:
        if proc is not None:
            monitor.bounded.stop_own_group(proc)
            result["returncode"] = proc.returncode
        for name in ("stdout", "stderr"):
            if (folder / name).is_file():
                result[name + "_sha256"] = prior.sha(folder / name)
        result["closed_utc"] = base.clock()
        prior.put(folder / "receipt.json", result)


def scoped(a, base, prior, r, start):
    r.update(source_contract(a, base, prior))
    decide = module(a.checkout / a.study / "decision.py", "cpu0_suffix_decision")
    prep, files = base.inputs(a, prior, r)
    with (a.input_dir / "ffn_moe_out-0.bin").open("rb") as f:
        f.seek(32 * 2880 * 4)
        gold = f.read(32 * 2880 * 4)
    need(hashlib.sha256(gold).hexdigest() == GOLD, "gold tile")
    r["monitor_provider"], unchanged = base.monitor_provider(prior)
    root = a.new_output_dir
    (root / "raw").mkdir()
    guard, policy, bounded, cg = base.admit(a, prior, a.checkout / a.study, r, root)
    monitor = base.Monitor(guard, policy, bounded, cg, root / "raw/samples.jsonl", start)
    thread = threading.Thread(target=monitor.run, daemon=True)
    thread.start()
    try:
        for seq, mode in enumerate(SCHEDULE):
            unchanged()
            need(
                files == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
                "input identity changed",
            )
            arm(a, base, prior, monitor, r, seq, mode, gold)
        unchanged()
        need(
            prior.sha(a.input_dir / "pack.bin") == r["pack_sha256"]
            and files == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
            "input closure",
        )
    finally:
        monitor.end.set()
        thread.join(timeout=6)
        need(not thread.is_alive(), "monitor cleanup")
        monitor.check()
    need((cg / "cgroup.procs").read_text().split() == [str(os.getpid())], "unreaped child")
    total = sum(arm["expected_pread_bytes"] for arm in r["arms"])
    need(
        len(
            {
                (arm["graph_fingerprint"], arm["graph_nodes"], arm["backend_splits"])
                for arm in r["arms"]
            }
        )
        == 1,
        "graph/split changed",
    )
    need(total == 528875520 and monitor.count >= 2, "work conservation")
    r.update(
        status=PASS,
        assessment=decide.evaluate(r["arms"]),
        full_tile_sha256=GOLD,
        expected_aligned_service_bytes=total,
        logical_service_bytes=sum(arm["logical_weight_bytes"] for arm in r["arms"]),
        prepared_pack_bytes=prep["pack_size_bytes"],
        monitor_samples=monitor.count,
        monitor_sha256=prior.sha(monitor.raw),
        peak_bytes=int((cg / "memory.peak").read_text()),
        swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
        io_stat=(cg / "io.stat").read_text(),
        cpu_stat=(cg / "cpu.stat").read_text(),
        cgroup_final=bounded.cgroup_state(),
        child_processes_at_cleanup=0,
    )
    need(prior.footprint(root) + len(json.dumps(r)) * 3 + 65536 < 32 * MIB, "output budget")


def main(a):
    os.umask(0o077)
    need(re.fullmatch(r"tesy-[a-z0-9][a-z0-9-]{1,110}", a.unit), "unit")
    out = a.new_output_dir
    if not a.in_scope:
        out.mkdir(mode=0o700)
    service = module(
        a.checkout / Q / "packed_layer_service/profile.py", "cpu0_service_controls", SERVICE
    )
    prior = module(a.checkout / Q / "packed_real_layer/profile.py", "cpu0_layer_controls", LAYER)
    start = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        unit=a.unit,
        arms=[],
        started_utc=service.clock(),
        cap_bytes=CAP,
        stop_bytes=STOP,
        swap_max_bytes=0,
    )
    try:
        if a.in_scope:
            scoped(a, service, prior, r, start)
        else:
            cmd = [
                "/usr/bin/systemd-run",
                "--user",
                "--scope",
                "--quiet",
                "--collect",
                "--unit=" + a.unit,
                "-p",
                f"MemoryMax={CAP}",
                "-p",
                "MemorySwapMax=0",
                "-p",
                "RuntimeMaxSec=720s",
                "-p",
                "CPUAccounting=yes",
                "-p",
                "IOAccounting=yes",
                sys.executable,
                "-I",
                "-B",
                SELF,
                *sys.argv[1:],
                "--in-scope",
            ]
            with (
                (out / "scope.stdout").open("xb") as stdout,
                (out / "scope.stderr").open("xb") as stderr,
            ):
                rc = subprocess.run(
                    cmd, stdout=stdout, stderr=stderr, timeout=728, check=False
                ).returncode
            r["scope_rc"] = rc
            if (out / "detail.json").is_file():
                doc = json.loads((out / "detail.json").read_bytes())
                r.update(
                    detail_sha256=prior.sha(out / "detail.json"),
                    inner_status=doc["status"],
                    reason=doc.get("reason"),
                    arms_started=sum(x["child_started"] for x in doc["arms"]),
                    assessment=doc.get("assessment"),
                )
            need(rc == 0 and r.get("inner_status") == PASS, "family scope failed")
            r["status"] = PASS
    except Exception as error:
        r.update(
            status="FAIL_PRESERVED",
            failure=f"{type(error).__name__}: {error}",
            reason=r.get("reason") or str(error),
        )
    finally:
        r.update(
            elapsed_s=time.monotonic() - start,
            closed_utc=service.clock(),
            supervisor_sha256=prior.sha(SELF),
        )
        prior.put(out / ("detail.json" if a.in_scope else "receipt.json"), r)
    print(r["status"], flush=True)
    return int(r["status"] != PASS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("checkout", "build-dir", "input-dir", "libs", "c55-receipt", "new-output-dir"):
        parser.add_argument("--" + key, type=lambda x: Path(x).absolute(), required=True)
    for key in ("expect-head", "unit", "build-sha256", "input-sha256", "c55-sha256"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--study", default="research/qualification-retake/cpu0_suffix")
    parser.add_argument("--in-scope", action="store_true", help=argparse.SUPPRESS)
    sys.exit(main(parser.parse_args()))
