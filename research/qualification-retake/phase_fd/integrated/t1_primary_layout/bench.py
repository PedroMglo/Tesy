"""Paired native NVMe transport to CPU memory on four real, preselected groups."""

import argparse
import hashlib
import json
import mmap
import os
import signal
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
CLOCK = time.monotonic_ns
PLAN = "761efff70fc046f5810974ab7656fe90f893e3a3a2af8461693103769d7f2b76"
SEAL = "02961fa8ffd49d4373ea66c57d5c2bf27973b8429b9ac1e0e1128266de63a999"
WEIGHT = 4406400
WIDTH = 3 * WEIGHT
WINDOW = 13221888
ORDER = ("ABDC", "BCAD", "CDBA", "DACB")
STRATA = ("148_cpu", "148_cuda", "decode_cpu", "decode_cuda")


def need(test, message):
    if not test:
        raise ValueError(message)


def read_at(fd, buffer, size, offset):
    with memoryview(buffer)[:size] as view:
        need(os.preadv(fd, [view], offset) == size, "short aligned read")


def check_payload(buf, record):
    with memoryview(buf) as source:
        for i, entry in enumerate(record["gguf"]):
            need(
                hashlib.sha256(source[i * WEIGHT : (i + 1) * WEIGHT]).hexdigest()
                == entry["sha256"],
                "canonical weight checksum",
            )


def deliver(source, layout, record, partial_offset, gold, target, scratch, gguf_fd, stage_fd):
    if source == "ram":
        target[:] = gold
        return 0
    need(source == "disk", "dispatch must have a source")
    if layout == "pack":
        read_at(stage_fd, scratch, WINDOW, partial_offset)
        with memoryview(scratch)[:WIDTH] as payload:
            target[:] = payload
        return WINDOW
    need(layout == "gguf", "layout")
    returned = 0
    for i, component in enumerate(record["gguf"]):
        read_at(gguf_fd, scratch, component["count"], component["aligned"])
        begin = component["logical"] - component["aligned"]
        with memoryview(scratch)[begin : begin + WEIGHT] as value:
            target[i * WEIGHT : (i + 1) * WEIGHT] = value
        returned += component["count"]
    return returned


def checked_plan(plan, seal):
    need(
        plan["weight_window"] == WINDOW
        and seal["distinct_records"] == 29
        and seal["bound_components"] == 87
        and seal["partial_bytes"] == 29 * WINDOW
        and set(plan["samples"]) == set(STRATA),
        "plan scope",
    )
    entries = {(r["layer"], r["expert"]): (i * WINDOW, r) for i, r in enumerate(plan["entries"])}
    need(len(entries) == len(plan["entries"]) == 29, "canonical keys")
    return entries


