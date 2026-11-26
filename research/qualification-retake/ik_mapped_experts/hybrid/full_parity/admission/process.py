"""E10 FILE_PAGING ownership and telemetry across two additional numeric boundaries."""

import os
import re
import resource
import select
import shutil
import subprocess
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BASE = run_path(str(HERE.parents[1] / "capacity/admission/run.py"))
S, CPU, DEVICE, stock = (BASE[k] for k in ("S", "CPU", "DEVICE", "stock"))
CAP, CAP_RAW, GIB, need, sha = (BASE[k] for k in ("CAP", "CAP_RAW", "GIB", "need", "sha"))
RecordingGuard, file_in_maps, limits, vram_gate, write_line = (
    BASE[k] for k in ("RecordingGuard", "file_in_maps", "limits", "vram_gate", "write_line")
)
PHASE = ("E", "L", "C", "P", "T", "F")
ACTIVE = {"L", "C", "P", "T"}
EXPECTED = {15: 3659, 16: 3992}
CUT = run_path(str(HERE.parent / "contrast.py"))


def check_time(start, marks, now):
    need(start <= now <= start + 460, "total lifetime exceeds 460s")
    if "L" not in marks:
        need(now <= start + 180, "load deadline")
        return
    for previous, upcoming, label in (
        ("L", "C", "context"),
        ("C", "P", "prefill"),
        ("P", "T", "teacher"),
    ):
        if upcoming not in marks:
            need(now <= marks[previous] + 90, label + " deadline")
            return
    need(now <= marks["T"] + 10, "cleanup deadline")


def owner(tag, owners, pid):
    BASE["owner"](tag, owners, pid)
    if tag in ACTIVE:
        need(owners == [pid], "active GPU owner absent at " + tag)


def written_row(folder, pos):
    path = folder / f"pos{pos}.f32"
    need(
        path.is_file() and not path.is_symlink() and path.stat().st_size == 804352,
        "missing/partial F32",
    )
    return CUT["CPU"]["describe"](path.read_bytes())


def row_gate(rows, pos, row):
    rows[str(pos)] = row
    need(
        row["finite"] and row["max_ties"] == 1 and row["top5"][0] == EXPECTED[pos],
        "nonfinite, tied or unexpected greedy at " + str(pos),
    )


def other_clients(pid=None):
    S["other_clients"](pid)
    for p in Path("/proc").glob("[0-9]*/comm"):
        try:
            foreign = p.read_text().strip() == "parity-client" and int(p.parent.name) != pid
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        need(not foreign, "foreign parity client")


def check_maps(tag, native, pid, placed, paths, drivers, r):
    live = DEVICE["mapped"](Path(f"/proc/{pid}/maps"), paths, drivers)
    name = {
        "L": "load.maps",
        "C": "context.maps",
        "P": "prefill.maps",
        "T": "teacher.maps",
        "F": "freed.maps",
    }[tag]
    saved = native / name
    need(file_in_maps(saved.read_text(), placed.key) == (tag in ACTIVE), "native GGUF VMA")
    need(live == DEVICE["mapped"](saved, paths, drivers), "live/native provider disagreement")
    if tag in ("P", "T"):
        pos = 15 if tag == "P" else 16
        row_gate(r.setdefault("rows_at_ack", {}), pos, written_row(native, pos))
    r.setdefault("live_providers", {})[tag] = live
    placed.verify()


