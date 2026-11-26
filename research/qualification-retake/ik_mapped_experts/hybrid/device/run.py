"""Run the tiny CUDA routing and placement fixture in a bounded physical family."""

import argparse
import hashlib
import json
import os
import resource
import select
import subprocess
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
HYBRID = HERE.parent
QUAL = HYBRID.parents[1]
INTEGRATED = QUAL / "phase_fd/integrated"
OLD = run_path(str(INTEGRATED / "t1_manager_cuda/device/run.py"))
COLD = run_path(str(INTEGRATED / "cold_read_fixture/runner.py"))
IO = COLD["io"]
INV = COLD["c135"]
ACTIVE = run_path(str(INTEGRATED / "t1_native_sink/measure.py"))["active_sample"]
need = COLD["need"]
load = COLD["load"]
sha = IO.sha256
save = OLD["save"]
GIB = 1 << 30
CAP = 2 * GIB
STOP = 1536 << 20
VRAM = 1536
MODES = ("RESIDENT", "BANK9", "BANK7")
TINY = "3771d5de5067095852a0132324c16b01e39c2b999082d4a3b6165e13aff90644"
ENV49 = "7e9d0efb4c9bac6ef88d0de0003e8643fc14f4f9942c72a8101e2c166b8b1729"


def c55(a):
    witness = load(a.c55, a.c55_sha256)
    policy = load(a.c55.parent / "resource-policy.json", witness["canonical_policy_sha256"])
    snap = json.loads((a.c55.parent / "snapshot.json").read_bytes())
    samples = a.c55.parent / "samples.jsonl"
    need(sha(samples) == witness["window_sha256"], "C55 sample digest")
    rows = [json.loads(line) for line in samples.read_text().splitlines()]
    need(len(rows) == witness["samples"] >= 61 and 60 <= witness["span_s"] < 100, "C55 coverage")
    need(
        IO.derive_policy(snapshot=snap) == policy
        and policy["memory"] == witness["canonical_memory"]
        and witness["runner_sha256"] == sha(QUAL / "nvme_admission/window.py")
        and witness["protocol_sha256"] == sha(QUAL / "nvme_admission/protocolo.md"),
        "C55 sources or canonical derivation",
    )
    reasons = set(witness["reason"])
    admitted = witness["status"] == "PASS_RESOURCE_WINDOW_ONLY" and not reasons
    capacity_only = (
        witness["status"] == "NOT_ADMITTED"
        and bool(reasons)
        and reasons <= {"HOST_CAP_PLUS_RESERVE_UNAVAILABLE", "C55_CAP_UNAVAILABLE"}
    )
    caps = [witness[k]["cap_max_bytes"] for k in ("memory", "canonical_memory")]
    need((admitted or capacity_only) and min(caps) >= CAP, "fixture capacity or resource gate")
    return policy, datetime.fromisoformat(rows[-1]["utc"])


def relevant(name):
    return name.startswith(("libcuda", "libcublas", "libnvidia", "libggml", "libllama"))


def mapped(path, loader_paths, driver_paths):
    observed = set()
    for line in path.read_text().splitlines():
        cols = line.split(None, 5)
        if len(cols) == 6 and cols[-1].startswith("/"):
            p = Path(cols[-1])
            if relevant(p.name):
                need(" (deleted)" not in str(p) and "/stubs/" not in str(p), "deleted/stub mapping")
                observed.add(str(p.resolve(strict=True)))
    required = {v for v in loader_paths if relevant(Path(v).name)}
    need(required <= observed <= (required | driver_paths), "unverified accelerator VMA")
    return sorted(observed)


