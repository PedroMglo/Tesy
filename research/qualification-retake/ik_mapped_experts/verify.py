"""Compile the pinned ik worker witness and bind its requests to the C283 inventory."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

PIN = "7a5d90009b7ae55d3239cdd33244977c4eb10ff6"
TREE = "a1706c85dc11d32b0fc34e20d699066a88b56201"
INVENTORY = "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82"
SIZE = 63_387_346_208
STRIDE = 4_406_400
ROLES = ("gate", "up", "down")
HERE = Path(__file__).resolve().parent
ENV = {"LC_ALL": "C", "PATH": "/usr/bin:/bin", "OMP_NUM_THREADS": "1"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def output(args, **kwargs):
    return subprocess.check_output(args, text=True, env=ENV, **kwargs).strip()


def revision(directory):
    return output(["git", "-C", directory, "rev-parse", "HEAD", "HEAD^{tree}"]).splitlines()


def require_clean(directory):
    need(not output(["git", "-C", directory, "status", "--porcelain"]), "dirty checkout")


def layer_geometry(raw):
    header, *rows = [json.loads(line) for line in raw.splitlines()]
    need(
        (header["gguf_version"], header["alignment"], header["data_offset"]) == (3, 32, 13_022_240)
        and header["tensor_count"] == len(rows) == 687,
        "GGUF metadata",
    )
    by_name = {t["name"]: t for t in rows}
    need(len(by_name) == len(rows), "duplicate tensor")
    layers = []
    for layer in range(36):
        bases = []
        for role in ROLES:
            for kind, shape, dtype, size in (
                ("weight", [2880, 2880, 128], "mxfp4", 128 * STRIDE),
                ("bias", [2880, 128], "f32", 128 * 2880 * 4),
            ):
                t = by_name[f"blk.{layer}.ffn_{role}_exps.{kind}"]
                base = t["data_offset"]
                need(
                    (t["shape"], t["tensor_type"], t["n_bytes"]) == (shape, dtype, size)
                    and base == header["data_offset"] + t["relative_data_offset"]
                    and base % header["alignment"] == 0
                    and header["data_offset"] <= base <= SIZE - size,
                    "expert dimensions or addresses",
                )
                if kind == "weight":
                    bases.append(base)
        layers.append(bases)
    intervals = sorted((base, base + 128 * STRIDE) for bases in layers for base in bases)
    need(
        all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:], strict=False)), "aliased weights"
    )
    return layers


def run(args, out):
    src, build = args.source.resolve(), args.build.resolve()
    lib = args.library.resolve(strict=True)
    need(lib.is_relative_to(build) and sha(lib) == args.library_sha256, "GGML library identity")
    require_clean(src)
    require_clean(HERE)
    need(revision(src) == [PIN, TREE], "external pin")
    cache = (build / "CMakeCache.txt").read_text().splitlines()
    for expected in (
        f"CMAKE_HOME_DIRECTORY:INTERNAL={src}",
        "GGML_CUDA:BOOL=OFF",
        "GGML_IQK_MUL_MAT:BOOL=ON",
        "GGML_IQK_FLASH_ATTENTION:BOOL=ON",
        "GGML_CCACHE:BOOL=OFF",
    ):
        need(expected in cache, "GGML build configuration: " + expected)
    raw = args.inventory.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == INVENTORY, "C283 digest")
    layers = layer_geometry(raw)
    native = HERE / "native.cpp"
    worker = src / "ggml/src/ggml-moe-prefetch.cpp"
    binary = out / "mapped-experts"
    cmd = [
        "/usr/bin/c++",
        "-std=c++17",
        "-O1",
        "-pthread",
        "-I" + str(src / "ggml/include"),
        "-I" + str(src / "ggml/src"),
        "-I" + str(src / "vendor"),
        str(native),
        str(worker),
        str(lib),
        "-Wl,--wrap=mincore,--wrap=madvise",
        "-Wl,-rpath," + str(lib.parent),
        "-o",
        str(binary),
    ]
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(cmd, env=ENV, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=90)
    linked = {}
    for line in output(["ldd", str(binary)]).splitlines():
        match = re.search(r"^\s*(\S+)\s+=>\s+(/\S+)", line)
        if match:
            soname, dest = match.groups()
            path = Path(dest).resolve(strict=True)
            linked[soname] = {"sha256": sha(path), "file": path.name}
            if soname.startswith("libggml."):
                need(path == lib, "GGML resolved elsewhere")
    need(any(n.startswith("libggml.") for n in linked), "missing GGML")
    need("undefined symbol:" not in output(["ldd", "-r", lib]), "unresolved GGML symbol")
    with (out / "native.stdout").open("xb") as log, (out / "native.stderr").open("xb") as err:
        subprocess.run(
            ["prlimit", "--as=3221225472", "--cpu=30", str(binary), *map(str, layers[0])],
            env=ENV,
            check=True,
            timeout=30,
            stdout=log,
            stderr=err,
        )
    result = json.loads((out / "native.stdout").read_bytes())
    need(result["status"] == "PASS_IK_MAPPED_EXPERTS" and result["cases"], "native evidence")
    return {
        "status": "PASS_IK_MAPPED_EXPERT_OPERATOR",
        "external_revision": revision(src),
        "tesy_revision": revision(HERE),
        "inventory_sha256": INVENTORY,
        "layer0_original_offsets_gate_up_down": layers[0],
        "layers": len(layers),
        "three_matrix_bytes_per_layer": 3 * 128 * STRIDE,
        "total_expert_matrix_bytes": len(layers) * 3 * 128 * STRIDE,
        "cpu_build": {
            "compiler": output(["/usr/bin/c++", "--version"]).splitlines()[0],
            "cmake_cache_sha256": sha(build / "CMakeCache.txt"),
            "linked": linked,
            "worker_sha256": sha(worker),
            "native_cpp_sha256": sha(native),
            "binary_sha256": sha(binary),
        },
        "native_stdout_sha256": sha(out / "native.stdout"),
        "native": result,
        "model_loads": 0,
        "gpu_compute": False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "build", "library", "inventory", "new-output-dir"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--library-sha256", required=True)
    args = ap.parse_args()
    out = args.new_output_dir.resolve()
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        receipt = run(args, out)
    except Exception as error:
        (out / "FAIL.json").write_text(json.dumps({"status": "FAIL", "error": str(error)}) + "\n")
        raise
    with (out / "receipt.json").open("x") as target:
        json.dump(receipt, target, indent=2, sort_keys=True)
        target.write("\n")
    print(receipt["status"], sha(out / "receipt.json"))


if __name__ == "__main__":
    os.umask(0o077)
    main()
