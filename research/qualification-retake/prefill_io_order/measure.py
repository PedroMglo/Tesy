"""Two C135 wave-0 cohorts. A single NVMe, four workers, no model runtime."""

import argparse
import ctypes
import fcntl
import hashlib
import json
import mmap
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "nvme_admission/io_pair"))
import run as io  # noqa: E402
from c118_start_inventory import collect, require_inventory  # noqa: E402

ORDER = ("fifo", "sorted", "sorted", "fifo")
CAP = 384 * 2**20
STOP = 352 * 2**20
PLAN_SHA = "ee32fdcb24cb3144c85b16e35e1e0402d5048ff329d6729ae52226c51fa0dd51"
POWER = {"source": "AC", "profile": "performance"}
require = io.require
now = time.monotonic_ns


def scope():
    cg = io.cgroup_state()
    require(
        cg
        and (cg["memory_high"], cg["memory_max"], cg["swap_max"], cg["swap_current"])
        == (CAP, CAP, 0, 0),
        "384 MiB zero-swap scope required",
    )
    require(
        cg["memory_peak"] < STOP
        and not any(cg["events_local"][k] for k in ("high", "max", "oom", "oom_kill")),
        "resource event",
    )
    return cg["memory_peak"]


def sample(policy):
    scope()
    require(not io.concurrent(), "competing job")
    obs = io.live_sample()
    io.validate_sample(obs, policy=policy, cap_bytes=CAP, expected_power=POWER)
    require(io.host_pressure() < 10, "host pressure")
    require(obs["thermal"]["cpu_tctl_c"] < policy["cpu"]["warning_c"], "CPU thermal warning")
    if policy["gpu"]["warning_c"] is not None:
        require(obs["gpu"]["temperature_c"] < policy["gpu"]["warning_c"], "GPU thermal warning")
    for s in policy["nvme"]:
        if s["warning_c"] is not None:
            require(
                obs["thermal"]["nvme_composite_by_sensor"][s["sensor"]] < s["warning_c"],
                "NVMe thermal warning",
            )
    return obs


def ordered_indices(jobs, mode):
    order = list(range(len(jobs)))
    if mode == "sorted":
        nd = sum(j["role"] == "demand" for j in jobs)
        order[:nd] = sorted(order[:nd], key=lambda i: jobs[i]["ranges"][0][0])
    else:
        require(mode == "fifo", "unknown treatment")
    return order


def cohort(pool, fd, jobs, buffers, mode, reader=io.one_job):
    # All jobs became eligible under one native producer lock. Timed code enqueues
    # them before opening the gate. Four existing threads then consume one FIFO.
    queue = deque()
    mutex = threading.Lock()
    ready = threading.Barrier(5, timeout=5)
    gate = threading.Event()
    records = [None] * len(jobs)
    pops = []
    abort = threading.Event()

    def worker():
        try:
            ready.wait()
            require(gate.wait(5), "release timeout")
            while not abort.is_set():
                with mutex:
                    if not queue:
                        break
                    i = queue.popleft()
                    pops.append(i)
                spans = reader(fd, jobs[i]["ranges"], buffers[i])
                records[i] = (spans, now(), threading.get_native_id())
        except BaseException:
            abort.set()
            raise

    futures = [pool.submit(worker) for _ in range(4)]
    ready.wait()
    start = now()
    order = ordered_indices(jobs, mode)
    queue.extend(order)
    release = now()
    gate.set()
    for f in futures:
        f.result()
    drain = now()
    require(pops == order and all(records), "incomplete dispatch")
    rows = []
    for j, (spans, finished, worker_id) in zip(jobs, records, strict=True):
        require(
            len(spans) == 3 and all(release <= a <= b <= finished for a, b in spans),
            "bad pread spans",
        )
        rows.append(
            dict(
                expert=j["expert"],
                role=j["role"],
                worker_id=worker_id,
                finish_ns=finished - start,
                read_spans_ns=[[a - start, b - start] for a, b in spans],
            )
        )
    reads = [(a, b) for item in rows for a, b in item["read_spans_ns"]]
    return dict(
        order_indices=order,
        release_cost_ns=release - start,
        demand_ns=max(j["finish_ns"] for j in rows if j["role"] == "demand"),
        drain_ns=drain - start,
        read_worker_ns=sum(b - a for a, b in reads),
        read_union_ns=io.union_ns(reads),
        jobs=rows,
    )


