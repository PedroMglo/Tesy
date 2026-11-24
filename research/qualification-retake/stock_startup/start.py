"""One local stock server initialization, zero HTTP requests, with a preventive paging stop."""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))
sys.path.insert(0, str(HERE.parent / "cuda35"))
import c55_inventory as c55  # noqa: E402
import c118_start_inventory as c118  # noqa: E402
import host_resource_policy as policy_api  # noqa: E402
import run_bounded as bounded  # noqa: E402
from vma_identity import Reference, stable  # noqa: E402

GIB = 1 << 30
MIB = 1 << 20
MODEL_SHA = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
MODEL_SIZE = 63387346208
MEM_FIELDS = ("anon", "file", "file_mapped", "pgfault", "pgmajfault", "workingset_refault_file")
PIN = "e95426f16982054c379ca7bdc8186996dd22f0fe"
MODEL = Path("/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf")
ARGS = (
    "-lm mmap -lzm off --no-repack --no-host --fit off -ngl 99 -cmoe "
    "--moe-cache-mib 2048 --moe-cache-cpu-share 0 -c 8192 -np 1 -b 256 -ub 32 "
    "-ctk f16 -ctv f16 --no-warmup --host 127.0.0.1 --port 0"
).split()


def check(ok, why):
    if not ok:
        raise ValueError(why)


