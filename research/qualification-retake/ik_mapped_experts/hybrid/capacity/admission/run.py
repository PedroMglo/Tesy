"""One 120B loader/context/cleanup, with no inference, in a dedicated FILE_PAGING scope."""

import argparse
import json
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
from types import SimpleNamespace

S = run_path(str(Path(__file__).with_name("sources.py")))
CPU, DEVICE, stock = S["CPU"], S["DEVICE"], S["stock"]
CAP, VRAM, GIB, MIB = S["CAP"], S["VRAM"], S["GIB"], S["MIB"]
need, sha, save = S["need"], S["sha"], DEVICE["save"]
PHASE = ("E", "L", "C", "F")
CAP_RAW = 64 * MIB


def check_time(start, marks, now):
    need(start <= now and now - start <= 280, "total lifetime exceeds 280s")
    if "L" not in marks:
        need(now - start <= 180, "load deadline")
    elif "C" not in marks:
        need(now - marks["L"] <= 90, "context allocation deadline")
    else:
        need(now - marks["C"] <= 10, "cleanup deadline")


def owner(marker, observed, pid):
    need(observed in ([], [pid]), "foreign compute owner")
    if marker in ("E", "exit"):
        need(observed == [], "compute owner at entry or exit")
    if marker in ("L", "C"):
        need(observed == [pid], "live context owner absent")


def vram_gate(values, canonical_stop):
    need(
        bool(values) and all(0 <= value <= VRAM and value < canonical_stop for value in values),
        "VRAM reserve",
    )


def file_in_maps(text, expected_key):
    for line in text.splitlines():
        parts = line.split(None, 5)
        if (
            len(parts) == 6
            and (tuple(int(k, 16) for k in parts[3].split(":")) + (int(parts[4]),)) == expected_key
        ):
            return True
    return False


class RecordingGuard:
    def __init__(self, underlying, journal):
        self.underlying = underlying
        self.journal = journal

    def check(self, sample):
        why = self.underlying.check(sample)
        if why is not None:
            write_line(
                self.journal,
                {
                    "phase": "resource_stop",
                    "monotonic_ns": time.monotonic_ns(),
                    "reason": why,
                    "data": sample,
                },
            )
        return why


def limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (CAP_RAW, CAP_RAW))


def write_line(f, data):
    f.write(json.dumps(data, sort_keys=True, allow_nan=False) + "\n")
    f.flush()


