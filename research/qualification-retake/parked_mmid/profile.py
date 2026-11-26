"""Run three numerical gates and four paired CPU tile measurements in one C118 scope."""

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

HERE = Path(__file__).resolve()
STUDY = Path("research/qualification-retake/parked_mmid")
ROOT = HERE.parents[3]
CPU0 = "64c526583837b485564003eb92f398117e99dcd9f5304788aa0a4d1bebb2745e"
REFERENCE = "b3db7c58b1aeac0c40a26131e89009793f04e0c16a8275f23e7238f55339a7b2"
QUALIFY = ("ORIGINAL", "OFF", "ON")
SCHEDULE = ("OFF", "ON", "ON", "OFF", "ON", "OFF", "OFF", "ON")
PASS = "PASS_PARKED_MMID_TILE_FAMILY"
MODE_ENV = "TESY_CPU_MMX_ALL_PARKED"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def cpu0_module():
    path = HERE.parents[1] / "cpu0_suffix/profile.py"
    need(hashlib.sha256(path.read_bytes()).hexdigest() == CPU0, "CPU0 supervisor")
    spec = importlib.util.spec_from_file_location("parked_cpu0_controls", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settings(a, prior, ref, build, mode):
    need(mode in QUALIFY, "kernel mode")
    cpu, base = prior.LIB_CODES["cpu"], prior.LIB_CODES["base"]
    original = mode == "ORIGINAL"
    cpu_dir = a.libs if original else a.build_dir / "candidate"
    providers = {
        "cpu": (
            cpu_dir / cpu,
            build["original_cpu_sha256" if original else "candidate_cpu_sha256"],
        ),
        "base": (a.libs / base, build["base_sha256"]),
    }
    for path, digest in providers.values():
        prior.sealed_file(path, digest)
    env = prior.child_env(a, "DENSE") | {"TESY_CPU_SUFFIX": "OFF"}
    if not original:
        env |= {
            "LD_LIBRARY_PATH": os.pathsep.join(map(str, (cpu_dir, a.libs))),
            MODE_ENV: str(int(mode == "ON")),
        }
    need(
        build["original_cpu_sha256"] == ref["provider_sha256"][cpu]
        and build["base_sha256"] == ref["provider_sha256"][base]
        and build["candidate_cpu_sha256"] != build["original_cpu_sha256"]
        and env["CUDA_VISIBLE_DEVICES"] == ""
        and env["OMP_NUM_THREADS"] == "8"
        and env["TESY_CPU_WAVE_SKIP_PARKED"] == "1",
        "operator authority",
    )
    return env, providers


def contract(a, prior, service, c):
    repo = a.checkout
    need(repo.resolve() == ROOT and HERE == repo / STUDY / "profile.py", "checkout")
    git = ["/usr/bin/git", "--no-optional-locks", "-C", repo]
    need(
        re.fullmatch(r"[a-f0-9]{40}", a.expect_head)
        and prior.command([*git, "rev-parse", "HEAD"]) == a.expect_head
        and not prior.command([*git, "status", "--porcelain"]),
        "clean frozen checkout",
    )
    tree = prior.command([*git, "rev-parse", "HEAD^{tree}"])
    ref = prior.sealed_json(HERE.parents[1] / "cpu0_suffix/physical-r01/receipt.json", REFERENCE)
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_C269_PARKED_MMID_BUILD"
        and build["binary_sha256"] == ref["executable_sha256"]
        and re.fullmatch("[0-9a-f]{64}", build["numerical_fixture_sha256"]),
        "qualified build and historical harness",
    )
    check_build(a, prior, service, build, git)
    prior.sealed_file(a.build_dir / "suffix-layer", build["binary_sha256"])
    expected_paths = {}
    for mode in QUALIFY:
        env, providers = settings(a, prior, ref, build, mode)
        loader = prior.command(["/usr/bin/ldd", a.build_dir / "suffix-layer"], env)
        need(
            "not found" not in loader
            and not re.search(r"lib(cuda|nvidia|llama|ggml-cuda)", loader),
            "CPU-only child",
        )
        mapped = {}
        for line in loader.splitlines():
            f = line.split()
            if f and f[0].startswith("libggml"):
                need(len(f) >= 3 and f[1] == "=>" and f[0] not in mapped, "ambiguous GGML provider")
                mapped[f[0]] = Path(f[2]).resolve(strict=True)
        need(
            set(mapped.values()) == {p.resolve(strict=True) for p, _ in providers.values()}
            and len(mapped) == len(providers),
            "loader provider",
        )
        expected_paths[mode] = {
            role: {"path": str(path.resolve()), "sha256": digest}
            for role, (path, digest) in providers.items()
        }
    c.update(
        commit=a.expect_head,
        tree=tree,
        build_sha256=a.build_sha256,
        executable_sha256=build["binary_sha256"],
        cpu0_compact_sha256=REFERENCE,
        numerical_fixture_sha256=build["numerical_fixture_sha256"],
        providers=expected_paths,
        source_sha256={
            n: service.frozen(repo, HERE.parent / n, a.expect_head)
            for n in ("profile.py", "protocol.md", "decision.py")
        },
    )
    return ref, build


