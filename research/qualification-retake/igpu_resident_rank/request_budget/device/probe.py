"""Observe the cgroup charge and independent namespace counters on the same monotonic clock."""

import argparse
import hashlib
import json
import os
import re
import select
import stat
import subprocess
import threading
import time
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")
HEADER = "lo_ns\thi_ns\trbytes\trios\tread_sectors\tinflight\n"
PERIOD_NS = 100_000_000
MAX_ROWS = 6650
MAX_TRACE = 2 << 20


def need(ok, cause):
    if not ok:
        raise ValueError(cause)


def save(path, value):
    with path.open("x") as stream:
        print(json.dumps(value, sort_keys=True, indent=2, allow_nan=False), file=stream)


def topology(model, pack):
    mounts = []
    file_devs = []
    for path in (model, pack):
        info = path.stat()
        need(stat.S_ISREG(info.st_mode) and not path.is_symlink(), "payload type")
        result = subprocess.check_output(
            [
                "findmnt",
                "--first-only",
                "-J",
                "-T",
                str(path),
                "-o",
                "SOURCE,FSTYPE,UUID,MAJ:MIN,ID,TARGET,FSROOT",
            ],
            text=True,
        )
        rows = json.loads(result)["filesystems"]
        need(len(rows) == 1 and rows[0]["fstype"] == "btrfs", "Btrfs mount")
        # Btrfs gives each subvolume its own st_dev; mountinfo reports the superblock.
        parent_fd = os.open(path.parent, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            fields = Path(f"/proc/self/fdinfo/{parent_fd}").read_text().splitlines()
            mount_ids = [int(s.split()[1]) for s in fields if s.startswith("mnt_id:")]
            need(mount_ids == [int(rows[0]["id"])], "findmnt/file-parent mount ID")
        finally:
            os.close(parent_fd)
        file_devs.append(f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}")
        mounts.append(rows[0])
    need(mounts[0] == mounts[1], "payloads have different mount identities")
    need(file_devs[0] == file_devs[1], "payload subvolume")
    mount = mounts[0]
    uuid = mount["uuid"]
    need(re.fullmatch(r"[a-f0-9-]{36}", uuid), "Btrfs volume identity")
    targets = list((Path("/sys/fs/btrfs") / uuid / "devices").iterdir())
    need(len(targets) == 1, "multi-device Btrfs")
    member = targets[0].resolve(strict=True)
    devfile = Path(mount["source"].split("[", 1)[0])
    need(devfile.name == member.name and devfile.is_block_device(), "Btrfs physical member")
    part = member / "partition"
    need(part.is_file() and int(part.read_text()) > 0, "partition expected")
    disk = member.parent
    match = re.fullmatch(r"(nvme[0-9]+)n[0-9]+", disk.name)
    need(match and (Path("/sys/class/block") / disk.name).resolve() == disk, "NVMe namespace")
    ctrl = Path("/sys/class/nvme") / match[1]
    need((disk / "device").resolve() == ctrl.resolve(), "controller/namespace")
    node = devfile.stat().st_rdev
    part_dev = (member / "dev").read_text().strip()
    need(part_dev == f"{os.major(node)}:{os.minor(node)}", "physical partition dev")
    parent_dev = (disk / "dev").read_text().strip()
    need(
        parent_dev != part_dev and (Path("/sys/dev/block") / parent_dev).resolve() == disk,
        "disk dev",
    )
    speed = (ctrl / "device/max_link_speed").read_text().strip()
    width = int((ctrl / "device/max_link_width").read_text())
    need((speed, width) == ("16.0 GT/s PCIe", 4), "unqualified link")
    return dict(
        mount=mount,
        file_dev=file_devs[0],
        partition=member.name,
        partition_dev=part_dev,
        namespace=disk.name,
        namespace_dev=parent_dev,
        link_speed=speed,
        link_width=width,
    )


def identity(pid):
    proc = Path("/proc") / str(pid)
    pid_stat = (proc / "stat").read_text()
    start_ticks = int(pid_stat[pid_stat.rindex(")") + 2 :].split()[19])
    (group,) = [r[3:] for r in (proc / "cgroup").read_text().splitlines() if r.startswith("0::")]
    need(group.startswith("/") and ".." not in group.split("/"), "cgroup v2")
    return dict(
        pid=pid,
        start_ticks=start_ticks,
        cgroup_path=group,
        cgroup_inode=(CGROUP / group.lstrip("/")).stat().st_ino,
    )


def counters(contents, device):
    selected = [line.split()[1:] for line in contents.splitlines() if line.split()[:1] == [device]]
    if not selected:
        return -1, -1
    need(len(selected) == 1, "duplicate namespace")
    fields = [v.split("=") for v in selected[0]]
    need(all(len(v) == 2 for v in fields) and len(fields) == len(dict(fields)), "io.stat fields")
    values = dict(fields)
    need(all(values.get(k, "").isdigit() for k in ("rbytes", "rios")), "missing namespace counters")
    return int(values["rbytes"]), int(values["rios"])


def sample(group_fd, disk_stats, dev):
    lo = time.monotonic_ns()
    fd = os.open("io.stat", os.O_RDONLY | os.O_CLOEXEC, dir_fd=group_fd)
    with os.fdopen(fd) as stream:
        data = stream.read(65537)
    need(len(data) <= 65536, "io.stat size")
    rbytes, rios = counters(data, dev)
    block = disk_stats.read_text().split()
    need(len(block) >= 11, "disk stats")
    sectors, inflight = int(block[2]), int(block[8])
    hi = time.monotonic_ns()
    need(lo <= hi and min(sectors, inflight) >= 0, "clock/namespace counters")
    return lo, hi, rbytes, rios, sectors, inflight


def record(target, topology_row, trace, done, *, limit=MAX_ROWS):
    pid = target["pid"]
    need(0 < limit <= MAX_ROWS, "observation cap")
    group = CGROUP / target["cgroup_path"].lstrip("/")
    disk_stats = Path("/sys/dev/block") / topology_row["namespace_dev"] / "stat"
    cpu_start = time.thread_time_ns()
    active = select.poll()
    group_fd = os.open(group, os.O_DIRECTORY | os.O_RDONLY | os.O_CLOEXEC)
    count = 0
    try:
        with os.fdopen(os.pidfd_open(pid), "rb", buffering=0) as pidfd, trace.open("x") as stream:
            active.register(pidfd, select.POLLIN)
            need(
                identity(pid) == target and os.fstat(group_fd).st_ino == target["cgroup_inode"],
                "bound cgroup/PID",
            )
            stream.write(HEADER)
            first = time.monotonic_ns()
            tick = first
            while not done.is_set() and not active.poll(0) and count < limit:
                try:
                    row = sample(group_fd, disk_stats, topology_row["namespace_dev"])
                except OSError:
                    if active.poll(0):
                        break
                    raise
                stream.write("\t".join(map(str, row)) + "\n")
                if count % 10 == 0:
                    stream.flush()
                need(stream.tell() <= MAX_TRACE, "observer output cap")
                count += 1
                tick += PERIOD_NS
                now = time.monotonic_ns()
                if tick <= now:
                    tick = now + PERIOD_NS
                done.wait((tick - now) / 1e9)
            need(limit != MAX_ROWS or count < MAX_ROWS, "observation row cap")
        return dict(
            samples=count,
            wall_ns=time.monotonic_ns() - first,
            observer_thread_cpu_ns=time.thread_time_ns() - cpu_start,
        )
    finally:
        os.close(group_fd)


def physical_observer(launch, unit, topo, trace, done, report):
    try:
        while not done.is_set():
            try:
                target = json.loads(launch.read_bytes())["process_identity"]
            except (FileNotFoundError, json.JSONDecodeError):
                done.wait(0.025)
                continue
            break
        else:
            raise RuntimeError("no native launch before exit")
        own_group = identity(os.getpid())["cgroup_path"]
        actual = target["cgroup_path"]
        need(
            Path(actual).name == unit + ".service"
            and own_group != actual
            and not own_group.startswith(actual + "/"),
            "observer outside target service",
        )
        sealed = topo | {"process_identity": target, "cgroup_inode": target["cgroup_inode"]}
        report.update(inventory=sealed)
        report.update(record(target, topo, trace, done))
        report["status"] = "OBSERVED"
    except Exception as exc:
        report.update(status="OBSERVATION_ERROR", reason=f"{type(exc).__name__}: {exc}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, type=Path)
    ap.add_argument("--pack", required=True, type=Path)
    ap.add_argument("--new-output-dir", required=True, type=Path)
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    r = {}
    try:
        topo = topology(a.model, a.pack)
        trace = out / "samples.tsv"
        r.update(
            inventory=topo, **record(identity(os.getpid()), topo, trace, threading.Event(), limit=6)
        )
        need(r["samples"] == 6, "six monitor observations")
        r.update(
            status="PASS_UNPRIVILEGED_MONITOR_PROBE",
            trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),
            model_opens=0,
        )
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