def direct(stack, path, flags):
    fd = os.open(path, flags | os.O_DIRECT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    stack.callback(os.close, fd)
    return fd


def prepare(plan, stage, model, external, create, monitor):
    gold = {}
    prepared_hash = hashlib.sha256()
    t = CLOCK()
    with ExitStack() as stack:
        target = stack.enter_context(mmap.mmap(-1, WIDTH))
        scratch = stack.enter_context(mmap.mmap(-1, WINDOW))
        verify = stack.enter_context(mmap.mmap(-1, WINDOW))
        for i, r in enumerate(plan["entries"]):
            offset = i * WINDOW
            if create:
                read_at(external, scratch, WINDOW, r["pack_offset"])
                check_payload(scratch, r)
                with memoryview(scratch) as v:
                    need(os.pwritev(stage, [v], offset) == WINDOW, "short stage write")
            read_at(stage, verify, WINDOW, offset)
            check_payload(verify, r)
            prepared_hash.update(verify)
            deliver("disk", "gguf", r, offset, None, target, scratch, model, stage)
            check_payload(target, r)
            with memoryview(verify)[:WIDTH] as packed:
                need(packed == target, "canonical GGUF differs from staged weights")
            gold[r["layer"], r["expert"]] = target[:]
            monitor()
    if create:
        os.fsync(stage)
    return gold, prepared_hash.hexdigest(), CLOCK() - t


def group(pool, cell, sample, args, gold, entries, dest, scratch, zero):
    policy = "lru_ram" if cell in "AB" else "evict_backed_first"
    layout = "gguf" if cell in "AC" else "pack"
    layer = sample["site"][2]
    tasks, checks = [], []
    for i, (expert, source) in enumerate(
        zip(sample["demand"], sample["paths"][policy], strict=True)
    ):
        key = (layer, expert)
        offset, record = entries[key]
        dest[i][:] = gold[key] if source == "primary" else zero
        checks.append((dest[i], record))
        if source != "primary":
            tasks.append((source, layout, record, offset, gold[key], dest[i], scratch[i], *args))
    begin = CLOCK()
    futures = [pool.submit(deliver, *args) for args in tasks]
    n = sum(future.result() for future in futures)
    wall = CLOCK() - begin
    for dst, r in checks:
        check_payload(dst, r)
    return dict(ns=wall, read_bytes=n, served=len(checks), dispatched=len(tasks))


def contrast(blocks):
    rows = []
    for block in blocks:
        times = {arm: sum(v["ns"] for v in waves.values()) for arm, waves in block.items()}
        rows.append(
            dict(
                ns=times,
                layout_on_new=times["C"] - times["D"],
                policy_on_pack=times["B"] - times["D"],
                combined=times["A"] - times["D"],
                interaction=times["B"] + times["C"] - times["A"] - times["D"],
            )
        )
    effects = {
        key: dict(
            positive=sum(r[key] > 0 for r in rows),
            median_ns=statistics.median(r[key] for r in rows),
        )
        for key in ("layout_on_new", "policy_on_pack", "combined", "interaction")
    }
    passes = all(
        effects[k]["positive"] >= 3 and effects[k]["median_ns"] > 0
        for k in ("layout_on_new", "policy_on_pack", "combined")
    )
    return dict(blocks=rows, effects=effects, passes=passes)


def execute(a, out, result):
    cold = run_path(str(HERE.parent / "cold_read_fixture/runner.py"))
    io = cold["io"]
    c135 = cold["c135"]

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(cold["ROOT"]), *args], text=True, timeout=10
        ).strip()

    need(
        git("rev-parse", "HEAD") == a.commit and not git("status", "--porcelain"),
        "clean frozen source",
    )
    result.update(commit=a.commit, tree=git("rev-parse", "HEAD^{tree}"), arm=a.arm, unit=a.unit)
    load = cold["load"]
    plan = load(a.plan, PLAN)
    seal = load(HERE / "plan-receipt.json", SEAL)
    entries = checked_plan(plan, seal)
    need(
        len(a.unit) < 128
        and a.partial.parent.resolve(strict=True) == a.model.parent.resolve(strict=True)
        and a.partial.name.startswith("tesy-c289-t1-service-")
        and a.partial.suffix == ".bin",
        "partial destination",
    )
    io.CAP, io.STOPS = 2**30, 896 * 2**20
    io.scope()
    need(io.cgroup_state()["path"].endswith("/" + a.unit + ".scope"), "scope identity")
    c55 = load(a.c55, a.c55_sha256)
    policy = load(a.c55.with_name("resource-policy.json"), c55["canonical_policy_sha256"])
    placement = load(a.placement, io.PLACEMENT_SHA)
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c55["reason"]
        and placement["source_sha256"]
        == placement["destination_direct_reread"]["sha256"]
        == io.TARGET
        and a.model.samefile(placement["working_copy"])
        and c55["selected_stat"] == io.stat_id(a.model)
        and policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0]
        and 0
        <= (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
        < 3400,
        "admission, placement or age",
    )
    disk = io.disk(a.model, "nvme")
    need(
        io.mount(a.model)[1] == "btrfs" and io.disk(a.partial.parent, "nvme") == disk,
        "internal NVMe",
    )
    profile = run_path(str(cold["QUAL"] / "packed_layer_service/profile.py"))
    provider, unchanged = profile["monitor_provider"](SimpleNamespace(token=io.stat_id))
    result.update(
        c55_sha256=a.c55_sha256,
        plan_sha256=PLAN,
        monitor_provider=provider,
        device=disk.parent.name,
        model_stat=io.stat_id(a.model),
        resource_cap=io.CAP,
    )
    prior = None
    if a.arm == 2:
        prior = load(a.first_dir / "receipt.json", a.first_sha256)
        need(
            prior["status"] == "PASS_RAM_TRANSPORT"
            and prior["arm"] == 1
            and prior["commit"] == a.commit
            and prior["plan_sha256"] == PLAN
            and prior["partial_stat"] == io.stat_id(a.partial)
            and prior["monitor_provider"] == provider,
            "first arm continuity",
        )
    (out / "raw").mkdir()
    kw = dict(policy=policy, cap_bytes=io.CAP, expected_power=c135.POWER)
    inv = c135.collect(out, a.unit, **kw, sample=lambda: io.monitor(policy)["observation"])
    c135.require_inventory(out, a.unit, inv, **kw)
    io.save(out / "inventory.json", inv)
    result["inventory_sha256"] = io.sha256(out / "inventory.json")
    with ExitStack() as stack:
        samples = stack.enter_context((out / "raw/service-monitor.jsonl").open("x"))
        last = CLOCK()

        def monitor(force=False):
            nonlocal last
            delta = CLOCK() - last
            need(delta <= 5_000_000_000, "monitor gap")
            if force or delta >= 500_000_000:
                cold["append_row"](samples, io.monitor(policy))
                last = CLOCK()

        monitor(True)
        model = direct(stack, a.model, os.O_RDONLY)
        cold["check_fd"](model, a.model, result["model_stat"])
        if a.arm == 1:
            io.disk(a.pack, "usb")
            need(a.pack.stat().st_size == 61096329216, "external pack size")
            pack = direct(stack, a.pack, os.O_RDONLY)
            stage = direct(stack, a.partial, os.O_RDWR | os.O_CREAT | os.O_EXCL)
        else:
            pack = None
            stage = direct(stack, a.partial, os.O_RDONLY)
        gold, stage_digest, prep_ns = prepare(plan, stage, model, pack, a.arm == 1, monitor)
        partial_stat = io.stat_id(a.partial)
        need(
            partial_stat[2] == 29 * WINDOW
            and (not prior or stage_digest == prior["partial_sha256"]),
            "stage",
        )
        result.update(partial_stat=partial_stat, partial_sha256=stage_digest, prepare_ns=prep_ns)
        cold["check_fd"](stage, a.partial, partial_stat)
        count = max(len(v["demand"]) for v in plan["samples"].values())
        dest = [stack.enter_context(mmap.mmap(-1, WIDTH)) for _ in range(count)]
        scratch = [stack.enter_context(mmap.mmap(-1, WINDOW)) for _ in range(count)]
        for buf in [*dest, *scratch]:
            for pos in range(0, len(buf), 4096):
                buf[pos] = 0
            monitor()
        zero = bytes(WIDTH)
        pool = stack.enter_context(ThreadPoolExecutor(max_workers=4))
        barrier = threading.Barrier(4)
        starts = [pool.submit(barrier.wait, 3) for _ in range(4)]
        need({f.result() for f in starts} == set(range(4)), "four reader threads")
        allblocks = []
        log = stack.enter_context((out / "raw/blocks.jsonl").open("x"))
        read_bytes = 0
        for block, order in enumerate(("ABCD", *ORDER)):
            cells = {}
            for cell in order:
                waves = {}
                for key in STRATA:
                    row = group(
                        pool,
                        cell,
                        plan["samples"][key],
                        (model, stage),
                        gold,
                        entries,
                        dest,
                        scratch,
                        zero,
                    )
                    waves[key] = row
                    read_bytes += row["read_bytes"]
                    need(
                        read_bytes + 2 * len(entries) * WINDOW + 2**20 < 8_000_000_000,
                        "read budget",
                    )
                    monitor()
                cells[cell] = waves
                cold["append_row"](log, dict(block=block, cell=cell, waves=waves))
                monitor(True)
            if block:
                allblocks.append(cells)
        cold["check_fd"](stage, a.partial, partial_stat)
        cold["check_fd"](model, a.model, result["model_stat"])
        unchanged()
        monitor(True)
    result.update(
        status="PASS_RAM_TRANSPORT",
        contrasts=contrast(allblocks),
        block_sha256=io.sha256(out / "raw/blocks.jsonl"),
        monitor_sha256=io.sha256(out / "raw/service-monitor.jsonl"),
        arm_read_bytes=read_bytes,
        verified_components=87 * 20,
        peak_bytes=io.scope(),
        model_forwards=0,
        gpu_compute=0,
    )
    if prior is not None:
        result["both_processes_pass"] = (
            prior["contrasts"]["passes"] and result["contrasts"]["passes"]
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("commit", "unit", "c55-sha256", "first-sha256"):
        p.add_argument("--" + name, required=name != "first-sha256")
    for name in (
        "model",
        "partial",
        "pack",
        "plan",
        "placement",
        "c55",
        "first-dir",
        "new-output-dir",
    ):
        p.add_argument("--" + name, type=Path, required=name != "first-dir")
    p.add_argument("--arm", choices=(1, 2), type=int, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    result = {}

    def alarm(*_):
        raise TimeoutError("family arm timeout")

    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(170)
    try:
        need(
            (a.first_dir is None) == (a.arm == 1) and (a.first_sha256 is None) == (a.arm == 1),
            "arm order",
        )
        execute(a, a.new_output_dir, result)
    except Exception as exc:
        result.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    signal.alarm(0)
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""), flush=True)
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
