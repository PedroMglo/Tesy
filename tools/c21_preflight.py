#!/usr/bin/env python3
"""Capture the physical-host identity for C21 cache OFF/ON pairs."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess

from c2_gate import strict_json
from c8_observer_runner import model_stat
from c9_server_admission import MODEL, configuration
from c18_cpu_telemetry import capture as cpu_capture


def call(*argv):
    return subprocess.check_output(argv, text=True, timeout=15).strip()


def scope_test():
    output = call("systemd-run", "--user", "--scope", "-p", "MemoryMax=19327352832",
                  "-p", "MemorySwapMax=0", "--", "python3", "-c",
                  'import json,sys;sys.path.insert(0,"tools");import c2_server_run as s;'
                  'c=s.cgroup_state();print(json.dumps({"path":c["path"],'
                  '"memory_max":c["memory_max"],"swap_max":c["swap_max"],'
                  '"swap_current":c["swap_current"]}))')
    result = strict_json(output.splitlines()[-1])
    result["status"] = "PASS" if result["memory_max"] == 19327352832 and \
        result["swap_max"] == 0 and result["swap_current"] == 0 else "FAIL"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol, _ = configuration(root)
    sensors = strict_json(call("sensors", "-j"))
    gpu = call("nvidia-smi", "--query-gpu=name,memory.total,memory.used,temperature.gpu,driver_version",
               "--format=csv,noheader,nounits")
    apps = call("nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory",
                "--format=csv,noheader")
    scope = scope_test()
    cpu_diagnostics = cpu_capture()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 18367))
    prior_model = strict_json(Path('results/c20-prefix-pairs-20260927T1857Z/preflight.json').read_text())['model']
    if prior_model['stat'] != model_stat():
        raise ValueError('model metadata changed since C20 full SHA verification')
    model_sha = prior_model['sha256']
    backend = Path("/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/streaming")
    report = {"schema": "c21-preflight-v1", "utc": datetime.now(timezone.utc).isoformat(),
              "cpu_policy": {"tjmax_c": 100, "warning_c": 95,
                             "tjmax_official_source": "https://www.amd.com/en/products/processors/laptop/ryzen/ai-300-series/amd-ryzen-ai-9-hx-370.html",
                             "C19_dependency": "one P12 exact-prefix ON mechanism PASS",
                             "C20_dependency": "first OFF arm PASS; ON blocked before model by strict thermal matching; no paired timing"},
              "cpu_diagnostics": cpu_diagnostics,
              "cooling_condition": "changed_physical_placement (owner report)",
              "ambient_temperature": "UNKNOWN", "power_source": "AC" if
                 Path("/sys/class/power_supply/AC0/online").read_text().strip() == "1" else "BATTERY",
              "power_profile": call("powerprofilesctl", "get"),
              "fan_profile_if_observable": "fan RPM observed; policy not directly readable",
              "fan_rpm": next((v for k,v in sensors.items() if k.startswith("asus-") and
                               "cpu_fan" in v), {}),
              "cpu_tctl_c": next(v["Tctl"]["temp1_input"] for k,v in sensors.items()
                                  if k.startswith("k10temp-")),
              "nvme_composite_c": next(v["Composite"]["temp1_input"] for k,v in sensors.items()
                                        if k.startswith("nvme-")),
              "gpu_csv": gpu, "gpu_compute_apps": apps,
              "host_kernel": call("uname", "-r"),
              "cpu_model": next(line.split(":",1)[1].strip() for line in
                                Path("/proc/cpuinfo").read_text().splitlines()
                                if line.startswith("model name")),
              "memory": {key: int(value.split()[0])*1024 for key,value in
                         (line.split(":",1) for line in Path("/proc/meminfo").read_text().splitlines())
                         if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")},
              "filesystem": call("findmnt", "-T", str(root), "-no", "TARGET,SOURCE,FSTYPE"),
              "free_bytes": os.statvfs(root).f_bavail*os.statvfs(root).f_frsize,
              "port_18367_free": True,
              "model": {"path": str(MODEL), "stat": model_stat(), "sha256": model_sha,
                        "full_sha_provenance": "C20 preflight with identical dev/inode/size/mtime/ctime; C21 admission rechecks stat"},
              "backend": {"head": call("git", "-C", str(backend), "rev-parse", "HEAD"),
                          "tree": call("git", "-C", str(backend), "rev-parse", "HEAD^{tree}"),
                          "dirty": call("git", "-C", str(backend), "status", "--porcelain"),
                          "binary_sha256": protocol["identity"]["binary_sha256"],
                          "library_sha256": protocol["identity"]["library_sha256"]},
              "scope_model_free_test": scope,
              "guard_status": "READY_FOR_IDLE_ADMISSION" if model_sha ==
                  "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
                  and scope["status"] == "PASS" and not apps and
                  cpu_diagnostics['processor_cooling_max_state'] == 0 and
                  not call("git", "-C", str(backend), "status", "--porcelain")
                  else "BLOCKED_IDENTITY_OR_GPU"}
    with (root / "preflight.json").open("x") as out:
        json.dump(report, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    print(json.dumps({"status": report["guard_status"], "gpu": gpu,
                      "cpu_c": report["cpu_tctl_c"], "nvme_c": report["nvme_composite_c"]}))


if __name__ == "__main__":
    main()
