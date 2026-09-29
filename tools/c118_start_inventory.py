"""No-replace per-arm 60 s start inventory for a future server campaign."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

import c2_server_run as server
from c2_gate import GateError
from c17_thermal_recovery import no_other_model
from host_resource_policy import live_power
from run_bounded import sha256


def live_sample():
    no_other_model()
    return {"thermal": server.thermal_state(prospective=True),
            "gpu": server.gpu_state(prospective=True),
            "power": live_power(),
            "mem_available_bytes": server.mem_available()}


def validate_sample(observation, *, policy, cap_bytes, expected_power):
    if type(observation) is not dict:
        raise GateError("start inventory observation missing")
    try:
        thermal, gpu, power = (observation[key] for key in ("thermal", "gpu", "power"))
        cpu = thermal["cpu_tctl_c"]
        sensor = policy["nvme"][0]["sensor"]
        nvme = thermal["nvme_composite_by_sensor"][sensor]
        gpu_temp, gpu_used = gpu["temperature_c"], gpu["used_mib"]
        gpu_uuid = gpu["uuid"]
        power_source, power_profile = power["source"], power["profile"]
        available = observation["mem_available_bytes"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GateError("start inventory essential sensor missing") from exc
    numbers = (cpu, nvme, gpu_temp, gpu_used, available)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in numbers):
        raise GateError("start inventory nonfinite/invalid sensor")
    if gpu_uuid != policy["gpu"]["uuid"] or \
       cpu >= policy["cpu"]["stop_c"] or \
       gpu_temp >= policy["gpu"]["stop_c"] or \
       nvme >= policy["nvme"][0]["stop_c"] or \
       gpu_used >= policy["gpu"]["memory_stop_total_mib"] or \
       available < cap_bytes + policy["memory"]["reserve_bytes"]:
        raise GateError("start inventory resource admission failed")
    if power_source != "AC" or power_source != expected_power["source"] or \
       power_profile != expected_power["profile"]:
        raise GateError("start inventory AC/profile changed")


def collect(root: Path, run_id: str, *, policy: dict, cap_bytes: int,
            expected_power: dict, sample=live_sample, monotonic=time.monotonic,
            sleep=time.sleep, duration_s=60):
    if type(duration_s) not in (int, float) or duration_s <= 0:
        raise ValueError("positive inventory duration required")
    path = root / "raw" / f"{run_id}.start-inventory.jsonl"
    start = monotonic()
    previous = None
    count = 0
    with path.open("x") as out:
        while True:
            elapsed = monotonic() - start
            if previous is not None and not 0 < elapsed - previous <= 1.5:
                raise GateError("start inventory cadence gap")
            obs = sample()
            validate_sample(obs, policy=policy, cap_bytes=cap_bytes,
                            expected_power=expected_power)
            row = {"elapsed_s": elapsed,
                   "utc": datetime.now(timezone.utc).isoformat(),
                   "observation": obs}
            out.write(json.dumps(row, allow_nan=False, sort_keys=True) + "\n")
            out.flush()
            count += 1
            previous = elapsed
            if elapsed >= duration_s:
                break
            sleep(max(0, start + count - monotonic()))
    if count < math.floor(duration_s) + 1:
        raise GateError("start inventory too few samples")
    return {"schema": "c118-per-arm-start-inventory-v1", "run_id": run_id,
            "duration_s": previous, "sample_count": count, "sha256": sha256(path),
            "path": str(path)}
