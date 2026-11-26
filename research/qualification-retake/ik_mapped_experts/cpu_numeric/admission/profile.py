"""Prepare, or run exactly one qualified CPU process in its separate systemd scope."""

import argparse
import heapq
import json
import math
import os
import re
import resource
import struct
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE_MODULE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE_MODULE))
from authority import (  # noqa: E402
    GIB,
    HERE,
    MIB,
    NAMES,
    PACK17,
    PLACEMENT,
    ROW,
    WIDTH,
    Q,
    child_env,
    digest,
    need,
    placed,
    receipt,
    references,
    sha,
    stock,
    verify_build,
    window_authority,
)

sys.path.insert(0, str(Q / "nvme_admission"))
import window  # noqa: E402

PHASES = [
    "load_begin",
    "load_end",
    "context_begin",
    "context_end",
    "prefill_begin",
    "prefill_end",
    "teacher_begin",
    "teacher_end",
    "cleanup_begin",
    "cleanup_end",
]
MONITOR_SHA = "1b310cec5baddefef24c0d4b6cec982f1a58e2cc77454de7f7da9809bd9e9ad3"


def deadlines(text, start, now, *, completed=False):
    tuples = [(k, int(t)) for k, t in re.findall(r"^PHASE (\w+) (\d+)\n", text, re.M)]
    labels = [k for k, _ in tuples]
    stamps = [t for _, t in tuples]
    need(labels == PHASES[: len(labels)], "native phase/order")
    need(stamps == sorted(stamps) and all(start <= t <= now for t in stamps), "native monotonic")
    d = dict(tuples)
    # Adjacent phase groups include publication and the native row gate.
    for begin, end, limit in (
        (None, "prefill_begin", 180),
        ("prefill_begin", "teacher_begin", 90),
        ("teacher_begin", "cleanup_begin", 90),
        ("cleanup_begin", None, 10),
    ):
        if begin is None or begin in d:
            lo = start if begin is None else d[begin]
            hi = d.get(end, now)
            need(hi - lo <= limit * 10**9, f"deadline {begin or 'load/context'}")
    if completed:
        need(labels == PHASES, "native trajectory incomplete")
    return d


def compare(data, ref):
    need(len(data) == len(ref) == ROW, "logit bytes")
    a, b = (struct.unpack(f"<{WIDTH}f", x) for x in (data, ref))
    need(all(map(math.isfinite, a)) and all(map(math.isfinite, b)), "nonfinite logits")
    words = sum(
        x != y for x, y in zip(memoryview(data).cast("I"), memoryview(ref).cast("I"), strict=True)
    )
    top_a, top_b = [heapq.nlargest(5, range(WIDTH), key=v.__getitem__) for v in (a, b)]
    return dict(
        different_words=words,
        top5=top_a,
        reference_top5=top_b,
        greedy_equal=top_a[0] == top_b[0],
        ties=a.count(a[top_a[0]]),
        top5_equal=top_a == top_b,
        max_abs=max(abs(x - y) for x, y in zip(a, b, strict=True)),
        mean_abs=math.fsum(abs(x - y) for x, y in zip(a, b, strict=True)) / WIDTH,
        rmse=math.sqrt(math.fsum((x - y) ** 2 for x, y in zip(a, b, strict=True)) / WIDTH),
    )


def scope_state(unit, envelope):
    cg = stock.bounded.cgroup_state()
    cap = envelope * GIB
    need(
        unit.startswith(f"tesy-ik-e{envelope}-")
        and cg
        and Path(cg["path"]).name == unit + ".scope"
        and Path(cg["path"]).parent.name == "app.slice"
        and cg["memory_max"] == cap
        and cg["memory_high"] == cap - 512 * MIB
        and cg["swap_max"] == cg["swap_current"] == 0,
        "exclusive FILE_PAGING scope",
    )
    root = Path("/sys/fs/cgroup") / cg["path"].lstrip("/")
    need((root / "memory.swap.peak").read_text().strip() == "0", "scope swapped")
    return cg, root


def own_scope(root, child=None):
    pids = {int(i) for i in (root / "cgroup.procs").read_text().split()}
    allowed = {os.getpid()}
    if child is not None:
        allowed.add(child)
    need(os.getpid() in pids and pids <= allowed, "unexpected process in scope")