def seal(a, prepared):
    b = load(a.client / "receipt.json", a.client_sha256)
    lib = load(a.dso / "receipt.json", a.dso_sha256)
    cpu = load(a.cpu / "receipt.json", a.cpu_sha256)
    need(
        lib["status"] == "PASS_IK_SM89_LINK_ONLY"
        and b["status"] == "PASS_TINY_HYBRID_CLIENT_BUILD"
        and b["variant"] == "cuda"
        and b["dso_build_sha256"] == a.dso_sha256
        and cpu["status"] == "PASS_TINY_HYBRID_CPU_REFERENCE"
        and cpu["mode"] == "CPU"
        and cpu["model_sha256"] == TINY,
        "sealed CPU control and CUDA builds",
    )
    exe = a.client / "hybrid-client"
    tiny = a.tiny.resolve(strict=True)
    need(b["binary"] == exe.name and sha(exe) == b["binary_sha256"], "client ELF")
    need(tiny.stat().st_size == 3390592 and sha(tiny) == TINY, "tiny fixture")
    need(b["sources"]["grade.py"] == sha(HYBRID / "client/grade.py"), "grade identity")
    expected = {str((a.dso / n).resolve(strict=True)): h for n, h in lib["libraries"].items()}
    desc = load(a.env49, ENV49)
    for name, target in desc["driver_aliases"].items():
        need((Path(desc["driver_dir"]) / name).resolve(strict=True) == Path(target), "driver alias")
    native = b["native_search"]
    need(
        native == ":".join(b["explicit_search"])
        and hashlib.sha256(native.encode()).hexdigest() == b["native_search_sha256"],
        "loader search path",
    )
    loader_paths = {v["file"]: v["sha256"] for v in b["closure"].values()}
    need(all(loader_paths.get(p) == v for p, v in expected.items()), "client uses other ik DSOs")
    for item in lib["closure"].values():
        need(all(loader_paths.get(p) == v for p, v in item.items()), "different CUDA dependency")
    driver_paths = set(desc["driver_aliases"].values())
    # Hash the actual files once before C118. Check their full stat identities again after drain.
    sealed = dict(loader_paths)
    for path in driver_paths:
        sealed[path] = desc["files"][path]["sha256"]
    sealed[str(exe)] = b["binary_sha256"]
    sealed[str(tiny)] = TINY
    stats = {}
    for p, h in sealed.items():
        path = Path(p)
        stats[p] = IO.stat_id(path)
        if prepared is None:
            need(sha(path) == h and IO.stat_id(path) == stats[p], "provider digest or drift")
        else:
            need(
                prepared["provider_identity"].get(p) == {"stat": stats[p], "sha256": h},
                "provider differs from preflight",
            )
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=native,
        CUDA_VISIBLE_DEVICES="0",
        CUDA_CACHE_DISABLE="1",
        OMP_NUM_THREADS="8",
        GGML_MOE_PREFETCH_AHEAD="0",
    )
    return (
        exe,
        tiny,
        env,
        {p: {"stat": s, "sha256": sealed[p]} for p, s in stats.items()},
        set(loader_paths),
        driver_paths,
        cpu,
    )


