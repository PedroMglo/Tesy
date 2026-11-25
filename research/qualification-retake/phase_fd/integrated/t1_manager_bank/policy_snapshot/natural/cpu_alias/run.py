"""Run three tiny Linux VMA/immutable-victim controls inside an exclusive cgroup."""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = 4096
WINDOW = 13221888
CAP = 256 << 20
STOP = 224 << 20
MODES = ("safe", "early", "reuse")


def require(ok, err):
    if not ok:
        raise ValueError(err)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def text(argv):
    return subprocess.check_output(argv, text=True, timeout=10).strip()


def scope(unit):
    own = Path("/proc/self/cgroup").read_text().strip().removeprefix("0::").lstrip("/")
    cg = Path("/sys/fs/cgroup") / own
    require(cg.name == unit + ".scope", "wrong scope")
    require(
        int((cg / "memory.max").read_text()) == CAP
        and int((cg / "memory.high").read_text()) == STOP
        and int((cg / "memory.swap.max").read_text()) == 0
        and (cg / "cgroup.procs").read_text().split() == [str(os.getpid())],
        "dedicated scope limits",
    )
    return cg


def stats(cg):
    mem = dict(x.split() for x in (cg / "memory.stat").read_text().splitlines())
    return dict(
        current=int((cg / "memory.current").read_text()),
        peak=int((cg / "memory.peak").read_text()),
        shmem=int(mem["shmem"]),
        pagetables=int(mem["pagetables"]),
        swap_peak=int((cg / "memory.swap.peak").read_text()),
        events=dict(
            (k, int(v))
            for k, v in (line.split() for line in (cg / "memory.events").read_text().splitlines())
        ),
    )


def make_input(path):
    d = hashlib.sha256()
    with path.open("xb", buffering=0) as f:
        for seed, pages in [(19, WINDOW // PAGE), (173, WINDOW // PAGE), (231, 1)]:
            page = bytes((i * 37 + (i >> 5) + seed) % 256 for i in range(PAGE))
            for _ in range(pages):
                require(f.write(page) == PAGE, "synthetic setup write")
                d.update(page)
        os.fsync(f.fileno())
    path.chmod(0o400)
    return d.hexdigest()


def monitor(argv, root, name, cg, started, telemetry):
    with (root / (name + ".out")).open("xb") as out, (root / (name + ".err")).open("xb") as err:
        child = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True)
        try:
            while True:
                sample = stats(cg)
                require(
                    sample["peak"] < STOP
                    and not sample["swap_peak"]
                    and time.monotonic() - started < 115,
                    "runtime resource stop",
                )
                telemetry["shmem_observed_max"] = max(
                    telemetry["shmem_observed_max"], sample["shmem"]
                )
                telemetry["pagetables_observed_max"] = max(
                    telemetry["pagetables_observed_max"], sample["pagetables"]
                )
                if child.poll() is not None:
                    break
                time.sleep(0.02)
            require(child.returncode == 0, name + " failed; private stderr preserved")
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)


def grade(value, name, st):
    expected = {"safe": (1, 1, 1), "early": (0, 1, 1), "reuse": (1, 0, 0)}[name]
    require(
        value["arm"] == name
        and value["status"] == "PASS"
        and tuple(value[k] for k in ("reader_old", "bank_old", "restored_old")) == expected
        and value["new_primary_correct"] is True
        and value["short_published"] is False,
        "outcome",
    )
    require(
        value["source_dev"] == st.st_dev
        and value["source_ino"] == st.st_ino
        and value["preads"] == 3
        and value["returned_bytes"] == 2 * WINDOW + PAGE
        and value["short_returned_bytes"] == PAGE,
        "source FD or byte totals",
    )
    require(
        value["backing_before_alias"] == value["backing_after_alias"] >= WINDOW
        and value["arena_virtual_bytes"] == 40 * WINDOW + 3 * PAGE
        and value["maxrss_kib"] * 1024 < STOP,
        "page accounting",
    )


def run(args, r):
    cg = scope(args.unit)
    initial = stats(cg)
    r["scope_before"] = initial
    root = args.new_output_dir
    mount = text(["findmnt", "--first-only", "-n", "-o", "SOURCE,FSTYPE", "-T", root]).split()
    require(
        len(mount) == 2
        and re.fullmatch(r"/dev/nvme\d+n\d+(p\d+)?(\[.*\])?", mount[0])
        and mount[1] == "btrfs",
        "synthetic source must be on NVMe Btrfs",
    )
    require(
        os.statvfs(root).f_bavail * os.statvfs(root).f_frsize >= 100 << 20,
        "insufficient fixture space",
    )
    repo = HERE.parents[7]
    git = ["git", "--no-optional-locks", "-C", repo]
    require(not text([*git, "status", "--porcelain"]), "dirty measurement checkout")
    r.update(
        commit=text([*git, "rev-parse", "HEAD"]),
        protocol_sha256=sha(HERE / "protocol.md"),
        source_sha256=sha(HERE / "fixture.c"),
        runner_sha256=sha(HERE / "run.py"),
        compiler_sha256=sha(Path("/usr/bin/gcc").resolve()),
        filesystem=mount[1],
        shmem_observed_max=initial["shmem"],
        pagetables_observed_max=initial["pagetables"],
    )
    tic = time.monotonic()
    binary = root / "fixture"
    source = root / "synthetic.bin"
    monitor(
        [
            "/usr/bin/gcc",
            "-std=gnu11",
            "-O2",
            "-pthread",
            "-Wall",
            "-Wextra",
            "-Werror",
            HERE / "fixture.c",
            "-o",
            binary,
        ],
        root,
        "build",
        cg,
        tic,
        r,
    )
    r["binary_sha256"] = sha(binary)
    r["source_data_sha256"] = make_input(source)
    st = source.stat()
    require(st.st_size == 2 * WINDOW + PAGE, "source size")
    for name in MODES:
        monitor([binary, source, name], root, name, cg, tic, r)
        row = json.loads((root / (name + ".out")).read_bytes())
        grade(row, name, st)
        r["arms"].append({k: v for k, v in row.items() if k not in ("source_dev", "source_ino")})
    final = stats(cg)
    r["scope_after"] = final
    end = source.stat()
    require(
        (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        == (end.st_dev, end.st_ino, end.st_size, end.st_mtime_ns, end.st_ctime_ns)
        and sha(source) == r["source_data_sha256"]
        and scope(args.unit) == cg,
        "source or cleanup changed",
    )
    require(
        final["peak"] < STOP
        and not final["swap_peak"]
        and all(
            final["events"][k] == initial["events"][k] for k in ("high", "max", "oom", "oom_kill")
        ),
        "cgroup pressure",
    )
    require(sum(p.stat().st_size for p in root.iterdir() if p != source) < 4 << 20, "output cap")
    r["elapsed_s"] = time.monotonic() - tic
    r["status"] = "PASS_ALIAS_READER_AND_TWO_FAULTS"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--unit", required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir = a.new_output_dir.resolve()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    r = {"status": "FAIL_PRESERVED", "arms": []}
    try:
        run(a, r)
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        r["reason"] = str(exc)
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    sys.exit(main())
