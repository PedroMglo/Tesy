"""Select the installed NVML for the running kernel for a single CPU-only campaign."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

NVML = "1b310cec5baddefef24c0d4b6cec982f1a58e2cc77454de7f7da9809bd9e9ad3"
SMI = "616dd34c46398fdd01b73eea69bef30d1388698d494a6e2bc187857f38a938ea"
VERSION = "620.70.06"


def sha(path):
    with path.open("rb") as inp:
        return hashlib.file_digest(inp, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-library", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.new_output_dir
    out.mkdir(exist_ok=False)
    library = args.installed_library.resolve(strict=True)
    cli = Path("/usr/bin/nvidia-smi")
    kernel = Path("/sys/module/nvidia/version").read_text().strip()
    if kernel != VERSION or sha(library) != NVML or sha(cli) != SMI:
        raise ValueError("kernel, tool or installed NVML differs from the diagnostic")
    libs = out / "lib"
    libs.mkdir()
    (libs / "libnvidia-ml.so.1").symlink_to(library)
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": str(libs.resolve())}
    query = "--query-gpu=pci.bus_id,name,memory.total,memory.used,temperature.gpu,driver_version"
    cmd = [str(cli), query, "--format=csv,noheader,nounits"]
    probe = subprocess.run(cmd, env={**env, "LD_DEBUG": "libs"}, capture_output=True, timeout=10)
    probe.check_returncode()
    resolved = any(
        "calling init:" in row and Path(row.split("calling init:")[-1].strip()).samefile(library)
        for row in probe.stderr.decode().splitlines()
        if "calling init:" in row and "libnvidia-ml" in row
    )
    fields = [v.strip() for v in probe.stdout.decode().strip().split(",")]
    if not resolved or len(fields) != 6 or fields[-1] != kernel:
        raise ValueError("active telemetry did not use the matched provider")
    receipt = {
        "status": "PASS_CPU_CAMPAIGN_MONITOR",
        "nvml_sha256": NVML,
        "nvidia_smi_sha256": SMI,
        "kernel_driver": kernel,
        "reported_driver": fields[-1],
        "gpu": fields[1],
        "gpu_total_mib": int(fields[2]),
        "loader_verified": resolved,
    }
    with (out / "receipt.json").open("x") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
        f.write("\n")
    print(receipt["status"])


if __name__ == "__main__":
    main()
