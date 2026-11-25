"""Time the previously qualified CPU0 FFN; verify the private archive without loading GGML."""

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
Q = HERE.parents[1]
REAL = "7b7f543d76d4c3a7f13200fa962a07d8ab31595ea821392f7c6982362b8a3b54"
REAL_PROFILE = "3e3039e0f9f6b4277f604a7cc631858a10f0b1892cf3d95993af36e569160551"
MODES = ("ORIGINAL", "MMID", "FUSION")
BLOCKS = tuple(tuple(MODES[int(i)] for i in k) for k in ("012", "120", "201", "210", "102", "021"))
ORDER = MODES + sum(BLOCKS, ())
PASS = "PASS_UNCOUNTED_FUSION_TIMING_FAMILY"
TILE_BYTES = 368640
GOLD = "bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24"


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(path):
    need(path.is_file() and not path.is_symlink(), "file identity: " + path.name)
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load(name, path, pin=None):
    if pin:
        need(digest(path) == pin, "source identity: " + path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def timings(rows, decide):
    need(
        decide.MODES == MODES and decide.BLOCKS == BLOCKS and decide.ORDER == ORDER[3:],
        "evaluator schedule",
    )
    need(tuple(x["mode"] for x in rows) == ORDER, "incomplete family")
    selected = []
    for i, r in enumerate(rows):
        phase = "qualification" if i < 3 else "timing"
        block = None if i < 3 else (i - 3) // 3
        need(
            r["run_index"] == i
            and r["phase"] == phase
            and r["block"] == block
            and r["child_started"] is True
            and r["returncode"] == 0
            and r["status"] == "PASS_TILE"
            and r["tile_sha256"] == GOLD
            and r["tile_bytes"] == TILE_BYTES,
            "arm identity",
        )
        if phase == "timing":
            selected.append({"mode": r["mode"], "graph_ns": r["graph_ns"]})
    return decide.evaluate(selected)


def gate(a, rec, mods, svc, prior):
    real, mm, c = mods
    git = ["/usr/bin/git", "--no-optional-locks", "-C", a.checkout]
    need(
        HERE == a.checkout / a.study
        and re.fullmatch("[0-9a-f]{40}", a.expect_head)
        and prior.command([*git, "rev-parse", "HEAD"]) == a.expect_head
        and not prior.command([*git, "status", "--porcelain"]),
        "clean checkout",
    )
    historical = prior.sealed_json(a.real_receipt, REAL)
    need(
        historical["status"] == real.PASS
        and historical["decision"] == "GO_TIMING_FIXTURE"
        and [v["counter_delta"] for v in historical["arms"]] == [None, 0, 0, 7]
        and {v["tile_sha256"] for v in historical["arms"]} == {GOLD}
        and historical["input_sha256"] == a.input_sha256,
        "numerical gate or window",
    )
    ref = prior.sealed_json(Q / "cpu0_suffix/physical-r01/receipt.json", mm.REFERENCE)
    build = prior.sealed_json(a.build_dir / "receipt.json", a.build_sha256)
    need(
        build["status"] == "PASS_C269_UNCOUNTED_FUSION_BUILD"
        and build["counted_cpu_sha256"] == historical["candidate_cpu_sha256"]
        and build["numeric_build_sha256"] == historical["numerical_receipt_sha256"]
        and build["binary_sha256"] == ref["executable_sha256"]
        and build["real_receipt_sha256"] == REAL
        and set(build["source_sha256"]) == {"build.py", "protocol.md"}
        and build["suffix_build_receipt_sha256"] == real.ORIGINAL_BUILD
        and build["counter_symbols_absent"] is True
        and build["counter_only_delta"] is True
        and build["candidate_cpu_sha256"] != build["counted_cpu_sha256"],
        "uncounted build",
    )
    for k in (historical["commit"], build["commit"]):
        need(re.fullmatch("[0-9a-f]{40}", k), "build commit")
        subprocess.run(
            [*git, "merge-base", "--is-ancestor", k, a.expect_head], check=True, timeout=8
        )
    for name, h in build["source_sha256"].items():
        need(
            Path(name).name == name
            and svc.frozen(a.checkout, HERE / name, build["commit"]) == h
            and svc.frozen(a.checkout, HERE / name, a.expect_head) == h,
            "compiled source",
        )
    exe = a.build_dir / "suffix-layer"
    prior.sealed_file(exe, build["binary_sha256"])
    environments = {}
    for mode in MODES:
        env, providers = mm.settings(
            a, prior, ref, build, "ORIGINAL" if mode == "ORIGINAL" else "ON"
        )
        if mode != "ORIGINAL":
            env["TESY_CPU_PARKED_FUSION"] = str(int(mode == "FUSION"))
        resolved = prior.command(["/usr/bin/ldd", exe], env)
        need(
            "not found" not in resolved
            and not re.search(r"lib(cuda|nvidia|llama|ggml-cuda)", resolved),
            "unexpected dependency",
        )
        picked = [
            Path(s.split()[2]).resolve(strict=True)
            for s in resolved.splitlines()
            if s.strip().startswith("libggml") and " => " in s
        ]
        need(
            len(picked) == 2 and set(picked) == {v[0].resolve() for v in providers.values()},
            "GGML loader",
        )
        environments[mode] = env, providers
    rec.update(
        commit=a.expect_head,
        tree=prior.command([*git, "rev-parse", "HEAD^{tree}"]),
        source_sha256={
            n: svc.frozen(a.checkout, HERE / n, a.expect_head)
            for n in ("protocol.md", "profile.py", "decision.py")
        },
        real_sha256=REAL,
        build_sha256=a.build_sha256,
        executable_sha256=build["binary_sha256"],
        candidate_cpu_sha256=build["candidate_cpu_sha256"],
        original_cpu_sha256=build["original_cpu_sha256"],
        base_sha256=build["base_sha256"],
        counter_symbols_absent=True,
    )
    return ref, exe, environments


def arm(a, i, r, exe, runtime, mon, mm, c, svc, prior, ref, gold):
    mode = ORDER[i]
    env, providers = runtime
    folder = a.new_output_dir / f"{i:02d}-{mode}"
    folder.mkdir()
    native = folder / "native"
    row = dict(
        mode=mode,
        run_index=i,
        phase="qualification" if i < 3 else "timing",
        block=None if i < 3 else (i - 3) // 3,
        status="FAIL_PRESERVED",
        child_started=False,
        started_utc=svc.clock(),
        suffix_env=env["TESY_CPU_SUFFIX"],
        mmid_env=env.get(mm.MODE_ENV),
        fusion_env=env.get("TESY_CPU_PARKED_FUSION"),
    )
    r["arms"].append(row)
    proc = None
    try:
        prior.sealed_file(exe, r["executable_sha256"])
        for path, h in providers.values():
            prior.sealed_file(path, h)
        mon.check()
        if i == 0:
            age = (
                dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(r["c118"]["last_utc"])
            ).total_seconds()
            need(0 <= age <= 3, "stale C118")
        start = time.monotonic()
        with (folder / "stdout").open("xb") as so, (folder / "stderr").open("xb") as se:
            proc = subprocess.Popen(
                [exe, a.input_dir, "OFF", native],
                env=env,
                cwd=a.checkout,
                stdout=so,
                stderr=se,
                start_new_session=True,
            )
            row.update(pid=proc.pid, child_started=True)
            while proc.poll() is None:
                mon.check()
                need(
                    time.monotonic() - start < 180
                    and prior.footprint(a.new_output_dir) < 32 * c.MIB,
                    "child budget",
                )
                try:
                    proc.wait(timeout=0.15)
                except subprocess.TimeoutExpired:
                    pass
        mon.check()
        row.update(spawn_to_observed_exit_s=time.monotonic() - start, returncode=proc.returncode)
        need(proc.returncode == 0 and row["spawn_to_observed_exit_s"] < 180, "native exit/time")
        raw = json.loads((folder / "stdout").read_bytes())
        need(not any(k.startswith("counter_") for k in raw), "counted client")
        row.update(mm.native_row(prior, c, ref, raw, providers, native, gold))
        row["status"] = "PASS_TILE"
    finally:
        if proc is not None:
            mon.bounded.stop_own_group(proc)
            row["returncode"] = proc.returncode
        for fname in ("stdout", "stderr"):
            if (folder / fname).is_file():
                row[fname + "_sha256"] = digest(folder / fname)
        row["closed_utc"] = svc.clock()
        prior.put(folder / "receipt.json", row)


def run(a):
    os.umask(0o077)
    a.study = str(HERE.relative_to(a.checkout))
    need(re.fullmatch("tesy-[a-z0-9][a-z0-9-]{1,110}", a.unit), "unit")
    dest = a.new_output_dir
    dest.mkdir(mode=0o700)
    real = load("fusion_real", HERE.parent / "real_tile/profile.py", REAL_PROFILE)
    mm, c, prior, svc = real.modules()
    start = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        arms=[],
        unit=a.unit,
        started_utc=svc.clock(),
        cap_bytes=c.CAP,
        stop_bytes=c.STOP,
        swap_max_bytes=0,
    )
    try:
        ref, exe, environments = gate(a, r, (real, mm, c), svc, prior)
        decide = load("timing_gate", HERE / "decision.py", r["source_sha256"]["decision.py"])
        _, initial = svc.inputs(a, prior, r)
        with (a.input_dir / "ffn_moe_out-0.bin").open("rb") as f:
            f.seek(TILE_BYTES)
            gold = f.read(TILE_BYTES)
        need(hashlib.sha256(gold).hexdigest() == GOLD, "C266 FFN tile")
        r["monitor_provider"], unchanged = svc.monitor_provider(prior)
        (dest / "raw").mkdir()
        guard, policy, bounded, cg = svc.admit(a, prior, Q / "parked_mmid", r, dest)
        mon = svc.Monitor(guard, policy, bounded, cg, dest / "raw/samples.jsonl", start)
        worker = threading.Thread(target=mon.run, daemon=True)
        worker.start()
        try:
            for i, mode in enumerate(ORDER):
                unchanged()
                need(
                    initial == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
                    "input changed",
                )
                arm(a, i, r, exe, environments[mode], mon, mm, c, svc, prior, ref, gold)
            unchanged()
            need(
                prior.sha(a.input_dir / "pack.bin") == r["pack_sha256"]
                and initial == {p.name: prior.token(p) for p in a.input_dir.iterdir()},
                "input closure",
            )
        finally:
            mon.end.set()
            worker.join(timeout=6)
            need(not worker.is_alive(), "monitor cleanup")
            r.update(
                monitor_samples=mon.count,
                monitor_sha256=digest(mon.raw) if mon.raw.is_file() else None,
                peak_bytes=int((cg / "memory.peak").read_text()),
                swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
                child_processes_at_cleanup=len((cg / "cgroup.procs").read_text().split()) - 1,
                cgroup_final=bounded.cgroup_state(),
                io_stat=(cg / "io.stat").read_text(),
            )
            mon.check()
            need((cg / "cgroup.procs").read_text().split() == [str(os.getpid())], "unreaped child")
        rows = r["arms"]
        r.update(
            expected_aligned_service_bytes=sum(v["expected_pread_bytes"] for v in rows),
            total_output_bytes=sum(v["tile_bytes"] for v in rows),
            assessment=timings(rows, decide),
        )
        need(
            r["expected_aligned_service_bytes"] == 1388298240
            and r["total_output_bytes"] == 7741440
            and mon.count >= 2
            and prior.footprint(dest) + 3 * len(json.dumps(r)) + 65536 < 32 * c.MIB,
            "family budget",
        )
        r["status"] = PASS
    except Exception as error:
        r.update(status="FAIL_PRESERVED", reason=f"{type(error).__name__}: {error}")
    finally:
        r.update(
            elapsed_s=time.monotonic() - start,
            closed_utc=svc.clock(),
            supervisor_sha256=digest(Path(__file__)),
        )
        prior.put(dest / "receipt.json", r)
    print(r["status"], flush=True)
    return int(r["status"] != PASS)


