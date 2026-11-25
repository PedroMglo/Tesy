"""One E10 numerical trajectory, with stock FILE_PAGING admission and complete output capture."""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from evaluate import HERE, SIZE, compare, dump, inputs, require

sys.path.insert(0, str(HERE.parent / "stock_startup"))
from start import (
    GIB,
    MODEL,
    MODEL_SHA,
    MODEL_SIZE,
    PlacedFile,
    Reference,
    bounded,
    c55,
    c118,
    identity,
    io_delta,
    io_stat,
    logged_geometry,
    policy_api,
    read,
    rollup_bytes,
    sha,
    vm_objects,
)  # noqa: E402

CAP = 10 * GIB
PACKED_SHA = "80536eadb97029b88c1d54a06a0ffb2f693c2a10029631f10e59e86745d73479"


def timeout_handler(*_):
    raise TimeoutError("bounded_client_timeout")


def run(a):
    os.umask(0o077)
    a.new_private.mkdir(mode=0o700, exist_ok=False)
    raw = a.new_private / "raw"
    raw.mkdir()
    a.new_output.mkdir(mode=0o700, exist_ok=False)
    r = {
        "status": "NOT_RUN",
        "client_starts": 0,
        "scope": "SUPPLIED_C110_16_1_1",
        "raw_sha256": {},
        "protocol_sha256": sha(HERE / "protocol.md"),
        "runner_sha256": sha(__file__),
        "energy_j": None,
    }
    proc = None
    cg = None
    before_io = None
    refs = ExitStack()
    log_path = raw / "client.log"
    tensor_path = raw / "candidate.logits.f32"
    overall = time.monotonic()
    try:
        packed, gold, arms = inputs(a.raw_parent)
        import hashlib

        require(hashlib.sha256(packed).hexdigest() == PACKED_SHA, "packed fixture")
        r.update(reference_arms=arms, input_sha256=PACKED_SHA)
        build = read(a.client_receipt)
        require(
            build["status"] == "PASS_STOCK_NUMERIC_CLIENT_MODEL_FREE"
            and build["source_sha256"] == sha(HERE / "client.cpp")
            and build["protocol_sha256"] == r["protocol_sha256"]
            and build["stock_build_receipt_sha256"] == sha(a.stock_receipt),
            "client provenance",
        )
        stock = read(a.stock_receipt)
        require(
            stock["status" if "status" in stock else "decision"]
            == "PASS_STOCK_BUILD_AND_MODEL_FREE_CLI"
            and stock["pin"] == build["pin"],
            "stock provenance",
        )
        policy = read(a.policy)
        require(policy_api.derive_policy(snapshot=policy["snapshot"]) == policy, "C55 derivation")
        limits = policy_api.freeze_protocol_resource_limits(
            policy,
            cgroup_memory_max_bytes=CAP,
            start_mode="CAPACITY_ADMISSION_START",
            execution_class="FILE_PAGING",
        )
        proto = {"limits": {}, "resources": limits}
        policy_api.validate_resource_protocol(proto)
        initial = bounded.cgroup_state()
        require(
            initial
            and initial["memory_max"] == CAP
            and initial["memory_high"] == limits["cgroup"]["memory_high_bytes"]
            and initial["swap_max"] == initial["swap_current"] == 0,
            "cgroup cap",
        )
        cg = Path("/sys/fs/cgroup") / initial["path"].lstrip("/")
        model_stat = identity(MODEL)
        placed = read(a.placement)
        require(
            placed["status"] == "PASS_NVME_MODEL_PLACEMENT"
            and placed["source_sha256"]
            == placed["destination_direct_reread"]["sha256"]
            == MODEL_SHA
            and MODEL.samefile(placed["working_copy"])
            and model_stat[2] == MODEL_SIZE
            and model_stat[4] <= a.placement.stat().st_mtime_ns,
            "model receipt",
        )
        meta = policy["snapshot"]["model_stat"]
        require(
            model_stat[:4] == (meta["dev"], meta["inode"], MODEL_SIZE, meta["mtime_ns"]),
            "model changed",
        )
        c55.mounts({"model": MODEL.resolve(strict=True)})
        exe = a.client.resolve(strict=True)
        keys = {"numeric-client": Reference(refs, exe, build["executable_sha256"]).key}
        libs = a.stock_lib_dir.resolve(strict=True)
        for name, digest in build["own_libraries"].items():
            p = (libs / name).resolve(strict=True)
            require(
                p.parent == libs and digest == stock["own_libs_sha256"][name],
                "unexpected stock DSO",
            )
            keys[name] = Reference(refs, p, digest).key
        r.update(
            client_sha256=build["executable_sha256"],
            policy_sha256=sha(a.policy),
            model_sha256=MODEL_SHA,
            build_receipt_sha256=sha(a.client_receipt),
            own_libs=sorted(build["own_libraries"]),
        )
        if a.before_inventory_only:
            r["status"] = "PASS_PRE_INVENTORY_WITHOUT_MODEL"
            return r["status"]
        cfg = dict(
            policy=policy,
            cap_bytes=CAP,
            expected_power={k: policy["power"][k] for k in ("source", "profile")},
        )

        def sample():
            obs = c118.live_sample()
            try:
                c118.validate_sample(obs, **cfg)
            except Exception:
                (raw / "failed-inventory-sample.json").write_text(json.dumps(obs) + "\n")
                raise
            return obs

        name = "stock-c110-numeric"
        inv = c118.collect(a.new_private, name, sample=sample, duration_s=60, **cfg)
        c118.require_inventory(a.new_private, name, inv, duration_s=60, max_age_s=3, **cfg)
        r["c118"] = {k: v for k, v in inv.items() if k != "path"}
        obs = sample()
        reasons = policy_api.validate_start_observation(
            proto,
            available_bytes=obs["mem_available_bytes"],
            gpu=obs["gpu"],
            thermal=obs["thermal"],
            power=obs["power"],
            psi_full_avg10=policy_api.host_pressure(),
        )
        require(not reasons, "start_" + ",".join(reasons))
        keys["target-gguf"] = PlacedFile(refs, MODEL, model_stat).key
        before_io = io_stat(cg)
        require(
            (datetime.now(UTC) - datetime.fromisoformat(inv["last_utc"])).total_seconds() <= 3,
            "stale C118",
        )
        guard = policy_api.RuntimeGuard(proto, initial)
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "CUDA_VISIBLE_DEVICES": "0",
            "LD_LIBRARY_PATH": str(libs),
            "HF_HUB_OFFLINE": "1",
        }
        with log_path.open("xb", buffering=0) as log:
            begin = time.monotonic()
            proc = subprocess.Popen(
                [exe, MODEL, tensor_path],
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        signal.alarm(180)
        r.update(status="FAIL", client_starts=1)
        proc.stdin.write(packed)
        proc.stdin.close()
        print("C118 admitted, one stock C110 numerical client", flush=True)
        prev = begin
        observed = set()
        first = None
        last = None
        with (raw / "monitor.jsonl").open("x") as series:
            while proc.poll() is None:
                s = {
                    "cgroup": bounded.cgroup_state(),
                    "proc": bounded.proc_status(proc.pid),
                    "smaps": bounded.live_smaps_rollup(proc),
                    "gpu": bounded.gpu_state(prospective=True),
                    "thermal": bounded.thermal_state(prospective=True),
                    "mem_available_bytes": bounded.mem_available(),
                    "resource_observation": {
                        "power": policy_api.live_power(),
                        "host_psi_full_avg10": policy_api.host_pressure(),
                    },
                }
                if proc.poll() is not None:
                    break
                s["smaps"] = rollup_bytes(s["smaps"])
                now = time.monotonic()
                s["elapsed_s"] = now - begin
                require(now - prev <= 3, "runtime_gap")
                prev = now
                why = guard.check(s)
                require(why is None, why or "runtime_guard")
                apps = subprocess.check_output(
                    ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
                    text=True,
                    timeout=3,
                )
                require(not ({int(p) for p in apps.split()} - {proc.pid}), "concurrent_compute")
                if proc.poll() is not None:
                    break
                observed.update(vm_objects(proc.pid))
                s["io"] = io_stat(cg)
                s["cgroup"].pop("path")
                series.write(json.dumps(s, allow_nan=False) + "\n")
                series.flush()
                first = s["elapsed_s"] if first is None else first
                last = s["elapsed_s"]
                r["sampled_gpu_peak_mib"] = max(
                    r.get("sampled_gpu_peak_mib", 0), s["gpu"]["used_mib"]
                )
                require(sum(p.stat().st_size for p in raw.iterdir()) <= 64 * 2**20, "output_budget")
                time.sleep(0.35)
        r["mapped"] = sorted(k for k, v in keys.items() if v in observed)
        why = bounded.prospective_endpoint_reason(
            first, last, time.monotonic() - begin, bounded.cgroup_state(), initial, limits
        )
        require(why is None, why or "endpoint")
        require(proc.returncode == 0 and identity(MODEL) == model_stat, "client_exit_or_model")
        require(set(r["mapped"]) == keys.keys(), "wrong VMA bindings")
        text = log_path.read_text(errors="replace")
        require(
            "warming up the model" not in text and text.count("STOCK_NUMERIC_READY") == 1,
            "startup_probe",
        )
        geometry = logged_geometry(text)
        require(all(v for k, v in geometry.items() if k != "ready"), "stock geometry")
        rows = re.findall(r"STOCK_NUMERIC_ROW begin=(\d+) count=(\d+) last=(\d+) n=(\d+)", text)
        require(
            rows
            == [
                ("0", "16", "15", "201088"),
                ("16", "1", "16", "201088"),
                ("17", "1", "17", "201088"),
            ],
            "row shape",
        )
        require(tensor_path.stat().st_size == SIZE, "missing full logits")
        r.update(compare(tensor_path.read_bytes(), gold))
    except Exception as exc:
        r["reason"] = str(exc)
    finally:
        signal.alarm(0)
        if proc:
            bounded.stop_own_group(proc)
            r.update(
                client_returncode=proc.returncode,
                client_elapsed_s=round(time.monotonic() - begin, 4),
                child_gone=proc.poll() is not None,
            )
        if cg:
            s = bounded.cgroup_state()
            r.update(
                cgroup_peak_bytes=s["memory_peak"],
                events=s["events"],
                swap_current=s["swap_current"],
            )
            if before_io is not None:
                r["io_by_device"] = io_delta(before_io, io_stat(cg))
        r["raw_sha256"] = {p.name: sha(p) for p in raw.iterdir() if p.is_file()}
        r["elapsed_s"] = round(time.monotonic() - overall, 4)
        refs.close()
        dump(a.new_output, r)
    return r["status"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "raw-parent",
        "client",
        "client-receipt",
        "stock-lib-dir",
        "stock-receipt",
        "policy",
        "placement",
        "new-private",
        "new-output",
    ):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--before-inventory-only", action="store_true")
    signal.signal(signal.SIGALRM, timeout_handler)
    status = run(p.parse_args())
    print(status)
    sys.exit(0 if status.startswith("PASS") else 1)
