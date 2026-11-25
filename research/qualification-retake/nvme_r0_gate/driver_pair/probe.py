"""Check the historical R0 CUDA driver at the enumeration boundary only."""

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

R0_DRIVER = "aa6bd5117c0c66bb804ec63b31b8b5d54130259b1079941b9e00e6b928e8ed71"


def inspect_driver(name):
    cuda = ctypes.CDLL(name)
    version = ctypes.c_int()
    count = ctypes.c_int()
    rc = cuda.cuInit(0)
    error = ctypes.c_char_p()
    cuda.cuGetErrorName(rc, ctypes.byref(error))
    version_rc = cuda.cuDriverGetVersion(ctypes.byref(version))
    count_rc = cuda.cuDeviceGetCount(ctypes.byref(count))
    devices = []
    if rc == count_rc == 0:
        for i in range(count.value):
            device = ctypes.c_int()
            label = ctypes.create_string_buffer(128)
            bus = ctypes.create_string_buffer(32)
            if any(
                (
                    cuda.cuDeviceGet(ctypes.byref(device), i),
                    cuda.cuDeviceGetName(label, len(label), device),
                    cuda.cuDeviceGetPCIBusId(bus, len(bus), device),
                )
            ):
                raise ValueError("device identification failed")
            devices.append({"name": label.value.decode(), "pci": bus.value.decode()})
    mappings = {
        Path(line.split()[-1])
        for line in Path("/proc/self/maps").read_text().splitlines()
        if "/libcuda.so." in line
    }
    if len(mappings) != 1:
        raise ValueError("ambiguous CUDA driver provider")
    mapped = mappings.pop()
    with mapped.open("rb") as lib:
        digest = hashlib.file_digest(lib, "sha256").hexdigest()
    return {
        "init_rc": rc,
        "init_error": error.value.decode(),
        "version_rc": version_rc,
        "driver_api": version.value,
        "count_rc": count_rc,
        "devices": devices,
        "provider": mapped.name,
        "provider_sha256": digest,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-driver", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.new_output_dir.mkdir(exist_ok=False, mode=0o700)
    with args.installed_driver.open("rb") as f:
        if hashlib.file_digest(f, "sha256").hexdigest() != R0_DRIVER:
            raise ValueError("historical R0 driver differs")
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
    result = {}
    for mode, provider in (("system", "libcuda.so.1"), ("r0", str(args.installed_driver))):
        proc = subprocess.run(
            [sys.executable, "-I", "-B", __file__, "--child", provider],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        result[mode] = json.loads(proc.stdout)
    r0 = result["r0"]
    result["kernel_module"] = Path("/sys/module/nvidia/version").read_text().strip()
    ok = (
        r0["init_rc"] == r0["version_rc"] == r0["count_rc"] == 0
        and r0["provider_sha256"] == R0_DRIVER
        and r0["devices"] == [{"name": "NVIDIA GeForce RTX 4060 Laptop GPU", "pci": "0000:c4:00.0"}]
    )
    result["status"] = "PASS_R0_DRIVER_ENUMERATION_ONLY" if ok else "FAIL_PRESERVED"
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(result["status"])
    return int(not ok)


if __name__ == "__main__":
    os.umask(0o077)
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        print(json.dumps(inspect_driver(sys.argv[2])))
    else:
        sys.exit(main())
