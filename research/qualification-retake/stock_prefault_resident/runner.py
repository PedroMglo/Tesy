"""Run the authenticated CPU fixture in a dedicated memory-limited systemd scope."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import resource
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE.parent / "stock_prefault_build"
TINY_SHA = "38fcf3f9af2e2fc118bdc27e482158346e450abc02554dcd7c4a77f75d64b7c5"
BUILD_SHA = "5f58a70ddc141a7a874776429c61e37169a9d7694e8b54e44e23aec0f9c69e02"
GGUF_SHA = "31a310d53e5c4c2a22994fc2fa75f095446af380885948120306fd6e7213a08d"
RESIDENT = 768 << 20
ADDRESS = 8 << 30
OUTPUT = 16 << 20
WINDOW = 180
SUCCESS = "PASS_TINY_CPU_INFERENCE_AND_MMAP"


def require(value, msg):
    if not value:
        raise ValueError(msg)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def git(*args):
    return subprocess.check_output(
        ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", *args],
        cwd=HERE,
        text=True,
        timeout=30,
    ).strip()


def scope_at(unit, membership, mount):
    require(re.fullmatch(r"[A-Za-z0-9_-]+\.scope", unit), "expected dedicated scope unit")
    entries = membership.splitlines()
    require(len(entries) == 1 and entries[0].startswith("0::/"), "unified cgroup membership")
    parts = Path(entries[0][3:]).parts
    require(
        len(parts) > 1 and parts[-1] == unit and ".." not in parts,
        "process outside the requested scope",
    )
    return mount.joinpath(*parts[1:])


def actual_scope(unit):
    mount = Path("/sys/fs/cgroup")
    table = Path("/proc/self/mountinfo").read_text().splitlines()
    require(
        any(line.split()[4] == str(mount) and " - cgroup2 " in line for line in table),
        "cgroup v2 filesystem",
    )
    return scope_at(unit, Path("/proc/self/cgroup").read_text(), mount)


def snapshot(cg):
    data = {
        k: int((cg / k).read_text())
        for k in (
            "memory.max",
            "memory.swap.max",
            "memory.peak",
            "memory.current",
            "memory.swap.current",
        )
    }
    data["memory.events"] = dict(
        (k, int(v))
        for k, v in (line.split() for line in (cg / "memory.events").read_text().splitlines())
    )
    data["sole_process"] = (cg / "cgroup.procs").read_text().split() == [str(os.getpid())]
    data["cgroup_inode"] = cg.stat().st_ino
    return data


def validate(data):
    require(data["sole_process"], "scope contains other process at boundary")
    require(
        data["memory.max"] == RESIDENT and data["memory.swap.max"] == 0,
        "scope memory.max or memory.swap.max",
    )
    # memory.current and memory.peak are separate counter reads.
    require(
        0 < data["memory.peak"] <= RESIDENT
        and 0 < data["memory.current"] <= RESIDENT
        and data["memory.swap.current"] == 0,
        "resident or swap budget",
    )
    ev = data["memory.events"]
    require(
        {"low", "high", "max", "oom", "oom_kill", "oom_group_kill"} <= ev.keys()
        and all(v >= 0 for v in ev.values()),
        "missing memory.events",
    )
    require(all(ev[k] == 0 for k in ("oom", "oom_kill", "oom_group_kill")), "scope OOM")


def child_limits():
    resource.setrlimit(resource.RLIMIT_AS, (ADDRESS, ADDRESS))
    require(resource.getrlimit(resource.RLIMIT_AS) == (ADDRESS, ADDRESS), "child address cap")


def interrupt(signum, _frame):
    raise RuntimeError(f"interrupted by {signal.Signals(signum).name}")


def save(path, data):
    tmp = path.with_suffix(".pending")
    with tmp.open("x") as f:
        f.write(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(path)


def execute(a, out, r):
    stock, overlay = a.stock_build_root.resolve(), a.overlay_root.resolve()
    source = UPSTREAM / "tiny_fixture.py"
    r.update(
        commit=git("rev-parse", "HEAD"),
        tree=git("rev-parse", "HEAD^{tree}"),
        clean=not git("status", "--porcelain=v1", "--untracked-files=normal"),
        program_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        upstream_fixture_sha256=sha(source),
        upstream_protocol_sha256=sha(UPSTREAM / "protocol.md"),
        build_receipt_sha256=sha(overlay / "receipt.json"),
    )
    require(
        r["clean"]
        and r["upstream_fixture_sha256"] == TINY_SHA
        and r["build_receipt_sha256"] == BUILD_SHA,
        "measurement inputs or tree",
    )
    cg = actual_scope(a.scope_unit)
    before = r["initial"] = snapshot(cg)
    validate(before)
    require(
        resource.getrlimit(resource.RLIMIT_AS)[1] in (-1, ADDRESS)
        or resource.getrlimit(resource.RLIMIT_AS)[1] >= ADDRESS,
        "inherited hard address cap",
    )
    save(out / "admission.json", r)
    try:
        spec = importlib.util.spec_from_file_location("tesy_pinned_tiny_resident", source)
        tiny = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tiny)
        tiny.bounded = child_limits
        r["stock_pin"] = tiny.PIN
        status = tiny.check_run(stock, overlay, out, r)
        require(
            status == SUCCESS
            and r["gguf_sha256"] == GGUF_SHA
            and set(r["arms"]) == {"stock", "OFF", "ON", "invalid"},
            "authenticated fixture result/fixture identity",
        )
    finally:
        require(actual_scope(a.scope_unit) == cg, "changed scope")
        after = r["final"] = snapshot(cg)
        events = before["memory.events"]
        r["memory_events_delta"] = {k: after["memory.events"][k] - v for k, v in events.items()}
        validate(after)
        require(
            after["cgroup_inode"] == before["cgroup_inode"]
            and after["memory.peak"] >= before["memory.peak"]
            and all(v >= 0 for v in r["memory_events_delta"].values()),
            "scope changed or reset",
        )
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("stock-build-root", "overlay-root", "new-output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--scope-unit", required=True)
    a = parser.parse_args()
    out = a.new_output_dir.resolve()
    require(
        not any(
            out.is_relative_to(p.resolve())
            for p in (a.stock_build_root, a.overlay_root, HERE.parents[2])
        ),
        "output inside an input checkout",
    )
    out.mkdir(mode=0o700)
    started = time.monotonic()
    r = dict(
        status="NOT_COMPLETED",
        scope_unit=a.scope_unit,
        memory_max_bytes=RESIDENT,
        swap_max_bytes=0,
        child_rlimit_as_bytes=ADDRESS,
        window_s=WINDOW,
        timeout_s_per_arm=90,
        output_cap_bytes=OUTPUT,
        cpu_backend="upstream CPU only",
        started_utc=datetime.now(UTC).isoformat(),
    )
    try:
        for sig in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, interrupt)
        signal.setitimer(signal.ITIMER_REAL, WINDOW)
        os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        r["status"] = execute(a, out, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", error=str(exc))
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            (out / "failed-command.stderr").write_bytes(exc.stderr)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    r.update(
        elapsed_s=round(time.monotonic() - started, 6),
        finished_utc=datetime.now(UTC).isoformat(),
        max_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        supervisor_max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    r["bytes_before_receipt"] = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    if (
        r["elapsed_s"] > WINDOW
        or r["bytes_before_receipt"] + len(json.dumps(r, indent=2).encode()) + 1 > OUTPUT
    ):
        r.update(status="FAIL_PRESERVED", budget_error="total window or output budget")
    save(out / "receipt.json", r)
    print(r["status"])
    return int(r["status"] != SUCCESS)


if __name__ == "__main__":
    raise SystemExit(main())