def sample_arm(mode, parent, args, policy, end, exe, tiny, env, paths, drivers, result):
    age = (datetime.now(UTC) - end).total_seconds()
    need(0 <= age < 3300, "stale C55 before C118")
    run_id = args.unit + "-" + mode.lower()
    target = parent / mode
    target.mkdir(mode=0o700)
    kw = dict(policy=policy, cap_bytes=CAP, expected_power=INV.POWER)

    def idle():
        obs = IO.monitor(policy)["observation"]
        need(obs["gpu"]["used_mib"] < VRAM, "idle GPU memory")
        return obs

    (parent / "raw").mkdir(mode=0o700, exist_ok=True)
    inv = INV.collect(parent, run_id, **kw, sample=idle)
    INV.require_inventory(parent, run_id, inv, **kw, max_age_s=3)
    result["admission"] = inv
    native = target / "native"
    stdout, stderr = target / "stdout", target / "stderr"

    def child_limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))

    with ExitStack() as stack:
        rx, tx = os.pipe()
        ack_rx, ack_tx = os.pipe()
        for fd in (rx, ack_tx):
            stack.callback(os.close, fd)
        out = stack.enter_context(stdout.open("xb"))
        err = stack.enter_context(stderr.open("xb"))
        journal = stack.enter_context((target / "monitor.jsonl").open("x"))
        result["launch_utc"] = datetime.now(UTC).isoformat()
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                [exe, mode, tiny, native],
                env=env | dict(TESY_TEST_TX=str(tx), TESY_TEST_RX=str(ack_rx)),
                pass_fds=(tx, ack_rx),
                stdout=out,
                stderr=err,
                start_new_session=True,
                preexec_fn=child_limits,
            )
        finally:
            os.close(tx)
            os.close(ack_rx)
        result.update(starts=1, pid=proc.pid)
        last = started
        stage = 0
        probes = []

        def sample(phase, attempt=1):
            nonlocal last
            data = IO.monitor(policy, sample=lambda: ACTIVE(proc.pid, policy["gpu"]["uuid"], False))
            now = time.monotonic()
            row = data["observation"]
            data.update(phase=phase, attempt=attempt, elapsed_s=now - started)
            probes.append(row["gpu"]["used_mib"])
            journal.write(json.dumps(data, sort_keys=True, allow_nan=False) + "\n")
            journal.flush()
            need(
                now - last <= 3 and now - started < 30 and probes[-1] < VRAM,
                "deadline or GPU limit",
            )
            last = now
            return row["gpu_owners"]

        try:
            while proc.poll() is None:
                need(time.monotonic() - started < 30, "child deadline")
                if select.select([rx], [], [], 0.15)[0]:
                    marker = os.read(rx, 1)
                    if not marker:
                        break
                    need(stage < 3 and marker == (b"E", b"A", b"F")[stage], "handoff order")
                    OLD["owner_handoff"](marker, proc.pid, sample)
                    if marker in (b"A", b"F"):
                        result[marker.decode() + "_providers"] = mapped(
                            Path(f"/proc/{proc.pid}/maps"),
                            paths,
                            drivers,
                        )
                    os.write(ack_tx, marker)
                    stage += 1
                elif time.monotonic() - last > 0.4:
                    sample("running")
                need(
                    sum(f.stat().st_size for f in parent.rglob("*") if f.is_file()) < 64 << 20,
                    "raw limit",
                )
            result["returncode"] = proc.wait(timeout=max(0.001, 30 - (time.monotonic() - started)))
            need(result["returncode"] == 0 and stage == 3, "child or handoff failed")
            need(not sample("after_exit"), "compute owner after exit")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)
            result.update(
                child_gone=proc.poll() is not None,
                returncode=proc.returncode,
                stdout_sha256=sha(stdout),
                stderr_sha256=sha(stderr),
                wall_s=time.monotonic() - started,
                monitor_sha256=sha(target / "monitor.jsonl"),
                observed_handoffs=stage,
                sampled_vram_mib_max=max(probes, default=None),
            )
    mapped(native / "maps", paths, drivers)
    return native


