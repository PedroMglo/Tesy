"""Time the sealed decode population on the two immutable NVMe sources."""

import argparse
import ctypes
import hashlib
import mmap
import os
import signal
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
INTEGRATED = next(p for p in HERE.parents if p.name == "integrated")
cold = run_path(str(INTEGRATED / "cold_read_fixture/runner.py"))
packlib = run_path(str(INTEGRATED / "t1_full_pack_service/measure.py"))
io, c135, need = cold["io"], cold["c135"], cold["need"]
clock = time.monotonic_ns
METHOD = "4b5a00e98c8798cd607fef4f42d4def09c8c1e800c74b6a98707d3bde65388df"
PLAN = "aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a"
PLAN_RECEIPT = "faa756041cab0f35b12ed06a91058e54b389582839820ea265dad69c52b19993"
PACK_PLACEMENT = "adc58125a13aa286371c127f41bf67b0ed4756e9ec2dc08bd2cb6e7ed754a000"
PASS = "PASS_DECODE_NVME_SERVICE_PAIR"
CAP, STOP = 384 << 20, 336 << 20
SIZE, WINDOW = 4406400, 13221888
PAGE = 4096
CHUNK = ((SIZE + 2 * PAGE - 2) // PAGE) * PAGE
BYTES = {"R": 10545446912, "P": 10537844736}


def specification(plan):
    groups = plan["groups"]
    need(len(groups) == 1656, "callback inventory")
    n_disk = n_bank = new = set_only_x4 = original_gguf = 0
    for idx, g in enumerate(groups):
        step, layer = divmod(idx, 36)
        need(
            (g["step"], g["position"], g["layer"], g["tile"], g["wave"], g["tier"])
            == (step, 2197 + step, layer, 1, -1, "CPU" if layer < 25 else "CUDA0")
            and g["call"] == groups[0]["call"] + step,
            "site and tier",
        )
        jobs = g["jobs"]
        need(len(jobs) <= 4 and len({j["expert"] for j in jobs}) == len(jobs), "demand")
        sets = []
        for idxj, j in enumerate(jobs):
            e = j["expert"]
            need(
                j["ordinal"] == idxj
                and 0 <= e < 128
                and 0 <= j["slot"] < 40
                and j["generation"] >= 1
                and j["source"] in ("bank", "disk")
                and j["pack_bytes"] == WINDOW
                and j["pack_offset"] == (128 * layer + e) * packlib["STRIDE"],
                "job binding",
            )
            disk = j["source"] == "disk"
            n_disk += disk
            n_bank += not disk
            ns = j["r0_same_site_set_ns"]
            if ns is None:
                new += 1
                need(not disk, "unmatched disk admission")
            else:
                need(type(ns) is int and ns >= 0, "R0 same-site SET")
            sets.append(ns or 0)
            need(len(j["components"]) == 3, "three expert matrices")
            for i, (c, role) in enumerate(
                zip(j["components"], ("gate", "down", "up"), strict=True)
            ):
                off, src, length = c["source_offset"], c["aligned_offset"], c["aligned_bytes"]
                need(
                    c["role"] == role
                    and c["size_bytes"] == SIZE
                    and 0 <= src == off // PAGE * PAGE
                    and length <= CHUNK
                    and length == (off - src + SIZE + PAGE - 1) // PAGE * PAGE
                    and src + length <= cold["MODEL_SIZE"]
                    and c["packed_relative_offset"] == i * SIZE
                    and len(bytes.fromhex(c["sha256"])) == 32,
                    "indexed range",
                )
                if disk:
                    original_gguf += length
        set_only_x4 += max(4 * max(sets, default=0), sum(sets))
    need(
        (n_disk, n_bank, new) == (797, 399, 227) and set_only_x4 // 4 == 522063311,
        "candidate counts and historical unpriced-pack floor",
    )
    need(original_gguf == BYTES["R"] and n_disk * WINDOW == BYTES["P"], "sealed byte census")
    return groups


def arena(stack):
    buffers = []
    for _ in range(4):
        buf = stack.enter_context(mmap.mmap(-1, 3 * CHUNK))
        ptr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
        need(ptr % PAGE == 0, "DIO buffer alignment")
        for p in range(0, 3 * CHUNK, PAGE):
            buf[p] = 0
        buffers.append((buf, ptr))
    return buffers


def ranges(layout, job):
    if layout == "P":
        return [(0, 0, job["pack_offset"], WINDOW)], [0]
    return [(0, 0, c["aligned_offset"], c["aligned_bytes"]) for c in job["components"]], [
        i * CHUNK for i in range(3)
    ]


def group_read(pool, fd, buffers, layout, g):
    jobs = [j for j in g["jobs"] if j["source"] == "disk"]
    row = {k: g[k] for k in ("step", "position", "call", "tile", "layer", "wave", "tier")}
    row.update(jobs=[], release_ns=0, drain_ns=0, hash_ns=0, read_worker_ns=0, read_union_ns=0)
    if not jobs:
        return row, 0
    # All workers and the caller meet before the eligible FIFO is released.
    gate, abort = threading.Event(), threading.Event()
    ready = threading.Barrier(5, timeout=5)
    lock = threading.Lock()
    queue, popped = deque(), []
    records = [None] * len(jobs)
    offsets = [ranges(layout, j) for j in jobs]

    def worker():
        try:
            ready.wait()
            need(gate.wait(5), "worker release")
            while not abort.is_set():
                with lock:
                    if not queue:
                        return
                    i = queue.popleft()
                    popped.append(i)
                extents, local_offsets = offsets[i]
                owner, ptr = buffers[i]
                spans = io.one_job(fd, extents, [(owner, ptr + p) for p in local_offsets])
                records[i] = (spans, threading.get_native_id())
        except BaseException:
            abort.set()
            raise

    work = [pool.submit(worker) for _ in range(4)]
    ready.wait()
    start = clock()
    queue.extend(range(len(jobs)))
    release = clock()
    gate.set()
    for f in work:
        f.result()
    end = clock()
    need(popped == list(range(len(jobs))), "FIFO dispatch")
    spans = []
    hash_start = clock()
    for i, (job, (times, tid)) in enumerate(zip(jobs, records, strict=True)):
        slices = []
        for ci, c in enumerate(job["components"]):
            offset = (
                c["packed_relative_offset"]
                if layout == "P"
                else (ci * CHUNK + c["source_offset"] - c["aligned_offset"])
            )
            with memoryview(buffers[i][0])[offset : offset + SIZE] as data:
                digest = hashlib.sha256(data).hexdigest()
            need(digest == c["sha256"], f"payload {g['step']}/{g['layer']}/{job['expert']}/{ci}")
            slices.append(digest)
        need(
            all(release <= a <= b <= end for a, b in times)
            and len(times) == (1 if layout == "P" else 3),
            "observed READ sequence",
        )
        row["jobs"].append(
            {
                **{k: job[k] for k in ("ordinal", "expert", "slot", "generation")},
                "worker": tid,
                "read_spans_ns": [[a - start, b - start] for a, b in times],
                "component_sha256": slices,
            }
        )
        spans.extend(times)
    row.update(
        hash_ns=clock() - hash_start,
        release_ns=release - start,
        drain_ns=end - start,
        read_worker_ns=sum(b - a for a, b in spans),
        read_union_ns=io.union_ns(spans),
    )
    return row, sum(r[3] for group_ranges, _ in offsets for r in group_ranges)


def auth_sources(a, c55):
    place = cold["load"](a.placement, io.PLACEMENT_SHA)
    need(
        place["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and place["source_sha256"] == place["destination_direct_reread"]["sha256"] == io.TARGET,
        "R0 NVMe copy",
    )
    path = Path(place["working_copy"])
    identity = io.stat_id(path)
    need(
        path.resolve(strict=True) == path
        and not path.is_symlink()
        and identity == c55["selected_stat"]
        and identity[2] == cold["MODEL_SIZE"]
        and identity[4] <= a.placement.stat().st_mtime_ns,
        "C55 GGUF identity",
    )
    ref = packlib["FullPack"](a.pack_placement, PACK_PLACEMENT)
    paths = {"R": path, "P": ref.path}
    ids = {"R": identity, "P": ref.stat}
    disks = {io.disk(p, "nvme") for p in paths.values()}
    need(
        len(disks) == 1 and all(io.mount(p)[1] == "btrfs" for p in paths.values()),
        "same NVMe Btrfs",
    )
    return paths, ids, disks.pop()


def execute(a, out, result):
    order = "RP" if a.process == 1 else "PR"
    need(io.sha256(HERE / "protocol.md") == METHOD, "method")
    need(
        io.call("git", "-C", str(cold["ROOT"]), "rev-parse", "HEAD") == a.commit
        and not io.call("git", "-C", str(cold["ROOT"]), "status", "--porcelain"),
        "clean freeze",
    )
    tree = io.call("git", "-C", str(cold["ROOT"]), "rev-parse", "HEAD^{tree}")
    selection = cold["load"](a.plan.with_name("receipt.json"), PLAN_RECEIPT)
    need(
        selection["status"] == "PASS_ORDERED_DECODE_TRANSPORT_PLAN"
        and selection["plan_sha256"] == a.plan_sha256 == PLAN,
        "sealed population",
    )
    plan = cold["load"](a.plan, a.plan_sha256)
    groups = specification(plan)
    io.CAP, io.STOPS = CAP, STOP
    io.scope()
    need(io.cgroup_state()["path"].endswith("/" + a.unit + ".scope"), "scope identity")
    c55 = cold["load"](a.c55, a.c55_sha256)
    policy = cold["load"](a.c55.with_name("resource-policy.json"), c55["canonical_policy_sha256"])

    def current():
        need(
            0
            <= (
                datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])
            ).total_seconds()
            <= 3600,
            "C55 expiry",
        )

    current()
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and io.operational_session_ready(policy)[0]
        and policy == io.derive_policy(snapshot=policy["snapshot"]),
        "resource policy",
    )
    paths, ids, disk = auth_sources(a, c55)
    mon = run_path(str(cold["QUAL"] / "packed_layer_service/profile.py"))
    provider, unchanged = mon["monitor_provider"](SimpleNamespace(token=io.stat_id))
    sources = {
        k: dict(
            stat=v,
            layout_sha256=io.TARGET if k == "R" else packlib["PACK"],
            placement_sha256=io.PLACEMENT_SHA if k == "R" else PACK_PLACEMENT,
        )
        for k, v in ids.items()
    }
    if a.process == 2:
        first = cold["load"](a.prior_receipt, a.prior_sha256)
        need(
            first["status"] == PASS
            and first["order"] == "RP"
            and first["process"] == 1
            and first["plan_sha256"] == a.plan_sha256
            and first["commit"] == a.commit
            and first["sources"] == sources
            and first["tree"] == tree
            and first["monitor_provider"] == provider
            and first["c55_sha256"] == a.c55_sha256,
            "first pair authority",
        )
    else:
        need(a.prior_receipt is a.prior_sha256 is None, "unexpected predecessor")
    result.update(
        process=a.process,
        order=order,
        plan_sha256=a.plan_sha256,
        commit=a.commit,
        tree=tree,
        protocol_sha256=METHOD,
        plan_receipt_sha256=PLAN_RECEIPT,
        program_sha256=io.sha256(Path(__file__)),
        c55_sha256=a.c55_sha256,
        prior_receipt_sha256=a.prior_sha256,
        sources=sources,
        monitor_provider=provider,
        device=disk.parent.name,
        filesystem="btrfs",
        cap_bytes=CAP,
        stop_bytes=STOP,
        arms={},
    )
    raw = out / "raw"
    raw.mkdir(mode=0o700)
    kw = dict(policy=policy, cap_bytes=CAP, expected_power=c135.POWER)
    inventory = c135.collect(out, a.unit, **kw, sample=lambda: io.monitor(policy)["observation"])
    c135.require_inventory(out, a.unit, inventory, **kw)
    io.save(out / "inventory.json", inventory)
    result["inventory_sha256"] = io.sha256(out / "inventory.json")
    current()
    with ExitStack() as stack:
        handles = {}
        for k, path in paths.items():
            fd = os.open(path, os.O_RDONLY | os.O_DIRECT | os.O_NOFOLLOW)
            stack.callback(os.close, fd)
            cold["check_fd"](fd, path, ids[k])
            handles[k] = fd
        buffers = arena(stack)
        workers = stack.enter_context(ThreadPoolExecutor(max_workers=4))
        telemetry = stack.enter_context((raw / "telemetry.jsonl").open("x"))
        last = clock()

        def monitor():
            nonlocal last
            tic = clock()
            need(tic - last < 3_000_000_000, "telemetry gap")
            unchanged()
            cold["append_row"](telemetry, io.monitor(policy))
            last = clock()
            need(last - tic < 3_000_000_000, "monitor duration")
            return last - tic

        for layout in order:
            start = clock()
            monitor_ns = monitor()
            before = io.diskstats(disk)
            totals = Counter()
            with (raw / (layout + ".jsonl")).open("x") as logs:
                for g in groups:
                    row, count = group_read(workers, handles[layout], buffers, layout, g)
                    cold["append_row"](logs, row)
                    totals["requested_bytes"] += count
                    totals["components"] += 3 * len(row["jobs"])
                    for k in ("drain_ns", "read_worker_ns", "read_union_ns", "hash_ns"):
                        totals[k] += row[k]
                    if clock() - last >= 800_000_000:
                        monitor_ns += monitor()
            after = io.diskstats(disk)
            monitor_ns += monitor()
            elapsed = clock() - start
            need(
                totals["requested_bytes"] == BYTES[layout] and totals["components"] == 2391,
                "full transport population",
            )
            residual = elapsed - totals["drain_ns"] - totals["hash_ns"] - monitor_ns
            need(residual >= 0, "wall accounting")
            result["arms"][layout] = dict(
                **totals,
                groups_sha256=io.sha256(raw / (layout + ".jsonl")),
                payload_bytes=SIZE * totals["components"],
                wall_ns=elapsed,
                monitor_ns=monitor_ns,
                residual_ns=residual,
                disk_delta={k: after[k] - before[k] for k in before},
            )
        for k in order:
            cold["check_fd"](handles[k], paths[k], ids[k])
        cleanup = clock()
    result["cleanup_ns"] = clock() - cleanup
    result["telemetry_sha256"] = io.sha256(raw / "telemetry.jsonl")
    result["cgroup_peak_bytes"] = io.scope()
    need(
        sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) < 32 * 2**20 - 32768,
        "output cap",
    )
    result["status"] = PASS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("commit", "unit", "plan-sha256", "c55-sha256", "prior-sha256"):
        parser.add_argument("--" + k, required=not k.startswith("prior"))
    for k in ("plan", "c55", "placement", "pack-placement", "prior-receipt", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=not k.startswith("prior"))
    parser.add_argument("--process", type=int, choices=(1, 2), required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)

    def timeout(*_):
        raise TimeoutError("240 s process deadline")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(240)
    result = dict(status="FAIL_PRESERVED", model_forwards=0, gpu_compute=0)
    try:
        execute(a, a.new_output_dir, result)
    except Exception as exc:
        result.update(reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
        io.save(a.new_output_dir / "receipt.json", result)
    print(result["status"], result.get("reason", ""))
    return int(result["status"] != PASS)


if __name__ == "__main__":
    raise SystemExit(main())
