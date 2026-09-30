#!/usr/bin/env python3
"""Run a local llama.cpp command with a resource watchdog and compact manifest."""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from c2_gate import strict_json
from host_resource_policy import (RuntimeGuard,ResourcePolicyError,
    validate_resource_protocol,validate_start_observation,host_pressure,live_power)


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_identity(path):
    st = Path(path).stat()
    return {"dev": st.st_dev, "inode": st.st_ino, "size_bytes": st.st_size,
            "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns}


def backend_library_hashes(binary, backend_dir):
    result = {}
    output = subprocess.check_output(["ldd", binary], text=True, timeout=15)
    root = backend_dir.resolve()
    for line in output.splitlines():
        if "=>" not in line:
            continue
        target = line.split("=>", 1)[1].strip().split()[0]
        path = Path(target)
        if path.is_file() and path.resolve().is_relative_to(root):
            resolved = path.resolve()
            result[str(resolved.relative_to(root))] = sha256(resolved)
    return result


def process_identity(pid):
    stat = Path(f"/proc/{pid}/stat").read_text()
    fields = stat[stat.rfind(")") + 2:].split()
    start_ticks = int(fields[19])
    cgroup = next(line.split("::", 1)[1].strip()
                  for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines()
                  if line.startswith("0::"))
    inode = (Path("/sys/fs/cgroup") / cgroup.lstrip("/")).stat().st_ino
    return {"pid": pid, "start_ticks": start_ticks,
            "cgroup_path": cgroup, "cgroup_inode": inode}


def mapped_backend_libraries(pid, backend_dir, hash_cache=None):
    """Read actual mappings; include unexpected llama/ggml libraries outside the backend."""
    root = backend_dir.resolve()
    found = {}
    for line in Path(f"/proc/{pid}/maps").read_text().splitlines():
        path = line.rsplit(" ", 1)[-1]
        if not path.startswith("/") or " (deleted)" in line:
            continue
        candidate = Path(path).resolve()
        if not candidate.is_file() or ".so" not in candidate.name or not (
                candidate.is_relative_to(root) or candidate.name.startswith(("libllama", "libggml"))):
            continue
        key = str(candidate.relative_to(root)) if candidate.is_relative_to(root) else str(candidate)
        identity = file_identity(candidate)
        cached = hash_cache.get(key) if hash_cache is not None else None
        value = cached[1] if cached and cached[0] == identity else sha256(candidate)
        if hash_cache is not None:
            hash_cache[key] = (identity, value)
        found[key] = value
    return found


def relevant_environment(env):
    exact = {"LD_LIBRARY_PATH", "LD_PRELOAD", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER"}
    return {key: value for key, value in env.items()
            if key in exact or key.startswith(("LLAMA_", "TESY_", "GGML_", "CUDA_"))}


def mapped_libraries_match(expected, mapped):
    return type(expected) is dict and bool(expected) and type(mapped) is dict and mapped == expected


def proc_status(pid):
    try:
        lines = Path(f"/proc/{pid}/status").read_text().splitlines()
        d = {}
        for line in lines:
            if line.startswith(("VmRSS:", "VmSwap:", "VmHWM:", "VmLck:")):
                k, v = line.split(":", 1)
                d[k] = int(v.strip().split()[0]) * 1024
        for line in Path(f"/proc/{pid}/io").read_text().splitlines():
            if line.startswith(("read_bytes:", "rchar:", "syscr:")):
                k, v = line.split(":", 1)
                d[k] = int(v)
        return d
    except (FileNotFoundError, ProcessLookupError):
        return {}

def live_smaps_rollup(process):
    try:
        return Path(f'/proc/{process.pid}/smaps_rollup').read_text()
    except (FileNotFoundError, ProcessLookupError):
        try:
            process.wait(timeout=0.2)
            return None
        except subprocess.TimeoutExpired:
            raise RuntimeError('required live smaps_rollup missing')


def mem_available():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return None


def cgroup_state():
    try:
        rel = next(line.split("::", 1)[1].strip() for line in Path("/proc/self/cgroup").read_text().splitlines() if "::" in line)
        base = Path("/sys/fs/cgroup") / rel.lstrip("/")
        def number(name):
            value = (base / name).read_text().strip()
            return None if value == "max" else int(value)
        events = {}
        for line in (base / "memory.events").read_text().splitlines():
            k, v = line.split()
            events[k] = int(v)
        local_events = {}
        for line in (base / "memory.events.local").read_text().splitlines():
            k, v = line.split()
            local_events[k] = int(v)
        pressure = {}
        for line in (base / "memory.pressure").read_text().splitlines():
            label, *pairs = line.split()
            pressure[label] = {k: float(v) if k != "total" else int(v)
                               for k, v in (item.split("=", 1) for item in pairs)}
        memstat = {}
        for line in (base / "memory.stat").read_text().splitlines():
            k, v = line.split()
            memstat[k] = int(v)
        return {"path": rel, "memory_max": number("memory.max"),
                "memory_high": number("memory.high"),
                "swap_max": number("memory.swap.max"), "memory_current": number("memory.current"),
                "memory_peak": number("memory.peak"),
                "swap_current": number("memory.swap.current"), "memory_stat": memstat,
                "events": events, "events_local": local_events, "pressure": pressure}
    except (OSError, ValueError, StopIteration):
        return None


def model_fd_state(pid, model_path):
    if not model_path:
        return None
    result = {"open": 0, "direct": 0, "buffered": 0}
    try:
        for fd in Path(f"/proc/{pid}/fd").iterdir():
            try:
                if os.readlink(fd) != model_path:
                    continue
                flags_line = next(line for line in Path(f"/proc/{pid}/fdinfo/{fd.name}").read_text().splitlines() if line.startswith("flags:"))
                flags = int(flags_line.split()[1], 8)
                result["open"] += 1
                result["direct" if flags & os.O_DIRECT else "buffered"] += 1
            except (OSError, StopIteration, ValueError):
                continue
    except OSError:
        pass
    return result


def gpu_state(*, prospective=False):
    try:
        fields = ("uuid,pci.bus_id,memory.used,temperature.gpu,power.draw" if prospective
                  else "memory.used,temperature.gpu,power.draw")
        p = subprocess.run(
            ["nvidia-smi", "--query-gpu="+fields, "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, check=True,
        )
        if len(p.stdout.strip().splitlines()) != 1:
            return None
        parts = [x.strip() for x in p.stdout.strip().split(",")]
        if prospective:
            from host_resource_policy import finite
            if len(parts)!=5:
                return None
            uuid,bdf=parts[:2]
            row={"uuid":uuid,"bdf":bdf,
                 "used_mib":finite(float(parts[2]),"GPU used MiB",0),
                 "temperature_c":finite(float(parts[3]),"GPU temperature",0,120),
                 "power_w":finite(float(parts[4]),"GPU power",0)}
            return row
        return {"used_mib": float(parts[0]), "temperature_c": float(parts[1]), "power_w": float(parts[2])}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def thermal_state(*, prospective=False):
    try:
        p = subprocess.run(["sensors", "-j"], capture_output=True, text=True, timeout=3, check=True)
        devices = json.loads(p.stdout)
        result = {}
        nvme = {}
        for device, reading in devices.items():
            if device.startswith("k10temp-"):
                result["cpu_tctl_c"] = reading["Tctl"]["temp1_input"]
            elif device.startswith("nvme-"):
                value = reading["Composite"]["temp1_input"]
                if prospective:
                    from host_resource_policy import temp
                    nvme[device] = temp(value, "NVMe Composite")
                else:
                    result["nvme_composite_c"] = value
        if prospective:
            from host_resource_policy import temp
            result["cpu_tctl_c"] = temp(result["cpu_tctl_c"], "CPU Tctl")
            result["nvme_composite_by_sensor"] = nvme
        return result or None
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return None


def stop_own_group(process):
    if process.poll() is None:
        expected = getattr(process, '_tesy_identity', None)
        if expected is not None:
            if process_identity(process.pid) != expected or \
               os.path.realpath(f'/proc/{process.pid}/exe') != process._tesy_executable:
                raise RuntimeError('own child PID/start ticks/executable/scope changed; stop refused')
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if expected is not None and process_identity(process.pid) != expected:
                raise RuntimeError('own child identity changed during stop')
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def prospective_endpoint_reason(first_sample_s,last_sample_s,elapsed_s,end,start,resources):
    """Classify start/end coverage and final cgroup without using last as first."""
    if first_sample_s is None or last_sample_s is None or \
       first_sample_s > 2 or elapsed_s-last_sample_s > 2:
        return 'PROSPECTIVE_ENDPOINT_TELEMETRY_MISSING'
    if not end or end.get('memory_max')!=resources['cgroup']['memory_max_bytes'] or \
       end.get('swap_max')!=0 or end.get('swap_current')!=0:
        return 'PROSPECTIVE_CGROUP_END_INVALID'
    if resources.get('execution_class') == 'FILE_PAGING' and \
       end.get('memory_high') != resources['cgroup']['memory_high_bytes']:
        return 'PROSPECTIVE_CGROUP_END_HIGH_INVALID'
    if any(end[group][event]>start[group][event]
           for group in ('events','events_local')
           for event in (('oom','oom_kill') if resources.get('execution_class') == 'FILE_PAGING'
                         else ('max','oom','oom_kill'))):
        return 'PROSPECTIVE_CGROUP_END_EVENT'
    return None


def inventory_before_spawn(root,run_id,protocol):
    """Only new opt-in flag uses this real producer/consumer chain at Popen."""
    from c118_start_inventory import collect,require_inventory
    r=validate_resource_protocol(protocol)
    contract=protocol.get('start_inventory')
    if not isinstance(contract,dict) or contract.get('schema')!='c120-start-inventory-v1' or contract.get('duration_s')!=60 or contract.get('max_age_s')!=3:
        raise RuntimeError('opt-in frozen inventory contract invalid')
    policy_path=root/'resource-policy.json'
    if sha256(policy_path)!=contract.get('policy_sha256'):raise RuntimeError('opt-in policy SHA changed')
    policy=strict_json(policy_path.read_text());power={k:policy['power'][k] for k in ('source','profile')}
    cap=r['cgroup']['memory_max_bytes']
    receipt=collect(root,run_id,policy=policy,cap_bytes=cap,expected_power=power,duration_s=60)
    path=root/'raw'/f'{run_id}.start-inventory.receipt.json'
    with path.open('x') as f:json.dump(receipt,f,indent=2,sort_keys=True);f.write('\n')
    now=dt.datetime.now(dt.timezone.utc)
    require_inventory(root,run_id,receipt,policy=policy,cap_bytes=cap,expected_power=power,duration_s=60,now=now,max_age_s=3)
    invoked=dt.datetime.now(dt.timezone.utc)
    if not 0<=(invoked-dt.datetime.fromisoformat(receipt['last_utc'])).total_seconds()<=3:
        raise RuntimeError('opt-in inventory stale at process creation')
    return {'receipt_sha256':sha256(path),'checked_utc':now.isoformat(),
            'popen_invoked_utc':invoked.isoformat(),'popen_invoked_monotonic_ns':time.monotonic_ns()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--model-id", required=True)
    p.add_argument("--backend", choices=["stock", "streaming", "streaming-reference", "streaming-reference-c2", "streaming-c6-attn-compat"], required=True)
    p.add_argument("--backend-root", type=Path, help="explicit pinned backend checkout for isolated worktree runs")
    p.add_argument("--output-root", type=Path, help="no-replace run artefact directory")
    p.add_argument("--variant", required=True)
    p.add_argument("--workload", required=True)
    p.add_argument("--cache-condition", required=True)
    p.add_argument("--timeout-s", type=int, default=300)
    p.add_argument("--max-rss-gib", type=float, default=24.0)
    p.add_argument("--max-cgroup-gib", type=float, default=None,
                   help="optional prospective reservation below the enforced cgroup memory.max")
    p.add_argument("--min-available-gib", type=float, default=6.0)
    p.add_argument("--max-gpu-mib", type=float, default=7600.0)
    p.add_argument("--max-cpu-c", type=float, default=None)
    p.add_argument("--max-gpu-c", type=float, default=None)
    p.add_argument("--max-nvme-c", type=float, default=None)
    p.add_argument("--require-telemetry", action="store_true")
    p.add_argument("--resource-protocol", type=Path,
                   help="versioned prospective resource authority; legacy caps disallowed")
    p.add_argument("--collect-start-inventory", action="store_true",
                   help="opt-in only: collect/validate60s inventory immediately at actual spawn")
    p.add_argument("--allow-cgroup-max-reclaim", action="store_true",
                   help="diagnostic reference only; OOM and memory.peak remain stop conditions")
    p.add_argument("--env", action="append", default=[], help="explicit KEY=VALUE for the child")
    p.add_argument("--stdin-file", help="input file for a bounded multi-turn CLI run")
    p.add_argument("--ready-marker", help="stdout marker emitted after model/context load")
    p.add_argument("command", nargs=argparse.REMAINDER)
    a = p.parse_args()
    prospective = a.resource_protocol is not None
    resource_contract = None
    resource_protocol = None
    if prospective:
        legacy_resource_flags=("--max-rss-gib","--max-cgroup-gib","--min-available-gib",
                               "--max-gpu-mib","--max-cpu-c","--max-gpu-c","--max-nvme-c",
                               "--allow-cgroup-max-reclaim")
        if any(flag in sys.argv[1:] for flag in legacy_resource_flags) or not a.require_telemetry:
            p.error('prospective resource protocol requires telemetry and forbids legacy caps')
        resource_protocol = strict_json(a.resource_protocol.read_text())
        resource_contract = validate_resource_protocol(resource_protocol)
    if a.max_cgroup_gib is not None and (not math.isfinite(a.max_cgroup_gib) or a.max_cgroup_gib <= 0):
        p.error("--max-cgroup-gib must be positive and finite")
    cmd = a.command[1:] if a.command and a.command[0] == "--" else a.command
    if not cmd or not Path(cmd[0]).is_file():
        p.error("command must start with an existing local binary path")
    model_path = next((str(Path(arg).resolve()) for arg in cmd if arg.endswith(".gguf") and Path(arg).is_file()), None)
    artifact_identity = None
    if model_path:
        lock = json.loads((ROOT / "models.lock.json").read_text())
        matches = [entry for entry in lock["models"] if entry["id"] == a.model_id and
                   str(Path(entry["path"]).resolve()) == model_path]
        if len(matches) != 1:
            p.error("model ID/path missing from lock")
        artifact_identity = {"revision": matches[0].get("revision"),
                             "sha256_previously_verified": matches[0].get("sha256_verified"),
                             "stat_at_launch": file_identity(model_path)}
    if a.stdin_file and not Path(a.stdin_file).is_file():
        p.error("stdin-file must exist")
    if not a.run_id.replace("-", "").replace("_", "").isalnum():
        p.error("run-id must contain only letters, digits, dash or underscore")
    child_env = os.environ.copy()
    explicit_env = {}
    for assignment in a.env:
        if "=" not in assignment:
            p.error("--env requires KEY=VALUE")
        key, value = assignment.split("=", 1)
        if not key or not key.replace("_", "").isalnum():
            p.error("invalid environment variable name")
        explicit_env[key] = value
        child_env[key] = value

    out = a.output_root if a.output_root else ROOT / "results"
    out.mkdir(parents=True, exist_ok=True)
    stem = out / a.run_id
    for suffix in (".json", ".json.tmp", ".stdout", ".stderr", ".samples.jsonl"):
        if Path(str(stem) + suffix).exists():
            p.error(f"run-id already exists: {a.run_id}")

    backend_dir = (a.backend_root if a.backend_root else ROOT / "backends" / a.backend).resolve()
    revision = subprocess.check_output(["git", "-C", str(backend_dir), "rev-parse", "HEAD"], text=True).strip()
    manifest = {
        "run_id": a.run_id,
        "started_utc": None,
        "model_id": a.model_id,
        "model_path": model_path,
        "artifact_identity": artifact_identity,
        "backend": a.backend,
        "backend_root": str(backend_dir),
        "backend_sha": revision,
        "binary_sha256": sha256(cmd[0]),
        "backend_libraries_sha256": backend_library_hashes(cmd[0], backend_dir),
        "variant": a.variant,
        "workload": a.workload,
        "workload_sha256": sha256(a.workload) if Path(a.workload).is_file() else None,
        "input_files_sha256": {arg: sha256(arg) for arg in cmd if arg.endswith(".ids") and Path(arg).is_file()},
        "cache_condition": a.cache_condition,
        "command": cmd,
        "explicit_env": explicit_env,
        "relevant_environment": relevant_environment(child_env),
        "stdin_file": a.stdin_file,
        "stdin_sha256": sha256(a.stdin_file) if a.stdin_file else None,
        "ready_marker": a.ready_marker,
        "limits": {"timeout_s": a.timeout_s, "max_rss_gib": a.max_rss_gib,
                   "max_cgroup_gib": a.max_cgroup_gib,
                   "min_available_gib": a.min_available_gib, "max_gpu_mib": a.max_gpu_mib,
                   "max_cpu_c": a.max_cpu_c, "max_gpu_c": a.max_gpu_c,
                   "max_nvme_c": a.max_nvme_c,
                   "allow_cgroup_max_reclaim": a.allow_cgroup_max_reclaim,
                   "require_telemetry": a.require_telemetry},
        "cgroup_start": cgroup_state(),
        "publication": "local only; stdout/stderr are untracked",
        "samples_path": str(stem) + ".samples.jsonl",
    }
    manifest["cgroup_limit_enforced"] = bool(manifest["cgroup_start"] and
                                                manifest["cgroup_start"]["memory_max"] is not None and
                                                manifest["cgroup_start"]["swap_max"] == 0)
    if prospective:
        manifest['limits']={'resource_protocol_sha256':sha256(a.resource_protocol),
                            'timeout_s':a.timeout_s,'require_telemetry':True}
        manifest['resource_authority']=resource_contract
        start_cg=manifest['cgroup_start']
        if not start_cg or start_cg['memory_max']!=resource_contract['cgroup']['memory_max_bytes'] or \
           start_cg['swap_max']!=0:
            p.error('prospective cgroup cap/swap differs from single authority')
        if resource_contract.get('execution_class') == 'FILE_PAGING' and \
           start_cg.get('memory_high') != resource_contract['cgroup']['memory_high_bytes']:
            p.error('FILE_PAGING memory.high differs from single authority')
        expected_scope = resource_protocol.get('execution_scope_unit')
        if expected_scope and not start_cg['path'].endswith('/'+expected_scope+'.service'):
            p.error('frozen campaign scope differs at actual entrypoint')
        gpu_start=gpu_state(prospective=True)
        thermal_start=thermal_state(prospective=True)
        available_start=mem_available()
        if not gpu_start or not thermal_start or available_start is None:
            p.error('prospective start sensors absent')
        power_start=live_power();psi_start=host_pressure()
        start_reasons=validate_start_observation(
            resource_protocol,available_bytes=available_start,gpu=gpu_start,
            thermal=thermal_start,power=power_start,psi_full_avg10=psi_start)
        manifest['resource_start_observation']={
            'gpu':gpu_start,'thermal':thermal_start,'mem_available_bytes':available_start,
            'power':power_start,'host_psi_full_avg10':psi_start,
            'admission_reasons':start_reasons}
        if start_reasons:p.error('prospective start admission: '+','.join(start_reasons))
    if a.require_telemetry and (not manifest["cgroup_limit_enforced"] or
                                manifest["cgroup_start"].get("memory_peak") is None):
        p.error("enforced cgroup and memory.peak required")
    if a.require_telemetry and not prospective and (not gpu_state() or not thermal_state()):
        p.error("GPU and thermal sensors required before launch")
    with open(str(stem) + ".stdout", "xb") as stdout, open(str(stem) + ".stderr", "xb") as stderr, open(str(stem) + ".samples.jsonl", "x") as samples:
        stdin = open(a.stdin_file, "rb") if a.stdin_file else subprocess.DEVNULL
        start_inventory = None
        if a.collect_start_inventory:
            if not prospective or out.name != 'raw':
                raise RuntimeError('fresh inventory requires prospective protocol/raw session root')
            start_inventory = inventory_before_spawn(out.parent,a.run_id,resource_protocol)
            cg_now=cgroup_state()
            if not cg_now or cg_now.get('memory_max')!=resource_contract['cgroup']['memory_max_bytes'] or cg_now.get('swap_max')!=0 or cg_now.get('path')!=manifest['cgroup_start'].get('path'):
                raise RuntimeError('opt-in cgroup identity/cap changed during inventory')
            if sha256(a.resource_protocol)!=manifest['limits']['resource_protocol_sha256'] or sha256(cmd[0])!=manifest['binary_sha256'] or backend_library_hashes(cmd[0],backend_dir)!=manifest['backend_libraries_sha256']:
                raise RuntimeError('opt-in protocol/binary/library identity changed during inventory')
            if artifact_identity and file_identity(model_path)!=artifact_identity['stat_at_launch']:
                raise RuntimeError('opt-in model changed during inventory')
            receipt_path=out/(a.run_id+'.start-inventory.receipt.json')
            receipt_now=strict_json(receipt_path.read_text())
            if sha256(receipt_path)!=start_inventory['receipt_sha256'] or not 0<=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(receipt_now['last_utc'])).total_seconds()<=3:
                raise RuntimeError('opt-in inventory changed/stale at actual spawn')
            final_obs=strict_json((out/(a.run_id+'.start-inventory.jsonl')).read_text().splitlines()[-1])['observation']
            final_reasons=validate_start_observation(resource_protocol,available_bytes=final_obs['mem_available_bytes'],gpu=final_obs['gpu'],thermal=final_obs['thermal'],power=final_obs['power'],psi_full_avg10=host_pressure())
            if final_reasons:raise RuntimeError('opt-in start authority failed at Popen: '+','.join(final_reasons))
            invoked_now=dt.datetime.now(dt.timezone.utc)
            if not 0<=(invoked_now-dt.datetime.fromisoformat(receipt_now['last_utc'])).total_seconds()<=3:raise RuntimeError('opt-in final freshness expired')
            start_inventory['popen_invoked_utc']=invoked_now.isoformat()
            start_inventory['popen_invoked_monotonic_ns']=time.monotonic_ns()
        t0 = time.monotonic()
        manifest["started_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        process = subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr,
                                   start_new_session=True, env=child_env)
        try:
            launch_identity = process_identity(process.pid)
        except (OSError, ValueError, StopIteration) as exc:
            stop_own_group(process)
            raise RuntimeError(f"cannot establish child identity: {exc}") from exc
        manifest["process_identity"] = launch_identity
        process._tesy_identity = launch_identity
        process._tesy_executable = os.path.realpath(f'/proc/{process.pid}/exe')
        if prospective and launch_identity['cgroup_path'] != manifest['cgroup_start']['path']:
            stop_own_group(process)
            raise RuntimeError('model child escaped frozen monitor scope')
        if start_inventory is not None:
            manifest['start_inventory'] = start_inventory
            launch_path = Path(str(stem)+'.launch.json')
            with launch_path.open('x') as launch_file:
                json.dump({'run_id':a.run_id,'process_identity':launch_identity,
                           'executable':str(Path(cmd[0]).resolve()),'binary_sha256':manifest['binary_sha256'],
                           'start_inventory':start_inventory,'resource_protocol_sha256':sha256(a.resource_protocol),
                           'model_stat':artifact_identity},launch_file,indent=2,sort_keys=True)
                launch_file.write('\n')
        reason = None
        maxima = {"rss_bytes": 0, "swap_bytes": 0, "cgroup_memory_bytes": 0,
                  "cgroup_peak_bytes": 0,
                  "cgroup_file_bytes": 0, "gpu_used_mib": 0, "gpu_temperature_c": 0,
                  "cpu_tctl_c": 0, "nvme_composite_c": 0,
                  "direct_model_fds": 0, "buffered_model_fds": 0}
        last = {}
        mapped = None
        mapped_hash_cache = {}
        ready_elapsed_s = None
        resource_gate=RuntimeGuard(resource_protocol,manifest['cgroup_start']) if prospective else None
        first_sample_t=None
        last_sample_t=None
        missing_since=None
        try:
            while process.poll() is None:
                collection_start = time.monotonic()
                status = proc_status(process.pid)
                # /proc/status can disappear between the loop's poll and this
                # read. Never publish a partial process sample or interpret an
                # absent VmSwap/VmRSS as zero. A normal exit is checked below.
                if not all(key in status for key in ("VmRSS", "VmSwap", "VmHWM")):
                    try:
                        # A dying process can briefly expose only /proc/io while
                        # waitpid has not reaped it yet. This is a terminal race
                        # only if it really exits within this bounded interval.
                        process.wait(timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        reason = "REQUIRED_PROCESS_TELEMETRY_MISSING"
                        stop_own_group(process)
                        break
                avail = mem_available()
                gpu = gpu_state(prospective=prospective)
                thermal = thermal_state(prospective=prospective)
                cg = cgroup_state()
                if prospective and (not gpu or not thermal or avail is None or not cg):
                    gpu = gpu_state(prospective=True)
                    thermal = thermal_state(prospective=True)
                    avail = mem_available()
                    cg = cgroup_state()
                    elapsed_missing=time.monotonic()-t0
                    if not gpu or not thermal or avail is None or not cg:
                        missing_since=elapsed_missing if missing_since is None else missing_since
                        if elapsed_missing-missing_since >= resource_contract['telemetry']['loss_persistence_s']:
                            reason='PROSPECTIVE_TELEMETRY_MISSING_PERSISTED'
                            stop_own_group(process);break
                        time.sleep(0.5);continue
                if prospective:missing_since=None
                fds = model_fd_state(process.pid, model_path)
                try:
                    identity = process_identity(process.pid)
                    if identity != launch_identity:
                        reason = "PROCESS_IDENTITY_CHANGED"
                        stop_own_group(process)
                        break
                    if ready_elapsed_s is None and a.ready_marker and \
                       a.ready_marker in Path(str(stem)+".stdout").read_text(errors="replace"):
                        ready_elapsed_s = round(time.monotonic()-t0,3)
                    if ready_elapsed_s is not None or not a.ready_marker:
                        candidate_mapped = mapped_backend_libraries(process.pid, backend_dir,
                                                                     mapped_hash_cache)
                        if candidate_mapped:
                            mapped = candidate_mapped
                except (OSError, ValueError, StopIteration):
                    if process.poll() is None:
                        reason = "PROCESS_IDENTITY_OR_MAPS_MISSING"
                        stop_own_group(process)
                    break
                sample = {"elapsed_s": round(time.monotonic() - t0, 3), "pid": process.pid, "proc": status,
                          "process_identity": identity,
                          "mem_available_bytes": avail, "gpu": gpu, "thermal": thermal, "cgroup": cg,
                          "model_fds": fds,"collection_s":time.monotonic()-collection_start}
                if prospective:
                    sample['resource_observation']={'host_psi_full_avg10':host_pressure(),
                                                    'power':live_power()}
                    if resource_contract.get('execution_class') == 'FILE_PAGING':
                        rollup=live_smaps_rollup(process)
                        if rollup is None:break
                        sample['smaps_rollup'] = rollup
                samples.write(json.dumps(sample,allow_nan=False) + "\n")
                samples.flush()
                last = sample
                if first_sample_t is None:first_sample_t=sample['elapsed_s']
                if prospective and last_sample_t is not None and \
                   sample['elapsed_s']-last_sample_t>resource_contract['telemetry']['max_gap_s']:
                    reason='PROSPECTIVE_TELEMETRY_GAP'
                    stop_own_group(process);break
                last_sample_t=sample['elapsed_s']
                maxima["rss_bytes"] = max(maxima["rss_bytes"], status["VmRSS"])
                maxima["swap_bytes"] = max(maxima["swap_bytes"], status["VmSwap"])
                if cg:
                    maxima["cgroup_memory_bytes"] = max(maxima["cgroup_memory_bytes"], cg["memory_current"] or 0)
                    maxima["cgroup_peak_bytes"] = max(maxima["cgroup_peak_bytes"], cg["memory_peak"] or 0)
                    maxima["cgroup_file_bytes"] = max(maxima["cgroup_file_bytes"], cg["memory_stat"].get("file", 0))
                if gpu:
                    maxima["gpu_used_mib"] = max(maxima["gpu_used_mib"], gpu["used_mib"])
                    maxima["gpu_temperature_c"] = max(maxima["gpu_temperature_c"], gpu["temperature_c"])
                if thermal:
                    maxima['cpu_tctl_c']=max(maxima['cpu_tctl_c'],thermal.get('cpu_tctl_c',0))
                    nvme_values=(thermal.get('nvme_composite_by_sensor',{}).values()
                                 if prospective else [thermal.get('nvme_composite_c',0)])
                    maxima['nvme_composite_c']=max(maxima['nvme_composite_c'],*nvme_values)
                if fds:
                    maxima["direct_model_fds"] = max(maxima["direct_model_fds"], fds["direct"])
                    maxima["buffered_model_fds"] = max(maxima["buffered_model_fds"], fds["buffered"])
                if sample["elapsed_s"] > a.timeout_s:
                    reason = "TIMEOUT"
                elif prospective:
                    try:
                        reason=resource_gate.check(sample)
                    except (ResourcePolicyError,KeyError,TypeError) as exc:
                        reason=f'PROSPECTIVE_TELEMETRY_INVALID:{type(exc).__name__}:{exc}'
                elif a.require_telemetry and (not status or not cg or not gpu or not thermal or avail is None or
                                              "cpu_tctl_c" not in thermal or "nvme_composite_c" not in thermal):
                    reason = "REQUIRED_TELEMETRY_MISSING"
                elif status["VmSwap"] > 0:
                    reason = "SWAP_USED"
                elif cg and cg["swap_current"] and cg["swap_current"] > 0:
                    reason = "CGROUP_SWAP_USED"
                elif cg and manifest["cgroup_start"] and cg["events"].get("oom", 0) > manifest["cgroup_start"]["events"].get("oom", 0):
                    reason = "CGROUP_OOM"
                elif cg and manifest["cgroup_start"] and any(
                        cg[group].get(event, 0) > manifest["cgroup_start"][group].get(event, 0)
                        for group in ("events", "events_local") for event in ("oom", "oom_kill")):
                    reason = "CGROUP_OOM_OR_KILL"
                elif cg and manifest["cgroup_start"] and not a.allow_cgroup_max_reclaim and cg["events"].get("max", 0) > manifest["cgroup_start"]["events"].get("max", 0):
                    reason = "CGROUP_LIMIT_HIT"
                elif cg and manifest["cgroup_start"] and not a.allow_cgroup_max_reclaim and \
                     cg["events_local"].get("max", 0) > manifest["cgroup_start"]["events_local"].get("max", 0):
                    reason = "CGROUP_LOCAL_LIMIT_HIT"
                elif cg and cg["memory_peak"] is not None and cg["memory_max"] is not None and cg["memory_peak"] > cg["memory_max"]:
                    reason = "CGROUP_PEAK_EXCEEDED"
                elif a.max_cgroup_gib is not None and cg and cg["memory_peak"] is not None and \
                     cg["memory_peak"] > a.max_cgroup_gib * 2**30:
                    reason = "CGROUP_RESERVATION_GUARD"
                elif status["VmRSS"] > a.max_rss_gib * 2**30:
                    reason = "RSS_GUARD"
                elif avail is not None and avail < a.min_available_gib * 2**30:
                    reason = "HOST_HEADROOM_GUARD"
                elif gpu and gpu["used_mib"] > a.max_gpu_mib:
                    reason = "GPU_GUARD"
                elif a.max_cpu_c is not None and thermal and thermal.get("cpu_tctl_c", 0) > a.max_cpu_c:
                    reason = "CPU_THERMAL_GUARD"
                elif a.max_gpu_c is not None and gpu and gpu["temperature_c"] > a.max_gpu_c:
                    reason = "GPU_THERMAL_GUARD"
                elif a.max_nvme_c is not None and thermal and thermal.get("nvme_composite_c", 0) > a.max_nvme_c:
                    reason = "NVME_THERMAL_GUARD"
                if reason:
                    stop_own_group(process)
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            reason = "INTERRUPTED"
            stop_own_group(process)
        except Exception as exc:
            reason=f'MONITOR_ERROR:{type(exc).__name__}:{exc}'
            stop_own_group(process)
        finally:
            stop_own_group(process)
            if a.stdin_file:
                stdin.close()
        rc = process.returncode
        if a.collect_start_inventory and Path(str(stem)+'.owner-stop.json').is_file() and reason is None:
            reason = 'INTERRUPTED_BY_OWNER'

    manifest.update({"ended_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "elapsed_s": round(time.monotonic() - t0, 3), "returncode": rc,
                     "stop_reason": reason, "maxima": maxima, "last_sample": last,
                     "stdout_path": str(stem) + ".stdout", "stderr_path": str(stem) + ".stderr",
                     "cgroup_end": cgroup_state()})
    manifest["mapped_backend_libraries_sha256"] = mapped
    manifest["ready_elapsed_s"] = ready_elapsed_s
    expected_libs = manifest["backend_libraries_sha256"]
    manifest["mapped_libraries_match_ldd"] = mapped_libraries_match(expected_libs, mapped)
    if prospective and reason is None:
        reason=prospective_endpoint_reason(
            first_sample_t,last_sample_t,manifest['elapsed_s'],
            manifest['cgroup_end'],manifest['cgroup_start'],resource_contract)
        if reason is not None:manifest['stop_reason']=reason
    if a.require_telemetry and not manifest["mapped_libraries_match_ldd"] and reason is None:
        reason = "MAPPED_LIBRARY_IDENTITY_MISMATCH"
        manifest["stop_reason"] = reason
    if a.ready_marker and ready_elapsed_s is None and reason is None:
        reason = "READY_MARKER_MISSING"
        manifest["stop_reason"] = reason
    if model_path:
        manifest["artifact_identity"]["stat_at_end"] = file_identity(model_path)
        if manifest["artifact_identity"]["stat_at_launch"] != \
                manifest["artifact_identity"]["stat_at_end"] and reason is None:
            reason = "MODEL_FILE_IDENTITY_CHANGED"
            manifest["stop_reason"] = reason
    manifest["output_sha256"] = {suffix: sha256(str(stem) + suffix)
                                 for suffix in (".stdout", ".stderr", ".samples.jsonl")}
    temporary = Path(str(stem) + ".json.tmp")
    final = Path(str(stem) + ".json")
    with temporary.open("x") as manifest_file:
        manifest_file.write(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
        manifest_file.flush()
        os.fsync(manifest_file.fileno())
    os.link(temporary, final)  # atomic no-replace on this filesystem
    temporary.unlink()
    print(json.dumps({k: manifest[k] for k in ("run_id", "elapsed_s", "returncode", "stop_reason", "maxima")}))
    return 0 if rc == 0 and reason is None else 1


if __name__ == "__main__":
    sys.exit(main())
