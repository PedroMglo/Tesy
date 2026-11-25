"""Time the fixed expert transfers into synchronous C269 CPU and CUDA slots."""

import argparse
import ctypes
import json
import mmap
import os
import signal
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RAM = HERE.parent / "t1_primary_layout"
ram = run_path(str(RAM / "bench.py"))
need, clock = ram["need"], ram["CLOCK"]
WEIGHT, WIDTH, WINDOW = (ram[k] for k in ("WEIGHT", "WIDTH", "WINDOW"))
PREVIOUS = "2a90de37b6ae809e9de63cd47ddabac192e743a2c44b037a0f472aa626d208bb"


def address(buf):
    return ctypes.addressof(ctypes.c_char.from_buffer(buf))


def byte_address(data):
    func = ctypes.pythonapi.PyBytes_AsString
    func.argtypes = (ctypes.py_object,)
    func.restype = ctypes.c_void_p
    return func(data)


def deliver(sinks, tier, slot, source, layout, record, offset, gold_ptr, scratch, gguf, pack):
    ptr = address(scratch)
    if source == "ram":
        for role in range(3):
            sinks.put(tier, role, slot, gold_ptr + role * WEIGHT)
        return 0
    need(source == "disk", "worker source")
    if layout == "pack":
        ram["read_at"](pack, scratch, WINDOW, offset)
        for role in range(3):
            sinks.put(tier, role, slot, ptr + role * WEIGHT)
        return WINDOW
    need(layout == "gguf", "layout")
    n = 0
    for role, r in enumerate(record["gguf"]):
        ram["read_at"](gguf, scratch, r["count"], r["aligned"])
        sinks.put(tier, role, slot, ptr + r["logical"] - r["aligned"])
        n += r["count"]
    return n


def group(pool, sinks, cell, sample, fds, pointers, entries, scratch, output, poison):
    policy = "lru_ram" if cell in "AB" else "evict_backed_first"
    layout = "gguf" if cell in "AC" else "pack"
    layer = sample["site"][2]
    tier = "cpu" if layer < 25 else "cuda"
    tasks = []
    records = []
    hits = 0
    sources = sample["paths"][policy]
    for slot, (expert, source) in enumerate(zip(sample["demand"], sources, strict=True)):
        key = (layer, expert)
        offset, r = entries[key]
        records.append(r)
        initial_ptr = pointers[key] if source == "primary" else poison
        for role in range(3):
            sinks.put(tier, role, slot, initial_ptr + role * WEIGHT)
        if source != "primary":
            tasks.append(
                (sinks, tier, slot, source, layout, r, offset, pointers[key], scratch[slot], *fds)
            )
            hits += source == "ram"
    sinks.sync(tier)
    begin = clock()
    futures = [pool.submit(deliver, *task) for task in tasks]
    n = sum(f.result() for f in futures)
    sinks.sync(tier)
    elapsed = clock() - begin
    get_ptr = address(output)
    for i, r in enumerate(records):
        for role in range(3):
            sinks.get(tier, role, i, get_ptr + role * WEIGHT)
        sinks.sync(tier)
        ram["check_payload"](output, r)
    return dict(
        ns=elapsed,
        read_bytes=n,
        served=len(records),
        dispatched=len(tasks),
        tier=tier,
        bank_bytes=hits * WIDTH,
        set_bytes=len(tasks) * WIDTH,
        verified_components=3 * len(records),
    )


