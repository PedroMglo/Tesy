"""No-replace per-arm 60 s start inventory for a future server campaign."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

import c2_server_run as server
from c2_gate import GateError, strict_json
from c17_thermal_recovery import no_other_model
from host_resource_policy import digest, live_power
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
        nvme_policy = policy["nvme"]
        if type(nvme_policy) is not list or not nvme_policy:
            raise GateError("start inventory NVMe policy missing")
        nvme_readings = thermal["nvme_composite_by_sensor"]
        nvme = [(row["sensor"], nvme_readings[row["sensor"]], row["stop_c"])
                for row in nvme_policy]
        gpu_temp, gpu_used = gpu["temperature_c"], gpu["used_mib"]
        gpu_uuid = gpu["uuid"]
        power_source, power_profile = power["source"], power["profile"]
        available = observation["mem_available_bytes"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GateError("start inventory essential sensor missing") from exc
    numbers = (cpu, gpu_temp, gpu_used, available, *(value for _, value, _ in nvme))
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in numbers):
        raise GateError("start inventory nonfinite/invalid sensor")
    if any(not 0 <= value <= 120 for value in (cpu, gpu_temp, *(v for _, v, _ in nvme))) or \
       gpu_used < 0 or available < 0:
        raise GateError("start inventory sensor out of range")
    if gpu_uuid != policy["gpu"]["uuid"] or \
       cpu >= policy["cpu"]["stop_c"] or \
       gpu_temp >= policy["gpu"]["stop_c"] or \
       any(value >= stop for _, value, stop in nvme) or \
       gpu_used >= policy["gpu"]["memory_stop_total_mib"] or \
       available < cap_bytes + policy["memory"]["reserve_bytes"]:
        raise GateError("start inventory resource admission failed")
    if power_source != "AC" or power_source != expected_power["source"] or \
       power_profile != expected_power["profile"]:
        raise GateError("start inventory AC/profile changed")


def collect(root: Path, run_id: str, *, policy: dict, cap_bytes: int,
            expected_power: dict, sample=live_sample, monotonic=time.monotonic,
            sleep=time.sleep, duration_s=60, utc_now=lambda: datetime.now(timezone.utc)):
    if type(duration_s) not in (int, float) or duration_s <= 0:
        raise ValueError("positive inventory duration required")
    path = root / "raw" / f"{run_id}.start-inventory.jsonl"
    start = None
    previous = None
    count = 0
    with path.open("x") as out:
        while True:
            sample_start = monotonic()
            obs = sample()
            sample_end = monotonic()
            if start is None:
                start = sample_end
            elapsed = sample_end - start
            if sample_end < sample_start or (previous is not None and
                    not 0 < sample_end - previous <= 1.5):
                raise GateError("start inventory cadence gap")
            validate_sample(obs, policy=policy, cap_bytes=cap_bytes,
                            expected_power=expected_power)
            row = {"run_id": run_id, "elapsed_s": elapsed,
                   "utc": utc_now().isoformat(),
                   "observation": obs}
            out.write(json.dumps(row, allow_nan=False, sort_keys=True) + "\n")
            out.flush()
            count += 1
            previous = elapsed
            if elapsed + 1e-6 >= duration_s:
                break
            sleep(max(0, start + count - monotonic()))
    if count < math.floor(duration_s) + 1:
        raise GateError("start inventory too few samples")
    return {"schema": "c118-per-arm-start-inventory-v2", "run_id": run_id,
            "duration_s": previous, "sample_count": count, "sha256": sha256(path),
            "policy_sha256": digest(policy), "cap_bytes": cap_bytes,
            "expected_power": expected_power,
            "path": str(path)}


def require_inventory(root: Path, run_id: str, receipt: dict, *, policy: dict,
                      cap_bytes: int, expected_power: dict, duration_s=60,
                      now=None, max_age_s=3):
    """Prospective gate. Historical C117 has no such receipts and remains FAIL."""
    path = root / "raw" / f"{run_id}.start-inventory.jsonl"
    if not path.is_file() or type(receipt) is not dict or \
       receipt.get("schema") != "c118-per-arm-start-inventory-v2" or \
       receipt.get("run_id") != run_id or receipt.get("path") != str(path) or \
       receipt.get("sha256") != sha256(path) or \
       receipt.get("policy_sha256") != digest(policy) or \
       receipt.get("cap_bytes") != cap_bytes or \
       receipt.get("expected_power") != expected_power:
        raise GateError("start inventory identity/hash missing or changed")
    rows = [strict_json(line) for line in path.read_text().splitlines()]
    if len(rows) < math.floor(duration_s) + 1 or receipt.get("sample_count") != len(rows):
        raise GateError("start inventory too few samples")
    times = []
    stamps = []
    for row in rows:
        if type(row) is not dict or row.get("run_id") != run_id:
            raise GateError("start inventory arm identity changed")
        elapsed = row.get("elapsed_s")
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed):
            raise GateError("start inventory elapsed invalid")
        times.append(elapsed)
        try:
            stamp = datetime.fromisoformat(row["utc"])
            if stamp.tzinfo is None:
                raise ValueError("naive UTC")
        except (KeyError, TypeError, ValueError) as exc:
            raise GateError("start inventory UTC invalid") from exc
        stamps.append(stamp)
        validate_sample(row.get("observation"), policy=policy, cap_bytes=cap_bytes,
                        expected_power=expected_power)
    if times[0] != 0 or times[-1] - times[0] + 1e-6 < duration_s or \
       receipt.get("duration_s") != times[-1] or \
       any(not 0 < b - a <= 1.5 for a, b in zip(times, times[1:])) or \
       any((b-a).total_seconds() < -0.1 for a, b in zip(stamps, stamps[1:])) or \
       abs((stamps[-1]-stamps[0]).total_seconds() - (times[-1]-times[0])) > 2:
        raise GateError("start inventory duration/cadence invalid")
    now = now or datetime.now(timezone.utc)
    age = (now-stamps[-1]).total_seconds()
    if not 0 <= age <= max_age_s:
        raise GateError("start inventory stale before launch")
    return len(rows)
