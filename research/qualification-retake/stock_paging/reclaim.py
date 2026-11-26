"""Exercise file-backed reclaim in a small real scope using a new sparse zero file."""

import argparse
import hashlib
import json
import mmap
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stock_startup"))
from start import MIB, at_preventive_limit, bounded, check, rollup_bytes  # noqa: E402


def run(private_root, output):
    private_root.mkdir(exist_ok=False)
    output.mkdir(exist_ok=False)
    t = time.monotonic()
    r = {"status": "FAIL", "scope": "MODEL_FREE_REAL_FILE_RECLAIM", "bytes": 80 * MIB, "passes": 2}
    try:
        first = bounded.cgroup_state()
        check(
            first
            and first["memory_max"] == 48 * MIB
            and first["memory_high"] == 32 * MIB
            and first["swap_max"] == first["swap_current"] == 0,
            "fixture_limits",
        )
        target = private_root / "zero.sparse"
        with target.open("xb") as w:
            w.truncate(r["bytes"])
        with target.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            page = os.sysconf("SC_PAGE_SIZE")
            for _ in range(2):
                sample = mm[::page]
                check(
                    len(sample) == r["bytes"] // page and not any(sample) and mm[-1] == 0,
                    "fixture_content",
                )
            r["sampled_smaps_bytes"] = rollup_bytes(Path("/proc/self/smaps_rollup").read_text())
            end = bounded.cgroup_state()
        r["stat_deltas"] = {
            k: end["memory_stat"][k] - first["memory_stat"][k]
            for k in (
                "file",
                "file_mapped",
                "pgfault",
                "pgmajfault",
                "pgscan",
                "pgsteal",
                "workingset_refault_file",
            )
        }
        r["events"] = {
            k: end["events"][k] - first["events"][k] for k in ("high", "max", "oom", "oom_kill")
        }
        r["memory_peak"] = end["memory_peak"]
        r["actually_allocated_file_bytes"] = target.stat().st_blocks * 512
        check(
            r["events"]["high"] > 0 and max(r["stat_deltas"][k] for k in ("pgscan", "pgsteal")) > 0,
            "reclaim_unobserved",
        )
        check(
            not at_preventive_limit(end["memory_current"], end["memory_peak"], None),
            "preventive_cut",
        )
        check(
            r["events"]["oom"] == r["events"]["oom_kill"] == end["swap_current"] == 0, "oom_or_swap"
        )
        check(r["actually_allocated_file_bytes"] <= MIB, "fixture_disk_budget")
        r["sampled_bytes_per_pass"] = len(sample)
        r["status"] = "PASS_RECLAIM_OF_ARTIFICIAL_FILE"
    except Exception as exc:
        r["reason"] = str(exc)
    finally:
        signal.alarm(0)
        r["elapsed_s"] = round(time.monotonic() - t, 6)
        r["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        pending = output / ".receipt.pending"
        pending.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
        pending.rename(output / "receipt.json")
    return r["status"]


def deadline(*_):
    raise TimeoutError("fixture_time_budget")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new-private-directory", required=True, type=Path)
    p.add_argument("--new-output", required=True, type=Path)
    a = p.parse_args()
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(30)
    status = run(a.new_private_directory, a.new_output)
    print(status)
    sys.exit(0 if status.startswith("PASS") else 1)
