"""Compare identical C135 reads on two sealed file copies. No forward pass."""

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
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[3] / "tools")]
from c55_inventory import call  # noqa: E402
from c118_start_inventory import live_sample, validate_sample  # noqa: E402
from host_resource_policy import (  # noqa: E402
    derive_policy,
    host_pressure,
    operational_session_ready,
)
from plan import REPO, require  # noqa: E402
from run_bounded import cgroup_state, sha256  # noqa: E402
from window import concurrent, mount, save, stat_id  # noqa: E402

PLAN_SHA = "0602cda61a6c16795c1efa883ebabee0f28848ff49c202e3221fbabc6d29cc0e"
PLACEMENT_SHA = "50a35a1e5c3fde78066d1378e13dfeb89867d9970528135ff3294c6aa5bd1bf7"
TARGET = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
ORDER = ("usb", "nvme", "nvme", "usb")
CAP = 256 * 2**20
STOPS = 224 * 2**20
libc = ctypes.CDLL(None, use_errno=True)
pread = libc.pread
pread.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_longlong]
pread.restype = ctypes.c_ssize_t


def scope():
    cg = cgroup_state()
    require(
        cg
        and (cg["memory_high"], cg["memory_max"], cg["swap_max"], cg["swap_current"])
        == (CAP, CAP, 0, 0),
        "wrong 256 MiB zero-swap scope",
    )
    require(
        cg["memory_peak"] < STOPS
        and not any(cg["events_local"][k] for k in ("high", "max", "oom", "oom_kill")),
        "cgroup resource event",
    )
    return cg["memory_peak"]


def monitor(policy):
    peak = scope()
    require(not concurrent(), "concurrent build, model or transfer")
    obs = live_sample()
    validate_sample(
        obs, policy=policy, cap_bytes=CAP, expected_power={"source": "AC", "profile": "performance"}
    )
    require(
        host_pressure() < 10 and obs["thermal"]["cpu_tctl_c"] < policy["cpu"]["warning_c"],
        "CPU temperature or host pressure",
    )
    if policy["gpu"]["warning_c"] is not None:
        require(obs["gpu"]["temperature_c"] < policy["gpu"]["warning_c"], "GPU temperature")
    for nvme in policy["nvme"]:
        if nvme["warning_c"] is not None:
            require(
                obs["thermal"]["nvme_composite_by_sensor"][nvme["sensor"]] < nvme["warning_c"],
                "NVMe temperature",
            )
    return dict(utc=datetime.now(UTC).isoformat(), peak_bytes=peak, observation=obs)


def disk(path, transport):
    device = mount(path)[0].split("[")[0]
    rows = call("lsblk", "-nrs", "-o", "KNAME,TYPE,TRAN", device).splitlines()
    names = [
        r.split()[0] for r in rows if len(r.split()) == 3 and r.split()[1:] == ["disk", transport]
    ]
    require(len(names) == 1, "physical disk ancestry mismatch")
    return Path("/sys/class/block") / names[0] / "stat"


def diskstats(path):
    v = list(map(int, path.read_text().split()))
    return dict(read_sectors_512B=v[2], write_sectors_512B=v[6], busy_ms=v[9])


def one_job(fd, ranges, buffers):
    calls = []
    for (_, _, offset, n), (_buf, addr) in zip(ranges, buffers, strict=True):
        begin = time.monotonic_ns()
        returned = pread(fd, addr, n, offset)
        end = time.monotonic_ns()
        if returned != n:
            raise OSError(
                f"short/failed pread: request={n}, return={returned}, errno={ctypes.get_errno()}"
            )
        calls.append((begin, end))
    return calls


def union_ns(spans):
    end = 0
    total = 0
    for a, b in sorted(spans):
        total += max(0, b - max(end, a))
        end = max(b, end)
    return total


