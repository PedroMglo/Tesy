"""Build or run a bounded RADV host-import fixture. Both destinations must be new."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = "61baf8c9fa4302c2d5d2b504c24671766e644d452e058000863b7d94f3946617"
HEADERS = {
    "vulkan_core.h": "3a62b8e11fb3a0927b5a8c39bfba27d16775d84f4e735b7149eb072a43bd4089",
    "vk_platform.h": "dfca6a95c7b511fdcf731d09c30fc145ef1801bef53799f4bcfdbe00a936cd48",
}
ICD = Path("/usr/share/vulkan/icd.d/radeon_icd.x86_64.json")
DRIVER = Path("/usr/lib64/libvulkan_radeon.so")
LOADER = Path("/usr/lib64/libvulkan.so.1.4.341")
FILES = {
    ICD: "d1c36db1d658755b0cb325f991e337544f7a607a6f5c277e62b1de7d81d7a4c7",
    DRIVER: "c68620e85ebce1e98ee787e46211661130f94378c791a66c9433f2a9c4ab5641",
    LOADER: "a09dab583a4b8e50bba61d1284b46b9d6256300713aa1db6f20f06b2dbbe0696",
}
CXX = Path("/usr/bin/c++")
SYS = Path("/sys/class/drm/renderD128/device")
PAYLOAD = 13_219_200
CAP = 128 << 20


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def save(path, row):
    with path.open("x") as f:
        json.dump(row, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def seals():
    need(sha(HERE / "protocol.md") == PROTOCOL, "protocol seal")
    for p, h in FILES.items():
        need(sha(p) == h, "installed driver/loader/ICD changed")
    need(json.loads(ICD.read_bytes())["ICD"]["library_path"] == str(DRIVER), "ICD provider")
    return {
        "protocol": PROTOCOL,
        "native": sha(HERE / "host_import.cpp"),
        "runner": sha(Path(__file__)),
        "icd": FILES[ICD],
        "driver": FILES[DRIVER],
        "loader": FILES[LOADER],
    }


def build(include, out):
    need(all(sha(include / "vulkan" / n) == h for n, h in HEADERS.items()), "Khronos headers")
    args = [
        str(CXX),
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-missing-field-initializers",
        "-I",
        str(include),
        str(HERE / "host_import.cpp"),
        str(LOADER),
        "-o",
        str(out / "host-import"),
    ]
    with (out / "compiler.log").open("xb") as f:
        subprocess.run(args, check=True, timeout=20, stdout=f, stderr=subprocess.STDOUT)
    need((out / "host-import").stat().st_size < 2 << 20, "fixture binary size")
    return dict(
        status="PASS_BUILD_ONLY",
        header_commit="1d99b835ec3cd5a7fb2f2a2dd9a615ee2d1f0101",
        headers=HEADERS,
        compiler_sha256=sha(CXX),
        compiler_options=args[1:7],
        binary_sha256=sha(out / "host-import"),
        gpu_processes=0,
    )


def inventory():
    attrs = {k: (SYS / k).read_text().strip() for k in ("vendor", "device", "revision")}
    need(
        attrs == {"vendor": "0x1002", "device": "0x150e", "revision": "0xc1"}
        and SYS.resolve().name == "0000:c5:00.0"
        and (SYS / "driver").resolve().name == "amdgpu"
        and platform.release() == "7.3.4-200.fc44.x86_64",
        "AMD host deployment",
    )
    cpus = [
        s.split(":", 1)[1].strip()
        for s in Path("/proc/cpuinfo").read_text().splitlines()
        if s.startswith("model name")
    ]
    need(cpus and all("AMD Ryzen AI 9 HX 370" in name for name in cpus), "APU model")
    mem = {
        s.split(":")[0]: int(s.split()[1])
        for s in Path("/proc/meminfo").read_text().splitlines()
        if s.split(":")[0] in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    }
    thermal = {}
    for node in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        label = (node / "name").read_text().strip()
        if label in {"amdgpu", "k10temp", "nvme"}:
            thermal[node.name + "/" + label] = [
                int(p.read_text()) for p in sorted(node.glob("temp*_input"))
            ]
    ac = Path("/sys/class/power_supply/AC0/online").read_text().strip()
    need(ac == "1" and mem["MemAvailable"] > (1 << 20), "AC and memory for bounded fixture")
    return dict(
        kernel=platform.release(),
        cpu=cpus[0],
        pci="0000:c5:00.0",
        amd=attrs,
        drm_driver="amdgpu",
        memory_kib=mem,
        ac_online=True,
        sensor_millicelsius=thermal,
    )


def review(raw):
    lines = [line.split("\t") for line in raw.splitlines()]
    need(lines[-1] == ["PASS_HOST_IMPORT_COPY_ONLY"], "native terminal")

    def rows(k):
        return [r[1:] for r in lines if r[0] == k]

    def one(k):
        (v,) = rows(k)
        return v

    dev = one("device")
    align = int(dev[6])
    need(
        len(dev) == 7
        and dev[1:6] == ["radv", "0000:c5:00.0", "4098", "5390", "1"]
        and align > 0
        and align & (align - 1) == 0,
        "integrated RADV device",
    )
    heap = {int(k): {"bytes": int(n), "flags": int(f)} for k, n, f in rows("heap")}
    types = {int(k): {"heap": int(h), "flags": int(f)} for k, h, f in rows("type")}
    imports = []
    for n, ba, pointers, allowed, t, h, flags in (map(int, r) for r in rows("import")):
        need(
            types[t] == {"heap": h, "flags": flags}
            and flags & 6 == 6
            and pointers & allowed & (1 << t)
            and n >= PAYLOAD
            and n % align == 0
            and ba > 0,
            "import identity",
        )
        imports.append(
            dict(
                allocation_bytes=n,
                buffer_alignment=ba,
                pointer_type_bits=pointers,
                buffer_type_bits=allowed,
                memory_type=t,
                heap=h,
                flags=flags,
                imported_host_visible_device_local=bool(heap[h]["flags"] & 1 and flags & 1),
            )
        )
    peaks = [int(r[0]) for r in rows("scope_peak_bytes")]
    need(
        len(imports) == 2
        and len(peaks) == 2
        and max(peaks) <= CAP
        and one("providers") == ["RADV+loader+renderD128"],
        "FD, providers or charged scope",
    )
    gen = [list(map(int, r)) for r in rows("generation")]
    need(
        gen == [[i, PAYLOAD // 4, PAYLOAD // 4] for i in (1, 2)]
        and int(one("external_features")[0]) & 4
        and int(one("queue")[1]) & 2,
        "copy, negative control or queue",
    )
    return dict(
        device_name=dev[0],
        driver=dev[1],
        pci=dev[2],
        host_pointer_alignment=align,
        heaps=heap,
        types=types,
        imports=imports,
        queue_family=int(one("queue")[0]),
        queue_flags=int(one("queue")[1]),
        external_features=int(one("external_features")[0]),
        host_visible_device_local_types=[
            t for t, v in types.items() if v["flags"] & 3 == 3 and heap[v["heap"]]["flags"] & 1
        ],
        scope_peak_bytes=max(peaks),
        generations=gen,
        payload_bytes_per_copy=PAYLOAD,
        shader_dispatches=0,
        device_copy_commands=2,
        host_imports=2,
    )


def measure(a, out):
    info = a.build_dir / "receipt.json"
    binary = a.build_dir / "host-import"
    need(sha(info) == a.build_sha256, "private build receipt")
    b = json.loads(info.read_bytes())
    need(
        b["status"] == "PASS_BUILD_ONLY"
        and b["inputs"] == seals()
        and sha(binary) == b["binary_sha256"],
        "build/source pins",
    )
    before = inventory()
    save(out / "before.json", before)
    layers = out / "empty-layers"
    layers.mkdir()
    env = [
        "PATH=/usr/bin:/bin",
        "LC_ALL=C",
        "VK_DRIVER_FILES=" + str(ICD),
        "VK_LAYER_PATH=" + str(layers),
        "VK_IMPLICIT_LAYER_PATH=" + str(layers),
        "VK_LOADER_LAYERS_DISABLE=~implicit~",
        "MESA_SHADER_CACHE_DISABLE=true",
    ]
    unit = "tesy-igpu-rank-" + out.name
    need(unit.replace("-", "").isalnum() and len(unit) < 165, "scope identity")
    args = [
        "/usr/bin/systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "--unit",
        unit,
        "-p",
        "MemoryMax=134217728",
        "-p",
        "MemoryHigh=134217728",
        "-p",
        "MemorySwapMax=0",
        "--",
        "/usr/bin/env",
        "-i",
        *env,
        "/usr/bin/timeout",
        "-k",
        "1s",
        "9s",
        str(binary),
    ]
    start = time.monotonic()
    with (out / "native.tsv").open("xb") as stdout, (out / "native.stderr").open("xb") as stderr:
        child = subprocess.run(args, stdout=stdout, stderr=stderr, timeout=15, check=False)
    elapsed = time.monotonic() - start
    save(out / "after.json", inventory())
    raw = (out / "native.tsv").read_text()
    if child.returncode == 3 and raw.splitlines()[-1].startswith("NOT_ADMITTED\t"):
        return dict(
            status="NO_GO_HOST_IMPORT_ON_THIS_DEVICE",
            reason=raw.splitlines()[-1],
            wall_s=elapsed,
            binary_sha256=sha(binary),
            build_sha256=sha(info),
        )
    need(child.returncode == 0, "native code " + str(child.returncode) + "; see native.tsv/stderr")
    return dict(
        status="PASS_RADV_HOST_IMPORT_COPY_ONLY",
        proof=review(raw),
        wall_s=elapsed,
        build_sha256=sha(info),
        binary_sha256=sha(binary),
        native_sha256=sha(out / "native.tsv"),
        pre_sha256=sha(out / "before.json"),
        post_sha256=sha(out / "after.json"),
        stderr_sha256=sha(out / "native.stderr"),
        model_forwards=0,
        device_scope=unit + ".scope",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", action="store_true")
    p.add_argument("--headers", type=Path)
    p.add_argument("--build-dir", type=Path)
    p.add_argument("--build-sha256")
    p.add_argument("--new-output-dir", required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    try:
        inputs = seals()
        r = build(a.headers, out) if a.build else measure(a, out)
        r["inputs"] = inputs
    except Exception as e:
        r = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