def native_row(prior, cpu0, ref, row, providers, out, gold):
    expected = dict(
        status="PASS_C291_CPU0_SUFFIX",
        arm="DENSE",
        mode="OFF",
        clock="CLOCK_MONOTONIC",
        compute_backend="CPU",
        roles=["gate", "down", "up"],
        cb_eval_registered=False,
        marked_graph_threads=0,
        graph_mmid_nodes=24,
        router_positions=153,
        ffn_positions=32,
        full_ffn_values=92160,
        graph_waves=8,
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
    for key in ("graph_fingerprint", "graph_nodes", "backend_splits"):
        expected[key] = ref[key]
    for key, value in expected.items():
        need(type(row.get(key)) is type(value) and row[key] == value, "native " + key)
    info = cpu0.clocks(row, "OFF")
    align = row["dio_offset_alignment"]
    need(
        type(align) is int
        and align > 0
        and align & (align - 1) == 0
        and 5 * ((13219200 + align - 1) // align) * align == row["expected_pread_bytes"],
        "transport",
    )
    need(set(row["providers"]) == set(providers), "native providers")
    for role, (path, digest) in providers.items():
        p = Path(row["providers"][role])
        need(p.is_absolute() and p.samefile(path) and prior.sha(p) == digest, "native " + role)
    tile = out / "tile.f32"
    need(
        {p.name for p in out.iterdir()} == {"tile.f32"}
        and not tile.is_symlink()
        and tile.stat().st_size == len(gold) == 368640
        and tile.read_bytes() == gold,
        "C266 bitwise tile",
    )
    return (
        info
        | {k: row[k] for k in expected if k not in {"status", "mode"}}
        | {
            "tile_sha256": cpu0.GOLD,
            "tile_bytes": len(gold),
            "provider_sha256": {role: digest for role, (_, digest) in providers.items()},
        }
    )


def run_arm(a, prior, service, cpu0, monitor, record, ref, build, gold, mode):
    index = len(record["arms"])
    folder = a.new_output_dir / f"{index:02d}-{mode}"
    folder.mkdir()
    native = folder / "native"
    arm = dict(
        run_index=index,
        phase="qualification" if index < 3 else "timing",
        mode=mode,
        observer="OFF",
        status="FAIL_PRESERVED",
        child_started=False,
        started_utc=service.clock(),
    )
    record["arms"].append(arm)
    proc = None
    try:
        exe = a.build_dir / "suffix-layer"
        prior.sealed_file(exe, build["binary_sha256"])
        env, providers = settings(a, prior, ref, build, mode)
        arm["kernel_env"] = env.get(MODE_ENV)
        monitor.check()
        if index == 0:
            age = (
                dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(record["c118"]["last_utc"])
            ).total_seconds()
            need(0 <= age <= 3, "stale C118")
        tic = time.monotonic()
        with (folder / "stdout").open("xb") as stdout, (folder / "stderr").open("xb") as stderr:
            proc = subprocess.Popen(
                [exe, a.input_dir, "OFF", native],
                cwd=a.checkout,
                env=env,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            arm.update(pid=proc.pid, child_started=True)
            while proc.poll() is None:
                monitor.check()
                need(
                    time.monotonic() - tic < 180
                    and prior.footprint(a.new_output_dir) < 32 * cpu0.MIB,
                    "child budget",
                )
                try:
                    proc.wait(timeout=0.15)
                except subprocess.TimeoutExpired:
                    pass
        arm["spawn_to_observed_exit_s"] = time.monotonic() - tic
        need(proc.returncode == 0 and arm["spawn_to_observed_exit_s"] < 180, "native exit/time")
        row = json.loads((folder / "stdout").read_bytes())
        arm.update(native_row(prior, cpu0, ref, row, providers, native, gold))
        monitor.check()
        arm["status"] = "PASS_PARKED_MMID_TILE_ARM"
    finally:
        if proc is not None:
            monitor.bounded.stop_own_group(proc)
            arm["returncode"] = proc.returncode
        for name in ("stdout", "stderr"):
            if (folder / name).is_file():
                arm[name + "_sha256"] = prior.sha(folder / name)
        arm["closed_utc"] = service.clock()
        prior.put(folder / "receipt.json", arm)


def timing_input(rows):
    need(
        len(rows) == 11 and tuple(r["mode"] for r in rows) == QUALIFY + SCHEDULE,
        "qualification and timing order",
    )
    for i, r in enumerate(rows):
        need(
            r["run_index"] == i
            and r["phase"] == ("qualification" if i < 3 else "timing")
            and r["status"] == "PASS_PARKED_MMID_TILE_ARM"
            and r["returncode"] == 0
            and r["child_started"] is True
            and r["observer"] == "OFF",
            "incomplete family",
        )
    return [{"mode": r["mode"], "graph_ns": r["graph_ns"]} for r in rows[3:]]


def scoped(a, prior, service, cpu0, r, start):
    ref, build = contract(a, prior, service, r)
    decide = cpu0.module(HERE.with_name("decision.py"), "parked_mmid_decision")
    prep, files = service.inputs(a, prior, r)
    with (a.input_dir / "ffn_moe_out-0.bin").open("rb") as f:
        f.seek(368640)
        gold = f.read(368640)
    need(hashlib.sha256(gold).hexdigest() == cpu0.GOLD, "C266 tile gold")
    r["monitor_provider"], unchanged = service.monitor_provider(prior)
    dest = a.new_output_dir
    (dest / "raw").mkdir()
    guard, policy, bounded, cg = service.admit(a, prior, HERE.parent, r, dest)
    mon = service.Monitor(guard, policy, bounded, cg, dest / "raw/samples.jsonl", start)
    thread = threading.Thread(target=mon.run, daemon=True)
    thread.start()
    try:
        for mode in QUALIFY + SCHEDULE:
            unchanged()
            need(files == {p.name: prior.token(p) for p in a.input_dir.iterdir()}, "input changed")
            run_arm(a, prior, service, cpu0, mon, r, ref, build, gold, mode)
        unchanged()
        need(
            prior.sha(a.input_dir / "pack.bin") == r["pack_sha256"]
            and files == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
            "input closure",
        )
    finally:
        mon.end.set()
        thread.join(timeout=6)
        need(not thread.is_alive(), "monitor cleanup")
        mon.check()
    need((cg / "cgroup.procs").read_text().split() == [str(os.getpid())], "unreaped child")
    arms = r["arms"]
    total = sum(row["expected_pread_bytes"] for row in arms)
    need(total == 727203840 and mon.count >= 2, "work conservation")
    r.update(
        assessment=decide.evaluate(timing_input(arms)),
        full_tile_sha256=cpu0.GOLD,
        expected_aligned_service_bytes=total,
        logical_service_bytes=sum(v["logical_weight_bytes"] for v in arms),
        total_output_bytes=sum(v["tile_bytes"] for v in arms),
        prepared_pack_bytes=prep["pack_size_bytes"],
        monitor_samples=mon.count,
        monitor_sha256=prior.sha(mon.raw),
        peak_bytes=int((cg / "memory.peak").read_text()),
        swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
        io_stat=(cg / "io.stat").read_text(),
        cpu_stat=(cg / "cpu.stat").read_text(),
        cgroup_final=bounded.cgroup_state(),
        child_processes_at_cleanup=0,
    )
    need(prior.footprint(dest) + len(json.dumps(r)) * 3 + 65536 < 32 * cpu0.MIB, "output budget")
    r["status"] = PASS


def synthetic_gate(build, directory, prior):
    digest = build["numerical_fixture_sha256"]
    prior.sealed_file(directory / "test-kernel-graph", build["fixture_executable_sha256"])
    need(
        set(build["synthetic_rows"]) == set(build["fixture_stdout"]) == {"r0", "off", "on"},
        "synthetic modes",
    )
    for mode in ("r0", "off", "on"):
        expected = (
            f"PASS_PARKED_MMID_GRAPH cases=192 skipped={24 if mode == 'on' else 0} rows_bytes=98304"
        )
        file = directory / f"fixture-{mode}.bin"
        need(
            build["fixture_stdout"][mode].strip() == expected
            and build["synthetic_rows"][mode] == {"bytes": 98304, "sha256": digest}
            and file.stat().st_size == 98304,
            "synthetic graph coverage",
        )
        prior.sealed_file(file, digest)


def check_build(a, prior, service, build, git):
    commit = build["commit"]
    need(re.fullmatch("[0-9a-f]{40}", commit), "build commit")
    subprocess.run(
        [*git, "merge-base", "--is-ancestor", commit, a.expect_head], check=True, timeout=8
    )
    sources = build["sources"]
    need(
        set(sources) == {"build.py", "kernel.py", "test_kernel_graph.cpp", "protocol.md"},
        "compiled sources",
    )
    for name, digest in sources.items():
        need(
            service.frozen(a.checkout, HERE.parent / name, commit) == digest
            and service.frozen(a.checkout, HERE.parent / name, a.expect_head) == digest,
            "compiled source identity: " + name,
        )
    synthetic_gate(build, a.build_dir, prior)


def main(a):
    os.umask(0o077)
    need(re.fullmatch(r"tesy-[a-z0-9][a-z0-9-]{1,110}", a.unit), "unit name")
    a.study = str(STUDY)
    dest = a.new_output_dir
    if not a.in_scope:
        dest.mkdir(mode=0o700)
    c = cpu0_module()
    service = c.module(
        HERE.parents[1] / "packed_layer_service/profile.py", "parked_service", c.SERVICE
    )
    prior = c.module(HERE.parents[1] / "packed_real_layer/profile.py", "parked_tile", c.LAYER)
    start = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        unit=a.unit,
        arms=[],
        started_utc=service.clock(),
        cap_bytes=c.CAP,
        stop_bytes=c.STOP,
        swap_max_bytes=0,
    )
    try:
        if a.in_scope:
            scoped(a, prior, service, c, r, start)
        else:
            cmd = [
                "/usr/bin/systemd-run",
                "--user",
                "--scope",
                "--quiet",
                "--collect",
                "--unit=" + a.unit,
                "-p",
                f"MemoryMax={c.CAP}",
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
                HERE,
                *sys.argv[1:],
                "--in-scope",
            ]
            with (dest / "scope.stdout").open("xb") as so, (dest / "scope.stderr").open("xb") as se:
                rc = subprocess.run(cmd, stdout=so, stderr=se, timeout=728).returncode
            r["scope_rc"] = rc
            detail = dest / "detail.json"
            if detail.is_file():
                d = json.loads(detail.read_bytes())
                r.update(
                    detail_sha256=prior.sha(detail),
                    inner_status=d["status"],
                    reason=d.get("reason"),
                    arms_started=sum(v["child_started"] for v in d["arms"]),
                    assessment=d.get("assessment"),
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
            supervisor_sha256=prior.sha(HERE),
        )
        prior.put(dest / ("detail.json" if a.in_scope else "receipt.json"), r)
    print(r["status"], flush=True)
    return int(r["status"] != PASS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("checkout", "build-dir", "input-dir", "libs", "c55-receipt", "new-output-dir"):
        parser.add_argument("--" + key, type=lambda x: Path(x).absolute(), required=True)
    for key in ("expect-head", "unit", "build-sha256", "input-sha256", "c55-sha256"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--in-scope", action="store_true", help=argparse.SUPPRESS)
    sys.exit(main(parser.parse_args()))