def arm(mode, a, out, r, bound, w, policy, resource_limits, expiry, monitor):
    exe, model, model_id, plan, _, env, providers, paths, drivers = bound
    init, cg = CPU["scope_state"](a.unit, 10)
    CPU["own_scope"](cg)
    need(
        resource.getrlimit(resource.RLIMIT_AS)[0] == resource.RLIM_INFINITY,
        "mmap needs unlimited virtual address space",
    )
    mounted = CPU["window"].mount(out)[0].split("[")[0]
    need(
        mounted == w["model_device"].split("[")[0] and shutil.disk_usage(out).free >= 11 * GIB,
        "NVMe/free space",
    )
    ns = re.fullmatch(r"/dev/(nvme\d+n\d+)(?:p\d+)?", mounted)
    need(ns, "NVMe namespace")
    ds = Path("/sys/class/block") / ns[1] / "stat"
    r.update(namespace=ns[1], unit=a.unit, cgroup_initial=init)
    raw = out / "raw"
    raw.mkdir()
    start_ns = 0
    guard = stock.policy_api.RuntimeGuard({"limits": {}, "resources": resource_limits}, init)
    kw = dict(
        policy=policy,
        cap_bytes=CAP,
        expected_power={k: policy["power"][k] for k in ("source", "profile")},
    )

    def idle():
        other_clients()
        o = stock.c118.live_sample()
        stock.c118.validate_sample(o, **kw)
        vram_gate([o["gpu"]["used_mib"]], policy["gpu"]["memory_stop_total_mib"])
        return o

    with ExitStack() as stack:
        placed = stock.PlacedFile(stack, model, model_id)
        # All hashing and provider checks happen before the 60s C118.
        S["same_files"](providers)
        monitor()
        S["age"](expiry)
        inv = stock.c118.collect(out, a.unit, duration_s=60, sample=idle, **kw)
        stock.c118.require_inventory(out, a.unit, inv, duration_s=60, max_age_s=3, **kw)
        r["c118"] = inv
        pre = idle()
        reasons = stock.policy_api.validate_start_observation(
            {"limits": {}, "resources": resource_limits},
            available_bytes=pre["mem_available_bytes"],
            gpu=pre["gpu"],
            thermal=pre["thermal"],
            power=pre["power"],
            psi_full_avg10=stock.policy_api.host_pressure(),
        )
        need(not reasons, "admission: " + ",".join(reasons))
        r["entry_vram_mib"] = pre["gpu"]["used_mib"]
        placed.verify()
        io0 = stock.io_stat(cg)
        disk0 = int(ds.read_text().split()[2])
        t0 = {"gpu": pre["gpu"], "thermal": pre["thermal"], "io": io0, "disk_read_sectors": disk0}
        stdout = raw / "stdout"
        stderr = raw / "stderr"
        f = stack.enter_context(stdout.open("xb"))
        e = stack.enter_context(stderr.open("xb"))
        journal = stack.enter_context((raw / "monitor.jsonl").open("x"))
        witness_guard = RecordingGuard(guard, journal)
        write_line(
            journal, {"phase": "before_launch", "data": t0, "monotonic_ns": time.monotonic_ns()}
        )
        rx, tx = os.pipe()
        ack_rx, ack_tx = os.pipe()
        for fd in (rx, ack_tx):
            stack.callback(os.close, fd)
        markers = {}
        proc = None
        started = last = first = None
        peak_vram = pre["gpu"]["used_mib"]
        ns_read = 0

        def sample(tag):
            nonlocal last, first, ns_read, peak_vram
            snap = CPU["snapshot"](proc, cg, ds, start_ns, witness_guard)
            if snap is None:
                return False
            data, objs = snap
            observed = DEVICE["ACTIVE"](proc.pid, policy["gpu"]["uuid"], False)
            observed_mib = [data["gpu"]["used_mib"], observed["gpu"]["used_mib"]]
            now = time.monotonic()
            peak_vram = max(peak_vram, *observed_mib)
            write_line(
                journal,
                {
                    "phase": tag,
                    "monotonic_ns": time.monotonic_ns(),
                    "data": data,
                    "owner_observation": observed,
                },
            )
            vram_gate(observed_mib, policy["gpu"]["memory_stop_total_mib"])
            need(now - last <= 3, "telemetry gap")
            need(observed["gpu"]["uuid"] == policy["gpu"]["uuid"], "owner device")
            owner(tag, observed["gpu_owners"], proc.pid)
            check_time(started, markers, now)
            ns_read = (data["disk_read_sectors"] - disk0) * 512
            need(0 <= ns_read < 1 << 40 and S["raw_size"](out) <= CAP_RAW, "dataset IO/raw limit")
            CPU["own_scope"](cg, proc.pid)
            other_clients(proc.pid)
            first = now if first is None else first
            last = now
            if tag in PHASE:
                need((placed.key in objs) == (tag in ACTIVE), "GGUF VMA lifecycle at " + tag)
                if tag != "E":
                    check_maps(tag, out / "native", proc.pid, placed, paths, drivers, r)
            return True

        try:
            need(
                0
                <= (datetime.now(UTC) - datetime.fromisoformat(inv["last_utc"])).total_seconds()
                <= 3,
                "stale C118",
            )
            S["age"](expiry)
            start_ns = time.monotonic_ns()
            started = last = start_ns / 1e9
            try:
                proc = subprocess.Popen(
                    [exe, mode, model, plan, a.ids, out / "native"],
                    stdout=f,
                    stderr=e,
                    stdin=subprocess.DEVNULL,
                    env=env | {"TESY_TEST_TX": str(tx), "TESY_TEST_RX": str(ack_rx)},
                    pass_fds=(tx, ack_rx),
                    start_new_session=True,
                    preexec_fn=limits,
                )
            finally:
                os.close(tx)
                os.close(ack_rx)
            r.update(model_starts=1, pid=proc.pid)
            ident = stock.bounded.process_identity(proc.pid)
            need(
                ident["cgroup_path"] == init["path"]
                and Path(f"/proc/{proc.pid}/exe").resolve() == exe.resolve(),
                "child identity",
            )
            proc._tesy_identity, proc._tesy_executable = ident, str(exe.resolve())
            while proc.poll() is None:
                check_time(started, markers, time.monotonic())
                if select.select([rx], [], [], 0.12)[0]:
                    payload = os.read(rx, 1)
                    if not payload:
                        break
                    i = len(markers)
                    need(i < len(PHASE) and payload == PHASE[i].encode(), "handoff order")
                    tag = PHASE[i]
                    need(sample(tag), "child lost at handoff")
                    markers[tag] = time.monotonic()
                    r["ack_elapsed_s"] = {k: v - started for k, v in markers.items()}
                    os.write(ack_tx, payload)
                elif time.monotonic() - last >= 0.35 and not sample("running"):
                    break
            if tuple(markers) != PHASE:
                # EOF follows the native error path. Give its original rc a chance to surface.
                proc.wait(timeout=2)
                raise ValueError(
                    f"missing handoff after {list(markers)}; native rc={proc.returncode}"
                )
            proc.wait(
                timeout=max(
                    0.01,
                    min(10 + markers["T"] - time.monotonic(), 460 + started - time.monotonic()),
                )
            )
            stop = time.monotonic()
            check_time(started, markers, stop)
            need(proc.returncode == 0, "native returned " + str(proc.returncode))
            reason = stock.bounded.prospective_endpoint_reason(
                first - started,
                last - started,
                stop - started,
                stock.bounded.cgroup_state(),
                init,
                resource_limits,
            )
            need(reason is None, reason or "endpoint")
        finally:
            if proc is not None:
                stock.bounded.stop_own_group(proc)
                r.update(
                    child_gone=proc.poll() is not None,
                    returncode=proc.returncode,
                    peak_vram_mib_sampled=peak_vram,
                    elapsed_s=time.monotonic() - started,
                )
                try:
                    restore_limit = time.monotonic() + 10
                    while True:
                        o = stock.c118.live_sample()
                        # The client has exited. Pages of the GGUF may remain reclaimable;
                        # re-opening a second 10 GiB launch budget is outside this endpoint.
                        stock.c118.validate_sample(
                            o, policy=policy, cap_bytes=0, expected_power=kw["expected_power"]
                        )
                        exit_obs = DEVICE["ACTIVE"](proc.pid, policy["gpu"]["uuid"], False)
                        owner("exit", exit_obs["gpu_owners"], proc.pid)
                        used = max(o["gpu"]["used_mib"], exit_obs["gpu"]["used_mib"])
                        vram_gate([used], policy["gpu"]["memory_stop_total_mib"])
                        r["exit_vram_mib"] = used
                        write_line(
                            journal,
                            {
                                "phase": "exit",
                                "monotonic_ns": time.monotonic_ns(),
                                "data": o,
                                "gpu_owners": exit_obs["gpu_owners"],
                                "io": stock.io_stat(cg),
                                "disk_read_sectors": int(ds.read_text().split()[2]),
                            },
                        )
                        if used <= pre["gpu"]["used_mib"] + 64:
                            r["restored"] = True
                            break
                        need(time.monotonic() < restore_limit, "GPU memory not restored")
                        time.sleep(0.2)
                except Exception as ex:
                    r["restore_error"] = str(ex)
    r["namespace_read_bytes"] = (int(ds.read_text().split()[2]) - disk0) * 512
    r["cgroup_io"] = stock.io_delta(io0, stock.io_stat(cg))
    need(r.get("restored") and r["child_gone"], "cleanup: " + r.get("restore_error", "unconfirmed"))
    need(0 <= r["namespace_read_bytes"] < 1 << 40, "final namespace IO")
    need(
        stock.identity(model) == model_id
        and sha(plan) == r["plan_sha256"]
        and sha(a.ids) == CUT["CPU"]["IDS17"],
        "changed input",
    )
    S["same_files"](providers)
    monitor()
    return (out / "native", stdout, stderr)