def execute(a, result, out):
    cold = run_path(str(HERE.parent / "cold_read_fixture/runner.py"))
    io, c135, load = cold["io"], cold["c135"], cold["load"]

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(cold["ROOT"]), *args], text=True, timeout=10
        ).strip()

    need(
        git("rev-parse", "HEAD") == a.commit and not git("status", "--porcelain"), "clean checkout"
    )
    result.update(commit=a.commit, tree=git("rev-parse", "HEAD^{tree}"), unit=a.unit, arm=a.arm)
    baseline = load(a.ram_dir / "receipt.json", PREVIOUS)
    plan = load(a.plan, ram["PLAN"])
    seal = load(RAM / "plan-receipt.json", ram["SEAL"])
    entries = ram["checked_plan"](plan, seal)
    need(
        baseline["status"] == "PASS_RAM_TRANSPORT"
        and baseline["model_stat"] == io.stat_id(a.model)
        and baseline["partial_stat"] == io.stat_id(a.partial)
        and io.disk(a.model, "nvme") == io.disk(a.partial, "nvme")
        and io.mount(a.model)[1] == io.mount(a.partial)[1] == "btrfs",
        "source identity",
    )
    io.CAP, io.STOPS = 2 * 2**30, 1856 * 2**20
    io.scope()
    need(io.cgroup_state()["path"].endswith("/" + a.unit + ".scope"), "scope name")
    gate = load(a.c55, a.c55_sha256)
    policy = load(a.c55.with_name("resource-policy.json"), gate["canonical_policy_sha256"])
    need(
        gate["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not gate["reason"]
        and gate["selected_stat"] == baseline["model_stat"]
        and policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0]
        and 0
        <= (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
        < 3300,
        "C55 admission",
    )
    profile = run_path(str(cold["QUAL"] / "packed_layer_service/profile.py"))
    provider, unchanged = profile["monitor_provider"](SimpleNamespace(token=io.stat_id))
    need(provider == baseline["monitor_provider"], "monitor identity")
    first = None
    if a.arm == 2:
        first = load(a.first_dir / "receipt.json", a.first_sha256)
        need(
            first["status"] == "PASS_NATIVE_SINKS"
            and first["arm"] == 1
            and first["commit"] == a.commit
            and first["monitor_provider"] == provider
            and first["partial_stat"] == io.stat_id(a.partial),
            "independent process chain",
        )
    result.update(
        plan_sha256=ram["PLAN"],
        ram_receipt_sha256=PREVIOUS,
        c55_sha256=a.c55_sha256,
        model_stat=baseline["model_stat"],
        partial_stat=baseline["partial_stat"],
        monitor_provider=provider,
        resource_cap=io.CAP,
        first_sha256=a.first_sha256,
    )
    (out / "raw").mkdir()
    kw = dict(policy=policy, cap_bytes=io.CAP, expected_power=c135.POWER)
    inv = c135.collect(out, a.unit, **kw, sample=lambda: io.monitor(policy)["observation"])
    c135.require_inventory(out, a.unit, inv, **kw)
    io.save(out / "inventory.json", inv)
    result["inventory_sha256"] = io.sha256(out / "inventory.json")
    read_bytes = 0
    verified = 0
    blocks = []
    with ExitStack() as outer:
        samples = outer.enter_context((out / "raw/service-monitor.jsonl").open("x"))
        last = clock()

        def monitor(force=False):
            nonlocal last
            delta = clock() - last
            need(delta <= 5_000_000_000, "monitor gap")
            if force or delta >= 500_000_000:
                s = io.monitor(policy)
                need(s["observation"]["gpu"]["used_mib"] < 1536, "local GPU cap")
                cold["append_row"](samples, s)
                last = clock()

        monitor(True)
        with ExitStack() as s:
            gguf = ram["direct"](s, a.model, os.O_RDONLY)
            pack = ram["direct"](s, a.partial, os.O_RDONLY)
            for fd, path, ident in (
                (gguf, a.model, baseline["model_stat"]),
                (pack, a.partial, baseline["partial_stat"]),
            ):
                cold["check_fd"](fd, path, ident)
            gold, digest, prep_ns = ram["prepare"](plan, pack, gguf, None, False, monitor)
            need(digest == baseline["partial_sha256"], "pack readback")
            result.update(partial_sha256=digest, prepare_ns=prep_ns)
            pointers = {k: byte_address(v) for k, v in gold.items()}
            poison = bytes([0xA5]) * WIDTH
            output = s.enter_context(mmap.mmap(-1, WIDTH))
            scratch = [
                s.enter_context(mmap.mmap(-1, WINDOW))
                for _ in range(max(len(w["demand"]) for w in plan["samples"].values()))
            ]
            for buf in [output, *scratch]:
                for pos in range(0, len(buf), 4096):
                    buf[pos] = 0
                monitor()
            native = run_path(str(HERE / "native.py"))
            start = clock()
            sinks = native["NativeSinks"](s, a.map)
            result["native_init_ns"] = clock() - start
            result["native"] = sinks.receipt
            monitor(True)
            pool = s.enter_context(ThreadPoolExecutor(max_workers=4))
            latch = threading.Barrier(4)
            jobs = [pool.submit(latch.wait, 3) for _ in range(4)]
            need({j.result() for j in jobs} == set(range(4)), "worker team")
            logs = s.enter_context((out / "raw/blocks.jsonl").open("x"))
            for b, order in enumerate(("ABCD", *ram["ORDER"])):
                block = {}
                for cell in order:
                    waves = {}
                    for key in ram["STRATA"]:
                        row = group(
                            pool,
                            sinks,
                            cell,
                            plan["samples"][key],
                            (gguf, pack),
                            pointers,
                            entries,
                            scratch,
                            output,
                            byte_address(poison),
                        )
                        waves[key] = row
                        read_bytes += row["read_bytes"]
                        verified += row["verified_components"]
                        need(
                            read_bytes + 2 * len(entries) * WINDOW + 2**20 < 8_000_000_000,
                            "read budget",
                        )
                        monitor()
                    block[cell] = waves
                    cold["append_row"](logs, dict(block=b, cell=cell, waves=waves))
                    monitor(True)
                if b:
                    blocks.append(block)
            sinks.end_check()
            for fd, path, ident in (
                (gguf, a.model, baseline["model_stat"]),
                (pack, a.partial, baseline["partial_stat"]),
            ):
                cold["check_fd"](fd, path, ident)
            need(
                verified == 1740 and read_bytes == baseline["arm_read_bytes"], "same verified work"
            )
            unchanged()
            cleanup = clock()
        result["fixture_cleanup_ns"] = clock() - cleanup
        monitor(True)
    result.update(
        status="PASS_NATIVE_SINKS",
        contrasts=ram["contrast"](blocks),
        arm_read_bytes=read_bytes,
        verified_components=verified,
        gpu_transfers=True,
        transformer_forwards=0,
        peak_bytes=io.scope(),
        block_sha256=io.sha256(out / "raw/blocks.jsonl"),
        monitor_sha256=io.sha256(out / "raw/service-monitor.jsonl"),
    )
    if first is not None:
        need(
            first["native"] == json.loads(json.dumps(result["native"])),
            "backend identity across processes",
        )
        result["both_processes_pass"] = (
            result["contrasts"]["passes"] and first["contrasts"]["passes"]
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("unit", "commit", "c55-sha256", "first-sha256"):
        p.add_argument("--" + name, required=name != "first-sha256")
    for name in (
        "model",
        "partial",
        "plan",
        "c55",
        "ram-dir",
        "map",
        "first-dir",
        "new-output-dir",
    ):
        p.add_argument("--" + name, type=Path, required=name != "first-dir")
    p.add_argument("--arm", type=int, choices=(1, 2), required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)

    def alarm(*_):
        raise TimeoutError("arm deadline")

    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(225)
    result = {}
    try:
        need((a.arm == 1) == (a.first_dir is None) == (a.first_sha256 is None), "arm continuity")
        execute(a, result, a.new_output_dir)
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    signal.alarm(0)
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