def arm(fd, path, ident, disk, plan, buffers, pool, policy, mode, baseline, progress):
    def check_file():
        st = os.fstat(fd)
        require(
            io.stat_id(path)
            == ident
            == [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns],
            "file/FD changed",
        )

    check_file()
    samples = [sample(policy)]
    last_sample = now()
    start = now()
    before = io.diskstats(disk)
    groups = []
    digests = {}
    for g in plan["groups"]:
        progress["layer"] = g["layer"]
        device_start = io.diskstats(disk)
        group = cohort(pool, fd, g["jobs"], buffers, mode)
        device_stop = io.diskstats(disk)
        group["disk_delta"] = {k: device_stop[k] - device_start[k] for k in device_start}
        group["layer"] = g["layer"]
        require(group["drain_ns"] < 2_000_000_000, "cohort exceeded 2 s")
        groups.append(group)
        for i, j in enumerate(g["jobs"]):
            for n, (offs, size, aligned, _) in enumerate(j["ranges"]):
                with memoryview(buffers[i][n][0])[offs - aligned : offs - aligned + size] as data:
                    h = hashlib.sha256(data).hexdigest()
                key = f"{g['layer']}/{j['expert']}/{n}"
                require(
                    key not in digests and (baseline is None or baseline[key] == h),
                    "payload SHA mismatch",
                )
                digests[key] = h
        progress["verified_components"] = len(digests)
        samples.append(sample(policy))
        stamp = now()
        require(stamp - last_sample < 2_000_000_000, "telemetry gap >2s")
        last_sample = stamp
    after = io.diskstats(disk)
    wall = now() - start
    require(
        wall < 15_000_000_000 and len(digests) == 96 and sum(g["drain_ns"] for g in groups) <= wall,
        "arm deadline/conservation",
    )
    check_file()
    return dict(
        mode=mode,
        groups=groups,
        samples=samples,
        payload_sha256=digests,
        wall_ns=wall,
        disk_delta={k: after[k] - before[k] for k in before},
        disk_scope="whole device; includes inter-cohort hash and sampling",
        **{k: sum(g[k] for g in groups) for k in ("demand_ns", "drain_ns", "read_worker_ns")},
    )


def decision(arms):
    pairs = []
    for a, b in ((0, 1), (3, 2)):
        ref, can = arms[a], arms[b]
        values = {k: 1 - can[k] / ref[k] for k in ("demand_ns", "drain_ns", "read_worker_ns")}
        group_gains = [
            1 - c["demand_ns"] / r["demand_ns"]
            for r, c in zip(ref["groups"], can["groups"], strict=True)
        ]
        eligible = (
            values["demand_ns"] >= 0.051150
            and values["read_worker_ns"] >= 0.051150
            and min(group_gains) > 0
            and values["drain_ns"] >= -0.05
        )
        pairs.append(
            dict(
                fifo_arm=a + 1,
                sorted_arm=b + 1,
                gains=values,
                group_demand_gains=group_gains,
                eligible=eligible,
            )
        )
    count = sum(p["eligible"] for p in pairs)
    return ("GO" if count == 2 else "INCONCLUSIVE" if count == 1 else "NO_GO"), pairs