def run(a, out, r):
    head = subprocess.check_output(["git", "-C", HERE, "rev-parse", "HEAD"], text=True).strip()
    need(
        head == a.commit
        and not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]),
        "unfrozen checkout",
    )
    r.update(
        commit=head,
        unit=a.unit,
        tree=subprocess.check_output(
            ["git", "-C", HERE, "rev-parse", "HEAD^{tree}"], text=True
        ).strip(),
        client_sha256=a.client_sha256,
        cpu_sha256=a.cpu_sha256,
        dso_sha256=a.dso_sha256,
        c55_sha256=a.c55_sha256,
        model_sha256=TINY,
        protocol_sha256=sha(HERE / "protocol.md"),
        supervisor_sha256=sha(__file__),
        arms={},
        energy_j=None,
        product_requests=0,
    )
    prepared = None
    if a.execute:
        need(a.prepared and a.prepared_sha256, "execution requires independent preflight")
        prepared = load(a.prepared, a.prepared_sha256)
        need(
            prepared["status"] == "PREPARED_ONLY"
            and all(
                r[k] == prepared[k]
                for k in (
                    "client_sha256",
                    "dso_sha256",
                    "cpu_sha256",
                    "c55_sha256",
                    "tree",
                    "commit",
                    "model_sha256",
                    "protocol_sha256",
                    "supervisor_sha256",
                )
            ),
            "different preflight",
        )
        r["prepared_sha256"] = a.prepared_sha256
    exe, tiny, env, stats, paths, drivers, cpu = seal(a, prepared)
    r["provider_identity"] = stats
    grade = run_path(str(HYBRID / "client/grade.py"))
    cpu_dir = a.cpu / "native"
    cpu_stdout, cpu_stderr = a.cpu / "stdout", a.cpu / "stderr"
    need(
        sha(cpu_stdout) == cpu["stdout_sha256"] and sha(cpu_stderr) == cpu["stderr_sha256"],
        "CPU logs",
    )
    cpu_grade = grade["check_arm"]("CPU", cpu_stdout.read_text(), cpu_stderr.read_text(), cpu_dir)
    need(cpu_grade == cpu["grade"], "CPU control changed")
    policy, end = c55(a)
    if not a.execute:
        r["status"] = "PREPARED_ONLY"
        return
    need(a.unit.startswith("tesy-ik-hybrid-device-"), "wrong unit prefix")
    IO.CAP, IO.STOPS = CAP, STOP
    IO.scope()
    initial = IO.cgroup_state()
    cg = Path("/sys/fs/cgroup") / initial["path"].lstrip("/")
    need(
        cg.name == a.unit + ".scope"
        and cg.parent.name == "app.slice"
        and set((cg / "cgroup.procs").read_text().split()) == {str(os.getpid())},
        "scope identity",
    )
    profile = run_path(str(QUAL / "packed_layer_service/profile.py"))
    provider, unchanged = profile["monitor_provider"](SimpleNamespace(token=IO.stat_id))
    r["monitor_provider"] = provider
    resident = resident_grade = None
    for mode in MODES:
        unchanged()
        s = {"starts": 0}
        r["arms"][mode] = s
        folder = sample_arm(mode, out, a, policy, end, exe, tiny, env, paths, drivers, s)
        parent = folder.parent
        current = grade["check_arm"](
            mode, (parent / "stdout").read_text(), (parent / "stderr").read_text(), folder
        )
        s["grade"] = current
        if mode == "RESIDENT":
            resident, resident_grade = folder, current
            s["cpu_comparison"] = grade["compare_arms"](cpu_dir, cpu_grade, folder, current)
        else:
            s["resident_comparison"] = grade["compare_arms"](
                resident, resident_grade, folder, current
            )
            if mode == "BANK9":
                need(
                    current["logits_sha256"] == resident_grade["logits_sha256"]
                    and current["ordered_top4_sha256"] == resident_grade["ordered_top4_sha256"],
                    "nine-slot numerical or routing difference",
                )
        save(parent / "grade.json", s)
    unchanged()
    need(
        all(IO.stat_id(Path(k)) == identity["stat"] for k, identity in stats.items()),
        "provider drift",
    )
    r.update(max_scope_bytes=IO.scope(), swap_peak_bytes=int((cg / "memory.swap.peak").read_text()))
    need(r["swap_peak_bytes"] == 0, "peak swap")
    r["status"] = "PASS_TINY_HYBRID_GPU_FIXTURE"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("c55", "client", "dso", "cpu", "tiny", "env49", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    for k in ("c55-sha256", "client-sha256", "dso-sha256", "cpu-sha256", "commit"):
        parser.add_argument("--" + k, required=True)
    parser.add_argument("--unit", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--prepared-sha256")
    a = parser.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = {"status": "FAIL_PRESERVED"}
    try:
        run(a, out, r)
    except Exception as error:
        r["reason"] = f"{type(error).__name__}: {error}"
    finally:
        if a.execute:
            try:
                state = IO.cgroup_state()
                need(state and Path(state["path"]).name == a.unit + ".scope", "exit scope identity")
                cg = Path("/sys/fs/cgroup") / state["path"].lstrip("/")
                r.update(
                    max_scope_bytes=state["memory_peak"],
                    swap_peak_bytes=int((cg / "memory.swap.peak").read_text()),
                    memory_events_local=state["events_local"],
                )
                r["raw_sha256"] = {
                    str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()
                }
            except Exception as error:
                r["status"] = "FAIL_PRESERVED"
                r["final_inventory_error"] = str(error)
        save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