def sha(p):
    with open(p, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(p):
    return json.loads(p.read_text())


def cap_for(policy, paging=False):
    check(policy_api.derive_policy(snapshot=policy["snapshot"]) == policy, "c55_policy_derivation")
    if paging:
        return 10 * GIB
    return min(20 * GIB, policy["memory"]["cap_max_bytes"] - 256 * MIB)


def identity(path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


class PlacedFile(Reference):
    """Use the placement's direct, full read plus the unchanged inode and timestamps."""

    def __init__(self, stack, path, expected):
        self.expected = expected
        super().__init__(stack, path, MODEL_SHA)

    def verify(self):
        check(
            stable(os.fstat(self.file.fileno())) == self.expected == identity(self.path),
            "placement_changed_at_mapping",
        )


def vm_objects(pid):
    objects = set()
    for line in Path(f"/proc/{pid}/maps").read_text().splitlines():
        fields = line.split(None, 5)
        major, minor = (int(x, 16) for x in fields[3].split(":"))
        objects.add((major, minor, int(fields[4])))
    return objects


def io_stat(cg):
    rows = {}
    for line in (cg / "io.stat").read_text().splitlines():
        device, *fields = line.split()
        rows[device] = {k: int(v) for k, v in (s.split("=") for s in fields)}
    return rows


def io_delta(first, last):
    return {
        dev: {k: v - first.get(dev, {}).get(k, 0) for k, v in values.items()}
        for dev, values in last.items()
    }


def logged_geometry(log):
    patterns = {
        "ready": r"\bmodel loaded\b",
        "mapped": r"CPU_Mapped model buffer size",
        "group": r"36 layers,\s*mxfp4:\s+161 slots",
        "full_kv": r"non-SWA KV cache, size = 8192 cells",
        "swa_kv": r"creating\s+SWA KV cache, size = 256 cells",
        "cuda": r"CUDA0\s+MoE cache size",
    }
    return {k: bool(re.search(p, log, re.I)) for k, p in patterns.items()}


def at_preventive_limit(current, peak, threshold):
    return threshold is not None and max(current, peak) >= threshold


def rollup_bytes(text):
    fields = {"Rss", "Pss", "Pss_Anon", "Pss_File", "Anonymous", "Locked", "Swap"}
    result = {
        name: int(n) * 1024
        for name, n in re.findall(r"^(\w+):\s+(\d+) kB$", text, re.M)
        if name in fields
    }
    check(result.keys() == fields, "smaps_rollup_missing")
    return result


def run(a, *, paging=False, placement_log=False):
    check(not placement_log or paging, "placement_log_requires_file_paging")
    unit = HERE
    if paging:
        unit = HERE.parent / ("stock_log" if placement_log else "stock_paging")
    a.new_raw.mkdir(exist_ok=False)
    raw = a.new_raw / "raw"
    raw.mkdir()
    a.new_output.mkdir(exist_ok=False)
    start = time.monotonic()
    r = {
        "status": "NOT_RUN",
        "server_starts": 0,
        "http_requests_sent": 0,
        "warmup_requested": False,
        "sampling_forwards_requested": 0,
        "physical_energy_j": None,
        "protocol_sha256": sha(unit / "protocol.md"),
        "runner_sha256": sha(__file__),
    }
    proc = None
    cg = None
    watcher = None
    refs = ExitStack()
    end = threading.Event()
    fast = {}
    first_io = None
    stop_log = raw / "server.log"
    try:
        policy = read(a.policy)
        cap = cap_for(policy, paging)
        resources = policy_api.freeze_protocol_resource_limits(
            policy,
            cgroup_memory_max_bytes=cap,
            start_mode="CAPACITY_ADMISSION_START",
            execution_class="FILE_PAGING",
        )
        protocol = {"limits": {}, "resources": resources}
        policy_api.validate_resource_protocol(protocol)
        high = cap - 512 * MIB
        stop = None if paging else high
        state0 = bounded.cgroup_state()
        check(
            state0
            and state0["memory_max"] == cap
            and state0["memory_high"] == high
            and state0["swap_max"] == state0["swap_current"] == 0,
            "scope_limit",
        )
        cg = Path("/sys/fs/cgroup") / state0["path"].lstrip("/")
        r.update(resource_policy_sha256=sha(a.policy), cap_bytes=cap, preventive_stop_bytes=stop)
        if paging:
            r.update(start_regime="FILE_PAGING_V3", memory_high_bytes=high)
        if placement_log:
            r.update(log_verbosity=4, logger_fixture_sha256=sha(unit / "fixture-r1/receipt.json"))
        verified = read(a.placement)
        check(
            verified["status"] == "PASS_NVME_MODEL_PLACEMENT"
            and verified["source_sha256"]
            == verified["destination_direct_reread"]["sha256"]
            == MODEL_SHA
            and verified["destination_direct_reread"]["size_bytes"] == MODEL_SIZE
            and MODEL.samefile(verified["working_copy"]),
            "verified_model_identity",
        )
        current = identity(MODEL)
        snapshot = policy["snapshot"]["model_stat"]
        check(
            current[:4] == (snapshot["dev"], snapshot["inode"], MODEL_SIZE, snapshot["mtime_ns"])
            and current[4] <= a.placement.stat().st_mtime_ns,
            "model_changed_since_qualification",
        )
        c55.mounts({"model": MODEL.resolve(strict=True)})
        r["model"] = {
            "sha256": MODEL_SHA,
            "size": MODEL_SIZE,
            "placement_receipt_sha256": sha(a.placement),
        }
        build = read(a.build_receipt)
        check(
            build["decision"] == "PASS_STOCK_BUILD_AND_MODEL_FREE_CLI"
            and build["pin"] == PIN
            and build["source_clean_after"]
            and build["sm89_elf_entries"] > 0,
            "stock_build",
        )
        exe = a.binary.resolve(strict=True)
        exe_key = Reference(refs, exe, build["server_sha256"]).key
        dep_ids = {}
        for name, expected in build["own_libs_sha256"].items():
            path = (exe.parent / name).resolve(strict=True)
            check(path.parent == exe.parent, "lib_" + name)
            dep_ids[name] = Reference(refs, path, expected).key
        r["build_receipt_sha256"] = sha(a.build_receipt)
        r["server_sha256"] = build["server_sha256"]
        env = {
            "PATH": os.environ["PATH"],
            "LANG": "C",
            "LC_ALL": "C",
            "CUDA_VISIBLE_DEVICES": "0",
            "LD_LIBRARY_PATH": str(exe.parent),
            "HF_HUB_OFFLINE": "1",
        }
        run_id = "stock-nvme-paging" if paging else "stock-nvme-startup"
        if placement_log:
            run_id = "stock-nvme-placement-log"
        args = {
            "policy": policy,
            "expected_power": {k: policy["power"][k] for k in ("source", "profile")},
            "cap_bytes": cap,
            "duration_s": 60,
        }
        if a.before_inventory_only:
            r["status"] = "PASS_MODEL_FREE_PRE_INVENTORY"
            return r["status"]

        def audited_inventory_sample():
            obs = c118.live_sample()
            try:
                c118.validate_sample(
                    obs, policy=policy, cap_bytes=cap, expected_power=args["expected_power"]
                )
            except Exception:
                (raw / "rejected-c118.json").write_text(json.dumps(obs, allow_nan=False) + "\n")
                raise
            return obs

        inv = c118.collect(
            a.new_raw,
            run_id,
            sample=audited_inventory_sample if paging else c118.live_sample,
            **args,
        )
        c118.require_inventory(a.new_raw, run_id, inv, **args, now=datetime.now(UTC), max_age_s=3)
        r["c118"] = {k: v for k, v in inv.items() if k != "path"}
        observation = c118.live_sample()
        issues = policy_api.validate_start_observation(
            protocol,
            available_bytes=observation["mem_available_bytes"],
            gpu=observation["gpu"],
            thermal=observation["thermal"],
            power=observation["power"],
            psi_full_avg10=policy_api.host_pressure(),
        )
        check(not issues, "start_resources_" + ",".join(issues))
        guard = policy_api.RuntimeGuard(protocol, state0)
        first_io = io_stat(cg)
        memory_fields = MEM_FIELDS + (("pgscan", "pgsteal") if paging else ())
        before = bounded.cgroup_state()
        r["pre_start_memory_stat"] = {k: before["memory_stat"][k] for k in memory_fields}
        check(
            identity(MODEL) == current
            and not at_preventive_limit(before["memory_current"], before["memory_peak"], stop),
            "pre_spawn_identity_or_memory",
        )
        check(
            (datetime.now(UTC) - datetime.fromisoformat(inv["last_utc"])).total_seconds() <= 3,
            "c118_stale",
        )
        model_key = PlacedFile(refs, MODEL, current).key
        with stop_log.open("xb", buffering=0) as logs:
            tick = time.monotonic()
            proc = subprocess.Popen(
                [exe, "-m", MODEL, *ARGS, *(["-lv", "4"] if placement_log else [])],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=logs,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        print("one stock loader started, cgroup cap", cap, flush=True)
        r.update(status="FAIL", server_starts=1)
        closing_at = None
        missing_placement = []
        first_observation_s = None
        last_observation_s = None

        def margin_watch():
            try:
                while not end.is_set():
                    mem = int((cg / "memory.current").read_text())
                    peak = int((cg / "memory.peak").read_text())
                    deadline = closing_at + 10 if closing_at is not None else tick + 180
                    if at_preventive_limit(mem, peak, stop) or time.monotonic() >= deadline:
                        fast.update(
                            reason="CGROUP_PREVENTIVE_MARGIN"
                            if at_preventive_limit(mem, peak, stop)
                            else ("SHUTDOWN_TIMEOUT" if closing_at is not None else "LOAD_TIMEOUT"),
                            current=mem,
                            peak=peak,
                            elapsed_s=round(time.monotonic() - tick, 4),
                        )
                        if proc.poll() is None:
                            os.killpg(proc.pid, signal.SIGKILL)
                        fast["memory_stat_at_stop"] = {
                            k: v
                            for k, v in bounded.cgroup_state()["memory_stat"].items()
                            if k in MEM_FIELDS
                        }
                        return
                    end.wait(0.05)
            except Exception as exc:
                fast["reason"] = "WATCHDOG_" + type(exc).__name__
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)

        watcher = threading.Thread(target=margin_watch, daemon=True)
        watcher.start()
        observed = set()
        prev = tick
        count = 0
        with (raw / "monitor.jsonl").open("x") as series:
            while proc.poll() is None:
                s = {
                    "cgroup": bounded.cgroup_state(),
                    "proc": bounded.proc_status(proc.pid),
                    "gpu": bounded.gpu_state(prospective=True),
                    "thermal": bounded.thermal_state(prospective=True),
                    "mem_available_bytes": bounded.mem_available(),
                    "resource_observation": {
                        "power": policy_api.live_power(),
                        "host_psi_full_avg10": policy_api.host_pressure(),
                    },
                }
                if paging:
                    rollup = bounded.live_smaps_rollup(proc)
                    if rollup is None and proc.poll() is not None:
                        break
                    s["smaps_rollup_bytes"] = rollup_bytes(rollup)
                stamp = time.monotonic()
                s["elapsed_s"] = stamp - tick
                if fast or proc.poll() is not None:
                    break
                check(stamp - prev <= 3, "runtime_telemetry_gap")
                prev = stamp
                reason = guard.check(s)
                check(reason is None, reason or "guard")
                apps = subprocess.check_output(
                    ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
                    text=True,
                    timeout=3,
                )
                check(not ({int(v) for v in apps.split()} - {proc.pid}), "concurrent_compute")
                if proc.poll() is not None:
                    break
                observed.update(vm_objects(proc.pid))
                s["io_stat"] = io_stat(cg)
                s["cgroup"].pop("path", None)
                series.write(json.dumps(s, allow_nan=False) + "\n")
                series.flush()
                count += 1
                r["telemetry_samples"] = count
                last_observation_s = s["elapsed_s"]
                if first_observation_s is None:
                    first_observation_s = last_observation_s
                if paging:
                    maxima = r.setdefault("sampled_smaps_max_bytes", {})
                    for k, v in s["smaps_rollup_bytes"].items():
                        maxima[k] = max(maxima.get(k, 0), v)
                peaks = r.setdefault("sampled_memory_max_bytes", {})
                for key in ("anon", "file", "file_mapped"):
                    peaks[key] = max(peaks.get(key, 0), s["cgroup"]["memory_stat"][key])
                r["sampled_peak_gpu_mib"] = max(
                    r.get("sampled_peak_gpu_mib", 0), s["gpu"]["used_mib"]
                )
                r["sampled_vm_locked_max_bytes"] = max(
                    r.get("sampled_vm_locked_max_bytes", 0), s["proc"]["VmLck"]
                )
                check(stop_log.stat().st_size < 32 * MIB and series.tell() < 32 * MIB, "log_budget")
                text = stop_log.read_text(errors="replace")
                marks = logged_geometry(text)
                if marks["ready"] and closing_at is None:
                    r["ready_s"] = round(time.monotonic() - tick, 4)
                    if placement_log:
                        live = vm_objects(proc.pid)
                        r["ready_vma"] = {
                            "executable": exe_key in live,
                            "gguf": model_key in live,
                            "own_libraries": sorted(k for k, v in dep_ids.items() if v in live),
                        }
                        r["ready_log_geometry"] = marks
                        missing_placement = [k for k, v in marks.items() if not v]
                        if not (
                            r["ready_vma"]["executable"]
                            and r["ready_vma"]["gguf"]
                            and set(r["ready_vma"]["own_libraries"]) == dep_ids.keys()
                        ):
                            missing_placement.append("live_elf_or_gguf")
                    else:
                        check(all(marks.values()), "startup_geometry")
                        check(
                            exe_key in observed
                            and model_key in observed
                            and all(x in observed for x in dep_ids.values()),
                            "elf_or_gguf_mapping",
                        )
                    check("warming up the model" not in text.lower(), "unexpected_warmup")
                    check("processing task, is_child" not in text, "unexpected_request")
                    check(identity(MODEL) == current, "model_changed")
                    shutdown = time.monotonic()
                    if paging:
                        closing_at = shutdown
                    os.killpg(proc.pid, signal.SIGTERM)
                    if paging:
                        end.wait(0.05)
                        continue
                    proc.wait(timeout=10)
                    r["shutdown_s"] = round(time.monotonic() - shutdown, 4)
                    check(proc.returncode == 0, "unclean_ready_shutdown")
                    check(
                        not fast
                        and not at_preventive_limit(0, int((cg / "memory.peak").read_text()), stop),
                        "shutdown_crossed_margin",
                    )
                    r["status"] = "PASS_STOCK_NVME_STARTUP_ONLY"
                    break
                end.wait(0.35)
        if paging and closing_at is not None:
            check(proc.poll() == 0, "unclean_ready_shutdown")
            r["shutdown_s"] = round(time.monotonic() - closing_at, 4)
            detail = bounded.prospective_endpoint_reason(
                first_observation_s,
                last_observation_s,
                time.monotonic() - tick,
                bounded.cgroup_state(),
                state0,
                resources,
            )
            check(detail is None, detail or "endpoint")
            check(not missing_placement, "startup_placement_" + ",".join(missing_placement))
            r["status"] = "PASS_STOCK_NVME_FILE_PAGING_STARTUP"
            if placement_log:
                r["status"] = "PASS_STOCK_NVME_PLACEMENT_AT_READY"
        r["mapped_own_libraries"] = sorted(name for name, val in dep_ids.items() if val in observed)
        r["gguf_mapping_observed"] = model_key in observed
        check(not fast, fast.get("reason", "watchdog"))
        check(r["status"].startswith("PASS"), "server_exited_before_ready")
    except Exception as exc:
        r["reason"] = fast.get("reason", str(exc).replace(str(a.new_raw), "<raw>"))
    finally:
        end.set()
        if watcher:
            watcher.join(timeout=2)
        if proc and proc.poll() is None:
            bounded.stop_own_group(proc)
        if proc:
            r["returncode"] = proc.returncode
            r["server_elapsed_s"] = round(time.monotonic() - tick, 4)
            r["child_gone"] = proc.poll() is not None
        if cg:
            st = bounded.cgroup_state()
            r["end_cgroup"] = {
                k: st[k]
                for k in ("memory_peak", "memory_current", "swap_current", "events", "events_local")
            }
            r["end_memory_stat"] = {k: st["memory_stat"][k] for k in MEM_FIELDS}
            if paging:
                r["end_memory_stat"].update(
                    {k: st["memory_stat"][k] for k in ("pgscan", "pgsteal")}
                )
                if r["server_starts"] and (
                    st["swap_current"]
                    or any(
                        st[which][k] > state0[which][k]
                        for which in ("events", "events_local")
                        for k in ("oom", "oom_kill")
                    )
                ):
                    r.update(status="FAIL", reason="CGROUP_END_OOM_OR_SWAP")
            r["io_stat_delta_by_device"] = (
                io_delta(first_io, io_stat(cg)) if first_io is not None else {}
            )
        if fast:
            r["fast_stop"] = fast
        if stop_log.exists():
            r["log_geometry"] = logged_geometry(stop_log.read_text(errors="replace"))
        r["raw_sha256"] = {p.name: sha(p) for p in raw.iterdir() if p.is_file()}
        r["elapsed_s"] = round(time.monotonic() - start, 4)
        refs.close()
        pending = a.new_output / ".receipt.pending"
        pending.write_text(json.dumps(r, indent=2, sort_keys=True, allow_nan=False) + "\n")
        pending.rename(a.new_output / "receipt.json")
    return r["status"]


def cli(*, paging=False, placement_log=False):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--before-inventory-only",
        action="store_true",
        help="Check the real policy, scope, placement metadata and ELFs, then stop before C118.",
    )
    for name in ("policy", "placement", "binary", "build-receipt", "new-raw", "new-output"):
        ap.add_argument("--" + name, type=Path, required=True)
    status = run(ap.parse_args(), paging=paging, placement_log=placement_log)
    print(status)
    sys.exit(0 if status.startswith("PASS") else 1)


if __name__ == "__main__":
    cli()