def arm(a, out, r, bound, w, policy, resource_limits, expiry, monitor):
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
        S["other_clients"]()
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
            S["other_clients"](proc.pid)
            first = now if first is None else first
            last = now
            if tag in ("E", "L", "C", "F"):
                need((placed.key in objs) == (tag in ("L", "C")), "GGUF VMA lifecycle at " + tag)
            if tag in ("L", "C", "F"):
                saved = (
                    out / "native" / {"L": "load.maps", "C": "context.maps", "F": "freed.maps"}[tag]
                )
                present = file_in_maps(saved.read_text(), placed.key)
                need(present == (tag in ("L", "C")), "native model snapshot lifecycle")
                live = DEVICE["mapped"](Path(f"/proc/{proc.pid}/maps"), paths, drivers)
                need(
                    live == DEVICE["mapped"](saved, paths, drivers),
                    "live/native provider disagreement",
                )
                r.setdefault("live_providers", {})[tag] = live
                placed.verify()
            return True

        try:
            need(
                0
                <= (datetime.now(UTC) - datetime.fromisoformat(inv["last_utc"])).total_seconds()
                <= 3,
                "stale C118",
            )
            start_ns = time.monotonic_ns()
            started = last = start_ns / 1e9
            try:
                proc = subprocess.Popen(
                    [exe, model, plan, out / "native"],
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
            need(tuple(markers) == PHASE, f"missing handoff after {list(markers)}")
            proc.wait(
                timeout=max(
                    0.01,
                    min(10 + markers["C"] - time.monotonic(), 280 + started - time.monotonic()),
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
    need(stock.identity(model) == model_id and sha(plan) == r["plan_sha256"], "changed input")
    S["same_files"](providers)
    monitor()
    return (out / "native", stdout, stderr)


MONITOR_RECEIPT = "58aa72dfb873e951ac49ed35e6da534b18870fcf1d845ed520c030d82ee23260"


def monitor_authority(prior, probe):
    override = os.environ.get("LD_LIBRARY_PATH", "")
    need(override and ":" not in override, "private NVML monitor directory required")
    alias_dir = Path(override)
    need(
        alias_dir.is_absolute() and alias_dir.resolve(strict=True) == alias_dir,
        "private NVML monitor path",
    )
    receipt = alias_dir.parent / "receipt.json"
    need(sha(receipt) == MONITOR_RECEIPT, "wrong packed-service NVML authority")
    provider, unchanged = probe(SimpleNamespace(token=DEVICE["IO"].stat_id))
    need(
        provider.get("mode") == "PRIVATE_MATCHED_NVML"
        and provider.get("monitor_receipt_sha256") == MONITOR_RECEIPT,
        "active monitor authority",
    )
    if prior is not None:
        need(provider == prior["monitor_provider"], "monitor differs from preflight")

    def verify():
        unchanged()
        need(sha(receipt) == MONITOR_RECEIPT, "monitor receipt changed")

    verify()
    return provider, verify


def run(a, out, r):
    prior = S["bind"](a, r)
    tiny = S["tiny_gate"](a.tiny, a.tiny_sha256, a.tiny_review, a.tiny_review_sha256)
    w, policy, frozen, end = S["c55"](a)
    bound = S["inputs"](a, w, tiny, prior)
    exe, _, identity, plan, _, env, ids, _, _ = bound
    r.update(
        model_stat=list(identity),
        plan_sha256=sha(plan),
        providers=ids,
        executable_sha256=sha(exe),
        cgroup_contract=frozen["cgroup"],
        child_env=env,
        resource_policy_sha256=w["canonical_policy_sha256"],
    )
    probe = run_path(str(CPU["Q"] / "packed_layer_service/profile.py"))["monitor_provider"]
    r["monitor_provider"], unchanged = monitor_authority(prior, probe)
    if not a.execute:
        r["status"] = "PREPARED_ONLY"
        return
    native, stdout, stderr = arm(a, out, r, bound, w, policy, frozen, end, unchanged)
    r["grade"] = run_path(str(S["CAPACITY"] / "grade.py"))["check_arm"](
        stdout.read_text(), stderr.read_text(), native, plan
    )
    grade = r["grade"]
    need(
        grade["status"] == "PASS_IK_CAPACITY_ZERO_FORWARD"
        and (
            grade["matrix_mmap_count"],
            grade["bias_cuda_count"],
            grade["slots"],
            grade["group_layers"],
            grade["expert_H2D_request_bytes"],
            grade["forwards"],
            grade["registrations"],
        )
        == (108, 108, 288, 36, 0, 0, 0),
        "native capacity grade",
    )
    r["status"] = "PASS_IK_REAL_CAPACITY_NO_FORWARD"


def main():
    parser = argparse.ArgumentParser()
    for k in (
        "tiny",
        "tiny-review",
        "client",
        "dso",
        "inputs",
        "placement",
        "env49-map",
        "c55",
        "new-output-dir",
    ):
        parser.add_argument("--" + k, type=Path, required=True)
    for k in (
        "commit",
        "tiny-sha256",
        "tiny-review-sha256",
        "client-sha256",
        "inputs-sha256",
        "c55-sha256",
    ):
        parser.add_argument("--" + k, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--unit", default="")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--prepared-sha256")
    a = parser.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.absolute()
    out.mkdir(mode=0o700)
    r = {
        "status": "FAIL_PRESERVED",
        "model_starts": 0,
        "http_requests": 0,
        "raw_max_bytes": CAP_RAW,
        "model_start_limit": 1,
        "load_deadline_s": 180,
        "context_deadline_s": 90,
        "cleanup_deadline_s": 10,
        "namespace_read_stop_bytes": 1 << 40,
        "energy_j": None,
    }
    try:
        run(a, out, r)
    except Exception as ex:
        r["reason"] = f"{type(ex).__name__}: {ex}"
    finally:
        try:
            if a.execute:
                end, cg = CPU["scope_state"](a.unit, 10)
                CPU["own_scope"](cg)
                r.update(cgroup_end=end, swap_peak=int((cg / "memory.swap.peak").read_text()))
                need(
                    not any(end["events_local"][k] for k in ("oom", "oom_kill")),
                    "OOM at termination",
                )
            need(S["raw_size"](out) <= CAP_RAW, "raw budget")
            r["raw_sha256"] = {
                str(f.relative_to(out)): sha(f) for f in sorted(out.rglob("*")) if f.is_file()
            }
        except Exception as ex:
            r.update(status="FAIL_PRESERVED", final_inventory_error=str(ex))
        save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