def execute(placement_path, policy_path, out, commit):
    root = HERE.parents[2]

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, timeout=4
        ).strip()

    require(
        git("rev-parse", "HEAD") == commit
        and len(commit) == 40
        and not git("status", "--porcelain"),
        "clean freeze HEAD required",
    )
    require(
        io.sha256(HERE / "schedule.json") == PLAN_SHA
        and io.sha256(placement_path) == io.PLACEMENT_SHA,
        "schedule or placement digest",
    )
    place = json.loads(placement_path.read_text())
    require(
        place["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and place["source_sha256"] == place["destination_direct_reread"]["sha256"] == io.TARGET,
        "placement identity",
    )
    path = Path(place["working_copy"]).resolve(strict=True)
    ident = io.stat_id(path)
    require(
        ident[2] == 63_387_346_208 and ident[4] <= placement_path.stat().st_mtime_ns,
        "file modified since digest",
    )
    disk = io.disk(path, "nvme")
    policy = json.loads(policy_path.read_text())
    require(
        policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0],
        "C55",
    )
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    require(0 <= age <= 3600, "C55 older than one hour")
    plan = json.loads((HERE / "schedule.json").read_text())
    require(plan["aligned_bytes_per_arm"] * 4 < 2**31, "2 GiB family budget")
    io.save(
        out / "freeze.json",
        dict(
            commit=commit,
            tree=git("rev-parse", "HEAD^{tree}"),
            schedule_sha256=PLAN_SHA,
            protocol_sha256=io.sha256(HERE / "protocol.md"),
            placement_sha256=io.PLACEMENT_SHA,
            policy_sha256=io.sha256(policy_path),
            file_stat=ident,
            order=ORDER,
            utc=datetime.now(UTC).isoformat(),
        ),
    )
    (out / "raw").mkdir(mode=0o700)
    inv = dict(policy=policy, cap_bytes=CAP, expected_power=POWER)
    inventory = collect(out, "c135-prefill-io-order", **inv, sample=lambda: sample(policy))
    require_inventory(out, "c135-prefill-io-order", inventory, **inv)
    io.save(out / "inventory-receipt.json", inventory)
    arms = []
    with ExitStack() as stack:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
        stack.callback(os.close, fd)
        require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_DIRECT, "missing direct I/O")
        max_len = max(r[3] for g in plan["groups"] for j in g["jobs"] for r in j["ranges"])
        buffers = []
        for _ in range(max(len(g["jobs"]) for g in plan["groups"])):
            parts = []
            for _ in range(3):
                buf = stack.enter_context(mmap.mmap(-1, max_len))
                addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
                require(addr % 4096 == 0, "unaligned buffer")
                for page in range(0, max_len, 4096):
                    buf[page] = 0
                parts.append((buf, addr))
            buffers.append(parts)
        pool = stack.enter_context(ThreadPoolExecutor(max_workers=4))
        scope()
        for n, mode in enumerate(ORDER, 1):
            progress = dict(arm=n, mode=mode, verified_components=0)
            try:
                result = arm(
                    fd,
                    path,
                    ident,
                    disk,
                    plan,
                    buffers,
                    pool,
                    policy,
                    mode,
                    arms[0]["payload_sha256"] if arms else None,
                    progress,
                )
            except Exception as exc:
                io.save(out / f"failed-{n}.json", dict(**progress, error=str(exc)))
                raise
            io.save(out / f"arm-{n}-{mode}.json", result)
            arms.append(result)
    status, pairs = decision(arms)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    require(size + 32000 < 2 * 2**20, "output budget")
    return dict(
        classification="MEDIDO_LOADER_ONLY",
        decision=status,
        pairs=pairs,
        group_layers=[14, 25],
        demand_jobs=17,
        preload_jobs=15,
        comparisons_per_component=3,
        logical_bytes_per_arm=plan["payload_bytes_per_arm"],
        aligned_bytes_per_arm=plan["aligned_bytes_per_arm"],
        model_forwards=0,
        gpu_work=0,
        cgroup_peak_bytes=scope(),
        energy_j=None,
        arms=[
            {
                k: a[k]
                for k in (
                    "mode",
                    "demand_ns",
                    "read_worker_ns",
                    "drain_ns",
                    "wall_ns",
                    "disk_delta",
                )
            }
            for a in arms
        ],
        payload_manifest_sha256=hashlib.sha256(
            json.dumps(arms[0]["payload_sha256"], sort_keys=True).encode()
        ).hexdigest(),
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("placement", "policy", "new-output-dir"):
        cli.add_argument("--" + name, type=Path, required=True)
    cli.add_argument("--commit", required=True)
    a = cli.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)

    def timeout(*_):
        raise TimeoutError("125 s limit")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(125)
    try:
        result = execute(a.placement, a.policy, out, a.commit)
    except Exception as exc:
        result = dict(
            decision="FAIL",
            error=f"{type(exc).__name__}: {exc}",
            model_forwards=0,
            completed_arms=sorted(p.name for p in out.glob("arm-*.json")),
        )
    signal.alarm(0)
    io.save(out / "receipt.json", result)
    print(json.dumps(result, indent=2))
    return int(result["decision"] == "FAIL")


if __name__ == "__main__":
    sys.exit(main())