def arm(fd, file, identity, diskpath, plan, buffers, pool, policy, expected, progress):
    require(stat_id(file) == identity, "path changed before arm")
    require(
        [
            getattr(os.fstat(fd), k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        ]
        == identity,
        "fd identity mismatch",
    )
    started = datetime.now(UTC).isoformat()
    initial = monitor(policy)
    before = diskstats(diskpath)
    wall = time.monotonic_ns()
    stats = []
    digests = []
    last_sample = wall
    samples = [initial]
    for g in plan["groups"]:
        progress["current_layer"] = g["layer"]
        start = time.monotonic_ns()
        futures = [
            pool.submit(one_job, fd, expert["ranges"], buffers[i])
            for i, expert in enumerate(g["experts"])
        ]
        spans = [s for f in futures for s in f.result()]
        end = time.monotonic_ns()
        for i, expert in enumerate(g["experts"]):
            for c, (offs, length, aligned, _n) in enumerate(expert["ranges"]):
                head = offs - aligned
                with memoryview(buffers[i][c][0])[head : head + length] as data:
                    digest = hashlib.sha256(data).hexdigest()
                if expected is not None:
                    require(digest == expected[len(digests)], "payload mismatch")
                digests.append(digest)
        stats.append(
            dict(
                layer=g["layer"],
                elapsed_ns=end - start,
                pread_union_ns=union_ns(spans),
                pread_sum_ns=sum(b - a for a, b in spans),
                pread_duration_ns=[b - a for a, b in spans],
            )
        )
        progress["groups_completed"] += 1
        progress["verified_components"] = len(digests)
        require(time.monotonic_ns() - wall < 15_000_000_000, "15 s arm limit")
        if time.monotonic_ns() - last_sample >= 1_000_000_000:
            monitor_time = time.monotonic_ns()
            require(monitor_time - last_sample < 3_000_000_000, "telemetry gap")
            samples.append(monitor(policy))
            last_sample = time.monotonic_ns()
    measured = time.monotonic_ns()
    require(measured - last_sample < 3_000_000_000, "terminal telemetry gap")
    after = diskstats(diskpath)
    samples.append(monitor(policy))
    require(stat_id(file) == identity and len(digests) == 60, "incomplete arm/file changed")
    return dict(
        status="PASS",
        started_utc=started,
        groups=stats,
        service_ns=sum(r["elapsed_ns"] for r in stats),
        arm_wall_ns=measured - wall,
        logical_bytes=plan["logical_bytes"],
        requested_bytes=plan["aligned_bytes"],
        payload_sha256=digests,
        disk_delta={k: after[k] - before[k] for k in before},
        samples=samples,
    )


def execute(placement_path, policy_path, out):
    require(
        sha256(HERE / "plan.json") == PLAN_SHA and sha256(placement_path) == PLACEMENT_SHA,
        "plan/placement digest",
    )
    placement = json.loads(placement_path.read_text())
    plan = json.loads((HERE / "plan.json").read_text())
    require(
        plan["aligned_bytes"] * 2 <= 2**31
        and placement["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and placement["source_sha256"]
        == placement["destination_direct_reread"]["sha256"]
        == TARGET,
        "placement/budget",
    )
    policy = json.loads(policy_path.read_text())
    require(
        policy == derive_policy(snapshot=policy["snapshot"])
        and operational_session_ready(policy)[0],
        "C55 resources",
    )
    age = (datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds()
    require(0 <= age <= 3600, "require same-hour C55 baseline")
    files = {
        k: Path(placement[field]).resolve(strict=True)
        for k, field in (("usb", "original"), ("nvme", "working_copy"))
    }
    ids = {k: stat_id(p) for k, p in files.items()}
    require(
        all(
            v[2] == 63_387_346_208 and v[4] <= placement_path.stat().st_mtime_ns
            for v in ids.values()
        ),
        "file changed since content receipt",
    )
    require(ids["usb"][:2] != ids["nvme"][:2], "devices must be independent")
    disks = {k: disk(p, k) for k, p in files.items()}
    require(disks["usb"] != disks["nvme"], "same physical disk")
    pinned_files = [
        str(p.relative_to(REPO))
        for p in (
            HERE / "protocolo.md",
            HERE / "plan.json",
            HERE / "plan.py",
            HERE / "run.py",
            HERE.parent / "window.py",
        )
    ]
    for name in pinned_files:
        blob = subprocess.check_output(["git", "-C", str(REPO), "show", "HEAD:" + name], timeout=5)
        require(blob == (REPO / name).read_bytes(), "measuring source differs from committed tree")
    head = call("git", "-C", str(REPO), "rev-parse", "HEAD")
    tree = call("git", "-C", str(REPO), "rev-parse", "HEAD^{tree}")
    freeze = dict(
        commit=head,
        tree=tree,
        utc=datetime.now(UTC).isoformat(),
        plan_sha256=PLAN_SHA,
        placement_sha256=PLACEMENT_SHA,
        policy_sha256=sha256(policy_path),
        source_sha256=sha256(__file__),
        protocol_sha256=sha256(HERE / "protocolo.md"),
        file_stat=ids,
        order=ORDER,
        output_identity=out.name,
    )
    save(out / "freeze.json", freeze)
    scope()
    arms = []
    with ExitStack() as stack:
        fds = {}
        for k, path in files.items():
            fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
            stack.callback(os.close, fd)
            require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_DIRECT, "direct flag absent")
            fds[k] = fd
        max_len = max(
            r[3]
            for group in plan["groups"]
            for expert in group["experts"]
            for r in expert["ranges"]
        )
        buffers = []
        for _ in range(4):
            slots = []
            for _ in range(3):
                buf = stack.enter_context(mmap.mmap(-1, max_len))
                addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
                require(addr % 4096 == 0, "buffer alignment")
                for page in range(0, max_len, 4096):
                    buf[page] = 0
                slots.append((buf, addr))
            buffers.append(slots)
        pool = stack.enter_context(ThreadPoolExecutor(max_workers=4))
        warm = threading.Barrier(4)
        futures = [pool.submit(warm.wait, 3) for _ in range(4)]
        for f in futures:
            f.result()
        for i, k in enumerate(ORDER, 1):
            progress = dict(
                arm=i, transport=k, status="FAIL", groups_completed=0, verified_components=0
            )
            try:
                row = arm(
                    fds[k],
                    files[k],
                    ids[k],
                    disks[k],
                    plan,
                    buffers,
                    pool,
                    policy,
                    arms[0]["payload_sha256"] if arms else None,
                    progress,
                )
            except Exception as exc:
                progress["error"] = f"{type(exc).__name__}: {exc}"
                save(out / f"failed-{i}-{k}.json", progress)
                raise
            row["transport"] = k
            save(out / f"arm-{i}-{k}.json", row)
            arms.append(row)
    comparisons = []
    for u, n in [(0, 1), (3, 2)]:
        usb, nv = arms[u]["service_ns"], arms[n]["service_ns"]
        comparisons.append(
            dict(
                usb_arm=u + 1, nvme_arm=n + 1, usb_ns=usb, nvme_ns=nv, saving_fraction=1 - nv / usb
            )
        )
    signs = [a["saving_fraction"] > 0 for a in comparisons]
    return dict(
        decision="GO" if all(signs) else "NO_GO" if not any(signs) else "INCONCLUSIVE",
        scope="READ_SERVICE_ONLY",
        forward_passes=0,
        comparison=comparisons,
        arm_service_ns=[a["service_ns"] for a in arms],
        arm_wall_ns=[a["arm_wall_ns"] for a in arms],
        logical_bytes_per_disk=2 * plan["logical_bytes"],
        requested_bytes_per_disk=2 * plan["aligned_bytes"],
        disk_delta=[a["disk_delta"] for a in arms],
        all_payload_hashes_equal=True,
        payload_manifest_sha256=hashlib.sha256(
            "\n".join(arms[0]["payload_sha256"]).encode()
        ).hexdigest(),
        cgroup_peak=scope(),
        elapsed_clock="CLOCK_MONOTONIC",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("placement", "policy", "new-output-dir"):
        ap.add_argument("--" + name, required=True, type=Path)
    a = ap.parse_args()
    a.new_output_dir.mkdir(mode=0o700)

    def timeout(*_):
        raise TimeoutError("120 s family limit")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:
        result = execute(a.placement, a.policy, a.new_output_dir)
    except Exception as exc:
        result = dict(
            decision="FAIL",
            error=f"{type(exc).__name__}: {exc}",
            forward_passes=0,
            completed_arms=sorted(p.name for p in a.new_output_dir.glob("arm-*.json")),
        )
    signal.alarm(0)
    save(a.new_output_dir / "receipt.json", result)
    print(json.dumps(result, indent=2))
    sys.exit(result["decision"] == "FAIL")