def loader(exe, b, env):
    interpreter = "/lib64/ld-linux-x86-64.so.2"
    out = subprocess.check_output([interpreter, "--list", exe], env=env, text=True, timeout=5)
    live = {}
    for line in out.splitlines():
        m = re.fullmatch(r"\s*(\S+) => (/\S+) \(0x[0-9a-f]+\)", line)
        if m:
            live[m[1]] = str(Path(m[2]).resolve(strict=True))
    key = "ld-linux-x86-64.so.2"
    live[key] = str(Path(interpreter).resolve(strict=True))
    need(live == {n: row["file"] for n, row in b["closure"].items()}, "ld.so --list drift")
    return digest(out.encode())


def conflicts(pid=None):
    need(not window.concurrent(), "parallel model/compiler/transfer")
    # C55 recognises stock names. An ik numeric client can be on CPU without a GPU PID.
    matches = []
    for name in Path("/proc").glob("[0-9]*/comm"):
        try:
            if name.read_text().strip() == "ik-cpu-numeric":
                matches.append(int(name.parent.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    need(all(i == pid for i in matches), "parallel ik client")


def snapshot(proc, root, disk_stat, start, guard):
    perf = stock.bounded
    smaps = perf.live_smaps_rollup(proc)
    if proc.poll() is not None:
        return None
    try:
        st = Path(f"/proc/{proc.pid}/status").read_text()
        objs = stock.vm_objects(proc.pid)
        status = perf.proc_status(proc.pid)
    except (FileNotFoundError, ProcessLookupError):
        if proc.poll() is not None:
            return None
        raise
    values = dict(
        (k, int(v) * 1024) for k, v in re.findall(r"^(VmSize|VmPeak):\s+(\d+) kB$", st, re.M)
    )
    need(len(values) == 2, "virtual memory telemetry")
    status.update(values)
    row = dict(
        cgroup=perf.cgroup_state(),
        proc=status,
        smaps=stock.rollup_bytes(smaps),
        gpu=perf.gpu_state(prospective=True),
        thermal=perf.thermal_state(prospective=True),
        mem_available_bytes=perf.mem_available(),
        io=stock.io_stat(root),
        disk_read_sectors=int(disk_stat.read_text().split()[2]),
        resource_observation={
            "power": stock.policy_api.live_power(),
            "host_psi_full_avg10": stock.policy_api.host_pressure(),
        },
        elapsed_s=(time.monotonic_ns() - start) / 1e9,
    )
    why = guard.check(row)
    need(why is None, why or "runtime guard")
    return row, objs


def sha_rows(folder):
    return {n: sha(folder / n) for n in NAMES if (folder / n).is_file()}


def expected_views(raw_parent):
    index = raw_parent / "c7-20260927T1130Z/raw/gguf-inventory.jsonl"
    data = index.read_bytes()
    need(
        digest(data) == "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82",
        "C283 index",
    )
    tensors = [json.loads(line) for line in data.splitlines()[1:]]
    roles = {
        t["name"]: [t["data_offset"], t["n_bytes"], {"f32": 0, "mxfp4": 39}[t["tensor_type"]]]
        for t in tensors
        if re.fullmatch(r"blk\.\d+\.ffn_(gate|up|down)_exps\.(weight|bias)", t["name"])
    }
    need(
        len(roles) == 216 and sum(t[1] for t in roles.values()) == 61073326080, "216 expert ranges"
    )
    return roles


def native_geometry(transcript, arm, views, closure):
    def fields(tag):
        return [s.split()[1:] for s in transcript.splitlines() if s.startswith(tag + " ")]

    def ints(tag):
        return [tuple(map(int, row)) for row in fields(tag)]

    native = fields("VIEW")
    need(
        len(native) == len(views) and {r[0]: list(map(int, r[1:])) for r in native} == views,
        "VMA views",
    )
    need(
        len(fields("PROVIDER")) == 2
        and dict(fields("PROVIDER"))
        == {k: closure["lib" + k + ".so"]["file"] for k in ("ggml", "llama")},
        "native dladdr",
    )
    maps = ints("MAP")
    need(
        len(maps) == 1
        and maps[0][:3] == (0, stock.MODEL_SIZE, 1)
        and maps[0][3] & 1
        and not maps[0][3] & 0x8000,
        "GGUF mapped flags",
    )
    need(not any(v[2] == 3 for v in ints("POSIX")), "unexpected startup WILLNEED")
    tiny = run_path(str(HERE.parents[1] / "tiny_loader/run.py"))
    drops = sorted(v for v in ints("MAD") if v[2] == 4)
    need(drops == tiny["expected_drops"](views), "expert DONTNEED ranges")
    (pool,) = ints("POOL")
    need(pool[2] == int(arm == "D1") and pool[1] - pool[0] == 4 * pool[2], "worker count")
    (drain,) = ints("DRAIN")
    need(
        drain[:2] == (108, 0) and ints("KV") == [(15, 16), (16, 17)], "native KV or worker cleanup"
    )
    return dict(
        expert_views=len(views),
        logical_expert_bytes=sum(v[1] for v in views.values()),
        drop_ranges=len(drops),
        dropped_bytes=sum(v[1] for v in drops),
        pool=pool,
        drain=drain,
    )


def run(a, out, r):
    r.update(
        arm=a.arm,
        envelope_gib=a.envelope,
        model_starts=0,
        http_requests=0,
        capture_dir="capture",
        energy_j=None,
        protocol_sha256=sha(HERE / "protocol.md"),
        source_sha256={n: sha(HERE / n) for n in ("authority.py", "profile.py")},
    )
    head = subprocess.check_output(["git", "-C", HERE, "rev-parse", "HEAD"], text=True).strip()
    need(
        head == a.commit
        and not subprocess.check_output(
            ["git", "-C", HERE, "status", "--porcelain", "--untracked-files=normal"]
        ),
        "unfrozen checkout",
    )
    r["commit"] = head
    w, p, limits = window_authority(a.c55, a.c55_sha256, a.envelope)
    model, model_id = placed(w, a.placement)
    packed, gold, other, arms = references(a.raw_parent, a.stock_raw)
    views = expected_views(a.raw_parent)
    exe, b = verify_build(a.build, a.build_sha256, a.synthetic, a.synthetic_sha256, a.objects)
    monitor = Path(os.environ["LD_LIBRARY_PATH"])
    need(
        set(f.name for f in monitor.iterdir()) == {"libnvidia-ml.so.1"}
        and sha(monitor / "libnvidia-ml.so.1") == MONITOR_SHA,
        "monitor-only NVML",
    )
    env = child_env(a.objects)
    r.update(
        loader_sha256=loader(exe, b, env),
        monitor_nvml_sha256=MONITOR_SHA,
        synthetic_sha256=a.synthetic_sha256,
        build_sha256=a.build_sha256,
        c55_sha256=a.c55_sha256,
        binary_sha256=b["binary_sha256"],
        providers=b["closure"],
        cgroup_contract=limits["cgroup"],
        model_stat=list(model_id),
        placement_sha256=PLACEMENT,
        model_sha256=stock.MODEL_SHA,
        gold_sha256={n: digest(g) for n, g in zip(NAMES, gold, strict=True)},
        stock_rows_sha256={n: digest(g) for n, g in zip(NAMES, other, strict=True)},
        input_sha256=PACK17,
        historical_arms=arms,
        raw_max_bytes=64 * MIB,
        namespace_read_stop_bytes=1 << 40,
    )
    with (out / "ids.i32").open("xb") as f:
        f.write(packed)
    raw = out / "raw"
    raw.mkdir()
    argv = [exe, "c110", a.arm, model, (out / "ids.i32"), "3659", out / "capture"]
    if a.arm == "D1":
        need(a.d0 and a.d0_sha256, "D1 requires accepted D0")
        d0 = receipt(a.d0, a.d0_sha256)
        need(
            d0["status"] == "PASS_IK_CPU_NUMERIC_ARM"
            and d0["arm"] == "D0"
            and d0["envelope_gib"] == a.envelope
            and d0["child_gone"]
            and d0["build_sha256"] == a.build_sha256
            and d0["commit"] == head
            and d0["model_stat"] == list(model_id)
            and d0["input_sha256"] == PACK17
            and d0["synthetic_sha256"] == a.synthetic_sha256,
            "D0 arm authority",
        )
        prior = a.d0.parent / "capture"
        need(
            set(d0["logits_sha256"]) == set(NAMES) and sha_rows(prior) == d0["logits_sha256"],
            "D0 rows changed",
        )
        argv.append(prior)
        r["d0_sha256"] = a.d0_sha256
    else:
        need(not a.d0 and not a.d0_sha256, "D0 cannot consume candidate")
    if not a.execute:
        r["status"] = "PREPARED_ONLY"
        return
    need(a.unit, "--unit required for execution")
    initial, cg = scope_state(a.unit, a.envelope)
    own_scope(cg)
    need(
        window.mount(out)[0].split("[")[0] == w["model_device"].split("[")[0]
        and os.statvfs(out).f_bavail * os.statvfs(out).f_frsize >= 11 * GIB,
        "raw NVMe/free space",
    )
    must = {
        "policy": p,
        "cap_bytes": a.envelope * GIB,
        "expected_power": {k: p["power"][k] for k in ("source", "profile")},
    }

    def admission_sample():
        conflicts()
        sample = stock.c118.live_sample()
        stock.c118.validate_sample(sample, **must)
        return sample

    inv = stock.c118.collect(out, a.unit, duration_s=60, sample=admission_sample, **must)
    stock.c118.require_inventory(out, a.unit, inv, duration_s=60, max_age_s=3, **must)
    r["c118"] = {k: v for k, v in inv.items() if k != "path"}
    sample = admission_sample()
    reasons = stock.policy_api.validate_start_observation(
        {"limits": {}, "resources": limits},
        available_bytes=sample["mem_available_bytes"],
        gpu=sample["gpu"],
        thermal=sample["thermal"],
        power=sample["power"],
        psi_full_avg10=stock.policy_api.host_pressure(),
    )
    need(not reasons, "start: " + ",".join(reasons))
    ns = re.fullmatch(r"/dev/(nvme\d+n\d+)(?:p\d+)?(?:\[.*\])?", w["model_device"])
    need(ns, "NVMe namespace missing")
    disk_stat = Path("/sys/class/block") / ns[1] / "stat"
    before = int(disk_stat.read_text().split()[2])
    before_io = stock.io_stat(cg)
    r["namespace"] = ns[1]
    proc = None
    capture = out / "capture"
    stdout = raw / "native.stdout"
    stderr = raw / "native.stderr"
    with ExitStack() as files:
        held = {
            n: stock.Reference(files, rec["file"], rec["sha256"]) for n, rec in b["closure"].items()
        }
        held["ik-cpu-numeric"] = stock.Reference(files, exe, b["binary_sha256"])
        placed_fd = stock.PlacedFile(files, model, model_id)
        held["GGUF"] = placed_fd
        f = files.enter_context(stdout.open("xb", buffering=0))
        e = files.enter_context(stderr.open("xb", buffering=0))
        series = files.enter_context((raw / "monitor.jsonl").open("x"))

        def child_limits():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_FSIZE, (64 * MIB, 64 * MIB))

        need(
            resource.getrlimit(resource.RLIMIT_AS)[0] == resource.RLIM_INFINITY,
            "finite virtual-address cap",
        )
        need(
            (datetime.now(UTC) - datetime.fromisoformat(inv["last_utc"])).total_seconds() <= 3,
            "stale C118",
        )
        r["unit"] = a.unit
        first = last = None
        observed = set()
        count = 0
        guard = stock.policy_api.RuntimeGuard({"limits": {}, "resources": limits}, initial)
        start = time.monotonic_ns()
        try:
            proc = subprocess.Popen(
                argv,
                env=env,
                stdout=f,
                stderr=e,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                preexec_fn=child_limits,
            )
            r.update(model_starts=1, pid=proc.pid)
            ident = stock.bounded.process_identity(proc.pid)
            need(
                ident["cgroup_path"] == initial["path"]
                and Path(f"/proc/{proc.pid}/exe").resolve() == exe.resolve(),
                "launch provenance",
            )
            proc._tesy_identity, proc._tesy_executable = ident, str(exe.resolve())
            while proc.poll() is None:
                snap = snapshot(proc, cg, disk_stat, start, guard)
                if snap is None:
                    break
                row, objs = snap
                own_scope(cg, proc.pid)
                conflicts(proc.pid)
                stock.c118.no_other_model()
                text = stdout.read_text()
                now = time.monotonic_ns()
                deadlines(text, start, now)
                elapsed = row["elapsed_s"]
                need(last is None or elapsed - last <= 3, "telemetry gap")
                first = elapsed if first is None else first
                last = elapsed
                count += 1
                observed.update(k for k, v in held.items() if v.key in objs)
                need(
                    0 <= (row["disk_read_sectors"] - before) * 512 < 1 << 40,
                    "NVMe counter or 1 TiB I/O bound",
                )
                need(
                    sum(t.stat().st_size for d in (raw, capture) if d.is_dir() for t in d.iterdir())
                    <= 64 * MIB,
                    "raw budget",
                )
                series.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                series.flush()
                time.sleep(0.35)
            code = proc.wait(timeout=2)
            stop = time.monotonic_ns()
            r.update(
                returncode=code,
                samples=count,
                mapped=sorted(observed),
                elapsed_s=(stop - start) / 1e9,
            )
            transcript = stdout.read_text()
            r["native_status"] = re.findall(r"^STATUS (\w+)$", transcript, re.M)
            need(code == 0, "native rc " + str(code) + " " + str(r["native_status"]))
            r["phase_monotonic_ns"] = deadlines(transcript, start, stop, completed=True)
            need(
                "STATUS PASS_IK_CPU_NUMERIC_ROWS\n" in transcript and observed == set(held),
                "native status or VMA",
            )
            # fstat and /proc/maps use different device numbers on some Btrfs mounts.
            dev = model_id[0]
            witness = [os.major(dev), os.minor(dev), *placed_fd.key]
            native_keys = [
                list(map(int, line.split()[1:]))
                for line in transcript.splitlines()
                if line.startswith("VMA_KEY ")
            ]
            need(native_keys == [witness], "native and supervisor FD witnesses differ")
            r["native_vma_key"] = witness
            r["native_geometry"] = native_geometry(transcript, a.arm, views, b["closure"])
            for ref in held.values():
                ref.verify()
            why = stock.bounded.prospective_endpoint_reason(
                first, last, (stop - start) / 1e9, stock.bounded.cgroup_state(), initial, limits
            )
            need(why is None, why or "endpoint")
        finally:
            if proc is not None:
                stock.bounded.stop_own_group(proc)
                r.update(child_gone=proc.poll() is not None, returncode=proc.returncode)
                r["native_status"] = re.findall(r"^STATUS (\w+)$", stdout.read_text(), re.M)
            end, _ = scope_state(a.unit, a.envelope)
            own_scope(cg)
            r.update(
                cgroup_end=end,
                io_by_device=stock.io_delta(before_io, stock.io_stat(cg)),
                swap_peak=int((cg / "memory.swap.peak").read_text()),
                namespace_read_bytes=(int(disk_stat.read_text().split()[2]) - before) * 512,
            )
    caprows = [(capture / n).read_bytes() for n in NAMES]
    r["comparison"] = {
        label: {n: compare(x, y) for n, x, y in zip(NAMES, caprows, ys, strict=True)}
        for label, ys in (("C110", gold), ("stock", other))
    }
    first = r["comparison"]["C110"][NAMES[0]]
    need(first["top5"][0] == 3659 and first["ties"] == 1, "independent first greedy")
    second = r["comparison"]["C110"][NAMES[1]]
    need(second["top5"][0] == 3992 and second["ties"] == 1, "independent second greedy")
    if a.arm == "D1":
        need(sha_rows(capture) == d0["logits_sha256"], "D1 differs from D0")
    need(stock.identity(model) == model_id, "changed GGUF")
    need(0 <= r["namespace_read_bytes"] < 1 << 40, "NVMe read budget")
    need(
        sum(t.stat().st_size for d in (raw, capture) for t in d.iterdir()) <= 64 * MIB,
        "final raw budget",
    )
    r["status"] = "PASS_IK_CPU_NUMERIC_ARM"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "c55",
        "placement",
        "raw-parent",
        "stock-raw",
        "build",
        "synthetic",
        "objects",
        "new-output-dir",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("commit", "c55-sha256", "build-sha256", "synthetic-sha256"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--arm", choices=["D0", "D1"], required=True)
    p.add_argument("--envelope", type=int, choices=[10, 20], required=True)
    p.add_argument("--unit")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--d0", type=Path)
    p.add_argument("--d0-sha256")
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = {"status": "FAIL_PRESERVED", "arm": a.arm, "model_starts": 0}
    try:
        run(a, out, r)
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        r["logits_sha256"] = sha_rows(out / "capture")
        r["raw_sha256"] = (
            {f.name: sha(f) for f in (out / "raw").iterdir() if f.is_file()}
            if (out / "raw").is_dir()
            else {}
        )
        with (out / "receipt.json").open("x") as f:
            json.dump(r, f, sort_keys=True, indent=2, allow_nan=False)
            print(file=f)
    print(r["status"], flush=True)
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    sys.exit(main())