def verify(closed, receipt_sha):
    """Check all private outputs by content and return a public manifest without host paths."""
    terminal = closed / "receipt.json"
    need(digest(terminal) == receipt_sha, "terminal receipt")
    r = json.loads(terminal.read_bytes())
    need(
        r["status"] in (PASS, "FAIL_PRESERVED")
        and digest(HERE / "profile.py") == r["supervisor_sha256"],
        "unfinished or foreign family",
    )
    summary = {k: r[k] for k in ("status", "elapsed_s", "supervisor_sha256")}
    summary["receipt_sha256"] = receipt_sha
    if r["status"] != PASS:
        summary["failed_reason_sha256"] = hashlib.sha256(r["reason"].encode()).hexdigest()
        summary["preserved_arms"] = [
            {
                k: x.get(k)
                for k in (
                    "run_index",
                    "mode",
                    "status",
                    "returncode",
                    "child_started",
                    "stdout_sha256",
                    "stderr_sha256",
                )
            }
            for x in r["arms"]
        ]
        return summary
    for n in ("profile.py", "protocol.md", "decision.py"):
        need(digest(HERE / n) == r["source_sha256"][n], "source closure")
    need(r["real_sha256"] == REAL and r["counter_symbols_absent"] is True, "missing gate")
    from_real = load("archive_real", HERE.parent / "real_tile/profile.py", REAL_PROFILE)
    mm, c, _, _ = from_real.modules()
    reference_path = Q / "cpu0_suffix/physical-r01/receipt.json"
    need(digest(reference_path) == mm.REFERENCE, "CPU0 reference")
    reference = json.loads(reference_path.read_bytes())
    need(reference["executable_sha256"] == r["executable_sha256"], "wrong harness")
    decide = load("archive_evaluator", HERE / "decision.py", r["source_sha256"]["decision.py"])
    assessment = timings(r["arms"], decide)
    need(assessment == r["assessment"], "unreproducible assessment")
    archive = []
    for i, (mode, row) in enumerate(zip(ORDER, r["arms"], strict=True)):
        folder = closed / f"{i:02d}-{mode}"
        need(json.loads((folder / "receipt.json").read_bytes()) == row, "arm receipt")
        for n in ("stdout", "stderr"):
            need(digest(folder / n) == row[n + "_sha256"], "arm stream")
        raw = json.loads((folder / "stdout").read_bytes())
        expected = c.clocks(raw, "OFF")
        need(
            all(row[k] == v for k, v in expected.items())
            and raw["clock"] == "CLOCK_MONOTONIC"
            and raw["marked_graph_threads"] == 0
            and raw["cb_eval_registered"] is False
            and not any(s.startswith("counter_") for s in raw),
            "graph clock/observer",
        )
        for k in ("graph_fingerprint", "graph_nodes", "backend_splits"):
            need(row[k] == raw[k] == reference[k], "graph topology")
        for k, v in {
            "graph_waves": 8,
            "active_waves": 1,
            "graph_mmid_nodes": 24,
            "unique_loads": 5,
            "expected_weight_sets": 15,
            "expected_pread_bytes": 66109440,
            "joined_workers": 4,
            "logical_weight_bytes": 66096000,
            "full_ffn_values": 92160,
        }.items():
            need(row[k] == raw[k] == v, "work conservation")
        tile = folder / "native/tile.f32"
        need(tile.stat().st_size == row["tile_bytes"] and digest(tile) == GOLD, "archived tile")
        cpu = r["original_cpu_sha256"] if mode == "ORIGINAL" else r["candidate_cpu_sha256"]
        need(
            row["provider_sha256"] == {"cpu": cpu, "base": r["base_sha256"]}
            and row["suffix_env"] == "OFF"
            and row["mmid_env"] == (None if mode == "ORIGINAL" else "1")
            and row["fusion_env"] == (None if mode == "ORIGINAL" else str(int(mode == "FUSION"))),
            "kernel assignment",
        )
        archive.append(
            {
                k: row[k]
                for k in (
                    "run_index",
                    "phase",
                    "block",
                    "mode",
                    "graph_ns",
                    "tile_bytes",
                    "tile_sha256",
                    "stdout_sha256",
                    "stderr_sha256",
                )
            }
        )
    journal = closed / "raw/samples.jsonl"
    inv = r["c118"]
    need(re.fullmatch("tesy-[a-z0-9][a-z0-9-]{1,110}", r["unit"]), "unit name")
    inventory = closed / "raw" / (r["unit"] + ".start-inventory.jsonl")
    need(
        digest(journal) == r["monitor_sha256"]
        and digest(inventory) == inv["sha256"]
        and len(inventory.read_bytes().splitlines()) == inv["sample_count"]
        and inv["duration_s"] >= 60,
        "C118 and live monitor",
    )
    samples = [json.loads(line) for line in journal.read_bytes().splitlines()]
    need(
        len(samples) == r["monitor_samples"] >= 2
        and all(not v["compute_pids"] and v["gap_s"] <= 3 for v in samples)
        and r["peak_bytes"] < r["stop_bytes"] == 3584 * 2**20
        and r["swap_peak_bytes"] == 0
        and r["child_processes_at_cleanup"] == 0
        and r["total_output_bytes"] == len(ORDER) * TILE_BYTES
        and r["expected_aligned_service_bytes"] == len(ORDER) * 66109440,
        "closure and resources",
    )
    summary.update(
        {
            k: r[k]
            for k in (
                "commit",
                "tree",
                "build_sha256",
                "real_sha256",
                "executable_sha256",
                "source_sha256",
                "input_sha256",
                "c55_sha256",
                "pack_sha256",
                "monitor_samples",
                "monitor_sha256",
                "candidate_cpu_sha256",
                "original_cpu_sha256",
                "base_sha256",
                "total_output_bytes",
                "peak_bytes",
                "swap_peak_bytes",
                "expected_aligned_service_bytes",
                "child_processes_at_cleanup",
            )
        }
    )
    summary.update(
        arms=archive,
        assessment=assessment,
        c118={k: inv[k] for k in ("sample_count", "duration_s", "sha256")},
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    live = subs.add_parser("run")
    for key in (
        "checkout",
        "build-dir",
        "real-receipt",
        "libs",
        "input-dir",
        "c55-receipt",
        "new-output-dir",
    ):
        live.add_argument("--" + key, type=lambda s: Path(s).resolve(), required=True)
    for key in ("expect-head", "build-sha256", "input-sha256", "c55-sha256", "unit"):
        live.add_argument("--" + key, required=True)
    closed = subs.add_parser("verify")
    closed.add_argument("--closed-run", type=Path, required=True)
    closed.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args()
    if args.command == "run":
        raise SystemExit(run(args))
    print(
        json.dumps(
            verify(args.closed_run, args.receipt_sha256), sort_keys=True, indent=2, allow_nan=False
        )
    )
