"""Bind the historical ik ELF and kernel-matched Fedora providers without changing the host."""

import hashlib
import os
import re
import subprocess
from pathlib import Path

VERSION = "620.73.04"
DRIVER = "33d4cbb6bc86ccc76c1e60af3b83c316ea49d7cb311efa79efc8ade96114cd8e"


def need(ok, msg):
    if not ok:
        raise ValueError(msg)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def rpm_files(paths):
    out = {}
    for p in sorted(set(paths)):
        pkg = subprocess.check_output(
            ["rpm", "-qf", "--qf", "%{NAME} %{VERSION}", p], text=True
        ).split()
        need(
            len(pkg) == 2 and pkg[1] == VERSION and pkg[0].startswith("xorg-x11-drv-nvidia"),
            "driver RPM " + str(p),
        )
        listing = subprocess.check_output(
            ["rpm", "-q", "--qf", "[%{FILENAMES} %{FILEDIGESTS}\\n]", pkg[0] + ".x86_64"], text=True
        )
        hits = [line.split()[1] for line in listing.splitlines() if line.startswith(str(p) + " ")]
        digest = sha(p)
        need(hits == [digest], "RPM file digest " + str(p))
        out[str(p)] = digest
    return out


def system_loader(exe, old, obj, *, llama_dir=None):
    driver_dir = Path("/usr/lib64")
    cuda = (driver_dir / "libcuda.so.1").resolve(strict=True)
    need(cuda.name == "libcuda.so." + VERSION and sha(cuda) == DRIVER, "system CUDA")
    llama_dir = obj / "src" if llama_dir is None else llama_dir
    search = [str(obj / "ggml/src"), str(llama_dir), "/usr/local/cuda-13.3/lib64"]
    env = dict(
        PATH="/usr/bin:/bin",
        LC_ALL="C",
        LD_LIBRARY_PATH=os.pathsep.join(search),
        CUDA_VISIBLE_DEVICES="0",
        CUDA_CACHE_DISABLE="1",
        GGML_CUDA_NO_PINNED="1",
        GGML_MOE_PREFETCH_AHEAD="0",
        OMP_NUM_THREADS="8",
    )
    ld = Path("/lib64/ld-linux-x86-64.so.2")
    deps = subprocess.check_output([ld, "--list", exe], text=True, env=env, timeout=10)
    p = subprocess.run(
        ["/usr/bin/ldd", "-r", exe], text=True, capture_output=True, env=env, timeout=15
    )
    need(
        p.returncode == 0
        and not re.search("not found|undefined symbol|/stubs/", deps + p.stdout + p.stderr),
        "unresolved dependency",
    )
    now = {
        n: str(Path(path).resolve(strict=True))
        for n, path in re.findall(r"^\s*(\S+) => (/\S+) \(0x", deps, re.M)
    }
    now[ld.name] = str(ld.resolve())
    need(set(now) == set(old["closure"]), "loader names")
    paths = {}
    for n, path in now.items():
        exp = {"file": str(cuda), "sha256": DRIVER} if n == "libcuda.so.1" else old["closure"][n]
        need(path == exp["file"] and sha(Path(path)) == exp["sha256"], "loader identity " + n)
        paths[path] = exp["sha256"]
    need(
        all(
            now[Path(n).name]
            == str(
                ((llama_dir / "libllama.so") if n == "src/libllama.so" else obj / n).resolve(
                    strict=True
                )
            )
            for n in old["libraries"]
        ),
        "ik provider",
    )
    aux = [
        driver_dir / name
        for name in (
            "libcuda.so.1",
            "libnvidia-gpucomp.so." + VERSION,
            "libnvidia-ptxjitcompiler.so.1",
            "libnvidia-nvvm70.so.4",
            "libnvidia-nvvm.so.4",
            "libnvidia-ml.so.1",
        )
    ]
    audited = rpm_files([p.resolve(strict=True) for p in aux] + [Path("/usr/bin/nvidia-smi")])
    return env, paths, audited
