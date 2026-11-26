"""Read the fixed first-demand waves on the authenticated NVMe copy, once per process."""

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
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[2]
ROOT = QUAL.parents[1]
sys.path.insert(0, str(QUAL / "prefill_io_order"))
import measure as c135  # noqa: E402

io = c135.io
need = c135.require
clock = time.monotonic_ns
MIB = 1 << 20
MODEL_SIZE = 63_387_346_208
BUDGET_NS = 4_003_104_286
PASS = "PASS_FIRST_DEMAND_NVME_TRAVERSAL"


def load(path, digest):
    need(
        path.is_file() and not path.is_symlink() and io.sha256(path) == digest,
        "input digest " + path.name,
    )
    return json.loads(path.read_bytes())


def memory(max_jobs, max_len):
    """64 MiB for interpreter, records, telemetry and committed thread stack pages."""
    arena = max_jobs * 3 * max_len
    for mib in (256, 384, 512, 768, 1024):
        cap = mib * MIB
        if arena + 64 * MIB < cap * 7 // 8:
            return arena, cap, cap * 7 // 8
    raise ValueError("arena does not fit the preregistered scope")


def validate_plan(plan):
    need(
        plan["status"] == "PASS_AUTHENTICATED_FIRST_READ_PLAN"
        and plan["model_sha256"] == io.TARGET
        and plan["model_size"] == MODEL_SIZE
        and plan["plan_protocol_sha256"] == io.sha256(HERE / "protocol.md"),
        "plan/target provenance",
    )
    jobs = [j for g in plan["groups"] for j in g["experts"]]
    ranges = [r for j in jobs for r in j["ranges"]]
    need(len(jobs) == plan["job_count"] == 875 and len(ranges) == 2625, "source generation count")
    need(
        plan["service_budget_ns"] == BUDGET_NS
        and plan["fixed_outside_callbacks_ns"] == 5_996_895_714
        and plan["original_service_floor_ns"] == 6_231_568_365,
        "historical clock cut",
    )
    seen = set()
    for g in plan["groups"]:
        need(g["experts"] and len(g["site"]) == 4, "wave")
        for j in g["experts"]:
            key = (g["site"][2], j["expert"])
            need(
                key not in seen and sorted(j["components"]) == [0, 1, 2] and len(j["ranges"]) == 3,
                "identity",
            )
            seen.add(key)
            for off, size, src, n in j["ranges"]:
                need(
                    size == 4_406_400
                    and src == off // 4096 * 4096
                    and src >= 0
                    and n == ((off - src + size + 4095) // 4096) * 4096
                    and src + n <= MODEL_SIZE,
                    "DIO extent",
                )
    aligned = sum(r[3] for r in ranges)
    need(aligned == plan["aligned_bytes"] and 2 * aligned <= 24 * 2**30, "family scope")
    need(sum(r[1] for r in ranges) == plan["logical_bytes"], "payload total")
    max_jobs = max(len(g["experts"]) for g in plan["groups"])
    need(max_jobs == plan["max_group_jobs"], "max group")
    max_len = max(r[3] for r in ranges)
    return max_jobs, max_len, memory(max_jobs, max_len)


def buffers(stack, jobs, length):
    parts = []
    for _ in range(jobs):
        row = []
        for _ in range(3):
            buf = stack.enter_context(mmap.mmap(-1, length))
            addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
            need(addr % 4096 == 0, "unaligned buffer")
            for start in range(0, length, 4096):
                buf[start] = 0
            row.append((buf, addr))
        parts.append(row)
    return parts


def wave(pool, fd, group, arena, expected):
    jobs = [j | {"role": "demand"} for j in group["experts"]]
    result = c135.cohort(pool, fd, jobs, arena, "fifo")
    all_spans = []
    chains = []
    for src, log in zip(jobs, result["jobs"], strict=True):
        spans = log["read_spans_ns"]
        need(
            log["expert"] == src["expert"]
            and len(spans) == 3
            and all(a < b for a, b in spans)
            and spans[0][1] <= spans[1][0]
            and spans[1][1] <= spans[2][0] <= spans[2][1] <= result["drain_ns"],
            "read clock/order",
        )
        chains.append(sum(b - a for a, b in spans))
        all_spans.extend(spans)
    floor = max(max(chains), sum(chains) // 4)
    span = max(b for _, b in all_spans) - min(a for a, _ in all_spans)
    need(
        floor <= span <= result["drain_ns"]
        and floor <= result["read_union_ns"] <= span
        and sum(chains) == result["read_worker_ns"],
        "wave service conservation",
    )
    hashes = []
    start = clock()
    for i, j in enumerate(jobs):
        for c, (off, size, src, _) in enumerate(j["ranges"]):
            with memoryview(arena[i][c][0])[off - src : off - src + size] as payload:
                digest = hashlib.sha256(payload).hexdigest()
            if expected is not None and digest != expected[len(hashes)]:
                raise ValueError(
                    f"payload checksum mismatch at {group['site']}/"
                    f"{j['expert']}/{j['components'][c]}: "
                    f"expected {expected[len(hashes)]}, observed {digest}"
                )
            hashes.append(digest)
    hash_ns = clock() - start
    result.update(
        site=group["site"],
        floor_ns=floor,
        longest_job_ns=max(chains),
        worker_quarter_ns=sum(chains) // 4,
        read_span_ns=span,
        hash_ns=hash_ns,
    )
    return result, hashes


def check_fd(fd, path, identity):
    v = os.fstat(fd)
    need(
        [v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns, v.st_ctime_ns]
        == io.stat_id(path)
        == identity
        and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_DIRECT,
        "NVMe GGUF path/FD identity or direct flag",
    )


def append_row(file, row):
    file.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    file.flush()


def classify(first, second):
    if min(r["drain_ns"] for r in (first, second)) <= BUDGET_NS:
        return "HEADROOM_ONLY"
    if min(r["floor_ns"] for r in (first, second)) > BUDGET_NS:
        return "NO_GO_OBSERVED_FIXED_READ_PRICES"
    return "INCONCLUSIVE_DISPATCH"


def execute(a, out, result):
    def git(*args):
        return subprocess.check_output(["git", "-C", ROOT, *args], text=True, timeout=10).strip()

    need(
        len(a.commit) == 40
        and git("rev-parse", "HEAD") == a.commit
        and not git("status", "--porcelain"),
        "clean build/plan freeze",
    )
    need(
        (a.first_dir is None) == (a.arm == 1) and (a.first_sha256 is None) == (a.arm == 1),
        "arm order",
    )
    plan = load(a.plan, a.plan_sha256)
    nj, length, (arena_bytes, cap, stop) = validate_plan(plan)
    # Adapt just these two constants of the imported C135 guard in this process.
    io.CAP, io.STOPS = cap, stop
    io.scope()
    need(io.cgroup_state()["path"].endswith("/" + a.unit + ".scope"), "wrong scope identity")
    placement = load(a.placement, io.PLACEMENT_SHA)
    need(
        placement["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and placement["source_sha256"]
        == placement["destination_direct_reread"]["sha256"]
        == io.TARGET,
        "placement identity",
    )
    path = Path(placement["working_copy"]).resolve(strict=True)
    ident = io.stat_id(path)
    disk = io.disk(path, "nvme")
    c55 = load(a.c55, a.c55_sha256)
    policy = load(a.c55.with_name("resource-policy.json"), c55["canonical_policy_sha256"])
    need(
        c55["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and c55["selected_stat"] == ident
        and ident[2] == MODEL_SIZE
        and ident[4] <= a.placement.stat().st_mtime_ns
        and policy == io.derive_policy(snapshot=policy["snapshot"])
        and io.operational_session_ready(policy)[0],
        "C55/model identity",
    )

    def current_policy():
        age = (
            datetime.now(UTC) - datetime.fromisoformat(policy["snapshot"]["utc"])
        ).total_seconds()
        need(0 <= age <= 3600, "expired C55")

    current_policy()
    spec = spec_from_file_location("service_monitor", QUAL / "packed_layer_service/profile.py")
    mon = module_from_spec(spec)
    spec.loader.exec_module(mon)
    provider, unchanged = mon.monitor_provider(SimpleNamespace(token=io.stat_id))
    expected = first = None
    if a.arm == 2:
        first = load(a.first_dir / "receipt.json", a.first_sha256)
        need(
            first["status"] == PASS
            and first["arm"] == 1
            and first["commit"] == a.commit
            and first["plan_sha256"] == a.plan_sha256
            and first["model_stat"] == ident
            and first["monitor_provider"] == provider
            and first["components"] == 2625,
            "first traversal chain",
        )
        expected = load(a.first_dir / "payloads.json", first["payload_manifest_sha256"])
        need(len(expected) == 2625, "first payload manifest")
    result.update(
        arm=a.arm,
        commit=a.commit,
        tree=git("rev-parse", "HEAD^{tree}"),
        plan_sha256=a.plan_sha256,
        c55_sha256=a.c55_sha256,
        placement_sha256=io.PLACEMENT_SHA,
        model_sha256=io.TARGET,
        model_stat=ident,
        device=disk.parent.name,
        file_system=io.mount(path)[1],
        monitor_provider=provider,
        arena_bytes=arena_bytes,
        cap_bytes=cap,
        stop_bytes=stop,
        groups_completed=0,
        components=0,
        forward_passes=0,
        gpu_work=0,
        first_sha256=a.first_sha256,
        classification="MEDIDO_READ_SERVICE_ONLY",
    )
    raw = out / "raw"
    raw.mkdir(mode=0o700)
    kw = dict(policy=policy, cap_bytes=cap, expected_power=c135.POWER)
    inventory = c135.collect(out, a.unit, **kw, sample=lambda: io.monitor(policy)["observation"])
    c135.require_inventory(out, a.unit, inventory, **kw)
    io.save(out / "inventory.json", inventory)
    result["inventory_sha256"] = io.sha256(out / "inventory.json")
    current_policy()
    start = clock()
    last = start
    all_hashes = []
    totals = {
        k: 0
        for k in (
            "floor_ns",
            "longest_job_ns",
            "worker_quarter_ns",
            "read_span_ns",
            "read_union_ns",
            "read_worker_ns",
            "drain_ns",
            "hash_ns",
        )
    }
    monitor_ns = 0
    with ExitStack() as stack:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECT)
        stack.callback(os.close, fd)
        check_fd(fd, path, ident)
        result["direct_flag"] = True
        arena = buffers(stack, nj, length)
        pool = stack.enter_context(ThreadPoolExecutor(max_workers=4))
        records = stack.enter_context((raw / "groups.jsonl").open("x"))
        samples = stack.enter_context((raw / "telemetry.jsonl").open("x"))

        def monitor():
            nonlocal last, monitor_ns
            start_obs = clock()
            need(start_obs - last < 3_000_000_000, "telemetry gap")
            unchanged()
            append_row(samples, io.monitor(policy))
            finished = clock()
            need(finished - last < 3_000_000_000, "telemetry sample gap")
            last = finished
            monitor_ns += finished - start_obs

        monitor()
        before = io.diskstats(disk)
        for g in plan["groups"]:
            result["current_site"] = g["site"]
            expected_wave = (
                None
                if expected is None
                else expected[len(all_hashes) : len(all_hashes) + 3 * len(g["experts"])]
            )
            row, hashes = wave(pool, fd, g, arena, expected_wave)
            append_row(records, row)
            all_hashes.extend(hashes)
            result["groups_completed"] += 1
            result["components"] = len(all_hashes)
            for k in totals:
                totals[k] += row[k]
            if clock() - last >= 800_000_000:
                monitor()
        after = io.diskstats(disk)
        monitor()
        check_fd(fd, path, ident)
    elapsed = clock() - start
    need(
        elapsed <= 180_000_000_000
        and totals["drain_ns"] + totals["hash_ns"] + monitor_ns <= elapsed,
        "arm deadline or clock accounting",
    )
    need(
        len(all_hashes) == 2625 and (expected is None or expected == all_hashes),
        "complete checksums",
    )
    io.save(out / "payloads.json", all_hashes)
    result.update(
        **totals,
        traversal_ns=elapsed,
        monitor_ns=monitor_ns,
        residual_ns=elapsed - totals["drain_ns"] - totals["hash_ns"] - monitor_ns,
        cgroup_peak_bytes=io.scope(),
        aligned_bytes=plan["aligned_bytes"],
        logical_bytes=plan["logical_bytes"],
        disk_delta={k: after[k] - before[k] for k in before},
        disk_scope="whole device including inter-wave gaps, hashes and samples",
        payload_manifest_sha256=io.sha256(out / "payloads.json"),
        groups_sha256=io.sha256(raw / "groups.jsonl"),
        telemetry_sha256=io.sha256(raw / "telemetry.jsonl"),
    )
    need(all(v >= 0 for v in result["disk_delta"].values()), "block counters")
    if first is not None:
        need(
            result["payload_manifest_sha256"] == first["payload_manifest_sha256"],
            "cross-arm manifest",
        )
        result["family_decision"] = classify(first, result)
    need(
        sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) + 32768 <= 16 * MIB,
        "output budget",
    )
    result["status"] = PASS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("commit", "plan-sha256", "c55-sha256", "unit"):
        parser.add_argument("--" + k, required=True)
    for k in ("placement", "plan", "c55", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    parser.add_argument("--arm", type=int, choices=(1, 2), required=True)
    parser.add_argument("--first-dir", type=Path)
    parser.add_argument("--first-sha256")
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    r = {"status": "FAIL_PRESERVED", "forward_passes": 0}

    def deadline(*_):
        raise TimeoutError("traversal process exceeded 180 seconds")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(180)
    try:
        execute(a, a.new_output_dir, r)
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
        io.save(a.new_output_dir / "receipt.json", r)
    return int(r["status"] != PASS)


if __name__ == "__main__":
    raise SystemExit(main())
